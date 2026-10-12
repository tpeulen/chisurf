---
type: Plugin Reference
title: Settings
description: Unified Settings for ChiSurf
resource: chisurf/plugins/core/setup/
tags: [reference, plugins, setup]
anchor: plugin-setup
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-setup)=
# Settings

Unified Settings for ChiSurf

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `setup` |
| Menu path | Setup → **Settings** |
| Categories | Setup |
| Version | 1.0.0 |
| Surfaces | emtk |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Output

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Folder | `output_path` | str |  |  | Standard folder for new measurements. Written to gui.acquisition.output_path on every change. |

### Advanced Configuration

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Chunk Size | `chunk_size` | int |  | 1000 … 65536 | Number of photons to read per chunk (each photon = 32 bits). |
| Real-time Sim | `real_time_sim` | bool |  |  | Pace simulation to roughly 1 s wall time = 1 s sim time. Only for the Simulation device. |

### Device Configuration

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Active Device Type | `device_type` | choice |  | choices: `device_types` | Which acquisition hardware (or the simulator) the Acquisition tool uses. |

### Acquisition

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Mode | `sim_excitation_mode` | choice |  | choices: CW, Pulsed | Excitation mode: CW (continuous) or Pulsed (pulsed laser; enables the micro-time / TCSPC axis). |
| Photons | `sim_N_ph_max` | int |  | 1 … 2000000000 | Total number of photons to simulate. |
| Photons/file | `sim_N_ph_per_file` | int |  | 1 … 2000000000 | Split the streamed SPC output into files of this many photons each. |
| Output folder | `sim_spc_output_path` | str |  |  | Folder where SPC/photon-stream files are written. |
| Diffusion seed | `sim_rmt1seed` | int |  | 0 … 2000000000 | Seed of the diffusion random number generator. |
| Emission seed | `sim_rmt2seed` | int |  | 0 … 2000000000 | Seed of the emission random number generator. |

### Geometry

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Box XY | `sim_box_xy` | float |  | 0.001 … 1000000.0 (step 0.1) | Lateral box size (um). |
| Box Z | `sim_box_z` | float |  | 0.001 … 1000000.0 (step 0.1) | Axial box size (um). |
| Focus w0 | `sim_focus_w0` | float |  | 0.001 … 1000000.0 (step 0.05) | Lateral focus waist (um). |
| Focus z0 | `sim_focus_z0` | float |  | 0.001 … 1000000.0 (step 0.05) | Axial focus extent (um). |
| Step | `sim_dt` | float |  | 1e-06 … 1000000.0 (step 0.001) | Simulation time step (ms). |

### Microtime

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| TAC channels | `sim_N_tac_channels` | int |  | 1 … 1000000 | Number of TAC (micro-time) channels. |
| TAC dt | `sim_tac_dt` | float |  | 1e-06 … 1000000.0 (step 0.0001) | Width of one TAC channel (ns). |
| Laser period | `sim_laser_period` | float |  | 1e-06 … 1000000.0 (step 0.1) | Laser repetition period (ns). |

### Performance

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Coasting | `sim_per_molecule_skip` | bool |  |  | Skip steps while a molecule is far from the focus. |
| Two-step field lookup | `sim_fast_grid_bbox` | bool |  |  | Look up the field in two steps (bounding box first). |
| Independent molecules | `sim_independent_molecules` | bool |  |  | Treat molecules as independent. |
| Analytic Gaussian focus | `sim_analytic_excitation` | bool |  |  | Use the analytic Gaussian excitation. |
| PSF / focus model | `sim_psf_type` | choice |  | choices: gaussian3d, analytic_gaussian3d, gaussian_lorentzian, radial | Point-spread function / focus model. |
| Rayleigh range zR (um) | `sim_psf_zR` | float |  | 0.0 … 1000000.0 (step 0.1) | Rayleigh range of the Gaussian-Lorentzian model. |
| PSF file (radial) | `sim_psf_file` | str |  |  | Measured radial PSF table (radial model only). |
| PSF r step (um) | `sim_psf_r_step` | float |  | 0.0 … 1000000.0 (step 0.01) | Radial step of the PSF table. |
| PSF z step (um) | `sim_psf_z_step` | float |  | 0.0 … 1000000.0 (step 0.01) | Axial step of the PSF table. |

