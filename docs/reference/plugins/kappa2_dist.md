---
type: Plugin Reference
title: Kappa2 Distribution
description: Calculate and visualise the k² orientation-factor distribution for FRET using WIC, DWT, or isotropic models.
resource: chisurf/plugins/calculator/kappa2_dist/
tags: [reference, plugins, kappa2-dist, structure, fret]
anchor: plugin-kappa2_dist
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-kappa2_dist)=
# Kappa2 Distribution

Calculate and visualise the k² orientation-factor distribution for FRET using WIC, DWT, or isotropic models.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `kappa2_dist` |
| Menu path | Structure → FRET → **Kappa2 Distribution** |
| Categories | Structure, FRET |
| Version | 1.1.0 |
| Surfaces | cli, gui, services |
| State namespace | `kappa2_dist` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### General

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Model | `model_type` | choice |  | choices: cone, diffusion, isotropic | Wobbling-in-Cone, Diffusion-with-Traps, or isotropic orientation model. |

### Anisotropy Parameters

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| r₀ (fund.) | `r_0` | float |  | 0.0 … 0.4 (step 0.01) | Fundamental anisotropy of the dye. |
| r_D∞ | `r_Dinf` | float |  | 0.0 … 0.4 (step 0.01) | Residual anisotropy of the donor without FRET. |
| r_A∞ | `r_Ainf` | float |  | 0.0 … 0.4 (step 0.01) | Residual anisotropy of direct-excited acceptor. |
| r_AD∞ | `r_ADinf` | float |  | 0.0 … 0.4 (step 0.001) | Residual anisotropy of FRET-sensitised acceptor. |

### Calculation Options

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| true κ² | `kappa2_true` | float |  | 0.0 … 4.0 (step 0.01) | Assumed orientation factor used for R_app / R_DA. |
| FRET E | `fret_efficiency` | float |  | 0.001 … 0.999 (step 0.01) | FRET efficiency (used for DWT model). |
| Step (°) | `step` | float |  | 0.01 … 10.0 (step 0.1) | Angular step size for the WIC grid search. |
| Bins | `n_bins` | int |  | 5 … 999 (step 1) | Number of bins in the κ² histogram. |
| r_AD known (use δ) | `rAD_known` | bool |  |  | When checked, use the δ angle computed from residual anisotropies. |

### Results

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Mean κ² | `k2_mean` | float |  |  |  |
| SD κ² | `k2_sd` | float |  |  |  |
| Mean R_app/R_DA | `Rapp_mean` | float |  |  |  |
| SD R_app/R_DA | `RappSD` | float |  |  |  |
| δ (deg) | `delta_deg` | float |  |  |  |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `kappa2_dist.compute` | no |  |

## Theory and workflow

- **Theory** — [The orientation factor κ² and what it costs](/concepts/kappa2_orientation.md)
- **Workflow** — [κ² distributions: how much is the orientation assumption costing?](/guides/61_kappa2_distribution.md)

## Source

- Plugin package: `chisurf/plugins/calculator/kappa2_dist/`
- Manifest: {src}`chisurf/plugins/calculator/kappa2_dist/manifest.json`
- UI spec: {src}`chisurf/plugins/calculator/kappa2_dist/k2dist.view.json`
