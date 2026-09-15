---
type: PRD
prd: "93"
title: "PRD-93: The clean four-repository split — tttrlib, imp.bff, imp-tricks, chisurf"
description: The scope boundaries are settled and three of them are enforced by tests, but the code has not moved. This PRD is the ordered work to make the tree match the rule — cgdye out of imp-tricks, κ² consolidated in imp.bff, decay finished off, and chisurf's 38k-line fluorescence library migrating by attrition.
status: in-progress
phase: "stages 0-2 done (boundaries, guards, cgdye + rotamer library, externals dropped, kappa-squared consolidated, IMP mandatory); stages 3-4 open"
resource: okf/references/imp-ecosystem.md
tags: [prd, scope, architecture, imp.bff, imp-tricks, tttrlib, migration]
timestamp: '2026-08-10T00:00:00Z'
---

# Where to pick this up

**Stages 0, 1 and 2 are done.** What remains is stage 3 (a measurement) and
stage 4 (attrition, deliberately never a single move).

Done, with the commits:

| | |
|---|---|
| boundaries settled, 3 rules enforced by tests | chisurf `789117879`, `1ec04bc24` |
| cgdye + fps.py + 45 MB rotamer library into imp.bff | imp.bff `8fac573`, imp-tricks `34cf4de` |
| cgdye's externals dropped to IMP + numpy + click | imp.bff `46f49c0`, `1ac2073` |
| decay wrapper deprecated; 4 value classes fixed | imp.bff `1a14a22` |
| κ² whole in imp.bff; PathMapHeader made a value | imp.bff `47a08b7`, chisurf `987b0d977` |
| IMP mandatory in chisurf, declared in all 3 manifests | chisurf `c0a610e17` |
| memory: AV PathMap leak, 8 operator leaks, 3 double-free hazards | imp.bff `5ae7716` |

imp.bff `dev` is pushed to `Fluorescence-Tools/IMP.bff`; everything else is
local.

**Stage 3 — the AV duplication, ~2.4k lines.** Still in imp-tricks under
`IMP/bff/`: `av` (1391 lines), `restraints` (469), `label` (344),
`distance_metrics.py` (261), `polymer.py` (212), `distributions.py` (169).
These are *additions*, so the add-never-replace guard passes and nothing is
broken — but AV is structure, and structure is imp.bff's. The open question is
not where it belongs but whether the Python `BasicAV`/`ACV` are a faster path
to the same answer as the C++ `AV`/`PathMap` or a genuinely different one
(point-cloud AV, accessible *contact* volume with trapped fraction). **Measure
before moving.**

**Stage 4 — chisurf's `core/fluorescence`, 38,384 lines.** Unchanged in size,
and that is the plan: it moves by attrition, not by a migration. The rule binds
new code now; existing code moves when it is already being touched. κ²'s two
functions are the only thing that has left so far, and they left because they
were touched.

**Standing hazards, both bit during this work:**

* Running `ctest` from the imp.bff *source* directory leaves `CMakeCache.txt`,
  `CMakeFiles/` and `Testing/` there, and IMP refuses an in-source build. Build
  and test from `imp/cmake-build-arm64`.
* Two sessions committing in one chisurf worktree delete each other's new files:
  a commit builds its tree from the *shared* index, so a file another session
  committed but never added there is dropped by your next commit. Sync the
  shared index after any isolated commit.

# Why

Four repositories hold one stack, and until 2026-08-10 nobody could say which
owned what. The cost was not theoretical. `AVNetworkRestraintWrapper` was
recorded in [known-issues](/references/known-issues.md) as a deleted upstream
API for five days while the class sat in the build tree, ten ChiSurf tests
failed on it, and the actual cause — imp-tricks' `IMP/bff/restraints` standing
in front of imp.bff's — is invisible unless you think to print `__path__`.

The rule now is a layering, with a placement test and a tiebreaker:

```
tttrlib → imp.bff → imp-tricks → chisurf
```

*What is the input?* Photons or curves → tttrlib. Coordinates → imp.bff.
Neither, it is a workflow → chisurf. *When input and consumer disagree, the
consumer wins.*

This PRD is the work of making the tree match that.

# Stage 1 — unblocked, small, do now

Each item is independent. None needs a decision, none is large.

1. **Delete `imp.bff/pyext/src/spectroscopy/decay.py`** (283 lines). Decay moved
   to tttrlib and the eleven C++ `Decay*` headers are already deprecated at
   2.25. Measured: **nothing imports it** — not imp.bff, not imp-tricks, not
   chisurf. It is dead code sitting in the module's public namespace.
2. **Give the four structure value-classes real SWIG declarations.**
   `AVPairDistanceMeasurement`, `PathMapHeader`, `PathMapTile`,
   `PathMapTileEdge` are on `value_object_exceptions` in
   `imp.bff/test/standards_exceptions`, meaning Python has no memory-management
   contract for them. They are structure-side and keep-forever; give them
   `IMP_SWIG_VALUE` and strike the four entries. (The decay half of that list
   leaves with the deprecated classes — do not "fix" those.)
3. **Move κ²'s two stragglers out of chisurf.**
   `kappa2_to_distance_ratio` and `convolve_distance_with_k2_ratio` in
   `chisurf/core/fluorescence/general.py` → `imp.bff/pyext/src/spectroscopy/`.
   κ² is imp.bff's whole, by the consumer-wins tiebreaker.
   `core/models/anisotropy_to_kappa.py` **stays** — it is a
   `FittingParameterGroup`, an app-layer adapter, not physics.
