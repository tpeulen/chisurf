---
type: Plugin Reference
title: Docking & Screening
description: FRET-restrained rigid-body docking, refinement, structure-library screening and error estimation using IMP + IMP.bff accessible volumes (a thin shim around IMP.pmi).
resource: chisurf/plugins/modelling/fret/
tags: [reference, plugins, fret-docking, structure, fret]
anchor: plugin-fret_docking
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-fret_docking)=
# Docking & Screening

FRET-restrained rigid-body docking, refinement, structure-library screening and error estimation using IMP + IMP.bff accessible volumes (a thin shim around IMP.pmi).

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `fret_docking` |
| Menu path | Structure → FRET → **Docking & Screening** |
| Categories | Structure, FRET |
| Version | 1.0.0 |
| Surfaces | cli, emtk, gui, services |
| State namespace | `fret_docking` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Inputs

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| fps.json | `fps_json` | str |  |  | Labelling positions and experimental distances (fps.json). |
| Output | `output_dir` | str |  |  | Directory for RMF trajectory, best-scoring PDBs and the score CSV. |
| Op | `operation` | choice |  | choices: dock, refine, screen, score | dock = rigid-body docking; refine = CG minimisation; screen = rank a library; score = single structure. |
| Method | `method` | choice |  | choices: minimize, mc | Docking engine: minimize = fast IMP conjugate-gradient energy minimisation (default); mc = replica-exchange Monte-Carlo sampling. |
| Score set | `score_set` | str |  |  | Named chi2 score set in the fps.json (empty = all distances). |

### Docking

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Runs | `n_repeats` | int |  | 1 … 1000 | Number of independent docking runs from random starts (FPS n_trials). >1 estimates the score spread; each run is plotted and listed in the results table and runs in parallel. |
| Iterations | `n_frames` | int |  | 1 … 100000 (step 50) | Maximum docking iterations per run (FPS max_iter) — conjugate-gradient steps for minimize, Monte-Carlo frames for mc. |
| Clash k | `ev_weight` | float |  | 0.0 … 1000.0 (step 1.0) | Excluded-volume / clash penalty weight (FPS k_clash). |
| Refine | `refine_av_cycles` | int |  | 0 … 20 | FPS-style refinement cycles after docking: re-compute the accessible volumes on the docked structure (real AV calc, accounting for inter-body occlusion) and re-minimise. 0 = none. |
| Fixed body | `fixed_body` | int |  | 0 … 100 | body_id kept fixed as the reference; the others are mobile. |
| sigma_DA | `sigma_da` | float |  | 0.0 … 30.0 (step 0.5) | Width of the mean-position transfer function (FPS distance distribution width). |
| AV backend | `av_backend` | choice |  | choices: auto, labellib, imp-bff | Accessible-volume backend for distance distributions / screening. |
| P(R_DA) | `save_distributions` | bool |  |  | After docking, compute and export the full P(R_DA) distance distributions (real AV convolution) to distance_distributions.csv. |
| Movie | `save_trajectory` | bool |  |  | Save the docking trajectory (minimize) so the 3D preview can animate the docking path with the movie slider. |
| Resume | `continue_from_poses` | bool |  |  | Continue from the docked poses of the last run or the loaded project (skip the random shuffle) instead of starting fresh. Enabled automatically when a project with saved poses is loaded. |

### Monte-Carlo (mc method only)

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| MC steps | `mc_steps` | int |  | 1 … 1000 | Monte-Carlo steps per frame. |
| Keep best | `n_best` | int |  | 0 … 1000 | Number of best-scoring PDB models to write (and step through in the 3D preview). |
| Anneal | `simulated_annealing` | bool |  |  | Enable the PMI simulated-annealing temperature schedule. |

### Input

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Stride | `stride` | int |  | 1 … 1000000 | Read every n-th frame of the trajectory (1 = all frames). |

### Candidate sites from residues

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Chain | `chain` | str |  |  | Chain of the residues: its identifier, or its index (empty = the first chain). |
| Residues (PDB resSeq) | `residues` | str |  |  | Residue numbers as written in the PDB file: single numbers and ranges, e.g. 35-50,85-95,115-120. |
| Attachment atom | `atom` | choice |  | choices: CB, CA | The atom the dye is attached at (CB falls back to CA where a residue has none, e.g. glycine). |

### Efficiency

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| R0 (Å) | `r0` | float |  | 1.0 … 200.0 | Forster radius of the dye pair, in Angstrom (a pair the FPS JSON gives its own R0 keeps it). |
| Use AV backend | `use_av` | bool |  |  | With an FPS JSON: compute the efficiency from the accessible volumes of the dyes instead of the attachment-atom distance (falls back to the distance, with a message, when the AV cannot be computed). |
| AV samples | `av_samples` | int |  | 100 … 1000000 | Distance samples drawn between the two accessible volumes of a pair, per frame. |
| Max AV points | `av_max_points` | int |  | 1000 … 500000 | Largest number of points kept of an accessible volume. |

### Selection

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Max pairs | `max_pairs` | int |  | 1 … 999 | How many pairs to choose. |
| Expected E error | `err` | float |  | 0.0001 … 1.0 (step 0.01) | The experimental uncertainty of a FRET efficiency; a pair is informative to the extent the conformations differ by more than this. |
| Unique pairs only | `unique_only` | bool |  |  | Choose every pair at most once. |
| RMSD atom selection | `rmsd_selection` | str |  |  | The atoms the conformations are compared on (an MDTraj-style selection, e.g. name CA); empty = all atoms. |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `fret.info_backends` | no |  |
| `fret.dock` | no |  |
| `fret.refine` | no |  |
| `fret.score` | no |  |
| `fret.screen` | no |  |
| `fret.estimate_errors` | no |  |

## Theory and workflow

- **Theory** — [Accessible-volume (AV) dye modeling](/concepts/accessible_volume.md), [Structure trajectories: superposition, RMSD, clashes and FRET along a trajectory](/concepts/structure_trajectories.md)
- **Workflow** — [Accessible-volume (AV) calculations](/guides/23_accessible_volume.md), [Trajectory tools: align, convert, filter, score and FRET a structure ensemble](/guides/81_trajectory_tools.md)

## Source

- Plugin package: `chisurf/plugins/modelling/fret/`
- Manifest: {src}`chisurf/plugins/modelling/fret/manifest.json`
- UI spec: {src}`chisurf/plugins/modelling/fret/gui/fret_dock.view.json`
- UI spec: {src}`chisurf/plugins/modelling/fret/gui/pair_selection.view.json`
