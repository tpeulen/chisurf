---
type: Plugin Reference
title: Diffusion/Volume Calculator
description: FCS confocal diffusion/volume calculator (tau, D, r_h, Veff, concentration).
resource: chisurf/plugins/fcs/fcs_calculator/
tags: [reference, plugins, fcs-calculator, spectroscopy, fluorescence-correlation-spectroscopy]
anchor: plugin-fcs_calculator
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-fcs_calculator)=
# Diffusion/Volume Calculator

FCS confocal diffusion/volume calculator (tau, D, r_h, Veff, concentration).

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `fcs_calculator` |
| Menu path | Spectroscopy → Fluorescence Correlation Spectroscopy → **Diffusion/Volume Calculator** |
| Categories | Spectroscopy, Fluorescence Correlation Spectroscopy |
| Version | 1.0.0 |
| Surfaces | cli, emtk, gui, services |
| State namespace | `fcs_calculator` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Diffusion / volume

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| τ (µs) | `tau_us` | float |  | 0.001 … 1000000000.0 | Diffusion correlation time τ_D. |
| D (µm²/s) | `D_um2_s` | float |  | 0.0001 … 1000000.0 | Translational diffusion coefficient (read-only unless 'Fix D'). |
| rₕ (nm) | `rh_nm` | float |  | 0.001 … 1000000.0 | Hydrodynamic radius (read-only unless 'Fix rₕ'). |
| S (wz/wxy) | `S` | float |  | 0.1 … 20.0 | Confocal aspect ratio (axial / lateral beam waist). |
| Veff (fL) | `veff_fL` | float |  | 1e-06 … 1000000000.0 | Effective confocal volume (read-only unless 'Fix Veff'). |
| T (°C) | `temp_C` | float |  | -50.0 … 200.0 | Temperature. |
| η (mPa·s) | `eta_mPa_s` | float |  | 0.01 … 10000.0 | Solvent viscosity; computed from the water model when 'Use water η(T)' is enabled. |
| Use water η(T) | `use_water_eta` | bool |  |  | Use the temperature-dependent viscosity of water (Kapusta 2010 app note). |

### Occupancy

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| 1/N | `invN` | float |  | 0.0 … 1000000000.0 | Inverse occupancy G(0) = 1/N; exceeds 1 for sub-single-molecule occupancy. |
| N | `num_mols` | float |  | 0.0 … 1000000000000.0 (step 0.1) | Average number of molecules in Veff. |
| Conc (nM) | `conc_nM` | float |  | 0.0 … 1000000000.0 (step 0.01) | Concentration; N = 0.602214 × c_nM × Veff_fL. |

### Constraint (choose one)

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| constraint | `constraint` | choice |  | choices: ['D', 'Fix D'], ['rh', 'Fix rₕ'], ['V', 'Fix Veff'] | Fix D, rₕ or Veff: that field is the input, the other two are computed and read-only. |

### Reference dye (D @ 25 °C, water)

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| dye | `dye` | choice |  | choices: `dye_names` | Reference species from MMFDB carrying a diffusion coefficient D(25 °C, water); curate them in the MMFDB admin tool. |
| scale_dref | `scale_dref` | choice |  | choices: [True, 'Apply with Temp/η scaling'], [False, 'Apply at 25 °C (no scaling)'] | Scale the reference D from 25 °C water to the current temperature and viscosity (Stokes-Einstein), or use it as tabulated. |

### Molecular shape

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Type | `shape_type` | choice |  | choices: Sphere, Ellipsoid, Cylinder | Sphere (Stokes-Einstein), prolate ellipsoid (Perrin friction factor) or cylinder (Hansen approximation). |
| Size (nm) | `shape_size_nm` | float |  | 0.1 … 1000000000.0 | Sphere diameter, ellipsoid minor-axis diameter or cylinder diameter, in nanometres. |
| Aspect | `shape_aspect` | float |  | 0.1 … 1000.0 | Ellipsoid major/minor axis ratio or cylinder length/diameter (not used for a sphere). |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `fcs_calculator.compute` | no | Solve the linked confocal-FCS quantities for one constraint. |
| `fcs_calculator.water_viscosity` | no | Water viscosity (mPa·s) at a temperature. |
| `fcs_calculator.reference_dyes` | no | MMFDB reference species with a diffusion coefficient D(25 °C, water). |

## Theory and workflow

- **Theory** — [FCS: the correlation curve and its models](/concepts/fcs_correlation.md)
- **Workflow** — [Enderlein MDF & two-focus FCS](/guides/05_enderlein_mdf_two_focus_fcs.md)

## Source

- Plugin package: `chisurf/plugins/fcs/fcs_calculator/`
- Manifest: {src}`chisurf/plugins/fcs/fcs_calculator/manifest.json`
- UI spec: {src}`chisurf/plugins/fcs/fcs_calculator/fcs_calculator.view.json`
- UI spec: {src}`chisurf/plugins/fcs/fcs_calculator/gui/fcs_calculator_emtk.view.json`
