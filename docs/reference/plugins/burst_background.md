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

### Files

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| files | `files` | path_list |  |  |  |

### Fit

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Fit from (ms) | `fit_from_ms` | float |  | 0.001 … 1000.0 (step 0.01) | Lower edge of the background tail fit, in milliseconds. This is the judgement call in a background estimate: too small and bursts are fitted as background, so the rate comes out too high. Drag the shaded band in the Inter-photon time plot instead if you prefer — it is the same setting. |
| Fit to (ms) | `fit_to_ms` | float |  | 0.001 … 1000.0 (step 0.01) | Upper edge of the fit. The far tail is bins holding one count each: including it stretches the fit over a decade that carries almost no information and visibly pulls the line off the points. Set it where the points stop being dense. |
| Bin width (ms) | `binsize_ms` | float |  | 0.001 … 10.0 (step 0.01) | Inter-photon-time histogram bin width. Wider bins are smoother and coarser; the fitted rate should not depend on it. |
| Min. counts per bin | `min_counts` | int |  | 0 … 1000 (step 1) | Bins with fewer counts than this are left out of the tail fit, so the sparse far tail does not dominate it. |

## Theory and workflow

- **Theory** — [Single-molecule FRET: burst analysis (E, S, corrections)](/concepts/smfret_bursts.md)
- **Workflow** — [Background rates](/guides/15_background_rates.md)

## Source

- Plugin package: `chisurf/plugins/burst/burst_background/`
- Manifest: {src}`chisurf/plugins/burst/burst_background/manifest.json`
- UI spec: {src}`chisurf/plugins/burst/burst_background/gui/background.view.json`
