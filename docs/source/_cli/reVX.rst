.. click:: reVX.cli:main
   :prog: reVX
   :show-nested:

Dataset Attributes
------------------

``reVX exclusions layers-to-h5`` accepts an optional ``attrs`` mapping in
the JSON file supplied with ``--layers``. Keys are output HDF5 dataset names;
each value is the attribute dictionary for that dataset:

.. code-block:: json

    {
       "layers": {"regions": "regions.tif", "roads": "roads.tif"},
       "attrs": {
          "regions": {"source": "survey", "year": 2026},
          "roads": {"units": "meters"}
       }
    }

The same mapping is supported with ``--setbacks`` and
``--distance_to_ports``, including scaled layers. Layers omitted from the
mapping receive no additional attributes. The Python ``layers_to_h5`` APIs
accept the same mapping; single-layer writer methods accept a flat dictionary.

``reVX exclusions mask`` accepts a flat ``attrs`` dictionary in the config
supplied with ``--excl_dict_fpath``:

.. code-block:: json

    {
       "excl_dict": {"regions": {"exclude_values": [0]}},
       "attrs": {"source": "combined exclusions", "year": 2026}
    }

Attributes apply to the output HDF5 dataset only, not global file attributes
or GeoTIFF outputs. Values must be supported by HDF5 attributes, such as
strings, numbers, and homogeneous lists. Omitting ``attrs`` preserves existing
behavior. Attribute names that overlap writer-generated metadata follow the
underlying writer's precedence rules.
