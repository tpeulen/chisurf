---
type: Plugin Reference
title: HydroPro
description: Graphical front-end to the HYDROPRO / HYDRO++ suite for computing hydrodynamic properties (e.g. translational diffusion coefficient) from atomic or bead-model structures.
resource: chisurf/plugins/modelling/hydropro/
tags: [reference, plugins, hydropro, structure, computation]
anchor: plugin-hydropro
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-hydropro)=
# HydroPro

Graphical front-end to the HYDROPRO / HYDRO++ suite for computing hydrodynamic properties (e.g. translational diffusion coefficient) from atomic or bead-model structures.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `hydropro` |
| Menu path | Structure → Computation → **HydroPro** |
| Categories | Structure, Computation |
| Version | 1.0.0 |
| Surfaces | cli, gui, services |
| State namespace | `hydropro` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Executable & input

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Executable | `exe_path` | str |  |  | Path to the HYDROPRO or HYDRO++ executable. The flavour is auto-detected from the filename. |
| Structures | `struct_files` | str |  |  | Comma-separated structural files (PDB or bead coordinate files). Set with the 'Select files…' button. |

### Primary model

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| INDMODE | `indmode` | choice |  | choices: 1, 2, 4 | 1 = atomic/shell; 2 = residue/shell; 4 = residue/bead. |
| AER | `aer` | float |  | 0.0 … 50.0 (step 0.1) | Hydrodynamic radius of primary elements. Typical: 2.9 (mode 1), 4.8 (2), 6.1 (4). |
| NSIG | `nsig` | int |  | -1 … 50 | Number of minibead radii (>2, typically 5–8). Use -1 for automatic SIGMIN/SIGMAX. |
| SIGMIN | `sigmin` | float |  | 0.0 … 50.0 (step 0.1) | Minimum minibead radius (shell modes 1/2 when NSIG ≠ -1). |
| SIGMAX | `sigmax` | float |  | 0.0 … 50.0 (step 0.1) | Maximum minibead radius (shell modes 1/2 when NSIG ≠ -1). |

### Solvent & macromolecule

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| T | `t` | float |  | -20.0 … 200.0 (step 1.0) | Temperature in centigrade. |
| ETA | `eta` | float |  | 0.0 … 10.0 (step 0.001) | Solvent viscosity in poises (water at 20 °C ≈ 0.01 P). |
| RM | `rm` | float |  | 0.0 … 1000000000.0 (step 1000.0) | Molecular weight in daltons. |
| VBAR | `vbar` | float |  | 0.0 … 5.0 (step 0.01) | Partial specific volume (proteins ≈ 0.73–0.75 cm³/g). |
| RHO | `rho` | float |  | 0.0 … 5.0 (step 0.01) | Solution (≈ solvent) density in g/cm³. |

### Optional calculations

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| NQ | `nq` | int |  | -1 … 1000 | Scattering q values: 0 omit, -1 automatic, >0 specify QMAX. |
| QMAX | `qmax` | float |  | 0.0 … 1000000000.0 | Upper limit of scattering variable q (only when NQ > 0). |
| NS | `ns` | int |  | -1 … 1000 | Intervals for the distance distribution p(r): 0 omit, -1 automatic, >0 specify RMAX. |
| RMAX | `rmax` | float |  | 0.0 … 1000000000.0 | Maximum distance for p(r) (only when NS > 0). |
| NTRIALS | `ntrials` | int |  | 0 … 100000000 | Monte-Carlo trials for the covolume calculation (0 to omit; very time-consuming). |
| Full diffusion tensor | `idif` | bool |  |  | IDIF=1: output the full 6×6 diffusion tensor and diffusion centre. |

### Results

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Status | `status` | str |  |  | Outcome of the last run. |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `hydropro.run` | no | Run HYDROPRO/HYDRO++ over structures and return diffusion coefficients. |
| `hydropro.parse_res` | no | Parse a HYDRO *.res report for the translational diffusion coefficient. |

## Theory and workflow

- **Theory** — [Molecular surfaces and solvent accessibility](/concepts/molecular_surfaces.md)

## Source

- Plugin package: `chisurf/plugins/modelling/hydropro/`
- Manifest: {src}`chisurf/plugins/modelling/hydropro/manifest.json`
- UI spec: {src}`chisurf/plugins/modelling/hydropro/gui/hydropro.view.json`
