---
type: Reference
title: Use case — preparing an MD trajectory for FRET analysis
description: The Traj Tools bench a user works through before any structural FRET analysis — topology export, superposition, clash filtering, placement, joining, format conversion and an energy check.
tags: [usecase, structure, trajectory, md, preparation, traj-tools]
timestamp: '2026-07-28T00:00:00Z'
---

# Use case: preparing an MD trajectory for FRET analysis

**Goal:** the housekeeping that comes *before*
[FRET observables from an MD trajectory](/usecases/md-trajectory-fret.md). A
simulation lands on disk as a raw trajectory; before `RDA(t)` or `κ²(t)` mean
anything the user has to know what is in the file, take the global tumbling out
of it, throw away the frames the integrator broke, put it in a common frame of
reference, stitch the runs together, hand a copy to another program in that
program's format, and sanity-check the result. All seven of those live in the
same window as the FRET tab, one tab each — this use case walks them in the
order a user actually needs them.

**Data:** `test/data/atomic_coordinates/trajectory/hgbp1/hgbp1_transition.dcd`
— 464 frames of hGBP1 through its open/closed transition, 5235 atoms, 570
residues, 2 chains (A = 1–151, B = 152–570). Note the file's own `time` array is
**not monotonic** (it runs 0…249 and restarts), so it is a good specimen for
checking what the tools do to the time axis.

> **Changed 2026-08-06 ([PRD-80](/prds/prd-80.md)).** This walkthrough was
> taken while the tools read and wrote mdtraj HDF5. They now read **DCD/XTC**
> and write **DCD**, and a trajectory is **two files**: DCD and XTC store
> coordinates and nothing else, so every tab has a **Topology** row beside the
> trajectory one. Read `.h5` below as `.dcd`, and *"Topology is optional"* as
> *"Topology is required"*. The UX findings further down were re-checked and
> still stand except where struck.

**Tool:** *Structure → Traj Tools* (`chisurf.plugins.traj.traj_tools`,
`gui.tool:TrajectoryToolsTool`). Eight tabs — *Align, Convert, Energy Calc,
FRET, Join, Remove Clashed, Rot Translate, Save Topol* — each an AutoForm panel
over a Qt-free view-model, all sharing the same shape: a trajectory row that
takes a drop or a `…` browse, the tool's parameters, one `💾`/`▶` action button,
and a timestamped log. A file dropped anywhere on the window goes to the tab in
front; the status bar names the active tab.

## Steps

1. Open **Structure → Traj Tools**. It comes up on **Align**, status bar
   *"Active tool: Align"*.
2. **Save Topol** — click the tab, drop the `.h5` on the window, press
   **💾 Save topology…** and give it `topology.pdb`. This is the file every other
   program (and the Convert tab) will want as the topology, and reading it is
   how you learn the chain/residue numbering the FRET tab's atom pickers use.
3. **Align** — click the tab, drop the same `.h5`, type the reference atom set
   into **Atom selection** as a comma-separated list of atom **ids** (e.g. the
   200 backbone `CA` indices), set **Stride** (32 for a quick pass), press
   **💾 Save aligned…** → `aligned.dcd`. Every frame is superposed onto frame 0.
   **Leaving Atom selection empty destroys the trajectory — see RF-706.**
4. **Remove Clashed** — drop the trajectory, keep or edit the selection
   expression (**not** the same syntax as Align's field — default
   `name CA and resSeq 1 to 256`), set **Min distance** in Ångström (default
   2.85), press **💾 Save clash-free…**. Frames in which any selected atom pair
   is closer than that are dropped.
5. **Rot Translate** — drop the trajectory, type the 3×3 **Rotation matrix** and
   the **Translation [Ang.]** row, press **💾 Save rotated/translated…**. Used to
   put an independently simulated partner into a common frame.
6. **Join** — put two trajectories in **Trajectory 1** / **Trajectory 2**, pick
   **By time (append frames)** or **By atoms (stack)**, optionally reverse either
   in time, set the read **Chunk size**, press **💾 Save joined…**.
7. **Convert** — fill **Topology** (the PDB from step 2; optional for `.h5`),
   **Trajectory**, **Target folder**, then the frame range (**First / Last /
   Stride**), the output base **Filename**, the **Format** combo
   (`.dcd/.xtc/.pdb/.h5`) and optionally *Split into one file per frame*; press
   **▶ Convert**.
8. **Energy Calc** — put the prepared trajectory in the **Trajectory** field
   (its own field only — the window-level drop is refused here, RF-709), pick a
   potential from the combo (H-Bond, AV-Potential, Iso-UNRES,
   Miyazawa-Jernigan, Go-Potential, ASA-Calpha, Radius of Gyration, Clash
   potential, Ramachandran), set its parameters and **Weight**, press
   **➕ Add**, repeat, then **⚙️ Process** and save the per-frame energy table.

## Expected

