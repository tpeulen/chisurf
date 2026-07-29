(plugin-tttr_lut_tools)=
# LUT Tools

Compute TTTR microtime LUTs and create channel LUT settings in one dockable workspace.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `tttr_lut_tools` |
| Menu path | Tools → TTTR → **LUT Tools** |
| Categories | TTTR, Microtime, LUT |
| Version | 1.0.0 |
| Surfaces | cli, gui, services |
| State namespace | `tttr_lut_tools` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### General

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| files | `files` | path_list |  |  |  |
| Preview channel | `channel` | choice |  | choices: `channels_options` | Preview / tune THIS routing channel's histogram + region. ‘Add to Detector setup’ computes and assigns a LUT for ALL channels. |

### Parameters

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Linear start | `linear_start` | int |  | 0 … 1000000 | First bin of the flat linear region (or drag the orange region). |
| Linear stop | `linear_stop` | int |  | 1 … 1000000 | First bin after the flat linear region. |
| TAC channels required | `ntac_required` | int |  | 2 … 1000000 | Target number of corrected NTAC bins (defaults to the input bin count). |
| Noffset | `noffset` | int |  | 0 … 1000000 | Offset subtracted from corrected NTAC indices (or drag the red line). |
| preview photons | `preview_photons` | int |  | 1000 … 100000000 | How many photons to use for the corrected-preview histogram. |
| Normalize by region mean | `normalize` | bool |  |  | Divide the displayed histogram by the region mean (display only). |

### Advanced

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| RNG seed | `seed` | int |  | 0 … 2147483647 | Seed for the stochastic rebinning (reproducible previews). |
| Low-count threshold | `threshold` | float |  | 0.0 … 1000000000.0 | Bins at or below this count are zeroed before building the LUT (or drag the green line). |
| Mitigate wrap spike (floor + ε) | `mitigate_wrap` | bool |  |  | Use floor rounding + a small ε to avoid a spike at the wrap boundary. |
| ε (wrap) | `eps` | float |  | 0.0 … 0.01 | Epsilon used when 'Mitigate wrap spike' is on. |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `lut.autodetect_region` | no | Auto-detect the flat linear TAC region of a histogram. |
| `lut.compute` | no | Compute a TAC-linearization LUT from uniform-illumination TTTR files. |
| `lut.apply_preview` | no | Apply a LUT to one channel and return its corrected micro-time histogram. |
| `lut.settings_build` | no | Build a settings.tttr.json bundle from per-channel LUTs and shifts. |
| `lut.settings_load` | no | Load a settings.tttr.json bundle. |

## Source

- Plugin package: `chisurf/plugins/tttr/tttr_lut_tools/`
- Manifest: `chisurf/plugins/tttr/tttr_lut_tools/manifest.json`
- UI spec: `chisurf/plugins/tttr/tttr_lut_tools/gui/lut_compute.view.json`
