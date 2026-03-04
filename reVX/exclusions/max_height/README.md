# Height Restriction Exclusions (local-only)

``reVX`` supports a jurisdiction-only ``height_restriction`` mode that
excludes entire jurisdictions if your system height exceeds the
region's allowed maximum height.

Use this mode when your regulations data encodes maximum allowed system
height per jurisdiction (i.e. per geometry).

## Required regulations format
For rows that should drive this calculation:
* ``Feature Type`` must be ``"maximum height"`` or ``"maximum turbine height"`` (case-insensitive and ignores dashes, underscores, and spaces)
* ``Value Type`` should be ``"meters"`` (case-insensitive)
* ``Value`` is the allowed maximum system height in meters

## Height input modes (exactly one required)
You must provide **exactly one** of the following:
* ``system_height`` (directly)
* Both ``hub_height`` and ``rotor_diameter`` (tip-height computed as ``hub_height + rotor_diameter / 2``)

Unlike normal setbacks, this mode is **local-only**, meaning the
``regulations_fpath`` input is required

## Minimal config example
```json
{
    "log_level": "INFO",
    "excl_fpath": "/path/to/Exclusions.h5",
    "regulations_fpath": "./height_regulations.csv",
    "system_height": 210,
}
```

Behavior is strict: a region is excluded only when
``system_height > local_max_height``.