- Step 2: a single-frame PDB with the full 5235 atoms / 570 residues / 2 chains.
- Step 3: an `.h5` with `ceil(464/stride)` frames whose deviation from frame 0,
  measured on the reference atoms *without* re-superposing, equals the RMSD of
  the source — i.e. the rigid-body motion is gone and nothing else changed.
- Step 4: a trajectory with the clashing frames missing and a count of what was
  dropped.
- Step 5: coordinates transformed by exactly `R·x + t/10` (the field is Å, the
  file is nm).
- Step 6: by time → `n1 + n2` frames at the same atom count; by atoms → `n`
  frames at `a1 + a2` atoms; mismatched topologies → a clear error, no file.
- Step 7: the requested frames in the requested format in the target folder.
- Step 8: a tab-separated table, one row per frame, one column per added
  potential.

## Observed (last run: 2026-07-28)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, arm64 env) against the hGBP1
trajectory, every tab visited and screenshotted, every output file re-loaded
with mdtraj and checked numerically.

**What is right.** The bench is coherent: eight panels with one identical
idiom, so learning one teaches the rest. The numbers that come out are correct
where they come out at all.

- **Save Topol** — instant; `topology.pdb` reloads as 1 frame / 5235 atoms /
  570 residues / 2 chains. Pressing the button with no trajectory raises a clean
  *"No trajectory — Open a trajectory first."* and writes nothing.
- **Align** with 200 explicit `CA` ids, stride 32 → 15 frames, no NaN, 0.4 s.
  The superposition is exact: raw deviation from frame 0 on the reference atoms
  fell from `0.089 / 0.194 / 0.284 / 0.589 nm` (source) to
  `0.085 / 0.156 / 0.130 / 0.133 nm`, matching `mdtraj.rmsd` to 3 decimals.
- **Remove Clashed** at the default 2.85 Å kept 15/15 frames of the strided
  trajectory in 0.5 s — correct, since consecutive Cα are ~3.8 Å apart.
- **Rot Translate** is exactly right in both halves. A typed translation of
  `10.0` Å along x moved every atom by `[1. 0. 0.]` nm; a typed 90° z-rotation
  sent `(7.0639, −1.3604, 0.3497)` to `(1.3604, 7.0639, 0.3497)`, which is
  `(−y, x, z)` to the last digit. The `[Ang.]` in the label is honoured.
- **Join** — by time: 15 + 15 → 30 frames × 5235 atoms; by atoms: 15 frames ×
  10470 atoms. Both in 0.4 s. Handing it two trajectories with different atom
  counts produced a proper modal *"Join failed — Number of atoms in self (5235)
  is not equal to number of atoms in other"* and left no half-written file.
- **Convert** — `.h5 → .dcd` wrote 15 frames reloadable against the topology;
  frames `2:6 stride 2 → .pdb` wrote exactly the 2 frames asked for. 0.2 s.
- **Energy Calc** — *Radius of Gyration* + *Clash potential* over 15 frames in
  1.5 s, writing a clean `FrameNbr / Radius-Gyration / Clash-Potential` table
  (Rg ≈ 39 Å for hGBP1, plausible). The panel is the best-labelled of the eight:
  each potential swaps in its own parameter row.

**What is wrong.** Three of the seven tools mis-report their own result, and one
of them does it on the default path:

- **The Align tab's default configuration silently destroys the trajectory.**
  The field's own placeholder reads *"e.g. 0, 1, 2, 3 (empty = all atoms)"*, so
  drop-a-file-and-press-save is the obvious first thing to do. Doing it wrote an
  `.h5` that is **100 % NaN** — 235 575 of 235 575 coordinates — while the log
  said *"Aligned trajectory saved"* with no warning of any kind. Only stray
  `Mean of empty slice` / `invalid value encountered in divide` runtime warnings
  on the terminal hint at it, and a GUI user never sees those. Filed **RF-706**.
- **Remove Clashed will happily write an empty trajectory and call it saved.**
  With **Min distance** at 50 Å (a plausible fat-finger, the box accepts up to
  100) every frame clashes; the log still reads *"Clash-free trajectory saved"*
  and the file on disk has **0 frames**. Neither the success case nor the
  failure case reports how many frames were kept — 15/15 and 0/15 produce the
  same message. Filed **RF-707**.
- **Align and Rot Translate throw the time axis away.** Both write
  `time = 0, 1, 2, …` regardless of what the source said and regardless of the
  stride: the source strided by 32 carries `0, 32, 64, 96, 128`, the output
  carries `0, 1, 2, 3, 4`. A trajectory subsampled 32× therefore claims unit
  frame spacing, and anything downstream that reads `t` — the FRET tab's
  `RDA(t)`, any rate fitted from it — reads a 32×-wrong time base with nothing
  on screen to say so. Filed **RF-708**.
