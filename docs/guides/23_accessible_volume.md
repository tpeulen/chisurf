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

s = Structure(filename="protein.pdb")
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
