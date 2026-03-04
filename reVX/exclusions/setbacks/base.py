# -*- coding: utf-8 -*-
"""
Base classes for setback exclusion computation
"""
import os
import logging
from warnings import warn
from abc import abstractmethod
from concurrent.futures import as_completed

import numpy as np
import geopandas as gpd
from shapely.ops import unary_union
from shapely.validation import make_valid
from rasterio import transform, coords

from rex.utilities import log_mem
from rex.utilities.execution import SpawnProcessPool
from reVX.handlers.geopackage import GPKGMeta
from reVX.exclusions.base import AbstractBaseExclusionsMerger
from reVX.exclusions.setbacks.functions import (
    parcel_buffer, positive_buffer, features_clipped_to_county,
    features_with_centroid_in_county)

logger = logging.getLogger(__name__)


BUFFERS = {
    "default": positive_buffer,
    "parcel": parcel_buffer,
}
"""Types of buffers available for setback calculations. """


FEATURE_FILTERS = {
    "centroid": features_with_centroid_in_county,
    "clip": features_clipped_to_county,
}
"""Types of feature filters available for setback calculations. """


class AbstractBaseSetbacks(AbstractBaseExclusionsMerger):
    """Base class for Setbacks Calculators"""

    def __init__(self, excl_fpath, regulations, features, hsds=False,
                 weights_calculation_upscale_factor=None):
        """

        Parameters
        ----------
        excl_fpath : str
            Path to .h5 file containing exclusion layers, will also be
            the location of any new setback layers
        regulations : `~reVX.exclusions.setbacks.regulations.SetbackRegulations`
            A `SetbackRegulations` object used to extract setback
            distances.
        features : str
            Path to file containing features to compute exclusions from.
        hsds : bool, optional
            Boolean flag to use h5pyd to handle .h5 'files' hosted on
            AWS behind HSDS. By default `False`.
        weights_calculation_upscale_factor : int, optional
            If this value is an int > 1, the output will be a layer with
            **inclusion** weight values instead of exclusion booleans.
            For example, a cell that was previously excluded with a
            a boolean mask (value of 1) may instead be converted to an
            inclusion weight value of 0.75, meaning that 75% of the area
            corresponding to that point should be included (i.e. the
            exclusion feature only intersected a small portion - 25% -
            of the cell). This percentage inclusion value is calculated
            by upscaling the output array using this input value,
            rasterizing the exclusion features onto it, and counting the
            number of resulting sub-cells excluded by the feature. For
            example, setting the value to `3` would split each output
            cell into nine sub-cells - 3 divisions in each dimension.
            After the feature is rasterized on this high-resolution
            sub-grid, the area of the non-excluded sub-cells is totaled
            and divided by the area of the original cell to obtain the
            final inclusion percentage. Therefore, a larger upscale
            factor results in more accurate percentage values. If `None`
            (or a value <= 1), this process is skipped and the output is
            a boolean exclusion mask. By default `None`.
        """
        super().__init__(excl_fpath, regulations, features, hsds)
        self.rasterizer.scale_factor = weights_calculation_upscale_factor
        self._features_meta = GPKGMeta(self._features)

    def __repr__(self):
        msg = "{} for {}".format(self.__class__.__name__, self._excl_fpath)
        return msg

    @property
    def description(self):
        """str: Description to be added to excl H5."""
        return ('{} computed with a base setback distance of {} and a '
                'multiplier of {} for a total generic setback value of {} '
                '(local exclusions may differ).'
                .format(self.__class__,
                        self._regulations.base_setback_dist,
                        self._regulations.multiplier,
                        self._regulations.generic))

    @property
    def no_exclusions_array(self):
        """np.array: Array representing no exclusions. """
        return self.rasterizer.rasterize(shapes=None)

    @property
    def exclusion_merge_func(self):
        """callable: Function to merge overlapping exclusion layers. """
        return np.minimum if self.rasterizer.inclusions else np.maximum

    def pre_process_regulations(self):
        """Reduce regulations to state corresponding to features."""
        feats_crs = self._features_meta.crs
        xmin, ymin, xmax, ymax = self._features_meta.bbox
        regulations_df = self.regulations_table.to_crs(feats_crs)
        regulations_df = regulations_df.cx[xmin:xmax, ymin:ymax]
        regulations_df = regulations_df.to_crs(crs=self.profile['crs'])
        self._regulations.df = regulations_df.reset_index(drop=True)

        mask = self._regulation_table_mask()
        if not mask.any():
            msg = "Found no local regulations!"
            logger.warning(msg)
            warn(msg)

        self._regulations.df = (self.regulations_table[mask]
                                .reset_index(drop=True))
        logger.debug('Loaded and processed setback regulations for {} counties'
                     .format(len(self.regulations_table)))

    def _local_exclusions_arguments(self, regulation_value, county):
        """Compile and return arguments to `compute_local_exclusions`. """
        logger.debug("Selecting county IDs using bounds {}"
                     .format(county.total_bounds))
        county = (county.buffer(regulation_value * 1.1)
                  .to_crs(self._features_meta.crs))
        ids = self._features_meta.feat_ids_for_bbox(county.total_bounds)
        logger.debug("Calculating setbacks for counties with IDs {}"
                     .format(ids))

        for start in range(0, len(ids), self.NUM_FEATURES_PER_WORKER):
            end = start + self.NUM_FEATURES_PER_WORKER
            yield (ids[start:end], self._features,
                   self._features_meta.primary_key_column, self.profile['crs'],
                   self.FEATURE_FILTER_TYPE, self.BUFFER_TYPE,
                   self.rasterizer)

    @staticmethod
    def compute_local_exclusions(regulation_value, county, *args):
        """Compute local features setbacks.

        This method will compute the setbacks using a county-specific
        regulations file that specifies either a static setback or a
        multiplier value that will be used along with the base setback
        distance to compute the setback.

        Parameters
        ----------
        regulation_value : float | int
            Setback distance in meters.
        county : geopandas.GeoDataFrame
            Regulations for a single county.
        features_ids : iterable of ints
            List of tuple (or other iterable) of integer values
            corresponding to the ID of the features in the GeoPackage
            to load and compute exclusions for. Note that these ID
            values are the internal SQL table ID's stored with the
            features, NOT the index of the features when loaded using
            :func:`geopandas.read_file`.
        features_fp : path-like
            Path to the GeoPackage file containing the features to be
            loaded and used for the exclusion calculation.
        col : str
            Namer of the primary key column in the main SQL table of the
            GeoPackage. This should be the name of the column under
            which the `features_ids` can be found.
        crs : str
            String representation of the Coordinate Reference System of
            the output exclusions array.
        features_filter_type : str
            Key from the :attr:`FEATURE_FILTERS` dictionary that points
            to the feature filter function to use. This feature filter
            function filters the loaded features such that they are
            localized to the county bounds.
        buffer_type : str
            Key from the :attr:`BUFFERS` dictionary that points to the
            feature buffer function to use.
        rasterizer : Rasterizer
            Instance of `Rasterizer` class used to rasterize the
            buffered county features.

        Returns
        -------
        setbacks : ndarray
            Raster array of setbacks
        slices : 2-tuple of `slice`
            X and Y slice objects defining where in the original array
            the exclusion data should go.
        """
        (features_ids, features_fp, col, crs, features_filter_type,
         buffer_type, rasterizer) = args
        logger.debug('- Computing setbacks for:\n{}'.format(county.iloc[0]))
        log_mem(logger)
        features = _load_features(features_ids, features_fp, col, crs)
        feature_bounds = _buffered_feature_bounds(features, rasterizer,
                                                  regulation_value)

        features = FEATURE_FILTERS[features_filter_type](features, county)
        features = BUFFERS[buffer_type](features, regulation_value)

        return rasterizer.rasterize_within_window(features, feature_bounds)

    def compute_generic_exclusions(self, max_workers=None):
        """Compute generic setbacks.

        This method will compute the setbacks using a generic setback
        of `base_setback_dist * multiplier`.

        Parameters
        ----------
        max_workers : int, optional
            Number of workers to use for exclusions computation, if 1
            run in serial, if > 1 run in parallel with that many
            workers, if `None` run in parallel on all available cores.
            By default `None`.

        Returns
        -------
        setbacks : ndarray
            Raster array of setbacks
        """
        generic_regulations_dne = (self._regulations.generic is None
                                   or np.isclose(self._regulations.generic, 0))
        if generic_regulations_dne:
            return self.no_exclusions_array

        max_workers = max_workers or os.cpu_count()
        ids = self._features_meta.feat_ids
        num_feats = self._features_meta.num_feats
        pk = self._features_meta.primary_key_column
        crs = self.profile['crs']
        exclusions = None
        if max_workers > 1:
            msg = ("Computing generic setbacks from {:,} features using {} "
                   "workers".format(num_feats, max_workers))
            logger.debug(msg)

            loggers = [__name__, 'reVX', 'rex']
            spp_kwargs = {"max_workers": max_workers, "loggers": loggers}
            with SpawnProcessPool(**spp_kwargs) as exe:
                exclusions = self._compute_generic_exclusions_in_chunks(
                    exe, max_workers, ids, pk, crs)
        else:
            logger.info("Computing generic setbacks from {} features in "
                        "serial.".format(num_feats))
            for start in range(0, len(ids), self.NUM_FEATURES_PER_WORKER):
                end = start + self.NUM_FEATURES_PER_WORKER
                out = _compute_exclusions(ids[start:end], self._features, pk,
                                          crs, self.BUFFER_TYPE,
                                          self._regulations.generic,
                                          self.rasterizer)
                new_exclusions, slices = out
                exclusions = self._combine_exclusions(exclusions,
                                                      new_exclusions,
                                                      slices=slices)
                msg = ("Computed generic setbacks for {:,}/{:,} features"
                       .format(end, num_feats))
                logger.info(msg)

        if exclusions is None:
            exclusions = self.no_exclusions_array

        return exclusions

    def _compute_generic_exclusions_in_chunks(self, exe, max_submissions,
                                              ids, pk, crs):
        """Compute exclusions in parallel using futures. """
        futures, exclusions = {}, None

        futures = []
        start_inds = range(0, len(ids), self.NUM_FEATURES_PER_WORKER)
        for ind, start in enumerate(start_inds, start=1):
            end = start + self.NUM_FEATURES_PER_WORKER
            future = exe.submit(_compute_exclusions, ids[start:end],
                                self._features, pk, crs,
                                self.BUFFER_TYPE,
                                self._regulations.generic,
                                self.rasterizer)
            futures.append(future)
            if ind % max_submissions == 0:
                exclusions = self._collect_ge_futures(futures, exclusions)
                msg = ("Computed generic setbacks for {:,}/{:,} features"
                       .format(end, len(ids)))
                logger.info(msg)

        exclusions = self._collect_ge_futures(futures, exclusions)
        return exclusions

    def _collect_ge_futures(self, futures, exclusions):
        """Collect all futures from the input dictionary. """
        logger.debug(f"Collecting {len(futures)} futures...")
        log_mem(logger)
        for future in as_completed(futures):
            new_exclusions, slices = future.result()
            exclusions = self._combine_exclusions(exclusions,
                                                  new_exclusions,
                                                  slices=slices)
        futures.clear()
        logger.debug("Finished collecting futures chunk!")
        log_mem(logger)
        return exclusions

    def _regulation_table_mask(self):
        """Return the regulation table mask for setback feature. """
        features = (self.regulations_table['Feature Type']
                    .isin(self.FEATURE_TYPES))
        not_excluded = ~(self.regulations_table['Feature Subtype']
                         .isin(self.FEATURE_SUBTYPES_TO_EXCLUDE))
        return features & not_excluded

    @property
    @abstractmethod
    def FEATURE_TYPES(self):
        """set: Feature type names using in the regulations file. """
        raise NotImplementedError

    @property
    @abstractmethod
    def FEATURE_SUBTYPES_TO_EXCLUDE(self):
        """set: Feature subtype names to exclude from regulations file. """
        raise NotImplementedError

    @property
    @abstractmethod
    def BUFFER_TYPE(self):
        """str: Key in `BUFFERS` pointing to buffer to use. """
        raise NotImplementedError

    @property
    @abstractmethod
    def FEATURE_FILTER_TYPE(self):
        """str: Key in `FEATURE_FILTERS` pointing to feature filter to use. """
        raise NotImplementedError

    @property
    @abstractmethod
    def NUM_FEATURES_PER_WORKER(self):
        """int: Number of features each worker processes at one time. """
        raise NotImplementedError


