---
type: Concept
title: The four-repository stack — scope boundaries and who owns what
description: tttrlib owns photons and fluorescence algorithms, imp.bff owns structure, dye simulation, spectroscopy and scoring, imp-tricks adds to IMP without replacing, chisurf is the application. The layering, the tiebreakers, and the debt still in the wrong place.
resource: /Users/tpeulen/dev/imp
tags: [scope, architecture, imp, imp.bff, imp-tricks, tttrlib, layering]
timestamp: '2026-08-10T00:00:00Z'
---

# GOLDEN RULE — never commit to the IMP checkout

**`/Users/tpeulen/dev/imp` takes no local commits. Ever.**

It is a clone of `salilab/imp` tracking `origin/develop`, and it is refreshed
with `git pull --ff-only`. A single local commit makes that pull fail forever
after, and the way out is a rebase or a reset on a 300-commit-behind tree with a
symlinked submodule in it — an afternoon lost to a one-line convenience.

Everything that would be a commit there goes somewhere else:

| You want to… | Do this instead |
|---|---|
| change IMP.bff | commit in `../imp.bff` — `modules/bff` is a symlink to it |
| add agent notes, an OKF page, a scratch file | put it in this bundle; if it must live in the checkout, add it to that checkout's local `.gitignore` (as `AGENTS.md` is) |
| patch IMP itself | open a PR upstream, or carry the change in a branch of a *separate* clone |
| keep a local build config | it is already ignored — `build`, `cmake_modules`, `cmake-build*` |

The two permanent local modifications there (`.gitignore`, the `modules/bff`
typechange) are **working-tree** modifications on purpose. They are never
committed, which is why `git log origin/develop..HEAD` is empty and must stay
empty.

A `pre-commit` hook in that checkout refuses commits outright. Note that IMP's
own `setup_git.py` regenerates `.git/hooks/`, so re-running it removes the
guard — re-apply it afterwards.

# Where to pick this up

## chisurf drops its direct IMP dependency (2026-09-09, owner's plan)

**Three of the four done; the fourth is FRET docking and it needs a ruling.**

The premise, corrected by the owner on 2026-09-09: **the bff wheel links IMP
at C++ level** (`IMPBFF_WITH_IMP`, PRD-139), so the connection layer's
capability is available from a plain `pip install`. The only rule is that
**nothing wrapped may name an IMP type**, or SWIG needs IMP's own `.i` files
and the extension imports `_IMP_kernel` at load. Verified here: a `core+imp`
build reports `get_build() == "core+imp"`, carries `DyeSimulation`, and its
Python surface is the core's 913 names rather than the IMP module build's
1275 -- with `import IMP.atom` failing.

So the work is *doors*, not ports. Landed:

1. ✅ **Structure reading** -- `IMP.bff.read_structure_table` (imp.bff
   `e36ecff`), IMP's PDB **and mmCIF** readers behind flat columns, with the
   radius a docking score measures clashes against. chisurf `f150ccc0e`.
2. ✅ **RMF trajectories** -- `IMP.bff.RmfStructureWriter` (imp.bff
   `285eedb`), the PMI tree through **RMF's own decorators**, so it needs no
   IMP at all. It is *core*, not layer. chisurf `61ec4b650`.
3. ✅ **MRC maps** -- `IMP.bff.write_mrc_grid` (imp.bff `4c780d3`), the
   sibling of `write_opendx`. chisurf `6890cc758`.
4. 🚫 **FRET docking** -- blocked on where the *workflow* layer lives.

### What blocks (4), measured 2026-09-09

