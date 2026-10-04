.. click:: reVX.least_cost_xmission.transmission_layer_creator_cli:main
   :prog: transmission-layer-creator
   :show-nested:

Dataset Attributes
------------------

The ``from-config`` command accepts optional ``attrs`` fields in its JSON
configuration. Each entry in ``layers`` and ``merge_friction_and_barriers``
accepts an attribute dictionary for its output HDF5 dataset. ``dry_costs``
accepts a mapping of HDF5 dataset names to attribute dictionaries, allowing
different metadata for each generated or imported layer:

.. code-block:: json

    {
       "layers": [
          {
             "layer_name": "friction",
             "description": "Routing friction",
             "build": {"friction.tif": {"pass_through": true}},
             "attrs": {"source": "survey", "year": 2026}
          }
       ],
       "dry_costs": {
          "iso_region_tiff": "regions.tif",
          "nlcd_tiff": "nlcd.tif",
          "slope_tiff": "slope.tif",
          "attrs": {
             "regions": {"source": "ISO boundaries"},
             "dry_multipliers": {"units": "multiplier"},
             "tie_line_costs_100MW": {"units": "USD/cell"}
          }
       },
       "merge_friction_and_barriers": {
          "friction_layer": "friction",
          "barrier_layer": "barriers",
          "attrs": {"source": "Combined routing constraints"}
       }
    }

This fragment supplements the normal required paths, including
``template_raster_fpath`` and ``h5_fpath``. Dry-cost input and ``extra_tiffs``
dataset names are their filename stems, without directories or extensions.
Generated layers use ``dry_multipliers`` and ``tie_line_costs_<capacity>MW``.
Base-line-cost GeoTIFFs are not written to HDF5 and cannot receive dataset
attributes. Layers omitted from the mapping receive no additional attributes.

The Python APIs ``LayerCreator.build`` and ``DryCostCreator.build`` accept
the same optional ``attrs`` inputs. Attributes apply only to HDF5 datasets, not the
GeoTIFF output, and layers with ``include_in_h5: false`` are not written to HDF5.
Values must be supported by HDF5 attributes, such as strings, numbers, and
homogeneous lists. Metadata is passed through to the underlying writer;
attribute names that overlap writer-generated metadata follow that writer's
precedence rules.
