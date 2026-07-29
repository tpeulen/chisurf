(plugin-img_pixel_mle)=
# Pixel-wise MLE

Pixel-wise MLE lifetime analysis for TTTR imaging data.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `img_pixel_mle` |
| Menu path | Imaging → Lifetime → **Pixel-wise MLE** |
| Categories | Imaging, Lifetime |
| Version | 2.0.0 |
| Surfaces | cli, gui, services |
| State namespace | `img_pixel_mle` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Analysis

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| CLSM imaging files | `sel_files` | path_list |  |  | Confocal (CLSM) TTTR image file(s) to analyse. Drag-drop to add. |
| IRF file | `sel_irf_files` | path_list |  |  | IRF TTTR measurement (the first file is used). |
| Parallel channels (∥) | `channels_parallel_text` | str |  |  | Space-separated routing channels forming the parallel (VV) detection. |
| Perpendicular channels (⊥) | `channels_perpendicular_text` | str |  |  | Space-separated routing channels forming the perpendicular (VH) detection. |
| Fit start | `micro_time_start` | int |  | 0 … 1000000 | Fit-window start on the binned micro-time axis. |
| Fit stop | `micro_time_stop` | int |  | 1 … 1000000 | Fit-window stop on the binned micro-time axis. |
| Micro-time binning | `micro_time_binning` | int |  | 1 … 100000 | Integer down-binning of the micro-time axis before fitting. |
| Min photons | `min_photons` | int |  | 1 … 10000000 | Pixels with fewer photons in the fit window are not fitted. |
| Region | `roi_path` | file |  |  | Optional region confining the fit to part of the frame — regions saved in CLSM Draw (.json), a Cellpose segmentation (_seg.npy), a label image or a binary mask. Leave empty to fit the whole frame. |

### IRF preparation

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Threshold | `irf_threshold` | float |  | 0.0 … 1.0 | Fraction of the IRF maximum below which bins are zeroed. |
| Shift ∥ | `shift_sp` | float |  | -1000.0 … 1000.0 | Parallel-channel sub-bin IRF shift. |
| Shift ⊥ | `shift_ss` | float |  | -1000.0 … 1000.0 | Perpendicular-channel sub-bin IRF shift. |

### Fit flags

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| 2I* (P+2S) | `twoi_star` | bool |  |  | Optimise P+2S instead of P and S separately. |
| BIFL scatter | `bifl_scatter` | bool |  |  | Reduce Istar by the background contribution. |

### Background

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Subtract | `use_bg` | bool |  |  | Subtract a flat background from the fit window. |
| bg ∥ | `bg_p` | float |  | 0.0 … 1000000.0 | Parallel background counts spread over the fit window. |
| bg ⊥ | `bg_s` | float |  | 0.0 … 1000000.0 | Perpendicular background counts spread over the fit window. |

### Performance

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Engine | `engine` | choice |  | choices: auto, fast, loop | Histogram extraction: fast = vectorised C++, loop = exact bincount, auto = fast with bincount fallback on saturation. |
| Threads | `n_workers` | int |  | 0 … 256 | Fit worker threads. 0 = auto (cpu − 1); 1 = serial. |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `img_pixel_mle.analyze.run` | yes | Run pixel-wise MLE on TTTR imaging data. |
| `img_pixel_mle.contract.describe` | no | Return the RPC contract. |

## Source

- Plugin package: `chisurf/plugins/microscopy/img_pixel_mle/`
- Manifest: `chisurf/plugins/microscopy/img_pixel_mle/manifest.json`
- UI spec: `chisurf/plugins/microscopy/img_pixel_mle/gui/pixel_mle.view.json`
