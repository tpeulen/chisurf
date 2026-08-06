(plugin-fcs-lfcs-sim)=
# Lifetime-FCS Simulator

Simulate diffusing species with distinct fluorescence lifetimes and optional interconversion, then recover them by lifetime-filtered (FLCS) correlation.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `fcs-lfcs-sim` |
| Menu path | Spectroscopy → Fluorescence Correlation Spectroscopy → **Lifetime-FCS Simulator** |
| Categories | Spectroscopy, Fluorescence Correlation Spectroscopy |
| Version | 1.0.0 |
| Surfaces | gui |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Species (lifetime + diffusion)

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| τ₁ (ns) | `tau1_ns` | float |  | 0.05 … 50.0 (step 0.1) | Fluorescence lifetime of species 1. |
| D₁ (µm²/ms) | `d1_um2_ms` | float |  | 0.001 … 100.0 (step 0.1) | Translational diffusion coefficient of species 1. τ_D = w₀²/(4·D). |
| τ₂ (ns) | `tau2_ns` | float |  | 0.05 … 50.0 (step 0.1) | Fluorescence lifetime of species 2. |
| D₂ (µm²/ms) | `d2_um2_ms` | float |  | 0.001 … 100.0 (step 0.1) | Translational diffusion coefficient of species 2. |

### Kinetics / statistics

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| k (1/ms) | `exchange_rate_ms` | float |  | 0.0 … 1000.0 (step 0.5) | Symmetric species interconversion rate (0 = static species). Set the two diffusion coefficients equal to isolate the exchange in the cross-correlation. |
| Photons | `n_photons` | int |  | 50000 … 20000000 (step 50000) | Photon budget. More photons = cleaner filtered correlations (and a slower simulation). |
| Seed | `seed` | int |  | 0 … 1000000 (step 1) | RNG seed (deterministic output). |

## Source

- Plugin package: `chisurf/plugins/fcs/fcs_lfcs_sim/`
- Manifest: {src}`chisurf/plugins/fcs/fcs_lfcs_sim/manifest.json`
- UI spec: {src}`chisurf/plugins/fcs/fcs_lfcs_sim/gui/lfcs_sim.view.json`
