(plugin-clsm)=
# CLSM-Draw

Create CLSM-TTTR image representations, select pixels interactively, and export fluorescence-decay histograms.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `clsm` |
| Menu path | Imaging → **CLSM-Draw** |
| Categories | Imaging, Lifetime |
| Version | 2.0.0 |
| Surfaces | cli, gui, services |
| State namespace | `clsm_draw` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### File

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| File | `filename` | file |  |  | Load a TTTR CLSM file, or an imaging HDF5 (resolved to its source photon data via the stored back-reference); markers are auto-detected. |
| Setup | `setup_name` | choice |  | choices: `setup_names` | Acquisition-setup preset. |
| Channels | `channels_text` | str |  |  | Routing channels, comma separated (e.g. 0,1). |
| CLSM | `current_clsm_name` | choice |  | choices: `clsm_image_names` | CLSM images built for the selected channels (+ to create, − to remove). |
| Image | `current_representation_name` | choice |  | choices: `representation_names` | Image representations (+ to create from the current CLSM image). |

### Acquisition

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| TTTR type | `tttr_type` | str |  |  |  |
| Routine | `routine` | str |  |  |  |
| Frame markers | `frame_marker_text` | str |  |  | Frame marker numbers, comma separated. |
| Line start | `line_start_marker` | int |  |  |  |
| Line stop | `line_stop_marker` | int |  |  |  |
| Event marker | `event_type_marker` | int |  |  |  |
| Pixel/line | `pixel_per_line` | int |  |  | Pixels per line. 0 makes it equal to the number of lines. |

### Brush & Decay

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Brush size | `size` | int |  | 1 … 99 |  |
| Brush width | `width` | float |  | 0.1 … 50.0 |  |
| Brush | `mode` | choice |  | choices: select, deselect |  |
| Live update | `live_update` | bool |  |  | Recompute the decay while brushing. |
| Image type | `image_type` | choice |  | choices: Intensity, Mean micro time, Intensity, Mean micro time |  |
| Min #Ph | `n_ph_min` | int |  | 0 … | Minimum photons per pixel for the mean micro time. |
| Coarsen | `tac_coarsening` | choice |  | choices: 1, 2, 4, 8, 16 | Micro-time (TAC) binning factor. |
| Frames | `frame_mode` | choice |  | choices: sum, mean, frame |  |
| Frame | `frame_idx` | int |  | 0 … |  |

### General

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Regions | `regions` | region_list |  |  | Named regions. Tick to include, ~ to use everything outside one, and pick how the ticked ones combine into the selection the decay is built from. + keeps the current brush stroke. |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `clsm.setups.list` | no | List built-in CLSM acquisition-setup presets. |
| `clsm.image.info` | yes | Load a TTTR file, build a CLSM image and report its dimensions. |
| `clsm.image.representation` | yes | Compute an intensity / mean-micro-time image representation. |
| `clsm.decay.extract` | yes | Extract a decay histogram from a pixel selection. |
| `clsm.contract.describe` | no | Return the RPC contract descriptor. |

## Source

- Plugin package: `chisurf/plugins/microscopy/clsm/`
- Manifest: {src}`chisurf/plugins/microscopy/clsm/manifest.json`
- UI spec: {src}`chisurf/plugins/microscopy/clsm/gui/clsm.view.json`
