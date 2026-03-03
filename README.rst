*********************************************************************************
Welcome to the `reV <https://natlabrockies.github.io/reV>`_ eXchange (reVX) tool!
*********************************************************************************

|Docs| |Tests| |Linter| |PythonV| |PyPi| |Codecov| |Zenondo|

.. |Docs| image:: https://github.com/NatLabRockies/reVX/workflows/Documentation/badge.svg
    :target: https://natlabrockies.github.io/reVX/

.. |Tests| image:: https://github.com/NatLabRockies/reVX/actions/workflows/pull_request_tests.yml/badge.svg
    :target: https://github.com/NatLabRockies/reVX/actions?query=workflow%3A%22Pytests%22

.. |Linter| image:: https://github.com/NatLabRockies/reVX/actions/workflows/linter.yml/badge.svg
    :target: https://github.com/NatLabRockies/reVX/actions?query=workflow%3A%22Lint+Code+Base%22

.. |PythonV| image:: https://img.shields.io/pypi/pyversions/NLR-reVX.svg
    :target: https://pypi.org/project/NLR-reVX/

.. |PyPi| image:: https://badge.fury.io/py/NLR-reVX.svg
    :target: https://badge.fury.io/py/NLR-reVX

.. |Codecov| image:: https://codecov.io/gh/NatLabRockies/reVX/branch/main/graph/badge.svg?token=3J5M44VAA9
    :target: https://codecov.io/gh/NatLabRockies/reVX

.. |Zenondo| image:: https://zenodo.org/badge/201337735.svg
   :target: https://zenodo.org/badge/latestdoi/201337735

.. inclusion-intro

reVX command line tools
=======================

- `reVX <https://natlabrockies.github.io/reVX/_cli/reVX.html#revx>`_
- `reV-rpm <https://natlabrockies.github.io/reVX/_cli/reV-rpm.html#rev-rpm>`_
- `reV-plexos <https://natlabrockies.github.io/reVX/_cli/reV-plexos.html>`_
- `plexos-plants <https://natlabrockies.github.io/reVX/_cli/plexos-plants.html#plexos-plants>`_
- `mean-wind-dirs <https://natlabrockies.github.io/reVX/_cli/mean-wind-dirs.html#mean-wind-dirs>`_
- `prominent-wind-dirs <https://natlabrockies.github.io/reVX/_cli/prominent-wind-dirs.html#prominent-wind-dirs>`_
- `setbacks <https://natlabrockies.github.io/reVX/_cli/setbacks.html#setbacks>`_
- `offshore-assembly-areas <https://natlabrockies.github.io/reVX/_cli/offshore-assembly-areas.html#offshore-assembly-areas>`_
- `offshore-dist-to-ports <https://natlabrockies.github.io/reVX/_cli/offshore-dist-to-ports.html#offshore-dist-to-ports>`_
- `offshore-inputs <https://natlabrockies.github.io/reVX/_cli/offshore-inputs.html#offshore-inputs>`_

Installing reVX
===============

NOTE: The installation instruction below assume that you have python installed
on your machine and are using `conda <https://docs.conda.io/en/latest/index.html>`_
as your package/environment manager.

#. Create a new environment:
    ``conda create --name revx python=3.11``

#. Activate your new environment:
    ``conda activate revx``

#. Clone the repo:
    From your home directory ``/home/{user}/`` or another directory that you have permissions in, run the command ``git clone git@github.com:NatLabRockies/reVX.git`` and then go into your cloned repository: ``cd reVX``

#. Install reVX:
    1) Follow the installation commands installation process that we use for our automated test suite `here <https://github.com/NatLabRockies/reVX/blob/main/.github/workflows/pull_request_tests.yml#L33-L36>`_. Make sure that you call ``pip install --no-build-isolation -e .`` from within the cloned repository directory e.g. ``/home/{user}/reVX/``. Don't forget to run ``pip install --upgrade setuptools``, especially if you run into any build errors.

        - NOTE: If you install using pip and want to run `exclusion setbacks <https://natlabrockies.github.io/reVX/_cli/reVX.exclusions.setbacks.setbacks.html>`_ you will need to install rtree manually:
            * ``conda install rtree``
            * `pip installation instructions <https://pypi.org/project/Rtree/#:~:text=Rtree%20is%20a%20ctypes%20Python,Multi%2Ddimensional%20indexes>`_
        - NOTE: If you install using pip and want to run shadow flicker exclusions, make sure you:
            * Use Python 3.10 or 3.11: ``conda create --name revx python=3.11``
            * Install the ``flicker`` dependency: ``pip install -e .[flicker]``

Recommended Citation
====================

Update with current version and DOI:

Michael Rossol, Grant Buster, and Robert Spencer.
The reV eXchange Tool: reVX. https://github.com/NatLabRockies/reVX
(version v0.3.20), 2021. https://doi.org/10.5281/zenodo.4507580.
