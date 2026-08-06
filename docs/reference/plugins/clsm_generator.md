(plugin-clsm_generator)=
# CLSM Generator

Generate a synthetic CLSM photon image from an intensity image + per-detector lifetime map(s).

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `clsm_generator` |
| Menu path | Imaging → Simulate → **CLSM Generator** |
| Categories | Imaging, Simulate |
| Version | 1.0.0 |
| Surfaces | gui |
| State namespace | `clsm_generator` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Inputs

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Intensity image | `sel_intensity` | file |  |  | Intensity image (TIFF or .npy/.npz); sets the per-pixel brightness. |
| Lifetime map(s) | `sel_lifetime_files` | path_list |  |  | One fluorescence-lifetime map (ns) per detector channel, matching the intensity-image shape. |

### Simulation

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Pixel size (µm) | `pixel_size` | float |  | 0.001 … 100.0 | Physical pixel size. |
| Dwell | `dwell` | float |  | 0.0001 … 100.0 | Per-pixel dwell time (simulator macro-time units). |
| Micro-time channels | `n_micro` | int |  | 8 … 65536 | Number of micro-time (TAC) channels. |
| Channel width (ns) | `dt` | float |  | 0.0001 … 10.0 | Micro-time channel width; the excitation period is n_micro × dt. |
| Brightness | `brightness_scale` | float |  | 1.0 … 1000000.0 | Peak per-pixel brightness (the brightest pixel). |
| IRF centre | `irf_center` | float |  | 0.0 … 100000.0 | Gaussian IRF centre (micro-time channels). |
| IRF σ | `irf_sigma` | float |  | 0.1 … 10000.0 | Gaussian IRF width (micro-time channels). |
| τ levels | `n_lifetime_levels` | int |  | 1 … 256 | Quantisation levels for the lifetime axis (more = finer, slower). |
| Intensity levels | `n_intensity_levels` | int |  | 1 … 256 | Quantisation levels for the intensity axis. |

## Theory and workflow

- **Theory** — [Simulating single-molecule photon streams](/concepts/photophysics_simulation.md)
- **Workflow** — [Confocal scan images (CLSM)](/guides/24_scan_images.md)

## Source

- Plugin package: `chisurf/plugins/microscopy/clsm_generator/`
- Manifest: {src}`chisurf/plugins/microscopy/clsm_generator/manifest.json`
- UI spec: {src}`chisurf/plugins/microscopy/clsm_generator/gui/generator.view.json`
