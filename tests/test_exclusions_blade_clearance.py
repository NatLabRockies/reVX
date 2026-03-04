# -*- coding: utf-8 -*-
# pylint: disable=protected-access,unused-argument,redefined-outer-name
# pylint: disable=too-many-arguments,too-many-locals
"""
Blade clearance exclusion tests
"""
from click.testing import CliRunner
import json
import numpy as np
import pandas as pd
import os
import pytest
import tempfile

from reV.handlers.exclusions import ExclusionLayers
from rex.utilities.loggers import LOGGERS

from reVX import TESTDATADIR
from reVX.handlers.geotiff import Geotiff
from reVX.exclusions.blade_clearance.regulations import (
    BladeClearanceRegulations, validate_blade_clearance_regulations_input)
from reVX.exclusions.blade_clearance.blade_clearance import (
    BladeClearanceExclusions)

from reVX.exclusions._cli import cli


EXCL_H5 = os.path.join(TESTDATADIR, 'setbacks', 'ri_setbacks.h5')


@pytest.fixture(scope="module")
def runner():
    """
    cli runner
    """
    return CliRunner()


def _find_out_tiff_file(directory):
    """Find the (single) tiff output file in the directory."""

    out_file = [fp for fp in os.listdir(directory) if fp.endswith("tif")]
    assert any(out_file)
    out_file = os.path.join(directory, out_file[0])
    return out_file


def _make_blade_clearance_regs(out_fpath, restricted_fips,
                               unrestricted_fips=None,
                               restricted_value=50,
                               unrestricted_value=20,
                               restricted_value_type='Meters',
                               unrestricted_value_type='Meters'):
    """Create a local regulations csv for blade clearance tests."""
    restricted_fips = set(restricted_fips)
    unrestricted_fips = set(unrestricted_fips or set())
    all_fips = sorted(restricted_fips | unrestricted_fips)

    regs = pd.DataFrame({
        'Feature Type': ['Blade Clearance'] * len(all_fips),
        'Feature Subtype': [''] * len(all_fips),
        'Value Type': [restricted_value_type if f in restricted_fips
                       else unrestricted_value_type
                       for f in all_fips],
        'Value': [restricted_value if f in restricted_fips
                  else unrestricted_value
                  for f in all_fips],
        'FIPS': all_fips,
    })
    regs.to_csv(out_fpath, index=False)
    return regs


def test_validate_blade_clearance_regulations_input():
    """Test strict input validation for blade clearance mode."""
    with pytest.raises(RuntimeError):
        validate_blade_clearance_regulations_input(
            rotor_diameter=100,
            regulations_fpath='dummy.csv',
        )

    with pytest.raises(RuntimeError):
        validate_blade_clearance_regulations_input(
            hub_height=100,
            regulations_fpath='dummy.csv',
        )

    with pytest.raises(RuntimeError):
        validate_blade_clearance_regulations_input(
            regulations_fpath='dummy.csv',
        )

    with pytest.raises(RuntimeError):
        validate_blade_clearance_regulations_input(
            hub_height=120,
            rotor_diameter=100,
        )


def test_blade_clearance_regulations_conversion():
    """Test blade-clearance, tip-height, and value conversions."""
    with tempfile.TemporaryDirectory() as td:
        regs_fpath = os.path.join(td, 'blade_regs.csv')
        regs = pd.DataFrame({
            'Feature Type': ['Blade Clearance'] * 4,
            'Feature Subtype': [''] * 4,
            'Value Type': ['Meters', 'Percent', 'Percent of Tower Height',
                           'Unsupported Units'],
            'Value': [60, 30, 40, 999],
            'FIPS': [44001, 44003, 44005, 44007],
        })
        regs.to_csv(regs_fpath, index=False)

        bc = BladeClearanceRegulations(
            hub_height=120,
            rotor_diameter=80,
            regulations_fpath=regs_fpath,
        )

        assert np.isclose(bc.tip_height, 160)
        assert np.isclose(bc.blade_clearance, 80)

        county_regs = bc.df.set_index('FIPS')
        assert np.isclose(bc._county_regulation_value(county_regs.loc[44001]),
                          60)
        assert np.isclose(bc._county_regulation_value(county_regs.loc[44003]),
                          48)
        assert np.isclose(bc._county_regulation_value(county_regs.loc[44005]),
                          64)

        with pytest.warns(UserWarning, match='Cannot create blade clearance'):
            assert bc._county_regulation_value(county_regs.loc[44007]) is None


def test_blade_clearance_exclusions():
    """Test local-only county exclusions for blade clearance restrictions."""
    with ExclusionLayers(EXCL_H5) as exc:
        fips = exc['cnty_fips']
        all_fips = sorted(set(np.unique(fips[fips > 0])))

    restricted = {all_fips[0]}
    unrestricted = {all_fips[1]}
    with tempfile.TemporaryDirectory() as td:
        regs_fpath = os.path.join(td, 'blade_regs.csv')
        _make_blade_clearance_regs(regs_fpath, restricted, unrestricted,
                                   restricted_value=90,
                                   unrestricted_value=70,
                                   restricted_value_type='Meters',
                                   unrestricted_value_type='Meters')

        regs = BladeClearanceRegulations(
            regulations_fpath=regs_fpath,
            hub_height=120,
            rotor_diameter=80,
        )
        bc = BladeClearanceExclusions(EXCL_H5, regs, features=None)
        out = bc.compute_exclusions(max_workers=1)

        truth = np.isin(fips, list(restricted)).astype(np.uint8)
        assert np.allclose(out, truth)


