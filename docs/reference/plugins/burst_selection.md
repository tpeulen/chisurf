---
type: Plugin Reference
title: Burst Selection
description: Burst selection and FRET analysis for single-molecule fluorescence data.
resource: chisurf/plugins/burst/burst_selection/
tags: [reference, plugins, burst-selection, spectroscopy, single-molecule]
anchor: plugin-burst_selection
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-burst_selection)=
# Burst Selection

Burst selection and FRET analysis for single-molecule fluorescence data.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `burst_selection` |
| Menu path | Spectroscopy → Single-Molecule → **Burst Selection** |
| Categories | Spectroscopy, Single-Molecule |
| Version | 2.1.0 |
| Surfaces | cli, emtk, gui, services |
| State namespace | `burst_selection` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Display

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| All photons | `show_all_photons` | bool |  |  | Show the diagnostic layers computed from every photon in the range. |
| Selected photons | `show_selected_photons` | bool |  |  | Show the diagnostic layers computed from the photons the burst search kept. |
| First photon | `photon_first` | int |  | 0 … 99999999 | First photon index to process. 0 is the start of the file. Set by the visible-window slider above; type here for an exact range. |
| Last photon | `photon_last` | int |  | 0 … 99999999 | Last photon index to process. The default is the end of the file. Set by the visible-window slider above; type here for an exact range. |
| Window start | `window_start_s` | float |  | 0.0 … 100000.0 | Start of the visible window in the active file. The plots and the preview are computed for this slice only. |
| Window length | `window_length_s` | float |  | 0.0 … 100000.0 | Length of the visible window; 0 shows the whole file. |
| MCS bin width | `trace_bin_ms` | float |  | 0.05 … 9999.0 | Bin width of the count-rate trace. |
| Decay coarsening | `decay_bins` | int |  | 1 … 9999 | Micro-time channels summed per decay bin. |
| Burst bins | `burst_bins` | int |  | 3 … 999 | Bins of the burst-duration histogram. |

### Output

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Zip output | `zip_output` | bool |  |  | Zip the companion folder after the run (vendor files only; a .pto has no folder). |
| Remove folder | `remove_folder` | bool |  |  | Delete the unzipped companion folder once it is zipped. |
| MMFDB | `mmfdb_output` | bool |  |  | Also register the raw files and the burst selection in the MMFDB, linked to a sample. |
| Sample | `sample_id` | choice |  | choices: `sample_options` | The MMFDB sample the raw files belong to. From the raw files: use the sample they are already registered with. |

### Burst search

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Search | `algorithm_choice` | choice |  | choices: `algorithm_options` | The burst search, from tttrlib's registry. Changing it starts the parameters from that search's defaults. |

### Channel selection

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Detector | `detector` | choice |  | choices: `detector_options` | Search only the routing channels of this detector. All: every photon. |
| Micro-time window | `window` | choice |  | choices: `window_options` | Search only photons inside this PIE window. All: the full decay. |

### Macro time interval

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Use min dT | `dt_min_active` | bool |  |  | Drop photons that follow the previous one sooner than the minimum. |
| Min dT | `dt_min` | float |  | 0.0 … 1000.0 | Minimum inter-photon time in milliseconds (active when Use min dT is on). |
| Use max dT | `dt_max_active` | bool |  |  | Keep only photons that follow the previous one within the maximum: the burst photons. |
| Max dT | `dt_max` | float |  | 0.0 … 1000.0 | Maximum inter-photon time in milliseconds (active when Use max dT is on). It also names the output folder. |
| Fill gaps | `use_gap_fill` | bool |  |  | Merge selections separated by a few unselected photons. |
| Merge gap | `merge_gap` | int |  | 0 … 1000 | Largest run of unselected photons that is filled (when Fill gaps is on). |

