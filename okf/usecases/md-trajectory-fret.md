---
type: Reference
title: Use case — FRET observables from an MD trajectory
description: Turn a molecular-dynamics trajectory into the RDA / kappa2 / FRET-rate time series a measured decay can be compared against, in the Traj Tools workspace.
tags: [usecase, structure, trajectory, fret, kappa2, md]
timestamp: '2026-07-28T00:00:00Z'
---

# Use case: FRET observables from an MD trajectory

**Goal:** the simulation side of a FRET experiment. A user has an MD trajectory of
their molecule and wants the observable a measurement can be compared against:
the donor–acceptor distance `RDA(t)`, the orientation factor `κ²(t)` and the
FRET-rate constant `k_RET(t)`, frame by frame, for one labelling pair. It is the
counterpart of [FPS labelling positions](/usecases/fps-labelling-positions.md):
there the dye position is a static accessible volume on one structure, here it is
two atoms followed through a conformational transition.

**Data:** `test/data/atomic_coordinates/trajectory/hgbp1/hgbp1_transition.dcd` —
464 frames of hGBP1 going through its open/closed transition, 5235 atoms, two
chains (A = residues 1–151, B = residues 152–570), frames 1 ps apart.

**Tool:** *Structure → Traj Tools* → the **FRET** tab
(`chisurf.plugins.traj.traj_tools`, panel
`chisurf.plugins.traj.fret_trajectory.gui:Structure2Transfer`). The panel is
AutoForm-rendered from `structure2transfer.view.json`.

## Steps

1. Open **Structure → Traj Tools**. The workspace comes up with eight tabs —
   *Align, Convert, Energy Calc, FRET, Join, Remove Clashed, Rot Translate,
   Save Topol* — and a status bar naming the active one.
2. Click the **FRET** tab.
3. Drag the `.h5` trajectory onto the **Trajectory** field (or press **…** and
   pick it; the filter is `H5-Trajectory-Files (*.h5)`). The tool writes the
   first frame to a temporary PDB and fills the four atom pickers from it.
4. In **Dipole atoms → Donor**, set the *first* dipole atom with the labelled
   Chain / Residue / Atom combos (e.g. `A` / `18` / `CA`) and the *second* dipole
   atom with the three unlabelled combos below it (`A` / `18` / `CB`).
5. Do the same under **Acceptor** (e.g. `B` / `344` / `CA` and `B` / `344` / `CB`).
   The two atoms of each pair define that dye's transition dipole; the distance
   is measured centre-to-centre.
6. In **Parameters**, set **R0 [Ang]** (Förster radius of the real dye pair),
   **τ0 [ns]** (donor lifetime without FRET) and **t-step [ns]** (the time
   between frames of *this* trajectory — 0.001 for a 1 ps trajectory). Leave
   **Dipole (κ2)** ticked to compute the orientation factor from the two atoms.
7. Optionally raise **Stride** to read only every Nth frame of a long trajectory.
8. Press **▶ Process trajectory** and choose the output CSV. The log panel
   reports `Processing 1/1: …` then `Finished … (N frames)`.
9. Open the CSV: one row per processed frame, columns
   `Frame · time[ns] · RDA[Ang] · kappa · kappa2 · FRETrate[1/ns]`.

## Expected

- The distance is the dipole-centre distance in Ångström, and κ² follows the
  relative orientation of the two dipole vectors.
- `FRETrate = 3/2 · κ² · (1/τ0) · (R0/RDA)^6`, so the per-frame transfer
  efficiency is `E = k_RET / (k_RET + 1/τ0)`.
- With **Dipole (κ2)** unticked only the first atom of each dye is used and the
  orientation factor falls back to the isotropic κ² = 2/3.
- A trajectory that cannot be read is reported as such and leaves the panel in
  its previous state.

## Observed (last run: 2026-07-28)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, `arm64` env) through the real
`TrajectoryToolsTool` window: opened the workspace, visited all eight tabs,
dropped the trajectory with a genuine `QDropEvent`, clicked through the twelve
atom combos, set the parameters and pressed **▶ Process trajectory**.
Screenshots at every step.

**The physics that is computed is exact and fast.**

- The workspace opened in 0.39 s; the drop read the topology in 0.92 s; the
  464-frame × 5235-atom trajectory was processed in 0.17–0.72 s on the GUI
  thread, chunked at 1000 frames.
- `RDA` matched an independent mdtraj computation of the same dipole-centre
  distance to **0.0000 Å** over all 464 frames (mean 44.05 Å, 40.26–48.48 Å).
  With the dipole option off it matched the plain first-atom distance to
  0.000 Å. The nm→Å conversion is right.
- κ² ran 0.000–0.662 (mean 0.272) across the transition, `k_RET`
  9.9e-5–1.06 ns⁻¹, i.e. E = 0.00–0.81 (mean 0.45) for R0 = 52 Å, τ0 = 4 ns —
  a plausible spread for a hinge motion.
