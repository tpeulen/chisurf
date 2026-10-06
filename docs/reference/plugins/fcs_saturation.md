---
type: Plugin Reference
title: FCS Saturation
description: FCS Saturation Calculator for arbitrary multi-state kinetic schemes (including Cy5).
resource: chisurf/plugins/calculator/fcs_saturation_calc/
tags: [reference, plugins, fcs-saturation, spectroscopy, fluorescence-correlation-spectroscopy]
anchor: plugin-fcs_saturation
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-fcs_saturation)=
# FCS Saturation

FCS Saturation Calculator for arbitrary multi-state kinetic schemes (including Cy5).

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `fcs_saturation` |
| Menu path | Spectroscopy → Fluorescence Correlation Spectroscopy → **FCS Saturation** |
| Categories | Spectroscopy, Fluorescence Correlation Spectroscopy |
| Version | 1.0.0 |
| Surfaces | cli, emtk, gui, services |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Photophysics

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Scheme | `scheme_preset` | choice |  | choices: `scheme_names` | Load a photophysical scheme. Presets are starting points, not constraints: every rate, cross-section and brightness stays editable. |
| Laser power | `power_mW` | float |  | 0.0 … 100.0 (step 0.05) | Total laser power measured at the objective (mW). It sets the photon flux and with it the peak excitation rate k_exc(0,0) = 2 sigma Phi / (pi w_r^2). At 0 the saturated curve is exactly the unsaturated Gaussian. Type a value or use the arrows. |
| Power (log) | `power_log` | float |  | -3.0 … 2.0 | The same power on a logarithmic scale from 0.001 to 100 mW (the exponent is shown), because the interesting range spans decades. |
| Excitation λ | `wavelength_nm` | float |  | 200.0 … 1200.0 (step 1.0) | Excitation wavelength. It sets the photon energy, so the same power delivers more photons at longer wavelengths, and the extinction read from a chosen dye. |
| Dye (MMFDB) | `dye` | choice |  | choices: `dye_options` | Read the extinction coefficient at the excitation wavelength from the dye's stored absorption spectrum in MMFDB. Leave empty to type the extinction in the Optics table. |
| Rate units | `rate_unit` | choice |  | choices: 1/s, 1/ms, 1/us, 1/ns | Time base of the dark transition rates. Changing it rescales the entered values, it does not reinterpret them. |
| Bunching dynamics | `include_bunching` | bool |  |  | Include the photokinetic bunching factor in the saturated curve: the relaxation of the scheme on the diffusion timescale. |
| Number of states | `n_states` | int |  | 2 … 6 (step 1) | Number of states of the scheme. Two is the minimum (ground and excited); add one for each dark, isomeric or bleached state. |

### General

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Normalize G(τ) to 1.0 | `normalize_fcs` | bool |  |  | Scale both curves to G(0) = 1 to compare their shapes: the saturated curve is not only smaller but broader. |
| 1-component fit | `show_gaussian_fit` | bool |  |  | Overlay the best single-component 3D Gaussian fit of the saturated curve, what a standard FCS analysis would report. |
| Excitation k(r) | `show_power_profile` | bool |  |  | Show the excitation rate profile across the focus, relative to its peak. |
| State populations | `show_state_profiles` | bool |  |  | Show the fraction of molecules in every state as a function of the radial position. |
| Emission Σ Q·P | `show_fluorescence_profile` | bool |  |  | Show the emission profile, the sum of the state brightnesses times their populations. |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `fcs_saturation.compute` | no | Compute unperturbed and saturated FCS curves for arbitrary kinetic scheme. |

## Theory and workflow

- **Theory** — [Optical saturation in FCS](/concepts/fcs_saturation.md)
- **Workflow** — [FCS saturation and focal-volume expansion](/guides/56_fcs_saturation.md)

## Source

- Plugin package: `chisurf/plugins/calculator/fcs_saturation_calc/`
- Manifest: {src}`chisurf/plugins/calculator/fcs_saturation_calc/manifest.json`
- UI spec: {src}`chisurf/plugins/calculator/fcs_saturation_calc/gui/saturation_emtk.view.json`
