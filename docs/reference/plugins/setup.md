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
| Surfaces | emtk, gui |

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

## Source

- Plugin package: `chisurf/plugins/core/setup/`
- Manifest: {src}`chisurf/plugins/core/setup/manifest.json`
- UI spec: {src}`chisurf/plugins/core/setup/gui/acq_settings_emtk.view.json`
