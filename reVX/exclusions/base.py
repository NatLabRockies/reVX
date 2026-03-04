# -*- coding: utf-8 -*-
"""
Driver class to compute exclusions
"""

import os
import logging
from copy import deepcopy
from math import floor, ceil
from itertools import product
from abc import ABC, abstractmethod
from concurrent.futures import as_completed
from warnings import warn

import numpy as np
import geopandas as gpd
import pandas as pd
from rasterio import (windows, transform, Affine,
                      features as rio_features)
from shapely.geometry import shape

from rex.utilities import SpawnProcessPool, log_mem
from reV.handlers.exclusions import ExclusionLayers
from reVX.handlers.geotiff import Geotiff
from reVX.handlers.layered_h5 import LayeredH5
from reVX.utilities.utilities import log_versions


logger = logging.getLogger(__name__)


class AbstractExclusionCalculatorInterface(ABC):
    """Abstract Exclusion Calculator Interface. """

    @property
    @abstractmethod
    def no_exclusions_array(self):
        """np.array: Array representing no exclusions. """
        raise NotImplementedError

    @property
    @abstractmethod
    def exclusion_merge_func(self):
        """callable: Function to merge overlapping exclusion layers. """
        raise NotImplementedError

    @abstractmethod
    def pre_process_regulations(self):
        """Reduce regulations to correct state and features.

        When implementing this method, make sure to update
        `self._regulations.df`.
        """
        raise NotImplementedError

    @abstractmethod
    def _local_exclusions_arguments(self, regulation_value, county):
        """Compile and yield arguments to `compute_local_exclusions`.

        This method should yield lists or tuples of extra args to be
        passed to `compute_local_exclusions`. Do not include the
        `regulation_value` or `county`.

        Parameters
        ----------
        regulation_value : float | int
            Regulation value for county.
        county : geopandas.GeoDataFrame
            Regulations for a single county.
        """
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def compute_local_exclusions(regulation_value, county, *args):
        """Compute local feature exclusions.

        This method should compute the exclusions using the information
        about the input county.

        Parameters
        ----------
        regulation_value : float | int
            Regulation value for county.
        county : geopandas.GeoDataFrame
            Regulations for a single county.
        *args
            Other arguments required for local exclusion calculation.

        Returns
        -------
        exclusions : np.ndarray
            Array of exclusions.
        slices : 2-tuple of `slice`
            X and Y slice objects defining where in the original array
            the exclusion data should go.
        """
        raise NotImplementedError

    @abstractmethod
    def compute_generic_exclusions(self, max_workers=None):
        """Compute generic exclusions.

        This method should compute the exclusions using a generic
        regulation value (`self._regulations.generic`).

        Parameters
        ----------
        max_workers : int, optional
            Number of workers to use for exclusions computation, if 1
            run in serial, if > 1 run in parallel with that many
            workers, if `None` run in parallel on all available cores.
            By default `None`.

        Returns
        -------
        exclusions : ndarray
            Raster array of exclusions
        """
        raise NotImplementedError


