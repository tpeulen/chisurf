---
type: Plugin Reference
title: ebFRET
description: 'ebFRET, ported from its MATLAB GUI: empirical-Bayes hidden Markov analysis of binned donor/acceptor smFRET time series. The same window -- time series with the Viterbi path, the ensemble histograms and parameter distributions, series/crop/state controls -- the same menus (load/save session, raw/SF-Tracer/SMD import, photobleaching and outlier removal, priors, summary/trace/SMD export) and the same analysis loop, run on the backend. Ships a simulated four-state demo.'
resource: chisurf/plugins/burst/burst_ebfret/
tags: [reference, plugins, burst-ebfret, spectroscopy, single-molecule]
anchor: plugin-burst_ebfret
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-burst_ebfret)=
# ebFRET

ebFRET, ported from its MATLAB GUI: empirical-Bayes hidden Markov analysis of binned donor/acceptor smFRET time series. The same window -- time series with the Viterbi path, the ensemble histograms and parameter distributions, series/crop/state controls -- the same menus (load/save session, raw/SF-Tracer/SMD import, photobleaching and outlier removal, priors, summary/trace/SMD export) and the same analysis loop, run on the backend. Ships a simulated four-state demo.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `burst_ebfret` |
| Menu path | Spectroscopy → Single-Molecule → **ebFRET** |
| Categories | Spectroscopy, Single-Molecule |
| Version | 0.2.0 |
| Surfaces | cli, gui, services |
| State namespace | `burst_ebfret` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### General

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Signal Type | `signal_type` | choice |  | choices: Donor-Acceptor, FRET | Donor-Acceptor: compute the signal from two columns. FRET: take the signal from one column. |
| Donor | `donor` | choice |  | choices: `column_labels` | Column holding the donor intensity. |
| Acceptor | `acceptor` | choice |  | choices: `column_labels` | Column holding the acceptor intensity. |
| FRET | `fret` | choice |  | choices: `column_labels` | Column holding the FRET signal. |
| Clip at Minimum: | `clip_min` | float |  |  | Signal values below this are clipped to it before analysis. |
| Clip at Maximum: | `clip_max` | float |  |  | Signal values above this are clipped to it before analysis. |
| Exclude when number of Outliers exceeds: | `max_outliers` | int |  | 0 … | A series with more points outside the range than this is excluded. |
| Threshold | `method` | choice |  | choices: Manual, Auto | Manual: crop where a smoothed channel first falls below its threshold. Auto: detect the bleaching step in donor and acceptor. |
| Donor | `don` | bool |  |  | Crop where the donor intensity falls below the value. |
| don_value | `don_value` | float |  |  |  |
| Acceptor | `acc` | bool |  |  | Crop where the acceptor intensity falls below the value. |
| acc_value | `acc_value` | float |  |  |  |
| Don + Acc | `sum` | bool |  |  | Crop where donor plus acceptor falls below the value. |
| sum_value | `sum_value` | float |  |  |  |
| fret_value | `fret_value` | float |  |  |  |
| Padding | `pad` | bool |  |  | Frames removed before the detected point. |
| pad_value | `pad_value` | float |  |  |  |
| Viterbi State | `viterbi_state` | bool |  |  | Most likely state number per frame. |
| Viterbi Mean | `viterbi_mean` | bool |  |  | Center of the most likely state per frame. |

