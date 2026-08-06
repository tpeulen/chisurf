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
| Surfaces | cli, gui, services |
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

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `fcs_calculator.compute` | no | Solve the linked confocal-FCS quantities for one constraint. |
| `fcs_calculator.water_viscosity` | no | Water viscosity (mPa·s) at a temperature. |
| `fcs_calculator.reference_dyes` | no | MMFDB reference species with a diffusion coefficient D(25 °C, water). |

## Source

- Plugin package: `chisurf/plugins/fcs/fcs_calculator/`
- Manifest: {src}`chisurf/plugins/fcs/fcs_calculator/manifest.json`
- UI spec: {src}`chisurf/plugins/fcs/fcs_calculator/fcs_calculator.view.json`