- **Energy Calc is the one single-trajectory tab that refuses a window drop.**
  Dropping the file on the window yields *"Energy Calc takes no dropped file —
  drop onto one of its fields"*, because it exposes `trajectory_file` while the
  window routes to `trajectory_filename`. Align, Remove Clashed, Rot Translate
  and Save Topol all accept it. Filed **RF-709**.
- The Convert tool's completion dialog is titled **"MC-Converter"** — a typo for
  MD-Converter, which is what the module docstrings, the class and the tab all
  say. Filed **RF-710**.

## UX / UI suggestions

- **"Atom selection" means two different things in adjacent tabs.** Align wants
  a comma-separated list of integer atom **ids**; Remove Clashed wants an
  **selection expression** (`name CA and resSeq 1 to 256`, now parsed by
  `core/structure/selection.py`). Same label,
  same oversized multi-line box, incompatible syntax — and pasting one into the
  other fails silently in Align (see RF-706) rather than erroring. Rename to
  *"Reference atom ids"* vs *"Atom selection (expression)"*, or better, give
  both tabs the expression and translate it internally.
- **Give the Align/Remove-Clashed atom box one line, not eight.** It eats a
  third of the panel for what is normally a short entry, pushing the log — the
  only place the tool tells you anything — into the leftovers.
- **Put the unit in the label.** *Min distance* is in Ångström (the tooltip says
  so, the value is `/10`-converted internally) but the label does not; *Rot
  Translate* gets this right with *Translation [Ang.]*. Also *Stride* would read
  better as *Read every Nth frame*.
- **Report counts, not just "saved".** Every one of the four `💾` tools ends with
  a bare *"<thing> saved: <path>"*. `Aligned 15/464 frames (stride 32) → …` and
  `Kept 12 of 15 frames, removed 3 clashed` would have made two of the three
  bugs above visible from the panel.
- **No progress on the long operations.** Align, Remove Clashed, Join and
  Convert all run synchronously in the GUI thread. On this 464-frame / 5 k-atom
  file everything was sub-second, but these tools exist for trajectories that do
  not fit in memory (the code streams in 1000-frame chunks precisely for that),
  and there the window simply stops repainting. Traj Tools should use the shared
  `ChiSurfProgress` the rest of the tree now has.
- **The Convert tab's three file rows have no placeholder text**, unlike every
  other tab's *"Drop a trajectory here or browse…"*. A user cannot tell they
  are drop targets. ~~nor that **Topology** is optional when the input is
  `.h5`~~ — resolved: the input is DCD/XTC, topology is always required, and
  every tab now has its own labelled Topology row with a placeholder saying so.
- ~~**`mdconvert`'s own progress goes to the terminal.**~~ Resolved: the
  shell-out to an external converter is gone -- it was this same read/write loop
  with an `argv` in the middle -- and the counts land in the panel log where the
  finding asked for them (`Wrote 15 frames of 5235 atoms`, verified headlessly
  at stride 32). The output-format list lost `.xtc` and `.h5` at the same time:
  neither can be written, and offering an unwritable format in a combo box turns
  a wrong pick into a traceback after the user has chosen a directory and a
  name.
- **Convert is the only tab that pops a modal on success** (*"Conversion
  done!"*) *and* logs it; the other seven only log. Pick one.
- **Energy Calc's added-potentials table is column-sized backwards** — the
  *Potential* column gets ~90 px and elides the names to *"Radius of ..."* /
  *"Clash ..."*, while *Weight*, which holds `1.0`, gets ~700 px.
- **The status bar keeps stale messages.** It still read *"Energy Calc takes no
  dropped file…"* long after a successful Process; the last thing that happened
  should win.
- **The tab bar overflows at the window's own default size.** At the shipped
  850×520 (and still at 900 px) the eighth tab renders as *"Save Top"* behind a
  scroll arrow. Either shorten the labels (*Clashes*, *Move*, *Topology*) or
  make the window wide enough for its own tab bar.
- **The eight tabs are unordered alphabetically, not by workflow.** A user meets
  *Align, Convert, Energy Calc, FRET, Join, Remove Clashed, Rot Translate, Save
  Topol* — the order in which they are needed is roughly the reverse. Ordering
  them as a pipeline (inspect → align → filter → place → join → convert →
  analyse) would teach the workflow for free.

## Bugs filed

- RF-706 — Align with the default empty atom selection writes an all-NaN
  trajectory and reports success.
- RF-707 — Remove Clashed writes a 0-frame trajectory and reports success; no
  kept/removed count in any case.
- RF-708 — Align and Rot Translate replace the time axis with a frame counter,
  ignoring the source times and the stride.
- RF-709 — Energy Calc refuses the window-level file drop although it has a
  single trajectory field.
- RF-710 — the Convert tool's dialogs are titled "MC-Converter".

## See also

- [FRET observables from an MD trajectory](/usecases/md-trajectory-fret.md) —
  the FRET tab of the same window, i.e. what this preparation feeds.
- [FPS labelling positions](/usecases/fps-labelling-positions.md) — the static,
  single-structure counterpart.
