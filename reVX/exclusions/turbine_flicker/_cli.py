# -*- coding: utf-8 -*-
"""
Turbine Flicker CLI
"""

import os
import logging

from gaps.cli import CLICommandFromFunction

from reVX.exclusions.turbine_flicker.turbine_flicker import TurbineFlicker
from reVX.exclusions.turbine_flicker.regulations import FlickerRegulations


logger = logging.getLogger(__name__)


def run_flicker(excl_fpath, res_fpath, hub_height, rotor_diameter, out_dir,
                out_layer=None, regulations_fpath=None, building_layer=None,
                tm_dset='techmap_wtk', building_threshold=0,
                flicker_threshold=30, resolution=128, grid_cell_size=90,
                max_flicker_exclusion_range="10x",
                max_workers=None, replace=False, hsds=False):
    """Compute turbine shadow flicker exclusions from building data

    Flicker exclusions can be computed using:

    - a generic annual flicker threshold (``flicker_threshold``),
    - county-specific regulations (``regulations_fpath``), or
    - both simultaneously (county values where provided and generic
      values elsewhere).

    Results are written to disk as GeoTIFF output and optionally to the
    exclusions HDF5 layer specified by ``out_layer``.

    Parameters
    ----------
    excl_fpath : str
        Path to exclusions HDF5 file used as the computation grid. This
        file must contain the building layer identified by
        ``building_layer``. If ``regulations_fpath`` is provided as a
        non-GeoPackage tabular file, this file must also contain a
        county FIPS layer used to map regulations to grid cells.
    res_fpath : str
        Path to wind resource HDF5 file with wind-direction data used
        for flicker simulation.
    hub_height : float | int
        Turbine hub height in meters.
    rotor_diameter : float | int
        Turbine rotor diameter in meters.
    out_dir : str
        Directory where the output flicker GeoTIFF is written.
    out_layer : str | None
        Optional name of the layer to write into ``excl_fpath``. If
        ``None``, no layer is written to the exclusions HDF5 unless
        handled elsewhere in the pipeline. By default, ``None``.
    regulations_fpath : str | None, optional
        Optional path to county-level regulations (.csv or .gpkg). When
        provided, local flicker limits are applied where available. If
        ``None``, generic regulations from ``flicker_threshold`` are
        used. By default, ``None``.
    building_layer : str, optional
        Name of the building exclusion layer in ``excl_fpath`` or path
        to a GeoTIFF of building data used to derive exclusions.
    tm_dset : str, optional
        Name of the techmap dataset in ``excl_fpath`` used to identify
        valid supply-curve points. By default, ``"techmap_wtk"``.
    building_threshold : float | int, optional
        Building-layer threshold used to classify a pixel as containing
        a building. Values are interpreted as percent building coverage
        per pixel; threshold comparison is not inclusive.
        By default, ``0``.
    flicker_threshold : float | int, optional
        Generic maximum allowable shadow flicker in hours/year. This
        value is used when county-specific regulations are absent.
        By default, ``30``.
    resolution : int, optional
        Supply-curve resolution used to evaluate flicker exclusions.
        By default, ``128``.
    grid_cell_size : float | int, optional
        Grid cell side length in meters for the exclusions grid.
        By default, ``90``.
    max_flicker_exclusion_range : float | int | str, optional
        Maximum distance (m) over which flicker exclusions are
        evaluated. Values may be numeric or expressed as a
        rotor-diameter multiplier such as ``"10x"``.
        By default, ``"10x"``.
    max_workers : int | None, optional
        Maximum number of worker processes used for parallel
        computation. If ``None``, the implementation selects a default.
    replace : bool, optional
        If ``True``, allow replacement of existing output layers.
        By default, ``False``.
    hsds : bool, optional
        If ``True``, use HSDS/h5pyd access for HDF5 resources.
        By default, ``False``.

    Raises
    ------
    RuntimeError
        If required exclusion datasets are missing or if input layer
        shapes do not match the exclusions grid.
    TypeError
        If ``max_flicker_exclusion_range`` is not numeric and cannot be
        parsed from the ``"Nx"`` multiplier format.
    Exception
        Propagates exceptions raised by
        :class:`~reVX.exclusions.turbine_flicker.regulations.FlickerRegulations`
        and
        :meth:`~reVX.exclusions.turbine_flicker.turbine_flicker.TurbineFlicker.run`.

    See Also
    --------
    reVX.exclusions.turbine_flicker.turbine_flicker.TurbineFlicker.run
        Method that performs the core flicker exclusion computation.
    reVX.exclusions.turbine_flicker.regulations.FlickerRegulations
        Class that encapsulates flicker regulations and provides lookup
        functionality for exclusion evaluation.

    Notes
    -----
    The output file name is generated as
    ``flicker_{hub_height}hh_{rotor_diameter}rd{tag}.tif`` in
    ``out_dir``.
    """

    if out_layer is not None:
        out_layers = {os.path.basename(building_layer): out_layer}
    else:
        out_layers = {}

    logger.info('Computing Turbine Flicker Exclusions from structures in {}'
                .format(building_layer))
    logger.debug('Flicker to be computed with:\n'
                 '- building_layer = {}\n'
                 '- hub_height = {}\n'
                 '- rotor_diameter = {}\n'
                 '- tm_dset = {}\n'
                 '- building_threshold = {}\n'
                 '- flicker_threshold = {}\n'
                 '- resolution = {}\n'
                 '- grid_cell_size = {}\n'
                 '- max_flicker_exclusion_range = {}\n'
                 '- regulations_fpath = {}\n'
                 '- using max_workers = {}\n'
                 '- replace layer if needed = {}\n'
                 '- out_layer = {}\n'
                 .format(building_layer, hub_height, rotor_diameter,
                         tm_dset, building_threshold, flicker_threshold,
                         resolution, grid_cell_size,
                         max_flicker_exclusion_range, regulations_fpath,
                         max_workers, replace, out_layer))

    regulations = FlickerRegulations(hub_height, rotor_diameter,
                                     flicker_threshold, regulations_fpath)
    fn = "flicker_{}hh_{}rd.tif".format(hub_height, rotor_diameter)
    out_fn = os.path.join(out_dir, fn)
    TurbineFlicker.run(excl_fpath, building_layer, out_fn,
                       res_fpath=res_fpath,
                       regulations=regulations,
                       building_threshold=building_threshold,
                       resolution=resolution,
                       grid_cell_size=grid_cell_size,
                       max_flicker_exclusion_range=max_flicker_exclusion_range,
                       tm_dset=tm_dset, max_workers=max_workers,
                       replace=replace, hsds=hsds, out_layers=out_layers)
    logger.info('Flicker exclusions computed and written to %r', out_fn)
    return out_fn


flicker_command = CLICommandFromFunction(
    function=run_flicker, name="turbine-flicker"
)
