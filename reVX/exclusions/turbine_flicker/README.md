# reVX Turbine Flicker
The ``reVX`` turbine flicker module computes shadow-flicker inclusion masks for wind siting workflows.
It can apply:

- a generic flicker threshold (hours/year),
- county-specific local regulations, or
- both simultaneously (local values where available and generic elsewhere).

This guide is supplemental to the generated CLI/API docs and follows the same project-directory workflow
used by other ``reVX`` exclusions tools.

<br>

## Computing turbine flicker exclusions
### Inputs and prerequisites
Before running turbine flicker, make sure you have:

1. A template exclusions HDF5 file (``excl_fpath``) that defines the output grid and contains:
   - a techmap layer (default ``techmap_wtk``), or permissions to create it automatically, and
   - a county FIPS layer (``cnty_fips``) if your local regulations file is tabular (CSV without geometry).
2. A wind resource HDF5 file (``res_fpath``) with hourly wind-direction data named
   ``winddirection_{hub_height}m``.
3. Building data referenced by ``building_layer``:
   - either a layer name in ``excl_fpath``
   - or a GeoTIFF path with the same shape/projection as ``excl_fpath``.
4. A Python environment with the flicker dependency installed:
   ```console
   $ pip install -e .[flicker]
   ```

### Config file setup
Each turbine flicker project should be run from its own directory.

Create a new directory, move into it, and generate template config files:
```console
$ exclusions template-configs
```

Then create or edit your turbine flicker config and include at least the required keys below:

```json
{
    "execution_control": {
        "option": "local"
    },
    "log_directory": "./logs",
    "log_level": "INFO",
    "excl_fpath": "/path/to/exclusions.h5",
    "res_fpath": "/path/to/wtk_resource.h5",
    "building_layer": "buildings",
    "hub_height": 116,
    "rotor_diameter": 163,
    "flicker_threshold": 30,
    "tm_dset": "techmap_wtk",
    "resolution": 128,
    "grid_cell_size": 90,
    "max_flicker_exclusion_range": "10x",
    "regulations_fpath": null,
    "building_threshold": 0,
    "out_layer": null,
    "replace": false,
    "hsds": false
}
```

#### Key input notes
- ``flicker_threshold`` is the generic max allowable flicker in hours/year.
- ``regulations_fpath`` may point to CSV or GeoPackage local regulations.
- If both are provided, local county values are used where available and ``flicker_threshold`` is used elsewhere.
- ``max_flicker_exclusion_range`` accepts either:
  - a numeric distance in meters (for example ``5000``), or
  - a rotor-diameter multiplier string (for example ``"10x"``).
- ``out_layer`` is optional. If provided, results are also written to ``excl_fpath`` in addition to GeoTIFF output.

### Local regulations format
Local regulations must include, at minimum:

- ``Feature Type``
- ``Value Type``
- ``Value``
- ``FIPS`` (required for non-geometric/tabular regulations)

For turbine flicker rows:

- ``Feature Type`` should resolve to ``Shadow Flicker``
- ``Value Type`` should resolve to ``Hrs/Year``
- ``Value`` should be the numeric allowable flicker threshold

If your regulations are provided as a GeoPackage with valid geometries, county mapping can be done spatially.
If regulations are tabular, ``cnty_fips`` in ``excl_fpath`` is required for county matching.

### Execution
When ready, run turbine flicker from the project directory:
```console
$ exclusions turbine-flicker -c config_turbine_flicker.json
```

If successful, output will include:

- a GeoTIFF named:
  ``flicker_{hub_height}hh_{rotor_diameter}rd.tif``
- optionally, an HDF5 layer in ``excl_fpath`` if ``out_layer`` is set

Output values are inclusion-style mask values:

- ``1`` means included
- ``0`` means excluded due to excessive shadow flicker

<br>

## Pipeline, batch, and status workflows
You can orchestrate turbine flicker runs using the generic exclusions CLI workflow commands.
As with other exclusions projects, this is typically done by driving job steps from a pipeline config.

### Pipeline
From the project directory:
```console
$ exclusions pipeline
```

Repeat as needed to submit the next pending step or re-run incomplete steps.

### Batch
To execute multiple turbine/scenario combinations, prepare a batch CSV that parameterizes turbine flicker
inputs (for example ``hub_height``, ``rotor_diameter``, ``flicker_threshold``, and regulation file path), then run:
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

## Advanced topics
### Generic-only vs local-only vs hybrid regulations
- Generic-only: set ``flicker_threshold`` and leave ``regulations_fpath`` as ``null``.
- Local-only: set ``regulations_fpath`` and set ``flicker_threshold`` to ``null``.
- Hybrid: provide both to use local rules where available with generic fallback elsewhere.

### Building data as an external GeoTIFF
If ``building_layer`` is a file path instead of an HDF5 layer name, ``reVX`` reads that GeoTIFF directly.
The GeoTIFF grid must match the exclusions grid shape and projection.

### Techmap behavior
If ``tm_dset`` is missing in ``excl_fpath``, turbine flicker will attempt to create it.
This requires valid exclusions/resource inputs and write access.

### Controlling memory/runtime
Larger values of ``max_flicker_exclusion_range`` increase memory and runtime.
Start with defaults (for example ``"10x"``) and increase only as needed.

<br>

## Common troubleshooting
- **Missing wind-direction dataset**
  - Ensure ``res_fpath`` contains ``winddirection_{hub_height}m``.
- **Layer shape mismatch**
  - Ensure ``building_layer`` (if GeoTIFF) exactly matches the exclusions grid.
- **Invalid max exclusion range**
  - Use a numeric value or an ``"Nx"`` string such as ``"10x"``.
- **No local regulations applied**
  - Confirm regulations rows have the expected ``Feature Type``/``Value Type`` values and valid county mapping data.
