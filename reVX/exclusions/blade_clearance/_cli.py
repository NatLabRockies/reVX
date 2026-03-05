# -*- coding: utf-8 -*-
"""
Blade Clearance exclusions CLI
"""
import os
import logging

from gaps.cli import CLICommandFromFunction

from reVX.exclusions.blade_clearance.blade_clearance import (
    BladeClearanceExclusions)
from reVX.exclusions.blade_clearance.regulations import (
    validate_blade_clearance_regulations_input)
from reVX import __version__


logger = logging.getLogger(__name__)


def compute_blade_clearance_exclusions(excl_fpath, out_dir, regulations_fpath,
                                       hub_height, rotor_diameter,
                                       replace=False, hsds=False,
                                       out_layers=None, max_workers=None):
    """Exclude regions where system blade clearance does not meet requirements

    Blade clearance restrictions are only computed locally - you must
    provide a set of local regulations that dictates the minimum blade
    clearance requirements for each county. The local regulations are
    then compared to the blade clearance of the system being considered,
    and any regions where the system does not meet the local blade
    clearance requirements are excluded.

    Parameters
    ----------
    excl_fpath : str
        Path to HDF5 file containing output layer profile information.
        If you are providing a ``regulations_fpath`` input that is not a
        GeoPackage, this HDF5 file should also contain a county FIPS
        layer (called ``cnty_fips``) used to match local regulations in
        ``regulations_fpath`` to counties on the grid. No data will be
        written to this file unless explicitly requested via the
        ``out_layers`` input.
    out_dir : str
        Path to output directory where output file should be written.
    regulations_fpath : str, optional
        Path to regulations ``.csv`` or ``.gpkg`` file. At a minimum,
        this file must contain the following columns:

            - ``Feature Type``: Contains labels for the type of
              restriction that each row represents. To compute blade
              clearance exclusions, at least one row must have the value
              "Blade Clearance" in this column (case-insensitive and
              ignoring dashes and underscores).
            - ``Feature Subtype``: Contains labels for feature subtypes.
              For blade clearance exclusion computations, you should
              leave this blank or set it to ``None``.
            - ``Value Type``: Specifies the units of the value in the
              ``Value`` column. For blade clearance exclusion
              computations, the value type must be "meters", "percent",
              or "percent of tower height" (case-insensitive).
            - ``Value``: Numeric value of the blade clearance
              restriction.
            - ``FIPS``: Specifies a unique 5-digit code for each county
              (this can be an integer - no leading zeros required). This
              is used along side the ``cnty_fips`` layer in the
              `excl_fpath` to match the county regulations to the
              county's spatial extent.

    hub_height : float | int
        Turbine hub height (m), used along with rotor diameter to
        compute blade clearance.
    rotor_diameter : float | int
        Turbine rotor diameter (m), used along with hub height to
        compute blade clearance.
    replace : bool, optional
        Flag to replace the output GeoTIFF if it already exists.
        By default, ``False``.
    hsds : bool, optional
        Boolean flag to use ``h5pyd`` to handle HDF5 "files" hosted on
        AWS behind HSDS. By default, ``False``.
    out_layers : dict, optional
        Dictionary mapping the input feature file names (with extension)
        to names of layers under which exclusions should be saved in the
        ``excl_fpath`` HDF5 file. If ``None`` or empty dictionary,
        no layers are saved to the HDF5 file. By default, ``None``.
    max_workers : int, optional
        Number of workers to use for exclusion computation. If this
        value is 1, the computation runs in serial. If this value
        is > 1, the computation runs in parallel with that many workers.
        If ``None``, the computation runs in parallel on all available
        cores. By default, ``None``.

    Returns
    -------
    str
        Path to output GeoTIFF file containing exclusion data.
    """

    logger.info('Computing blade clearance exclusions')
    logger.debug('Blade clearance exclusions to be computed with:\n'
                 '- hub_height = {}\n'
                 '- rotor_diameter = {}\n'
                 '- regulations_fpath = {}\n'
                 '- using max_workers = {}\n'
                 '- replace layer if needed = {}\n'
                 '- out_layers = {}\n'
                 .format(hub_height, rotor_diameter, regulations_fpath,
                         max_workers, replace, out_layers))

    regulations = validate_blade_clearance_regulations_input(
        hub_height=hub_height,
        rotor_diameter=rotor_diameter,
        regulations_fpath=regulations_fpath,
    )

    fn = ("blade_clearance_restrictions_{}hh_{}rd.tif"
          .format(hub_height, rotor_diameter))
    out_fn = os.path.join(out_dir, fn)
    BladeClearanceExclusions.run(excl_fpath, None, out_fn, regulations,
                                 max_workers=max_workers, replace=replace,
                                 hsds=hsds, out_layers=out_layers)

    logger.info('Blade clearance restrictions computed and written to %r',
                out_fn)
    return out_fn


blade_clearance_command = CLICommandFromFunction(
    function=compute_blade_clearance_exclusions, name="blade-clearance"
)
