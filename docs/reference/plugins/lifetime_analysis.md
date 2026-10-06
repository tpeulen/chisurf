---
type: Plugin Reference
title: Decay Analysis
description: Integrated fluorescence lifetime analysis tools with IRF estimation, MaxEnt MEM, Lazy Lifetime Analysis, microtime histograms, VV/VH G-factor calibration, the VV/VH anisotropy decay, and a synthetic decay generator.
resource: chisurf/plugins/fluorescence_decay/lifetime_analysis/
tags: [reference, plugins, lifetime-analysis, spectroscopy, decay, fluorescence-decay]
anchor: plugin-lifetime_analysis
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-lifetime_analysis)=
# Decay Analysis

Integrated fluorescence lifetime analysis tools with IRF estimation, MaxEnt MEM, Lazy Lifetime Analysis, microtime histograms, VV/VH G-factor calibration, the VV/VH anisotropy decay, and a synthetic decay generator.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `lifetime_analysis` |
| Menu path | Spectroscopy → Decay → **Decay Analysis** |
| Categories | Spectroscopy, Decay, Fluorescence decay |
| Version | 1.0.0 |
| Surfaces | emtk, gui |
| State namespace | `lifetime_analysis` |

## Parameters

This plugin's window is an EMTK app: its controls and tables are described in the plugin's guide, and the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Theory** — [TCSPC: fluorescence-lifetime fitting](/concepts/tcspc_lifetime.md)
- **Workflow** — [Decay Analysis window, Lazy Lifetime Analysis and synthetic decays](/guides/76_decay_analysis_tools.md)

## Source

- Plugin package: `chisurf/plugins/fluorescence_decay/lifetime_analysis/`
- Manifest: {src}`chisurf/plugins/fluorescence_decay/lifetime_analysis/manifest.json`
