(plugin-fret_calculator)=
# FRET-Calculator

Combined heteroFRET and homoFRET parameter calculator.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `fret_calculator` |
| Menu path | Main → Tools → **FRET-Calculator** |
| Categories | Main, Tools |
| Version | 1.0.0 |
| Surfaces | cli, gui, services |
| State namespace | `fret_calculator` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Lifetime D0 | `tau0` | float |  | 0.001 … 9999.0 | Donor-only fluorescence lifetime (no acceptor). |
| Förster R0 | `R0` | float |  | 0.1 … 999.0 | Förster radius R0. |
| Distance DA | `R` | float |  | 0.1 … 9999.0 | Donor-acceptor distance. Any of distance, lifetime, efficiency or rate may be entered; the others are recomputed. |
| Lifetime DA | `tau` | float |  | 0.0 … 9999.0 | Donor lifetime in the presence of acceptor (D in DA). Editable input that back-computes the distance. |
| Efficiency | `E` | float |  | 0.0 … 1.0 | FRET efficiency. Editable input that back-computes the distance. |
| kFRET | `kFRET` | float |  | 0.0 … 9999.0 | FRET rate constant. Editable input that back-computes the distance. |
| Sigma | `sigma` | float |  | 0.1 … 999.0 | Width of the donor-acceptor distance distribution. |
| chi distribution | `use_chi` | bool |  |  | Use a 3D non-central chi distance distribution instead of a Gaussian. Distances are never Gaussian: a Gaussian assigns weight to negative / near-zero distances, while the chi distribution is non-negative and vanishes at contact (R=0). |
| t_RM | `t_RM` | float |  | 0.001 … 9999.0 | Anisotropy decay (energy-migration) time t_RM. |
| rho | `rho` | float |  | 0.001 … 9999.0 | Rotational correlation time rho. |
| k_homo | `k_homo` | float |  | 0.0 … 9999.0 | Homo-FRET (energy-migration) rate constant (derived from t_RM / rho). |
| R_DA | `R_DA` | float |  | 0.0 … 9999.0 | Donor-acceptor distance implied by the homo-FRET rate. Editable input that back-maps to the anisotropy relaxation time. |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `fret_calculator.fret.compute` | no | Compute FRET parameters from donor-acceptor distance. |
| `fret_calculator.fret.compute_from_efficiency` | no | Compute FRET parameters from transfer efficiency. |
| `fret_calculator.fret.compute_from_lifetime` | no | Compute FRET parameters from donor lifetime with acceptor. |
| `fret_calculator.fret.compute_from_rate` | no | Compute FRET parameters from rate constant. |
| `fret_calculator.homo.compute` | no | Compute homoFRET exchange rate and effective distance. |
| `fret_calculator.homo.backmap` | no | Back-map homoFRET distance to anisotropy relaxation time. |

## Theory and workflow

- **Theory** — [Förster resonance energy transfer (FRET)](/concepts/fret.md)

## Source

- Plugin package: `chisurf/plugins/calculator/fret_calculator/`
- Manifest: {src}`chisurf/plugins/calculator/fret_calculator/manifest.json`
- UI spec: {src}`chisurf/plugins/calculator/fret_calculator/gui/fret.view.json`
- UI spec: {src}`chisurf/plugins/calculator/fret_calculator/gui/homofret.view.json`
