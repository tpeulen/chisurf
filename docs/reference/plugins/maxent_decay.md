---
type: Plugin Reference
title: MaxEnt MEM
description: Maximum-entropy analysis of TCSPC decays (lifetime and FRET distance).
resource: chisurf/plugins/fluorescence_decay/maxent_decay/
tags: [reference, plugins, maxent-decay, spectroscopy, fluorescence-decay]
anchor: plugin-maxent_decay
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-maxent_decay)=
# MaxEnt MEM

Maximum-entropy analysis of TCSPC decays (lifetime and FRET distance).

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `maxent_decay` |
| Menu path | Spectroscopy → Fluorescence decay → **MaxEnt MEM** |
| Categories | Spectroscopy, Fluorescence decay |
| Version | 2.0.0 |
| Surfaces | cli, emtk, gui, services |
| State namespace | `maxent_decay` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Native window (emtk)

The default window is drawn with emtk (`gui/app.py`, forms `gui/maxent_emtk.view.json`).

| Area | Controls |
| --- | --- |
| Actions | **Run MEM**, **L-curve**, **Sample**, **Save**, **Cancel job** (Sample and Save need a result; FRET needs a donor spectrum) |
| Data | **Refresh** (session fits and datasets, **Fit**, **Use as decay**, **Use as IRF**), **Load decay**, **IRF file**, **Clear IRF**, **Prior**, **Donor**, **Donor from fit**, **JSON** preferences; file drops (decay, IRF, preferences) |
| MEM settings | *Mode*, *nu (reg)*, *MEM iterations*; *Lifetime grid* (tau min/max/points) or *Distance grid* (tau0, R0, R/R0 min/max, R points, donor-only fraction) |
| Periodic, instrument | *Periodic convolution* and *Period (ns)*; *timeshift*, *background*, *IRF background*, *lamp scatter*; *Fit nuisance* and the fix switches |
| L-curve span and sampling | decades below/above nu; Q-MCMC steps, thinning, walkers, chunk size, CPUs, vectorized |
| Plots | decay with fit, IRF and a draggable fit-range box; distribution (with sampling band); weighted residuals; L-curve (click a point to take its nu) |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `maxent_decay.jobs.run_lifetime_mem` | yes | Run MaxEnt lifetime MEM on arrays. |
| `maxent_decay.jobs.run_fret_mem` | yes | Run MaxEnt FRET distance MEM on arrays. |
| `maxent_decay.jobs.run_lcurve` | yes | Sweep regularization values and return L-curve data. |
| `maxent_decay.contract.describe` | no | Return the MaxEnt workflow contract. |

## Theory and workflow

- **Theory** — [Lifetime distributions and maximum entropy](/concepts/maximum_entropy.md), [TCSPC: fluorescence-lifetime fitting](/concepts/tcspc_lifetime.md)
- **Workflow** — [Maximum-entropy decay analysis](/guides/62_maxent_decay.md)

## Source

- Plugin package: `chisurf/plugins/fluorescence_decay/maxent_decay/`
- Manifest: {src}`chisurf/plugins/fluorescence_decay/maxent_decay/manifest.json`
