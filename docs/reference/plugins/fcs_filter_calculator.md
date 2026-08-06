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
| Surfaces | cli, gui, services |
| State namespace | `fcs_filter_calculator` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| ↔ Pol | `polarized` | bool |  |  | Stack parallel and perpendicular detector-routing channels for anisotropy-aware filter computation. |
| ▤ AP | `fit_background` | bool |  |  | Add a constant microtime basis pattern representing afterpulsing and uniform dark-count background. |
| ⚡ IRF | `scatter_irf` | bool |  |  | Model scattered excitation light (the IRF) as a nuisance component. Each detector's measured IRF file, or its synthetic-IRF Width/Skew, is set per row in the Detectors table below. Afterpulse and scatter/IRF are always absorbed by their filters and excluded from the correlation-facing output. |
| ⟳ Periodic convolution | `periodic` | bool |  |  | Model the finite laser repetition period: the previous pulse's decay tail wraps into the window (fixes the ramp/offset in the residuals). |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `fcs_filter.compute` | no | Compute fFCS filters from arrays. |
| `fcs_filter.compute_from_files` | no | Compute fFCS filters from histogram files. |
| `fcs_filter.compute_mfd` | no | Compute MFD fFCS filters from arrays. |
| `fcs_filter.compute_mfd_from_files` | no | Compute MFD fFCS filters from files. |

## Source

- Plugin package: `chisurf/plugins/fcs/fcs_filter_calculator/`
- Manifest: {src}`chisurf/plugins/fcs/fcs_filter_calculator/manifest.json`
- UI spec: {src}`chisurf/plugins/fcs/fcs_filter_calculator/gui_parts/calculator_options.view.json`
- UI spec: {src}`chisurf/plugins/fcs/fcs_filter_calculator/gui_parts/instrument_options.view.json`
