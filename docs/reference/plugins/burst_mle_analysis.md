---
type: Plugin Reference
title: Burst MLE
description: Maximum likelihood lifetime analysis for single-molecule burst data.
resource: chisurf/plugins/burst/burst_mle_analysis/
tags: [reference, plugins, burst-mle-analysis, spectroscopy, single-molecule]
anchor: plugin-burst_mle_analysis
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-burst_mle_analysis)=
# Burst MLE

Maximum likelihood lifetime analysis for single-molecule burst data.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `burst_mle_analysis` |
| Menu path | Spectroscopy → Single-Molecule → **Burst MLE** |
| Categories | Spectroscopy, Single-Molecule |
| Version | 1.1.0 |
| Surfaces | emtk, gui, services |
| State namespace | `burst_mle_analysis` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Start value and fit window

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Tau start [ns] | `tau` | float |  | 0.01 … 100.0 | Starting value of the lifetime in ns (the wizard's Tau start). A change refits the current decay. |
| Window start [bin] | `micro_time_start` | int |  | 0 … 100000 | First micro-time bin of the fit window (after binning). Leave out the empty bins before the prompt. |
| Window stop [bin] | `micro_time_stop` | int |  | 1 … 100000 | Micro-time bin after the last bin of the fit window. Leave out the noisy tail. |

### Detector and window

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Detector | `current_detector` | choice |  | choices: `detector_names` | The detector (colour) whose decay is shown and fitted. Define detectors in the Detector setup tab. |
| Current file | `current_file` | int |  | 0 … 100000 | Index of the burst file whose decay is shown (0 is the first). |
| Binning | `binning` | choice |  | choices: `binning_options` | Micro-time binning factor: raw channels per bin. Too fine leaves bins empty, finer than the IRF resolves nothing. Auto picks one. |
| Min photons | `min_photons` | int |  | 2 … 100000 | A burst with fewer photons in the fit window is not fitted (its lifetime is left empty). |

### IRF

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| VH shift [bin] | `shift` | int |  | -9999 … 9999 | Integer shift of the perpendicular decay, IRF and background relative to the parallel one. |
| VV sub-bin shift | `shift_sp` | float |  | -100.0 … 100.0 | Fractional shift of the parallel IRF (interpolated). |
| VH sub-bin shift | `shift_ss` | float |  | -100.0 … 100.0 | Fractional shift of the perpendicular IRF (interpolated). |
| IRF start | `irf_start` | int |  | -1 … 999999 | First IRF bin kept; earlier bins are zeroed. -1 keeps all. |
| IRF stop | `irf_stop` | int |  | -1 … 999999 | Last IRF bin kept; later bins are zeroed. -1 keeps all. |
| VV threshold | `irf_threshold_vv` | float |  | 0.0 … 1.0 | IRF bins below this fraction of the parallel IRF maximum are zeroed (removes the noise floor). |
| VH threshold | `irf_threshold_vh` | float |  | 0.0 … 1.0 | IRF bins below this fraction of the perpendicular IRF maximum are zeroed. |
| 2I*: P+2S | `p2s_twoIstar` | bool |  |  | Use the P+2S form of the 2I* statistic. |
| BIFL scatter | `BIFL_scatter` | bool |  |  | Treat the scattered light as burst-integrated fluorescence lifetime scatter (soft). |

### H2MM states

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Split by H2MM state | `split_by_state` | bool |  |  | Fit each burst once more per H2MM state (Tau S0 (green) ... beside Tau (green)), after a fit of each state's decay pooled over the measurement, whose lifetime also starts the per-burst fits. Needs an H2MM run of this burst folder. |
| State min photons | `state_min_photons` | int |  | 1 … 100000 | A burst's state with fewer photons in the window is not fitted (its columns stay empty). |

### Burst

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Burst | `nav_burst` | int |  | 0 … 100000000 | Index of the burst shown in the inspected-burst plot (all bursts of all loaded files). |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `burst_mle.workflow.prepare` | no | Resolve MLE burst files and channel definitions from workflow context. |
| `burst_mle.contract.describe` | no | Return the Burst MLE workflow contract. |

## Theory and workflow

- **Workflow** — [Fluorescence lifetime from photon bursts](/guides/21_lifetime_from_bursts.md), [ns-ALEX / PIE: FRET, stoichiometry and lifetime together](/guides/32_nsalex_lifetime.md)

## Source

- Plugin package: `chisurf/plugins/burst/burst_mle_analysis/`
- Manifest: {src}`chisurf/plugins/burst/burst_mle_analysis/manifest.json`
- UI spec: {src}`chisurf/plugins/burst/burst_mle_analysis/gui/mle.view.json`
- UI spec: {src}`chisurf/plugins/burst/burst_mle_analysis/gui/mle_native.view.json`