class AbstractBaseExclusionsMerger(AbstractExclusionCalculatorInterface):
    """
    Create exclusions layers for exclusions
    """

    def __init__(self, excl_fpath, regulations, features, hsds=False):
        """
        Parameters
        ----------
        excl_fpath : str
            Path to .h5 file containing exclusion layers, will also be
            the location of any new exclusion layers
        regulations : `~reVX.utilities.AbstractBaseRegulations` subclass
            A regulations object used to extract exclusion regulation
            values.
        features : str
            Path to file containing features to compute exclusions from.
        hsds : bool, optional
            Boolean flag to use h5pyd to handle .h5 'files' hosted on
            AWS behind HSDS. By default `False`.
        """
        log_versions(logger)
        self._excl_fpath = excl_fpath
        self._regulations = regulations
        self._features = features
        self._hsds = hsds
        self._profile = self.shape = None
        self._process_regulations(regulations.df)

    def __repr__(self):
        msg = "{} for {}".format(self.__class__.__name__, self._excl_fpath)
        return msg

    def _parse_excl_properties(self):
        """Parse shape, chunk size, and profile from exclusions file"""
        with ExclusionLayers(self._excl_fpath, hsds=self._hsds) as exc:
            self._shape = exc.shape
            self._profile = exc.profile

        if len(self._shape) < 3:
            self._shape = (1, *self._shape)

        logger.debug('Exclusions properties:\n'
                     'shape : {}\n'
                     'profile : {}\n'
                     .format(self._shape, self._profile))

    def _process_regulations(self, regulations_df):
        """Parse the county regulations.

        Parse regulations, combine with county geometries from
        exclusions .h5 file. The county geometries are intersected with
        features to compute county specific exclusions.

        Parameters
        ----------
        regulations : pandas.DataFrame
            Regulations table

        Returns
        -------
        regulations: `geopandas.GeoDataFrame`
            GeoDataFrame with county level exclusion regulations merged
            with county geometries, use for intersecting with exclusion
            features.
        """
        if regulations_df is None:
            return

        if self._regulations.geometry_provided:
            self._regulations.df = self._validate_regulations_geopackage_input(
                regulations_df)
            return

        self._regulations.df = self._add_region_shapes_from_fips_layer(
            regulations_df)

    def _validate_regulations_geopackage_input(self, regulations_df):
        """Validate regulations GeoDataFrame input.="""
        geometry_mask = ~regulations_df['geometry'].isna()
        if not geometry_mask.any():
            msg = ('Regulations were supplied with a geometry column, '
                    'but all geometries are null.')
            logger.error(msg)
            raise RuntimeError(msg)

        regs_with_geom = regulations_df.loc[geometry_mask].copy()
        if regs_with_geom.crs is None:
            msg = ('Regulations geometries must have a defined CRS. '
                    'Set the CRS prior to computing exclusions.')
            logger.error(msg)
            raise RuntimeError(msg)

        regs_with_geom = regs_with_geom.to_crs(crs=self.profile['crs'])
        return regs_with_geom.reset_index(drop=True)

    def _add_region_shapes_from_fips_layer(self, regulations_df):
        """Add shapes to regulations by rasterizing county FIPS layer"""
        with ExclusionLayers(self._excl_fpath, hsds=self._hsds) as exc:
            fips = exc['cnty_fips']
            cnty_fips_profile = exc.get_layer_profile('cnty_fips')

        if 'FIPS' not in regulations_df:
            msg = ('Regulations does not have county FIPS! Please add a '
                   '"FIPS" columns with the unique county FIPS values.')
            logger.error(msg)
            raise RuntimeError(msg)

        if 'geometry' not in regulations_df:
            regulations_df['geometry'] = None

        regulations_df = regulations_df[~regulations_df['FIPS'].isna()]
        regulations_df = regulations_df.set_index('FIPS')

        logger.info('Merging county geometries w/ local regulations')
        shapes_from_raster = rio_features.shapes(
            fips.astype(np.int32),
            transform=cnty_fips_profile['transform']
        )
        county_regs = []
        for polygon, fips_code in shapes_from_raster:
            fips_code = int(fips_code)
            if fips_code in regulations_df.index:
                local_regs = regulations_df.loc[[fips_code]].copy()
                local_regs['geometry'] = shape(polygon)
                county_regs.append(local_regs)

        if county_regs:
            regulations_df = pd.concat(county_regs)

        regulations_df = gpd.GeoDataFrame(
            regulations_df,
            crs=self.profile['crs'],
            geometry='geometry'
        )
        regulations_df = regulations_df.reset_index()
        return regulations_df.to_crs(crs=self.profile['crs'])

    @property
    def profile(self):
        """dict: Geotiff profile. """
        if self._profile is None:
            self._parse_excl_properties()
        return self._profile

    @property
    def shape(self):
        """tuple: Geotiff shape. """
        if self._shape is None:
            self._parse_excl_properties()
        return self._shape

    @property
    def regulations_table(self):
        """Regulations table.

        Returns
        -------
        geopandas.GeoDataFrame | None
        """
        return self._regulations.df

    @regulations_table.setter
    def regulations_table(self, regulations_table):
        self._process_regulations(regulations_table)

    def _write_exclusions(self, geotiff, exclusions, replace=False):
        """
        Write exclusions to geotiff, replace if requested

        Parameters
        ----------
        geotiff : str
            Path to geotiff file to save exclusions too
        exclusions : ndarray
            Rasterized array of exclusions.
        replace : bool, optional
            Flag to replace local layer data with arr if file already
            exists on disk. By default `False`.
        """
        if os.path.exists(geotiff):
            _error_or_warn(geotiff, replace)

        Geotiff.write(geotiff, self.profile, exclusions)

    def _write_layer(self, out_layer, exclusions, replace=False):
        """Write exclusions to H5, replace if requested

        Parameters
        ----------
        out_layer : str
            Name of new exclusion layer to add to h5.
        exclusions : ndarray
            Rasterized array of exclusions.
        replace : bool, optional
            Flag to replace local layer data with arr if layer already
            exists in the exclusion .h5 file. By default `False`.
        """
        with ExclusionLayers(self._excl_fpath, hsds=self._hsds) as exc:
            layers = exc.layers

        if out_layer in layers:
            _error_or_warn(out_layer, replace)

        try:
            description = self.description
        except AttributeError:
            description = None

        LayeredH5(self._excl_fpath).write_layer_to_h5(exclusions, out_layer,
                                                      self.profile,
                                                      description=description)

    def _county_exclusions(self):
        """Yield county exclusion arguments. """
        for ind, regulation_info in enumerate(self._regulations, start=1):
            exclusion, cnty = regulation_info
            logger.debug('Computing exclusions for {}/{} counties'
                         .format(ind, len(self.regulations_table)))
            for args in self._local_exclusions_arguments(exclusion, cnty):
                yield exclusion, cnty, args

    def compute_all_local_exclusions(self, max_workers=None):
        """Compute local exclusions for all counties either.

        Parameters
        ----------
        max_workers : int, optional
            Number of workers to use for exclusions computation, if 1
            run in serial, if > 1 run in parallel with that many
            workers, if `None` run in parallel on all available cores.
            By default `None`.

        Returns
        -------
        exclusions : ndarray
            Raster array of exclusions.
        """
        mw = max_workers or os.cpu_count()

        log_mem(logger)
        exclusions = None
        if mw > 1:
            logger.info('Computing local exclusions in parallel using {} '
                        'workers'.format(mw))
            spp_kwargs = {"max_workers": mw, "loggers": [__name__, 'reVX']}
            with SpawnProcessPool(**spp_kwargs) as exe:
                exclusions = self._compute_local_exclusions_in_chunks(exe, mw)

        else:
            logger.info('Computing local exclusions in serial')
            for ind, cnty_inf in enumerate(self._county_exclusions(), start=1):
                exclusion_value, cnty, args = cnty_inf
                out = self.compute_local_exclusions(exclusion_value, cnty,
                                                    *args)
                local_exclusions, slices = out
                geometry = cnty.geometry.to_list()
                exclusions = self._combine_exclusions(exclusions,
                                                      local_exclusions,
                                                      slices,
                                                      local_geometry=geometry)
                logger.debug("Computed exclusions for {:,} counties"
                             .format(ind))
        if exclusions is None:
            exclusions = self.no_exclusions_array

        return exclusions

    def _compute_local_exclusions_in_chunks(self, exe, max_submissions):
        """Compute exclusions in parallel using futures. """
        futures, exclusions = {}, None

        for ind, reg in enumerate(self._county_exclusions(), start=1):
            exclusion_value, cnty, args = reg
            future = exe.submit(self.compute_local_exclusions,
                                exclusion_value, cnty, *args)
            geometry = cnty.geometry.to_list()
            futures[future] = geometry
            if ind % max_submissions == 0:
                exclusions = self._collect_local_futures(futures, exclusions)
        exclusions = self._collect_local_futures(futures, exclusions)
        return exclusions

    def _collect_local_futures(self, futures, exclusions):
        """Collect all futures from the input dictionary. """
        for future in as_completed(futures):
            new_exclusions, slices = future.result()
            geometry = futures.pop(future)
            exclusions = self._combine_exclusions(exclusions,
                                                  new_exclusions,
                                                  slices=slices,
                                                  local_geometry=geometry)
            log_mem(logger)
        return exclusions

    def compute_exclusions(self, out_layer=None, out_tiff=None, replace=False,
                           max_workers=None):
        """
        Compute exclusions for all states either in serial or parallel.
        Existing exclusions are computed if a regulations file was
        supplied during class initialization, otherwise generic exclusions
        are computed.

        Parameters
        ----------
        out_layer : str, optional
            Name to save rasterized exclusions under in .h5 file.
            If `None`, exclusions will not be written to the .h5 file.
            By default `None`.
        out_tiff : str, optional
            Path to save geotiff containing rasterized exclusions.
            If `None`, exclusions will not be written to a geotiff file.
            By default `None`.
        replace : bool, optional
            Flag to replace geotiff if it already exists.
            By default `False`.
        max_workers : int, optional
            Number of workers to use for exclusion computation, if 1 run
            in serial, if > 1 run in parallel with that many workers,
            if `None`, run in parallel on all available cores.
            By default `None`.

        Returns
        -------
        exclusions : ndarray
            Raster array of exclusions
        """
        exclusions = self._compute_merged_exclusions(max_workers=max_workers)

        if out_layer is not None:
            logger.info('Saving exclusion layer to {} as {}'
                        .format(self._excl_fpath, out_layer))
            self._write_layer(out_layer, exclusions, replace=replace)

        if out_tiff is not None:
            logger.debug('Writing exclusions to {}'.format(out_tiff))
            self._write_exclusions(out_tiff, exclusions, replace=replace)

        return exclusions

    def _compute_merged_exclusions(self, max_workers=None):
        """Compute and merge local and generic exclusions, if necessary. """
        mw = max_workers

        if self._regulations.locals_exist:
            self.pre_process_regulations()

        generic_exclusions_exist = self._regulations.generic_exists
        local_exclusions_exist = self._regulations.locals_exist

        if not generic_exclusions_exist and not local_exclusions_exist:
            msg = ("Found no exclusions to compute: No regulations detected, "
                   "and generic multiplier not set.")
            logger.warning(msg)
            warn(msg)
            return self.no_exclusions_array

        if generic_exclusions_exist and not local_exclusions_exist:
            return self.compute_generic_exclusions(max_workers=mw)

        if local_exclusions_exist and not generic_exclusions_exist:
            local_excl = self.compute_all_local_exclusions(max_workers=mw)
            # merge ensures local exclusions are clipped county boundaries
            return self._merge_exclusions(None, local_excl)

        generic_exclusions = self.compute_generic_exclusions(max_workers=mw)
        local_exclusions = self.compute_all_local_exclusions(max_workers=mw)
        return self._merge_exclusions(generic_exclusions, local_exclusions)

    def _merge_exclusions(self, generic_exclusions, local_exclusions):
        """Merge local exclusions onto the generic exclusions."""
        logger.info('Merging local exclusions onto the generic exclusions')

        local_geometry = self.regulations_table.geometry.to_list()
        return self._combine_exclusions(generic_exclusions, local_exclusions,
                                        replace_existing=True,
                                        local_geometry=local_geometry)

    def _combine_exclusions(self, existing, additional=None, slices=None,
                            replace_existing=False, local_geometry=None):
        """Combine local exclusions using FIPS code"""
        if additional is None:
            return existing

        if existing is None:
            existing = self.no_exclusions_array.astype(additional.dtype)

        if slices is None:
            slices = tuple([slice(None)] * len(existing.shape))

        if local_geometry is None:
            local_exclusions = slice(None)
        else:
            local_exclusions = self._geometry_mask(local_geometry, slices,
                                                   additional.shape)

        if replace_existing:
            new_local_exclusions = additional[local_exclusions]
        else:
            new_local_exclusions = self.exclusion_merge_func(
                existing[slices][local_exclusions],
                additional[local_exclusions])
        existing[slices][local_exclusions] = new_local_exclusions
        return existing

    def _geometry_mask(self, geometry, slices, target_shape):
        """Rasterize geometry into a boolean mask for the provided window."""
        geoms = [geom for geom in geometry if geom and not geom.is_empty]
        if not geoms:
            return np.zeros(target_shape, dtype=bool)

        array_shape = (self.profile['height'], self.profile['width'])
        row_slice, col_slice = slices
        window = windows.Window.from_slices(row_slice, col_slice,
                                            height=array_shape[0],
                                            width=array_shape[1])
        base_transform = self.profile['transform']
        if not isinstance(base_transform, Affine):
            base_transform = Affine(*base_transform)

        transform = windows.transform(window, base_transform)
        mask = rio_features.rasterize(((geom, 1) for geom in geoms),
                                      out_shape=target_shape,
                                      transform=transform,
                                      fill=0,
                                      dtype=np.uint8)

        return mask.astype(bool)

    @classmethod
    def run(cls, excl_fpath, features_path, out_fn, regulations,
            max_workers=None, replace=False, out_layers=None, hsds=False,
            **kwargs):
        """
        Compute exclusions and write them to a geotiff. If a regulations
        file is given, compute local exclusions, otherwise compute
        generic exclusions. If both are provided, generic and local
        exclusions are merged such that the local exclusions override
        the generic ones.

        Parameters
        ----------
        excl_fpath : str
            Path to .h5 file containing exclusion layers, will also be
            the location of any new exclusion layers.
        features_path : str
            Path to file or directory feature shape files.
            This path can contain any pattern that can be used in the
            glob function. For example, `/path/to/features/[A]*` would
            match with all the features in the directory
            `/path/to/features/` that start with "A". This input
            can also be a directory, but that directory must ONLY
            contain feature files. If your feature files are mixed
            with other files or directories, use something like
            `/path/to/features/*.geojson`.
        out_fn : str
            Path to output geotiff where exclusion data should be
            stored.
        regulations : `~reVX.utilities.AbstractBaseRegulations` subclass
            A regulations object used to extract exclusion regulation
            distances.
        max_workers : int, optional
            Number of workers to use for exclusion computation, if 1 run
            in serial, if > 1 run in parallel with that many workers,
            if `None`, run in parallel on all available cores.
            By default `None`.
        replace : bool, optional
            Flag to replace geotiff if it already exists.
            By default `False`.
        out_layers : dict, optional
            Dictionary mapping feature file names (with extension) to
            names of layers under which exclusions should be saved in
            the `excl_fpath` .h5 file. If `None` or empty dictionary,
            no layers are saved to the h5 file. By default `None`.
        hsds : bool, optional
            Boolean flag to use h5pyd to handle .h5 'files' hosted on
            AWS behind HSDS. By default `False`.
        **kwargs
            Keyword args to exclusions calculator class.
        """

        out_layers = out_layers or {}
        cls_init_kwargs = {"excl_fpath": excl_fpath,
                           "regulations": regulations}
        cls_init_kwargs.update(kwargs)

        if os.path.exists(out_fn) and not replace:
            msg = ('{} already exists, exclusions will not be re-computed '
                   'unless replace=True'.format(out_fn))
            logger.error(msg)
        else:
            logger.info("Computing exclusions from {} and saving "
                        "to {}".format(features_path, out_fn))
            out_layer = None
            if out_layers and features_path:
                out_layer = out_layers.get(os.path.basename(features_path))
            exclusions = cls(excl_fpath=excl_fpath, regulations=regulations,
                             features=features_path, hsds=hsds, **kwargs)
            exclusions.compute_exclusions(out_tiff=out_fn, out_layer=out_layer,
                                          max_workers=max_workers,
                                          replace=replace)


