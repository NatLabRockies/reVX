# -*- coding: utf-8 -*-
"""
Blade clearance exclusion
"""
import logging
from warnings import warn

import numpy as np

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
        """np.array: Array representing no exclusions. """
        return self.rasterizer.rasterize(shapes=None)

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
                                .reset_index(drop=True)
                                .to_crs(crs=self.profile['crs']))
        logger.debug('Loaded and pre-processed blade clearance regulations '
                     'for %d jurisdictions', len(self.regulations_table))

    def _local_exclusions_arguments(self, *__, **___):
        """Yield args needed for local blade clearance exclusions."""
        yield (self._regulations.blade_clearance, self.rasterizer)

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
        rasterizer : Rasterizer
            Rasterizer object used to rasterize the exclusion features.
        """
        blade_clearance, rasterizer = args

        features = []
        if blade_clearance < regulation_value:
            features = [geom for geom in county.geometry
                        if geom is not None and not geom.is_empty]

        return rasterizer.rasterize_within_window(
            features, county.total_bounds
        )

    def compute_generic_exclusions(self, *__, **___):
        """Return no exclusions because this mode is local-only"""
        return self.no_exclusions_array
