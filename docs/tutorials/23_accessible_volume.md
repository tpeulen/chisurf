# Accessible-volume (AV) calculations

## What it does

To turn a FRET distance into a **structural** restraint you need the mean dye
position, not the attachment-point position: a dye on a flexible linker samples
a sterically **accessible volume** (AV) around its attachment site. Simulating
that volume gives the dye's mean position and the inter-dye distance distribution
$P(R_{DA})$ — which, combined with the [SAW-ν / WLC / Ising](03_polymer_distance_distributions.md)
or Gaussian models, connects a measured efficiency to a structure.

## In ChiSurf

AV sampling lives in `chisurf/core/structure/av/` (static, dynamic and iterated
AV, with the fast C accessible-volume kernel) and the labelling framework in
`chisurf/core/structure/label/`; the molecular-modelling framework
(`IMP.bff.cgdye`) provides the coarse-grained dye models used for docking.

```python
from chisurf.core.structure.av import functions as av

# grid an accessible volume around an attachment atom given linker geometry
cloud = av.calculate_av(structure, attachment_atom,
                        linker_length=20.0, linker_width=4.5, radius=3.5)
mean_position = cloud.mean_xyz
```

The `fps_json_editor` plugin edits FPS-style labelling/AV configurations, and the
AV-based decay model (`models/tcspc/av_decay.py`) uses the simulated $P(R_{DA})$
directly in a FRET decay fit.

## See also

- `chisurf/core/structure/av/`, `chisurf/core/structure/label/`; plugin `modelling/fps_json_editor`.
