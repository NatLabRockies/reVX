# -*- coding: utf-8 -*-
"""reVX PLEXOS unit test module
"""
from click.testing import CliRunner
import geopandas as gpd
import os
import pytest
import pandas as pd
from pandas.testing import assert_series_equal
from shapely.geometry import box
import tempfile
import traceback

from rex.utilities.loggers import LOGGERS

from reVX import TESTDATADIR
from reVX.utilities.region_classifier import RegionClassifier
from reVX.cli import main


META_PATH = os.path.join(TESTDATADIR, 'classification/meta.csv')
REGIONS_PATH = os.path.join(TESTDATADIR, 'classification/us_states.shp')
RESULTS_PATH = os.path.join(TESTDATADIR, 'classification/new_meta.csv')

REGIONS_LABEL = 'NAME'


@pytest.fixture(scope="module")
def runner():
    """
    cli runner
    """
    return CliRunner()


def test_region_classification():
    """Test the rpm clustering pipeline and run a baseline validation."""

    classification = RegionClassifier.run(meta_path=META_PATH,
                                          regions=REGIONS_PATH,
                                          regions_label=REGIONS_LABEL,
                                          force=True)

    test_labels = classification[REGIONS_LABEL]
    baseline = pd.read_csv(RESULTS_PATH)
    valid_labels = baseline[REGIONS_LABEL]
    bad_mask = (test_labels != valid_labels)
    msg = ('Classification failed on these sites: \n{}\nGot new labels:\n{}'
           .format(baseline[bad_mask], test_labels[bad_mask]))
    assert not any(bad_mask), msg


@pytest.mark.parametrize('labels', [['west', 'east'], [1, 2]])
@pytest.mark.parametrize('force', [False, True])
def test_region_label_types(labels, force):
    """Region labels and the outlier sentinel can coexist in one column."""
    meta = pd.DataFrame({'latitude': [0.5, 0.5, 0.5],
                         'longitude': [0.5, 2.5, 4.0]}, index=[10, 20, 30])
    regions = gpd.GeoDataFrame(
        {REGIONS_LABEL: labels},
        geometry=[box(0, 0, 1, 1), box(2, 0, 3, 1)],
        crs=RegionClassifier.CRS)

    classifier = RegionClassifier(meta, regions, regions_label=REGIONS_LABEL)
    classification = classifier.classify(force=force)

    expected = pd.Series(
        [*labels, labels[1] if force else -999],
        index=meta.index, name=REGIONS_LABEL, dtype=object)
    assert_series_equal(classification[REGIONS_LABEL], expected)


def test_cli(runner):
    """
    Test CLI
    """
    valid_labels = pd.read_csv(RESULTS_PATH)[REGIONS_LABEL]
    with tempfile.TemporaryDirectory() as td:
        out_path = os.path.join(td, 'test.csv')
        result = runner.invoke(main, ['region-classifier',
                                      '-mp', META_PATH,
                                      '-rp', REGIONS_PATH,
                                      '-rl', REGIONS_LABEL,
                                      '-o', out_path,
                                      '-f'])
        msg = ('Failed with error {}'
               .format(traceback.print_exception(*result.exc_info)))
        assert result.exit_code == 0, msg

        test_labels = pd.read_csv(out_path)[REGIONS_LABEL]

    assert_series_equal(test_labels, valid_labels)

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