4. **Upstream the SWIG 4.3 fix.** `imp.bff` `dev` carries a vendored `numpy.i`
   adapted to the `SWIG_Python_AppendOutput` arity change. That break hits
   *anyone* building imp.bff with SWIG ≥ 4.3, and the wrong sign of the
   `is_void` flag silently returns `[None, array]` from every argout-array
   function. It should not live only on a local branch.
5. **Re-apply the commit guard after any `setup_git.py` run.** IMP's
   `setup_git.py` regenerates `.git/hooks/`, removing the `pre-commit` hook that
   enforces the golden rule. Cheap to lose, expensive to notice.

# Stage 2 — cgdye moved (done)

`cgdye` is in imp.bff: 67 Python files under `pyext/src/cgdye`, plus `fps.py`,
which its rotamer package was the only external dependency on and which reads the
same fps.json `AVNetworkRestraint` already parses in C++.

**The open question is answered: the rotamer library is data.** Untracking the
vendored `thirdparty/` had exposed that `rotamer/r0.py`, `rotamer/io.py`,
`cli.py` and `scripts/label_protein.py` *load* `.dcd` trajectories, weight files,
R0 CSVs and `libraries.yml` from it at run time — three by walking up from
`__file__`, one through the import path
`IMP.bff.cgdye.thirdparty.FRETpredict...`, all of which broke the moment the
module moved. It ships as IMP module data at `data/rotamer_library` (45 MB, 227
files) and every loader now goes through `IMP.bff.get_data_path`, so none depends
on where the package sits.

`scripts/migrate_reference_libs.py` was dropped rather than moved: a one-off
migration for a layout that no longer exists.

**Left over, and now stage 1's fifth item**: cgdye's externals (`Bio`,
`MDAnalysis`, `click`, `numba`) are neither declared nor guarded. IMP.bff ships
through conda-forge as part of IMP, where the runtime dependency list is a public
contract, so each has to be declared, guarded, or dropped — it cannot simply
arrive.

# Stage 3 — resolve the AV duplication

imp-tricks ships `IMP/bff/av` (1391 lines: `BasicAV`, `ACV`, `compute_av`,
numba kernels) while imp.bff has AV in C++ (`IMP.bff.AV`, `PathMap`). These are
*additions*, not replacements, so they are legal under the rule and the guard
passes — but AV is structure, and structure is imp.bff's.

The question is not where it belongs but whether the Python implementations are
a faster path to the same answer or a genuinely different one (point-cloud AV
and accessible **contact** volume with trapped fraction). Measure both against
the C++ before deciding whether to fold them in, keep them as an imp-tricks
extension, or replace one with the other.

# Stage 4 — chisurf's fluorescence library, by attrition

`chisurf/core/fluorescence` is 38,215 lines across 100 files; `core/models` is
24,349; `core/structure` 8,160. Under the rule most of the first belongs in
tttrlib and the structure-facing part in imp.bff.

**This does not get a migration.** The rule binds *new* code immediately — new
physics goes to the owning library and chisurf imports it — and existing code
moves when it is already being touched, or when a second consumer appears. A
big-bang evacuation of 38k lines breaks every plugin, notebook and saved project
at once, during a window in which nothing new works either. Attrition turns an
unbounded risk into a bounded per-change cost.

The burn-down lives in [references/imp-ecosystem](/references/imp-ecosystem.md),
not here, so it stays next to the rule it serves.

Rough shape of where it goes, for when a file is touched:

| chisurf area | owner |
|---|---|
| `burst`, `mfd`, `pda`, `pda3c`, `fcs`, `tcspc`, `decay*`, `mle` | tttrlib |
| `anisotropy`, `dyes`, `fret`, κ² in `general.py` | imp.bff |
| `imaging`, `diffusion`, `kinetics`, `simulation`, `crosstalk`, `curation` | unclassified — decide when touched |

# Definition of done

* No `IMP.bff.*` name is provided by two repositories, and the imp-tricks guard
  proves it on every run.
* `imp.bff` contains cgdye, all of κ², and no decay.
* `chisurf/core/fluorescence` is shrinking monotonically, with each move
  recorded in `okf/log.md`.
* `git log origin/develop..HEAD` in the IMP checkout is empty — permanently.

# What is already enforced

| Rule | Where | Verified to fail on |
|---|---|---|
| tttrlib's shipped code imports nothing upward | `tttrlib/test/test_no_upward_imports.py` | a probe importing `IMP.bff` |
| tttrlib is optional inside imp.bff | `imp.bff/test/test_tttrlib_is_optional.py` | an unguarded module-level `import tttrlib` |
| imp-tricks adds, never replaces | `imp-tricks/tests/package_imports/test_adds_never_replaces.py` | a module named as one imp.bff provides |
| no commits in the IMP checkout | `imp/.git/hooks/pre-commit` | an actual `git commit` |

"chisurf owns no algorithms" is deliberately **not** a test: it cannot be
written without defining *algorithm*, and a test that fails on 38k lines of
existing debt is one that gets disabled within a week.

# Note from imp.bff (2026-08-17, PRD-107)

The cgdye externals item is closed on the imp.bff side: `Bio`, `MDAnalysis`
and `numba` are gone; `click` is declared in `conda-recipe/meta.yaml` and is a
CLI-only dependency — the library imports without it
(`cgdye/utils.import_click`, proven by `test/cgdye/test_shipped_files_compile.py`).
