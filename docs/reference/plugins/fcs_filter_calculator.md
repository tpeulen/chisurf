---
type: Plugin Reference
title: FCS Filter Calculator
description: Compute filtered-FCS (fFCS) lifetime filters from microtime decay patterns.
resource: chisurf/plugins/fcs/fcs_filter_calculator/
tags: [reference, plugins, fcs-filter-calculator, spectroscopy, fluorescence-correlation-spectroscopy]
anchor: plugin-fcs_filter_calculator
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-fcs_filter_calculator)=
# FCS Filter Calculator

Compute filtered-FCS (fFCS) lifetime filters from microtime decay patterns.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `fcs_filter_calculator` |
| Menu path | Spectroscopy → Fluorescence Correlation Spectroscopy → **FCS Filter Calculator** |
| Categories | Spectroscopy, Fluorescence Correlation Spectroscopy |
| Version | 1.0.0 |
| Surfaces | cli, emtk, gui, services |
| State namespace | `fcs_filter_calculator` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Inputs

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Pol | `polarized` | bool |  |  | Stack parallel and perpendicular detector-routing channels for anisotropy-aware filter computation. |
| AP | `fit_background` | bool |  |  | Add and reject a constant afterpulse and dark-count nuisance filter. |
| IRF | `scatter_irf` | bool |  |  | Add and reject the detector's measured or synthetic IRF as a scattered-light nuisance filter. |
| Global (stacked) detectors | `stacked` | bool |  |  | Global (stacked) multi-detector filters: use the inter-detector relative species brightness in one global filter solve. |

### Mixed decay

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Fit start | `fit_start` | int |  | 0 … 1000000 (step 1) | First TAC bin included in the filter fit. |
| Fit stop | `fit_stop` | int |  | 1 … 1000000 (step 1) | Exclusive upper TAC bin of the filter fit. |

### General

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Periodic convolution | `periodic` | bool |  |  | Model the finite laser repetition period: the previous pulse's decay tail wraps into the window. |

### Auto-fit

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Type | `autofit_kind` | choice |  | choices: `autofit_kinds` | Fit lifetime components, or FRET distances against the Forster radius. |
| Components / states | `autofit_components` | int |  | 1 … 12 (step 1) | Number of lifetime components or FRET states, 1 to 12. |
| Lifetime min (ns) | `autofit_tau_min` | float |  | 0.01 … 1000.0 (step 0.1) | Lower fitted lifetime bound in nanoseconds. |
| Lifetime max (ns) | `autofit_tau_max` | float |  | 0.02 … 1000.0 (step 0.5) | Upper lifetime bound; the donor lifetime for FRET fitting. |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `fcs_filter.compute` | no | Compute fFCS filters from arrays. |
| `fcs_filter.compute_from_files` | no | Compute fFCS filters from histogram files. |
| `fcs_filter.compute_mfd` | no | Compute MFD fFCS filters from arrays. |
| `fcs_filter.compute_mfd_from_files` | no | Compute MFD fFCS filters from files. |

## Theory and workflow

- **Theory** — [Filtered FCS (fFCS/FLCS) and 2D-FLCS](/concepts/filtered_fcs.md)
- **Workflow** — [Filtered FCS (fFCS / 2D-FLCS)](/guides/17_filtered_fcs.md)

## Source

- Plugin package: `chisurf/plugins/fcs/fcs_filter_calculator/`
- Manifest: {src}`chisurf/plugins/fcs/fcs_filter_calculator/manifest.json`
- UI spec: {src}`chisurf/plugins/fcs/fcs_filter_calculator/gui/filter_emtk.view.json`
- UI spec: {src}`chisurf/plugins/fcs/fcs_filter_calculator/gui_parts/calculator_options.view.json`
- UI spec: {src}`chisurf/plugins/fcs/fcs_filter_calculator/gui_parts/instrument_options.view.json`
