---
type: Guide
title: 'Trajectory tools: align, convert, filter, score and FRET a structure ensemble'
description: The eight panels of Traj Tools — superposing a trajectory, converting and slicing it, joining two, removing clashed frames, rigid-body transforms, extracting a topology, per-frame energies, and per-frame FRET distances, orientation factors and rates — worked on the T4 lysozyme ensemble that ships with ChiSurf.
tags: [guides, structure, trajectory, fret]
---

# Trajectory tools: align, convert, filter, score and FRET a structure ensemble

A molecular-dynamics run, a normal-mode ensemble or a docking screen produces a
trajectory: many frames of one molecule. **Traj Tools** is a set of small tools
for preparing such a trajectory for FRET work. They superpose it, cut it, remove
frames that cannot exist, score frames, and write the donor–acceptor geometry of
every frame to a table.

Each tool reads a trajectory, writes a new file and logs what it did. None of
them keeps the trajectory in the session. For the theory (Kabsch superposition,
RMSD, clash criteria, and why the frame-averaged FRET efficiency depends on
the averaging regime), see {ref}`concept-structure-trajectories`.

## Open the tools

**Structure → Structure → Structure Tools**, then **🎞️ Trajectory Tools** in the
left list. The workspace has one dock tab per tool: *Align*, *Convert*,
*Energy Calc*, *FRET*, *Join*, *Remove Clashed*, *Rot Translate*, *Save Topol*.
A file dropped on the window goes to the tab in front if that tab has a single
trajectory field. Each tool also runs as its own window from the command line
(`csg_traj_align`, `csg_traj_convert`, `csg_traj_fret_analysis`, `csg_traj_join`,
`csg_traj_energy_calculator`, `csg_traj_remove_clashed_frames`,
`csg_traj_rotate_translate`, `csg_traj_save_topology`).

**Files.** Trajectories are read and written as **DCD**. A DCD holds only
coordinates (Å), so every tool that reads one also needs a **topology**: a
PDB or mmCIF of the same molecule with the same atoms in the same order. A PDB
or mmCIF on its own is read as a one-frame trajectory. HDF5 and XTC
trajectories are no longer read.

**Example data.** Every number and screenshot below uses the T4 lysozyme
normal-mode ensemble in
`chisurf/plugins/modelling/fret/examples/olga_t4l/`:
`3GUN_NMSim_cl-rep_894.dcd` (894 frames) with the topology
`3GUN_NMSim_cl-rep-001.pdb` (1293 heavy atoms, 162 Cα).

## Align

Superposes every frame on **frame 0** and writes the aligned trajectory. The
superposition is Kabsch's SVD with the handedness correction.

```{figure} figures/traj_tools_align.png
:name: fig-traj-tools-align
:width: 100%

Align on the T4 lysozyme ensemble, fitted on the 162 Cα atoms (their indices
are in *Atom selection*). The log confirms the aligned file was written.
```

* **Trajectory**, **Topology**: the input DCD and its PDB.
* **Atom selection**: comma-separated **atom indices** (0-based) of the fitting
  set. This field does not take a selection expression. Leave it empty to fit
  on all atoms. A token that is not an integer is refused with a log message,
  so you never get a fit on fewer atoms than you asked for. Every atom is
  moved, but only the listed ones define the fit.
* **Stride**: read every Nth frame. The output keeps the source frame spacing
  (frames 0, 10, 20, … at stride 10), so the time axis stays correct.
* **💾 Save aligned…** writes the DCD.

On the example, the Cα RMSD to frame 0 falls from a median of 6.56 Å (raw
coordinates) to 3.86 Å (after superposition). In the aligned file, the plain
RMSD equals the minimal RMSD to within 2×10⁻⁶ Å. The run takes 0.2 s.

