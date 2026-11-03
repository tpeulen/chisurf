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
| Menu path | not in the menus (opened from a hub or another tool); display name Spectroscopy → Single-Molecule → **Burst MLE** |
| Categories | Spectroscopy, Single-Molecule |
| Version | 1.1.0 |
| Surfaces | emtk, services |
| State namespace | `burst_mle_analysis` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Burst files

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Fit model | `fit_model` | choice |  | choices: `fit_model_choices` | Registered tttrlib lifetime estimator used by the preview and every detector's batch fit. Fit23 measures a single lifetime with anisotropy, Fit24 a bi-exponential decay, and Fit25 selects among four fixed candidate lifetimes. Each model retains its start values and fixed flags. |

### Detector and window

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Detector | `current_detector` | choice |  | choices: `detector_names` | The detector (colour) whose decay is shown and fitted. Define detectors in the Detector setup tab. |
| Current file | `current_file` | int |  | 0 … 100000 | Index of the burst file whose decay is shown (0 is the first). |
| Window start [bin] | `micro_time_start` | int |  | 0 … 100000 | First micro-time bin of the fit window, in bins of the setup's micro-time binning. Drag the green line or type it; until set, the window is the detector's gate. It may reach past the gate. |
| Window stop [bin] | `micro_time_stop` | int |  | 1 … 100000 | Micro-time bin after the last bin of the fit window. Leave out the noisy tail. Until set, the window is the detector's gate; it may reach past the gate. |
| Min photons | `min_photons` | int |  | 2 … 100000 | A burst with fewer photons in the fit window is not fitted (its lifetime is left empty). |

### Measured IRF and background

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| IRF model | `irf_model` | choice |  | choices: `irf_model_choices` | Shape of the IRF estimated from the non-burst photons, the last resort when there is neither a scatter (water, Ludox) nor a reference-dye (Rh110, Alexa647) measurement beside the data. Skewed Gaussian (default): a skew-normal fitted to the prompt, following the detector's slow edge without the fluorescent tail. Gaussian: symmetric. Experimental: the raw baseline-subtracted histogram, which still holds fluorescence. A measured IRF file replaces the estimate. |
| IRF: one for all | `irf_one_for_all` | bool |  |  | The IRF files serve every detector; each detector reads its own channels from them. Off: files are set for the selected detector only. |
| Background: one for all | `bg_one_for_all` | bool |  |  | The buffer files serve every detector; each detector reads its own channels from them. Off: files are set for the selected detector only. |
| Save VV/VHs | `save_vv_vhs` | bool |  |  | Write the VV and VH histogram of every IRF or background file beside it (&lt;file>_&lt;channels>.dat) when it is read. |

### IRF

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| VH shift [bin] | `shift` | int |  | -9999 … 9999 | Integer shift of the perpendicular decay, IRF and background relative to the parallel one. |
| VV sub-bin shift [bin] | `shift_sp` | float |  | -100.0 … 100.0 | Fractional shift of the parallel IRF (interpolated). |
| VH sub-bin shift [bin] | `shift_ss` | float |  | -100.0 … 100.0 | Fractional shift of the perpendicular IRF (interpolated). |
| IRF start [bin] | `irf_start` | int |  | -1 … 999999 | First IRF bin kept; earlier bins are zeroed. -1 keeps all. |
| IRF stop [bin] | `irf_stop` | int |  | -1 … 999999 | Last IRF bin kept; later bins are zeroed. -1 keeps all. |
| VV background level | `irf_threshold_vv` | float |  | 0.0 … 1.0 | The level, as a fraction of the parallel IRF's peak, at and below which it counts as background: it is taken off every bin of the IRF and what falls below zero is zero. |
| VH background level | `irf_threshold_vh` | float |  | 0.0 … 1.0 | The level, as a fraction of the perpendicular IRF's peak, at and below which it counts as background: it is taken off every bin of the IRF and what falls below zero is zero. |
| 2I*: P+2S | `p2s_twoIstar` | bool |  |  | Use the P+2S form of the 2I* statistic. |
| BIFL scatter | `BIFL_scatter` | bool |  |  | Treat the scattered light as burst-integrated fluorescence lifetime scatter (soft). |
| Opt iterations | `opt_iterations` | int |  | 5 … 999 | Number of fits the Opt button may spend searching the VH shift, sub-bin shifts, IRF window and IRF thresholds for the lowest 2I*. |

### H2MM states

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Split by H2MM state | `split_by_state` | bool |  |  | Fit each burst once more per H2MM state (Tau S0 (G\|G) ... beside Tau (G\|G)), after a fit of each state's decay pooled over the measurement, whose lifetime also starts the per-burst fits. Needs an H2MM run of this burst folder. |
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

- **Theory** — [TCSPC: fluorescence-lifetime fitting](/concepts/tcspc_lifetime.md)
- **Workflow** — [Fluorescence lifetime from photon bursts](/guides/21_lifetime_from_bursts.md), [ns-ALEX / PIE: FRET, stoichiometry and lifetime together](/guides/32_nsalex_lifetime.md)

## Source

- Plugin package: `chisurf/plugins/burst/burst_mle_analysis/`
- Manifest: {src}`chisurf/plugins/burst/burst_mle_analysis/manifest.json`
- UI spec: {src}`chisurf/plugins/burst/burst_mle_analysis/gui/mle_native.view.json`
