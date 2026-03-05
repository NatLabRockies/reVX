# -*- coding: utf-8 -*-
# pylint: disable=all
"""
Base exclusions functionality tests
"""
import os
from itertools import product

import pytest
import numpy as np
import rasterio
import geopandas as gpd
from reV.handlers.exclusions import ExclusionLayers

from reVX import TESTDATADIR
from reVX.exclusions.base import Rasterizer


EXCL_H5 = os.path.join(TESTDATADIR, 'setbacks', 'ri_setbacks.h5')


@pytest.fixture(scope='module')
def excl_props():
    """Exclusion layer properties to use for tests"""
    with ExclusionLayers(EXCL_H5) as excl:
        crs = excl.crs
        shape = excl.shape
        profile = excl.profile

    if len(shape) < 3:
        shape = (1, *shape)

    return crs, shape, profile


def test_rasterizer_array_dtypes(excl_props):
    """Test that rasterizing empty array yields correct array dtypes."""
    __, shape, profile = excl_props
    rasterizer = Rasterizer(shape, profile,
                            weights_calculation_upscale_factor=1)
    rasterizer_hr = Rasterizer(shape, profile,
                               weights_calculation_upscale_factor=5)

    assert rasterizer.rasterize(shapes=None).dtype == np.uint8
    assert rasterizer_hr.rasterize(shapes=None).dtype == np.float32


def test_rasterizer_window(excl_props):
    """Test rasterizing in a window. """
    crs, shape, profile = excl_props
    rail_path = os.path.join(TESTDATADIR, 'setbacks',
                             'Rhode_Island_Railroads.gpkg')

    features = gpd.read_file(rail_path).to_crs(crs)
    features = list(features["geometry"].buffer(500))

    transform = rasterio.Affine(*profile["transform"])
    window = rasterio.windows.from_bounds(70_000, 30_000, 130_000, 103_900,
                                          transform)
    window = window.round_offsets().round_lengths()

    rasterizer = Rasterizer(shape, profile, 1)

    raster = rasterizer.rasterize(features)
    window_raster = rasterizer.rasterize(features, window=window)

    assert raster.shape == shape[1:]
    assert window_raster.shape == (window.height, window.width)
    assert np.allclose(raster[window.toslices()], window_raster)


@pytest.mark.parametrize('set_uf', [True, False])
def test_high_res_excl_array(set_uf, excl_props):
    """Test the multiplier of the exclusion array is applied correctly. """

    __, shape, profile = excl_props
    mult = 5

    if set_uf:
        rasterizer = Rasterizer(shape, profile)
        rasterizer.scale_factor = mult
    else:
        rasterizer = Rasterizer(shape, profile,
                                weights_calculation_upscale_factor=mult)

    hr_array = rasterizer._no_exclusions_array(multiplier=mult)

    assert hr_array.dtype == np.uint8
    for ind, shape in enumerate(rasterizer.arr_shape[1:]):
        assert shape != hr_array.shape[ind]
        assert shape * mult == hr_array.shape[ind]


def test_aggregate_high_res(excl_props):
    """Test the aggregation of a high_resolution array. """

    __, shape, profile = excl_props
    mult = 5
    rasterizer = Rasterizer(shape, profile,
                            weights_calculation_upscale_factor=mult)

    hr_array = rasterizer._no_exclusions_array(multiplier=mult)
    hr_array = hr_array.astype(np.float32)
    arr_to_rep = np.arange(rasterizer.arr_shape[1] * rasterizer.arr_shape[2],
                           dtype=np.float32)
    arr_to_rep = arr_to_rep.reshape(rasterizer.arr_shape[1:])

    for i, j in product(range(mult), range(mult)):
        hr_array[i::mult, j::mult] += arr_to_rep

    assert np.allclose(rasterizer._aggregate_high_res(hr_array, window=None),
                       arr_to_rep * mult ** 2)


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