- **Stride** is honoured correctly: stride 10 gave 47 rows, the `Frame` column
  counting 0…460 in the source file's numbering while `time[ns]` used the
  strided spacing.
- The layout is clean at 1000×640 and at the panel's own 560 px minimum:
  nothing clipped, four collapsible panels, every spin box carries a tooltip.
- The workspace-level drop gives honest feedback — dropping a file on the window
  while the FRET tab is in front says *"FRET takes no dropped file — drop onto
  one of its fields"* rather than swallowing it.
- Two trajectories can be loaded at once and are processed in sequence.

**What a user gets wrong, and is not told about.**

- Unticking **Dipole (κ2)** does not give the isotropic κ² = 2/3 it promises —
  it writes `kappa2 = 0` and therefore `FRETrate = 0` for **every frame**
  (verified: all 464 rates exactly 0.0, against 0.7655 ns⁻¹ expected at
  κ² = 2/3). "No dipole averaging" silently becomes "no FRET at any distance".
  → **RF-676**
- Immediately after a trajectory is loaded, **all four atom pickers sit on the
  same atom** (the first atom of the first residue of whichever chain the combo
  happened to list first). Donor and acceptor are then the same atom and both
  dipoles are degenerate. Pressing **▶ Process trajectory** at that point writes
  464 rows of `nan nan nan nan` and the log says
  `Finished … (464 frames)` — the run reads as a success. → **RF-677**
- Dropping a file that is not a readable trajectory throws the HDF5 error out of
  the Qt drop handler while the log records *"Loaded 1 trajectory file(s)"*, the
  field is left blank (or, worse, still showing the *previous* trajectory) and
  the model quietly points at the unreadable file. → **RF-678**
- The chain drop-down is built from a Python `set`, so its order — and hence the
  default selection — changes between runs of the same file: chain `B` came
  first in three of four runs and `A` in the fourth. → **RF-679**
- **t-step [ns]** stays at its 1.000 default even though the tool has just
  opened the file and could read the 1 ps frame spacing from it; a user who does
  not override it gets a `time[ns]` column 1000× too long. → **RF-680**
- The plugin README advertises FRET-efficiency histograms, time traces,
  accessible-volume dye models and structure visualisation. None of them exist
  in the panel. → **RF-681**

## UX / UI suggestions

- **Show the result.** The panel computes a 464-point `RDA(t)` / `κ²(t)` /
  `k_RET(t)` series, writes it to disk and shows the user nothing. A chiplot
  trace of RDA and κ² against time, plus an E histogram, is the whole point of
  the tool — it is what a user then compares with a measured FRET histogram.
  Right now the only way to see the answer is to open the CSV elsewhere.
- **Give the second dipole atom a label.** The Donor group is three labelled
  combos followed by three unlabelled ones; nothing on screen says the lower row
  is "the second atom of the donor dipole". Label the two rows *Atom 1* /
  *Atom 2*, or caption them *dipole start* / *dipole end*.
- **Add an `E` column** (and a `kappa2`-averaged ⟨E⟩ line in the log). Every
  consumer of this table computes `E = k/(k+1/τ0)` by hand.
- **Write the parameters into the output.** The CSV records neither R0, τ0,
  t-step, stride nor the four atom indices, so a `FRETrate` column cannot be
  interpreted a week later. A commented header block would fix it.
- **Say where the file went.** The log ends with `Finished … (464 frames)` and
  never names the CSV it just wrote.
- **Offer the trajectory's frame spacing.** After loading, either prefill
  **t-step** from the file or display "file: 464 frames, 1 ps apart" next to the
  path, so the units question is answered where it is asked.
- **Naming the multi-file outputs.** Two trajectories with output `multi.csv`
  produce `multi.csv.1.csv` and `multi.csv.2.csv`. Insert the index before the
  extension instead.
- **Stale status bar.** The workspace status bar still showed the drop-routing
  message *"FRET takes no dropped file …"* long after the trajectory had been
  loaded and processed; it never reports what the active panel is doing.
- **Docs gap.** There is no `docs/concepts/` page and no numbered
  `docs/guides/` workflow for MD→FRET, although the project rule requires a
  plugin to be documented in theory and in application. The theory (κ² from two
  dipole atoms, the Förster rate, when a per-frame κ² is preferable to the
  isotropic assumption) is exactly the part a user needs and it is written
  nowhere.

## Bugs filed

- **RF-676** — unticking *Dipole (κ2)* writes `FRETrate = 0` for every frame
  instead of using the documented κ² = 2/3 fallback.
- **RF-677** — after loading, all four dipole pickers default to one and the
  same atom; *Process* then writes an all-NaN table and reports success.
- **RF-678** — a trajectory that fails to load leaves the panel and the model out
  of step, and the log records the failed load as *"Loaded 1 trajectory file(s)"*.
- **RF-679** — the chain drop-down order (and therefore the default atom
  selection) is not deterministic between runs.
- **RF-680** — the trajectory's own frame spacing is never read into **t-step**.
- **RF-681** — the plugin README documents outputs and dye models the tool does
  not have.
