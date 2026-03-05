# reVX Blade Clearance

The ``reVX`` blade clearance module computes local-only exclusion masks for wind
siting workflows where jurisdictions define a minimum allowed blade clearance.

It excludes counties where turbine blade clearance is smaller than the local
minimum requirement.

This guide is supplemental to the generated CLI/API docs and follows the same
project-directory workflow used by other ``reVX`` exclusions tools.

<br>

## Computing blade clearance exclusions
### Inputs and prerequisites
Before running blade clearance, make sure you have:

1. A template exclusions HDF5 file (``excl_fpath``) that defines the output
   grid.
2. A local regulations file (``regulations_fpath``) in ``.csv`` or ``.gpkg``
   format containing blade-clearance rows.
3. Turbine specifications:
   - ``hub_height`` (m)
   - ``rotor_diameter`` (m)
4. If ``regulations_fpath`` is tabular (CSV without geometry), ``excl_fpath``
   must contain a county FIPS layer named ``cnty_fips`` for county matching.

### Config file setup
Each blade clearance project should be run from its own directory.

Create a new directory, move into it, and generate template config files:
```console
$ exclusions template-configs
```

Then create or edit your blade clearance config and include at least the
required keys below:

```json
{
    "execution_control": {
        "option": "local"
    },
    "log_directory": "./logs",
    "log_level": "INFO",
    "excl_fpath": "/path/to/exclusions.h5",
    "regulations_fpath": "/path/to/blade_clearance_regulations.csv",
    "hub_height": 116,
    "rotor_diameter": 163,
    "replace": false,
    "hsds": false
}
```

#### Key input notes
- Blade clearance mode is local-only. ``regulations_fpath`` is required.
- You must provide both ``hub_height`` and ``rotor_diameter``.
- Blade clearance is computed as:
  ``hub_height - rotor_diameter / 2``
- Tip height is also used for percentage-based regulations:
  ``hub_height + rotor_diameter / 2``

### Local regulations format
Local regulations must include, at minimum:

- ``Feature Type``
- ``Value Type``
- ``Value``
- ``FIPS`` (required for non-geometric/tabular regulations)

For blade-clearance rows:

- ``Feature Type`` should resolve to ``Blade Clearance``
- ``Value Type`` must be one of:
  - ``Meters``
  - ``Percent``
  - ``Percent of Tower Height``
- ``Value`` should be numeric

``Value Type`` interpretation:

- ``Meters``: value is used directly as required minimum blade clearance (m)
- ``Percent`` and ``Percent of Tower Height``: converted to meters as
  ``tip_height * value / 100``

If your regulations are provided as a GeoPackage with valid geometries, county
mapping can be done spatially. If regulations are tabular, ``cnty_fips`` in
``excl_fpath`` is required for county matching.

### Execution
When ready, run blade clearance from the project directory:
```console
$ exclusions blade-clearance -c config_blade_clearance.json
```

If successful, output will include a GeoTIFF named:
``blade_clearance_restrictions_{blade_clearance}m.tif``

Output values are exclusion-style mask values:

- ``1`` means excluded
- ``0`` means included

Exclusion behavior is strict:

- a county is excluded when ``blade_clearance < local_minimum``
- if ``blade_clearance == local_minimum``, the county is not excluded

<br>

## Pipeline, batch, and status workflows
You can orchestrate blade-clearance runs using the generic exclusions CLI
workflow commands.

### Pipeline
From the project directory:
```console
$ exclusions pipeline
```

Repeat as needed to submit the next pending step or re-run incomplete steps.

### Batch
To execute multiple turbine/scenario combinations, prepare a batch CSV that
parameterizes blade-clearance inputs (for example ``hub_height``,
``rotor_diameter``, and ``regulations_fpath``), then run:
```console
$ exclusions batch -c config_batch.csv
```

### Job status
Check project job states with:
```console
$ exclusions status
```

To display specific input metadata in the status table:
```console
$ exclusions status -i node_file_path
```

<br>

## Common troubleshooting
- **Missing local regulations**
  - Provide a valid ``regulations_fpath``; this mode does not support
    generic-only operation.
- **Partial turbine inputs**
  - Provide both ``hub_height`` and ``rotor_diameter``.
- **No local regulations applied**
  - Confirm rows contain blade-clearance ``Feature Type`` values and valid
    county mapping fields.
- **Tabular regulations do not map to counties**
  - Ensure ``FIPS`` values are valid and ``excl_fpath`` contains
    ``cnty_fips``.