def _error_or_warn(name, replace):
    """If replace, throw warning, otherwise throw error. """
    if not replace:
        msg = ('{} already exists. To replace it set "replace=True"'
               .format(name))
        logger.error(msg)
        raise IOError(msg)

    msg = ('{} already exists and will be replaced!'.format(name))
    logger.warning(msg)
    warn(msg)


class Rasterizer:
    """Helper class to rasterize shapes."""

    def __init__(self, shape, profile,
                 weights_calculation_upscale_factor=None):
        """

        Parameters
        ----------
        shape : tuple
            Shape of the output (i.e. exclusion) array. Should contain
            a band dimension as the first dimension.
        profile : dict
            Geotiff profile containing the transform and CRS information
            necessary for rasterization.
        weights_calculation_upscale_factor : int, optional
            If this value is an int > 1, the output will be a layer with
            **inclusion** weight values (floats ranging from 0 to 1).
            Note that this is backwards w.r.t the typical output of
            exclusion integer values (1 for excluded, 0 otherwise).
            Values <= 1 will still return a standard exclusion mask.
            For example, a cell that was previously excluded with a
            a boolean mask (value of 1) may instead be converted to an
            inclusion weight value of 0.75, meaning that 75% of the area
            corresponding to that point should be included (i.e. the
            exclusion feature only intersected a small portion - 25% -
            of the cell). This percentage inclusion value is calculated
            by upscaling the output array using this input value,
            rasterizing the exclusion features onto it, and counting the
            number of resulting sub-cells excluded by the feature. For
            example, setting the value to 3 would split each output
            cell into nine sub-cells - 3 divisions in each dimension.
            After the feature is rasterized on this high-resolution
            sub-grid, the area of the non-excluded sub-cells is totaled
            and divided by the area of the original cell to obtain the
            final inclusion percentage. Therefore, a larger upscale
            factor results in more accurate percentage values. If
            ``None`` (or a value <= 1), this process is skipped and the
            output is a boolean exclusion mask. By default ``None``.
        """
        self._shape, self._profile = shape, profile
        self.scale_factor = weights_calculation_upscale_factor

    @property
    def scale_factor(self):
        """Integer upscale factor used to calculate inclusion weights"""
        return self._scale_factor

    @scale_factor.setter
    def scale_factor(self, sf):
        self._scale_factor = int((sf or 1) // 1)

    @property
    def profile(self):
        """Geotiff profile.

        Returns
        -------
        dict
        """
        return self._profile

    @property
    def transform(self):
        """rasterio.Affine: Affine transform for exclusion layer. """
        return Affine(*self.profile["transform"])

    @property
    def arr_shape(self):
        """Rasterize array shape.

        Returns
        -------
        tuple
        """
        return self._shape

    @property
    def inclusions(self):
        """Flag indicating whether or not the output raster represents
        inclusion values.

        Returns
        -------
        bool
        """
        return self.scale_factor > 1

    def _no_exclusions_array(self, multiplier=1, window=None):
        """Get an array of the correct shape representing no exclusions.

        The array contains all zeros, and a new one is created
        for every function call.

        Parameters
        ----------
        multiplier : int, optional
            Integer multiplier value used to scale up the dimensions of
            the array exclusions array (e.g. multiplier of 3 turns an
            array of shape (10, 20) into an array of shape (30, 60)).
        window : :cls:`rasterio.windows.Window`
            A ``rasterio`` window defining the area of the raster. Can
            be used to speed up computation and decrease memory
            requirements if features are localized to a small portion of
            the raster array.

        Returns
        -------
        np.array
            Array of zeros representing no exclusions.
        """
        if window is None:
            shape = tuple(x * multiplier for x in self.arr_shape[1:])
        else:
            shape = (window.height * multiplier, window.width * multiplier)
        return np.zeros(shape, dtype='uint8')

    def rasterize(self, shapes, window=None):
        """Convert geometries into exclusions array.

        Parameters
        ----------
        shapes : list, optional
            List of geometries to rasterize (i.e. list(gdf["geometry"])).
            If `None` or empty list, returns array of zeros.
        window : :obj:`rasterio.windows.Window`
            A ``rasterio`` window defining the area of the raster. Can
            be used to speed up computation and decrease memory
            requirements if features are localized to a small portion of
            the raster array.

        Returns
        -------
        arr : ndarray
            Rasterized array of shapes.
        """

        shapes = shapes or []
        shapes = [(geom, 1) for geom in shapes if geom is not None]

        if self.inclusions:
            return self._rasterize_to_weights(shapes, window)

        return self._rasterize_to_mask(shapes, window)

    def rasterize_within_window(self, features, bounds):
        """Rasterize the features using the GeoSeries bounding box

        Parameters
        ----------
        features : list
            List of geometries to rasterize
            (i.e. list(gdf["geometry"])).
        bounds : tuple
            Bounding box to rasterize within, in the form (left, bottom,
            right, top).

        Returns
        -------
        arr : ndarray
            Rasterized array of shapes within the bounding box.
        slices : 2-tuple of `slice`
            X and Y slice objects defining where in the original array
            the exclusion data should go.
        """
        window = _cropped_window(bounds, self.transform, self.arr_shape[1:])
        if len(features):
            logger.debug("Rasterizing %d features using %r",
                         len(features), window)
        exclusions = self.rasterize(features, window=window)
        log_mem(logger)
        logger.debug("Exclusion mem size: %.2fMB", exclusions.nbytes / 1048576)
        return exclusions, window.toslices()

    def _rasterize_to_weights(self, shapes, window):
        """Rasterize features to weights using a high-resolution array."""

        if not shapes:
            return ((1 - self._no_exclusions_array(window=window))
                    .astype(np.float32))

        hr_arr = self._no_exclusions_array(multiplier=self.scale_factor,
                                           window=window)
        transform = self._window_transform(window)
        transform *= transform.scale(1 / self.scale_factor)

        rio_features.rasterize(shapes=shapes, out=hr_arr, fill=0,
                               transform=transform)

        arr = self._aggregate_high_res(hr_arr, window)
        return 1 - (arr / self.scale_factor ** 2)

    def _rasterize_to_mask(self, shapes, window):
        """Rasterize features with to an exclusion mask."""

        arr = self._no_exclusions_array(window=window)
        if shapes:
            transform = self._window_transform(window)
            rio_features.rasterize(shapes=shapes, out=arr, fill=0,
                                   transform=transform)

        return arr

    def _aggregate_high_res(self, hr_arr, window):
        """Aggregate the high resolution exclusions array to output shape. """

        arr = self._no_exclusions_array(window=window).astype(np.float32)
        for i, j in product(range(self.scale_factor),
                            range(self.scale_factor)):
            arr += hr_arr[i::self.scale_factor, j::self.scale_factor]
        return arr

    def _window_transform(self, window):
        """Calculate the transform for a given window, if any. """
        if window is None:
            return deepcopy(self.transform)
        return windows.transform(window, self.transform)


def _cropped_window(bounds, raster_transform, shape):
    """Calculate the raster array window corresponding to the bounding box."""
    left, bottom, right, top = bounds

    rows, cols = transform.rowcol(raster_transform,
                                  [left, right, right, left],
                                  [top, top, bottom, bottom],
                                  op=float)

    row_start = max(floor(min(rows)), 0)
    col_start = max(floor(min(cols)), 0)
    row_stop = min(ceil(max(rows)), shape[0])
    col_stop = min(ceil(max(cols)), shape[1])
    return windows.Window(col_off=col_start, row_off=row_start,
                          width=max(col_stop - col_start, 1),
                          height=max(row_stop - row_start, 1))
