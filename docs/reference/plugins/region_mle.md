---
type: Plugin Reference
title: Region MLE
description: Region MLE lifetime analysis from TTTR imaging data (PTU).
resource: chisurf/plugins/microscopy/region_mle/
tags: [reference, plugins, region-mle, imaging, lifetime]
anchor: plugin-region_mle
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-region_mle)=
# Region MLE

Region MLE lifetime analysis from TTTR imaging data (PTU).

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `region_mle` |
| Menu path | Imaging → Lifetime → **Region MLE** |
| Categories | Imaging, Lifetime |
| Version | 2.1.0 |
| Surfaces | cli, gui, services |
| State namespace | `region_mle` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Analysis

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| CLSM imaging files | `sel_files` | path_list |  |  | Confocal (CLSM) TTTR image file(s) to analyse. Drag-drop to add. |
| IRF file | `sel_irf_files` | path_list |  |  | IRF TTTR measurement (the first file is used). |
| Analysis region | `regions` | region_list |  |  | Restricts which of the detected regions are fitted — one cell, one illuminated patch, a field with the bright edge cropped off. Draw one, or load a saved region, a mask or a segmentation; several combine by the rule below. Empty = the whole frame. |
| Detector channels | `detector_chs_text` | str |  |  | Space-separated routing channels; even = parallel (∥), odd = perpendicular (⊥). |
| Fit start | `mtr_start` | int |  | 0 … 1000000 | Fit-window start on the binned micro-time axis. |
| Fit stop | `mtr_stop` | int |  | 1 … 1000000 | Fit-window stop on the binned micro-time axis. |
| Micro-time binning | `micro_time_binning` | int |  | 1 … 100000 | Integer down-binning of the micro-time axis before fitting. |
| Open results | `results_tsv` | file |  |  | Reopen a saved molecule_data.tsv (or joint_output.tsv) from a previous analysis to browse its molecules. |

### Regions

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Detection | `region_set` | str |  |  | Which detection in the measurement's container to fit, when it holds more than one. Regions are found by the Spot Finder; this tool fits the ones it is given. |
| Min photons | `min_photons` | int |  | 1 … 10000000 | Regions with fewer photons in the fit window are not fitted; they keep a row, with NaN parameters. |

### Fit (Fit23)

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| τ (ns) | `tau` | float |  | 0.0 … 1000.0 | Initial fluorescence lifetime. |
| fix τ | `fix_tau` | bool |  |  | Hold the lifetime fixed. |
| γ | `gamma` | float |  | 0.0 … 1.0 | Initial scatter fraction. |
| fix γ | `fix_gamma` | bool |  |  | Hold the scatter fraction fixed. |
| r0 | `r0` | float |  | 0.0 … 0.4 | Fundamental anisotropy. |
| fix r0 | `fix_r0` | bool |  |  | Hold the fundamental anisotropy fixed. |
| ρ (ns) | `rho` | float |  | 0.0 … 1000.0 | Rotational correlation time. |
| fix ρ | `fix_rho` | bool |  |  | Hold the rotational correlation time fixed. |
| l1 | `l1` | float |  | 0.0 … 1.0 | Polarisation mixing correction l1. |
| l2 | `l2` | float |  | 0.0 … 1.0 | Polarisation mixing correction l2. |
| 2I* (P+2S) | `p2s_twoIstar` | bool |  |  | Optimise P+2S instead of P and S separately. |
| BIFL scatter | `soft_bifl_scatter` | bool |  |  | Reduce Istar by the background contribution. |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `region_mle.analyze.run` | yes | Run molecule-wise MLE on PTU files. |
| `region_mle.contract.describe` | no | Return the RPC contract. |

## Theory and workflow

- **Theory** — [Regions and their properties](/concepts/region_properties.md)

## Source

- Plugin package: `chisurf/plugins/microscopy/region_mle/`
- Manifest: {src}`chisurf/plugins/microscopy/region_mle/manifest.json`
- UI spec: {src}`chisurf/plugins/microscopy/region_mle/gui/region_mle.view.json`
