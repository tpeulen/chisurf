---
type: Plugin Reference
title: Intensity trace
description: Bin a TTTR photon stream into intensity traces per detector, histogram the counts per bin, and find discrete states with a hidden Markov model, with dwell-time histograms of each state.
resource: chisurf/plugins/tttr/intensity_trace/
tags: [reference, plugins, intensity-trace, spectroscopy, single-molecule]
anchor: plugin-intensity_trace
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-intensity_trace)=
# Intensity trace

Bin a TTTR photon stream into intensity traces per detector, histogram the counts per bin, and find discrete states with a hidden Markov model, with dwell-time histograms of each state.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `intensity_trace` |
| Menu path | Spectroscopy → Single-Molecule → **Intensity trace** |
| Categories | Spectroscopy, Single-Molecule |
| Version | 1.0.0 |
| Surfaces | emtk, script |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### General

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| File | `path` | str |  |  | The TTTR file being shown (load another with Load TTTR or drop one on the window). |
| Setup | `setup_name` | choice |  | choices: `setup_names` | The detector setup: which routing channels (and micro-time ranges) make each detector. 'Routing channels' bins every routing channel on its own. |
| Min Bin | `dwell_min` | float |  | 0.0 … 90000.0 | Shortest dwell time in the histograms. |
| Max Bin | `dwell_max` | float |  | 0.1 … 90000.0 | Longest dwell time in the histograms. |
| Number of Bins | `dwell_bins` | int |  | 10 … 200 | Number of bins of each dwell-time histogram. |
| Normalize Histogram | `dwell_normalize` | bool |  |  | Show each histogram as fractions of its dwells. |

### Time Window

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| ms | `window_ms` | float |  | 0.1 … 999.0 (step 0.5) | Width of one bin of the trace, in milliseconds; the file is binned again when it changes. |

### Histogram Settings

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Bins | `n_bins` | int |  | 10 … 500 | Number of bins of the count histograms beside the traces. |
| Min Counts | `hist_min` | float |  | 0.0 … 10000.0 | Lowest count per bin included in the histograms. |
| Max Counts | `hist_max` | float |  | 0.0 … 10000.0 | Highest count per bin included in the histograms. |

### HMM Settings

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| HMM Components | `n_states` | int |  | 1 … 15 | Number of hidden states of the model. |

## Theory and workflow

- **Theory** — [Intensity traces: counting photons in time bins](/concepts/intensity_traces.md)
- **Workflow** — [Intensity traces and file tools](/guides/74_intensity_traces_and_file_tools.md)

## Source

- Plugin package: `chisurf/plugins/tttr/intensity_trace/`
- Manifest: {src}`chisurf/plugins/tttr/intensity_trace/manifest.json`
- UI spec: {src}`chisurf/plugins/tttr/intensity_trace/gui/intensity_trace.view.json`