def test_blade_clearance_exclusions_boundary_equal_not_excluded():
    """Test equality boundary where blade clearance equals regulation value."""
    with ExclusionLayers(EXCL_H5) as exc:
        fips = exc['cnty_fips']
        all_fips = sorted(set(np.unique(fips[fips > 0])))

    equal_county = {all_fips[0]}
    with tempfile.TemporaryDirectory() as td:
        regs_fpath = os.path.join(td, 'blade_regs.csv')
        _make_blade_clearance_regs(regs_fpath, equal_county, set(),
                                   restricted_value=80,
                                   restricted_value_type='Meters')

        regs = BladeClearanceRegulations(
            regulations_fpath=regs_fpath,
            hub_height=120,
            rotor_diameter=80,
        )
        bc = BladeClearanceExclusions(EXCL_H5, regs, features=None)
        out = bc.compute_exclusions(max_workers=1)

        assert not np.any(out[np.isin(fips, list(equal_county))])


def test_blade_clearance_exclusions_feature_filtering():
    """Test that non blade-clearance rows are ignored."""
    with ExclusionLayers(EXCL_H5) as exc:
        fips = exc['cnty_fips']
        all_fips = sorted(set(np.unique(fips[fips > 0])))

    county = all_fips[0]
    with tempfile.TemporaryDirectory() as td:
        regs_fpath = os.path.join(td, 'blade_regs.csv')
        regs = pd.DataFrame({
            'Feature Type': ['Maximum Height', 'Blade Clearance'],
            'Feature Subtype': ['', ''],
            'Value Type': ['Meters', 'Meters'],
            'Value': [999, 90],
            'FIPS': [county, county],
        })
        regs.to_csv(regs_fpath, index=False)

        regs_obj = BladeClearanceRegulations(
            regulations_fpath=regs_fpath,
            hub_height=120,
            rotor_diameter=80,
        )
        bc = BladeClearanceExclusions(EXCL_H5, regs_obj, features=None)
        out = bc.compute_exclusions(max_workers=1)

        truth = np.isin(fips, [county]).astype(np.uint8)
        assert np.allclose(out, truth)


def test_cli_blade_clearance(runner):
    """Test CLI for local-only blade clearance mode."""
    with ExclusionLayers(EXCL_H5) as exc:
        fips = exc['cnty_fips']
        all_fips = sorted(set(np.unique(fips[fips > 0])))

    restricted = {all_fips[0]}
    unrestricted = {all_fips[1]}
    with tempfile.TemporaryDirectory() as td:
        regs_fpath = os.path.join(td, 'blade_regs.csv')
        _make_blade_clearance_regs(regs_fpath, restricted, unrestricted,
                                   restricted_value=90,
                                   unrestricted_value=70,
                                   restricted_value_type='Meters',
                                   unrestricted_value_type='Meters')

        config = {
            "log_directory": td,
            "execution_control": {"option": "local"},
            "excl_fpath": EXCL_H5,
            "log_level": "INFO",
            "regulations_fpath": regs_fpath,
            "replace": True,
            "hub_height": 120,
            "rotor_diameter": 80,
        }
        config_path = os.path.join(td, 'config.json')
        with open(config_path, 'w') as f:
            json.dump(config, f)

        result = runner.invoke(cli, ['blade-clearance', '-c', config_path])
        assert result.exit_code == 0, result.output

        test_fp = _find_out_tiff_file(td)
        with Geotiff(test_fp) as tif:
            out = tif.values

        truth = np.isin(fips, list(restricted)).astype(np.uint8)
        assert np.allclose(out, truth)

    LOGGERS.clear()


def test_cli_blade_clearance_invalid_partial_turbine_inputs(runner):
    """Test CLI rejects partial turbine input."""
    with tempfile.TemporaryDirectory() as td:
        regs_fpath = os.path.join(td, 'blade_regs.csv')
        _make_blade_clearance_regs(regs_fpath, {44007}, {44009})

        config = {
            "log_directory": td,
            "execution_control": {"option": "local"},
            "excl_fpath": EXCL_H5,
            "log_level": "INFO",
            "replace": True,
            "regulations_fpath": regs_fpath,
            "hub_height": 120,
        }
        config_path = os.path.join(td, 'config.json')
        with open(config_path, 'w') as f:
            json.dump(config, f)

        result = runner.invoke(cli, ['blade-clearance', '-c', config_path])
        assert result.exit_code == 1

    LOGGERS.clear()


def execute_pytest(capture='all', flags='-rapP'):
    """Execute module as pytest with detailed summary report.

    Parameters
    ----------
    capture : str
        Log or stdout/stderr capture option. ex: log (only logger),
        all (includes stdout/stderr)
    flags : str
        Which tests to show logs and results for.
    """

    fname = os.path.basename(__file__)
    pytest.main(['-q', '--show-capture={}'.format(capture), fname, flags])


if __name__ == '__main__':
    execute_pytest()
