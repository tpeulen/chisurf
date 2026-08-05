---
type: PRD
prd: "80"
title: "PRD-80: Retire mdtraj — DCD and RMF3 trajectories on IMP, and the end of pytables/numexpr"
description: mdtraj is the only reason ChiSurf pulls pytables and, through it, numexpr. IMP is already imported in 34 places and covers the structure side; the gaps are a DCD reader/writer, which IMP does not have, and migrating the one class that stores trajectories in mdtraj's HDF5 format.
status: planned
phase: "unassigned"
resource: chisurf/core/structure/trajectory.py
tags: [prd, dependencies, mdtraj, imp, rmf, dcd, pytables, numexpr, trajectories]
timestamp: '2026-08-05T00:00:00Z'
---

# Summary

`mdtraj` is the last dependency dragging a whole HDF5-plus-compression stack
into ChiSurf, and it is the *only* reason `pytables` and `numexpr` are
installed. Both are unwanted. IMP is already a real dependency — 34 import
sites, and the declared-dependency guardrail treats it as a sibling project
alongside tttrlib and mmfdb — and it covers everything ChiSurf asks of mdtraj
except reading and writing trajectory frames.

The target is **`.dcd` for frame trajectories and `.rmf3` for IMP-native
hierarchies**, with mdtraj's HDF5 trajectory format retired.

This is not a swap. `TrajectoryFile` *subclasses* `mdtraj.Trajectory`, so the
central abstraction changes shape, and 19 files import mdtraj. It needs its own
staging and a lot of testing, which is why it is a PRD rather than a patch.

# The dependency chain, measured

`chisurf → mdtraj → pytables → numexpr`, both hard requirements — verified in
the installed conda metadata, not inferred:

* `mdtraj 1.11.1` `depends:` includes `pytables`
* `pytables 3.11.1` `depends:` includes `numexpr`
* `tables/file.py` does `import numexpr as ne` at module scope

So neither can be dropped while mdtraj stays, however few ChiSurf modules import
them directly. (As of `15fcf8b03` **none** do: the one `numexpr` expression is a
Numba kernel, and `pytables` survives only in six HDF5 read/write helpers.)

Standalone closures on conda-forge, `python=3.12` plus the package alone:

| Package | Closure |
|---|---|
| mdtraj | **70** |
| MDAnalysis | **142** |
| IMP | **159** |

# Why not MDAnalysis

It was considered and measured. It is **twice** mdtraj's footprint, and it is
the wrong direction for three independent reasons:

1. **It reintroduces retired packages.** `networkx` and `tqdm` are both in the
   closure, and both were deliberately removed from ChiSurf with a guardrail
   test banning their import. It also brings seaborn, statsmodels,
   scikit-learn, biopython, netcdf4, hdf4, matplotlib-base and a cairo/fonts
   stack.
2. **It does not read the format ChiSurf has on disk.** MDAnalysis's H5MD
   reader is a different format from mdtraj's HDF5.
3. **The abstraction is further away, not closer.** `Universe`/`AtomGroup` is a
   different model from the numpy-array `Trajectory` ChiSurf is written
   against.

The one point in its favour, stated honestly: it is far more actively
maintained than mdtraj, supports many more formats, and uses `h5py` rather than
`pytables` — so it *would* take `pytables` and `numexpr` with it. At +72
packages net, that is not a trade worth making.

# What IMP covers, and the one thing it does not

Read from the IMP source tree, not from the API listing alone.
`modules/atom/include/` contains exactly `pdb.h`, `mmcif.h`, `mol2.h` and
`secondary_structure_reader.h`.

| Need | IMP |
|---|---|
| PDB / mmCIF / BinaryCIF / mol2 | `read_pdb`, `read_mmcif`, `read_bcif`, `read_mol2`, and the `read_multimodel_*` variants |
| Multi-frame hierarchies | RMF (`IMP.rmf`, RMF 1.7.0, `frames.h`) |
| Geometry, superposition, RMSD | `IMP.algebra` / `IMP.atom` |
| Secondary structure | `read_psipred` only — **parses** an external prediction, does not compute DSSP |
| **DCD / XTC / any frame trajectory** | **Nothing.** |

The `dcd` matches in the IMP tree are prose: `python-ihm`'s `location.py` and
PMI's `mmcif.py` mention DCD as a *file type you can cite in a deposition*.
There is no reader.

