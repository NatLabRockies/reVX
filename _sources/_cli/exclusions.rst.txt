.. click:: reVX.exclusions._cli:cli
   :prog: exclusions
   :show-nested:

Dataset Attributes
------------------

The ``setbacks``, ``max-height``, and ``blade-clearance`` configuration files
accept an optional ``attrs`` mapping from output HDF5 layer names to attribute
dictionaries. Use ``out_layers`` to select which outputs are saved to HDF5:

.. code-block:: json

    {
       "out_layers": {"structures.gpkg": "structure_setbacks"},
       "attrs": {
          "structure_setbacks": {"source": "survey", "year": 2026}
       }
    }

For setbacks, ``out_layers`` keys are input feature filenames. Height and
blade-clearance calculations have no feature file, so their keys are output
GeoTIFF filenames: ``height_restrictions_<system_height>m.tif`` and
``blade_clearance_restrictions_<hub_height>hh_<rotor_diameter>rd.tif``.
For example, a height config with ``system_height: 150`` can include:

.. code-block:: json

    {
       "out_layers": {"height_restrictions_150m.tif": "height_limits"},
       "attrs": {"height_limits": {"source": "local regulations"}}
    }

The ``turbine-flicker`` command has one ``out_layer`` and accepts a flat
attribute dictionary instead:

.. code-block:: json

    {
       "out_layer": "flicker",
       "attrs": {"source": "building survey", "year": 2026}
    }

These fragments supplement the normal required command inputs. Attributes
apply only to output HDF5 datasets, not GeoTIFFs. Values must be supported
by HDF5 attributes, such as strings, numbers, and homogeneous lists.

