---
type: Guide
title: Sampling a protein under FRET distance restraints
description: 'Tool: Protein Monte Carlo (proteinmc), a command-line plugin with no menu entry. Samples torsion-angle conformations of a structure that satisfy FPS distance restraints and writes them as an RMF3 trajectory.'
tags: [guides, sampling, fret, plugins, structure]
---

# Sampling a protein under FRET distance restraints

**Tool:** Protein Monte Carlo (`proteinmc`), `csc proteinmc`. Its manifest is menu-hidden and it has no window: it is a
command and a Python runner. **What you get:** an RMF3 trajectory of conformations, and per frame the total
energy, the restraint $\chi^2$ and the RMSD to the start. Theory: [Protein Monte Carlo](../concepts/protein_monte_carlo.md).

## 1. What you need

- A structure: a local PDB or PQR file, or a four-character PDB id (fetched from the RCSB).
- Optionally an FPS labeling file (`.fps.json`) with `Positions` and `Distances`, for example from the
  [FPS JSON editor](44_molecular_viewer.md). Without one the walk is driven by the structural potentials alone.

## 2. Run it

```bash
csc proteinmc 148l.pdb -l restraint.fps.json -o run.rmf3 --n-iter 4000 --n-out 5 --n-written 200 --scale 0.05
```

| Option | Meaning |
|---|---|
| `STRUCTURE` | PDB/PQR path or PDB id |
| `-l`, `--labeling-file` | FPS JSON; adds the restraint potential with weight 1 |
| `-s`, `--settings-file` | JSON that overrides the `mc_settings` of the ChiSurf settings |
| `-o`, `--output` | trajectory file; a temporary `.rmf3` when omitted. The command prints the path |
| `--n-iter` | total trials |
| `--n-out` | accepted moves between two written frames |
| `--n-written` | stop after this many written frames |
| `--scale` | torsion step size |
| `--eval-interval` | evaluate the restraint every N steps (1 = every step) |
| `-v` | detailed progress |

The run ends at `--n-iter` trials or `--n-written` frames, whichever is first. The settings file takes the keys of
`mc_settings` in the ChiSurf settings: `kt`, `scale`, `n_iter`, `n_out`, `pdbOut`, `pPhi`, `pPsi`, `pOmega`,
`pChi`, `move_map` and `potentials`, a list of `{"name", "weight", "eval_interval", "settings"}` entries with the
names listed in the [theory page](../concepts/protein_monte_carlo.md#energy). A settings file without
`potentials` runs the restraint potential only; add the entries to use the structural potentials.

## 3. Python

```python
from chisurf.plugins.modelling.proteinmc.model import ProteinMCRunner

runner = ProteinMCRunner(
    "148l.pdb",
    settings={"n_iter": 4000, "n_out": 5, "n_written": 200, "scale": 0.05, "kt": 1.5,
              "potentials": [{"name": "dye", "weight": 1.0,
                              "settings": {"labeling_file": "restraint.fps.json"}}]},
    output_file="run.rmf3",
)
result = runner.run()
result.labeling_energies   # restraint chi-square per written frame
result.rmsd                # RMSD to the start structure
result.accepted, result.rejected
```

`progress_callback` receives a `ProteinMCProgress` after each written frame; `runner.stop()` ends the loop.
`flexfit_set` selects the `FlexFit` set of the labeling file that defines which residues move.

## 4. Read the result

```{figure} figures/106_protein_monte_carlo.png
:name: fig-protein-monte-carlo
:width: 70%

T4 lysozyme (148L), one restraint pulling the CA atoms of two residues 15 Å closer, error 1 Å. The restraint
$\chi^2$ falls from 225 to a few within 200 frames while the structure drifts 8 Å (RMSD) from the start.
Figure script: `docs/guides/screenshots/proteinmc_run.py`.
```

Check that the restraint $\chi^2$ reaches about the number of distances and stays there; a plateau far above
means the restraint cannot be met with the moves allowed (a restricted move map, a step too small, too few
trials). The RMSD shows how far the walk went; it keeps rising while the walk is still exploring. Open the RMF3
in the [molecular viewer](44_molecular_viewer.md) to look at the frames. Writing RMF needs an RMF-enabled
`IMP.bff` build; where it is missing the run fails when it opens the output.

## Theory

[Protein Monte Carlo: torsion-angle sampling under distance restraints](../concepts/protein_monte_carlo.md).
Tool: Protein Monte Carlo (`chisurf/plugins/modelling/proteinmc/`).