**So a DCD reader/writer is the one genuinely new piece of code this PRD
needs.** DCD is a small, stable, well-documented binary format (CHARMM/NAMD
header, per-frame X/Y/Z blocks with Fortran record markers), which puts it
squarely in the category this project already reimplements rather than depends
on. The endianness and the CHARMM-vs-X-PLOR header variants are the parts that
need real test coverage.

# Where `.h5` really is

This matters for scope, and the answer is much narrower than a grep for `.h5`
suggests.

* **mdtraj's HDF5 trajectory format is used in exactly one file**:
  `chisurf/core/structure/trajectory.py`. It is the only place that touches
  `mdtraj.formats.hdf5.HDF5TrajectoryFile` / `save_hdf5`. (A `save_hdf5` in the
  TTTR photon-filter wizard is an unrelated method of the same name.)
* **24 other files use `.h5` for something else entirely** — TTTR photon files,
  burst results, H2MM exports, MMFDB. **None of these are affected**, and
  `hdf5` itself stays in the environment regardless, because the TTTR library
  reads `.hdf` photon files.

So "drop `.h5`" means *drop the mdtraj trajectory container*, not drop HDF5.

# The work

## Inventory

19 files import mdtraj: 17 runtime and 2 tests.

| Area | Files | What it uses |
|---|---|---|
| Core | `structure/trajectory.py`, `structure/structure.py`, `structure/av/static.py` | `Trajectory` (subclassed), `HDF5TrajectoryFile`, `load`, `Topology`, `element.*` |
| `traj` plugins (8) | align, join, convert, rotate/translate, remove-clashes, save-topology, fret-trajectory, potential-energy | `load`, `iterload`, `join`, `slice`, `superpose`, `save`, `scripts.mdconvert.main` |
| FRET modelling (4) | `core/trajectory.py`, `core/evaluate.py`, `core/pair_selection.py`, `gui/pair_selection_wizard.py` | `rmsd`, `compute_distances`, `load` |
| chimol | `io/structure.py` | `load` |
| Tests (2) | `chimol/test/test_ss_vs_mdtraj.py`, `fret/test/test_pair_selection.py` | `compute_dssp` as an oracle, `Topology` |

The full symbol surface: `load`, `load_frame`, `iterload`, `join`, `slice`,
`Trajectory` (+`save`, `superpose`, `load`), `Topology`, `core.topology`,
`element.{carbon,hydrogen,nitrogen,oxygen}`, `compute_distances`,
`compute_dssp`, `rmsd`, `formats.hdf5.HDF5TrajectoryFile`,
`scripts.mdconvert.main`, `urls`, `hasUrls`.

Format counts across the structure and traj code: `.h5` 143, `.pdb` 97, `.xyz`
75, `.xtc` 4, `.dcd` 3. The HDF5 dominance is an artefact of `TrajectoryFile`
converting *everything* to `.h5` on construction, not of users having HDF5
trajectories.

## Two things already exist, and shrink the estimate

* **`compute_dssp` is only a test oracle.** Its single use is
  `chimol/test/test_ss_vs_mdtraj.py`, which checks chimol's *own* secondary
  structure against mdtraj. That test needs a recorded fixture, not a DSSP
  implementation.
* **Kabsch superposition is already in-tree**:
  `chimol/analysis/metrics.py::compute_kabsch`. `superpose` and the pairwise
  `md.rmsd` matrices in the FRET plugin can be built on it.

## Staging

1. **DCD reader/writer**, standalone and tested against files written by other
   tools, both endiannesses and both header variants. Nothing else depends on
   the rest of the PRD.
2. **A trajectory abstraction that is not an mdtraj subclass.** `TrajectoryFile`
   currently inherits `mdtraj.Trajectory`; it becomes a class of its own over
   `(xyz, topology, time)` with DCD and RMF3 backends. This is the change
   everything else waits on.
3. **Topology without `mdtraj.Topology`** — IMP hierarchies for structures read
   from PDB/mmCIF, and the element table (`element.{carbon,…}`) replaced by
   IMP's.
4. **Port the eight `traj` plugins**, including replacing the `mdconvert`
   shell-out in `traj_convert` with the in-tree converter.
