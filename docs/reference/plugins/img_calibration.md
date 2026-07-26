(plugin-img_calibration)=
# IRF & BG

Per-detector IRF file and background (kHz) calibration; transferred to phasor and pixel-wise MLE. Optional (skippable) pipeline step.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `img_calibration` |
| Menu path | Imaging → **IRF & BG** |
| Categories | Imaging |
| Version | 1.0.0 |
| Surfaces | gui |
| State namespace | `img_calibration` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Detector | `display_detector` | choice |  | choices: `window_names` | Detector to calibrate (settings are per detector). |
| IRF files (this detector) | `sel_irf_files` | path_list |  |  | IRF TTTR file(s) for this detector (summed); carried to Phasor + pixel-wise MLE. Drag-drop to add. |
| Conv start | `sel_conv_start` | int |  | 0 … 1000000 | Convolution/fit window start (micro-time channel). Drag the blue region. |
| Conv stop | `sel_conv_stop` | int |  | 0 … 1000000 | Convolution/fit window stop (micro-time channel). Drag the blue region. |
| IRF start | `sel_irf_start` | int |  | 0 … 1000000 | IRF window start (separate from the conv window). Drag the green region. |
| IRF stop | `sel_irf_stop` | int |  | 0 … 1000000 | IRF window stop (separate from the conv window). Drag the green region. |
| Background VV (∥) | `sel_bg_vv` | float |  | 0.0 … 1000000.0 | Parallel-channel background subtracted from the VV IRF (0 = auto baseline). |
| Background VH (⊥) | `sel_bg_vh` | float |  | 0.0 … 1000000.0 | Perpendicular-channel background subtracted from the VH IRF (0 = auto baseline). |
| Shift VV (∥, ch) | `sel_shift_vv` | float |  | -100000.0 … 100000.0 (step 1.0) | Circular (wrap-around) shift of the VV IRF, in micro-time channels. |
| Shift VH (⊥, ch) | `sel_shift_vh` | float |  | -100000.0 … 100000.0 (step 1.0) | Circular (wrap-around) shift of the VH IRF, in micro-time channels. |

## Source

- Plugin package: `chisurf/plugins/microscopy/img_calibration/`
- Manifest: `chisurf/plugins/microscopy/img_calibration/manifest.json`
- UI spec: `chisurf/plugins/microscopy/img_calibration/gui/calibration.view.json`
