# -*- coding: utf-8 -*-
"""
Blade clearance exclusion
"""
import logging
from warnings import warn

import numpy as np
from affine import Affine
from rasterio import features as rio_features

from reVX.exclusions.base import AbstractBaseExclusionsMerger


logger = logging.getLogger(__name__)


class BladeClearanceExclusions(AbstractBaseExclusionsMerger):
    """Exclude whole regions where blade clearance is insufficient."""

    FEATURE_TYPES = {'blade clearance'}

    @property
    def description(self):
        """str: Description to be added to excl H5."""
        return ('Pixels with value 1 are excluded where local minimum blade '
                'clearance requirements are larger than the turbine\'s blade '
                'clearance ({} m).'.format(self._regulations.blade_clearance))

    @property
    def no_exclusions_array(self):
        """np.ndarray: Array representing no exclusions."""
        shape = (self.profile['height'], self.profile['width'])
        return np.zeros(shape, dtype=np.uint8)

    @property
    def exclusion_merge_func(self):
        """callable: Function to merge overlapping exclusion layers."""
        return np.maximum

    def pre_process_regulations(self):
        """Reduce regulations to only local blade clearance entries."""
        mask = self.regulations_table['Feature Type'].isin(self.FEATURE_TYPES)

        if not mask.any():
            msg = ('Found no local blade clearance regulations in '
                   'regulations table.')
            logger.warning(msg)
            warn(msg)

        self._regulations.df = (self.regulations_table[mask]
                                .reset_index(drop=True))

    def _local_exclusions_arguments(self, *__, **___):
        """Yield args needed for local blade clearance exclusions."""
        yield (self._regulations.blade_clearance, self.profile)

    @staticmethod
    def compute_local_exclusions(regulation_value, county, *args):
        """Compute local blade clearance exclusions

        Parameters
        ----------
        regulation_value : float | int
            Minimum blade clearance in meters.
        county : geopandas.GeoDataFrame
            Regulations for a single county.
        blade_clearance :  float | int
            Blade clearance of the turbine in meters.
        profile : dict
            Rasterio profile for the output exclusion raster. This is
            needed to ensure the output raster is properly georeferenced
            and aligned with the input data. The profile should contain
            at least the following keys: 'height', 'width', and
            'transform'. The 'height' and 'width' keys specify the
            dimensions of the output raster, while the 'transform' key
            provides the affine transformation needed to map pixel
            coordinates to geographic coordinates. The 'transform' can
            be provided as an Affine object or as a list/tuple of 6
            values that can be converted to an Affine object.
        """
        blade_clearance, profile = args
        shape = (profile['height'], profile['width'])

        meets_requirement = blade_clearance >= regulation_value
        if meets_requirement:
            return np.zeros(shape, dtype=np.uint8), (slice(None), slice(None))

        transform = profile['transform']
        if not isinstance(transform, Affine):
            transform = Affine(*transform)

        geometry = ((geom, 1) for geom in county.geometry
                    if geom is not None and not geom.is_empty)

        exclusions = rio_features.rasterize(geometry,
                                            out_shape=shape,
                                            transform=transform,
                                            fill=0,
                                            dtype=np.uint8)
        return exclusions, (slice(None), slice(None))

    def compute_generic_exclusions(self, *__, **___):
        """Return no exclusions because this mode is local-only"""
        return self.no_exclusions_array
