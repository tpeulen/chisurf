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
| Surfaces | gui |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Audio

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Bin width | `bin_width` | float |  | 0.001 … 1.0 (step 0.01) | Macro-time bin width used to build the amplitude envelope. |
| Envelope | `env_mode` | choice |  | choices: linear, sqrt, log | Envelope compression applied to per-bin photon counts. |
| Sample rate | `sample_rate` | int |  | 8000 … 192000 (step 100) | Audio sample rate (Hz). |
| Master gain | `master_gain` | float |  | 0.0 … 2.0 (step 0.05) |  |
| Env floor | `env_floor` | float |  | 0.0 … 0.99 (step 0.05) |  |
| Env scale | `env_scale` | float |  | 0.1 … 10.0 (step 0.1) |  |
| Attack | `attack_frames` | int |  | 0 … 100 |  |
| Release | `release_frames` | int |  | 0 … 200 |  |

### Waterfall params

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Mode | `waterfall_mode` | choice |  | choices: microtime, lifetime | Show a micro-time histogram waterfall or an ILT lifetime waterfall. |

### Micro-time

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Bin width | `wf_bin_width` | float |  | 0.001 … 1.0 (step 0.01) |  |
| Micro bins | `wf_micro_bins` | int |  | 32 … 1024 |  |
| Log scale | `wf_log` | bool |  |  |  |

### Lifetime

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Bin width | `lt_bin_width` | float |  | 0.001 … 1.0 (step 0.01) |  |
| τ min | `lt_tau_min` | float |  | 0.1 … 100.0 |  |
| τ max | `lt_tau_max` | float |  | 0.1 … 100.0 |  |
| N τ points | `lt_n_tau` | int |  | 20 … 500 |  |
| Regularization | `lt_reg` | float |  | 1e-06 … 1.0 (step 0.001) |  |

## Source

- Plugin package: `chisurf/plugins/tttr/audifier/`
- Manifest: {src}`chisurf/plugins/tttr/audifier/manifest.json`
- UI spec: {src}`chisurf/plugins/tttr/audifier/gui/audifier.view.json`
