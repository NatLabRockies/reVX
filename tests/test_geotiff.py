# -*- coding: utf-8 -*-
"""
pytests for exclusions converter
"""
import os
import numpy as np
import pytest
import rasterio
from pyproj import Transformer

from reV.handlers.exclusions import ExclusionLayers

from reVX.handlers.geotiff import Geotiff
from reVX import TESTDATADIR

DIR = os.path.join(TESTDATADIR, 'ri_exclusions')
EXCL_H5 = os.path.join(DIR, 'ri_exclusions.h5')


def extract_layer(h5_path, layer):
    """
    Extract layer data from .h5 file

    Parameters
    ----------
    h5_path : str
        Path to .h5 file of interest
    layer : str
        Layer to extract data for

    Returns
    -------
    values : ndarray
        Layer values
    profile : str
        Layer profile
    """
    with ExclusionLayers(h5_path) as f:
        values = f.get_layer_values(layer)
        profile = f.get_layer_profile(layer)

    return values, profile


@pytest.fixture
def output_profile():
    """Small georeferenced profile for writer tests."""
    return {'driver': 'GTiff', 'height': 2, 'width': 2, 'count': 1,
            'dtype': 'float32', 'crs': 'EPSG:4326',
            'transform': rasterio.transform.from_origin(-71, 42, 0.1, 0.1)}


@pytest.mark.parametrize('layer',
                         ['ri_padus', 'ri_reeds_regions', 'ri_smod',
                          'ri_srtm_slope'])
