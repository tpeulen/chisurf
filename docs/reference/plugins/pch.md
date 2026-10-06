---
type: Plugin Reference
title: PCH
description: Photon Counting Histogram (PCH) analysis for single-molecule fluorescence data. Compute PCH histograms from TTTR files and fit multi-species models to extract molecular brightness and occupancy.
resource: chisurf/plugins/pch/
tags: [reference, plugins, pch, spectroscopy, correlation]
anchor: plugin-pch
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-pch)=
# PCH

Photon Counting Histogram (PCH) analysis for single-molecule fluorescence data. Compute PCH histograms from TTTR files and fit multi-species models to extract molecular brightness and occupancy.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `pch` |
| Menu path | Spectroscopy → Correlation → **PCH** |
| Categories | Spectroscopy, Correlation |
| Version | 2.0.0 |
| Surfaces | cli, emtk, gui, services |
| State namespace | `pch` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Data settings

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| File | `filename` | str |  |  | The photon-stream file that is loaded. Use Load TTTR or drop a file on the window. |
| Channels | `channels` | str |  |  | Comma-separated routing channels whose photons are counted, for example 0,2. Empty uses all channels. |
| Bin time | `bin_time_us` | float |  | 0.1 … 1000000.0 (step 10.0) | Width of the counting interval in microseconds. The histogram is the distribution of photon counts per interval. |
| Micro time | `micro_time_min` | int |  | 0 … 65535 (step 1) | Lower micro-time gate (TAC channel): photons below it are not counted. |
| to | `micro_time_max` | int |  | 0 … 65535 (step 1) | Upper micro-time gate (TAC channel): photons above it are not counted. |

### Model fit

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Components | `n_components` | int |  | 1 … 10 (step 1) | Number of molecular species in the model. Each species has a brightness ε and a mean occupancy ⟨N⟩. |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `pch.load_tttr` | no | Opens a TTTR file with tttrlib and reports its metadata: available routing channels, total photon count, macro-time resolution and micro-time range. Call this first to discover which channels to select for pch.compute. |
| `pch.compute` | no | Bins the photon stream into counting intervals of bin_time_us and histograms the counts per bin into the photon counting histogram P(k). An optional micro-time window gates the photons before binning. |
| `pch.fit` | no | Fits an n-component PCH model to an experimental P(k), yielding per-species molecular brightness (epsilon), mean occupancy (N) and amplitude fractions plus chi-square statistics. Restrict the fitted k range with fit_low/fit_high. |

## Theory and workflow

- **Theory** — [Photon-counting histogram (PCH) and FIDA](/concepts/pch_fida.md)
- **Workflow** — [FIDA — photon-counting histograms](/guides/04_fida_pch.md)

## Source

- Plugin package: `chisurf/plugins/pch/`
- Manifest: {src}`chisurf/plugins/pch/manifest.json`
- UI spec: {src}`chisurf/plugins/pch/gui/pch.view.json`