`chisurf/plugins/modelling/fret/core/` is eight forwarders onto
`IMP.bff.fret.*`, a subpackage deleted on 2026-08-19 (`6cd2206`, the layout
migration) and finished off on 2026-08-23 (`6584e80`, "zero .py files in
pyext, flat IMP.bff namespace only"). **Every one raises
`ModuleNotFoundError` on both builds today** -- this is not a pip-versus-conda
difference, the plugin has simply been dead since August. The same cut took
`IMP.bff.quenching`, `.av` and `.io` with it, which is why
`test/structure/test_av_dynamic_quenching.py` cannot be collected either.

Checking every name the plugin needs against the flat surface splits it
cleanly in two:

| module | on flat `IMP.bff` | missing |
|---|---|---|
| `stat` | `count_frames`, `read_score_series` | -- |
| `olga_greedy` | `select_informative_pairs` | -- |
| `distance` | `average_distance`, `chi2_score`, `histogram_rda`, `model_distance` | `DistanceEvaluator`, `DistanceDistributionEvaluator` |
| `av` | `AccessibleVolume`, `load_structure_with_vdw` | `BasicAV`, `compute_av`, `compute_avs_for_structure`, `select_backend`, `VDW_RADII` |
| `engine` | -- | `RigidBody`, `DistanceRestraint`, `SpringParameters` |
| `imp_engine` | `DockingParameters`, `DockingResult`, `dock_minimize`, `capture_poses`, `apply_poses` | `dock`, `refine`, `screen`, `score`, `build_assembly`, `estimate_errors`, `ensure_fps_json` |

The pattern: **the primitives became C++ and are all there; the workflow
wrappers around them were dropped.** And the workflows are not gone -- they
were rewritten inside `imp.bff/bin/imp_bff` as `run_replica_exchange_docking`
and `estimate_errors`, driving the `imp_bff dock` and `imp_bff dock-errors`
commands. That file **cannot be imported**: it is a click program with no
extension, which is why imp.bff's own `test/conftest.py` carries a bespoke
loader for it.

### The ruling, and what it has produced so far

**Owner, 2026-09-09**: *"the workflow should be implemented in bff,
preferentially in cpp, chisurf just consumes and interfaces. there can be
imp_bff dock. the fret plugin was dead on purpose as there was too much work
on bff to be done, if it can be fixed, this could be a good time to fix it."*

So: option (c) below, C++ in bff, with chisurf a consumer. Landed in imp.bff
`c91cdfb`:

- **`IMP::bff::dock`** -- the FRET-restrained sampler, C++, the piece that was
  missing. It writes no walk of its own: the mobile bodies' poses are one
  vector (six numbers each, a translation and a rotation vector) and
  `IMP::bff::Sampler` samples it against the network score.
- **`IMP::bff::estimate_docking_errors`** -- independent random starts and
  their spread, which is what `bin/imp_bff`'s Python `estimate_errors` did.
- **`Sampler` gained a `"slice"` backend** (`zeus`), so the vocabulary is
  `metropolis` / `stretch` / `slice` / `de` -- one interface, four backends,
  which is the second half of the owner's instruction ("i do not want too
  diverse sampling interfaces").

That closes the C++ side. `bin/imp_bff`'s `run_replica_exchange_docking` (the
`IMP.pmi` one) is now a duplicate of `dock` and should be deleted in favour
of it; `imp_bff dock` keeps its name and its flags.

**What is left is the chisurf side**, and it is a *split*, not a move. The
eight forwarders divide cleanly by the layering rule (what is the input?):

| module | where it belongs | why |
|---|---|---|
| `stat`, `olga_greedy` | **bff, done** | `count_frames`, `read_score_series`, `select_informative_pairs` are all on the flat surface already; the forwarders just need repointing |
| `distance` | **split** | the kernels (`chi2_score`, `model_distance`, `average_distance`, `histogram_rda`) are bff's and present; `DistanceEvaluator` / `DistanceDistributionEvaluator` are fps.json evaluator *objects*, which are the application's |
| `av` | **split** | `get_av` and `AccessibleVolume` are bff's; `BasicAV`, `select_backend`, `VDW_RADII` are backend-selection glue, chisurf's |
| `engine` | **chisurf** | 179 lines of plain dataclasses (`RigidBody`, `DistanceRestraint`, `SpringParameters`) for the OLGA evaluators. No IMP, no algorithm. It went to bff and bff correctly dropped it |
| `imp_engine` | **bff, done** | `dock`, `dock_minimize`, `refine_docking`, `screen_structures`, `score_structures`, `capture_poses`, `apply_poses`, `create_docking_assembly`, `estimate_docking_errors` are all C++ now |
| `distributions`, `uncertainty` | small; `distributions` is P(R_DA) for a structure (bff), `uncertainty` is precision from repeated docking (a workflow reading `estimate_docking_errors`) |

