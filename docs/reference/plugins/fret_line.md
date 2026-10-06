---
type: Plugin Reference
title: FRET Line Generator
description: Compute static, dynamic, WLC, and mixture FRET lines for parameter ranges. Results are suitable for overlaying on smFRET 2D histograms in ndX.
resource: chisurf/plugins/fret_line/
tags: [reference, plugins, fret-line, spectroscopy, fret, analysis]
anchor: plugin-fret_line
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-fret_line)=
# FRET Line Generator

Compute static, dynamic, WLC, and mixture FRET lines for parameter ranges. Results are suitable for overlaying on smFRET 2D histograms in ndX.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `fret_line` |
| Menu path | Spectroscopy → FRET → **FRET Line Generator** |
| Categories | Spectroscopy, FRET, Analysis |
| Version | 1.0.0 |
| Surfaces | cli, emtk, gui, services |
| State namespace | `fret_line` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Components

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Model | `model_label` | choice |  | choices: `model_labels` | The model of the selected component. Choosing another replaces the component (its weight is kept, its parameters reset to the new model's defaults). |
| Weight | `weight` | float |  | 0.0 … 1000000.0 (step 0.1) | Mixing weight of the selected component (normalised across the components). |

### Sweep

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Filter | `sweep_filter` | str |  |  | Keep only the targets whose label contains this text (case-insensitive). |
| Vary | `sweep_label` | choice |  | choices: `sweep_labels` | The parameter or mixing fraction to vary: C<i> [model] name, or fraction of a component. |
| All parameters | `show_all_parameters` | bool |  |  | Also list the timing, IRF, background and anisotropy parameters and the donor-only fraction, which do not move a FRET line. |
| Min | `minimum` | float |  | -1000000000.0 … 1000000000.0 (step 1.0) | First value of the swept quantity. |
| Max | `maximum` | float |  | -1000000000.0 … 1000000000.0 (step 1.0) | Last value of the swept quantity. |
| log | `log_scale` | bool |  |  | Logarithmic spacing (both ends must be positive). |
| Points | `n_points` | int |  | 2 … 10000 (step 1) | Number of evaluated sweep points. |
| τ_D0 (ns) | `tau_d0` | float |  | 0.0 … 1000.0 (step 0.1) | Donor-only lifetime for E = 1 - τ_X/τ_D0. 0 takes it from the first FRET component. |

## Theory and workflow

- **Theory** — [Förster resonance energy transfer (FRET)](/concepts/fret.md)
- **Workflow** — [FRET lines: static, dynamic and model lines for the E–lifetime plot](/guides/82_fret_lines.md)

## Source

- Plugin package: `chisurf/plugins/fret_line/`
- Manifest: {src}`chisurf/plugins/fret_line/manifest.json`
- UI spec: {src}`chisurf/plugins/fret_line/gui/fret_line_emtk.view.json`
