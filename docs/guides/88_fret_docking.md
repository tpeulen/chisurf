---
type: Guide
title: 'FRET docking and pair selection'
description: 'Tool: Structure → FRET → Docking & Screening.'
tags: [guides, structure, fret, docking]
---

# FRET docking and pair selection

**Tool:** *Structure → FRET → Docking & Screening*. One window with two tools in the list on the left:
**Docking & Screening** places rigid bodies against measured FRET distances and ranks structure libraries; **Pair
Selection** chooses the label pairs that tell the conformations of a trajectory apart. Each keeps its state while the
other is shown and has its own **Guide** and **Help**.

The restraints are an `fps.json` plan: build it in ChiMOL's labelling window (*Structure → FRET → FPS JSON Editor*,
see the [accessible-volume guide](23_accessible_volume.md)). Theory of the accessible volumes behind the restraints:
[accessible volumes](../concepts/accessible_volume.md).

## 1. Docking and screening

```{figure} figures/88_docking_results.png
:width: 100%

**Load example**, Runs 3, Iterations 60, **Run**: three docking runs of the HIV reverse transcriptase and its DNA
against 20 distances. The tool list is on the left, the inputs in the middle, the results sorted by score on the right.
```

1. **Load example** copies the shipped HIV reverse-transcriptase project (`protein_1R0A.pdb`, `dna.pdb`, the
   `hiv_rt.fps.json` with 20 measured distances and `docking_project.json`) into the settings demo folder and fills
   every input; a run then writes there, never into the installed package. **Project** loads a project of your own.
2. **Add Files** (or drop .pdb files, or **Database** for structures in the MMFDB): one structure per rigid body;
   the row number is the body id.
3. **fps.json** chooses the restraints; **Output** the folder (default `dock_out` next to the fps.json).
4. **Op** (dock, refine, screen, score), **Method** (minimize, mc), **Runs** above 1 repeats from random starts.
5. **Run**; the bar shows progress and the best score, **Stop** ends it. Results are rows of the sortable **Results**
   table; the **Score** tab plots the trace per trial, the **Structure** tab the selected result in the ChiMOL viewer,
   as cartoon (**Previous** / **Next** step through several models).

Headless: `csc fret imp dock-project --project docking_project.json`, or the RPC methods `fret.dock`, `fret.refine`,
`fret.score`, `fret.screen`.

## 2. Pair selection

Choose a trajectory (and a topology for a DCD), optionally an fps.json whose positions are the candidate sites, the
Förster radius and the number of pairs; **Run selection** adds pairs one at a time, each the pair that most reduces
the mean RMSD between the conformations the chosen pairs cannot yet distinguish. The table lists the pairs in order
with the RMSD after each, the plot shows its decay, **Export** writes the table.

## Related

- [QuEst](80_quenching_estimator.md) (*Structure → Computation → QuEst*), [HydroPro](79_hydropro.md)
  (*Structure → Computation → HydroPro*), [trajectory tools](81_trajectory_tools.md) (*Structure → Trajectory →
  Traj Tools*).