### Interface

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Face | `ui_family` | choice |  | choices: `families` | Face of the interface text. monospace is the built-in face: the sharpest and fastest. Any installed family works; a proportional one lays out from its measured widths. |
| Size | `ui_size` | float |  | 6.0 … 24.0 (step 0.5) | Size of all interface text. Headings, captions and code follow it unless they have a size of their own. 8 pt is the shipped size. |
| Magnification | `zoom` | float |  | 0.5 … 3.0 (step 0.05) | Magnifies the whole window -- text, spacing, icons and plots together, as a browser zoom does. 1.00 is actual size; 1.25 suits a high-resolution screen viewed from a distance. |

### Editor and console

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Face | `code_family` | choice |  | choices: `mono_families` | Face of code. Only monospaced families are listed: the editor lines its columns up on a fixed character width. The code editor's own font setting, when changed there, takes precedence in that tool. |
| Size | `code_size` | float |  | 0.0 … 32.0 (step 0.5) | Size of code in points. Same as interface (0) follows the interface size. |

### Documentation

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Text face | `prose_family` | choice |  | choices: `families` | Face of running text and captions. prose picks Verdana, else DejaVu Sans: the proportional relatives of the built-in interface face. |
| Text size | `prose_size` | float |  | 0.0 … 32.0 (step 0.5) | Size of running text. Headings and captions are set relative to it. Same as interface (0) follows the interface size. The A− / A+ buttons of the Documentation dock zoom on top of it. |
| Heading face | `heading_family` | choice |  | choices: `families` | Face of headings. |
| Heading scale | `heading_step` | float |  | 1.0 … 1.6 (step 0.025) | Ratio between neighbouring heading levels: a fourth-level heading is the text size times this, a page title times its fourth power. 1.125 is the shipped scale; 1.0 sets headings at the text size. |
| Bold headings | `heading_bold` | bool |  |  | Set headings in the bold weight of their face. |
| Caption size | `caption_size` | float |  | 0.0 … 32.0 (step 0.5) | Size of figure captions and footnotes. One step below text (0) sets them one step of the heading scale below the text size. |

### Formulas

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Face | `math_family` | choice |  | choices: `math_families` | Text face of formulas; it needs an italic style. auto picks the first installed of STIX Two, Times New Roman and DejaVu Serif. Symbols the face lacks come from the installed mathematical faces. |
| Size | `math_size` | float |  | 0.0 … 32.0 (step 0.5) | Size of formulas. Same as text (0) follows the documentation text size. |

### Rendering

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Resolution | `oversample` | choice |  | choices: `oversample_choices` | Glyph raster scale. 1× draws one glyph pixel per screen pixel, placed on the pixel grid: the sharpest text. Higher values rasterise finer and scale down: smoother curves, slightly softer stems, more memory. |
| Smooth edges | `antialias` | bool |  |  | Grey-scale anti-aliasing of glyph edges. Off draws hard black-and-white edges, which some people read more easily at small sizes. Hinting cannot be chosen: the rasteriser does not offer it. |
| Fallback faces | `fallbacks` | str |  |  | Comma-separated faces tried, in order, for a character the chosen face does not have (CJK, mathematical symbols, subscripts), before the faces the system provides. A face may also be given a chain of its own: Inter, Verdana, prose. |

## Theory and workflow

- **Theory** — [The application shell: settings, interface, account, help and hubs](/concepts/application_shell.md)
- **Workflow** — [The Settings window: one list, every settings panel](/guides/97_settings_hub.md)

## Source

- Plugin package: `chisurf/plugins/core/setup/`
- Manifest: {src}`chisurf/plugins/core/setup/manifest.json`
- UI spec: {src}`chisurf/plugins/core/setup/gui/acq_settings_emtk.view.json`
- UI spec: {src}`chisurf/plugins/core/setup/gui/app.view.json`
- UI spec: {src}`chisurf/plugins/core/setup/gui/fonts.view.json`
