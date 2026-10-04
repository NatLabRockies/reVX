"""Disk-backed transmission layer metadata API and CLI tests."""
import copy
import json

import h5py
import numpy as np
import pytest
import rasterio
from click.testing import CliRunner
from rasterio.transform import from_origin

from reVX.config.transmission_layer_creation import (
    LayerBuildConfig, MergeFrictionBarriers,
)
from reVX.handlers.layered_h5 import LayeredTransmissionH5
from reVX.least_cost_xmission.layers import LayerCreator
from reVX.least_cost_xmission.layers.dry_cost_creator import DryCostCreator
from reVX.least_cost_xmission.layers.masks import Masks
from reVX.least_cost_xmission.transmission_layer_creator_cli import (
    _combine_friction_and_barriers, main,
)


@pytest.fixture
def layer_files(tmp_path):
    """Create aligned rasters and an empty transmission H5 on disk."""
    profile = {
        "driver": "GTiff", "height": 128, "width": 128, "count": 1,
        "dtype": "float32", "crs": "EPSG:32613",
        "transform": from_origin(500000, 4400000, 90, 90),
    }
    files = {}
    for name, value in (("iso", 1), ("nlcd", 21), ("slope", 0),
                        ("extra", 7), ("friction", 2), ("barrier", 3)):
        path = tmp_path / f"{name}.tif"
        with rasterio.open(path, "w", **profile) as raster:
            raster.write(np.full((1, 128, 128), value, dtype="float32"))
        files[name] = str(path)
    handler = LayeredTransmissionH5(
        str(tmp_path / "layers.h5"), template_file=files["iso"])
    handler.create_new()
    return files, handler


@pytest.fixture
def cost_config_path(tmp_path):
    """Use section JSON files supported by the transmission config loader."""
    sections = {
        "power_classes": {"100MW": 100},
        "base_line_costs": {"TEPPC": {"100": 1609}},
        "iso_multipliers": [],
    }
    paths = {}
    for name, values in sections.items():
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(values))
        paths[name] = str(path)
    path = tmp_path / "costs.json"
    path.write_text(json.dumps(paths))
    return str(path)


@pytest.mark.parametrize("attrs",
                         [None, {}, {"source": "survey", "year": 2026}])
def test_layer_build_attrs(layer_files, tmp_path, attrs):
    """Layer builds preserve data and description while forwarding attrs."""
    files, handler = layer_files
    original = copy.deepcopy(attrs)
    builder = LayerCreator(handler, Masks(handler), tmp_path)
    builder.build("custom.tif", {files["friction"]: LayerBuildConfig(
        pass_through=True)}, description="Custom costs", attrs=attrs)
    builder.build("tiff_only", {}, write_to_h5=False, attrs=attrs)

    with h5py.File(handler.h5_file) as h5_file:
        dataset = h5_file["custom"]
        assert np.all(dataset[...] == 2)
        assert dataset.attrs["description"] == "Custom costs"
        assert "profile" in dataset.attrs
        for key, value in (attrs or {}).items():
            assert dataset.attrs[key] == value
        if not attrs:
            assert "source" not in dataset.attrs
        assert "tiff_only" not in h5_file
    assert attrs == original
    assert (tmp_path / "tiff_only.tif").exists()


@pytest.mark.parametrize("attrs", [None, {}, {
    "iso": {"source": "regions"},
    "nlcd": {"year": 2026},
    "slope": {"units": "percent"},
    "extra": {"source": "extra raster"},
    "dry_multipliers": {"units": "multiplier"},
    "tie_line_costs_100MW": {"units": "USD/cell", "capacity": 100},
}])
def test_dry_cost_build_attrs(layer_files, tmp_path, cost_config_path, attrs):
    """Both dry-cost writer loops select metadata by H5 dataset name."""
    files, handler = layer_files
    original = copy.deepcopy(attrs)
    creator = DryCostCreator(handler, np.full(handler.shape, True), tmp_path)
    creator.build(files["iso"], files["nlcd"], files["slope"],
                  cost_configs=cost_config_path,
                  extra_tiffs=[files["extra"], files["friction"]], attrs=attrs)

    with h5py.File(handler.h5_file) as h5_file:
        assert np.all(h5_file["dry_multipliers"][...] == 1)
        assert np.all(h5_file["tie_line_costs_100MW"][...] > 0)
        for layer_name, layer_attrs in (attrs or {}).items():
            for key, value in layer_attrs.items():
                assert h5_file[layer_name].attrs[key] == value
        assert "source" not in h5_file["friction"].attrs
        assert "units" not in h5_file["iso"].attrs
        if not attrs:
            assert "units" not in h5_file["tie_line_costs_100MW"].attrs
    assert attrs == original


@pytest.mark.parametrize("attrs", [None, {}, {"source": "API override"}])
def test_merge_attrs(layer_files, tmp_path, attrs):
    """Merge uses config metadata unless the API supplies an override."""
    _, handler = layer_files
    config = MergeFrictionBarriers(
        friction_layer="friction", barrier_layer="barrier",
        output_layer_name="merged", barrier_multiplier=10,
        attrs={"source": "config"})
    _combine_friction_and_barriers(config, handler, tmp_path, attrs=attrs)
    with h5py.File(handler.h5_file) as h5_file:
        dataset = h5_file["merged"]
        assert np.all(dataset[...] == 32)
        expected = config.attrs if attrs is None else attrs
        if expected:
            assert dataset.attrs["source"] == expected["source"]
        else:
            assert "source" not in dataset.attrs
    assert config.attrs == {"source": "config"}


def test_from_config_attrs(layer_files, tmp_path, cost_config_path):
    """JSON config forwards metadata through all transmission actions."""
    files, handler = layer_files
    config = {
        "h5_fpath": handler.h5_file,
        "template_raster_fpath": files["iso"],
        "output_tiff_dir": str(tmp_path),
        "layers": [{
            "layer_name": "custom", "description": "CLI layer",
            "build": {files["friction"]: {"pass_through": True}},
            "attrs": {"source": "CLI", "year": 2026},
        }],
        "dry_costs": {
            "iso_region_tiff": files["iso"], "nlcd_tiff": files["nlcd"],
            "slope_tiff": files["slope"], "cost_configs": cost_config_path,
            "extra_tiffs": [files["extra"]],
            "attrs": {"iso": {"source": "regions"},
                      "extra": {"year": 2026},
                      "dry_multipliers": {"units": "multiplier"},
                      "tie_line_costs_100MW": {"units": "USD/cell"}},
        },
        "merge_friction_and_barriers": {
            "friction_layer": "custom", "barrier_layer": "barrier",
            "output_layer_name": "merged", "barrier_multiplier": 10,
            "attrs": {"source": "CLI merge"},
        },
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))
    result = CliRunner().invoke(main, ["from-config", "-c", str(config_path)])
    assert result.exit_code == 0, result.output
    with h5py.File(handler.h5_file) as h5_file:
        assert h5_file["custom"].attrs["source"] == "CLI"
        assert h5_file["custom"].attrs["year"] == 2026
        assert h5_file["custom"].attrs["description"] == "CLI layer"
        assert h5_file["iso"].attrs["source"] == "regions"
        assert h5_file["extra"].attrs["year"] == 2026
        assert h5_file["dry_multipliers"].attrs["units"] == "multiplier"
        assert h5_file["tie_line_costs_100MW"].attrs["units"] == "USD/cell"
        assert h5_file["merged"].attrs["source"] == "CLI merge"
        assert np.all(h5_file["merged"][...] == 32)
        assert "source" not in h5_file["nlcd"].attrs