### Select Series

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| series_value | `series_value` | int |  | 0 … | The time series shown in the Time Series panel (ebFRET's IndexControl: edit box and slider). The slider's range is the number of loaded series. |

### Crop

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Min | `crop_min` | int |  | 1 … | First frame of the current series that enters the analysis. Changing the crop resets this series' result. |
| Max | `crop_max` | int |  | 1 … | Last frame of the current series that enters the analysis. Frames past it are drawn dashed. |
| Exclude | `exclude` | bool |  |  | Leave the current series out of the analysis entirely. |

### Select States

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| ensemble_value | `ensemble_value` | int |  | 1 … | The number of states whose model the Ensemble panel and the Viterbi overlay show. Its range is States Min to Max. |

### States

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Min | `min_states` | int |  | 1 … | Smallest number of states analysed. |
| Max | `max_states` | int |  | 1 … | Largest number of states analysed. |

### Analysis

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| States | `run_scope` | choice |  | choices: All, Current | All: analyse every number of states from Min to Max. Current: only the one selected in Select States. |
| Restarts | `restarts` | int |  | 0 … | Re-initialisations of each series' variational fit per iteration. 0 continues from the last result, 1 adds an uninformative start, more add random starts drawn from the prior. 2 suffices for most datasets. |
| Precision | `run_precision` | float |  | 0 … | Convergence threshold of the lower bound, relative. 1e-3 for exploring, 1e-6 for results you publish. |

### Number of States

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| states | `states` | choice |  | choices: `state_options` | Which model to export. |
| scope | `scope` | choice |  | choices: All, Current | All: set the priors of every number of states from Min to Max. Current: only the selected one. |

### Time Series Group

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| group | `group` | choice |  | choices: `group_options` | Export every series (all) or one group; for a group the prior is re-estimated from its series. |

### Expected Parameters

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Min Center | `mu_min` | float |  |  | Mean signal of the lowest state; the states' centers are spread evenly from Min to Max Center. |
| Max Center | `mu_max` | float |  |  | Mean signal of the highest state. |
| Noise | `sigma` | float |  | 0 … | Expected standard deviation of the signal around a state's center. |
| Dwell | `tau` | float |  | 0 … | Expected number of frames spent in a state before a transition. |

### Prior Strength

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Center | `count_mu` | float |  | 0 … | How many observations the center prior is worth. Low values let superfluous states stay empty. |
| Noise | `count_sigma` | float |  | 0 … | How many observations the noise prior is worth. |
| Dwell | `count_tau` | float |  | 0 … | How many observations the dwell-time prior is worth. |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `burst_ebfret.jobs.compute` | yes | Fit an empirical-Bayes Gaussian HMM over a set of binned FRET traces. |
| `burst_ebfret.session.open` | no | Open an ebFRET session (one main window). |
| `burst_ebfret.session.close` | no | Stop and release a session. |
| `burst_ebfret.session.status` | no | Revision, running flag, controls and messages. |
| `burst_ebfret.session.view` | no | Plot lines, limits and control values to draw. |
| `burst_ebfret.session.series_table` | no | Label, file, group, crop and exclusion of every series. |
| `burst_ebfret.session.load` | no | File > Load: session, raw .dat, SF-Tracer .tsv or SMD .mat/.json/.json.gz. |
| `burst_ebfret.session.smd_columns` | no | Column labels of SMD files, for Assign Channels. |
| `burst_ebfret.session.save` | no | File > Save the session .mat. |
| `burst_ebfret.session.set` | no | Set one control (series, crop, states, restarts, precision, view flags). |
| `burst_ebfret.session.run` | yes | Run the empirical-Bayes analysis on the backend. |
| `burst_ebfret.session.stop` | no | Stop the running analysis. |
| `burst_ebfret.session.reset` | no | Reset the analysis (All or Current). |
| `burst_ebfret.session.remove_bleaching` | no | Analysis > Remove Photo-bleaching. |
| `burst_ebfret.session.clip_outliers` | no | Analysis > Clip Outliers. |
| `burst_ebfret.session.update_priors` | no | Re-guess the priors (Auto). |
| `burst_ebfret.session.init_priors` | no | Analysis > Set Priors. |
| `burst_ebfret.session.export_summary` | no | File > Export > Analysis Summary (.csv). |
| `burst_ebfret.session.export_traces` | no | File > Export > Traces (.dat/.mat). |
| `burst_ebfret.session.export_smd` | no | File > Export > Single-molecule Dataset (.mat/.json/.json.gz). |

## Theory and workflow

- **Theory** — [ebFRET: variational-Bayes HMM of binned traces](/concepts/ebfret.md)
- **Workflow** — [Hidden Markov analysis of binned FRET traces (ebFRET)](/guides/20_ebfret_binned_hmm.md)

## Source

- Plugin package: `chisurf/plugins/burst/burst_ebfret/`
- Manifest: {src}`chisurf/plugins/burst/burst_ebfret/manifest.json`
- UI spec: {src}`chisurf/plugins/burst/burst_ebfret/gui/assign_smd_channels.view.json`
- UI spec: {src}`chisurf/plugins/burst/burst_ebfret/gui/clip_outliers.view.json`
- UI spec: {src}`chisurf/plugins/burst/burst_ebfret/gui/main.view.json`
- UI spec: {src}`chisurf/plugins/burst/burst_ebfret/gui/remove_bleaching.view.json`
- UI spec: {src}`chisurf/plugins/burst/burst_ebfret/gui/select_analysis.view.json`
- UI spec: {src}`chisurf/plugins/burst/burst_ebfret/gui/select_channels.view.json`
- UI spec: {src}`chisurf/plugins/burst/burst_ebfret/gui/set_priors.view.json`