To get atom indices from a selection expression, use Python:
`md.load(pdb).top.select("name CA")` (see [Headless](#headless)).

## Convert

Writes a trajectory, or a range of it, as one file or as one file per frame.

```{figure} figures/traj_tools_convert.png
:name: fig-traj-tools-convert
:width: 100%

Convert writing every tenth frame of the ensemble to one DCD: 90 frames of
1293 atoms.
```

**Input:** **Topology**, **Trajectory**, **Target folder**; **First frame**,
**Last frame** (−1 = to the end; otherwise *exclusive*: 10 → 20 writes frames
10–19) and **Stride**. **Output:** **Filename** (base name), **Format**
(`.dcd` or `.pdb`), **Split into one file per frame**
(`{filename}_00000000.pdb`, …), then **▶ Convert**. The log reports how many
frames and atoms were written. Check that line: a range or stride that
selects nothing also finishes with "Conversion done".

Several combinations currently fail or ignore settings. See
[Known defects](#known-defects) before relying on `.pdb` output, *Split* or
*Input is a folder of PDBs*. Writing a DCD, with or without stride and frame
range, works.

## Join

Concatenates two trajectories.

* **Trajectory 1**, **Trajectory 2**, **Topology** (shared).
* **Join mode**: *time* appends the frames of trajectory 2 after those of
  trajectory 1 (same atoms). *atoms* places the two side by side as one system
  (same number of frames). In atoms mode the output has twice the atoms
  (2586 for the example), so a topology for the combined system must be
  supplied separately when the file is read back.
* **Reverse trajectory 1/2**: reverses each chunk in time.
* **Chunk size**: frames read at a time.

Keep **Chunk size** at least as large as the longer trajectory. Joining in time
alternates chunks rather than appending whole trajectories. With chunk 100, the
output is A₀…₉₉, B₀…₉₉, A₁₀₀…₁₉₉, … (see [Known defects](#known-defects)).
The same applies to *Reverse*, which only reverses whole trajectories when one
chunk holds them.

## Remove Clashed

Drops every frame in which some pair of selected atoms is closer than
**Min distance** (Å), and writes the frames that remain.

```{figure} figures/traj_tools_clashes.png
:name: fig-traj-tools-clashes
:width: 100%

Remove Clashed with the Cα atoms and a 3.5 Å threshold. 132 of the 894 frames
have a Cα pair closer than that and are dropped. 762 frames are kept.
```

* **Atom selection**: a selection *expression* (`name CA`,
  `name CA and resSeq 1 to 256`, …), unlike Align.
* **Stride**: read every Nth frame.
* **Min distance** (default 2.85 Å).
* **💾 Save clash-free…** writes the DCD and, beside it,
  `<name>.dcd.times.npy` with the source time of every kept frame. A DCD
  header can only store uniform spacing, and the sidecar keeps the gaps
  visible.

The test does not exclude bonded atoms and uses no per-element radii (see the
concept). Use it on a sparse set such as Cα, with a threshold below the 3.8 Å
spacing of consecutive Cα atoms. On the example: 0 frames are flagged at
3.0 Å, 132 at 3.5 Å, 420 at 3.7 Å and all 894 at 3.8 Å. On all heavy atoms,
2.0 Å flags every frame because of the covalent bonds. The log does not say how
many frames were kept, so read the output back to count them.

## Rot Translate

Applies one rigid-body transform to every frame,
**x′ = R x + t**: rotate first, then translate (Å). **Rotation matrix** is a
3×3 grid, **Translation [Ang.]** a 3-vector, **Stride** reads every Nth frame, and
**💾 Save rotated/translated…** writes the DCD. The matrix is not checked. A
non-orthogonal matrix shears the molecule without any warning. A 90° rotation
about z plus 10 Å along x moves atom 0 of the example from (0.233, 8.831,
−15.129) to (1.169, 0.233, −15.129), as expected.

Use it to place a trajectory into the frame of a reference structure, for
example with the rotation and translation from a superposition done
elsewhere.

## Save Topol

**💾 Save topology…** writes **frame 0** of a trajectory as a PDB, using the atom names of the
topology and the coordinates of the trajectory. The coordinates match frame 0
of the DCD to within 2×10⁻⁶ Å. The topology is still needed to read a DCD, so
in practice this tool gives you the starting structure of a run. Most other
programs expect that structure next to the trajectory.

## Energy Calc

Scores every frame with one or more structure potentials and writes a
tab-separated table: `FrameNbr` followed by one column per potential.

```{figure} figures/traj_tools_energy.png
:name: fig-traj-tools-energy
:width: 100%

Energy Calc with the radius of gyration and the clash potential, every tenth
frame (90 frames). The combo and parameter box below the files configure the
next potential to add.
```

1. **Trajectory**, **Topology**.
2. Pick a potential in the combo and set its parameters in the box below it,
   set **Weight**, then **➕ Add**. The table lists the potentials added, and a
   double-click removes one.
3. **Stride**, then **⚙ Process** and choose the output file.

Only **Radius of Gyration**, **Clash potential** and **Ramachandran** run on a
trajectory at present (see [Known defects](#known-defects)). On the example,
the radius of gyration is 15.9 Å (15.3–16.4 Å over the frames). `FrameNbr` is
1-based: at stride 10 the rows are 1, 11, 21, …, which are source frames 0,
10, 20.

## FRET

Writes, for every frame, the donor–acceptor distance, the orientation factor
and the FRET rate. The dye transition dipoles are taken from two atoms each.

```{figure} figures/traj_tools_fret.png
:name: fig-traj-tools-fret
:width: 100%

The FRET tab with Cα→Cβ of residue 36 as the donor dipole and of residue 132
as the acceptor dipole, R0 = 52 Å, τ0 = 4 ns. Each dipole is two atom
pickers (chain, residue, atom).
```

* **Trajectory**, **Stride**.
* **Dipole atoms**: two atoms for the **Donor** and two for the **Acceptor**.
  The distance is taken between the dipole centres.
* **R0 [Ang]**: the Förster radius for κ² = 2/3.
* **τ0 [ns]**: donor lifetime without acceptor.
* **t-step [ns]**: time between frames, which sets the `time[ns]` column.
* **Dipole (κ2)**: on, κ² is computed per frame from the two dipoles. Off,
  only the first atom of each dye is used and κ² = 2/3.
* **▶ Process trajectory** writes the table. With several trajectories each
  one gets `<name>.<i>.csv`.

The output columns are `Frame`, `time[ns]`, `RDA[Ang]`, `kappa`, `kappa2` and
`FRETrate[1/ns]`, with $k = \tfrac32\,\kappa^2\,(R_0/R)^6/\tau_0$. On the
example, the dipole-centre distance is 27.1 ± 5.7 Å and ⟨κ²⟩ = 0.574. The
table stores no efficiency and does no averaging on purpose: which average
applies depends on the timescales (see
{ref}`concept-structure-trajectories`, where this same table gives
⟨E⟩ = 0.840 for static averaging against 0.993 for dynamic averaging).

The panel has **no topology field**, so a DCD cannot be opened from it yet
(see [Known defects](#known-defects)). Use the Python route below. Atoms are
not dyes: for labelled positions, model the dye clouds with an accessible
volume ({doc}`23_accessible_volume`).

## Where results go next

* An aligned, clash-free DCD goes into the **FRET-modelling** screening and
  evaluation tools (AV per frame), and into the molecular viewer
  ({doc}`44_molecular_viewer`).
* The FRET table is a plain TSV. Average it according to the regime your
  timescales imply, or histogram `RDA[Ang]` against a distance distribution
  fitted to a donor decay ({ref}`concept-distance-distributions`).
* The energy table ranks or filters frames before ensemble averaging.

(headless)=
## Headless

Every panel is backed by a Qt-free view model in
`chisurf/plugins/traj/<tool>/view_model.py`. The panel only sets its fields and
calls its action. The geometry is in `chisurf.core.structure.trajectory_data`.
This script ran on the example data:

```python
from chisurf.core.structure import trajectory_data as md
from chisurf.plugins.traj.traj_align.view_model import AlignTrajectoryViewModel
from chisurf.plugins.traj.traj_remove_clashes.view_model import RemoveClashesViewModel
from chisurf.plugins.traj.fret_trajectory.view_model import FretTrajectoryViewModel

top = "chisurf/plugins/modelling/fret/examples/olga_t4l/3GUN_NMSim_cl-rep-001.pdb"
dcd = "chisurf/plugins/modelling/fret/examples/olga_t4l/3GUN_NMSim_cl-rep_894.dcd"

traj = md.load(dcd, top=top)                    # 894 frames, 1293 atoms, Å
ca = traj.top.select("name CA")                 # 162 atoms
rmsd = md.rmsd(traj, traj, 0, atom_indices=ca)  # minimal RMSD vs frame 0

align = AlignTrajectoryViewModel()
align.set_topology(top)
align.set_trajectory(dcd)
align.atom_selection = ",".join(map(str, ca))
align.save_aligned("t4l_aligned.dcd")

clash = RemoveClashesViewModel()
clash.set_topology(top)
clash.set_trajectory(dcd)
clash.atom_selection = "name CA"
clash.min_distance = 3.5                        # Å
clash.save_clash_free("t4l_clash_free.dcd")     # + t4l_clash_free.dcd.times.npy

fret = FretTrajectoryViewModel()
fret.set_topology(top)
fret.set_trajectory(dcd)
atom = lambda res, name: int(traj.top.select(f"resSeq {res} and name {name}")[0])
fret.donor = (atom(36, "CA"), atom(36, "CB"))
fret.acceptor = (atom(132, "CA"), atom(132, "CB"))
fret.forster_radius, fret.tau0, fret.t_step = 52.0, 4.0, 1.0
table = fret.calc("t4l_36_132.csv")   # frame, time, RDA, kappa, kappa2, kFRET
```

It prints a median RMSD of 3.86 Å, 762 kept frames and ⟨κ²⟩ = 0.574. The other
view models follow the same pattern: `MDConverterViewModel.convert()`,
`JoinTrajectoriesViewModel.save_joined(path)`,
`RotateTranslateViewModel.save_rotated_translated(path)`,
`SaveTopologyViewModel.save_topology(path)` and
`PotentialEnergyViewModel.process(path)`. The energy potentials are the editor
widgets of `chisurf.gui.widgets.structure.potentialDict`, so that view model
needs a `QApplication`.

## Using it well

**Align before anything that compares frames.** RMSD, per-atom fluctuations
and visual inspection all assume the rigid-body motion has been removed. FRET
distances and κ² do not need it, because they are internal coordinates.

**Choose the fitting set for the question.** Fit on the domain you consider
the reference, so the other domain's motion shows relative to it.

**Filter clashes on Cα, not on all atoms.** The filter has no bond exclusion.
Start below 3.5 Å and look at how many frames go. If a threshold drops most of
the ensemble, the threshold is wrong, not the ensemble.

**Keep the times.** Stride, clash removal and joining all change which frames
remain. The tools keep source times, so average against `time`, not the row
index.

(known-defects)=
## Known defects

Measured on the example data. File references are to the current tree.

* **Multi-frame PDB output fails.** Convert with Format `.pdb` (no split)
  raises `Invalid reading_routine "a+"`: `Trajectory.save_pdb` appends models
  through `write_pdb(..., append_model=True)`
  (`chisurf/core/fio/structure/coordinates.py:111` opens with mode `"a+"`),
  which `open_maybe_zipped` does not accept (`chisurf/core/fio/zipped.py:68`).
* **Split ignores the stride and fails with a frame range.** With *Split* on,
  stride 100 still writes all 894 files, because `iterload` is called without
  `stride`. A first/last frame together with *Split* raises
  `TypeError: int() … 'NoneType'`, because `chunk=None` reaches `iterload`
  (`traj_convert/view_model.py`, `convert`).
* **"Input is a folder of PDBs" does nothing useful.** The folder listing is
  built and never used. `md.load` is called on the folder path itself, and the
  run ends with "Wrote 1 frames of 1 atoms".
* **Last frame is exclusive**, so First frame > 0 with Last frame −1 drops the
  final frame (`slice(first, -1, stride)`).
* **Join interleaves chunks.** In time mode, trajectory 1 and 2 are read
  chunk by chunk and written as A-chunk, B-chunk, A-chunk, …. With chunk 100
  on two 894-frame files, frame 100 of the output is frame 0 of trajectory 2.
  The two iterators are also `zip`ped, so the longer trajectory is truncated.
* **The FRET panel has no topology row.** Picking a DCD there raises
  `'…dcd' stores coordinates only; pass top=`. The view model has
  `set_topology`, but the `fret_traj_io` section does not expose it.
* **Six of the nine potentials fail on a trajectory.** H-Bond,
  Miyazawa-Jernigan and ASA-Calpha fail with `Structure object has no
  attribute 'l_res'`. Iso-UNRES and Go-Potential fail with `no attribute
  'dist_ca'`. AV-Potential fails with "Positions not set". The scored
  structure is a plain `Structure`, not the residue-level structure these
  kernels need. Ramachandran runs but returns 0.000 for every frame. H-Bond is
  the default combo entry.
* **Stale units in `trajectory_data`.** The module, `Trajectory` and `rmsd`
  docstrings say nanometres. The coordinates, distances and RMSD are in
  ångström (the T4L coordinates span −29…34, and `compute_distances` itself
  says Å). As a result, `chisurf/plugins/modelling/fret/core/trajectory.py:158`
  (`compute_efficiencies`) still multiplies by 10 as a "nm → Å" step. That
  gives E ≈ 2×10⁻⁵ where 0.97 is correct for a 27 Å pair at R0 = 52 Å, and
  `rmsd_matrix` there is 10× too large.
* The `traj2fret.py` command-line block (`__main__`) is Python 2
  (`string.letters`) and reads `frame.timestep`, which the trajectory object
  does not have.

## See also

- Concept: {ref}`concept-structure-trajectories`. Dye clouds:
  {ref}`concept-accessible-volume`, {doc}`23_accessible_volume`. Orientation
  factor: {ref}`concept-kappa2-orientation`.
- Tool: **Traj Tools** (`chisurf/plugins/traj/traj_tools/`), reached through
  the Structure Tools hub.
