# -*- coding: utf-8 -*-
"""
Max height exclusion
"""
import logging
from warnings import warn

import numpy as np
from affine import Affine
from rasterio import features as rio_features

from reVX.exclusions.base import AbstractBaseExclusionsMerger


logger = logging.getLogger(__name__)


class HeightRestrictionExclusions(AbstractBaseExclusionsMerger):
    """Exclude whole regions where system height exceeds local limits."""

    FEATURE_TYPES = {'maximum height', 'maximum turbine height'}

    @property
    def description(self):
        """str: Description to be added to excl H5."""
        return ('Pixels with value 1 are excluded where local maximum '
                'height regulations are lower than the input system '
                'height ({} m).'.format(self._regulations.system_height))

    @property
    def no_exclusions_array(self):
        """np.ndarray: Array representing no exclusions."""
        return self.rasterizer.rasterize(shapes=None)

    @property
    def exclusion_merge_func(self):
        """callable: Function to merge overlapping exclusion layers."""
        return np.maximum

    def pre_process_regulations(self):
        """Reduce regulations to only local maximum height entries."""
        mask = self.regulations_table['Feature Type'].isin(self.FEATURE_TYPES)

        if not mask.any():
            msg = ('Found no local maximum height regulations in '
                   'regulations table.')
            logger.warning(msg)
            warn(msg)

        self._regulations.df = (self.regulations_table[mask]
                                .reset_index(drop=True)
                                .to_crs(crs=self.profile['crs']))
        logger.debug('Loaded and pre-processed maximum height regulations '
                     'for %d jurisdictions', len(self.regulations_table))

    def _local_exclusions_arguments(self, *__, **___):
        """Yield args needed for local height-restriction exclusions."""
        yield (self._regulations.system_height, self.rasterizer)

    @staticmethod
    def compute_local_exclusions(regulation_value, county, *args):
        """Compute local height restrictions

        Parameters
        ----------
        regulation_value : float | int
            Height limit in meters.
        county : geopandas.GeoDataFrame
            Regulations for a single county.
        system_height :  float | int
            Height of the system in meters.
        rasterizer : Rasterizer
            Rasterizer object used to rasterize the exclusion features.
        """
        system_height, rasterizer = args

        features = []
        if system_height > regulation_value:
            features = [geom for geom in county.geometry
                        if geom is not None and not geom.is_empty]

        return rasterizer.rasterize_within_window(
            features, county.total_bounds
        )

    def compute_generic_exclusions(self, *__, **___):
        """Return no exclusions because this mode is local-only"""
        return self.no_exclusions_array