def test_geotiff_properties(layer):
    """
    Test Geotiff class properties

    Parameters
    ----------
    layer : str
        Layer to extract
    """
    geotiff = os.path.join(DIR, f'{layer}.tif')
    with Geotiff(geotiff) as f:
        inds_x = [np.random.randint(low=0, high=f.shape[0] // 2),
                  np.random.randint(low=f.shape[0] // 2, high=f.shape[0])]
        inds_y = [np.random.randint(low=0, high=f.shape[1] // 2),
                  np.random.randint(low=f.shape[1] // 2, high=f.shape[1])]
        slices = [slice(*inds_x), slice(*inds_y)]
        values = f[0, slices[0], slices[1]]
        all_values = f.values

    true_values, _ = extract_layer(EXCL_H5, layer)

    assert np.allclose(true_values[0, slices[0], slices[1]].flatten(), values)
    assert np.allclose(true_values, all_values)


def test_geotiff_getter():
    """
    Test extraction of layer and creation of GeoTiff

    Parameters
    ----------
    layer : str
        Layer to extract
    """
    geotiff = os.path.join(DIR, 'ri_padus.tif')
    with Geotiff(geotiff) as f:
        band = f[0]
        values = f.values

    true_values, _ = extract_layer(EXCL_H5, 'ri_padus')

    assert np.allclose(true_values.ravel(), band)
    assert np.allclose(values.ravel(), band)


def test_geotiff_shapes():
    """Test Geotiff shapes"""
    geotiff = os.path.join(DIR, 'ri_padus.tif')
    with Geotiff(geotiff) as f:
        assert f.shape == f.tiff_shape[1:]
        assert f.bands == f.tiff_shape[0]
        assert f.n_rows == f.tiff_shape[1]
        assert f.n_cols == f.tiff_shape[2]


def test_geotiff_profile():
    """Test Geotiff Profile"""
    geotiff = os.path.join(DIR, 'ri_padus.tif')
    __, profile = extract_layer(EXCL_H5, 'ri_padus')
    with Geotiff(geotiff) as f:
        assert (rasterio.crs.CRS.from_string(f.profile["crs"])
                == rasterio.crs.CRS.from_string(profile["crs"]))
        assert np.allclose(f.profile["transform"], profile["transform"])
        assert f.profile["tiled"] == profile["tiled"]
        assert f.profile["nodata"] == profile["nodata"]
        assert f.profile["blockxsize"] == profile["blockxsize"]
        assert f.profile["blockysize"] == profile["blockysize"]
        assert f.profile["dtype"] == profile["dtype"]
        assert f.profile["count"] == profile["count"]
        assert f.profile["height"] == profile["height"]
        assert f.profile["width"] == profile["width"]


@pytest.mark.parametrize("use_prop", [True, False])
def test_geotiff_lat_lon(use_prop):
    """Test Geotiff Lat/Lon"""
    geotiff = os.path.join(DIR, "ri_padus.tif")
    with Geotiff(geotiff) as f:
        lat, lon = f.lat_lon if use_prop else f["lAt_LON"]
        cols, rows = np.meshgrid(np.arange(f.n_cols), np.arange(f.n_rows))
        transform = rasterio.transform.Affine(*f.profile["transform"])
        xs, ys = rasterio.transform.xy(transform, rows, cols)
        transformer = Transformer.from_crs(f.profile["crs"],
                                           'epsg:4326', always_xy=True)
        # pylint: disable=unpacking-non-sequence
        lon_truth, lat_truth = transformer.transform(np.array(xs),
                                                     np.array(ys))
        assert np.allclose(lon.flatten(), lon_truth.flatten())
        assert np.allclose(lat.flatten(), lat_truth.flatten())
        assert lon.min() > -71.912
        assert lon.max() < -70.856
        assert lat.min() > 40.8558
        assert lat.max() < 42.0189


@pytest.mark.parametrize("x_slice", [slice(100, 200), slice(1000, 1400)])
@pytest.mark.parametrize("y_slice", [slice(275, 324), slice(-100, None)])
def test_geotiff_lat_lon_sliced(x_slice, y_slice):
    """Test Geotiff Lat/Lon sliced accessor"""
    geotiff = os.path.join(DIR, "ri_padus.tif")
    with Geotiff(geotiff) as f:
        lat, lon = f["lat_lon", x_slice, y_slice]
        cols, rows = np.meshgrid(np.arange(f.n_cols), np.arange(f.n_rows))
        transform = rasterio.transform.Affine(*f.profile["transform"])
        xs, ys = rasterio.transform.xy(transform, rows, cols)
        transformer = Transformer.from_crs(f.profile["crs"],
                                           'epsg:4326', always_xy=True)
        # pylint: disable=unpacking-non-sequence
        lon_truth, lat_truth = transformer.transform(np.array(xs),
                                                     np.array(ys))
        lon_truth = lon_truth.reshape(rows.shape)
        lat_truth = lat_truth.reshape(rows.shape)
        lon_truth = lon_truth[x_slice, y_slice]
        lat_truth = lat_truth[x_slice, y_slice]
        assert np.allclose(lon, lon_truth)
        assert np.allclose(lat, lat_truth)


@pytest.mark.parametrize("x_inds", ([1, 5, 10], slice(1, 20)))
@pytest.mark.parametrize("y_inds", ([3, 4, 5], slice(None)))
def test_geotiff_lat_lon_components_sliced(x_inds, y_inds):
    """Test Geotiff Lat/Lon components with sliced accessor"""
    geotiff = os.path.join(DIR, 'ri_padus.tif')
    with Geotiff(geotiff) as f:
        lat_truth, lon_truth = f.lat_lon
        lat = f["latitude", x_inds, y_inds]
        lon = f["longitude", x_inds, y_inds]

        assert np.allclose(lon, lon_truth[x_inds, y_inds])
        assert np.allclose(lat, lat_truth[x_inds, y_inds])


@pytest.mark.parametrize('dtype,nodata,expected', [
    ('uint8', float(np.finfo('float32').max), 255),
    ('uint8', -9999, 255),
    ('uint8', np.nan, 255),
    ('uint8', np.inf, 255),
    ('float32', float(np.finfo('float64').max), np.finfo('float32').max),
    ('uint8', None, None),
    ('uint8', 0, 0),
    ('int16', -9999, -9999),
    ('float32', -9999, -9999),
    ('float32', np.nan, np.nan),
])
def test_geotiff_write_nodata(tmp_path, output_profile, dtype, nodata,
                             expected):
    """Replace incompatible inherited nodata, preserving valid settings."""
    output_profile['nodata'] = nodata
    values = np.array([[0, 1], [1, 0]], dtype=dtype)
    out_fp = tmp_path / 'output.tif'

    Geotiff.write(out_fp, output_profile, values)

    with rasterio.open(out_fp) as src:
        assert src.dtypes == (dtype,)
        if expected is not None and np.isnan(expected):
            assert np.isnan(src.nodata)
        else:
            assert src.nodata == expected
        assert src.crs == rasterio.crs.CRS.from_epsg(4326)
        assert src.transform == output_profile['transform']
        np.testing.assert_array_equal(src.read(1), values)


def test_geotiff_write_dtype_override(tmp_path, output_profile):
    """Validate inherited nodata against the explicitly requested dtype."""
    output_profile['nodata'] = float(np.finfo('float32').max)
    values = np.ones((2, 2), dtype='float32')
    out_fp = tmp_path / 'output.tif'

    Geotiff.write(out_fp, output_profile, values, dtype='uint8')

    with rasterio.open(out_fp) as src:
        assert src.dtypes == ('uint8',)
        assert src.nodata == 255
        np.testing.assert_array_equal(src.read(1), values)


def test_geotiff_write_default_nodata(tmp_path, output_profile):
    """Missing nodata remains unset in the output GeoTIFF."""
    out_fp = tmp_path / 'output.tif'
    values = np.ones((2, 2), dtype='int16')

    Geotiff.write(out_fp, output_profile, values)

    with rasterio.open(out_fp) as src:
        assert src.nodata is None
        np.testing.assert_array_equal(src.read(1), values)


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
