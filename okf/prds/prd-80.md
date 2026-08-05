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
   still inherits `mdtraj.Trajectory`; it becomes a class of its own over
   `(xyz, topology, time)` with DCD and XTC backends. This is the change
   everything else waits on. *Partly done*: the loader now **opens `.dcd` and
   `.xtc` through ChiSurf's own codecs* — only the container object and the
   topology still come from mdtraj.
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

**Read speed against the C plugin it replaces** — medians of 7 alternating
runs, after a warm-up, because a single shot cannot tell a speed difference
from noise:

| Shape | ours | mdtraj | ratio |
|---|---|---|---|
| 200 frames × 2500 atoms | 4.2 ms | 4.6 ms | 1.10× |
| 464 frames × 5235 atoms | 12.9 ms | 21.9 ms | 1.69× |
| 2000 frames × 500 atoms | 5.5 ms | 18.4 ms | 3.37× |
| 50 frames × 20000 atoms | 5.2 ms | 5.6 ms | 1.08× |

**This took two goes, and the first answer was wrong.** The initial version read
frame by frame — a seek, a read and three strided assignments per frame in
Python — and a single unrepeated measurement flattered it into looking 3×
faster than mdtraj. Repeated properly it was **0.79–1.04×**, i.e. slightly
*slower*, and worst exactly where the per-frame Python cost dominates: many
frames of few atoms. The fix is to read the whole payload once and de-interleave
it in a single `numba` pass (`_gather_frames`, `prange` over frames). The
decoding itself was never the cost — the payload is already `float32` — the
per-frame Python was.

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
each caught by the suite. (A fourth mutation — `arccos` for `90 − asin` — is
*not* caught, and should not be: the two are the same identity.)

The strongest parity result is byte-level and needs no other library at test
time: reading the coordinates out of the reference file and writing them back
reproduces its coordinate records **byte for byte** — on the full 464-frame
trajectory, 1392 of 1392 records identical, same md5. That says the reader and
writer are exact *inverses* of the other implementation's, which no tolerance
comparison can. It also explains the only apparent discrepancy: comparing
against mdtraj's array shows ~7.6e-06, and that is mdtraj's own Å→nm→Å
conversion, not our error.

# Landed: the XTC decoder

`chisurf/core/fio/trajectory/xtc.py` — `read_xtc`, `xtc_info`. Ported from
GROMACS' `xdrfile` (BSD-2), again from the C rather than the LGPL wrapper.

Unlike DCD, this is a real decode: coordinates are quantised to a stated
precision, stored as integers relative to a per-frame bounding box, and
bit-packed. The bit-level routines are numba kernels because there is no
vectorised way to walk a bit stream.

**Faster than the reference C, by decoding frames in parallel** — medians of 5,
against mdtraj's vendored `xdrfile`:

| Frames × atoms | ours | mdtraj | ratio |
|---|---|---|---|
| 50 × 5235 | 6.5 ms | 12.4 ms | 1.91× |
| 200 × 5235 | 26.2 ms | 47.3 ms | 1.81× |
| 464 × 5235 | 61.4 ms | 133.5 ms | 2.17× |

Unpacking one frame is strictly serial, but each frame is a self-contained
compressed block — the bit stream never crosses a frame boundary — so the
frames are embarrassingly parallel. That is the entire source of the win; the
reference decodes them one after another.

**Bit-exact** against the reference on every branch: 1, 4, 9 (uncompressed),
10, 100 and 5235 atoms.

Three things cost real time to get right, all of them silent failures:

1. **`run` persists across atoms.** When the flag bit is 0 the reference does
   *not* reset the run length — a second water molecule of the same length
   costs that single bit. Resetting it decodes the first molecule and then
   walks off the stream.
2. **The ≤9-atom branch has a different frame layout.** The coordinates sit
   behind the atom-count field that only the compressed branch otherwise reads,
   so the frame walker desynchronises four bytes in and reports "not an XTC
   file" at the *second* frame.
3. **`lastbyte` is a 32-bit unsigned in C** and the shift discards the high
   bits. Letting it grow in 64-bit changes what the next shift reads.

**The oracle must be what the reference reads back, not what it was given.**
XTC is lossy; storing the pre-write coordinates as "expected" fails by
0.0005 nm against a perfectly correct decoder, and invites loosening the
tolerance until real bugs fit through. That mistake was made and corrected
here.

XTC stays **read-only**: ChiSurf writes DCD, which is lossless, so an encoder
would exist only to hand files to other tools, and it would have to reproduce
the quantisation ladder exactly to be worth having.

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
- [x] XTC reader (the `xdr3dfcoord` bit-packing, in numba)
- [ ] XTC writer — only needed to hand files to other tools; ChiSurf writes DCD
- [ ] TRR reader/writer — no call site needs it yet; add on demand
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

# Landed: the loader reaches the new codecs

`TrajectoryFile(path, topology=<pdb>)` now opens `.dcd` and `.xtc`, decoding
with `chisurf.core.fio.trajectory`. Only the container and the topology are
still mdtraj's. Both formats store coordinates and nothing else, so a topology
argument is **required** and a mismatched atom count is refused — accepting one
silently renames every atom, and that travels into distances and FRET pairs
without an error.

An unknown suffix is now refused too. It used to fall through to a branch that
never set `_mdtraj` and failed later with an `AttributeError` far from the
cause.

**A trap for whoever does stage 2.** `TrajectoryFile` computes an RMSD in its
constructor, and `mdtraj.rmsd` **centres its inputs in place** — so every
trajectory this class loads comes back recentred, by 5.5 nm on the test file.
That is long-standing behaviour for every format, not something the new path
introduced, but it is invisible in the code and a reimplementation will either
reproduce it by accident or drop it by accident. Decide deliberately. The tests
put the reference through the same centring rather than pretending it is not
there.

# Where to pick this up

The codecs are done and the loader uses them. What remains is the port.

1. **Stage 2 — take `mdtraj.Trajectory` out of the base classes.** This is the
   one thing everything else waits on, and it is not gated on the IMP question
   below: coordinates no longer need mdtraj at all. `TrajectoryFile` becomes a
   class over `(xyz, topology, time)`. Its consumers reach mdtraj methods
   *through inheritance* (`superpose`, slicing, `join`, `.xyz`, `.topology`),
   so they break together the moment the base class goes — expect to port the
   eight `traj` plugins in the same change rather than after it.
   Read the centring trap above first.
2. **Stage 3 — topology without `mdtraj.Topology`.** *This* is what the IMP
   question gates. `chisurf.core.structure.Structure` already reads PDB without
   mdtraj (it uses it only in the `find_best` RMSD helper), so the topology may
   be closer to hand than it looks — check what `Structure` can already supply
   before reaching for IMP.
3. **Then the FRET modelling plugin** (`rmsd` matrices, `compute_distances`)
   and the `mdconvert` shell-out in `traj_convert`.
4. **Then drop the three dependencies** and extend the guardrail.

**Settle before stage 3, not before stage 2:** IMP is imported 34 times but
declared in no manifest — allowlisted as a sibling project, with one
*module-level* `IMP.cgmol` import in `potentials.py`. If a packaged install
cannot assume IMP, topology cannot depend on it.

Do not remove mdtraj until the equal-to-mdtraj tests exist and pass; they are
the only evidence that the coordinates did not move. The committed fixtures
under `test/data/atomic_coordinates/trajectory/{dcd,xtc}/` already cover the
codecs and need no mdtraj — it is the *operations* that still lack that cover.
