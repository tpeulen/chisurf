---
type: Plugin Reference
title: Lazy Lifetime Analysis
description: Lazy Lifetime Analysis for TCSPC fluorescence decay data.
resource: chisurf/plugins/fluorescence_decay/lltf/
tags: [reference, plugins, lltf, spectroscopy, fluorescence-decay]
anchor: plugin-lltf
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-lltf)=
# Lazy Lifetime Analysis

Lazy Lifetime Analysis for TCSPC fluorescence decay data.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `lltf` |
| Menu path | Spectroscopy → Fluorescence decay → **Lazy Lifetime Analysis** |
| Categories | Spectroscopy, Fluorescence decay |
| Version | 1.0.0 |
| Surfaces | cli, emtk |
| State namespace | `lltf` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Number of Lifetimes | `n_lifetimes` | int |  | 1 … 6 (step 1) | Exponential components of the fit. Used when Find Optimal is off; it then also switches the configuration file's own find_optimal off. |
| Find Optimal | `find_optimal` | bool |  |  | Find the optimal number of lifetimes: fit 1 … Max Lifetimes components and pick a count by the probability test. Read the χ²ᵣ sequence (Analysis Output, or optimal_fitting in the JSON) rather than taking the count as a verdict. |
| Max Lifetimes to Try | `max_lifetimes` | int |  | 2 … 6 (step 1) | Largest component count the search fits. |
| Probability Threshold | `prob_threshold` | float |  | 0.0 … 1.0 (step 0.01) | Probability a further component must reach to be kept. At the default 0.68 it needs about a 14 % drop in reduced χ², whatever the photon count. |
| Verbose Output | `verbose` | bool |  |  | Print the fitter's progress and diagnostics in Analysis Output. |

## Theory and workflow

- **Theory** — [TCSPC: fluorescence-lifetime fitting](/concepts/tcspc_lifetime.md)
- **Workflow** — [Decay Analysis window, Lazy Lifetime Analysis and synthetic decays](/guides/76_decay_analysis_tools.md)

## Source

- Plugin package: `chisurf/plugins/fluorescence_decay/lltf/`
- Manifest: {src}`chisurf/plugins/fluorescence_decay/lltf/manifest.json`
- UI spec: {src}`chisurf/plugins/fluorescence_decay/lltf/gui/lltf.view.json`
