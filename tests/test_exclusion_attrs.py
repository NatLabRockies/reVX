"""Generated exclusion dataset metadata tests."""
import os
import shutil
import json

import h5py
import numpy as np
import pytest
from click.testing import CliRunner

from reVX import TESTDATADIR
from reVX.cli import main
from reVX.exclusions._cli import cli
from reVX.exclusions.max_height.max_height import HeightRestrictionExclusions
from reVX.exclusions.max_height.regulations import HeightRestrictionRegulations
from reVX.exclusions.turbine_flicker._cli import run_flicker
from reVX.exclusions.turbine_flicker.turbine_flicker import TurbineFlicker


@pytest.mark.parametrize("attrs",
                         [None, {}, {"source": "survey", "year": 2026}])
def test_compute_exclusions_attrs(tmp_path, attrs):
    """Metadata reaches the shared writer without changing exclusion values."""
    h5_path = tmp_path / "exclusions.h5"
    shutil.copyfile(os.path.join(TESTDATADIR, "setbacks", "ri_setbacks.h5"),
                    h5_path)
    regulations = HeightRestrictionRegulations(
        system_height=150, generic_height_limit=120)
    exclusions = HeightRestrictionExclusions(str(h5_path), regulations,
                                             features=None)
    values = exclusions.compute_exclusions(out_layer="height", max_workers=1,
                                            attrs=attrs)
    with h5py.File(h5_path) as h5_file:
        dataset = h5_file["height"]
        np.testing.assert_array_equal(dataset[0], values)
        assert "profile" in dataset.attrs
        for key, value in (attrs or {}).items():
            assert dataset.attrs[key] == value
        assert "source" not in h5_file.attrs
        assert "source" not in h5_file["cnty_fips"].attrs


def test_setbacks_cli_attrs(tmp_path):
    """Setback config metadata survives feature preprocessing and CLI"""
    h5_path = tmp_path / "exclusions.h5"
    shutil.copyfile(os.path.join(TESTDATADIR, "setbacks", "ri_setbacks.h5"),
                    h5_path)
    feature_path = os.path.join(TESTDATADIR, "setbacks", "RhodeIsland.gpkg")
    config = {
        "log_directory": str(tmp_path),
        "execution_control": {"option": "local"},
        "excl_fpath": str(h5_path), "max_workers": 1,
        "features": {"structure": feature_path},
        "generic_setback_dist": 100, "generic_setback_multiplier": 1,
        "out_layers": {"RhodeIsland.gpkg": "structures"},
        "attrs": {"structures": {"source": "CLI", "year": 2026}},
    }
    config_path = tmp_path / "setbacks.json"
    config_path.write_text(json.dumps(config))
    result = CliRunner().invoke(cli, ["setbacks", "-c", str(config_path)])
    assert result.exit_code == 0, result.output
    with h5py.File(h5_path) as h5_file:
        assert h5_file["structures"].attrs["source"] == "CLI"
        assert h5_file["structures"].attrs["year"] == 2026
        assert "description" in h5_file["structures"].attrs
        assert "source" not in h5_file["cnty_fips"].attrs


def test_flicker_cli_function_attrs(tmp_path, monkeypatch):
    """Flicker's single-layer metadata is mapped for the shared run API."""
    calls = []

    def capture_run(*__, **kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(TurbineFlicker, "run", capture_run)
    attrs = {"source": "survey", "year": 2026}
    run_flicker("exclusions.h5", "resource.h5", 100, 80, str(tmp_path),
                building_layer="buildings", out_layer="flicker", attrs=attrs)
    assert calls[0]["attrs"] == {"flicker": attrs}
    assert calls[0]["out_layers"] == {"buildings": "flicker"}
    run_flicker("exclusions.h5", "resource.h5", 100, 80, str(tmp_path),
                building_layer="buildings", attrs=attrs)
    assert calls[1]["attrs"] is None


@pytest.mark.parametrize("command,inputs,filename", [
    ("max-height", {"system_height": 150, "generic_height_limit": 120},
     "height_restrictions_150m.tif"),
    ("blade-clearance", {"hub_height": 120, "rotor_diameter": 80,
                         "generic_minimum_clearance": 90},
     "blade_clearance_restrictions_120hh_80rd.tif"),
])
def test_generated_exclusion_cli_attrs(tmp_path, command, inputs, filename):
    """Generated CLI configs forward output-layer metadata to disk."""
    h5_path = tmp_path / "exclusions.h5"
    shutil.copyfile(os.path.join(TESTDATADIR, "setbacks", "ri_setbacks.h5"),
                    h5_path)
    config = {
        "log_directory": str(tmp_path),
        "execution_control": {"option": "local"},
        "excl_fpath": str(h5_path), "max_workers": 1,
        "out_layers": {filename: "restriction"},
        "attrs": {"restriction": {"source": "CLI", "year": 2026}},
        **inputs,
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))
    result = CliRunner().invoke(cli, [command, "-c", str(config_path)])
    assert result.exit_code == 0, result.output
    with h5py.File(h5_path) as h5_file:
        assert np.all(h5_file["restriction"][...] == 1)
        assert h5_file["restriction"].attrs["source"] == "CLI"
        assert h5_file["restriction"].attrs["year"] == 2026
        assert "source" not in h5_file["cnty_fips"].attrs


def test_mask_cli_attrs(tmp_path):
    """The mask CLI uses flat metadata from the exclusion config."""
    h5_path = tmp_path / "exclusions.h5"
    shutil.copyfile(os.path.join(TESTDATADIR, "setbacks", "ri_setbacks.h5"),
                    h5_path)
    config_path = tmp_path / "mask.json"
    config_path.write_text(json.dumps({
        "excl_fpath": str(h5_path),
        "excl_dict": {"cnty_fips": {"exclude_values": [0]}},
        "attrs": {"source": "CLI", "year": 2026},
    }))
    result = CliRunner().invoke(main, [
        "exclusions", "--excl_h5", str(h5_path), "mask",
        "--excl_dict_fpath", str(config_path), "--out", "mask",
    ])
    assert result.exit_code == 0, result.output
    with h5py.File(h5_path) as h5_file:
        assert h5_file["mask"].attrs["source"] == "CLI"
        assert h5_file["mask"].attrs["year"] == 2026
        assert "description" in h5_file["mask"].attrs
        assert "source" not in h5_file["cnty_fips"].attrs


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
