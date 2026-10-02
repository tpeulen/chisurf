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
| Surfaces | cli, emtk, gui |
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

## Native window (emtk)

The default window is drawn with emtk (`gui/app.py`, form `gui/anisotropy_emtk.view.json`); the AutoForm wizard above is the Qt fallback.

| Step | Controls |
| --- | --- |
| Data | four path fields with **Browse** and found/missing marks, *Two stacked VV/VH files*, *First column is time (ns)*, *Use file header*, *Bin width (ns)*, *Repetition rate (MHz)*, *Header rows*; file drops fill the next empty path |
| Normalize IRF | **Load / reload data**, **Export corrected IRFs**, *Background from* / *Background to*, IRF plot with a draggable background box (wheel zooms) |
| Corrections | *g-factor*, *l1*, *l2* |
| Components | lifetime and rotation tables (double-click to edit, Delete removes), *Amplitude* and time fields with **Add component** / **Remove selected**, **Save spectra**, **Load spectra** |
| Finish | **Create fits** (VV, VH and the linked global fit) |

## Theory and workflow

- **Theory** — [Time-resolved fluorescence anisotropy](/concepts/anisotropy.md)
- **Workflow** — [Fluorescence lifetime and anisotropy decay fitting](/guides/10_lifetime_anisotropy_fitting.md)

## Source

- Plugin package: `chisurf/plugins/fluorescence_decay/tr_anisotropy/`
- Manifest: {src}`chisurf/plugins/fluorescence_decay/tr_anisotropy/manifest.json`
- UI spec: {src}`chisurf/plugins/fluorescence_decay/tr_anisotropy/anisotropy.view.json`