def _load_features(features_ids, features_fp, col, crs):
    """Load the `features_ids` from the `features_fp`. """
    ids = ",".join(map(str, features_ids))
    logger.debug("  Loading {} features from {}".format(len(features_ids),
                                                        features_fp))
    features = gpd.read_file(features_fp,
                             where="{} in ({})".format(col, ids),
                             engine="pyogrio")
    features = features.to_crs(crs=crs)
    features["geometry"] = features.apply(_make_row_shape_valid, axis=1)

    logger.debug("Loaded {} features".format(len(features)))
    logger.debug("Features total bounds: {}".format(features.total_bounds))
    log_mem(logger)

    return features


def _make_row_shape_valid(row):
    """Make a row shape valid using shapely `make_valid`"""
    return unary_union(make_valid(row["geometry"]))


def _compute_exclusions(features_ids, features_fp, col, crs, buffer_type,
                        setback, rasterizer):
    """Compute exclusions by loading features, buffering, and rasterizing. """
    setbacks, feature_bounds = _load_and_buffer(features_ids, features_fp,
                                                col, crs, buffer_type,
                                                setback, rasterizer)
    if setbacks is None:
        return None, None

    return rasterizer.rasterize_within_window(setbacks, feature_bounds)


def _load_and_buffer(features_ids, features_fp, col, crs, buffer_type,
                     setback, rasterizer):
    """Load features and immediately buffer them.

    The intention is to keep loading and buffering in one function so
    that large sets of features get dropped immediately instead of
    hanging in memory during rasterization.
    """
    features = _load_features(features_ids, features_fp, col, crs)
    excl_array_bbox = transform.array_bounds(*rasterizer.arr_shape[1:],
                                             rasterizer.transform)
    if coords.disjoint_bounds(excl_array_bbox, features.total_bounds):
        return None, None

    logger.debug(f"Buffering {len(features)} features...")
    setbacks = BUFFERS[buffer_type](features, setback)
    feature_bounds = _buffered_feature_bounds(features, rasterizer, setback)
    return setbacks, feature_bounds


def _buffered_feature_bounds(features, rasterizer, regulation_value):
    """Calculate the buffered feature bounds"""
    buffer_len = max(abs(rasterizer.transform.a), abs(rasterizer.transform.e))
    bound_buffer = regulation_value * 2 + buffer_len
    return features.buffer(bound_buffer).total_bounds
