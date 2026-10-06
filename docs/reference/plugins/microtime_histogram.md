---
type: Plugin Reference
title: Histogram-Microtime
description: Create and inspect TTTR microtime histograms.
resource: chisurf/plugins/tttr/microtime_histogram/
tags: [reference, plugins, microtime-histogram, spectroscopy, fluorescence-decay, tttr]
anchor: plugin-microtime_histogram
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-microtime_histogram)=
# Histogram-Microtime

Create and inspect TTTR microtime histograms.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `microtime_histogram` |
| Menu path | Spectroscopy → Fluorescence decay → **Histogram-Microtime** |
| Categories | Spectroscopy, Fluorescence decay, TTTR |
| Version | 1.0.0 |
| Surfaces | cli, emtk, gui |
| State namespace | `microtime_histogram` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Run

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Autosave after compute | `auto_save` | bool |  |  | Write the cumulative decay to Output once the computation succeeds. |

### Detector and channels

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Detector | `detector` | choice |  | choices: `detector_options` | Detector of the setup whose interleaved routing channels (parallel, perpendicular, parallel, ...) and G-factor are used. |
| Parallel | `parallel_text` | text |  |  | Comma-separated routing channels of the parallel (VV) stream; choosing a detector fills them. |
| Perpendicular | `perpendicular_text` | text |  |  | Comma-separated routing channels of the perpendicular (VH) stream; empty when polarization resolution is off. |
| Polarization resolved | `polarized` | bool |  |  | Split the detector channels into alternating VV/VH routes; unchecked gives one unpolarized stream. |

### Reading and gates

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Excitation window | `window` | choice |  | choices: `window_options` | Apply this inclusive excitation micro-time gate, or include all windows. |
| TTTR format | `filetype` | choice |  | choices: `format_options` | Container reader override; Auto uses the file header (headerless SPC data needs its subtype). |
| Binning | `binning` | choice |  | choices: 1, 2, 4, 8, 16, 32 | Group this many adjacent micro-time bins. |
| Inter-photon filter | `gap_filter` | bool |  |  | Keep only photons whose next selected photon follows within the gap below: the photons of bursts. With Invert, keep the isolated photons between them instead: a background decay from the same measurement. |
| Max gap [ticks] | `gap_ticks` | int |  | 1 … | Largest gap to the next selected photon, in macro-time ticks (200000 ticks is 2.7 ms at a 13.5 ns clock). |
| Invert (isolated photons) | `gap_invert` | bool |  |  | Keep the photons whose next selected photon is at least the gap away: the background between bursts. |

### Time step, G-factor and shifts

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| dt [ns] | `dt_ns` | float |  | 0.0 … | Nanoseconds per binned TAC channel; reading derives it from the header. Typing a value keeps it (Manual time step). |
| Manual time step | `dt_manual` | bool |  |  | Keep the entered time step instead of the file header's resolution. |
| G-Factor | `g_factor` | float |  | 0.0 … | Weights VH by 2G in the combined VV + 2G VH trace. |
| VV shift (channels) | `vv_shift` | int |  |  | Pad or clip the VV histogram by this many bins; photon times are not wrapped. |
| VH shift (channels) | `vh_shift` | int |  |  | Pad or clip the VH histogram by this many bins; photon times are not wrapped. |

### Output

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Output | `output` | text |  |  | Single-column export: VV bins followed by VH bins, compatible with read_vv_vh. |
| Polarization | `polarization` | choice |  | choices: vm, vv, vh | TCSPC reader polarization mode used when the saved decay is transferred. |

## Theory and workflow

- **Theory** — [Micro-time histograms: the decay of a detector, a polarization and a window](/concepts/microtime_histogram.md)
- **Workflow** — [Handling TTTR files (and Photon-HDF5)](/guides/12_handling_tttr_files.md), [Decays and correlation curves straight from a photon file](/guides/73_tttr_decay_and_correlation.md)

## Source

- Plugin package: `chisurf/plugins/tttr/microtime_histogram/`
- Manifest: {src}`chisurf/plugins/tttr/microtime_histogram/manifest.json`
- UI spec: {src}`chisurf/plugins/tttr/microtime_histogram/gui/histogram.view.json`