The pure application code is recoverable: `git show 046cb9989^:<path>` in
chisurf is each module as it was before it became a forwarder.

### The options as they stood before the ruling

Where do the Python-level docking workflows live? They use `IMP.pmi` and
`IMP.core` from Python, so they cannot be C++ without a real port.

- **(a) A CLI chisurf shells out to.** `imp_bff dock` and `dock-errors`
  already exist; `refine`, `screen` and `score` would be added. Honours
  imp.bff's "zero .py files in pyext" rule, and puts a process boundary
  between chisurf and IMP, which is the strongest form of the goal. Cost: the
  plugin's in-process semantics have to be re-expressed -- `dock_minimize`
  takes a `stop_check` callback and `initial_poses`, and returns a result
  object the GUI reads.
- **(b) An importable Python module in imp.bff**, reversing `6584e80` for
  this one area. Cheapest by far, and keeps the callback semantics. Costs the
  rule that made the package flat.
- **(c) Port the workflows to C++.** PRD-137 measured the blocker for the
  neighbouring case: bff has **no analytic gradients** anywhere, and IMP's
  restraints are what supply the derivatives its optimiser steps on.

"as a cli or similar" (owner, 2026-09-09) points at (a). Not started, because
which one is chosen changes the whole shape of `fret/core/`.

### Before touching it

`test/structure/test_av_dynamic_quenching.py` and the eight forwarders fail at
*collection*, so any suite run that includes them stops there. Exclude them
until (4) lands, and do not read those failures as caused by whatever you are
changing.

## The four-repository boundaries

The boundaries below were settled on 2026-08-10 and are the target. Three of
them are enforced by tests; the rest is debt with a known direction. Open work,
in the order it should be done:

1. ✅ **`cgdye` is in imp.bff** (`imp.bff` `8fac573`, `imp-tricks` `34cf4de`),
   with `fps.py` and the FRETpredict rotamer library. The library was the open
   question and it is **data**: 45 MB / 227 files now shipping as IMP module
   data at `imp.bff/data/rotamer_library`, reached by every loader through
   `IMP.bff.get_data_path("rotamer_library")` rather than by walking up from
   `__file__`. Its vendored `thirdparty/` (280 MB) stayed behind as gitignored
   `junk/`.
2. **cgdye's externals are undeclared** — `Bio`, `MDAnalysis`, `click`, `numba`.
   IMP.bff ships through conda-forge as part of IMP, where the runtime
   dependency list is a public contract, so each must be declared, guarded or
   dropped. It cannot simply arrive.
3. **chisurf's κ² is debt** — `core/models/anisotropy_to_kappa.py` (the fitting
   adapter) stays; `kappa2_to_distance_ratio` and
   `convolve_distance_with_k2_ratio` in `core/fluorescence/general.py` belong in
   imp.bff.
4. **chisurf's `core/fluorescence` (38k lines) migrates by attrition**, not in
   one move. See "chisurf owns no algorithms" below for why.

# The layering

```
tttrlib      photons, fluorescence algorithms          — never imports upward
   ↑
imp.bff      structure, dye simulation, spectroscopy,  — may import tttrlib,
             scoring                                     but only optionally
   ↑
imp-tricks   additive layer on IMP (any namespace)     — adds, never replaces
   ↑
chisurf      the application                           — binds; owns no algorithms
```

**The rule for placing a new algorithm is: what is the input?** Photons or
curves → tttrlib. Coordinates → imp.bff. Neither, it is a workflow → chisurf.

