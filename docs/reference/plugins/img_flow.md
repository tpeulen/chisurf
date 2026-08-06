---
type: Plugin Reference
title: Flow Maps
description: 'Map the velocity field of a sample from its own correlations — one arrow per tile, over the image. No model and no fit: the velocity is read off where a correlation peak is. Ships a simulated demo whose flow profile is known, so the arrows can be checked.'
resource: chisurf/plugins/microscopy/img_flow/
tags: [reference, plugins, img-flow, imaging]
anchor: plugin-img_flow
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-img_flow)=
# Flow Maps

Map the velocity field of a sample from its own correlations — one arrow per tile, over the image. No model and no fit: the velocity is read off where a correlation peak is. Ships a simulated demo whose flow profile is known, so the arrows can be checked.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `img_flow` |
| Menu path | Imaging → **Flow Maps** |
| Categories | Imaging |
| Version | 1.0.0 |
| Surfaces | cli, gui, services |
| State namespace | `img_flow` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Settings

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Image | `filename` | data_source |  |  | The acquisition to map: a TIFF stack, or a photon stream (PTU/HT3/…) reconstructed into a confocal scan. It needs at least three frames — a flow map measures what moved *between* frames, so a single image carries no velocity at all. If you have never run one, press ▶ Load demo in the toolbar: it simulates a scan whose flow profile is known, so the arrows can be checked against a number. |
| Channel | `channel` | choice |  | choices: `channel_names` | Image channel to map. Pick the one whose molecules are moving; a structural channel that never changes has no correlation peak to track. |
| Estimator | `method` | choice |  | choices: stics, pcf | How a velocity is read. STICS tracks how far the correlation peak travels between frame lags: two-dimensional and direct, but blind to a flow too slow to shift the peak at all. Pair correlation asks *when* molecules arrive a distance away: one-dimensional along the fast scan axis, resolved per pixel, and the only one that can report no transport rather than slow transport — which is what a barrier looks like. Neither fits a transport model, so there is nothing to initialise. |
| Tile [px] | `tile` | int |  | 4 … 512 | Side of the sub-region each arrow is computed from — the spatial resolution of the map, and the setting that decides the whole result. Smaller localizes the flow but holds fewer molecules and leaves the peak less room to travel; larger averages distinct flows into one arrow. Several focus waists across is the usual compromise. |
| Frame lags | `n_lags` | int |  | 2 … 64 | STICS only: correlate frame i against frames i+0 … i+N-1. The peak has to stay inside its tile over that whole range — its displacement is v × lag × frame time ÷ pixel size. Overshoot and the correlation map, being periodic, wraps the peak round to the other side, where a straight line fits a confident velocity pointing the wrong way; such tiles are refused and counted rather than reported. |
| Pair distance [px] | `distance` | int |  | 1 … 128 | Pair correlation only: how far apart the two correlated points are. Too small and the transit time falls below the line period; too large and molecules do not survive the trip, so the peak drowns. Run two distances and check the scaling: a flow peak moves as δ, a diffusive one as δ². |
| Min. quality | `min_quality` | float |  | 0.0 … 1.0 | Arrows below this are not drawn. It is not cosmetic: peak jitter fitted to a straight line always yields a slope, and a slope is a speed, so an unfiltered map paints a convincing flow field onto a sample that has none. Raise it until a region you know is static goes blank. |

### Scanner

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Pixel dwell [µs] | `pixel_duration_us` | float |  | 0.001 … 1000000.0 | Time the beam spends on each pixel. With the line and frame times left at zero they are derived from it, which is exact for a scanner without dead time between lines or frames. |
| Frame time [ms] | `frame_duration_ms` | float |  | 0.0 … 1000000.0 | Time between one frame and the next. This is the clock a STICS velocity is measured against, so an inter-frame dead time that is not accounted for scales every arrow. Zero derives it from the dwell. |
| Line time [ms] | `line_duration_ms` | float |  | 0.0 … 1000000.0 | Time between one line and the next; the clock the pair-correlation lags are measured against. Zero derives it from the dwell. |
| Pixel size [nm] | `pixel_size_nm` | float |  | 0.01 … 100000.0 | Physical pixel size. Every velocity scales linearly with it, so an uncertain pixel size is an equally uncertain µm/s. |

### Display and estimator

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Arrow scale | `arrow_scale` | float |  | 0.05 … 50.0 | Multiplies the drawn arrow length. Display only — it never touches the numbers, and the caption under the field says what scale was used. |
| Tile step [px] | `step` | int |  | 0 … 512 | Distance between neighbouring tile origins. Zero uses half a tile, so tiles overlap — which smooths the field without adding information. Set it equal to the tile size for independent tiles. |
| Background | `subtract_average` | choice |  | choices: frame, stack | 'Each frame's own mean' removes the offset. 'Also the time-average' additionally removes whatever never moves — the immobile fraction — which otherwise adds a correlation peak fixed at zero lag and drags every velocity towards zero. On a sample with genuinely stuck material the difference is large. |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `img_flow.map.compute` | yes | Map the velocity field of an image stack or photon stream. |
| `img_flow.methods.list` | no | List the estimators and what each of them can and cannot see. |
| `img_flow.demo.create` | yes | Simulate a photon stream with a known flow profile and write it as PTU. |
| `img_flow.contract.describe` | no | Return the RPC contract descriptor. |

## Theory and workflow

- **Theory** — [Image correlation: RICS, STICS, TICS and iMSD are one method](/concepts/image_correlation.md), [Pair correlation and flow maps: where molecules go](/concepts/pair_correlation.md)
- **Workflow** — [Pair correlation and flow maps: measuring where molecules go](/guides/55_pair_correlation.md)

## Source

- Plugin package: `chisurf/plugins/microscopy/img_flow/`
- Manifest: {src}`chisurf/plugins/microscopy/img_flow/manifest.json`
- UI spec: {src}`chisurf/plugins/microscopy/img_flow/gui/flow.view.json`
