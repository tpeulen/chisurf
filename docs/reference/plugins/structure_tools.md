---
type: Plugin Reference
title: Structure Tools
description: 'Unified structure toolbox: FPS JSON Editor, FRET Docking & Screening, QuEst, HydroPro and Trajectory Tools.'
resource: chisurf/plugins/modelling/structure_tools/
tags: [reference, plugins, structure-tools, structure, modelling]
anchor: plugin-structure_tools
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-structure_tools)=
# Structure Tools

Unified structure toolbox: FPS JSON Editor, FRET Docking & Screening, QuEst, HydroPro and Trajectory Tools.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `structure_tools` |
| Menu path | Structure → Modelling → **Structure Tools** |
| Categories | Structure, Modelling |
| Version | 1.0.0 |
| Surfaces | emtk, gui |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Selected restraint

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Label 1 | `d_label1` | choice |  | choices: `label_options` | First position (every position of the Positions tab). |
| Label 2 | `d_label2` | choice |  | choices: `label_options` | Second position; it must differ from the first. |
| Type | `d_type` | choice |  | choices: dRDA, dRDAE, dRMP, pRDA | dRDA: mean R_DA; dRDAE: mean FRET-averaged distance; dRMP: distance of the mean positions; pRDA: a distribution loaded from a file. |
| Score set | `d_set` | choice |  | choices: `set_options` | The scoring group (chi-squared set) that includes the restraint; empty = none. |
| Forster radius (R0, A) | `Forster_radius` | float |  | 0.0 … 999.0 (step 1.0) | Forster radius of the dye pair in angstrom. |
| Distance (d, A) | `distance` | float |  | 0.0 … 999.0 (step 1.0) | The measured distance in angstrom. |
| Error neg (err-, A) | `error_neg` | float |  | 0.0 … 99999.0 (step 0.5) | Lower error of the distance. |
| Error pos (err+, A) | `error_pos` | float |  | 0.0 … 9999.0 (step 0.5) | Upper error of the distance. |

### Structure and attachment

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Chain | `p_chain` | choice |  | choices: `chain_options` | Chain of the attachment atom, from the loaded structure. |
| Residue | `p_res` | choice |  | choices: `residue_options` | Residue of the attachment atom, from the loaded structure. |
| Atom | `p_atom` | choice |  | choices: `atom_options` | Attachment atom, from the loaded structure (CB when the residue has one). |

### Selected position

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| PDB file or ID | `p_pdb` | str |  |  | The structure file of the row, or a four-character PDB ID that is downloaded. Press Enter to load it. |
| Color | `p_color` | color |  |  | Colour of the accessible volume (the transparency stays as it was). |

### Dye

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Dye preset | `p_preset` | choice |  | choices: `preset_options` | A dye definition: sets linker length and width, radii and the model. Custom keeps the values below. |
| Dye model | `p_model` | choice |  | choices: AV1, AV0, AV3, ROTAMER | AV1: one dye radius; AV0: a point dye; AV3: three radii; ROTAMER: rotamer library. |

### Dye dimensions

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Linker length | `linker_length` | float |  | 0.0 … 200.0 (step 1.0) | Length of the flexible linker. |
| Linker width | `linker_width` | float |  | 0.0 … 50.0 (step 0.5) | Width of the linker. |
| Radius 1 | `radius1` | float |  | 0.0 … 50.0 (step 0.5) | First dye radius. |
| Radius 2 | `radius2` | float |  | 0.0 … 50.0 (step 0.5) | Second dye radius (AV3 only). |
| Radius 3 | `radius3` | float |  | 0.0 … 50.0 (step 0.5) | Third dye radius (AV3 only). |

### Simulation

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Body ID | `body_id` | int |  | 0 … 10000 | The rigid body the position belongs to (docking). |
| Allowed sphere | `allowed_sphere_radius` | float |  | 0.0 … 50.0 (step 0.5) | Radius of the sphere around the attachment point where the dye may clash. |
| Grid resolution | `simulation_grid_resolution` | float |  | 0.1 … 10.0 (step 0.1) | Grid spacing of the accessible volume, in angstrom. |
| Anchor atoms | `anchor_atoms` | str |  |  | Atoms the linker is anchored to, if not the attachment atom. |
| Strip mask | `strip_mask` | str |  |  | Atoms removed before the volume is computed. |

### Advanced

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Chain weighting | `chain_weighting` | bool |  |  | Weight the sampled positions by the chain length. |
| Contact thickness | `contact_volume_thickness` | float |  | 0.0 … 50.0 (step 0.5) | Thickness of the contact volume around the surface. |
| Contact trapped | `contact_volume_trapped_fraction` | float |  | -1.0 … 1.0 (step 0.05) | Fraction of dyes trapped in the contact volume; -1 = not used. |
| Min sphere volume | `min_sphere_volume_fraction` | float |  | 0.0 … 1.0 (step 0.05) | Smallest accepted fraction of the sphere volume. |

## Theory and workflow

- **Theory** — [Molecular surfaces and solvent accessibility](/concepts/molecular_surfaces.md)
- **Workflow** — [Accessible-volume (AV) calculations](/guides/23_accessible_volume.md)

## Source

- Plugin package: `chisurf/plugins/modelling/structure_tools/`
- Manifest: {src}`chisurf/plugins/modelling/structure_tools/manifest.json`
- UI spec: {src}`chisurf/plugins/modelling/structure_tools/cards/views/fps_distances.view.json`
- UI spec: {src}`chisurf/plugins/modelling/structure_tools/cards/views/fps_flexfit.view.json`
- UI spec: {src}`chisurf/plugins/modelling/structure_tools/cards/views/fps_positions.view.json`