**Sharpened by the owner, 2026-09-02: a *forward model* goes to imp.bff even
when its subject is photons.** "Model stuff that is model and does not
touch/transform data directly should be in bff" — a function that computes a
model curve or quantity *from parameters* and never reads or reshapes
measured data is a model, not data reduction, so the FCS MDF/saturation
forward models and their PSF math belong in imp.bff. What reads or transforms
measured photons/curves stays tttrlib's, and kernel neighbourhood is a
legitimate tiebreaker the other way: pile-up scales the model *from the
data* and sits beside the decay convolution, so it is tttrlib's. (tttrlib's
`SimGrid` PSF profiles serve the photon *simulator* and stay; the twin is
cited in comments, never rewritten as a third copy.)

**The tiebreaker, when input and consumer disagree, is: the consumer wins.**
This is not a footnote; it is the rule that decides the hardest real case, and
without it someone will "correct" κ² into tttrlib. See below.

# The repositories

**`../tttrlib`** — the bottom of the stack: photon data and the fluorescence
algorithms that run on it. It depends on nothing above it, and that is the one
edge whose violation would turn a layered stack into a cycle. It has its own OKF
bundle at `../tttrlib/okf/` for photon-level concerns and shares this project's
agent message board.

**`../imp.bff`** — an IMP C++/SWIG module, reached through `imp/modules/bff`
(a symlink, not a submodule). Owns structure and the simulation of dyes: once
dyes are simulated, structures can be scored. `IMP.bff.AV`, `PathMap`,
`AVNetworkRestraint`, and `spectroscopy` including **all of κ²**. Local work is
on its `dev` branch. The `Decay*` classes are deprecated at 2.25 — that
functionality lives in tttrlib now, and imp.bff delegates rather than
duplicates.

**`../imp-tricks`** — a pure-Python tree that grafts itself into the `IMP`
namespace at import time through its `sitecustomize.py`. It is **not** specific
to `IMP.bff`: `cgmol`, `finite`, `speciation` and `swarm` are its own IMP
namespaces. Its role is to add features to IMP without waiting on a C++ build,
and the layering is deliberate.

**`../chisurf`** — the application. GUI, projects, plugins, orchestration. It is
the only place tttrlib and imp.bff meet: 143 files import tttrlib, 9 import IMP.

# imp.bff owns κ² whole, even the parts fed by measurement data

`spectroscopy/kappa2.py` (762 lines) contains both routes, and they share
helpers:

* **coordinates in** — `kappa`, `kappa_distance`, `calculate_kappa_distance`
* **anisotropy in** — `kappasq_all_delta`, `kappasq_dwt`, `s2delta`,
  `kappasq_all`, `p_isotropic_orientation_factor`

Read literally, "what is the input?" would split that file down the middle and
separate `kappa()` from `s2delta()` and `p_isotropic_orientation_factor()`,
forcing either duplication or a dependency reaching back the wrong way. The
consumer-wins tiebreaker settles it: κ²'s whole purpose is to turn orientation
information into an R₀/distance correction used when **scoring a structure**,
which is imp.bff's job regardless of whether that orientation arrived as
coordinates or as a residual anisotropy. The route is anisotropy → structure,
and it lives in imp.bff.

The consequence to state plainly, because it looks like an inconsistency to
anyone reading only the input rule: **imp.bff legitimately owns algorithms whose
input is measurement data.**

# tttrlib is optional inside imp.bff

imp.bff *may* import tttrlib — tttrlib is lower level — but **most of imp.bff
must work without it**. Guarded imports only; no module-level `import tttrlib`
on a path the core API needs. Without a test this softness hardens the first
time someone finds it convenient, and the breakage surfaces only for a user who
does not have tttrlib installed.

# imp-tricks adds, never replaces

imp-tricks may contribute names to any `IMP.*` namespace. It may not replace one
that IMP or an IMP module already provides.

