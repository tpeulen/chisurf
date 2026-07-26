(plugin-img_drift)=
# Drift Correction

Measure and remove inter-frame sample drift in TIFF stacks and photon-stream images. Photon streams are corrected photon by photon, so lifetimes and correlations stay valid.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `img_drift` |
| Menu path | Imaging → **Drift Correction** |
| Categories | Imaging |
| Version | 1.0.0 |
| Surfaces | cli, gui |
| State namespace | `img_drift` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Settings

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Image | `filename` | data_source |  |  | The stack to correct: a TIFF stack, or a photon-stream file (PTU/HT3/…) reconstructed into a confocal-scan image. Photon streams are corrected photon by photon, so the result stays usable for lifetime and correlation analysis. |
| Measure on | `channel` | choice |  | choices: `channel_names` | Channel the drift is measured on. The sample moves as a whole, so one channel drives the estimate and the correction is applied to all of them. Pick the brightest, most structured channel — a flat, empty channel gives a soft correlation peak and an unreliable shift. |
| Reference | `reference` | choice |  | choices: first, previous, mean | Which frame each frame is compared with. 'First frame' is right for slow monotonic drift and never accumulates error. 'Previous frame' follows non-monotonic wander but lets small per-frame errors add up over a long series. 'Stack mean' is a compromise for noisy data. |
| Apply by | `mode` | choice |  | choices: wrap, constant | Wrapping rolls the content that leaves one edge back in at the other, conserving every photon but making the wrapped strip meaningless. Blanking discards it and leaves the vacated strip empty — honest, but the edges then carry no signal. Wrapping matches the reference implementation. |

### Estimator

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Smoothing (σ px) | `smooth` | float |  | 0.0 … 20.0 | Gaussian blur applied to the correlation before the peak is located. Guards against a noise-driven tie between two neighbouring pixels flipping the answer by one pixel. Zero disables it. |
| Sub-pixel refinement | `subpixel` | bool |  |  | Refine each integer peak by fitting a parabola through its neighbours. Useful for slow drift measured over many frames; the correction itself is still applied in whole pixels. |

## Source

- Plugin package: `chisurf/plugins/microscopy/img_drift/`
- Manifest: `chisurf/plugins/microscopy/img_drift/manifest.json`
- UI spec: `chisurf/plugins/microscopy/img_drift/gui/drift.view.json`
