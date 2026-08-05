---
type: PRD
prd: "80"
title: "PRD-80: Retire mdtraj — DCD and RMF3 trajectories on IMP, and the end of pytables/numexpr"
description: mdtraj is the only reason ChiSurf pulls pytables and, through it, numexpr. IMP covers the structure side but has no trajectory reader at all, and RMF3 -- measured -- is ~750x slower to read than DCD, so DCD is the trajectory container and RMF3 the hierarchy/model container.
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
hierarchies and integrative models**, with mdtraj's HDF5 trajectory format
retired. That split is not a preference — it is what the measurements below
force, and the intent to store trajectories *as* RMF3 was tested and does not
survive contact with a real trajectory.

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

# Which container holds the frames — measured

The intended plan was `.h5` → `.rmf3`. It was tested on a realistic trajectory
(2500 atoms, 200 frames — roughly T4 lysozyme, a short run) before being
adopted, and it does not hold up:

| Container | Size | Write | Read |
|---|---|---|---|
| mdtraj `.h5` | 5.14 MB | 381 ms | — |
| **`.dcd`** | 6.01 MB | **34 ms** | **14 ms** |
| `.rmf3` via `IMP.rmf` | 7.08 MB | 3 767 ms | 41 586 ms |
| `.rmf3` via RMF's own API | 7.08 MB | 4 006 ms | 10 489 ms |

**RMF3 reads ~750× slower than DCD and writes ~120× slower, while producing a
larger file.** The second RMF3 row matters: bypassing IMP's hierarchy and using
RMF's raw `ParticleFactory` still costs 10.5 s, so this is RMF's storage model,
not IMP overhead. RMF is per-node keyed — every atom is a node and every frame
is a lookup per node — which is the right shape for a coarse-grained
integrative model with tens to thousands of richly annotated particles, and the
wrong shape for a dense all-atom coordinate block. A 10 000-frame trajectory
would take minutes to open.

So the split is:

* **`.dcd` — frame trajectories.** Contiguous coordinate blocks, the format the
  MD world already exchanges.
* **`.rmf3` — IMP hierarchies, integrative models, anything where the
  per-particle annotation is the point.** Verified working: a 12-frame
  multi-frame round-trip is exact at float32.

One useful property of RMF3 confirmed while testing: it is **Avro-backed, not
HDF5** (magic bytes `Obj\x01…av`; `rmf-hdf5` is a separate, deprecated suffix).
So choosing RMF3 anywhere does not reintroduce the HDF5 stack.

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

1. ~~**DCD reader/writer**~~ — **done**, see below. Standalone; nothing else
   depended on it.
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

# The port source

`junk/` is gitignored, so the reference tree is recorded here rather than only
in `junk/clone.sh`:

```bash
git clone --depth 1 https://github.com/mdtraj/mdtraj.git junk/mdtraj   # 0ca6ffc
```

**Port from the vendored C, not from the `.pyx`.** `mdtraj/formats/dcd/src/`
holds VMD's `dcdplugin.c` under the University of Illinois Open Source Licence,
and `mdtraj/formats/xtc/src/` holds GROMACS' `xdrfile` under BSD-2-clause —
both permissive, both compatible with ChiSurf's GPL-2.0, both requiring only
that the copyright notice travels with the code. The `.pyx` wrappers around
them are mdtraj's own and LGPL-2.1; LGPL §3 does permit relicensing under
GPL-2, but there is no reason to take the more encumbered copy when the
reference implementation underneath is permissive.

# Landed: the DCD codec

`chisurf/core/fio/trajectory/dcd.py` — `read_dcd`, `write_dcd`, `dcd_info`.
Ported from VMD's `dcdplugin.c` (UIUC licence, permissive) rather than from
mdtraj's LGPL `.pyx` wrapper, to NumPy rather than a compiled extension: a
frame is three contiguous `float32` blocks, so reading one is a
`np.frombuffer` and no C is needed to be fast.

