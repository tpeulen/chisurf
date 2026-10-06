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

### General

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| IRF VV | `irf_vv_path` | file |  |  | Vertical-excitation, vertical-emission IRF file. |
| IRF VH | `irf_vh_path` | file |  |  | Vertical-excitation, horizontal-emission IRF file. |
| Data VV | `data_vv_path` | file |  |  | Vertical-excitation, vertical-emission sample decay. |
| Data VH | `data_vh_path` | file |  |  | Vertical-excitation, horizontal-emission sample decay. |
| g-factor | `g_factor` | float |  |  | Detection-efficiency ratio between the VV and VH channels. |
| l1 | `l1` | float |  |  | Channel-mixing correction factor l1. |
| l2 | `l2` | float |  |  | Channel-mixing correction factor l2. |

### Reader settings

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Two stacked VV/VH files | `stacked_files` | bool |  |  | Each IRF/data file holds both polarization channels (one IRF file, one data file); otherwise choose four separate files. |
| First column is time (ns) | `first_column_is_time` | bool |  |  | Keep a measured time axis unchanged; otherwise the first column is treated as channel indices. Not used with stacked files. |
| Use file header | `use_header` | bool |  |  | Read available channel/calibration information from the file header. |
| Bin width (ns) | `bin_width` | float |  | 1e-06 … 100.0 (step 0.01) | Time per histogram channel for channel-index or stacked files; a time-axis column is preserved. |
| Repetition rate (MHz) | `rep_rate` | float |  | 0.001 … 10000.0 (step 1.0) | Excitation repetition rate used to initialize the lifetime fits. |
| Header rows | `skiprows` | int |  | 0 … 100000 (step 1) | Number of header rows to skip while reading text decays. |

### Background region

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Background from | `region_lb` | int |  | 0 … 1000000 (step 1) | First background channel, inclusive; choose a signal-free region. |
| Background to | `region_ub` | int |  | 0 … 1000000 (step 1) | Last background channel boundary, exclusive. |

### Lifetime spectrum

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Amplitude | `new_amplitude` | float |  | 0.0 … 1000000.0 (step 0.1) | Amplitude of the component to add. |
| Lifetime (ns) | `new_value` | float |  | 0.001 … 1000000.0 (step 0.1) | Lifetime of the component to add, in nanoseconds. |

## Theory and workflow

- **Theory** — [Time-resolved fluorescence anisotropy](/concepts/anisotropy.md)
- **Workflow** — [Fluorescence lifetime and anisotropy decay fitting](/guides/10_lifetime_anisotropy_fitting.md)

## Source

- Plugin package: `chisurf/plugins/fluorescence_decay/tr_anisotropy/`
- Manifest: {src}`chisurf/plugins/fluorescence_decay/tr_anisotropy/manifest.json`
- UI spec: {src}`chisurf/plugins/fluorescence_decay/tr_anisotropy/anisotropy.view.json`
- UI spec: {src}`chisurf/plugins/fluorescence_decay/tr_anisotropy/gui/anisotropy_emtk.view.json`
