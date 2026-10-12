---
type: Plugin Reference
title: QuEst
description: 'Structure-based simulation of dynamic PET quenching and FRET for dyes tethered to proteins by flexible linkers: accessible volume, Brownian dynamics and photon Monte-Carlo on IMP.bff. The engine is this plugin''s core/ (the former quest package).'
resource: chisurf/plugins/quenching_estimator/
tags: [reference, plugins, quenching-estimator, structure, computation]
anchor: plugin-quenching_estimator
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-quenching_estimator)=
# QuEst

Structure-based simulation of dynamic PET quenching and FRET for dyes tethered to proteins by flexible linkers: accessible volume, Brownian dynamics and photon Monte-Carlo on IMP.bff. The engine is this plugin's core/ (the former quest package).

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `quenching_estimator` |
| Menu path | Structure → Computation → **QuEst** |
| Categories | Structure, Computation |
| Version | 19.8.13 |
| Surfaces | cli, emtk, gui, services |
| State namespace | `quenching_estimator` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Structure

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Structure file | `pdb` | file |  |  | Path to the structure file (PDB/CIF), or a bare four-character RCSB PDB ID used for AV calculation. |
| Attachment chain | `attachment_chain` | str |  |  | Chain identifier of the amino acid residue where the dye is tethered. |
| Attachment residue | `attachment_residue` | int |  | -100000 … 100000 | Residue sequence number of the amino acid where the dye is tethered. |
| Attachment atom | `attachment_atom` | str |  |  | Atom name (e.g., CB, CA) used as the tethering point for the dye. |
| Structure | `structure_label` | str |  |  | Outcome of the last simulation. |

### Dye

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Linker length (Å) | `av_linker_length` | float |  | 0.0 … 200.0 | Maximum distance from attachment point to the center of the dye. |
| Linker width (Å) | `av_linker_width` | float |  | 0.0 … 50.0 | Width of the linker tethering the dye. |
| Dye radius (Å) | `av_radius1` | float |  | 0.0 … 50.0 | Exclusion radius representing the dye sphere (single-sphere approximation). |
| Allowed sphere (Å) | `av_allowed_sphere_radius` | float |  | 0.0 … 20.0 | Radius around the attachment atom inside which the linker ignores obstacles, so it can leave the atom it is tied to. On by default at FPS's 2.25 Å (0.5 × the 4.5 Å linker width); the attachment atom itself is never an obstacle. |
| Grid resolution (Å) | `dg` | float |  | 0.1 … 5.0 | Grid resolution used to compute the accessible volume (AV) and diffusion search space. |

### Simulation

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Unquenched lifetime (ns) | `tau0` | float |  | 0.0 … 1000.0 | Fluorescence lifetime of the donor dye in the absence of quenching. |
| Donor diffusion coefficient (Å²/ns) | `donor_D` | float |  | 0.0 … 1000.0 | Diffusion coefficient of the donor dye in solution, when not interacting with the protein surface. |
| Simulation time (ns) | `t_max` | float |  | 0.0 … 1000000000.0 | Total length of the simulated Brownian dynamics trajectory. |
| Time step (ns) | `t_step` | float |  | 1e-06 … 1000.0 | Time step size for the Brownian dynamics trajectory calculation. |
| Simulated photons | `n_photons` | int |  | 1 … 2147483647 | Number of excitation photons simulated to reconstruct the fluorescence decay histogram. |
| Decay bins | `n_bins` | int |  | 1 … 65535 | Number of time channels/bins used to construct the output decay histogram. |
| Coarse-grained structure | `coarse_grained` | bool |  |  | Reduce the structure to backbone plus CB before simulating, with CB moved to the side-chain centre of mass. Side-chain atoms are then absent, so every residue's quenching centre falls back to that CB pseudo-atom, and the accessible volume grows because side chains no longer block it. This is a modelling choice, not a speed optimisation: QuEst's cost is dominated by the AV grid rather than the atom count. |

### Quenching

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Fallback contact radius (Å) | `critical_distance` | float |  | 0.0 … 50.0 | Contact radius used by residue types that do not define their own quench_radius. It is measured from the dye centre to the residue's quenching centre, so it must exceed the dye radius plus van der Waals contact (typically 7-9 A for a 3.5 A dye). |

