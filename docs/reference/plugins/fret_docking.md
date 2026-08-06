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
| Surfaces | cli, gui, services |
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

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `fret.info_backends` | no |  |
| `fret.dock` | no |  |
| `fret.refine` | no |  |
| `fret.score` | no |  |
| `fret.screen` | no |  |
| `fret.estimate_errors` | no |  |

## Source

- Plugin package: `chisurf/plugins/modelling/fret/`
- Manifest: {src}`chisurf/plugins/modelling/fret/manifest.json`
- UI spec: {src}`chisurf/plugins/modelling/fret/gui/fret_dock.view.json`
