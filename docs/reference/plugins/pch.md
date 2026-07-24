(plugin-pch)=
# PCH

Photon Counting Histogram (PCH) analysis for single-molecule fluorescence data. Compute PCH histograms from TTTR files and fit multi-species models to extract molecular brightness and occupancy.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `pch` |
| Menu path | Spectroscopy → Single-Molecule → **PCH** |
| Categories | Spectroscopy, Single-Molecule |
| Version | 2.0.0 |
| Surfaces | cli, gui, services |
| State namespace | `pch` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `pch.load_tttr` | no | Opens a TTTR file with tttrlib and reports its metadata: available routing channels, total photon count, macro-time resolution and micro-time range. Call this first to discover which channels to select for pch.compute. |
| `pch.compute` | no | Bins the photon stream into counting intervals of bin_time_us and histograms the counts per bin into the photon counting histogram P(k). An optional micro-time window gates the photons before binning. |
| `pch.fit` | no | Fits an n-component PCH model to an experimental P(k), yielding per-species molecular brightness (epsilon), mean occupancy (N) and amplitude fractions plus chi-square statistics. Restrict the fitted k range with fit_low/fit_high. |

## Source

- Plugin package: `chisurf/plugins/pch/`
- Manifest: `chisurf/plugins/pch/manifest.json`
