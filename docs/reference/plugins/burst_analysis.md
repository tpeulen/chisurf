---
type: Plugin Reference
title: Burst Analysis
description: Integrated burst workflow with burst selection, BVA, burst MLE, burst browser, and background estimation.
resource: chisurf/plugins/burst/burst_analysis/
tags: [reference, plugins, burst-analysis, spectroscopy, single-molecule]
anchor: plugin-burst_analysis
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-burst_analysis)=
# Burst Analysis

Integrated burst workflow with burst selection, BVA, burst MLE, burst browser, and background estimation.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `burst_analysis` |
| Menu path | Spectroscopy → **Burst Analysis** |
| Categories | Spectroscopy, Single-Molecule |
| Version | 1.0.0 |
| Surfaces | gui |
| State namespace | `burst_analysis` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Theory** — [Simulating single-molecule photon streams](/concepts/photophysics_simulation.md)
- **Workflow** — [A complete µs-ALEX smFRET burst-analysis workflow](/guides/27_alex_smfret_workflow.md), [Working with timestamps and bursts (the data model)](/guides/33_timestamps_and_bursts.md), [Combining measurements / technical repeats](/guides/35_combining_repeats.md), [Accurate FRET: calibration](/guides/fret_calibration.md)

## Source

- Plugin package: `chisurf/plugins/burst/burst_analysis/`
- Manifest: {src}`chisurf/plugins/burst/burst_analysis/manifest.json`
