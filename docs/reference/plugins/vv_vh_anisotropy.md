---
type: Plugin Reference
title: VV/VH Anisotropy Decay
description: Compute and plot the anisotropy decay r(t) of a VV/VH file with a g-factor, backgrounds and a fractional VH shift.
resource: chisurf/plugins/vv_vh_anisotropy/
tags: [reference, plugins, vv-vh-anisotropy, spectroscopy, fluorescence-decay]
anchor: plugin-vv_vh_anisotropy
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-vv_vh_anisotropy)=
# VV/VH Anisotropy Decay

Compute and plot the anisotropy decay r(t) of a VV/VH file with a g-factor, backgrounds and a fractional VH shift.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `vv_vh_anisotropy` |
| Menu path | Spectroscopy → Fluorescence decay → **VV/VH Anisotropy Decay** |
| Categories | Spectroscopy, Fluorescence decay |
| Version | 1.0.0 |
| Surfaces | emtk, gui |
| State namespace | `vv_vh_anisotropy` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### VV/VH anisotropy

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| File | `loaded_file` | str |  |  | The VV/VH file that is loaded. |

### Correction

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| G-factor | `g_factor` | float |  | 0.0 … 10.0 (step 0.001) | Detector sensitivity correction applied to VH (0 to 10). |
| Apply backgrounds | `apply_bg` | bool |  |  | Subtract constant VV and VH backgrounds before calculation. |
| BG VV | `bg_vv` | float |  | -1000000000.0 … 1000000000.0 (step 1.0) | Constant background to subtract from VV. |
| BG VH | `bg_vh` | float |  | -1000000000.0 … 1000000000.0 (step 1.0) | Constant background to subtract from VH. |
| Flip VV↔VH | `flip` | bool |  |  | Swap channels when the source file has reversed polarization (data swapped in VV/VH). |
| Shift VH (channels) | `shift` | float |  | -150.0 … 150.0 (step 0.5) | Shift VH by a fractional channel using interpolation (-150 to 150). |

### r-infinity region

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Region start | `region_start` | float |  |  | First channel in the r-infinity averaging region. |
| Region end | `region_end` | float |  |  | Last boundary of the r-infinity averaging region. |
| r∞ | `r_infty_text` | str |  |  | r-infinity: the mean of r(t) over the region, five decimals; N/A when there is no valid point in it. |

## Theory and workflow

- **Theory** — [Time-resolved fluorescence anisotropy](/concepts/anisotropy.md)
- **Workflow** — [Fluorescence lifetime and anisotropy decay fitting](/guides/10_lifetime_anisotropy_fitting.md)

## Source

- Plugin package: `chisurf/plugins/vv_vh_anisotropy/`
- Manifest: {src}`chisurf/plugins/vv_vh_anisotropy/manifest.json`
- UI spec: {src}`chisurf/plugins/vv_vh_anisotropy/gui/vv_vh_emtk.view.json`