### FRET

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| FRET enabled | `fret_enabled` | bool |  |  | Whether a FRET acceptor dye is simulated to compute FRET efficiency and decay curves. |
| Förster radius (Å) | `fret_R0` | float |  | 0.0 … 500.0 | Förster radius R0 of the donor–acceptor pair, in Ångström like every other length in a project. Stored as the donor→acceptor cell of fret.R0_matrix; the transfer rate scales as (R0/r)^6, so entering nanometres makes FRET vanish. Typical xanthene pairs are 45–65 Å. |
| Orientation factor κ² | `fret_kappa2` | float |  | 0.0 … 4.0 | Orientation factor κ² of the transfer, between 0 (perpendicular transition dipoles) and 4 (collinear). QuEst does not model it: the dye is a point diffusing in a volume and has no dipole to orient, so this is the averaging regime you are asserting. The default 2/3 is the isotropic dynamic average, which is what a published Förster radius already assumes — leaving it there reproduces the rate exactly. Raise it only with evidence that both dyes are orientationally restricted. |
| Acceptor chain | `acceptor_chain` | str |  |  | Chain identifier of the residue where the FRET acceptor dye is attached. |
| Acceptor residue | `acceptor_residue` | int |  | -100000 … 100000 | Residue sequence number where the FRET acceptor dye is attached. |
| Acceptor atom | `acceptor_atom` | str |  |  | Atom name where the FRET acceptor dye is attached. |
| Acceptor linker length (Å) | `acceptor_linker_length` | float |  | 0.0 … 200.0 | Maximum distance from attachment point to the center of the FRET acceptor dye. |
| Acceptor linker width (Å) | `acceptor_linker_width` | float |  | 0.0 … 50.0 | Width of the linker tethering the FRET acceptor dye. |
| Acceptor dye radius (Å) | `acceptor_radius1` | float |  | 0.0 … 50.0 | Exclusion radius representing the FRET acceptor dye sphere. |
| Acceptor diffusion coefficient (Å²/ns) | `acceptor_D` | float |  | 0.0 … 1000.0 | Diffusion coefficient of the FRET acceptor dye when not interacting with the protein surface. |
| Acceptor dynamics | `acceptor_dynamics` | choice |  | choices: trajectory, averaged | How the acceptor is treated: 'trajectory' simulates its Brownian walk with its own diffusion coefficient and stickiness and uses the instantaneous donor-acceptor distance, 'averaged' averages over its static accessible volume (the fast-acceptor limit, valid only when it explores that volume quickly compared with the donor lifetime). The two disagree because a cloud is weighted uniformly while a trajectory is weighted by where the dye dwells. |
| Acceptor slowing radius (Å) | `acceptor_slow_radius` | float |  |  | Radius around each amino-acid centre within which that residue slows the acceptor. Separate from the donor's: a cyanine and a rhodamine do not adhere to a protein surface in the same way. Defaults to the donor's value. |

### Advanced

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Parallel trajectories | `parallel_trajectories` | int |  | -1 … 1024 | Number of independent Brownian dynamics trajectories run concurrently and combined before photon sampling. Use -1 to use all CPU cores, capped at 8. |
| Slowing radius (Å) | `slow_radius` | float |  | 0.0 … 50.0 | Radius around each whole-protein amino-acid center where that residue type contributes its slow_factor to the diffusion coefficient grid. |
| Save AV files | `save_avs` | bool |  |  | Whether to save the calculated accessible volume grids as XYZ files. |
| Output file prefix | `output_file` | str |  |  | Base filename prefix used when saving simulation outputs, trajectories, and decays. |
| Trajectory skip frames | `skip_frame` | int |  | 1 … 1000000 | Subsampling factor for writing trajectory frames to coordinates files. |
| Random seed | `random_seed` | int |  | 0 … 2147483647 | Seed for the Monte-Carlo simulation. When set, both the diffusion trajectory and the photon trace are seeded, so repeated runs of the same project reproduce the same decay and quantum yield exactly. Leave unset for an independent random run; the photon trace then uses a faster multi-threaded kernel. |

### Results

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| State | `status` | str |  |  | Outcome of the last simulation. |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `quest.template` | no | Return a minimal valid project, optionally with FRET. |
| `quest.validate` | no | Check a project and report why it is malformed. |
| `quest.simulate` | yes | Run one simulation and return the decay and derived metrics. |
| `quest.scan` | yes | Simulate a set of labeling sites and return one record each. |
| `quest.parameter_catalog` | no | Return the parameter catalog (labels, units, help), optionally translated. |
| `quest.dyes.list` | no | Return the dye presets. |
| `quest.dyes.save` | no | Add or replace a dye preset. |
| `quest.quenching_defaults` | no | Return the residue-type PET chemistry defaults. |
| `quest.structure.metadata` | no | Return the chains, residues and atoms of a structure file. |
| `quest.runs.list` | no | Return run-artefact summaries, newest first. |
| `quest.runs.get` | no | Return a finished run's result. |
| `quest.locales` | no | List the languages QuEst's labels and help text are available in. |
| `quest.contract.describe` | no | Return the contract: methods, schemas, error codes and where serialization happens. |
| `quest.jobs.list` | no | Return the running and recent operations. |
| `quest.jobs.get` | no | Return one operation's status and progress. |
| `quest.jobs.cancel` | no | Ask a running operation to stop at its next checkpoint. |

## Theory and workflow

- **Theory** — [Dye quenching by amino acids: photoinduced electron transfer at contact](/concepts/dye_quenching.md), [Molecular surfaces and solvent accessibility](/concepts/molecular_surfaces.md)
- **Workflow** — [QuEst: predicting dye quenching at a labelling site](/guides/80_quenching_estimator.md)

## Source

- Plugin package: `chisurf/plugins/quenching_estimator/`
- Manifest: {src}`chisurf/plugins/quenching_estimator/manifest.json`
- UI spec: {src}`chisurf/plugins/quenching_estimator/gui/quest.view.json`
