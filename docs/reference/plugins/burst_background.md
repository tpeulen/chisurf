---
type: Plugin Reference
title: Burst Background Estimation
description: Estimate detector background rates from TTTR burst data.
resource: chisurf/plugins/burst/burst_background/
tags: [reference, plugins, burst-background, spectroscopy, single-molecule]
anchor: plugin-burst_background
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-burst_background)=
# Burst Background Estimation

Estimate detector background rates from TTTR burst data.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `burst_background` |
| Menu path | Spectroscopy → Single-Molecule → **Burst Background Estimation** |
| Categories | Spectroscopy, Single-Molecule |
| Version | 1.0.0 |
| Surfaces | cli, gui |
| State namespace | `burst_background` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| files | `files` | path_list |  |  |  |

## Theory and workflow

- **Theory** — [Single-molecule FRET: burst analysis (E, S, corrections)](/concepts/smfret_bursts.md)
- **Workflow** — [Background rates](/guides/15_background_rates.md)

## Source

- Plugin package: `chisurf/plugins/burst/burst_background/`
- Manifest: {src}`chisurf/plugins/burst/burst_background/manifest.json`
- UI spec: {src}`chisurf/plugins/burst/burst_background/gui/background.view.json`
