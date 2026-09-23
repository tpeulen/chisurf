---
type: Guide
title: Accessible-volume (AV) calculations
description: 'To turn a FRET distance into a structural restraint you need the mean dye position, not the attachment-point position: a dye on a flexible linker samples a sterically accessible volume (AV) around its attachment site.'
tags: [guides, fret, structure]
---

# Accessible-volume (AV) calculations

:::{admonition} Theory
:class: seealso
The AV grid model, the accessible-contact volume (ACV), the three AV-to-distance
measures ($R_\text{mp}$, $\langle R_{DA}\rangle$, $\langle R_{DA}\rangle_E$), and
the $\kappa^2=2/3$ assumption are covered in the concept page
{ref}`concept-accessible-volume`.
:::

## What it does

To turn a FRET distance into a **structural** restraint you need the mean dye
position, not the attachment-point position: a dye on a flexible linker samples
a sterically **accessible volume** (AV) around its attachment site. Simulating
that volume gives the dye's mean position and the inter-dye distance distribution
$P(R_{DA})$ — which, combined with the [SAW-ν / WLC / Ising](03_polymer_distance_distributions.md)
or Gaussian models, connects a measured efficiency to a structure.

## In ChiSurf

`chisurf/core/structure/av/` implements the standard grid-based AV: a
`BasicAV` samples the volume reachable by a dye of one (`AV1`) or three (`AV3`)
radii on a linker of given length and width, attached to an atom of a loaded
`Structure`; `ACV` adds an accessible-*contact* volume (surface-sticking
fraction) and `DynamicAV` the diffusion-with-quenching variant. The fast kernel
uses the LabelLib backend when available. Given two AVs, the inter-dye distance
distribution and the FRET-averaged distance come straight off the object:

```python
from chisurf.core.structure import Structure
from chisurf.core.structure.av import BasicAV

s = Structure(filename="test/data/atomic_coordinates/pdb_files/148l.pdb")   # T4 lysozyme
kw = dict(linker_length=20.5, linker_width=1.5, radius1=3.5, simulation_type="AV1")
donor    = BasicAV(s, residue_seq_number=27, atom_name="CA", **kw)
acceptor = BasicAV(s, residue_seq_number=95, atom_name="CA", **kw)

p, r = donor.pRDA(acceptor)          # inter-dye distance distribution P(R_DA)
rda_e = donor.dRDAE(acceptor, forster_radius=52.0)   # FRET-averaged <R_DA>_E
mean_donor_position = donor.Rmp      # mean dye position (for a structural restraint)
```

The `fps_json_editor` plugin edits FPS-style labelling/AV configurations, the
AV-based decay model (`models/tcspc/av_decay.py`) uses the simulated $P(R_{DA})$
directly in a FRET decay fit, and the FRET-docking tools use AV clouds as
restraints. The coarse-grained dye models for docking come from the external
molecular-modelling framework.

On 148L (residues 27 and 95, CA, AV1 as above) this gives $P(R_{DA})$ on 96
bins with $\langle R_{DA}\rangle = 40.4$ Å and
$\langle R_{DA}\rangle_E = 42.2$ Å ($R_0 = 52$ Å).

### The FPS JSON Editor

**Structure ▸ FRET ▸ FPS JSON Editor.** The toolbar loads/saves a
`*.fps.json` labelling project, **Update** pushes hand edits of the *JSON* tab
back into the tables, **Clear** empties it. Tabs:

- **Positions** — one row per labelling site: **Show**, **Name**, **PDB
  (File/ID)** (a path or a PDB ID), **Chain**, **Res**, **Atom**, **Dye Preset**,
  **Dye Model** (AV1/AV3/…), linker and radii under **Details…**, a **Color**
  and delete. **Compute AVs** computes every populated row (a row also
  recomputes when its site changes); **Save AV MRC** writes the selected AVs as
  density maps. The status line reports each AV's volume and grid points.
- **Distances** — donor/acceptor pairs (**Label 1**, **Label 2**), the distance
  **Type** (`dRDAE` = $\langle R_{DA}\rangle_E$, `dRDA`, `dRmp`, …), the
  measured value and errors under **Details…**, and a **Score set** grouping.
- **FlexFit**, **JSON** (the raw file), **3D View** (the structure with AV
  clouds; OpenGL, not captured offscreen).

```{figure} figures/23_fps_editor.png
:name: fig-23-fps-editor
:width: 100%

**Positions** of the HIV-RT example
(`chisurf/plugins/modelling/fret/examples/fps_hiv_rt/hiv_rt.fps.json`): eight
AV1 sites on the p66/p51 subunits of 1R0A and three AV3 sites on the DNA. The
shipped file names no structure; for the figure each site was pointed at
`protein_1R0A.pdb` (body 0) or `dna.pdb` (body 1), and all 11 AVs were
computed (last: p51_E194C, 16 530.8 Å³, 4898 grid points).
```

```{figure} figures/23_fps_editor_distances.png
:name: fig-23-fps-editor-distances
:width: 100%

**Distances** of the same project: 20 protein–DNA pairs of type `dRDAE`
(the last row is the empty row for adding one).
```

Besides **Load** in the toolbar, the editor window accepts a dropped
`*.fps.json` file from the file manager — the first JSON path dropped anywhere on
the window is loaded. The window also remembers its size and position between
sessions.

## Result

Two accessible volumes (donor, acceptor) simulated on T4 lysozyme (PDB 148L) and
the resulting inter-dye distance distribution $P(R_{DA})$ — the mean distance and
mean FRET efficiency follow directly.

```{figure} figures/av.png
:name: fig-av
:width: 90%

Accessible volumes and the inter-dye distance distribution.
```

## See also

- `chisurf/core/structure/av/` (`BasicAV`, `ACV`, `DynamicAV`, `calculate_1_radius`/`calculate_3_radius`); plugin `modelling/fps_json_editor`; the AV decay model `models/tcspc/av_decay.py`.
- Tool: the **FPS JSON Editor** (`chisurf/plugins/modelling/fps_json_editor/`) and **Structure Tools** (`chisurf/plugins/modelling/structure_tools/`).