### Filter

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Filter on | `filter_active` | bool |  |  | Apply the photon filter. Off: every photon goes to the search. |
| Invert | `invert` | bool |  |  | Invert the filter selection. |
| Min photons | `min_photons` | int |  | 2 … 1000000 | A burst with fewer photons is dropped after the search (every search). It names the output folder. |
| Count-rate photons | `photon_window` | int |  | 2 … 999 | Photons used to compute a count rate (recorded with the run). |

### Histogram

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Feature | `hist_feature` | choice |  | choices: `feature_options` | The burst-table column histogrammed (the proximity ratio is computed from the green and red photons). |
| Bins | `hist_bins` | int |  | 1 … 999 | Number of histogram bins. |
| Range from | `hist_min` | float |  | -9999.0 … 9999.0 | Lower histogram bound (a range with from >= to uses the data range). |
| Range to | `hist_max` | float |  | -9999.0 … 9999.0 | Upper histogram bound. |
| Log counts | `hist_log` | bool |  |  | Logarithmic count axis. |
| GMM components | `gmm_components` | int |  | 0 … 10 | Gaussians fitted by Fit GMM (0 with Auto components: chosen by BIC). |
| Auto components | `gmm_auto_components` | bool |  |  | With 0 components, choose the number by the Bayesian information criterion. |

### Scatter

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| X | `scatter_x` | choice |  | choices: `feature_options` | Feature on the horizontal axis. |
| Y | `scatter_y` | choice |  | choices: `feature_options` | Feature on the vertical axis. |

### GMM settings

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Covariance type | `covariance_type` | choice |  | choices: full, tied, diag, spherical | Covariance model of the mixture. |
| Random state | `random_state` | int |  | 0 … 1000000 | Seed of the initialisation (fixed for reproducible fits). |
| Max iterations | `max_iter` | int |  | 1 … 100000 | Expectation-maximisation iterations per start. |
| Starts | `n_init` | int |  | 1 … 1000 | Random starts; the best is kept. |
| Tolerance | `tol` | float |  | 1e-12 … 1.0 | Convergence threshold of the log-likelihood gain. |
| Max components | `max_components` | int |  | 1 … 50 | Largest number of components tried by Auto components. |
| Covariance regularisation | `reg_covar` | float |  | 0.0 … 1.0 | Added to the covariance diagonal for stability. |

### Metadata

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Key | `metadata_key` | choice |  | choices: `metadata_keys` | A metadata key (the common ones first, then the PDBx keys). |
| Value | `metadata_value` | str |  |  | Its value. |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `burst_selection.jobs.analyze_files` | yes | Run burst selection analysis over TTTR files. |
| `burst_selection.results.inspect_bur` | no | Inspect a saved ChiSurf .bur file. |
| `burst_selection.gmm.fit` | no | Fit a GMM to features extracted from a .bur file. |
| `burst_selection.diagnostics.load` | no | Run photon filtering and burst finding for diagnostic plots. |
| `burst_selection.contract.describe` | no | Return the Burst Selection workflow contract. |

## Theory and workflow

- **Workflow** — [Recurrence analysis of single particles (RASP)](/guides/02_recurrence_rasp.md), [Photon burst identification and the burst list](/guides/13_burst_identification.md), [Photon-by-photon hidden Markov models (H2MM)](/guides/19_h2mm_hidden_markov.md), [Binned photon traces (MCS)](/guides/22_binned_photon_traces.md), [2-D peak fitting](/guides/26_2d_peak_fitting.md), [Selecting and comparing FRET populations](/guides/28_selecting_fret_populations.md), [FRET-efficiency histogram fitting](/guides/29_fret_histogram_fitting.md), [Combining measurements / technical repeats](/guides/35_combining_repeats.md)

## Source

- Plugin package: `chisurf/plugins/burst/burst_selection/`
- Manifest: {src}`chisurf/plugins/burst/burst_selection/manifest.json`
- UI spec: {src}`chisurf/plugins/burst/burst_selection/gui/burst_display.view.json`
- UI spec: {src}`chisurf/plugins/burst/burst_selection/gui/native.view.json`