This is not a style preference. Until 2026-08-10 imp-tricks' `IMP/bff/restraints`
stood in front of imp.bff's, and because a subpackage resolves to the **first**
matching directory and stops, imp.bff's was unreachable — submodules and
exported names alike. `AVNetworkRestraintWrapper` was recorded in
[known-issues](known-issues.md) as a deleted upstream API for five days while
the class sat in the build tree, and ten ChiSurf tests failed on it. The merge
machinery in `sitecustomize` now unions the directories and adopts the shadowed
`__init__`'s names, and a collision warns rather than winning silently.

# chisurf owns no algorithms — and that is debt, not description

Today chisurf is both application and fluorescence library: `core/fluorescence`
is 38,215 lines across 100 files (`burst`, `mfd`, `pda`, `pda3c`, `fcs`,
`tcspc`, `decay*`, `mle`, `anisotropy`, `dyes`, `fret`, `imaging`, `diffusion`,
`kinetics`, `simulation`), `core/models` 24,349, `core/structure` 8,160. Under
the rule most of that belongs in tttrlib, and the structure-facing part in
imp.bff.

**Migrate by attrition, not by a migration.** The rule binds *new* code
immediately: new physics goes to the owning library and chisurf imports it.
Existing code moves when it is already being touched, or when a second consumer
appears. A big-bang evacuation of 38k lines would break every plugin, notebook
and saved project at once, during a window in which nothing new works either.
Attrition turns an unbounded risk into a bounded per-change cost, and the
remaining debt stays visible here rather than in someone's head.

# Vendored code is junk/, and junk/ is gitignored

`cgdye/thirdparty/` was 51,066 of cgdye's 65,778 lines — FRETpredict, fpsim,
MDAnalysis tooling, and a Flask + Celery + Redis web application, all vendored
for reference. It is renamed `junk/` and gitignored, following the convention in
[reference-checkouts](../workflows/reference-checkouts.md). None of it moves
into imp.bff: `IMP.bff` ships through conda-forge as part of IMP, its runtime
dependency list is a public contract, and `flask`/`celery`/`redis` cannot appear
in it. IMP also globs every `.py` under a module's `test/` into ctest, so a
vendored test suite becomes an IMP test failure — that exact thing happened on
2026-08-10 with two stray files.

# What is enforced, and what is prose

Three rules are tests, because a rule nobody can run is a rule that rots. Each
lives in the repository it constrains, so it needs no sibling checkout to run —
six FRET tests fail in this tree today for precisely that mistake, needing an
`../olga` that is not on this machine.

| Rule | Where |
|---|---|
| tttrlib imports nothing from IMP, imp.bff or chisurf | tttrlib |
| imp.bff imports and its core API works with tttrlib absent | imp.bff |
| no imp-tricks name replaces one IMP already provides | imp-tricks |

The other two are prose on purpose. "chisurf owns no algorithms" cannot be
tested without a definition of *algorithm*, and a test that fails on 38k lines
of existing debt is a test that gets disabled within a week. That burn-down
belongs here.

# The IMP checkout itself

`/Users/tpeulen/dev/imp` is a clone of `salilab/imp` on `develop`, currently
**IMP 2.25** (`develop-345e71cb9a`, 2026-08-07), built from source because the
conda-forge `imp` package cannot supply `IMP.bff` — see
[workflows/imp-local-build](../workflows/imp-local-build.md).

Two deliberate, permanent local modifications, neither a mistake to clean up:

| Path | State |
|---|---|
| `modules/bff` | **symlink** → `../../imp.bff`, replacing the git submodule, so the module builds from the editable sibling checkout |
| `.gitignore` | adds `build`, `cmake_modules`, `cmake-build*` |

`git status` therefore reports `typechange: modules/bff` permanently, and
`git config submodule.modules/bff.update none` stops both `git pull` and IMP's
`post-checkout` hook from replacing the symlink.

`cmake-build-arm64/` is the live build. `build/` and `cmake-build-Debug/` are
**dead** — they target conda environments that no longer exist and import
nothing.
