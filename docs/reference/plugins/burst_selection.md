---
type: Plugin Reference
title: Burst Selection
description: Burst selection and FRET analysis for single-molecule fluorescence data.
resource: chisurf/plugins/burst/burst_selection/
tags: [reference, plugins, burst-selection, spectroscopy, single-molecule]
anchor: plugin-burst_selection
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-burst_selection)=
# Burst Selection

Burst selection and FRET analysis for single-molecule fluorescence data.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `burst_selection` |
| Menu path | Spectroscopy → Single-Molecule → **Burst Selection** |
| Categories | Spectroscopy, Single-Molecule |
| Version | 2.1.0 |
| Surfaces | cli, gui, services |
| State namespace | `burst_selection` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| All photons | `show_all_photons` | bool |  |  | Show the diagnostic layers computed from every photon in the range. |
| Selected photons | `show_selected_photons` | bool |  |  | Show the diagnostic layers computed from the photons the burst search kept. |
| First photon | `photon_first` | int |  | 0 … 99999999 | First photon index to process. 0 is the start of the file. Set by the visible-window slider above; type here for an exact range. |
| Last photon | `photon_last` | int |  | 0 … 99999999 | Last photon index to process. The default is the end of the file. Set by the visible-window slider above; type here for an exact range. |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `burst_selection.jobs.analyze_files` | yes | Run burst selection analysis over TTTR files. |
| `burst_selection.results.inspect_bur` | no | Inspect a saved ChiSurf .bur file. |
| `burst_selection.gmm.fit` | no | Fit a GMM to features extracted from a .bur file. |
| `burst_selection.diagnostics.load` | no | Run photon filtering and burst finding for diagnostic plots. |
| `burst_selection.contract.describe` | no | Return the Burst Selection workflow contract. |

## Theory and workflow

- **Workflow** — [Recurrence analysis of single particles (RASP)](/guides/02_recurrence_rasp.md), [Photon burst identification and the burst list](/guides/13_burst_identification.md), [2-D peak fitting](/guides/26_2d_peak_fitting.md), [Selecting and comparing FRET populations](/guides/28_selecting_fret_populations.md), [FRET-efficiency histogram fitting](/guides/29_fret_histogram_fitting.md)

## Source

- Plugin package: `chisurf/plugins/burst/burst_selection/`
- Manifest: {src}`chisurf/plugins/burst/burst_selection/manifest.json`
- UI spec: {src}`chisurf/plugins/burst/burst_selection/gui/burst_display.view.json`
