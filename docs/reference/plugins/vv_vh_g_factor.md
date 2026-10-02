---
type: Plugin Reference
title: VV/VH G-Factor Calculator
description: Calculate detector G-factors using tail-matching on VV/VH format files.
resource: chisurf/plugins/vv_vh_g_factor/
tags: [reference, plugins, vv-vh-g-factor, spectroscopy, fluorescence-decay]
anchor: plugin-vv_vh_g_factor
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-vv_vh_g_factor)=
# VV/VH G-Factor Calculator

Calculate detector G-factors using tail-matching on VV/VH format files.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `vv_vh_g_factor` |
| Menu path | Spectroscopy → Fluorescence decay → **VV/VH G-Factor Calculator** |
| Categories | Spectroscopy, Fluorescence decay |
| Version | 1.0.0 |
| Surfaces | cli, emtk, gui, services |
| State namespace | `vv_vh_g_factor` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Native window (emtk)

The default window is drawn with emtk (`gui/app.py`, forms `gui/gfactor_emtk.view.json`).

| Area | Controls |
| --- | --- |
| Files | **Fast reference...**, **Slow protein...** (or drop files: first fast, second slow, the rest queue for the batch) |
| Channels, tail matching | *Flip VV/VH*, *Background correction*, *Tail start/stop (bin)*, *Background start/stop (bin)*, *VH shift (bins)*, *Manual G* + *G used*; the yellow and blue lines in the decay plot are draggable |
| Results | G table (raw, SD, corrected, SD, backgrounds) |
| Slow-reference mixing | *dt*, *rho*, *r0*, manual lifetime / target rS / l1 = l2, estimate table |
| Output | **Export calibration JSON...**, **Archive reference calibration** |
| Batch anisotropy tab | **Add files...**, **Run batch**, **Save table...**, **Clear batch**, results table (Delete removes a row) |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `vv_vh_g_factor.calculate` | no | Calculate G-factor based on tail matching for VV/VH decays. |
| `vv_vh_g_factor.perrin_steady_state` | no | Perrin steady-state anisotropy for a sphere. |
| `vv_vh_g_factor.solve_linked_l` | no | Solve for the linked l1=l2 mixing parameter. |
| `vv_vh_g_factor.archive_g_factor` | no | Register reference decay and archive G-factor calibration in MMFDB. |

## Theory and workflow

- **Theory** — [Time-resolved fluorescence anisotropy](/concepts/anisotropy.md)
- **Guide** — [The G-factor of a polarised setup](/guides/91_vv_vh_g_factor.md)
- **Workflow** — [Fluorescence lifetime and anisotropy decay fitting](/guides/10_lifetime_anisotropy_fitting.md)

## Source

- Plugin package: `chisurf/plugins/vv_vh_g_factor/`
- Manifest: {src}`chisurf/plugins/vv_vh_g_factor/manifest.json`
