# -*- coding: utf-8 -*-
# pylint: disable=protected-access,unused-argument,redefined-outer-name
# pylint: disable=too-many-arguments,too-many-locals
"""
Height exclusion tests
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
from reVX.exclusions.max_height.regulations import (
    HeightRestrictionRegulations, validate_height_regulations_input)
from reVX.exclusions.max_height.max_height import HeightRestrictionExclusions

from reVX.exclusions._cli import cli


EXCL_H5 = os.path.join(TESTDATADIR, 'setbacks', 'ri_setbacks.h5')
REGS_FPATH = os.path.join(TESTDATADIR, 'setbacks', 'ri_wind_regs_fips.csv')


@pytest.fixture(scope="module")
def runner():
    """
    cli runner
    """
    return CliRunner()


def _find_out_tiff_file(directory):
    """Find the (single) tiff output file in the directory. """

    out_file = [fp for fp in os.listdir(directory) if fp.endswith("tif")]
    assert any(out_file)
    out_file = os.path.join(directory, out_file[0])
    return out_file


def _make_height_restriction_regs(out_fpath, restricted_fips,
                                  unrestricted_fips=None,
                                  restricted_height=100,
                                  unrestricted_height=300):
    """Create a local regulations csv for height restriction tests."""
    restricted_fips = set(restricted_fips)
    unrestricted_fips = set(unrestricted_fips or set())
    all_fips = sorted(restricted_fips | unrestricted_fips)

    regs = pd.DataFrame({
        'Feature Type': ['Maximum Height'] * len(all_fips),
        'Feature Subtype': [''] * len(all_fips),
        'Value Type': ['Meters'] * len(all_fips),
        'Value': [restricted_height if f in restricted_fips
                  else unrestricted_height
                  for f in all_fips],
        'FIPS': all_fips,
    })
    regs.to_csv(out_fpath, index=False)
    return regs


def test_validate_height_restriction_regulations_input():
    """Test strict input validation for height restriction mode."""
    with pytest.raises(RuntimeError):
        validate_height_regulations_input(
            hub_height=100,
            regulations_fpath=REGS_FPATH,
        )

    with pytest.raises(RuntimeError):
        validate_height_regulations_input(
            rotor_diameter=100,
            regulations_fpath=REGS_FPATH,
        )

    with pytest.raises(RuntimeError):
        validate_height_regulations_input(
            regulations_fpath=REGS_FPATH,
        )

    with pytest.raises(RuntimeError):
        validate_height_regulations_input(
            system_height=150,
        )

    with pytest.raises(RuntimeError):
        validate_height_regulations_input(
            system_height=150,
            hub_height=100,
            rotor_diameter=100,
            regulations_fpath=REGS_FPATH,
        )


def test_select_height_restriction_regulations():
    """Test selecting height restriction regulations mode."""
    regs = HeightRestrictionRegulations(
        regulations_fpath=REGS_FPATH,
        system_height=150,
    )
    assert isinstance(regs, HeightRestrictionRegulations)
    assert np.isclose(regs.system_height, 150)


@pytest.mark.parametrize('max_workers', [1, 4])
def test_height_restriction_exclusions(max_workers):
    """Test local-only county exclusions for height restrictions."""
    with ExclusionLayers(EXCL_H5) as exc:
        fips = exc['cnty_fips']
        all_fips = sorted(set(np.unique(fips[fips > 0])))

    restricted = {all_fips[0], all_fips[3]}
    unrestricted = {all_fips[1], all_fips[10]}
    with tempfile.TemporaryDirectory() as td:
        regs_fpath = os.path.join(td, 'height_regs.csv')
        _make_height_restriction_regs(regs_fpath, restricted, unrestricted,
                                      restricted_height=120,
                                      unrestricted_height=180)

        regs = HeightRestrictionRegulations(
            regulations_fpath=regs_fpath,
            system_height=150,
        )
        hr = HeightRestrictionExclusions(EXCL_H5, regs, features=None)
        out = hr.compute_exclusions(max_workers=max_workers)

        truth = np.isin(fips, list(restricted)).astype(np.uint8)
        assert np.allclose(out, truth)


def test_cli_height_restriction(runner):
    """Test CLI for local-only height restriction mode."""
    with ExclusionLayers(EXCL_H5) as exc:
        fips = exc['cnty_fips']
        all_fips = sorted(set(np.unique(fips[fips > 0])))

    restricted = {all_fips[0], all_fips[3]}
    unrestricted = {all_fips[1], all_fips[10]}
    with tempfile.TemporaryDirectory() as td:
        regs_fpath = os.path.join(td, 'height_regs.csv')
        _make_height_restriction_regs(regs_fpath, restricted, unrestricted,
                                      restricted_height=120,
                                      unrestricted_height=180)

        config = {
            "log_directory": td,
            "execution_control": {"option": "local"},
            "excl_fpath": EXCL_H5,
            "log_level": "INFO",
            "regulations_fpath": regs_fpath,
            "replace": True,
            "system_height": 150,
        }
        config_path = os.path.join(td, 'config.json')
        with open(config_path, 'w') as f:
            json.dump(config, f)

        result = runner.invoke(cli, ['max-height', '-c', config_path])
        assert result.exit_code == 0, result.output

        test_fp = _find_out_tiff_file(td)
        with Geotiff(test_fp) as tif:
            out = tif.values

        truth = np.isin(fips, list(restricted)).astype(np.uint8)
        assert np.allclose(out, truth)

    LOGGERS.clear()


def test_cli_height_restriction_invalid_generic_multiplier(runner):
    """Test CLI rejects bad input"""
    with tempfile.TemporaryDirectory() as td:
        regs_fpath = os.path.join(td, 'height_regs.csv')
        _make_height_restriction_regs(regs_fpath, {44007}, {44009})

        config = {
            "log_directory": td,
            "execution_control": {"option": "local"},
            "excl_fpath": EXCL_H5,
            "log_level": "INFO",
            "replace": True,
            "regulations_fpath": regs_fpath,
            "system_height": 150,
            "hub_height": 100,
            "rotor_diameter": 100,
        }
        config_path = os.path.join(td, 'config.json')
        with open(config_path, 'w') as f:
            json.dump(config, f)

        result = runner.invoke(cli, ['max-height', '-c', config_path])
        assert result.exit_code == 1
        assert 'Must provide exactly one of' in str(result.exception)

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
