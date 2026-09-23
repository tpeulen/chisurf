# Traj Tools

Small tools for preparing a structure trajectory (MD, normal modes, docking)
for FRET work. Each tab reads a trajectory, writes a new file and logs what it
did.

**Files.** Trajectories are **DCD** files, in Å. A DCD stores only coordinates,
so each tab also needs a **topology**: a PDB or mmCIF with the same atoms in
the same order. Example data:
`chisurf/plugins/modelling/fret/examples/olga_t4l/` (T4 lysozyme, 894 frames).

## The tabs

* **Align**: superposes every frame on frame 0 (Kabsch SVD). *Atom selection*
  takes comma-separated **atom indices** of the fitting set, not an
  expression. Leave it empty to fit on all atoms. Every atom is moved.
* **Convert**: writes a frame range (*Last frame* is exclusive, −1 = to the
  end) and stride as one file or one file per frame. DCD output is reliable.
  Multi-frame PDB, *Split* with a stride or range, and folder input have known
  defects (see the guide).
* **Energy Calc**: scores frames with structure potentials into a TSV.
  Radius of Gyration, Clash potential and Ramachandran run on trajectories.
* **FRET**: per frame, the dipole-centre distance R_DA, κ, κ² and
  k_FRET = 1.5 κ² (R0/R)⁶/τ0, using two atoms per dye. It computes no
  efficiency and no average, because which average applies depends on the
  timescales. This tab has no topology row yet, so use the Python route for a
  DCD.
* **Join**: appends two trajectories in time, or stacks them as one system
  (atoms). Keep *Chunk size* at least as large as the longer trajectory,
  otherwise chunks alternate.
* **Remove Clashed**: drops frames in which any selected pair is closer than
  *Min distance* (Å). Bonds are not excluded, so use it on Cα (below the
  3.8 Å Cα–Cα spacing), not on all atoms. Kept frame times go to
  `<name>.dcd.times.npy`.
* **Rot Translate**: applies x′ = R x + t to every frame. The matrix is not
  checked for orthogonality.
* **Save Topol**: writes frame 0 as a PDB.

## Headless

Each tab has a Qt-free view model in `chisurf/plugins/traj/<tool>/view_model.py`.

```python
from chisurf.core.structure import trajectory_data as md
from chisurf.plugins.traj.traj_align.view_model import AlignTrajectoryViewModel

traj = md.load("traj.dcd", top="top.pdb")
align = AlignTrajectoryViewModel()
align.set_topology("top.pdb")
align.set_trajectory("traj.dcd")
align.atom_selection = ",".join(map(str, traj.top.select("name CA")))
align.save_aligned("aligned.dcd")
```

## Further reading

* [Structure trajectories](docs/concepts/structure_trajectories.md) — superposition, RMSD, clashes and FRET averaging regimes
* [Trajectory tools guide](docs/guides/81_trajectory_tools.md) — every tab, measured on T4 lysozyme, headless use and known defects
* [Accessible-volume dye modelling](docs/concepts/accessible_volume.md) — dye clouds instead of atoms
- {cite}`kabsch1976` — the optimal rotation
- {cite}`theobald2005` — the quaternion characteristic-polynomial RMSD
- {cite}`hoefling2011` — FRET efficiency from atomistic trajectories with κ²(t)