5. **Port the FRET modelling plugin** (`rmsd` matrices, `compute_distances`).
6. **Migration path for existing `.h5` trajectories** — see below.
7. **Drop `mdtraj`, `pytables` and `numexpr`** from `pixi.toml`,
   `pyproject.toml` and the recipe; add all three to
   `test/test_no_retired_dependency_imports.py`. Remove the six direct
   `import tables` sites (HDF5 helpers) first.

## Migration

Existing `.h5` trajectories are real user data. A converter (`.h5` → `.dcd` +
topology) has to be written and shipped **while mdtraj is still installed**, and
run before step 7 removes it — a converter that needs the dependency it is
migrating off is useless. It should be a `csc` subcommand so it works headlessly
and can be pointed at a directory.

# Testing

The user's own framing: this needs a lot of it. The risk is not that a port
fails loudly — it is that coordinates come back subtly wrong (units, axis
order, precision, frame offsets) and every downstream FRET distance shifts by a
few percent without anything raising.

* **Round-trip, bit-level.** Write and re-read DCD and RMF3; coordinates must
  match to float32 exactly, not `allclose`.
* **Cross-reader parity.** A DCD written here must be readable by an
  independent tool, and a DCD written elsewhere readable here. This is the test
  that catches an endianness or record-marker mistake, which a self-round-trip
  cannot.
* **Against mdtraj, while it is still installed.** Every ported operation
  (`load`, `superpose`, `rmsd`, `compute_distances`, slicing, joining) gets a
  test asserting the new path equals the mdtraj path on a real structure.
  These tests are written **before** step 7 and deleted with it — they are the
  evidence the port is faithful, and they cannot be written afterwards.
* **Units.** mdtraj works in nanometres; PDB and IMP in Ångström. The existing
  code already multiplies by 10 in places (`core/trajectory.py`). Every
  conversion needs a test with a known distance, because a factor of 10 in a
  FRET distance is the kind of error that produces plausible-looking results.
* **The reference structures** are the project's standard ones: T4 lysozyme
  (148L) for protein and HIV-RT (1RTD) for protein + nucleic acid.

# Definition of Done

- [ ] DCD reader/writer, with cross-tool parity tests both directions
- [ ] `TrajectoryFile` no longer subclasses `mdtraj.Trajectory`
- [ ] All 17 runtime import sites ported; 2 test sites resolved (DSSP fixture)
- [ ] `csc` converter for existing `.h5` trajectories, shipped and documented
- [ ] Equal-to-mdtraj tests written, passing, then removed with the dependency
- [ ] `mdtraj`, `pytables`, `numexpr` gone from all three manifests and added to
      the retired-dependency guardrail
- [ ] `docs/` updated: the trajectory formats ChiSurf reads and writes
- [ ] Closure re-measured and the real saving recorded (see the caution below)

# Risks and open questions

* **The saving may be smaller than 70 packages.** `hdf5` and its curl/AWS stack
  stay for the TTTR photon readers, and `pandas`/`scipy` are direct
  dependencies. The honest number is mdtraj + pytables + numexpr + their
  exclusive leaves; it must be *measured* after the fact, not asserted. An
  attempt to measure the marginal cost during this investigation produced
  unusable output and was abandoned rather than reported.
* **IMP is imported but not declared.** 34 import sites, and
  `potentials.py` imports `IMP.cgmol` at *module* level, yet IMP appears in no
  manifest — it is allowlisted as a sibling project in
  `test/test_declared_dependencies.py`. Making IMP load-bearing for
  trajectories raises the question of whether a packaged ChiSurf install is
  expected to have it. **Decide this before step 2.**
* **XTC.** Four references. If any real data uses it, DCD alone is not enough
  and the scope grows; check before starting.

# Where to pick this up

1. **Answer the IMP-declaration question first** — it decides whether this PRD
   is viable at all. If a packaged install cannot assume IMP, the trajectory
   layer cannot depend on it and this becomes an in-tree-reader PRD instead.
2. **Write the DCD codec** (stage 1). It is independent, self-contained, and the
   only genuinely new code; everything else is porting. Do not start it by
   round-tripping against itself — get a DCD written by another tool first, or
   the endianness bug will survive the whole test suite.
3. **Then stage 2**, the `TrajectoryFile` reshape, which unblocks the rest.

Do not remove mdtraj until the equal-to-mdtraj tests exist and pass; they are
the only evidence that the coordinates did not move.
