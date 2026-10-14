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

`chisurf/core/structure/av/` wraps the grid-based AV of `IMP.bff`: a
`BasicAV` samples the volume reachable by a dye of one (`AV1`) or three (`AV3`)
radii on a linker of given length and width, attached to an atom of a loaded
`Structure`; `ACV` adds an accessible-*contact* volume (surface-sticking
fraction) and `DynamicAV` the diffusion-with-quenching variant. Given two AVs, the inter-dye distance
distribution and the FRET-averaged distance come straight off the object:

```python
from chisurf.core.structure import Structure
from chisurf.core.structure.av import BasicAV

s = Structure(filename="test/data/atomic_coordinates/pdb_files/148l.pdb")   # T4 lysozyme
kw = dict(linker_length=20.5, linker_width=1.5, radius1=3.5, simulation_type="AV1")
donor    = BasicAV(s, residue_seq_number=27, atom_name="CA", **kw)
acceptor = BasicAV(s, residue_seq_number=95, atom_name="CA", **kw)

p, r = donor.pRDA(acceptor)          # inter-dye distance distribution P(R_DA)
rda = donor.dRDA(acceptor)           # <R_DA>
rda_e = donor.dRDAE(acceptor, forster_radius=52.0)   # FRET-averaged <R_DA>_E
rmp = donor.dRmp(acceptor)           # distance between the mean dye positions
mean_donor_position = donor.Rmp      # mean dye position (for a structural restraint)
```

ChiMOL's labelling window (**Structure ▸ FRET ▸ FPS JSON Editor**) edits FPS-style
labelling/AV plans, the structure-ensemble FRET decay model
({src}`chisurf/core/models/tcspc/fret_structure.py`) fits the simulated
$P(R_{DA})$ of each structure directly, and the FRET-docking tools use AV clouds as
restraints. The coarse-grained dye models for docking come from the external
molecular-modelling framework.

On 148L (residues 27 and 95, CA, AV1 as above) this gives $P(R_{DA})$ on 96
bins, $R_\text{mp} = 40.4$ Å, $\langle R_{DA}\rangle = 44.1$ Å and
$\langle R_{DA}\rangle_E = 45.2$ Å ($R_0 = 52$ Å).

### The FPS JSON editor (ChiMOL's labelling window)

**Structure ▸ FRET ▸ FPS JSON Editor** opens ChiMOL with its **Labelling network**
window on the *Positions* tab; inside ChiMOL it is **Tools ▸ Labelling ▸ Labelling
network…**.
The editor is a plugin of ChiMOL, so every accessible volume it computes is an
object of the viewer it sits in: a cloud with its mean position, shown, hidden,
coloured and saved like any other object, and a line per distance. Its header
**Load…**, **Save**, **Save as…**, **Clear** (asks first), **Guide** and **?**
act on the `*.fps.json` plan. Tabs:

- **Network** — the plan as a circle: chains on the rim, positions as dots,
  distances as chords coloured by the FRET efficiency at the declared distance
  and Förster radius.
- **Positions** — one row per labelling site: **Show**, **Name**, **Structure**,
  **Chain**, **Res**, **Atom**, **Dye Preset**, **Dye Model** (AV1/AV0/AV3/ROTAMER),
  **Cloud colour** and the computed **AV** volume. Selecting a row opens its form
  under the table: attachment lists read from the structure, dye preset and model,
  colour, the dye dimensions (linker length and width, three radii), and the
  folded **Simulation** (body id, allowed sphere — shown as FPS's 0.5 × linker
  width until declared —, grid resolution, anchor atoms, strip mask, obstacle
  radius scale) and **Advanced** panels. **Add Row**, **Delete Row(s)** (Ctrl/Shift
  select several; asks once, the distances that use them go too), **Delete AV(s)**,
  **Attach to selection**, **Browse PDB…**, **Fetch PDB…** (a 4-character RCSB ID),
  **◀ Residue** / **Residue ▶**, **Compute AVs** (a row also recomputes when its
  site changes) and **Save AV MRC…**.
- **Distances** — **Label 1**, **Label 2**, **Type** (`dRDAE` = $\langle R_{DA}\rangle_E$,
  `dRDA`, `dRMP`, `pRDA`), $R_0$, the measured value and errors, a **Score set**,
  the scoring-group filter with **Add / Remove Scoring Group**, and **Load DA
  Distribution…** for a `pRDA` restraint.
- **FlexFit** (sets of flexible residues and bonds) and **JSON** (the raw file;
  **Apply** pushes hand edits back).

```{figure} figures/23_fps_editor.png
:name: fig-23-fps-editor
:width: 100%

**Positions** of the HIV-RT example
(`chisurf/plugins/modelling/fret/examples/fps_hiv_rt/hiv_rt.fps.json`): eight
AV1 sites on the p66/p51 subunits of 1R0A and three AV3 sites on the DNA. Each
site names its structure relative to the file (`protein_1R0A.pdb`, `dna.pdb`,
both shipped beside it), so **Load…** computes all 11 AVs as the file is.
```

```{figure} figures/23_fps_editor_distances.png
:name: fig-23-fps-editor-distances
:width: 100%

**Distances** of the same plan: 20 protein–DNA pairs of type `dRDAE`.
```

```{figure} figures/23_fps_editor_network.png
:name: fig-23-fps-editor-network
:width: 100%

**Network** of the same plan: the 11 positions on the rim of their chains, the 20
distances as chords.
```

A `*.fps.json` dropped on the ChiMOL window, or `load plan.fps.json` at its
prompt, opens the plan in the same window. Every control is also a ChiMOL
command (`fps_circle`, `fps_position`, `fps_step`, `fps_compute`, `fps_distance`,
…), so a plan can be built from a script.

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

- `chisurf/core/structure/av/` (`BasicAV`, `ACV`, `DynamicAV`, computed by `IMP.bff`); plugin `modelling/fps_json_editor`; the structure-ensemble decay model `chisurf/core/models/tcspc/fret_structure.py`.
- Tool: the **FPS JSON Editor** entry (`chisurf/plugins/modelling/fps_json_editor/`) opens ChiMOL's labelling window (`chimol.plugins.labelling`); the headless payload validation, PDB fetch, CLI and RPC stay in that plugin.
