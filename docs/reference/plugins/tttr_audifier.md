---
type: Plugin Reference
title: Audifier
description: Convert TTTR photon streams to audio, with a live micro-time / lifetime waterfall preview.
resource: chisurf/plugins/tttr/audifier/
tags: [reference, plugins, tttr-audifier, tools, tttr, analysis]
anchor: plugin-tttr_audifier
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-tttr_audifier)=
# Audifier

Convert TTTR photon streams to audio, with a live micro-time / lifetime waterfall preview.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `tttr_audifier` |
| Menu path | Tools → TTTR → **Audifier** |
| Categories | Tools, TTTR, Analysis |
| Version | 2.0.0 |
| Surfaces | emtk, gui |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Audio

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Bin width | `bin_width` | float |  | 0.001 … 1.0 (step 0.01) | Macro-time bin width used to build the amplitude envelope. |
| Envelope | `env_mode` | choice |  | choices: linear, sqrt, log | Envelope compression applied to per-bin photon counts. |
| Sample rate | `sample_rate` | int |  | 8000 … 192000 (step 100) | Audio sample rate (Hz). |
| Master gain | `master_gain` | float |  | 0.0 … 2.0 (step 0.05) | Overall output gain of the rendered audio (0 to 2). |
| Env floor | `env_floor` | float |  | 0.0 … 0.99 (step 0.05) | Lowest envelope level; counts below it are silent (0 to 0.99). |
| Env scale | `env_scale` | float |  | 0.1 … 10.0 (step 0.1) | Multiplier applied to the envelope before it is compressed (0.1 to 10). |
| Attack | `attack_frames` | int |  | 0 … 100 | Frames over which a channel's envelope rises when photons start. |
| Release | `release_frames` | int |  | 0 … 200 | Frames over which a channel's envelope falls when photons stop. |

### Waterfall params

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Mode | `waterfall_mode` | choice |  | choices: microtime, lifetime | Show a micro-time histogram waterfall or an ILT lifetime waterfall. |

### Micro-time

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Bin width | `wf_bin_width` | float |  | 0.001 … 1.0 (step 0.01) | Macro-time bin width of the micro-time waterfall. |
| Micro bins | `wf_micro_bins` | int |  | 32 … 1024 | Number of micro-time bins of the waterfall. |
| Log scale | `wf_log` | bool |  |  | Show log(1+counts) instead of counts. |

### Lifetime

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Bin width | `lt_bin_width` | float |  | 0.001 … 1.0 (step 0.01) | Macro-time bin width of the lifetime waterfall. |
| τ min | `lt_tau_min` | float |  | 0.1 … 100.0 | Shortest lifetime of the lifetime grid. |
| τ max | `lt_tau_max` | float |  | 0.1 … 100.0 | Longest lifetime of the lifetime grid. |
| N τ points | `lt_n_tau` | int |  | 20 … 500 | Number of lifetimes of the grid. |
| Regularization | `lt_reg` | float |  | 1e-06 … 1.0 (step 0.001) | Regularization strength of the lifetime inversion. |

## Source

- Plugin package: `chisurf/plugins/tttr/audifier/`
- Manifest: {src}`chisurf/plugins/tttr/audifier/manifest.json`
- UI spec: {src}`chisurf/plugins/tttr/audifier/gui/audifier.view.json`