**It is faster than the C plugin it replaces.** On 2500 atoms × 200 frames,
against the numbers that chose the format:

| | write | read |
|---|---|---|
| mdtraj (C molfile plugin) | 34 ms | 14 ms |
| **this codec (NumPy)** | **22 ms** | **5 ms** |

One read plus a `frombuffer` per frame beats a `fread` per record.

Handled because real files use them: 64-bit record markers (CHARMM `-i8`),
opposite-endian files, the X-PLOR header variant (timestep as a double), and
both unit-cell conventions — cosines (CHARMM/NAMD > 2.5) and degrees (NAMD
2.5). Refused loudly rather than mis-read: fixed-atom files, which store every
atom only in frame 0, and 4-dimensional files.

Units are **Ångström**, as stored. Nothing is rescaled on the way in or out —
the other convention in this ecosystem is nanometres, and a silent factor of
ten in a FRET distance produces results that look plausible.

**The parity fixtures are committed, not generated.** A self-round-trip proves
almost nothing about an interchange format: a reader and writer sharing a
misunderstanding agree perfectly with each other and with nobody else. So
`test/data/atomic_coordinates/trajectory/dcd/` holds real DCD files written by
mdtraj from this project's own test trajectory, with mdtraj's coordinates
alongside as the oracle — so the check survives mdtraj's removal. The
triclinic-cell fixture is deliberately unequal in all three lengths and angles,
because an orthogonal cell hides an ordering mistake.

The subtle decodings were **mutation-tested**: swapping alpha/gamma, reading
the lengths as values 0–2 instead of 0/2/5, and skipping the cosine branch are
each caught by the suite.

# Migration

**`.h5` trajectories are not supported and not converted.** They were an
artefact of `TrajectoryFile` writing everything to mdtraj's HDF5 container, not
a format users chose, so there is nothing to preserve an on-disk compatibility
story for. Anyone holding one converts it with mdtraj before upgrading; the
tree stops reading them.

The one `.h5` trajectory in the test data has already been re-cut as DCD
(`test/data/atomic_coordinates/trajectory/dcd/`), which is where the parity
fixtures came from.

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
* **Time the load.** Choosing the container on a performance argument means the
  performance is part of the contract: a test that opens a few-hundred-frame
  trajectory and fails if it takes seconds. Without it nothing stops the format
  quietly regressing to what RMF3 would have cost.

# Definition of Done

- [x] DCD reader/writer, with cross-tool parity tests both directions
- [ ] XTC reader/writer (the `xdr3dfcoord` bit-packing; numba for the inner loop)
- [ ] TRR reader/writer
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
* **Do not revisit RMF3-as-trajectory without new numbers.** It was measured,
  not assumed: 10.5 s to read 200 frames of 2500 atoms through RMF's own API,
  against 14 ms for DCD. If a future RMF gains a bulk coordinate path, the
  measurement is cheap to repeat — the script is three dozen lines — but the
  per-node key model is structural, so expect it to still lose.

# Where to pick this up

1. **Answer the IMP-declaration question first** — it decides whether this PRD
   is viable at all. If a packaged install cannot assume IMP, the trajectory
   layer cannot depend on it and this becomes an in-tree-reader PRD instead.
2. **Write the DCD codec** (stage 1). It is independent, self-contained, and the
   only genuinely new code; everything else is porting. Do not start it by
   round-tripping against itself — write the fixtures with mdtraj's
   `save_dcd` *first*, while it is still installed, or the endianness bug will
   survive the whole test suite.

   The container question is **settled and measured** — DCD for frames, RMF3 for
   hierarchies. Do not reopen it without repeating the benchmark.
3. **Then stage 2**, the `TrajectoryFile` reshape, which unblocks the rest.

Do not remove mdtraj until the equal-to-mdtraj tests exist and pass; they are
the only evidence that the coordinates did not move.
