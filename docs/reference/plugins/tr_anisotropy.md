---
type: Plugin Reference
title: Anisotropy-Wizard
description: 'Guided setup of a linked VV/VH global time-resolved anisotropy fit: load polarised decays, background-correct the IRFs, set instrument corrections and define lifetime/rotation spectra.'
resource: chisurf/plugins/fluorescence_decay/tr_anisotropy/
tags: [reference, plugins, tr-anisotropy, spectroscopy, fluorescence-decay]
anchor: plugin-tr_anisotropy
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-tr_anisotropy)=
# Anisotropy-Wizard

Guided setup of a linked VV/VH global time-resolved anisotropy fit: load polarised decays, background-correct the IRFs, set instrument corrections and define lifetime/rotation spectra.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `tr_anisotropy` |
| Menu path | Spectroscopy → Fluorescence decay → **Anisotropy-Wizard** |
| Categories | Spectroscopy, Fluorescence decay |
| Version | 1.0.0 |
| Surfaces | cli, gui |
| State namespace | `tr_anisotropy` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| IRF VV | `irf_vv_path` | file |  |  | Vertical-excitation, vertical-emission IRF file. |
| IRF VH | `irf_vh_path` | file |  |  | Vertical-excitation, horizontal-emission IRF file. |
| Data VV | `data_vv_path` | file |  |  | Vertical-excitation, vertical-emission sample decay. |
| Data VH | `data_vh_path` | file |  |  | Vertical-excitation, horizontal-emission sample decay. |
| g-factor | `g_factor` | float |  |  | Detection-efficiency ratio between the VV and VH channels. |
| l1 | `l1` | float |  |  | Channel-mixing correction factor l1. |
| l2 | `l2` | float |  |  | Channel-mixing correction factor l2. |

## Theory and workflow

- **Theory** — [Time-resolved fluorescence anisotropy](/concepts/anisotropy.md)
- **Workflow** — [Fluorescence lifetime and anisotropy decay fitting](/guides/10_lifetime_anisotropy_fitting.md)

## Source

- Plugin package: `chisurf/plugins/fluorescence_decay/tr_anisotropy/`
- Manifest: {src}`chisurf/plugins/fluorescence_decay/tr_anisotropy/manifest.json`
- UI spec: {src}`chisurf/plugins/fluorescence_decay/tr_anisotropy/anisotropy.view.json`
