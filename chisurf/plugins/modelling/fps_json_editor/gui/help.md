# FPS JSON Editor

Build and edit a labelling plan (`*.fps.json`): where the dyes sit on a structure
(**positions**) and which FRET distances were measured between them
(**distances**). The editor is ChiMOL's **Labelling network** window; every
accessible volume (AV) it computes is an object of the viewer it sits in.

## The window

| Part | What it does |
|---|---|
| Header | **Load…**, **Save**, **Save as…**, **Clear** act on the plan file. |
| Network | The plan as a circle: chains on the rim, positions as dots, distances as chords. |
| Positions | One row per labelling site: structure, chain, residue, atom, dye model and the computed AV. |
| Distances | Pairs of positions, the distance type (`dRDAE`, `dRDA`, `dRMP`, `pRDA`), R₀ and the measured value. |
| FlexFit, JSON | Flexible residues and bonds; the raw file, with **Apply** for hand edits. |

## Typical path

Load a structure, **Add Row** for each labelling site, walk it along the chain
with **Residue ▶** until the AV sits where the dye can reach, **Compute AVs**,
add the measured distances on the *Distances* tab and **Save as…**. Every button
is also a ChiMOL command (`fps_position`, `fps_step`, `fps_compute`,
`fps_distance`, …), so a plan can be scripted.

## What to check

- An AV that is empty or tiny means the attachment atom is buried: choose another
  site rather than shrinking the linker.
- The distance **type** must match what the experiment measured — the
  FRET-averaged distance (`dRDAE`) is not the distance between the mean dye
  positions (`dRMP`).

## Further reading

- [Accessible-volume modelling](docs/concepts/accessible_volume.md)
- [Accessible volumes and the FPS JSON editor](docs/guides/23_accessible_volume.md)
- [FRET docking](docs/guides/88_fret_docking.md)
- {cite}`kalinin2012`
