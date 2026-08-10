## Five red tests in `test/fluorescence`, unrelated to what found them

**Found 2026-08-10** while porting `chisurf/core/fluorescence/general.py` off
numba. They fail identically with the pre-change file in place — verified by
swapping `git show HEAD:...general.py` in, re-running, and restoring — so they
are **not** caused by that work, and fixing them inside it would have made an
unrelated change unreviewable.

* `test_mfd_burst_roundtrip.py` — all four tests die at
  `chisurf/core/fluorescence/mfd/prepare.py:491` with
  `FileNotFoundError: no .bur tables under <tmpdir>/burst-pipeline0`. The
  pipeline the fixture runs produces no `.bur` output at all, so every
  assertion downstream of it is untested rather than passing. Whatever changed
  in the burst writer, the reader is reporting it correctly; the fixture is the
  thing to look at first.
* `test_gopich_szabo.py::test_no_exchange_reduces_to_a_static_mixture` — the
  likelihood comes back `-inf` where `-3.66516292749662` is expected. `-inf` is
  the numba kernel's own numerical-failure sentinel
  (`_total_log_likelihood` breaks out and returns it), so this is the guarded
  path firing, not an assertion drifting. Note this module is due to be
  delegated to `tttrlib.GopichSzabo`, whose branch at `gopich_szabo.py:522-537`
  is already preferred when available — check whether the compiled path gives
  the expected value before debugging the kernel that is being deleted.

Neither is a regression from the numba retirement, and neither should be
counted as one when that work reports its test results.

## Stale generated plugin reference pages after the `sm_image_mle` rename

**Found 2026-08-10** while adding a guide, by running
`chisurf/plugins/core/help/test/test_docs_crosslinks.py`. Three of its
assertions fail, and **none of them is caused by the change that found them**:

* `docs/reference/plugins/sm_image_mle.md` describes a plugin that no longer
  exists — `chisurf/plugins/microscopy/sm_image_mle/` is gone, renamed to
  `region_mle`. The page is **generated**
  (`generator: build_tools/docs/generate_plugin_docs.py`) and no
  `region_mle.md` has been generated to replace it, so the reference section
  documents a plugin nobody can open and omits the one that exists.
* `docs/reference/plugins/region_properties.md` points at the same dead path.
* `docs/guides/64_notebooks.md` links to no concept page, and
  `docs/concepts/deconvolution.md` trips the third assertion.

**The fix is one command** — `pixi run -e docs docs-plugins` — but it rewrites
every plugin reference page at once, which cannot land cleanly inside an
unrelated change. Whoever owns the `region_mle` rename should run it and delete
the stale page; the two link failures want a concept cross-reference adding.

## RESOLVED 2026-08-10 — importing chisurf broke every subprocess that draws an icon

**The symptom** was a bus error that made no sense: constructing
`CodeEditorWindow` in a subprocess crashed *deterministically* when the parent
was pytest and *never* when the same snippet was run from a shell. Not memory,
not the disk, not `QT_PLUGIN_PATH` — each of those was tested and cleared.

**The cause** was `chisurf/core/settings/env_bootstrap.py`, imported by
`chisurf.core.settings` and therefore by everything: on macOS it prepended the
environment's `lib` to **`DYLD_LIBRARY_PATH`** as well as to
`DYLD_FALLBACK_LIBRARY_PATH`. Those two are not variants of one idea:

- `DYLD_FALLBACK_LIBRARY_PATH` is consulted *after* normal resolution fails, so
  it can rescue a library that would not be found and cannot displace one that
  would;
- `DYLD_LIBRARY_PATH` is searched *first*, so it overrides what each extension
  module was linked against.

dyld reads both once, at process start. So setting `DYLD_LIBRARY_PATH` did
nothing for the process that set it — and silently re-pointed library
resolution for **every child it spawned**. In such a child, Qt's font engine
binds to the wrong library and the first `create_text_icon` call bus-errors
(`chisurf/plugins/icon_utils.py`), taking down anything that draws an emoji
icon: a spawned tool, a headless render, `csc`, a per-tool test.

**Fixed** by keeping only the fallback variable. Verified: the icon renders with
neither variable and with the fallback alone, and crashes with
`DYLD_LIBRARY_PATH` — and `test/fio` + `test/core` still pass 1629 tests with
zero loader errors afterwards, so nothing depended on the override. Guarded by
`test/test_env_bootstrap_dyld.py`.

**Not** the cause of the separate `test/gui` crash below: that suite still
segfaults without either variable.

## Every plugin GUI tool constructs, except mmfdb_admin, which blocks

**2026-08-10.** Measured by building all 114 tools the manifests declare, each
in its own process: **111 construct, 1 blocks, 2 failed** (both since fixed —
see below). None opens a metadata-store connection while constructing, so
PRD-23's read-only-construction rule holds everywhere else.

**`mmfdb_admin` performs four blocking RPCs while building** — `mmfdb.status`
twice (its Overview panel, loaded eagerly by the navigation shell),
`mmfdb.users.list` (the admin gate in `_verify_admin_access`) and
`mmfdb.security.auth.login` (`_ensure_authenticated`), both called directly
from `__init__`. With no server up each waits out the 5 s client timeout, so
opening the tool freezes for ~20 s and looks like a hang.

Not fixed here, deliberately: `_verify_admin_access` is a permission gate, and
deciding where it should fire when the tool is opened without a server is a
design call inside a security-sensitive tool, not a mechanical deferral. The
shape of the fix is the one used for `ProjectBrowserTool` — post the work
instead of doing it in `__init__` — plus a lazy Overview panel.

Tracked by `BLOCKING` in `test/gui/test_every_tool_constructs.py`; that test
fails if the tool starts constructing cleanly, so the entry cannot outlive the
defect.

**Two tools segfault while constructing** — `psf_calculator` (in
`PSFComputation.run`, the vectorial PSF scheduled on a `QThreadPool` worker from
`__init__`) and `lightpath_simulator` (aborts, then segfaults). Both reproduce
standalone, not only under pytest, and both start background work during
construction — the side effect the read-only-construction rule forbids, and the
likely mechanism: the worker outlives the objects it touches. Tracked by
`CRASHING` in the same test.

**Fixed in passing:** `acq` (SM Acquisition) crashed with
`AttributeError: 'NoneType' object has no attribute '_acquisition_manager'` —
it keyed "are we inside chisurf?" on `import chisurf` succeeding, which it
always does, rather than on `chisurf.cs` existing, which it does not until the
main window is built.

## A simulated photon stream cannot be persisted, and the HDF5 path aborts the process

**Found 2026-08-10** while capturing a pre-split baseline for
[PRD-92](/prds/prd-92.md), which wanted the simulated CLSM stream stored beside
the labels it produced so an equivalence test could re-derive the whole chain
rather than its two ends.

**`TTTR.write` itself is fine**, including the `"PTO"` container: a stream read
from a real file (`m000.spc`, 174,438 photons) writes a 1.2 MB `.pto` and a
1.2 MB `.spc`, both returning `True`. The limitation is specific to a stream
**built in memory** — what `simulate_clsm_molecules` returns. It carries
`get_tttr_record_type() == -1`, `TTTRHeader.ensure_minimal_tags(header, 20, n)`
does not give it one, and PTO header writing is not implemented in the installed
build (`Error in TTTR::write, writing of headers not implemented`). The write
then returns `False` and leaves a **0-byte file**, with nothing raised — so a
caller that does not check the return value gets an empty container and
discovers it later.

**The HDF5 path is worse and is a separate defect.** `tttr.write(path)` with the
HDF5 default `abort()`s the interpreter — the installed tttrlib was compiled
against HDF5 headers 1.14.6 and links a 2.1.1 library, and the library's version
check kills the process rather than raising. A dependency mismatch should not be
able to end a user's session.

Neither is worked around in ChiSurf, and neither should be: **ChiSurf persists
to `.mmfdb.pto`**, and the container writers (`Measurement.create`,
`write_imaging_table`, `write_image`, `write_regions`) all embed files that
already exist on disk, so nothing in the shipped tree hits either path. It is
recorded because the *tests* want it — a simulated measurement that cannot be
stored is a fixture that has to be a pile of derived arrays instead — and
because the next person to try will spend the same half hour on `record type -1`.

Fix belongs in tttrlib: a record type for in-memory streams (or a PTO header
writer), and an HDF5 version check that raises instead of aborting.

## `test/gui/test_chiplot.py` segfaults in the shared working tree, and not from chiplot

**Found 2026-08-10** while landing the WebGPU plot backend. `pytest
test/gui/test_chiplot.py` reports **56 passed** and then dies with
`Fatal Python error: Segmentation fault` during garbage collection, inside a
pyqtgraph `ViewBox` weakref lambda or an `InfiniteLine.boundingRect`. Rate in
the working tree: **5–8 of 8 runs**.

**It is not the chiplot changes.** A clean `git worktree` at HEAD carrying the
*entire* WebGPU backend, its 31 tests, the pyqtgraph SI-prefix and legend fixes,
and every uncommitted chiplot source edit (`canvas.py`, `handles.py`,
`backends/base.py`, `backends/pyqtgraph_backend.py`) runs the four chiplot-related
suites **0 crashes in 8 runs**. Adding the working tree's `chisurf/gui/__init__.py`
and settings edits on top: still 0 in 6. The trigger is one of the other several
dozen files another agent instance has in flight, and it was not found.

**The trap, which cost most of a session.** The crash is a *latent* pyqtgraph
teardown defect — abandoned panels whose finalizers touch Qt objects C++ has
already deleted — so it fires inside **whatever happens to allocate next**, and
the traceback names that caller. It pointed at the WebGPU driver's cffi
initialisation, then at a legend, then at an axis. Each looked like a specific
bug in the code being written. Two rules follow:

* **Never add a `gc.collect()` to "fix" it.** Doing so converts a probabilistic
  crash into a deterministic one at the collect site, and the new site looks
  even more like the culprit.
* **Bisect in a clean worktree, not by editing the shared tree.** Six A/B
  measurements at 6–8 runs each were run against a baseline that was already
  crashing, so every one of them was noise. The clean-worktree comparison
  settled it in two runs.

Whoever owns the in-flight change should re-measure; until then, run
`test/gui/test_chiplot.py` in its own pytest invocation.

## 33 of the MMFDB suite's failures are test-order contamination, not defects

**Found 2026-08-10** while adding three enumeration terms to
`mmfdb_flr_ext.dic` for the region/spot container contract
([PRD-92](/prds/prd-92.md)) and checking what that broke. `pytest tests` in
`modules/mmfdb` reports **33 failed / 757 passed**, concentrated in four files:
`test_mmfdb_user_management.py` (14), `test_security_architecture.py` (10),
`test_zip_archive_export.py` (6), plus one each in `test_fdb_general.py`,
`test_fdb_setups.py`, `test_mmcif_database_resolver.py`.

**Every one of them passes when its file is run alone** — the two largest were
checked directly (`test_mmfdb_user_management.py` + `test_security_architecture.py`
→ 40 passed), as was `test_zip_archive_export.py` (6 passed). So the suite is
carrying process-wide state between files, most likely an auth/session or
database singleton, in the same family as the `_DISPLAY_CONFIG` contamination
already recorded for ChiMOL: one test's leftovers break *other files*, which is
why bisecting with `-k` finds nothing.

**Not fixed here**, and not caused by the dictionary change (that adds three
enum values and a comment; the failures are in user management, security and
zip export, none of which read the enumeration). Recorded because the number is
large enough to look like a regression to whoever runs the suite next, and
because it means the suite currently cannot tell a real breakage from this
noise. Whoever fixes it should bisect by explicit node ids across *files*, not
within one.

## The OpenGL point glyph renders at half the size it is asked for

**Found 2026-08-10** while porting point geometry to the WebGPU backend, by
comparing the same scene through both renderers.

`dots` on 148L carries `meta["size"] = 8.0`. `qtgl` sets both `gl_PointSize` and
`glPointSize` to `size * devicePixelRatioF()`, and the fragment shader keeps the
inscribed circle of the sprite, so the dot should be **8 px across**. Measured on
`test/renders/gl_baseline/dots_view.png`, the modal lit run per row is **4 px**
(2,112 rows at 4, tailing off by 8). Ruled out: the device pixel ratio is
genuinely `1.0` for both the window and the GL widget, and
`GL_ALIASED_POINT_SIZE_RANGE` is `[1, 64]`, so neither scaling nor clamping
explains it. Apple's GL-over-Metal sprite path is the remaining suspect.

**Not fixed here, deliberately.** The fix would change what `qtgl` draws and
invalidate the `dots` baseline in the same change that uses that baseline as a
reference. The WebGPU renderer already draws the documented size (8 px for
`size = 8`), so this is a difference the port *corrects*; it is recorded here so
the next person comparing the two does not read the correct half as a regression.
Whoever retires `qtgl` retires this with it.

## `test/gui` crashes the interpreter mid-run, and 20 of its failures are contamination

**2026-08-10.** `pytest test/gui` dies with `Bus error: 10` (exit 138) at around
44 %, just after `test_language_selector`, and reports ~22 failures before it
does. Almost none of that is real:

- **The failures are mostly cross-test contamination.** Two of three sampled
  failures (`test_dialogs_and_progress::test_confirm_declines_by_default`,
  `settings/test_log_filter::test_log_list_widget_uses_multiple_columns`) **pass
  when run on their own**. Judge a `test/gui` failure by re-running that test
  alone before believing it.
- **The one real failure sampled** is `ParseFCSModel object has no attribute
  'get_plot_reference_modes'` (raised from `chisurf/core/base.py`), i.e. an FCS
  model/plot-reference API mismatch — not a GUI defect.
- **A second, separate crash** appears when several plugin suites are combined in
  one process: `chisurf/plugins/{tttr,pch,core/project_browser,burst/...}` plus
  the dock suites run to ~89 % **with zero failures** and then take
  `Segmentation fault: 11` in teardown. Split into two invocations, the same
  tests are 146 + 254 passed. Same shape as the `fret_trajectory` entry below.

So a red `test/gui` is not evidence that a change broke something. Until the
contamination and the two crashes are fixed, verify a GUI change by running the
suites that cover it, individually, and say which ones.

## A simulated photon stream cannot be persisted, and the HDF5 path aborts the process

**Found 2026-08-10** while capturing a pre-split baseline for
[PRD-92](/prds/prd-92.md), which wanted the simulated CLSM stream stored beside
the labels it produced so an equivalence test could re-derive the whole chain
rather than its two ends.

**`TTTR.write` itself is fine**, including the `"PTO"` container: a stream read
from a real file (`m000.spc`, 174,438 photons) writes a 1.2 MB `.pto` and a
1.2 MB `.spc`, both returning `True`. The limitation is specific to a stream
**built in memory** — what `simulate_clsm_molecules` returns. It carries
`get_tttr_record_type() == -1`, `TTTRHeader.ensure_minimal_tags(header, 20, n)`
does not give it one, and PTO header writing is not implemented in the installed
build (`Error in TTTR::write, writing of headers not implemented`). The write
then returns `False` and leaves a **0-byte file**, with nothing raised — so a
caller that does not check the return value gets an empty container and
discovers it later.

**The HDF5 path is worse and is a separate defect.** `tttr.write(path)` with the
HDF5 default `abort()`s the interpreter — the installed tttrlib was compiled
against HDF5 headers 1.14.6 and links a 2.1.1 library, and the library's version
check kills the process rather than raising. A dependency mismatch should not be
able to end a user's session.

Neither is worked around in ChiSurf, and neither should be: **ChiSurf persists
to `.mmfdb.pto`**, and the container writers (`Measurement.create`,
`write_imaging_table`, `write_image`, `write_regions`) all embed files that
already exist on disk, so nothing in the shipped tree hits either path. It is
recorded because the *tests* want it — a simulated measurement that cannot be
stored is a fixture that has to be a pile of derived arrays instead — and
because the next person to try will spend the same half hour on `record type -1`.

Fix belongs in tttrlib: a record type for in-memory streams (or a PTO header
writer), and an HDF5 version check that raises instead of aborting.

## `test/gui/test_chiplot.py` segfaults in the shared working tree, and not from chiplot

**Found 2026-08-10** while landing the WebGPU plot backend. `pytest
test/gui/test_chiplot.py` reports **56 passed** and then dies with
`Fatal Python error: Segmentation fault` during garbage collection, inside a
pyqtgraph `ViewBox` weakref lambda or an `InfiniteLine.boundingRect`. Rate in
the working tree: **5–8 of 8 runs**.

**It is not the chiplot changes.** A clean `git worktree` at HEAD carrying the
*entire* WebGPU backend, its 31 tests, the pyqtgraph SI-prefix and legend fixes,
and every uncommitted chiplot source edit (`canvas.py`, `handles.py`,
`backends/base.py`, `backends/pyqtgraph_backend.py`) runs the four chiplot-related
suites **0 crashes in 8 runs**. Adding the working tree's `chisurf/gui/__init__.py`
and settings edits on top: still 0 in 6. The trigger is one of the other several
dozen files another agent instance has in flight, and it was not found.

**The trap, which cost most of a session.** The crash is a *latent* pyqtgraph
teardown defect — abandoned panels whose finalizers touch Qt objects C++ has
already deleted — so it fires inside **whatever happens to allocate next**, and
the traceback names that caller. It pointed at the WebGPU driver's cffi
initialisation, then at a legend, then at an axis. Each looked like a specific
bug in the code being written. Two rules follow:

* **Never add a `gc.collect()` to "fix" it.** Doing so converts a probabilistic
  crash into a deterministic one at the collect site, and the new site looks
  even more like the culprit.
* **Bisect in a clean worktree, not by editing the shared tree.** Six A/B
  measurements at 6–8 runs each were run against a baseline that was already
  crashing, so every one of them was noise. The clean-worktree comparison
  settled it in two runs.

Whoever owns the in-flight change should re-measure; until then, run
`test/gui/test_chiplot.py` in its own pytest invocation.

## `test/gui/test_chiplot.py` segfaults in the shared working tree, and not from chiplot

**Found 2026-08-10** while landing the WebGPU plot backend. `pytest
test/gui/test_chiplot.py` reports **56 passed** and then dies with
`Fatal Python error: Segmentation fault` during garbage collection, inside a
pyqtgraph `ViewBox` weakref lambda or an `InfiniteLine.boundingRect`. Rate in
the working tree: **5–8 of 8 runs**.

**It is not the chiplot changes.** A clean `git worktree` at HEAD carrying the
*entire* WebGPU backend, its 31 tests, the pyqtgraph SI-prefix and legend fixes,
and every uncommitted chiplot source edit (`canvas.py`, `handles.py`,
`backends/base.py`, `backends/pyqtgraph_backend.py`) runs the four chiplot-related
suites **0 crashes in 8 runs**. Adding the working tree's `chisurf/gui/__init__.py`
and settings edits on top: still 0 in 6. The trigger is one of the other several
dozen files another agent instance has in flight, and it was not found.

**The trap, which cost most of a session.** The crash is a *latent* pyqtgraph
teardown defect — abandoned panels whose finalizers touch Qt objects C++ has
already deleted — so it fires inside **whatever happens to allocate next**, and
the traceback names that caller. It pointed at the WebGPU driver's cffi
initialisation, then at a legend, then at an axis. Each looked like a specific
bug in the code being written. Two rules follow:

* **Never add a `gc.collect()` to "fix" it.** Doing so converts a probabilistic
  crash into a deterministic one at the collect site, and the new site looks
  even more like the culprit.
* **Bisect in a clean worktree, not by editing the shared tree.** Six A/B
  measurements at 6–8 runs each were run against a baseline that was already
  crashing, so every one of them was noise. The clean-worktree comparison
  settled it in two runs.

Whoever owns the in-flight change should re-measure; until then, run
`test/gui/test_chiplot.py` in its own pytest invocation.

## 33 of the MMFDB suite's failures are test-order contamination, not defects

**Found 2026-08-10** while adding three enumeration terms to
`mmfdb_flr_ext.dic` for the region/spot container contract
([PRD-92](/prds/prd-92.md)) and checking what that broke. `pytest tests` in
`modules/mmfdb` reports **33 failed / 757 passed**, concentrated in four files:
`test_mmfdb_user_management.py` (14), `test_security_architecture.py` (10),
`test_zip_archive_export.py` (6), plus one each in `test_fdb_general.py`,
`test_fdb_setups.py`, `test_mmcif_database_resolver.py`.

**Every one of them passes when its file is run alone** — the two largest were
checked directly (`test_mmfdb_user_management.py` + `test_security_architecture.py`
→ 40 passed), as was `test_zip_archive_export.py` (6 passed). So the suite is
carrying process-wide state between files, most likely an auth/session or
database singleton, in the same family as the `_DISPLAY_CONFIG` contamination
already recorded for ChiMOL: one test's leftovers break *other files*, which is
why bisecting with `-k` finds nothing.

**Not fixed here**, and not caused by the dictionary change (that adds three
enum values and a comment; the failures are in user management, security and
zip export, none of which read the enumeration). Recorded because the number is
large enough to look like a regression to whoever runs the suite next, and
because it means the suite currently cannot tell a real breakage from this
noise. Whoever fixes it should bisect by explicit node ids across *files*, not
within one.

## The OpenGL point glyph renders at half the size it is asked for

**Found 2026-08-10** while porting point geometry to the WebGPU backend, by
comparing the same scene through both renderers.

`dots` on 148L carries `meta["size"] = 8.0`. `qtgl` sets both `gl_PointSize` and
`glPointSize` to `size * devicePixelRatioF()`, and the fragment shader keeps the
inscribed circle of the sprite, so the dot should be **8 px across**. Measured on
`test/renders/gl_baseline/dots_view.png`, the modal lit run per row is **4 px**
(2,112 rows at 4, tailing off by 8). Ruled out: the device pixel ratio is
genuinely `1.0` for both the window and the GL widget, and
`GL_ALIASED_POINT_SIZE_RANGE` is `[1, 64]`, so neither scaling nor clamping
explains it. Apple's GL-over-Metal sprite path is the remaining suspect.

**Not fixed here, deliberately.** The fix would change what `qtgl` draws and
invalidate the `dots` baseline in the same change that uses that baseline as a
reference. The WebGPU renderer already draws the documented size (8 px for
`size = 8`), so this is a difference the port *corrects*; it is recorded here so
the next person comparing the two does not read the correct half as a regression.
Whoever retires `qtgl` retires this with it.

## `test/gui` crashes the interpreter mid-run, and 20 of its failures are contamination

**2026-08-10.** `pytest test/gui` dies with `Bus error: 10` (exit 138) at around
44 %, just after `test_language_selector`, and reports ~22 failures before it
does. Almost none of that is real:

- **The failures are mostly cross-test contamination.** Two of three sampled
  failures (`test_dialogs_and_progress::test_confirm_declines_by_default`,
  `settings/test_log_filter::test_log_list_widget_uses_multiple_columns`) **pass
  when run on their own**. Judge a `test/gui` failure by re-running that test
  alone before believing it.
- **The one real failure sampled** is `ParseFCSModel object has no attribute
  'get_plot_reference_modes'` (raised from `chisurf/core/base.py`), i.e. an FCS
  model/plot-reference API mismatch — not a GUI defect.
- **A second, separate crash** appears when several plugin suites are combined in
  one process: `chisurf/plugins/{tttr,pch,core/project_browser,burst/...}` plus
  the dock suites run to ~89 % **with zero failures** and then take
  `Segmentation fault: 11` in teardown. Split into two invocations, the same
  tests are 146 + 254 passed. Same shape as the `fret_trajectory` entry below.

So a red `test/gui` is not evidence that a change broke something. Until the
contamination and the two crashes are fixed, verify a GUI change by running the
suites that cover it, individually, and say which ones.

## 20 file types in `chisurf/` are missing from an installed distribution

**Found 2026-08-10** while adding `*.wgsl` for the chigame shader, which had the
same defect and would have shipped broken.

`[tool.setuptools.package-data]` is an allow-list of globs. Any extension not in
it is **not copied into an installed copy**, and nothing warns: the package keeps
working from a source checkout, so the failure only ever appears for someone who
installed it.

The ones that matter, because shipped code loads them at runtime:

* **`.ico`, `.icns`, `.bmp`, `.qrc`** — GUI icons and the Qt resource manifest;
* **`.ini`, `.yml`** — device configuration (the PicoQuant TCSPC device files)
  and plugin example configuration;
* **`.xlsx`, `.xlsm`, `.gnumeric`** — the potential-energy databases under
  `core/structure/potential/database/`;
* **`.c`, `.cpp`, `.h`** — the bundled AV kernel sources.

The rest (`.dcd`, `.pdb`, `.pml`, `.pdf`, `.pdat`, `.mti`, `.spc`, `.rmf3`,
`.bur`) are fixtures and reference material, so they matter less — but the sweep
does not distinguish, and neither does an install.

**Not fixed here** because the correct pattern differs per family: some want a
package-data glob, some belong in a fixture directory that is not installed at
all, and the `.qrc`/icon set may want compiling rather than copying. Deciding
that is a packaging change, not a side effect of adding a shader.

**Guarded**: `test/test_package_data_covers_shipped_files.py` holds these as a
**shrinking** `KNOWN_UNCOVERED` list and fails on any *newly* uncovered type, so
this cannot grow silently. A companion test fails when an entry becomes stale.
The fix for each is to add a pattern to `pyproject.toml` and strike the line.

## ✅ FIXED — ChiMOL ambient occlusion was wired the wrong way round

**Fixed 2026-08-10.** Kept here because the *first* diagnosis below was wrong in
an instructive way, and because one gap remains.

**What it actually was.** Not a stray `not`. The coarse per-residue estimate at
`view.py` is a deliberate **fallback** for when the fine per-vertex bake does not
run — its own comment says running both would darken the cartoon twice — but it
was gated on `not enabled` while the fine bake contributed *nothing* to a tube
cartoon. So the fallback was the only occlusion a cartoon ever received, and it
appeared exactly when the user asked for none. Flipping the `not`, which is what
the first diagnosis proposed, would have deleted the only working AO.

**The fix.** `_occlusion_enabled()` is now the single reader of
`occlusion.enabled`; `_estimate_ambient_occlusion` is wrapped in `view.py` so all
**six** call sites honour it (only one consulted it before, and five shaded
regardless); and the coarse path asks `_per_vertex_occlusion_available()` rather
than a second, disagreeing condition — which preserves the no-double-darkening
intent in both directions. `sticks.ambient_occlusion` is deleted: a second switch
for the same concept, read by nothing, and sticks bake no occlusion for it to
turn on. Guarded by `test/test_occlusion_switch.py`, which asserts **both**
directions — a test that only checks "the image changed" passes an inverted
switch, which is how this survived.

Measured after, on lit pixels only: cartoon 91.05 on / 142.66 off, spheres 109.74
/ 158.96, surface 106.78 / 109.49 — on darkens in every case.

**Still open: `sticks` has no ambient-occlusion path at all** (toggling the switch
changes exactly 0 pixels). That is a missing feature, not a broken switch, and it
is why `sticks` is excluded from the guardrail's parametrisation.

**Two measurement traps worth keeping.** The first grab after a rebuild can be a
partially initialised framebuffer that comes back as *noise* — it poisoned a
brightness comparison until the image was looked at, and the fix is to discard one
grab. And the background is most of the frame, so a mean over the whole image
dilutes an inverted switch into what looks like rounding; compare lit pixels only.

## Superseded first diagnosis, and the other two settings

**2026-08-10.** Found while capturing the OpenGL render baselines before the
WebGPU port ([chimol-web](/plugins/chimol-web.md)). All three were measured with
matched A/B pairs that differ by one setting, not read off the source.

**1. `occlusion.enabled` is inverted.** The only gate is
`chimol/renderer/view.py:5441`:

```python
if not bool((_DISPLAY_CONFIG.get("occlusion") or {}).get("enabled", True)):
    occ_ca = _estimate_ambient_occlusion(...)
```

so ambient occlusion is computed when occlusion is switched **off**. Measured on
148L cartoon against a plain control: `enabled=on` is **0.00 %** different from
no-AO-at-all, `enabled=off` is **9.35 %** different with a max channel delta of
188. Turning the feature on turns it off.

The same line is the only gate in the file: the other three
`_estimate_ambient_occlusion` call sites (`view.py:5785, 6265, 7817`) are
**ungated entirely**, so sticks/surface/bead AO ignores the setting in both
directions. Fixing the `not` alone would therefore change cartoon only and leave
the setting still lying about the other three.

**Not fixed in the same change deliberately**: the fix changes what the renderer
draws, and it would invalidate the GL baselines being captured in that very
change — the baselines have to record what ships today, or the WebGPU port has
nothing to be compared against. It wants its own before/after pair.

**2. `sticks.ambient_occlusion` gates nothing.** It is registered, reachable via
`set sticks.ambient_occlusion, on`, and stores a value that no code reads — the
real key is `occlusion.enabled`. Measured: **0 pixels** change. Another instance
of "the setting is registered" and "the setting works" being different claims.

**3. `balls.impostor_min_atoms` does not apply to atomic spheres.** Not a defect —
`view.py:6026` reads it from `balls_cfg` and the docstring says *beads* — but it
means `show spheres` on a PDB never takes the point-sprite impostor path, so a
baseline for that path needs a bead/integrative model. Recorded because two
sphere scenes captured with `balls.impostor_min_atoms` at 100000 and at 10 came
out **bit-identical**, which looks like a broken setting until you find the
docstring.

## `test_prd_mentions` is red on three files that belong to another session

**2026-08-10.** `test/test_prd_mentions.py` fails on three files that name a PRD
in shipped source:

```
chisurf/gui/chiplot/backends/opengl/__init__.py
chisurf/plugins/burst/mfd_prepare/api/__init__.py
chisurf/plugins/burst/mfd_prepare/backend/services.py
```

All three are **untracked** — they are new files from other sessions' in-flight
work in the shared tree, so editing them would collide with whoever is writing
them. The fix is one line each (point at the OKF concept that owns the area, or
drop the reference) and belongs to the session that lands those files.

Not to be confused with a regression from the tool-window migration: that pass
*removed* a file from the allowlist (`chisurf_dock_tool.py`, 154 → 153 entries)
and added none.

## Registering a dropped measurement in MMFDB fails on a foreign key

**2026-08-07.** Dropping eleven `.spc` files into the burst workflow, with the
`tttr_to_pto` guard converting them, stores the object and then fails to
register it:

```
INFO  mmfdb.store.object_store - Stored new object: a3dbd6be... (13227189 bytes)
ERROR mmfdb.store.transactions - Database transaction failed and was rolled back: FOREIGN KEY constraint failed
ERROR root - MMFDB RPC failed: raw_data.register: FOREIGN KEY constraint failed
```

The object store keeps the blob; the metadata row is rolled back — so the
container is on disk and MMFDB does not know about it, which is the state that
makes "open it in ndX from MMFDB" fail later with nothing to point at. The
analysis itself continues, so nothing surfaces in the window.

Not diagnosed here: the failing constraint is not named in the message, and
`raw_data.register` lives in the **mmfdb repository** (`modules/mmfdb` is a
symlink to its own checkout), where the fix and its test belong. Whoever picks
it up should first turn the bare `FOREIGN KEY constraint failed` into a message
that says *which* key — SQLite will report it with
`PRAGMA foreign_key_check` after the failure — because the same message will
otherwise be re-diagnosed from scratch every time.

## `NUMBA_NUM_THREADS` collides when the fio suite runs as a whole

**2026-08-07.** `test/fio/test_vv_vh.py::test_vv_vh_spectrum_equals_concatenated_components`
and `test/fio/test_ndxplorer_rpc_bridge.py::test_lines_service_phasor_and_fret_over_inprocess_client`
fail with `RuntimeError: Cannot set NUMBA_NUM_THREADS to a different value once
the threads have been launched (currently have 7, trying to set 8)` when
`pytest test/fio` runs the directory, and **both pass in isolation**. Something
earlier in the directory launches numba's thread pool at 7 and something later
asks for 8; neither of the failing tests is the one setting it. Pre-existing and
unrelated to the burst/`.pto` work that surfaced it. The fix is to find the
setter and have it either run before any numba entry point or not set the count
at all — the same "one process-wide global, so one test breaks *other files*"
shape as chimol's `_DISPLAY_CONFIG`, and it wants the same treatment: bisect by
explicit node ids, not `-k`.

## Burst Selection's progress bar cannot advance within a single large file

**2026-08-07.** `analyze_request` (`chisurf/plugins/burst/burst_selection/api/selection.py`)
now reports progress **per file** to the GUI's `TaskHandle` (one file
finishing is the chunk it can report on), which fixed the busy-spinner feel
of a multi-file batch. It does **not** help a single very large file — a
merged multi-measurement `.pto` (easy to produce since the `tttr_to_pto`
drop guard landed the same day, see [PRD-85](/prds/prd-85.md)) or simply a
long acquisition still reports only once, at completion, because
`apply_photon_filters`/`find_bursts` inside `analyze_file` are each one
vectorized call over the whole photon stream with no internal chunking.

Not fixed here because it is a correctness risk, not a wiring gap: splitting
a burst search into windows requires carrying detector/burst-in-progress
state across window boundaries correctly, or a burst near a window edge
either gets cut in two or double-counted. `tttrlib`'s burst-search
implementations (`chisurf/core/fluorescence/burst/tttrlib_search.py`,
registry-driven) are compiled and offer no progress callback to hook into
either. Whoever picks this up should first check whether a newer `tttrlib`
exposes incremental/streaming burst search before attempting to chunk the
input in Python.

Separately, the fix deliberately did **not** thread
`TaskHandle.progress_window()`'s cancellation-aware `set_value` through this
path (only report-only `progress_callback`): `chisurf/server/dispatcher.py`'s
`ServiceDispatcher.dispatch` catches `except Exception` broadly and converts
*any* exception — including the `concurrent.futures.CancelledError` a
cancelled `progress_window.set_value()` raises — into an ordinary
`{"ok": False, "error_code": "INTERNAL_ERROR"}` result. `BurstSelectionClient.analyze_files`
then raises a plain `RuntimeError` from that, so cancelling a burst search
would show as a scary error message instead of the silent stop the rest of
the app gives you via `run_in_background`'s `CancelledError` handling. Giving
burst_selection real mid-search cancellation needs the dispatcher to let
`CancelledError` (or some other user-cancel signal) propagate instead of
being folded into a generic error — a dispatcher-level change, not a
burst_selection one, and worth checking whether any other RPC service
already depends on the current blanket-catch behaviour before changing it.

## Two `ParameterGroupTable*` GUI tests fail headless, unrelated to anything they test

**2026-08-07.** `test/gui/test_paired_table_layout.py::test_the_list_style_stacks_a_wide_component`
and `test/gui/test_parameter_table_wheel.py::test_a_long_table_can_still_be_scrolled`
fail deterministically under `QT_QPA_PLATFORM=offscreen`, both against a
`QtWarningMsg: This plugin does not support propagateSizeHints()` warning —
the first as a row-count mismatch after a delete (`4` instead of `2`), the
second as a scrollbar that never gains a range (`0 > 0`). Both look like the
offscreen platform plugin not computing real widget/viewport geometry, not a
behavioural regression: `chisurf/gui/autoform/sections/parameter_table.py`
(the module both tests exercise) imports only
`chisurf.gui.widgets.chitable.delegates`, which has no import of
`chitable.source` or `chitable.filters` at all — verified by grep, not by
reverting anything, since the working tree is shared with other sessions.
Found incidentally while checking chitable's own test suite for regressions
after removing chitable's module-level pandas import; not investigated
further because neither file was touched.

## img_flow: the demo PTU is one frame short of what it simulates

`test_the_demo_is_a_readable_ptu_whose_flow_comes_back` asks `create_demo` for
30 frames and `load_image_stack` reports 29. Pre-existing and deterministic —
it reproduces with no local changes to the plugin.

The cause is the marker convention rather than a lost frame. `demo.py` calls
`engine.run_scan(scanner)` once per frame and the simulator emits a frame
marker at the **start** of each, so 30 markers arrive. A CLSM reader builds a
frame from one marker to the next, which makes 30 markers 29 closed frames; the
last frame's photons are in the file with nothing to terminate them.

Not fixed here because the fix is not local. Emitting a 31st marker by running
one more scan would add that scan's photons too, so closing the last frame
means either a simulator API for a trailing marker (tttrlib's `SimScanner`) or
a reader that treats end-of-file as a frame boundary. Which of those is right is
a question about the simulator, not about this plugin, and changing the demo
changes both the guided tour's data and `expected_profile`.

Worth checking first: whether a real PTU from a scanner has a trailing frame
marker. If it does, the simulator is wrong; if it does not, the reader is, and
every measured file has been one frame short all along — which would be the
more interesting answer.

## RESOLVED — burst FCS: the `td4` companion was written on the bursts that produced a result, not on the bursts

**Discovered 2026-08-07, fixed the same day.** `_save_td4_results` in
`chisurf/plugins/burst/burst_fcs_correlator/wizard.py` built its row grid from
the correlations it computed, then zero-interleaved that. The
[burst-companion contract](../subsystems/burst-companions.md) requires **one
row per burst of the measurement, including the ones the analysis skipped** —
because the file is merged onto the burst table *by position*.

The function's own docstring already stated the consequence, which is why this
was recorded rather than merely discovered: "a burst the correlator skipped is
a missing row there rather than a blank one, so every burst after it is merged
against the wrong burst's diffusion time — silently, because the shape and the
column names stay right and only the attribution is wrong."

Two further deviations in the same function:

* it wrote the layout **by hand** (`out[1::2]`, `'\t'.join(cols) + '\t\n'`,
  `%.6f`) rather than through `burst_companion.write_companion`. That was the
  same divergence the `.bv4` writer had until 2026-08-07;
* the container written beside it (`_write_container`) was already **correct**
  — it carries `Burst Index` as a declared key, and is unaffected by this fix.

**The fix needed the burst count**, which the correlator did not hold at the
point the row grid was built. It turned out to already be available higher up:
`local_idx` (the row's `Burst Index`) comes from `enumerate(ranges)` where
`ranges` is the *full* per-measurement burst list `parse_bur_file`/
`parse_bst_file` returns — so `len(ranges)` is exactly the true grid size, no
second `.bur` read needed. `_run_burstwise_fcs` now threads that through as
`burst_counts: {(Burst Folder, First Stem): n_bursts}`, and
`_save_td4_results` allocates a full `(n_bursts, n_cols)` grid, fills in the
computed rows at their true `Burst Index` position, and writes it through
`burst_companion.write_companion` (which also fixed the by-hand layout). The
sparse, results-only table still goes to `_write_container` unchanged, since
its declared-key join was already correct.

Pinned by `chisurf/plugins/burst/burst_fcs_correlator/test/test_td4_writer.py`
(the layout test the original note asked for): a skipped burst reads back as a
sentinel row, not a missing one, and a computed burst keeps its true row
position rather than being compacted upward. Landed alongside the last three
[PRD-82](../prds/prd-82.md) pandas ports.

## acquisition: the SPC-130 record decoder exists twice, because the library exposes its own only behind a file reader

**2026-08-06.** `_process_bh_spc_records_numba` in
`chisurf/plugins/core/acq/gui/tool.py` is a hand-maintained numba copy of the
simulation library's `RecordProcessor<BH_RECORD_TYPE_SPC130>`, and its own
docstring says so. Asked "why is this here at all, it should be the library":
because the acquisition path decodes records arriving **from the card, in
memory**, and the library's Python surface offers no "decode this buffer" entry
point — only `TTTR(filename)`, plus `append_events`, which takes events that are
already decoded. The duplication is forced by that gap, not chosen.

**It has not drifted.** Measured against `m000.spc` (SPC-130, 174 438 events):
same event count, and macro times, micro times and routing channels identical
over the whole file. Pinned now by
`chisurf/plugins/core/acq/test/test_spc_record_decoder.py`, which reads a real
`.spc` both ways — a copy of a decoder with nothing holding it to the original
is how the two come to disagree about an overflow run or a gap flag on
somebody's data months later, with no error anywhere.

**The fix is an in-memory record decoder in the library's Python surface**, and
it is now specified there as the library's PRD-021 — "decode this buffer" with
the decoder state carried across chunks, ranged and streaming reads for all
fourteen container types, and the whole `.set` sidecar in every binding. **Two
deletions here are that PRD's definition of done**, and neither can happen
before it lands or acquisition stops working:

* `_process_bh_spc_records_numba` and its pinning test;
* `bh_spc/reader.py`, once the sidecar parser is in the library.

**The sidecar is the second half, and it is the same story.** `bh_spc/reader.py`
parses the `#PR`/`#SP` hardware-parameter blocks of a `.set` file for the
card-setup dialog. The library reads `.set` sidecars too (`read_bh_set_file`),
but only the five imaging tags a photon reader needs — `SP_IMG_X`, `SP_IMG_Y`,
`SP_PIX_CLK`, `SP_TAC_R`, `SP_ADC_RE` — and that function is **not exposed in
any binding**. Measured on two real sidecars, that is **5 of 115** parameters
and **5 of 121**: the same file is parsed twice by two implementations, each
ignoring what the other wants. Neither is wrong; the split is.

**The copy is not a performance workaround, which is the thing most likely to be
assumed.** Reading and decoding 299 999 records from a file through the library
costs 1.50 ms (200 M records/s); the numba copy decodes the same records,
already in memory, in 0.66 ms (457 M records/s). Different work — one includes
the file read — and both far faster than anything downstream needs. The copy
exists because there is no entry point.

## RESOLVED — photon container: adding an instrument file read it whole into memory

**2026-08-06, fixed 2026-08-07.** `Measurement.create` embeds the instrument
file verbatim, and the only input path tttrlib exposed took bytes, so an 8 GiB
PTU became an 8 GiB Python `bytes` before it was written.

Fixed in the library rather than worked around here: tttrlib PRD-020 added
`PtoFile::add_file`, which writes the same header and streams the payload in
blocks. `_add_payload_from_path` already preferred it when present, so the seam
picked it up with no chisurf-side change. The same PRD closed the read half —
column subsets and row windows of an embedded store, ranged byte reads, and
cues for positioning in a photon stream.

## imaging: a 30-frame acquisition reconstructs as 29, and the flags that would fix it do not reach the reconstruction

**2026-08-06.** Found by rebuilding the simulation library from source (the
environment carried a build predating its 2026-08-05 CLSM fix, so this is
invisible until someone rebuilds). `chisurf/plugins/microscopy/img_flow/test/
test_img_flow.py::test_the_demo_is_a_readable_ptu_whose_flow_comes_back` fails
on `assert stack.data.shape[0] == 30` with **29** — one full frame of a
30-frame scan is gone.

**The file is not at fault, and the edge arithmetic is right.** The demo writes
30 frame markers and the last one is followed by a complete frame: 64 line-start
and 64 line-stop markers. Called directly, the edge finder answers correctly —

```
get_frame_edges(tttr, 0, -1, [4], 1, 0, skip_before, skip_after, 1, -1)
  skip_before=True  skip_after=False -> 31 edges = 30 frames   <- correct
  skip_before=True  skip_after=True  -> 30 edges = 29 frames
  skip_before=False skip_after=False -> 32 edges = 31 frames   (leading stub)
```

and `create_frames` makes `len(edges) - 1` frames, which is the right rule.

**What is wrong is one layer up.** Constructing `CLSMImage` with those flags
gives **29 frames for both values of `skip_before_first_frame_marker`** and 28
for both values of `skip_after_last_frame_marker` — i.e. the count moves with one
flag and not the other, and is one lower than the edge list implies in every
combination. The flags are not reaching the reconstruction the edge finder sees.
Reproduce with:

```python
from chisurf.plugins.microscopy.img_flow.demo import create_demo
create_demo(path, n_frames=30)
tttrlib.CLSMImage(tttrlib.TTTR(str(path)), marker_frame_start=[4],
                  marker_line_start=1, marker_line_stop=2, marker_event_type=1,
                  skip_before_first_frame_marker=..., channels=[0], fill=True)
```

**Trap in re-deriving it**: the demo's frame marker is routing channel **4**, not
3 — PTU writes markers as bit positions, so the value in the file and the value
in the docs differ. Passing `[3]` finds no frame markers at all and
`get_frame_edges` returns an empty list, which looks like a different bug.

Not fixed here because it belongs in the imaging module of the companion library
and has nothing to do with the table work that surfaced it. The test is left
**red rather than xfailed**: this is silent data loss — the frame simply is not
there, and the array shape is the only thing that says so.

## PDA: the dynamic two-state fit lands just past its convergence threshold

**2026-08-06.** `test/gui/test_pda2c_model_editor.py::test_dynamic_pda_recovers_
exchange_and_rejects_the_static_model` fails on `assert fit_dyn.chi2r < 1.5` with
**chi2r = 1.5339**, deterministically — the same value on every run and on the
commit before the PRD-38 cleanup, so it is not a flake and not caused by that
work (verified in a detached worktree at `b5f6eec0c^`).

Everything the test is *about* passes: it recovers `k_ex`, `R1`, `R2` and `x1`
within tolerance and does reject the static model. Only the absolute goodness-of-
fit is 2 % over the line, so the question is whether 1.5 is the right threshold
for this fixture or whether the dynamic model leaves a small systematic residual.
Do not "fix" it by moving the number without answering that.

## chimol: the mouse-mode block's text is clipped at the panel's column width

**2026-08-06.** Seen while composing the object panel over a `ray` result on a
902x562 viewport: the bottom-right block reads `Mouse Mode 3-Button Viewin`,
`Whee`, `MovS`, `+Box-BoxClipMovS` — every line runs out of column. The column
is a fixed `column_width = 220`, and the block is laid out to that regardless of
what its longest line needs, so it is clipped at every window size rather than
at small ones.

Not caused by the ray-image change (it is the same before and after, and the
panel is a fixed-width column either way), and not chased there because the fix
is a layout question for the panel: either the block measures its own text and
the column takes the wider of the two demands, or the mode names abbreviate.
PyMOL sizes the internal-GUI column from the text. Reproduce with the composer
in `chisurf/plugins/chimol/test/test_ray_keeps_the_panel.py` — paint
`paint_screen_space` onto a `QImage` and read the bottom-right corner.

## models: `ReactionWidget` (stopped flow) could not be instantiated — RESOLVED 2026-08-06

**Resolved** by [PRD-38](../prds/prd-38.md) increment 18: `ReactionModel`
(`core/models/stopped_flow/reaction.py` + `reaction.view.json`) implements
`update_model`, `reaction.ui` is deleted, and `ReactionWidget` is a deprecation
alias. Kept here for what the port found underneath it.

`ReactionWidget.__abstractmethods__` was `frozenset({'update_model'})`, so choosing
"Reaction" in the stopped-flow model menu raised `TypeError`. **All three**
stopped-flow / ET entries were in that state.

**Because it could never be opened, `ReactionSystem` had never really run**, and
carried four defects the new model is the first caller to hit:

* `reactions` returned a `zip`. `odeint` calls `rate_equation` once per step with
  that same object, so it was exhausted after the first call, every later
  derivative was zero, and **every reaction system integrated to a flat line**.
* `n_species` raised `NameError` — `reduce` was never imported and the `except`
  only caught `TypeError`.
* `species_brightness` could not round-trip a list of numbers: the setter stored
  what it was given, the getter read `.value` off each entry.
* `plot()` called a matplotlib alias the module never imported. Deleted rather
  than fixed.

Rate constants were plain `Parameter`s, i.e. **not fittable**; the hand-written
editor hid that by appending its own widget-backed parameters instead of calling
`add_reaction`. The guard (`test/models/test_reaction_model.py`) asserts an
`A ⇌ B` system relaxes to the analytic `k_f/k_r` equilibrium, not merely that it
computes something.

*General lesson: an unopenable editor hides the state of everything below it. Look
for the missing caller, not only the missing control.*

## models: `EtModelFreeWidget` is registered and cannot be instantiated

**2026-08-06. Resolved by deprecation** — the fit is deregistered and the module
deleted; `EtModelFreeWidget` resolves to `None` so an old config drops the entry
instead of crashing. Kept here because the *reason* matters: it had never worked.
Choosing it failed with

```
TypeError: Can't instantiate abstract class EtModelFreeWidget
           without an implementation for abstract method 'update_model'
```

`EtModelFreeWidget.__abstractmethods__` is `frozenset({'update_model'})`. Its
compute class `EtModelFree` lives *inside*
`chisurf/gui/widgets/models/tcspc/et.py` (line ~250), which is why it is tier B in
[PRD-38](../prds/prd-38.md): the model has to be extracted into `core/models/**`
before its editor can be described in JSON, and the extraction is also what would
give it a real `update_model`.

**Why it went unnoticed:** nothing constructs it. Construction smoke tests skip GUI
model widgets, and the editor-integration guard walks only the JSON-described
models. It is registered in `experiment_configs.yaml`, so it appears in the menu
regardless.

To reproduce, resolve it the way `add_fit` does and build a `Fit`:

```python
from chisurf.gui.widgets.models.tcspc import EtModelFreeWidget
print(EtModelFreeWidget.__abstractmethods__)   # -> {'update_model'}
```

Once ported, drop it from `_a_still_legacy_widget_model`'s skip in
`test/gui/test_auto_model_widget.py` -- that helper currently steps over abstract
widgets so the MRO tests do not report this pre-existing breakage as their own.

## models: the parse editors' validity badge and LaTeX preview — RESOLVED 2026-08-06

**Resolved** by [PRD-38](../prds/prd-38.md): a `value` section of
`kind: "expression"` renders the equation field through the shared
`chisurf/gui/widgets/expression_input.py::ExpressionInput`, so **any** view spec
now gets a formula field with the safe-AST ✓/✗ badge, the reason in a tooltip, the
typeset LaTeX preview, the names-and-functions reference and parameter discovery
— which is strictly more than the hand-written `ParseFormulaWidget` had.

`parse/widget.py` and `parseWidget.ui` are deleted; `parse/latex.py` stays, since
`equation_editor` and `expression_input` both use it.

*The point worth keeping: the gap was closed by reusing the widget that already
did it rather than re-implementing the check inside `ValueWidget`. A second
implementation of "is this formula safe" is a second answer to that question.*

## chimol: the nucleic-acid cartoon has artifacts — RESOLVED 2026-08-06

Kept for the mechanism, which generalises past this one representation.

Reported as "the backbone of the nucleic acid is offset, thus it looks like
there are sticks sticking out of the backbone". The sticks were the base
connectors, drawn correctly to the real sugar atoms while the tube ran
somewhere else -- so the three symptoms it presented as (offset backbone,
detached rings, stray spokes) were **one** fault.

The fault is a category error, not arithmetic. The nucleic trace was passed
through PyMOL-style `RepCartoonSmoothLoops` control-point averaging, which
PyMOL applies to **loops** -- because a moving average over points on a HELIX
is not a smoothing but a **contraction toward the helix axis**. A duplex C4'
trace is a helix of radius ~9 A; the shipped two 3-point passes moved it a
measured 1.68 A (max 2.43 A) off the atoms, against a tube radius of 0.4. It is
also sharply window-sensitive: `window=3` on the same structure reaches 8.3 A,
so a half-width that reads like a quality knob is a displacement knob.

Two changes, because the default was only half of it: nucleic smoothing is off
by default (`nucleic_smooth_cycles`, and the spline already smooths *and*
passes through its control points), and each base connector is now anchored to
the same array the tube is swept along instead of to the raw atom -- so no
smoothing setting can separate them again.

**Why the render test did not catch it:** it pinned `backbone_smooth_cycles` to
0 in its own config while the shipped default was 2. It rendered, and asserted
on, a configuration nobody ran. That is the second instance this week of a test
asserting a non-shipped environment into existence (the first was mouse picking),
and it is worth treating as a pattern: a test that supplies its own config is
testing the code, not the product.

## ndX: the mask event filter reads a deleted check box during start-up (2026-08-06)

`MaskDrawingIntegration.eventFilter` (`utils/mask_drawing_integration.py:427`)
asks `plot_control.mask_widget.is_drawing_enabled()` on every event it sees,
including one `Enter` on the plot canvas raised while the window is still being
built. At that moment `MaskDrawingWidget.enable_drawing_checkbox` holds a wrapped
object that has been deleted, and the `except (RuntimeError, AttributeError)`
around it logs

```
WARNING - Error checking drawing enabled state:
          wrapped C/C++ object of type QCheckBox has been deleted
```

and returns `False`. By the time construction finishes the reference is valid
again and points at the live check box, so the visible effect is limited to that
one event being treated as "drawing off" — which it is anyway, since drawing
starts disabled. What is *not* known is which object is deleted: only one
`SurfacePlotWidget` is ever constructed, and the check box the control holds at
the end is alive and is the same object the mask widget references.

**Measured, not assumed: this is not from the AutoForm panel work.** It
reproduces on a pristine `HEAD` checkout of the module — copy the tree, restore
every modified file with `git show HEAD:<path>`, put the copy first on
`PYTHONPATH` and build an `NDXplorer`; the warning appears exactly once there
too. It also appears with both AutoForm panel builders monkey-patched to no-ops,
which is what rules out the panels rather than the check box that replaced the
checkable group box.

The fix is to look the check box up by `objectName` at call time rather than
hold a reference across construction, or to install the event filter after the
window is built. Both are changes to the mask subsystem, which is why neither
was made while wrapping the panels.

## okf: the update log is ~40 % duplicated entries (2026-08-06)

`okf/log.md` holds **1977 entries of which 1180 are distinct** — 765 appear more
than once, some four times, and the repeats go back months (`chimol: sessions`,
`Parameter error estimates were wrong by √2`, `German catalogue brought to ~90 %`).
It is not one bad commit: several instances work this file at once, each inserting
at the same `## <date>` anchor and each committing a *view* of the file that
overlaps the others'.

Re-derive it before touching anything:

```python
# split on lines starting with "## " (date headings) or "* **" (entries),
# then count distinct entry bodies
```

**Not fixed here, deliberately.** De-duplicating touches ~11 500 lines of a file
that other instances are committing to *right now*, and a mechanical pass that
drops one entry by accident is worse than the duplication. It needs a dedicated
change made when nothing else is mid-edit, with the check being that the set of
**distinct** entries is identical before and after.

**One trap already paid for.** A first attempt at that pass, run casually while
doing something else, cut the file from 29 265 to 17 759 lines in one write —
because "drop exactly-duplicated blocks" is only safe if the block splitter is
right, and there is no undo for a working-tree write. It was restored from
`HEAD` (the file happened to be clean), but that was luck, not design: **build
the new content, diff it against the old, and only then write.**

## testing: `fret_trajectory`'s suite crashes the interpreter *after* every test passes

**2026-08-06.** `pytest chisurf/plugins/traj/fret_trajectory/` reports
`11 passed  [100%]` and then dies with `Fatal Python error: Bus error` (sometimes
`Segmentation fault`) during interpreter shutdown. Every test passes; the process
exit code does not, so CI reads it as a failure.

**Pre-existing, and measured as such.** It is tempting to blame the DCD port,
because the port is what made the four previously-`ValueError`-ing tests run at
all. It is not the cause: a detached worktree at the pre-port commit crashes the
same way. To re-derive it —

```bash
git worktree add --detach /tmp/wt <pre-port-sha>
cd /tmp/wt && export PYTHONPATH="$PWD:$REPO/modules/mmfdb/src:$REPO/modules/chinet:$REPO/modules/imp-tricks/src"
QT_QPA_PLATFORM=offscreen python -m pytest -q chisurf/plugins/traj/fret_trajectory/
```

**The traps in measuring it.** Both nearly sent me after the wrong thing:

- **`grep`ing for `failed` finds nothing.** The crash prints no pytest summary
  at all — the process is gone before one is written. Match on `Bus error` /
  `Segmentation fault`, or a green-looking run will read as a clean one.
- **It does not reproduce from a plain script.** A QApplication, four
  `Structure2Transfer` widgets and three model loads exit 0. It needs the
  pytest-qt fixtures, so it is a *harness* shutdown-order problem, not something
  the product does to a user.
- **No single test causes it.** `test_gui.py` minus `test_gui_interaction_process`
  is clean 5/5; that test alone is clean 5/5; the four together crash ~1/3; the
  whole directory crashes 8/8. It accumulates with how much Qt was built, which
  is why bisecting to one test id finds nothing.
- **Order matters.** `test_view_model.py` then `test_gui.py` passes; the
  alphabetical order pytest actually uses is the crashing one.

**Tried and reverted.** The Qt-free view model and the Qt atom-pair section hold
each other (`section._model` / `model.atom_pair_section`), a strong QWidget↔object
cycle collected by the GC — possibly after `QApplication` is gone. Making the
back-reference weak is defensible on its own, but it does **not** fix this: 5/5
still crash. Reverted rather than kept under a rationale that had been
disproven. Whatever holds the Qt objects past shutdown is something else; the
shared session-scoped `qapp` in `chisurf/plugins/conftest.py`, which overrides
pytest-qt's own and never tears the application down, is the next thing to look at.

## packaging: five pandas HDF5 writers outlived the `pytables` removal — RESOLVED 2026-08-06

**2026-08-06.** `pytables` was dropped on the grounds that its "only remaining
use" was the MEM sampler's posterior (commit `ffeab9f0c`). It was not: pandas
reaches for it too, and **five live call sites still do**, none of them guarded
by a `try` —

- `chisurf/plugins/burst/burst_h2mm/core/export.py:279` — `write_hdf5`, the
  **ndX-openable** export (`key="results"`, `format="table"`)
- `chisurf/plugins/burst/bid_to_analysis/__init__.py:317,322,331` — `pd.HDFStore`
- `chisurf/core/fluorescence/imaging/pixel_maps.py:699,703,713,753` — the pixel-map
  store and `add_maps_to_hdf5`
- `chisurf/core/fio/fluorescence/burst_states.py:88` — `pd.read_hdf`
- `chisurf/core/fitting/fit.py:2363` — `save_chain_to_hdf5`

**Why nobody has hit it yet, and the trap in re-deriving it.** The developer
`arm64` env still carries `pytables 3.7.0` from before the removal, so every one
of these paths works locally and every test covering them passes; the failure
appears only in an environment solved from the current manifest. Reproduce
without rebuilding anything by hiding the module from the import machinery:

```python
import builtins; real = builtins.__import__
builtins.__import__ = lambda n, *a, **k: (_ for _ in ()).throw(ImportError(n)) if n.split('.')[0] == 'tables' else real(n, *a, **k)
import pandas as pd
pd.DataFrame({"a": [1]}).to_hdf("p.h5", key="results", format="table", mode="w")
# ImportError: Missing optional dependency 'pytables'.
```

**What it blocks, and why the fix is a scope call rather than an oversight.**
The h2mm export is not an internal cache — the pandas `format="table"` layout
*is* the interchange contract with ndX, so the two repairs are not equivalent:
re-declaring `pytables` restores the contract and costs the dependency back
(measured 0 packages while `mdtraj` was present — that is now stale and needs
re-solving, since `mdtraj` went too), whereas moving the writers to `.npz`/plain
HDF5 keeps the dependency out and **changes a file format another tool reads**,
which needs ndX checked against it first. Whichever is chosen, the guardrail is
the same shape as the one `pyarrow` needed: a test that fails when a
module-level *or* in-function `pd.to_hdf`/`pd.read_hdf`/`pd.HDFStore` exists
without `pytables` declared.

## `test/server` — three real defects fixed, 43 tests still red

**The RPC server could not build a fit at all.** ``fit_create`` resolves a model
by walking ``Model.__subclasses__()``, which only sees *imported* classes, and
the server imports none of them: measured in a fresh server process, exactly
**one** model class was reachable ("Global fit", pulled in by the fitting
machinery). Every ``fit.create`` naming a real model answered ``model 'X' not
found``. It now runs the same headless bootstrap the agent layer uses
(``ensure_experiments_registered``), which brings the count to 43, and the error
lists what *is* available.

Two more, each hidden behind the first:

* ``FitGroup`` **iterates** its data to build one member fit per dataset, and a
  bare ``DataCurve`` iterates into ``(x, y)`` tuples — so the single-dataset
  path built member fits whose ``data`` was a tuple and the first read of
  ``data.x`` failed. It takes a ``DataGroup``, one dataset or several.
* A server-created fit had the range ``(0, 0)`` and could be created but never
  run (``Improper input: N=4 must not exceed M=(0,)``). ``fit_create`` now
  initialises it from the reader's ``autofitrange``, falling back to the whole
  curve for a dataset that arrived as raw ``curve_data`` and has no reader.

Also fixed: ``fit_set_dataset`` did not accept ``fit_uid`` while the dispatcher
passes it, and ``fit_set_result_idx`` made ``fit_index`` a required positional —
so addressing either by uid, the documented way, raised ``TypeError`` inside the
dispatcher. And ``Fit.set_result_idx`` documented "clipped to the valid range"
while ``np.clip(idx, 0, len(results) - 1)`` returns **-1** for an empty deque and
then indexes it: "this fit has not been run yet" reached the caller as
``IndexError: deque index out of range``.

### What is left, and the trap in measuring it

43 failures across 12 classes in ``test_integration_lifecycle.py``. **They do not
reproduce class by class**: ``TestErrorBoundary`` passes **12/12 alone** and
fails 3 in the full file, and ``TestProxyRpcErrorHandling`` passes 6/6 alone and
fails 6 in it. The file shares one module-scoped server and client
(``_client()``) and resets only datasets and fits between tests
(``reset_state`` → ``fit__clear`` / ``dataset__clear``), so anything else a test
leaves behind is inherited by the next one. **Fix the isolation before chasing
any individual assertion** — a per-test failure here may be a previous test's
residue, and a fix verified on one class is not verified.

Three classes have been ported and pass in isolation (``TestErrorBoundary``,
``TestProxyRpcErrorHandling``, ``TestChisurfRunPattern``); the pattern for the
rest is the same. A failing call **raises** ``RemoteError`` — service errors are
carried in the JSON-RPC ``error`` member (SV-04) — and these tests still assert
``not result.get("ok")``, which never described the contract: it also passes on
success, because a result payload has no ``"ok"`` key either. Port to
``pytest.raises(RemoteError)``, and where the test only means "the server must
survive this", assert that with a following ``meta__ping``.

The whole file takes **13.5 minutes**; run one class at a time while working.

## The arm64 env's tttrlib symlinks can dangle into a deleted pixi cache

**Found 2026-08-04**, mid-session: every GUI tool stopped constructing with
`ModuleNotFoundError: No module named 'tttrlib'`, having worked minutes earlier.

The cause is not a missing install. In the `arm64` conda env,

```
site-packages/tttrlib.py          -> ~/Library/Caches/rattler/cache/envs/chisurf-<hash>/…/tttrlib.py
site-packages/_tttrlib.cpython-312-darwin.so -> …/_tttrlib.cpython-312-darwin.so
```

are **symlinks into a pixi/rattler cache environment**, and that cache directory
had been emptied — `ls <target dir> | grep -c tttr` returns 0 — while the links
remain. A dangling symlink imports as "no module", so nothing in the error says
the file is there-but-pointing-nowhere.

Diagnose with `ls -la $CONDA_PREFIX/lib/python3.12/site-packages/tttrlib.py` and
then look at the target. Stale `.bak_*` and randomly-suffixed copies
(`_tttrlib.cpython-312-darwin.so6uhgcN`) beside them are the fingerprint of an
install that was interrupted or replaced.

**Not repaired here**: another agent instance was running pixi at the time, and
re-linking or reinstalling underneath an in-flight environment solve is how one
instance breaks another's. The repair is to re-run the tttrlib editable install
for this env once nothing else is building.

**What it blocked**: the `irf_estimator` guided tour could not be walked with
`build_tools/dev_utils/check_plugin_guide.py`, so its `help.md` / `guide.json`
are written and **deliberately left uncommitted** — a GUI change is unfinished
until its render has been looked at, and this one has not been.

**Resolved by the third repair**: [PRD-82](/prds/prd-82.md) stage 2 moved every
one of these onto the columnar writer — one dataset per column, no optional HDF5
package, and with a text column *smaller* on disk than the frame file it
replaces (60.0 MB against 72.6 MB) rather than larger. It did **not** wait for a
reader for the legacy layout: that reader was written in the simulation library
and reverted as out of scope there, so files from earlier releases still need
the optional package, now behind a named `LegacyTableError`. See the storage
entry below and [PRD-82](/prds/prd-82.md).

## Test suite: what is still red after the 2026-08-04 sweep

**Where to pick this up.** The suite was run **one directory (and, for
`test/gui`, one file) per pytest process**, because a directory-wide run dies
with SIGBUS/SIGSEGV partway through and takes the failure summary — and every
later file — with it. Re-derive with the scripts kept in the session scratchpad
pattern: `python -m pytest <target> -q --tb=no -rf` per target, recording the
return code, and treat `rc=139`/`rc=134` as "this file crashed, its failures are
unknown", not as "one failure".

**Trap in taking the measurement**: run inside the **activated** `arm64` conda
env (`conda activate arm64`), not merely with its interpreter path. With the
base env activated, PIL binds to base's `libz-ng` and any test that shells out
(`test/scripts/test_scripts.py`) fails with `Symbol not found: _zng_deflateInit2`
— a harness artifact that looks exactly like a code defect. Those two script
tests pass when the env is activated properly.

**Blocked as of 2026-08-04**: `import tttrlib` fails in the `arm64` env. The
package was rebuilt as a **directory** (`site-packages/tttrlib/`, holding its own
`_tttrlib*.so` and the split `libtttrlib_*.dylib`), while the env still carries
the two symlinks of the old single-module layout — `tttrlib.py` and a top-level
`_tttrlib*.so` — both now dangling. Repair by replacing them with one link to the
package directory:

```bash
SP=$CONDA_PREFIX/lib/python3.12/site-packages          # with arm64 activated
P=~/Library/Caches/rattler/cache/envs/chisurf-*/envs/default/lib/python3.12/site-packages
rm "$SP/tttrlib.py" "$SP/_tttrlib.cpython-312-darwin.so"   # both dangle; nothing is lost
ln -s "$P/tttrlib" "$SP/tttrlib"
```

Until then every test importing `tttrlib` errors **at collection**, which
`pytest -q --tb=no` reports only as ``1 error during collection`` with no cause
— re-run the target without `--tb=no` before believing any `rc=2`.

### `test/gui` — 30 failures across 22 files, plus 5 crashes

Five files crash rather than fail, so their contents are unmeasured:
`test_gui_plots.py` (139), `test_lineplot.py` (139), `test_widgets.py` (139),
`test_gui_tool_fret_line.py` (134), `test_region_editor.py` (134). One cause of
the 139s is fixed — `get_app()` built a **second `QApplication`** per process —
and `test_gui_plots.py` gets past it, so re-measure these five first; what
remains after that is a different fault.

The rest, grouped by what they look like rather than by file:

* **Stale test doubles** — the same class already fixed in five other files: a
  widget attribute that has moved (`new_detector_le`, `load_detector_setups`),
  a value that is now read from a model rather than the Designer widget, a
  fixture whose data shape predates the loader. `test_gui_tool_pdb2label.py`
  (3, `AttributeError`), `test_init_chisurf_onboarding_wizard_import.py` /
  `test_wizard.py` (the same test, in two files), `test_updater_*.py` (2).
* **Numeric disagreement** — `test_gui_tool_kappa2dist.py` (2) and
  `test_gui_tools.py::test_kappa2_calculation_*` are the *same two* assertions
  in two files, both `assert 0.1 == 0.0`; likewise
  `test_gui_tool_tttr_histogram.py::test_load_data` and
  `test_gui_tools.py::test_histogram_load_data` (`assert 0 == 1`). Fixing the
  pair fixes four entries. **Note the duplication**: `test_gui_tools.py` looks
  like a rewritten copy of the three `test_gui_tool_*.py` files, and
  `test_info_json_uppercase.py` was a byte-level subset of `test_info_json.py`
  (deleted). Check for a duplicate before debugging anything here.
* **`test_rate_matrix.py` (4) — diagnosed, deliberately not fixed.** Each cell
  of the grid is now a container `QWidget` holding a *fix checkbox plus* the
  spin box, with the spin boxes kept in `RateMatrixSection._spins[(i, j)]`; the
  tests still call `table.cellWidget(i, j).setValue(...)`, from when the cell
  *was* the spin box, and get `'QWidget' object has no attribute 'setValue'`.
  Left alone because `chisurf/gui/autoform/sections/rate_matrix_section.py` had
  **uncommitted changes from another instance** while this was measured — the
  tests belong to whoever is changing that widget. Port them through `_spins`,
  not through `cellWidget`.
* **Widget behaviour** — `test_proteinmc_mdl.py` (3),
  `test_parameter_prior_widget.py`,
  ~~`test_parameter_table_actions.py`~~ (fixed 2026-08-05: the test asserted, as
  its *precondition*, the very warning that
  `FittingParameterGroup.finalize` had deliberately stopped emitting — a
  parameter without a controller is the ordinary case. Rewritten to assert
  silence in both halves),
  `test_image_section_axes.py`, `test_plot_construction.py`. These are the ones
  most likely to be *real* defects rather than stale tests, and the rate-matrix
  four are the biggest single cluster.

`rc=5` (`test_save_button.py`, `test_style.py`, `test_gui_chisurf_tcspc.py`,
`test/repro/`) means **no tests collected** — empty or fully skipped, not a
failure.

### A parameter that starts exactly on its bound cannot move

Not a test failure but the reason one "fix" was reverted, and worth knowing
before bounding anything. `leastsqbound` maps a bounded parameter through
`sin` (two-sided) or `sqrt(x**2 + 1)` (one-sided); both are **quadratically
flat** where they meet the bound, so a parameter sitting *on* its bound has a
derivative of zero with respect to the coordinate MINPACK varies. Its Jacobian
column comes back empty however strongly the residuals depend on it: at
MINPACK's default `1e-3` internal step, a background bounded at `bg >= 0` and
started at `0` moves by **5e-7**.

Nudging the start inward was tried and reverted. The offset has to be ~0.1 in
internal coordinates to give a usable derivative, and for a two-sided bound that
is 0.25% of the *whole box* — for a rate bounded at `(0, 1e9)` it starts the fit
at 2.5 million, which broke three PDA rate tests
(`test_pda2c_time_binned.py` x2, `test_pda3c_rates.py`). A scale-aware offset
small enough to be safe is too small to help. Any real fix has to change the
*transform* (or use an optimiser with genuine box constraints), not the start.

## 2D-FLCS prints a pyqtgraph teardown traceback when its window closes

**Found 2026-08-04**, while walking the new 2D-FLCS guided tour headlessly.

Closing `FlcTwoDTool` prints, two to four times,

```
RuntimeError: wrapped C/C++ object of type QComboBox has been deleted
  ... ViewBox.forgetView -> updateAllViewLists -> updateViewLists
  ... ViewBoxMenu.setViewList:  current = c.currentText()
```

The chain is entirely inside pyqtgraph: a destroyed `ViewBox` runs a
`destroyed`-signal lambda that rebuilds **every** view list, and reaches a
`ViewBoxMenu` whose combo box Qt has already deleted. Nothing of ours is on the
stack.

**Not caused by the guided tour**, though the tour makes it louder. Measured by
disabling `GuidedTour._unfold` entirely and walking the tour again: the traceback
still appears (2×). With the tour's extra `processEvents` it appears 4×, because
more deferred deletions get to run before the interpreter exits. Other
pyqtgraph-backed tools (H2MM) do not reproduce it — 0 occurrences.

Harmless in the sense that matters: it is an exception inside a Qt slot at
teardown, printed and swallowed, with no state left broken. Left alone because
the fix belongs in pyqtgraph's `ViewBoxMenu`, and the plugin is scheduled to move
off pyqtgraph anyway ([PRD-64](../prds/prd-64.md), [chiplot](../subsystems/chiplot.md)).

## chimol: every scene rebuild refits the camera — RESOLVED 2026-08-04

**Found 2026-08-04**, while photographing `cartoon_side_chain_helper` — the
framing kept resetting between the "off" and "on" shots.

`MolView._update_view(fit_camera=True)` is the default, and a rebuild is what
colouring, a representation change, a label, a bond edit and **every `set`** all
trigger. Measured on 148L: `zoom resi 20-26` puts the camera distance at
**1.26**, and the next `set` of *anything at all* puts it back to **5.0**. So
framing a binding site and then adjusting a stick radius loses the framing — in
a viewer, which is a serious thing to get wrong. PyMOL moves the camera only for
a camera command (`zoom`/`orient`/`center`/`reset`) or a load (`auto_zoom`).

**Attempted and reverted**: flipping the default to `False` and passing `True`
from the three load paths (`set_structure`, `set_coordinates`, `add_volume`) is
*not* sufficient, and the suite says so — `test_ray_command.py::
test_every_representation_reaches_the_image` then traces an **empty image** for
all four representations. `ray` and the headless load path both depend on this
refit to frame at all: at the point the load paths call it the scene has no
geometry to measure, so the first rebuild that *does* is what actually frames.
An `auto_zoom`-once flag (frame on the first build with geometry) does not fix
it either, because in that test the window is never shown and `_update_view`
returns early with no renderer.

The real fix moves framing to where a structure is loaded and the scene is
built, rather than flipping a default — six call sites had already been patched
to `fit_camera=False` one at a time, which is the signature of a default that is
wrong but load-bearing. Left as it was, because a half-verified change across
~64 call sites in a viewer is worse than a known defect.

Six call sites already pass `fit_camera=False`; the ones that matter for a user
are colouring, representations and `set`.

**Resolved 2026-08-04, and the revert was for the wrong reason.** The default is
now `False`, with the three load paths passing `True` — the change described
above as insufficient. It was not insufficient; the `ray` failure it was blamed
for was the **aspect** defect two entries down, not the framing. A window that
is never shown has no viewport, `_aspect()` read 1/30 off the one-pixel column
that left, and the camera went thirty times too far away; refitting on every
rebuild hid that, because the last rebuild landed after the widget had a size.
With `_aspect()` fixed, `test_ray_command.py` passes with the default flipped
and no other change.

Two things the flip needed on top: `_rebuild_after_coordinate_change` reuses
`set_structure` — the *load* path — to re-derive after an edit, so `h_add` on a
zoomed-in residue still jumped out until `set_structure`/`set_coordinates` grew
a `fit_camera` argument; and nothing re-derived the distance on a **resize**,
which the old behaviour had been covering by accident, so `resizeGL` now
re-frames when the viewport's shape changes (distance only — the clips carry a
user's `clip` adjustments — and by *scaling* the distance rather than
recomputing it, since the scroll wheel moves the camera without changing what
was framed).

Measured: 12 of 12 ordinary commands threw the framing away before, 0 of 12
after. `test_camera_persistence.py` pins both halves — what must not move the
camera, and what must.

**The lesson is about the revert, not the bug.** "Attempted and reverted, with
why" was the right thing to record and is what made this cheap to re-open — but
the recorded *why* was a symptom seen through another defect. When an attempt
fails, the note is worth more if it says what was measured than what was
concluded.

---

## Stale tests left behind by finished refactors

**Found 2026-08-03**, while running the guard suites for the PSF calculator's
guide/help and export work. Six failures in `test/gui` and `test/server` that
have nothing to do with that change, and are not flaky — they fail on an idle
machine, on paths with no uncommitted edits, so they are committed breakage
rather than another instance's work in flight.

* `test/gui/project/test_info_json.py::test_info_json_uppercase` and its
  duplicate `test_info_json_uppercase.py` monkeypatch
  `filter_widget.load_detector_setups`. That method moved off the widget and
  became the module-level `chisurf.core.data_io.detector_setups.load_detector_setups`
  in the SV-01 Qt-free split; the tests still patch the bound method, so they
  raise `AttributeError` before asserting anything.
* `test/gui/settings/test_acquisition_simulation_autoform.py` references an
  undefined `TestWidget` (`NameError`) in three tests.
* `test/gui/test_mmfdb_picker.py::test_shared_client_adopts_chisurf_login_session`
  expects the shared client's token to be `None` and finds one.

Not fixed in the change that found them: each is a test that a *completed*
refactor left pointing at the old shape, and repairing one means deciding what
the refactor intended it to assert — which belongs with whoever owns that
refactor, not with a change to a calculator plugin. Recorded rather than
silently skipped, because a red suite that everyone steps over is how the next
real regression gets missed.

Fixed in passing, since they were unambiguous and one line each: the
`node_editor` package promising names in `__all__` it never bound, the
`ReentrancyGuard` that never guarded, `to_elementary` keeping the keys it was
asked to skip, a missing `Path` import, and three stale
`serialize_reader_state` mocks.

## test/server: the shared-server integration file errors and then hangs

**Found 2026-07-28**, while test-gating an unrelated proxy fix (RF-722).
`pytest test/server` never finishes: `test_integration_lifecycle.py` runs its
module-scoped `ChiSurfServer` in-process, and most of its tests error in
*setup* with

```
chisurf.startup.services.AppStartupError: service 'mmfdb' did not become ready
within 5.0s
```

after which the run stalls indefinitely at
`TestParameterLifecycle::test_linked_info` (>180 s, no output). The 5 s
`ready_timeout` in `chisurf/startup/services.py` is the visible trigger and it
is load-dependent — the same tests pass when the machine is idle, so a machine
running several suites (or several agent instances) turns it red. Which of the
two symptoms causes the other is not yet established: a server whose startup
raised may leave the ZMQ socket half-alive, which would explain a later call
that never returns.

Not fixed in the change that found it: the failure is in the shared server
fixture, not in anything that change touched (nothing in the file calls the
insertion routes it altered), and diagnosing a startup-timeout-plus-hang is its
own change. The proxy behaviour itself is covered by `test_proxy.py` and
`test_proxy_integration.py`, which are green.

**Update 2026-07-28 — the startup half is fixed; two other faults were behind
it.** The `mmfdb` stage now declares `"ready_timeout": 30` in
`chisurf/startup/services.d/10_mmfdb.json`. Measured, the stage costs **3.8 s**
on an *idle* machine for its first import, so the 5 s default was never a budget
— it was a hang-detector consuming 76 % of itself on a good day. Raising it
costs nothing in failure latency: `_run_service` records the exception and sets
`ready_event` on the way out, so a service that *fails* still surfaces at once
and only a service that truly *hangs* waits out the budget
(`test_app_startup_manager_reports_background_failure_without_waiting` pins
that, and `test_config_background_services_budget_a_cold_import` stops a new
background stage from silently inheriting the bare default). The server now
constructs, and `TestProxyLifecycle`/`TestLargePayload` run to completion in 8 s.

What that uncovered, both still open:

1. **The fit tests ask for a model that does not exist.** Every
   `client.fit__create(..., model_name="TCSPC")` returns `model 'TCSPC' not
   found`. `fit_create` (`chisurf/server/services/fits.py:410`) resolves a model
   by walking `Model.__subclasses__()` for one whose `name` matches; after
   importing `chisurf.core.models` the only reachable names are `Global fit` and
   `Model name not available`, so no spelling of that call can succeed. Two
   faults stacked: the name is stale, *and* the subclass walk only sees models
   some other import happened to pull in.
2. **The intended skip guard is dead.** `TestParameterLifecycle._setup` writes
   `if not ft.get("ok"): pytest.skip(...)`, but since [SV-04](../specs/assessment.md#sv-04)
   moved service errors into the JSON-RPC `error` member, `fit__create` *raises*
   `RemoteError` instead of returning `{"ok": False}`. So the guard never runs
   and 7 tests fail where the author meant them to skip. Do **not** patch the
   guard to swallow `RemoteError` — that would hide finding 1 rather than fix it.

**The hang is still unexplained**, and it is not specific to `test_linked_info`:
with the timeout raised the run now stalls in the same class at
`TestParameterLifecycle::test_set_bounds` (>5 min, no output), while
`test_set_value` and `test_set_fixed` — which reach the identical `_setup` —
fail fast a moment earlier.

**To close it:** give `fit.create` a model lookup that does not depend on what
happens to have been imported (an explicit registry, as the model/UI split
already needs), fix the test's model name, then give the client a receive
timeout so the remaining stall is a failure with a traceback instead of silence.

**Update 2026-08-03 — the model name is not the only blocker.** Driving the
server directly, with `chisurf.core.models.tcspc.lifetime` imported first so
the subclass walk can see it, both real names (`"Lifetime "` — note the
trailing space — and `"Lifetime (new)"`) get past the lookup and then fail in
`fit.create` itself with

```
'tuple' object has no attribute 'x'
```

so a dataset loaded over `dataset.load` with a `curve_data` payload does not
arrive as something `FitGroup` can build a fit on. Fixing the test's model name
alone would therefore turn a wrong error into a different wrong error. The
whole-suite symptom is unchanged: `pytest test/ --ignore=test/gui` still stalls
at `TestParameterLifecycle::test_set_bounds` (main thread blocked in
`zmq_ctx_destroy` → `ctx_t::terminate` → `mailbox_t::recv`, i.e. a context
being torn down while a socket still holds queued data), and run on its own the
class fails fast instead. So the hang needs state from the tests that precede
it.

## fitting over a genuinely remote server still has a 5-second deadline (2026-08-03)

`FittingClient.run_fit` no longer crosses the socket when the server is embedded
in this process -- which is the GUI's normal case, and where the bug actually
bit: the fit ran on the server thread, the GUI thread blocked in `recv`, and the
`fitting_timeout_ms` deadline (5000 ms, `settings.mmfdb`) expired mid-fit and
disabled RPC for the rest of the session:

    FittingClient: disabling RPC after transport failure in 'fit.run':
    timeout: no response within 5000ms

A real two-state MFD fit takes about 130 s, so it lost that race every time.

**Still open for a genuinely remote server.** Any fit longer than the deadline
will do the same thing over the wire, and the blocking call freezes the GUI for
its duration regardless. The right shape is almost certainly a job submitted to
the server's `JobManager` with progress arriving over the event bus -- the
machinery already exists for sampling (`_watch_sampling_job` polls exactly that
way). Not attempted here because this tree has no remote server to test against,
and a fix that cannot be run is a guess.

## quest: the plugin's RPC layer targets a backend the package does not have

**Found 2026-07-28.** Starting the GUI logs

```
Failed to register services for plugin 'quenching_estimator'
ModuleNotFoundError: No module named 'quest.backend'
```

`chisurf/plugins/quenching_estimator/` is deliberately a thin shell: its
`rpc/services.py`, `api/contract.py` and `api/client.py` all forward to
`quest.backend.services` / `quest.backend.contract` so the CLI, the web backend
and ChiSurf share one implementation of the sixteen `quest.*` methods the
manifest declares. That backend package does not exist -- not in the checked-out
`modules/quest`, and not on any of its branches (`git ls-tree` over `master`,
`main`, `dev`, `devel`, `development`, `chisurf-pin` shows only `quest/lib` and
`quest/settings`). So every `quest.*` RPC is unreachable, and the plugin's own
tests for the contract cannot run either. The GUI entry point still works: it
imports `quest.gui` directly and never touches the backend.

**To close it:** write `quest/backend/{contract,services}.py` in the quest
repository, over `quest.core` / `quest.api`, matching the schemas already in
`chisurf/plugins/quenching_estimator/manifest.json` (that file is the contract's
written form). It belongs there, not here: a second implementation ChiSurf-side
is exactly the `LAY-01` duplication the shell was built to avoid. Until then the
failure is a logged registration error, not a crash.

## packaging: the LaTeX converter has no Python 3.12 conda build

**Found 2026-07-28.** `chisurf/gui/widgets/models/parse/latex.py` renders a
parse-model formula through the third-party `latexify` converter. The
conda-forge package for it stops at Python 3.11, so it cannot go into the
recipe's `run:` list, and the module-level `from latexify import ...` therefore
made the module -- and with it the whole parse-model widget -- unimportable in
the released conda package. Only a pip install ever had it.

The import is now inside the conversion function, next to the `except` that
already fell back to `_convert_python_expression_to_latex_fallback`, the in-tree
AST converter. A conda install renders through the fallback instead of failing:
it covers the operators the parse models use, and is less complete than
`latexify` for anything exotic.

**To close it:** either a Python 3.12 build lands on conda-forge (then declare it
in the recipe and drop the fallback path from the hot path), or the in-tree
converter grows to full parity and the dependency goes for good -- it is one
`ast.NodeVisitor`, so the second is the more likely end state.

## RESOLVED — chimol: large integrative models, and the "fix" that killed them

**Opened and closed 2026-07-27.** The nuclear pore complex was the case that
showed it.

| Entry | Beads | Load before | Load after |
| --- | --- | --- | --- |
| `PDBDEV_00000010` (one spoke) | 29,273 | 8.7 s → 4.3 s | **0.36 s** |
| `PDBDEV_00000012` (eight spokes) | 234,184 | **430 s**, ~11 GB | **1.6 s**, 0.7 GB |

The cost was never the reader — `ihm` reads the 31.5 MB file in well under a
second. It was **a cartoon splined through beads that have no backbone**: 234k
beads become thousands of short chains, each fully splined, framed and extruded.
A bead stands for a *range* of residues, so the ribbon was meaningless as well as
expensive.

**The trap, explained.** Switching beads to the sphere representation — the
correct depiction, and what `set_rmf_data` already did — appeared to make the
entry *die silently*. It did not die. `ball_mask` was left all-**false** by the
mmCIF path (only the RMF path set it), and the sphere branch's fallback for "no
selection" is a **sparse sampling of 50 points along the chain**. The viewer drew
fifty dots and called it a nuclear pore. Nothing raised, because nothing was
wrong as far as any single line of it was concerned.

**What landed.** A bead model is now recognised in the viewer, so every reader
agrees on it: all beads selected, spheres on, cartoon and trace off, no bond
inference, per-bead radii carried through `set_coordinates` and scaled with the
coordinates. Past 20,000 beads the depiction is **sphere impostors** — one vertex
each, shaded as a sphere in the fragment shader — instead of ~160 vertices of
merged mesh per bead, with the impostor's world radius projected to a sprite size
so it follows the camera. Pinned by `test/test_bead_model.py`.

**IMP RMF support landed on 2026-07-28** — and the shape of what was wrong is
worth keeping. RMF was not missing the bead rule because nobody had written it
for RMF; it was missing it because RMF had *its own route into the viewer* and
therefore could not receive anything the common route learned. Measured: one
global radius for every bead, decimation instead of impostors, and hierarchy
check boxes that moved nothing. All of it silent. The fix was to remove the
route, not to duplicate the rule — see the log for that date.

**Still open from that thread:** interior culling (`_get_surface_atom_mask`
exists and is unused), dynamic LOD on camera motion (the draft/settle mechanism
from the trajectory work generalises), and depth-cue fog.

---

## chimol: three atom dtypes — RESOLVED 2026-07-28

Chimol carried **three** transcriptions of "the atom dtype every reader
produces", no two of them the same: a six-field one in `io/beads.py` for the
PDB/mmCIF/RMF readers, a twelve-field `_MDTRAJ_ATOM_DTYPE` for trajectory
topologies, and a twelve-field `PSEUDOATOM_DTYPE` in `cmd/editing.py`. Two of
the three carried a comment asserting they matched the core's `keys_formats`.

All three are gone. `chimol/io/atoms.py` (renamed from `beads.py`, since it now
owns the atom row and not only the bead) imports
`chisurf.core.fio.structure.coordinates.atom_dtype`. Rows are built by field
name (`atom_row(**fields)`) rather than as twelve-long positional tuples.

**The interesting part was not the duplication but what it hid.** The canonical
dtype had `chain` as `|U1`. An mmCIF asym id runs `A..Z` then `AA`, `AB`, …, so
on the eight-spoke nuclear pore 518 of 544 chains needed two characters and
every one was stored as its first letter: **544 chains became 26**, silently.
`chain AB` selected the whole of A and colouring by chain painted twenty
molecules alike. The field is `|U4` now. Widening it made the PDB *writer* a
hazard in turn — `%1s` is a minimum width in Python, not a truncation, so a
two-character id would have shifted every following column — so the writer uses
`%1.1s` and warns, naming the chains whose identity a PDB file cannot carry.

**`modules/quest` still carries two more copies of that PDB format string**
(`quest/lib/io/PDB.py`, `quest/lib/structure/Structure.py`), with the same `%1s`
that does not truncate. They are deliberately untouched: quest builds its own
atom arrays, so the core's widened `chain` cannot reach them, and quest is
slated for deprecation rather than repair. If any of it is kept, the writer goes
with the rest of the duplication — it should not be ported forward as it is.

---

## chimol: a ray-traced mesh is shaded twice, and comes out muddy

**2026-08-03.** Mesh vertex colours arrive at the tracer with ambient occlusion
*and* a cast shadow already multiplied in — `Geometry.occlusion` says so in its
own docstring ("Already multiplied into `colors`") — and the tracer then applies
its own lighting and its own shadows on top. Measured on the 148L cartoon: the
bake costs 44 % of the vertex colour (mean 0.567 → 0.318), and the traced image
is mean 33.3 against 54.5 for the same scene built with baking off. The picture
reads as muddy rather than as shaded, and the baked shadow comes from a *fixed*
light direction that need not be one of the ray lights.

**Not fixed here, and why the obvious fix is wrong.** Dividing the bake back out
of the colours is inexact: the shadow is folded into the `occlusion` channel with
a different constant from the AO (`shadow_darkness` 0.45 vs `darkness` 0.7), so
recovery is off by a mean 0.03–0.05 and up to 0.44 on individual vertices — a
colour error that looks like a colour, not like a bug. The right fix is to carry
the **base** colour plus the occlusion channel and let each backend apply it,
which changes the `Geometry` contract and therefore the GL backend too, and needs
verifying in a real window (offscreen creates no GL context). Worth doing; it is
its own change.

The depth-cue half of the same darkness *was* fixed — see
[the parity tracker](/plugins/pymol-parity.md).

---

## chimol: five camera-framing tests are red

**2026-08-03.** `test_camera_framing.py` fails five ways, in isolation and in the
full run, and identically at `HEAD` with no working-tree changes:
`test_distance_follows_the_field_of_view[True/False]`,
`test_zoom_fits_every_atom_not_just_the_trace`, and
`test_camera_distance_matches_pymol[True/False]`. The measured distance is ~30×
the expected one (41429 against 1381), which points at a scale factor — chimol
scales coordinates by `_scale_factor` (default 10) — rather than at the framing
rule. Recorded here because it was found while working on something else and is
not that change's to fix; the assertions encode PyMOL's
`d = R / tan(fov/2)` and are worth keeping.

---

## chimol: a sphere impostor occludes as a flat disc (RF-522)

**2026-07-27.** The impostor is exact in silhouette and in shading, but every
fragment is written at the depth of the bead *centre*, because the fragment
shader assigns no `gl_FragDepth`. Where beads overlap each other or other
geometry, the nearer centre takes the whole disc instead of the two surfaces
intersecting — by up to one bead radius, which on the nuclear pore is tens of
ångström. Below `balls.impostor_min_atoms` the same beads are meshes and
intersect correctly, so the two depictions do not match across the threshold.

**Why it is not simply fixed.** Writing `gl_FragDepth` in *any* branch of a
GLSL 1.20 shader disables early-Z for every draw that shader serves — and this
one serves the cartoon and every mesh in the scene, which is the path a lot of
work has gone into keeping fast. The correct fix is a **separate shader program
for impostors** (its own vertex/fragment pair, the depth write confined to it),
not a branch in the shared one. Documented as a limitation in the viewer guide
in the meantime.

---

## chimol: `show` and `hide` say nothing on an empty viewer

**2026-07-27.** `spectrum`, `zoom` and `color` now answer "nothing is loaded" on
an empty viewer instead of describing a molecule that is not there, because they
all resolve a selection first and the resolver raises. `show spheres` and `hide
everything` do not go through the resolver — they go through
`RenderingMixin._toggle_representation` — so on an empty viewer they still
silently do nothing, which is the same class of wart one step quieter.

Not fixed with the others only because `rendering.py` had concurrent edits from
another working copy at the time; it is a two-line guard in
`_toggle_representation`.

---

## chimol: a point glyph's configured size never reaches the renderer

**2026-07-27.** `QtGLRenderer._geometry_to_draw_data` computes `size` from
`geom.meta["size"]` and then does not pass it to `_DrawData`, so every point
glyph draws at the 4-pixel default: `dots.size_px`, the overlay sizes, and the
`px_mode` flag that distinguishes a pixel size from a world one are all dead
configuration. Sphere impostors are unaffected — they carry a per-vertex radius,
which does reach the shader.

Not fixed in the change that found it because the fix changes the size of every
point glyph in the application at once, and the render fixtures would all need
re-inspecting; that is its own change, with its own before/after images.

---

## mmfdb: the shipped curated seed is two schema versions behind

**2026-07-28.** `tests/test_mmcif_database_resolver.py::test_packaged_seed_is_curated_and_on_the_current_schema`
is red at mmfdb `HEAD`: the packaged `data/sample_management.db` is stamped
schema **45** while `schema.SCHEMA_VERSION` is **47**. Since PRD-19 removed the
migration waterfall a stale seed is not fully migrated forward — missing
*columns* are added, stale *table structure* is not — so an unconfigured first
run copies a seed the current code cannot fully write to. The regenerator is
`build_tools/regenerate_curated_db.py` in chisurf (`--replace`).

Not fixed here because that script had concurrent edits from another working
copy at the time; regenerating and re-committing the binary seed belongs to
whoever bumped the schema.

---

## examples: a shipped example imports a package that moved, and no test reaches it

**2026-07-29.** `examples/fdb_burst_selection_roundtrip.py` opens with
`from chisurf.core.mmfdb import FluorescenceDatabase, BurstPipeline`. That
package no longer exists — MMFDB lives in `modules/mmfdb/src/mmfdb/` — so the
example fails on its second import line. It has failed silently ever since the
move because [PRD-46](/prds/prd-46.md)'s script runner
(`test/scripts/test_scripts.py`) discovers `examples/scripts/*.py` only:
anything in the `examples/` root is outside the glob and is never run.

Two separate repairs, which is why neither landed with the flrCIF alignment fix
that found it: the example needs porting to the current `mmfdb` API and a
verifying run against the `bh_spc132_sm_dna` SPC file it references, and the
runner's discovery needs widening (or the example needs moving into
`examples/scripts/`) so the next one cannot rot unnoticed. The other five root
examples at least resolve every top-level import; whether they still *run* is
exactly what nothing checks.

---
type: Reference
title: Known issues & recurring gotchas
description: Curated open functional bugs and cross-cutting engineering pitfalls distilled from working bug logs.
resource: chisurf/
tags: [bugs, gotchas, pitfalls, gui, qt]
timestamp: '2026-07-06T00:00:00Z'
---

# Purpose

This concept distills durable content out of ad-hoc working bug logs (formerly in
a top-level `notes/` folder) so the knowledge survives without keeping a raw log
in the tree. Two things are worth preserving from those logs: **functional bugs
that were still open** when the log was last touched, and **recurring root-cause
patterns** that keep re-biting across subsystems.

This is not a live issue tracker. Architecture-divergence items (spec violations,
review-found correctness bugs, schema/manifest drift) live in the
[cleanup backlog](/specs/assessment.md); this page is for runtime/functional
behaviour. The open list below was captured around **June 2026** — re-verify each
against the current tree before acting, as some may already be fixed.

# Recurring gotchas (durable — verify before you re-break them)

These are the patterns; each caused more than one bug.

- **pyqtgraph draws a 2-D array transposed.** `ImageItem`'s default axis order
  is column-major: axis 0 becomes *x*. Everything else in ChiSurf — numpy, the
  ROI subsystem, the AutoForm `image` section's own markers, click picks and
  rectangle gate, and its 3-D path — treats `(x, y)` as `(column, row)`. The
  mismatch is invisible on square or symmetric data and puts every marker and
  every drawn region on the transposed pixel otherwise. Set
  `axisOrder="row-major"` on any new `ImageItem`/`ImageView`; the array handed
  around is unchanged either way, so masks keep their `(row, col)` meaning.
- **Several pyqtgraph views destroyed together abort the process.** `ViewBox`
  registers itself in a process-global `NamedViews` dict and, when destroyed,
  walks every other registered view to rebuild its menu — reaching one whose
  `QComboBox` is already gone. At interpreter exit this aborts *after* the last
  test passed: a green run with a non-zero exit code, and no pytest summary to
  explain it. Keep at most one long-lived view per test module (module-scoped
  fixture) and build the rest under `qtbot`, which deletes them while Qt is
  still alive.

- **Collecting a TCSPC model widget between tests is a bus error.** Same
  signature as the entry above — every test prints a dot and then
  `Fatal Python error: Bus error` — but a different subject and a different
  trigger: `Fit(model_class=GaussianModelWidget, …)`. Building *five in one
  test* is stable; building one per test across five tests aborts on roughly
  four runs in five, so it is the per-test garbage collection of the fit and its
  Qt children (with the session `QApplication` still up), not the count. Not
  root-caused. Until it is, hold every such fit in a module-level list and never
  release it — see `test/gui/models/test_distance_widget_append.py`.

- **Qt Python-wrapper vs C++ lifetime.** `RuntimeError: wrapped C/C++ object …
  has been deleted` on window close. The Python wrapper outlives the destroyed
  C++ widget; a shared `_new_closeEvent` in `chisurf/gui/misc_helpers.py` calls
  through to a dead object. Any close-event / save-window-state handler must
  guard against an already-deleted widget (`sip.isdeleted`). Recurs across
  plugins (microtime histogram, MLE lifetime wizard).
- **`@property`-backed reader settings silently drop on serialize.**
  `serialize_reader_state()` / `_reader_settings_dict()` iterate
  `reader.__dict__` and skip `_`-prefixed keys. A `@property` (e.g. `is_vv_vh`)
  is not in `__dict__`; only its private backing field is, and that is filtered
  out — so the setting fails to persist across restart with no error. Any new
  `@property` on an `ExperimentReader` needs the serializer to look for the
  public property. PRD-40 aims to make AutoForm/`.view.json` own persistence and
  remove this class of bug.
- **`DataCurve[key]` returns 5 items, not 4** (since masks were added). Every
  consumer (`calculate_weighted_residuals`, `DataCurve.save`) must unpack 5. A
  `Curve.__getitem__` regression that returned `y` where `x` was expected
  produced huge residuals / wrong χ² rather than a crash — easy to miss.
- **Refresh derived outputs explicitly.** Updating input parameters and plots
  does *not* refresh derived/output parameters. After any fit switch or parameter
  edit, call `model.finalize()` and refresh the output-parameter controllers.
- **Propagate anisotropy calibration as a unit.** `g_factor`, `l1`, `l2` must
  travel together reader → dataset/group metadata → model kwargs → parameters;
  propagating `g_factor` alone was a repeated bug. Values may be scalar floats or
  parameter objects — handle both (no `.value` on a float). Coerce NaN/inf to
  finite before constructing parameters (non-finite calibration caused Windows
  access-violation crashes on project load). Steady-state anisotropy uses
  `r = (VV - VH)/(g*VV + 2*VH)` and should prefer dual-channel VV/VH.
- **pyqtgraph text overlays + threading.** Before `setHtml`/`updateTextPos` on a
  `TextItem`, verify both it and its backing `QGraphicsTextItem` are alive
  (`sip.isdeleted`); dangling items crash on Windows. Prefer plain `setText`.
  Qt-owning objects (MCP server, GUI executor) must be created/owned/destroyed on
  the main thread.
- **macOS ARM64 text rendering.** Emojis/special symbols in UI strings can hit
  CoreText paths that SIGBUS (`EXC_ARM_DA_ALIGN`); keep UI strings ASCII-safe on
  that platform. (Note this tension with the general emoji-toolbutton preference.)
- **Keep hot-path logging at DEBUG.** Logging a full DataFrame repr / per-redraw
  traces at INFO on every recompute was itself a major interactive slowdown.
  `resizeEvent` should rescale cached data (debounced), never re-bin/recompute.
- **A GUI log handler must batch, be bounded, and never touch the widget per
  record.** `QTextEditLogger` sits on the root logger, so *any* subsystem's
  logging pays its cost. Writing to the widget from the logging thread is
  undefined behaviour (`QBasicTimer` warnings, crashes); inserting one row per
  record pays a relayout plus `scrollToBottom` each; and running the O(rows)
  console filter per record makes a burst O(rows^2) — a data load logging a few
  hundred records took seconds. Records are queued and applied in batches on the
  GUI thread (one wake-up per batch, ~50 ms rate limit, newest-only for the
  status bar), the console is capped at `LogListWidget.max_rows`, and the filter
  pass is debounced and skipped entirely while no filter is active.
- **File-save dialogs seed from the data location.** Default the save dir to the
  loaded data file's folder / `cs.working_path` (not Qt's last-used dir) and
  update `cs.working_path` after save. `chisurf/gui/main.py` "Save Fit" is the
  reference.
- **Plugin menu-callback contract.** The menu system `exec`s a plugin file with
  `__name__ == "plugin"`; without an explicit `if __name__ == "plugin": load()`
  guard the plugin silently does nothing.
- **Plugin `.ui` paths must be plugin-relative and existence-checked** (cached
  resolver) before `uic.loadUi`; stale relative paths break silently after folder
  moves. Contract tests cover this — keep them.
- **Batch/action dispatch must not swallow per-item exceptions.** A batch
  `fit.add` that swallowed callback errors reported success while creating no
  fits. Route default actions to `cs.current_fit`, not fit index 0.
- **macOS QComboBox popups render translucent.** Node/embedded combos need an
  explicit opaque palette + `setAutoFillBackground(True)` and cleared
  `WA_TranslucentBackground` on the view; QSS `QComboBox QAbstractItemView`
  alone does not fix the popup window. (Seen in the light-path node editor — see
  [Light Path Simulator](/plugins/profiles/lightpath-simulator.md).)

# Open functional issues (re-verify against current tree)

Grouped by area; captured June 2026.

**The generated manual still names the retired emcee dependency at its source
(2026-07-28).** `docs/manual/*.rst` are generated from
`docs/_old_manual/manual.docx` by `pixi run -e docs docs-manual`. The three
places that said ChiSurf "uses emcee" (and showed `method: emcee` in the settings
listing) were corrected **in the generated RST**, because the sampler is now
in-tree; the `.docx` still says it, so a regeneration reintroduces the wrong
statement. Fixing it properly means editing the binary source or retiring that
manual page in favour of `docs/concepts/parameter_uncertainty.md`, which now
covers the same ground.

**Anisotropy now follows Schaffer/Eggeling throughout (settled 2026-07-27).**
`r = (Fp - G Fs) / ((1 - 3 l2) Fp + (2 - 3 l1) G Fs)` with **G = S_par/S_perp**,
the ratio a paper quotes and the one tttrlib's estimators already took. Four
sites moved together — `compute_g_factor_perrin` (was returning the reciprocal),
`anisotropy_from_integrals`, `LifetimeModel._tcspc_rt_curves`, and the
`vm_rt_to_vv_vh` generator (now divides the perpendicular channel by G). The
chain closes: the generator round-trips exactly at every G, the calibration's
output feeds its own consumer, tttrlib's formula and the VM combination
`vv + 2 G vh` and all three return the truth. That also retires the two splits
recorded here earlier — the cross-repo one and the VM one — without touching
tttrlib or the five VM call sites.

**The l1/l2 parameterisation is settled too (2026-07-27).** It was the
generator that was out of step, not the correction. `vm_rt_to_vv_vh` built an
ideal pair and mixed it with a 2x2 matrix (Koshioka 1995), which is a different
meaning for l1/l2 and does not invert the Schaffer correction. tttrlib states
the right one in its own forward model (`DecayFit23.cpp`:
`x_vv[2] = r0 (2 - 3 l1)`, `x_vh[0] = 1/g`, `x_vh[2] = r0 (-1 + 3 l2)/g`):

    VV = vm (1 + (2 - 3 l1) r),    VH = vm (1 - (1 - 3 l2) r) / G

Substituting that into `(sp - G ss) / ((1 - 3 l2) sp + (2 - 3 l1) G ss)` makes
numerator and denominator collapse to `3 vm (1 - l1 - l2) r` and
`3 vm (1 - l1 - l2)`, so the round trip is exact for any l1, l2 and G. The
generator now uses it, and the round-trip test covers a non-unit G and non-zero
mixing together — the combination that exposed the old one (0.274 and 0.318
against 0.300).



**Found 2026-07-27, not fixed: the PCH settings panel is clipped at its right
edge.** `chisurf/plugins/pch/gui/tool.py` puts the settings form in a
`QScrollArea` with `setHorizontalScrollBarPolicy(ScrollBarAlwaysOff)`, and the
form is wider than the splitter gives it, so the File / Channels / Bin Time /
Micro Time editors run past the window edge and their right-hand ends are
unreachable — visible in any screenshot of the tool at its default 1000×650. The
fix is a layout one (let the form shrink, or give the splitter a sensible initial
size, or stop suppressing the scroll bar), not a one-liner, so it was left out of
the message-groups change that surfaced it.

**Reported 2026-07-27. Plugin names and menu categories are never translated,
in any locale.** Everything a plugin's `manifest.json` shows *except* its name
is translated: `chisurf/core/plugin/manifest.py` runs `description`, `summary`,
`experimental_message` and `deprecation_message` (plugin-level and per RPC
method) through `tr()` at load time, and the extractor collects them. The two
fields the user actually reads in the menu — `display_name` and `categories` —
are excluded on purpose at *both* ends: `extract_strings.py` leaves them out of
`TEXT_KEYS` and `manifest.py` keeps them canonical, each with a comment saying
they double as menu-path / identity keys and are "localized at the nav seam".

**That nav seam does not exist.** The plugin-menu builder in
`chisurf/gui/__init__.py` (`parse_hierarchical_plugin_name`) splits
`display_name` on `:` into hierarchy parts plus a leaf and uses both verbatim —
there is no `tr()` call anywhere in that path — and the ribbon does the same via
`ribbon_categories.py::_parse_hierarchical_plugin_name`. So a manifest naming
`Spectroscopy:Single-Molecule:PCH` renders as those exact English words under
`de` and `fr`. Verified: "Burst Analysis", "Microtime Shifter" and
"Spectroscopy" have zero entries in `chisurf_en.ts` *and* `chisurf_de.ts` — the
strings are not merely untranslated, they were never offered to a translator.

This compounds with the ribbon entry below: the ribbon's plugin categories are
built from these same paths, so wrapping the ribbon's own literals in `i18n.tr`
would still leave every plugin-derived entry English until this seam is built.

The reason it cannot be fixed by wrapping the field is worth stating, because it
is the whole design problem: `display_name` **is** the identity key. It is the
menu path, it keys `plugin_order` in the ribbon, and it feeds
`get_plugin_settings_path(plugin_name)`. Translating it in place would move a
plugin's settings directory and lose its ordering when the user switches
language. A fix has to separate identity from display — keep the canonical path
as the key, translate each path segment and the leaf only at render time, and
teach the extractor to emit those segments (they are a small closed vocabulary:
Spectroscopy, Single-Molecule, FRET, Tools, Structure, Simulation, …). The same
anchoring rule as everywhere else then applies: any code re-deriving a key from
display text must repeat the identical `i18n.tr(...)` call.

**Reported 2026-07-27. The ribbon is not translated, and the mechanism that
looks like it covers it does not.** Switch the language and the whole top
navigation stays English. `chisurf/gui/widgets/ribbon/` contains **no**
`i18n.tr` call and no `.ui` file, so none of its text is translatable, and none
of it is even *extracted*: `build_tools/i18n/extract_strings.py` collects from
`.view.json`, `manifest.json`, `.ui` files and AST `i18n.tr(...)` calls, and the
ribbon matches none of those. Verified — "Other Tools", "Utilities" and
"Clipboard" have zero entries in `chisurf_en.ts`. ("Fitting" and "Analysis" do
appear, but from `fittingWidget.ui`; the ribbon's own literals are never looked
up, so those entries are a coincidence, not coverage.)

Two groups of strings are affected:

- **Category and panel titles**, hard-coded in `ribbon_categories.py`: Main,
  Edit, Analysis, Tools, Setup, View, Help, Documentation, Basic, Clipboard,
  Fitting, Utilities, Other Tools.
- **The ribbon's own chrome**, hard-coded across `titlewidget.py`,
  `ribbonbar.py`, `panel.py`, `toolbutton.py`, `ribbon_auto_fold.py`: "Collapse
  Ribbon" / "Expand Ribbon", "Panel options", "Remove from Quick Access
  Toolbar", "Show All Hidden Items", "Pin ribbon" / "Unpin ribbon", "Open Help
  Plugin", and the "ChiSurf" title and its tooltip.

Why it went unnoticed: `main.py::_retranslate_interface` tears the ribbon down
and rebuilds it on every language change, and its docstring says that rebuild
"re-reads every string through the freshly installed translator". That holds for
ribbon buttons derived from **QActions** — those come from `gui.ui` and are
retranslated in the step before — but a hard-coded literal re-read is the same
English literal. The rebuild is therefore not the fix, and the docstring
overstates what it achieves.

Fixing it is the ordinary in-place path already used for rich non-form tools
(wrap each static string in `i18n.tr`, see `tttr_time_windows` /
`tttr_microtime_shifter`), after which the extractor picks them up. Note the
ribbon is a **vendored** widget family: `ribbonbar.py`, `panel.py`,
`toolbutton.py`, `titlewidget.py` etc. carry upstream chrome strings, so decide
per file whether to localize in place or to keep the vendored copy pristine and
translate only ChiSurf's own layer (`ribbon_categories.py`,
`ribbon_auto_fold.py`, `ribbon_file.py`). Also mind the anchoring gotcha in
[/subsystems/i18n.md](/subsystems/i18n.md): the ribbon styles buttons by object
names derived from action text, so any `i18n.tr` added there must be mirrored
wherever a key is re-derived from display text.

**Found 2026-07-26 while unifying the progress bars. `PDBFolderLoad` cannot be
constructed at all.** `chisurf/gui/widgets/pdb/pdb.py` has rotted against a
refactored `TrajectoryFile`, in two places: `__init__` calls `TrajectoryFile()`
and `onLoadStructure` calls `TrajectoryFile(use_objects=…, calc_internal=…,
verbose=…)`, but the current constructor requires a positional `p_object` and
takes none of those keywords. The widget is reachable — the modelling
experiment page builds one (`gui/widgets/experiments/modelling/modelling.py`) —
so that page is broken too.

Half of it is fixed: `LoadThread`'s `procDone`/`partDone` signals had been
commented out during the PyQt-to-qtpy move (their `pyqtSignal` spelling did not
survive), so construction raised `AttributeError` one line earlier still; they
are restored as `QtCore.Signal`. The remaining `TrajectoryFile` calls need a
real port, and what `use_objects` / `calc_internal` were meant to select is no
longer expressed anywhere in that class — so the intent has to be recovered
before the call sites can be rewritten, which is why this is logged rather than
guessed at.

**Found and fixed 2026-07-26 — and the first diagnosis was wrong.**
`test_consistency_check_rejects_the_wrong_kinetic_scheme` was accepting a
deliberately wrong scheme at p = 0.297. It was filed here as "not the rename,
bisect the concurrent fitting-layer edits". That attribution was wrong: the
cause was the earlier change that made `k_ex` an **absolute rate in Hz**
(time-binned PDA) while this test still set it as the dimensionless
`K = (k1 + k2) T`. At 2 Hz over a 2 ms window that is K = 0.004 — the
"dynamic" data the test generated was *static*, so the static scheme it exists
to reject fitted it perfectly. The sibling test in
`test_pda2c_model_editor.py` had already been converted; this one was missed.

Fixed by converting through the dataset's observation time, as the sibling
does. With real dynamics the model recovers K = 2.04 against a truth of 2.0 and
the static scheme is crushed (chi2r 176 against 1.38), so the rejection is now
emphatic.

Worth keeping from the episode: **a unit change in a shared parameter needs a
sweep of every test that sets it**, because a test that silently generates the
wrong physics still passes — it just stops testing anything. And the acceptance
branch of that pair is now pinned to a typical realisation: at K = 2 the default
seed gives chi2r = 1.55 at the *true* parameters where seeds 2-8 give 0.80-1.18,
and the bootstrap correctly rejects that draw. Asserting on it would test the
noise, not the model.

**Found 2026-07-26 while making the PDA3c rate matrix fittable.** A rate fitted
by the three-colour dynamic model comes out **systematically fast, by some tens
of percent**, and more computation does not help. Measured on bursts simulated
from a known two-state scheme by an independent forward route (a fresh distance
triple per state per burst, mixed by sampled occupation times, then split
multinomially): the profile likelihood along `k_tot` peaks at 650–700 Hz for a
truth of 500 Hz, and the argmax moves by at most one grid step from 600 to 8000
sampled trajectories and from an occupancy resolution of 24 to 192. So it is
**not** Monte-Carlo noise in the occupation-time sampling — that part is exact
in distribution.

The cause is the approximation made *outside* the sampling, in
`Pda3cModel._mean_channel_probabilities`: each state is collapsed to its
distance-averaged per-photon probability vector *before* the occupation-time
mixing, so the intra-state distance spread contributes to the predicted
burst-to-burst width differently than it does to real bursts. Fixing it properly
means carrying the distance quadrature through the dynamic average (nodes x
occupancy nodes x bursts), which is a real cost increase and a design decision
about where to truncate — hence recorded rather than fixed in the change that
found it. Until then, `pda3c.py`, the concept page and the guide all say to read
a fitted rate as an exchange **timescale**, not a rate measurement; comparisons
between conditions are sound.

Note this was invisible before, because the rate matrix was a plain array
attribute nobody could fit — the bias only became reachable when the rates
became parameters.

**Narrowed down 2026-07-26, with the exact statement of the defect.** The same
approximation has a consequence with a *checkable* answer: **the multistate
route does not nest the static model.** At 1e-3 Hz over a 2 ms window nothing
switches, so every molecule sits in one state for the whole burst and the
likelihood must equal the static mixture's term for term. It is off by **2357
log-likelihood units** — because a pure trajectory is evaluated at its
distance-*averaged* probability vector where the static model integrates the
likelihood over the distance distribution, and those differ by Jensen. A
static-versus-dynamic comparison (an F-test, a model choice) is therefore
meaningless in exactly the regime where the two models are nested.
`test/models/test_pda3c_rates.py::test_the_multistate_route_nests_the_static_model`
records this as a **strict xfail**, so it will fail loudly when fixed.

**Two approaches tried and rejected, so nobody repeats them:**

1. *Exact atoms alone.* Giving pure trajectories the full static treatment, with
   the analytic weight `pi_i exp(-lambda_i T)` rather than their sampled
   frequency, makes the static limit exact to five decimals and removes a
   1901-unit spike at slow exchange (caused by occupancy quantisation merging a
   switching trajectory into a near-pure cell). But it leaves the *interior*
   annealed, and the halves are then inconsistent: the fit compensates by
   slowing exchange, the recovered rate moves from 199 to **65** against a truth
   of 200, and the profile bias flips from +30% to −30% (stably, 300–350 Hz at
   every sampling setting). Fixing one half alone is not an improvement.
2. *Sampling the joint average.* Drawing one quenched distance triple per state
   per occupancy node is the right average in principle, but the node labels
   *are* the occupancies, which shift continuously with the rates — so
   neighbouring evaluations see unrelated conformations however the draws are
   keyed (a per-node hash of the quantised occupancy included). The optimiser
   reads the noise as structure and walks off: 200 → 52.

**The fix is to carry the distance quadrature through the occupancy average** —
both halves together, deterministically — and the open question is where to
truncate it, since the product over states is combinatorial in the quadrature
nodes.

**Found 2026-07-26 while adding typeset labels.** `pytest test/fitting` used to
**abort the interpreter** part-way through (~47 %), so everything after it never
ran. `chisurf/macros/core_data.py::add_dataset` popped a `MyMessageBox` on its
two "nothing was read" paths; a modal dialog needs a GUI to close it, and with no
`QApplication` at all Qt aborts the process outright. The exception path a few
lines below already guarded on `gui is None` with exactly that reasoning — the
two earlier sites had been missed. Fixed by applying the same guard (head-lessly
the log is the report), which is what makes the suite run to completion.

That uncovered **14 pre-existing failures and 1 collection error** that the abort
had been hiding. All confirmed identical on an unmodified tree with only the
guard applied, so none belongs to the change that found them; recorded rather
than fixed because they span five unrelated subsystems:

- `test_fit_state.py` (5) — model `get_state`/`set_state` round-trips, including
  the FRET-Gaussian and PDA length-preservation contracts.
- ~~`test_grouping.py` (3) + `test_grouped_default_linking_contract.py` (1)~~ —
  fixed 2026-07-26; they read *source text* from paths that no longer exist and
  are now behavioural.
- ~~`test_experiment.py::test_FCS_Reader`~~ — fixed 2026-07-26. Remaining:
  `test_models_regression.py::test_parse_model_evaluation`,
  `test_parameter.py::test_equality`,
  `test_fit.py::test_fit_save_full_length_curves_have_nan_padding`,
  `test_reference_models.py::test_lifetime_model_convergence`.
- `test_derived_quantities.py::test_a_well_determined_ratio_is_where_the_delta_method_is_right`
  (noted 2026-07-28) — the skew diagnostic fires on a ratio it is meant to pass
  (`0.771 +0.0207 -0.0236`), so the asymmetry threshold is tripped by ordinary
  Monte-Carlo noise rather than by real skew. It samples with `method='de'`,
  which the ensemble-sampler change did not touch; recorded rather than fixed
  because the fix is a re-derivation of the threshold in `derived.py`.
- `test_sampling_diagnostics_report.py::test_posterior_summary_prefers_a_converged_chain`
  (noted 2026-07-28) — **flaky, roughly one failure in four** on an unchanged
  tree. It asserts that every posterior entry reports `method == 'mcmc'` after
  sampling; on a failing run they report `'laplace'`, i.e. the MCMC result was
  not adopted and the Laplace approximation stood. Measured by running the test
  alone five times: 2 failed, 3 passed, no edits in between.

  Worth knowing *how* this was established, because a single controlled run said
  the opposite. It first appeared while checking whether the atom-dtype change
  had caused it: reverted, the test passed; restored, it failed — a clean-looking
  A/B that was pure coincidence. Only repetition showed it flips on its own.
  A one-shot before/after cannot tell causation from flakiness, and a flaky test
  will happily frame whatever change is in flight.
- ~~`test_group_polarization_any_size.py` errors at collection.~~ — fixed
  2026-07-26.

**`test/gui` cannot currently run to completion (noted 2026-07-28).** It
**segfaults** (exit 139) about 19% in, at `test_channel_definition_lut_box.py`
— a file whose 8 tests all pass when it is run *alone*, so the crash is
cross-test state and not that file's doing. 17 failures precede it. Everything
after the crash is simply unrun, which is the worse part: the suite reports
nothing about roughly four fifths of itself.

Established as independent of the atom-dtype change by running the whole area
with the old `|U1` field and the new `|U4` one: **byte-identical** progress,
the same 17 failures, the same crash at the same point. The TTTR
channel-definition wizard and LUT tools had several files under concurrent edit
at the time, which is the first place to look.

**Update 2026-07-29 — there is also a hang, before the segfault.**
`test/gui/test_gui_plots.py::test_plot_updates_when_parameter_changes` did not
finish in **10 minutes** when run entirely on its own; it errors in the
`chisurf_app` fixture (`chisurf.gui.get_app()`, which boots the whole main
window) and then stalls. Seen while checking that a chiplot fix had not broken
plot consumers. A second instance's `pytest test/gui -q` was 87 minutes in at
the same moment, so a shared-resource conflict (server ports, the settings
directory) cannot be excluded and *neither run is a clean measurement of the
other* — but the solo run had the whole boot to itself and still did not
progress, which the concurrency explanation does not cover. Whoever picks this
up should time the fixture alone on an idle machine first.

**Found 2026-07-26 while closing [RF-182](/reviews/findings.md#rf-182).**
`test/core/test_curve.py::Tests::test_reading` passes when `test/core` runs on
its own and fails when `test/fitting` has run first in the same process: the
yaml round-trip comes back with a different `unique_identifier`. It is an
ordering artifact over process-wide registry state, not a defect in the curve
I/O, and it is identical with and without the `DataCurve` change that surfaced
it. Not fixed here because the poisoning module is somewhere in `test/fitting`
as a whole (no single file reproduces it) and chasing it is a separate job.
Two order-dependent failures in the *same* run **were** fixed:
`test_fit.py::test_fit_parse` and `::test_fit_data_setter` used
`chisurf.core.models.parse` / `chisurf.core.fitting.fit` while importing only
the package roots, so they passed only when another test module had imported
those submodules first; the test module now imports them itself.

**Found 2026-07-26 while closing [RF-168](/reviews/findings.md#rf-168) in the
BVA layer.** `test/plugins/burst/test_background_gui.py` has two failures that
are stale against the AutoForm conversion of the Burst Background tool
(`61a2803ae`, then `993577745`), unrelated to the BVA change that surfaced them.

- **`test_diagnostics_plots_build_and_render`** asserts
  `hasattr(w, "iht_plot")` on `BurstBackgroundEstimator`; the AutoForm rebuild
  no longer exposes named plot attributes on the tool, so the assertion fails at
  the first line and the render path is never exercised.
- **`test_semantic_detector_colors`** does
  `from chisurf.plugins.burst.burst_background import _det_color`, which no
  longer exists — the detector-colour mapping moved with the conversion.

  Both need re-pointing at the AutoForm section handles rather than a code fix;
  left open here because doing that properly means driving the tool headlessly
  and inspecting the render (the screenshot rule), which does not belong in an
  unrelated docstring/dedup change. The colour test in particular should assert
  through a public seam, not a private helper name.

**Found 2026-07-26 while routing the fit jobs through the job manager
([INC-08](/specs/assessment.md#inc-08)).** Two failures in the server suite,
both confirmed identical on the unmodified tree, both about the RPC *transport*
rather than the services under change — left open because fixing them means
re-deciding the client's error contract, which is [SV-04](/specs/assessment.md#sv-04)
territory and does not belong in an unrelated change.

- **Eight `test/server/test_rpc_edge_cases.py` tests are stale against the
  SV-04 error contract.** `ChisurfClient.call()` now raises `RemoteError` for
  application-level errors (that *was* the SV-04 fix), but these tests still
  expect an error **dict** back — e.g. `test_very_long_method_name` calls an
  unknown method and asserts on the returned payload, and gets
  `RemoteError: method '…' not found`. The tests need updating to
  `pytest.raises(RemoteError)`, not the code.
- **`pytest test/server` never terminates; the wedge is in
  `test_integration_lifecycle.py`.** Localised on 2026-07-26 by an A/B against a
  clean `HEAD` worktree: `pytest test/server --ignore=test/server/test_integration_lifecycle.py`
  finishes in **86 s** with **21 failed, 501 passed**, while the same run *with*
  that file idles indefinitely (0 % CPU) inside `TestParameterLifecycle` —
  stack in `zmq_ctx_destroy` → `zmq::mailbox_t::recv` → `poll`, i.e. a context
  termination waiting on a socket an earlier test left open. Run in isolation
  (`-k TestParameterLifecycle`) the class completes, so it is leaked state from
  earlier tests in the file, not the class itself. Until a socket is closed (or
  `LINGER` set) somewhere upstream, exclude that one file to run the suite.
  The 21 remaining failures are pre-existing at `HEAD` — the eight stale
  `test_rpc_edge_cases.py` expectations above plus fit-endpoint tests
  (`test_fit_save_endpoint`, `test_fit_list_includes_chi2r`,
  `test_model_finalize_endpoint`, …).

**Found 2026-07-25 while migrating the imaging tools onto the ROI subsystem.**
Three red tests, each pointing at real behaviour rather than a stale test alone.
Left open because each needs a decision from the owner of code being actively
worked in this tree; the fourth found alongside them (a `np.float` in
`test_fluorescence`, removed in NumPy 1.24) and three stale imports of the
retired `_dev/fluorophore_db` plugin were fixed on the spot. Two of the three —
the `calculcate_spectrum` term count and the binary `.pqres` read — were
resolved on 2026-07-25 and 2026-07-26 and are recorded below.

- **`test_structure.py::test_labeled_structure` fails on the labelled-structure
  path.** Molecular modelling has moved out of chisurf into the external
  framework, so this may be a test that outlived its subject rather than a
  live defect; confirm before either fixing or removing it.

**Found 2026-07-25 while closing [BUG-09](/specs/assessment.md#bug-09).** Both sit
in the anisotropy area; neither is reachable from a production call path today.

- ~~**`vm_rt_to_vv_vh` puts the g-factor in the one place that is not
  invertible.**~~ Fixed 2026-07-26 in its own change, as
  [RF-231](/reviews/findings.md#rf-231). It computed `vh = vm · (1 − g·r)`, while
  its sibling `calculcate_spectrum` — the one the fitting models actually call —
  computes `g · vm · (1 − r)`; only the latter satisfies
  `r = (I_VV − I_VH/g) / (I_VV + 2 I_VH/g)`, because a detection sensitivity scales
  the whole perpendicular channel, not just its depolarization term. The helper now
  uses that placement, the two doc pages that repeated the wrong formula were
  corrected with it, and `test_vm_rt_to_vv_vh_recovers_anisotropy` pins the round
  trip *and* term-for-term agreement with the spectrum path at `g ∈ {0.8, 1, 1.5}`.

**Fixed 2026-07-25/26 — kept here because the *patterns* keep recurring**

- **Five test files about one behaviour, and none of them could fail.**
  `test_group_polarization_any_size.py`, `test_polarization_fix.py`,
  `test_unified_polarization.py`, `test_group_reference.py` and
  `test_polarization_group_update.py` were written during a single bug hunt and
  between them contained *zero* assertions about polarization: each
  `logger.error(...)`d on a wrong value instead of asserting; one took a
  `num_datasets` argument with no fixture and no `parametrize`, so pytest errored
  at collection and the sizes were only passed from a `__main__` block; one ended
  `return True`. Consolidated into one parametrized file that asserts the
  contract stated in `Anisotropy.set_polarization_by_group_position`. The open
  question this was filed under — does a 3-fit group really alternate
  vv/vh/vv? — was not an owner call after all: the code answers it in so many
  words, and it does. The rewrite also found the expectation that had been
  logged-and-ignored for years: two fits *added separately* are two groups of
  one, so both are `vm`, not the `vv`/`vh` the old test wanted. **Pattern: a
  test that logs instead of asserting is worse than no test — it occupies the
  slot where a real one would go.**
- **Four "contract" tests grepped source text out of files they could not
  open.** `test_grouping.py` and `test_grouped_default_linking_contract.py`
  asserted that `"def _is_global_fit_dataset(" in Path("cs/macros/core_data.py")
  .read_text()`. The package was renamed `cs/` → `chisurf/` and one path was
  relative to the working directory, so all four raised `FileNotFoundError` —
  a test that asserts a substring appears in a file it cannot open tells you
  nothing twice over. Replaced with tests of what the functions do: which
  parameters count as nuisance, that grouping links the physics and leaves the
  instrument parameters local, that the global-fit dataset survives
  `remove_datasets`. **Pattern: asserting on source text pins the spelling, not
  the behaviour, and rots at the first rename.**
- **Every unnamed data group called itself `ExperimentDataCurveGroup`.**
  `DataGroup.name` documented a fallback to the current dataset's name, in a
  `except KeyError` branch that could never run: `Base.__init__` stamps
  `self.__class__.__name__` into `__dict__['name']` whenever no name is passed,
  so the key was always present. After loading an FCS file the dataset list
  showed the class name instead of the file. A stamped class name is now treated
  as absent. **Pattern: a fallback guarded by a condition its own constructor
  makes impossible is dead code that reads as a feature.**

- **A binary `.pqres` file was read with `np.loadtxt`, and three layers had to
  break for that to happen.** `FCS.read()` accepted a `reader_name` argument,
  documented it, and then dropped it on the floor — every call used the reader's
  configured default (`kristine`), so asking for `'pqres'` sent a binary file to
  a text parser and it died on byte 0xff. Behind that, `read_pqres_fcs` returned
  a `DataCurveGroup` where the dispatcher expects `list[dict]`, so the format had
  never worked through `read_fcs` at all. Behind *that*, every `<base>X`/`<base>Y`
  tag pair was promoted to a curve — the standard deviations, the weights and a
  25 025-point TCSPC decay included — yielding 10 curves where the file holds 3.
  **Pattern: a keyword argument that is accepted and ignored is worse than one
  that raises; and a test that `print`s and `return`s reports green over all of
  it.** (`test/fluorescence/test_pqres.py` now asserts the three named
  correlations, their 54 lag times and finite non-zero weights.)
- **The anisotropy spectrum test pinned a VH model that cannot be inverted.**
  The test asserted `−2·r` in the perpendicular channel where the code produces
  `−1·r`, and the "16 terms vs 8" term-count mismatch it was filed under was the
  union/concatenate mixing form, not a defect. The definition of `r` settles it:
  only `g · f_VM · (1 − r)` round-trips back to the `r(t)` that generated the
  pair. The test now compares the *decays* the spectra stand for against the
  analytic definitions, so it is immune to the term count. **Pattern: a test
  whose expectation was recorded from the implementation pins the bug as
  hard as it pins the behaviour — derive references from the definitions.**
- **A test loaded its subject from a hand-built file path and rotted silently.**
  `test/fitting/test_anisotropy_integrals.py` built
  `parents[1] / "chisurf" / "fluorescence" / ...` and `exec_module`d it; when the
  module moved under `chisurf.core` the path pointed at `test/chisurf/...` and the
  file errored at collection instead of failing loudly at a rename. Replaced with
  a normal import (the module pulls in nothing but numpy). **Pattern: importing by
  path defeats every tool that would have caught the move.**
- **A GUI modal reported an error from the macro layer, so head-less loading
  hung forever.** `core_data.add_dataset` caught every read failure and built
  `MyMessageBox`, whose `__init__` calls `exec_()`. With a `QApplication` but
  no user — CLI, script, test, the assistant — that blocks indefinitely; with
  no `QApplication` at all Qt *aborts the process*. A file that could not be
  read therefore looked like "loading is very slow". Errors are now re-raised
  when there is no GUI. **Pattern: never report from core/macro code with a
  modal; the caller cannot always click.**
- **`np.float` and `np.float_` were still used in 7 modules**, and NumPy
  removed them (1.24 and 2.0). Three FCS readers — ConfoCor3, ALV `.ASC` and
  PyCorrFit — raised `AttributeError` on the first data line they parsed, so
  those formats simply did not load. Fixed to `float`/`np.float64`, with a
  guardrail test that scans for the removed aliases. **Pattern: a removed
  alias only fails when its code path runs, so it hides in readers for
  formats nobody exercised recently.**
- **`GeneralFCSModel` exposed all three diffusion presets to the optimiser**
  while computing with one, so a fit reported its untouched defaults
  (`N = 1.0`, `D = 300.0`) as results and `n_free` was 15 instead of 5.
  **Pattern: when a model holds alternative parameter groups, the parameter
  list has to follow the active one.**

**Test collection**
- **RESOLVED — `test/core/test_rename.py`** no longer breaks collection of the
  whole `test/core` package. It used to be an ad-hoc tttrlib file-locking script
  that ran at import time against a hardcoded `e:\dev\chisurf\…\Leica_SP8.ptu`;
  it is now a real test over the repository's own `test/data/clsm/`, guarding
  that reading a photon file leaves no handle that blocks renaming or deleting it.
- **RESOLVED — the `chisurf.gui.widgets.yaml_utils` test modules are gone**
  (2026-07-26). Four modules imported `dump_yaml`/`prepare_for_yaml` from a
  module that **has never existed** — `git log -S` finds no commit adding or
  removing it — so they failed at collection with `ModuleNotFoundError` and took
  `test/settings`, `test/plugins` and `test/gui` down with them. They were
  print-driven prototyping scripts that never ran against real code (the same
  never-existed-API class as `test/models/test_user_models.py` below), so they
  were deleted and replaced by `test/settings/test_settings_yaml_lists.py`,
  which asks the same question — do list-valued settings survive as lists? — of
  the serializer that does exist (`chisurf/core/settings/settings_utils.py`).
- **RESOLVED — `test/plugins` collects again** (2026-07-26). Three further
  modules tested `chisurf.plugins._dev.chato`, a scratch tree that is
  **gitignored** (`.gitignore:78`) and absent from the repo, and one tested
  `chisurf.plugins.chat`, deleted in `c28d07b65`; all four were untestable by
  construction and were removed. `test_plugin_manager_mistral_icon.py` imported
  a real class (`AIIconRateLimitError`) that the package simply did not
  re-export — it now does. Two `test_manifest.py` files in `__init__.py`-less
  directories also collided on the module name (`import file mismatch`); the
  three `test/plugins/*/` subpackages got their `__init__.py`.
  **Pattern: a test module whose import fails takes its whole package's
  collection with it, so one dead import hides hundreds of live tests.**
- **OPEN — `test_plugin_manager_mistral_icon.py`: 6 tests red since the HTTP
  client swap** (found 2026-07-28 while test-gating an unrelated plugin-manifest
  fix). `085bd79b4` ("an HTTP client of our own") moved
  `PluginManagerWidget._post_mistral_json_with_retries` and its siblings off an
  injected session object onto the module-level `chisurf.core.http.post`, and
  dropped the `session` parameter — but the tests still pass a
  `SimpleNamespace(post=...)` as the second positional argument, so it binds to
  `path`, the real path binds to `headers`, and every call raises
  `TypeError: … got multiple values for argument 'headers'`. The signature is
  identical in HEAD and in the working tree, so this is not an in-flight edit:
  it is red on a clean checkout. The fix is test-side — monkeypatch
  `chisurf.core.http.post` instead of injecting a session — and it is small, but
  `chisurf/plugins/core/plugin_manager/gui/tool.py` has concurrent uncommitted
  edits in exactly this HTTP path from another instance, so rewriting the tests
  against a signature that may still be moving was left to whoever lands that
  migration. Nothing outside these 6 tests is affected; the rest of
  `test/plugins` (321 tests) is green.

**Qt teardown in test suites**
- `chisurf/plugins/fcs/fcs_filter_calculator/test/test_widgets.py` aborts with
  `libc++abi: Pure virtual function called!` when the file is run as one
  process. Every test passes individually, and the abort is independent of the
  test that happens to be running when it fires, so it is cross-test teardown
  (a C++ object outliving its Python wrapper, the usual pyqtgraph/`DockArea`
  shape) rather than a defect in any one test. Confirmed pre-existing in July
  2026 by reproducing it with the then-current working changes stashed.
  Workaround: run the file with `--forked`, or per-test, until fixed.

**Project save / restore**
- Project round-trip: decay/lifetime models do not save & reload (critical).
- Save→close→open resolves the active window via `chisurf.cs` after teardown
  removed it → `AttributeError: module 'chisurf' has no attribute 'cs'`.
- Dataset removal no longer confirms and closes dependent fits.
- TCSPC "stacked" (`is_vv_vh`) not persisted across restart (see the
  `@property` gotcha above).
- Undo/redo does not destroy stashed dataset/fit UI windows
  (`history_replay.apply_entity_lifecycle`) — stale windows linger.

**Fit creation / fitting**
- Access violation (`0xC0000005`) on fit creation after dataset load, in
  TCSPC/anisotropy chinet init — keep parameter init scalar/type-safe into the
  native layer (no catchable Python exception at the crash boundary).
- FCS MaxEnt fit does not autorange on creation → zero points in range →
  non-computable out of the box.
- Parameter-widget edits do not fully propagate to model/chinet.

**Plugins / tools**
- NDXplorer stays blocked after data load; clear-then-reload shows no data — a
  proper `reinit()` (reset caches, plot objects, combos) is needed rather than a
  partial `clear_plots`.
- TraceBrowser does not populate its file list on folder open (severe).
- Correlator/FCS channel-preset saving does not work.
- TTTR Image Browser exports to the wrong folder; anisotropy "Save CSV" ignores
  the loaded-data location (see file-save gotcha).
- BH / SPC-130 micro-time resolution is wrong and not corrected on load (data
  correctness).
- mmfdb-admin: cancelling the password prompt still opens the UI.

**Tests**

Found while verifying an unrelated change (2026-07-25) and **all resolved on
2026-07-25**; `pytest test/core` and `pytest test/models` both run clean (498
passed / 3 skipped, and 246 passed). Kept as a record of what each turned out to
be, because three of them were defects in the code rather than in the tests.

- `test/core/test_mmfdb_schema_migration.py` **did not finish** — this is what
  made a full `pytest test/core` run look like a hang. `sqlite3`'s `conn.backup()`
  retries a busy source forever, and the migration held an open write transaction
  while snapshotting. Fixed in the MMFDB repository (commit `38973c5`) by
  committing before the backup, with a regression test.
- `test/core/test_rename.py` failed at **collection** on a hard-coded Windows path
  (`e:\dev\chisurf\test\data\clsm\Leica_SP8.ptu`), taking the whole directory down
  with it. Rewritten against the repo's own test data.
- Of the four API-drift files, three were **code** defects, not stale tests:
  `Curve.__init__` did not coerce `None` axes and `to_dict` had lost
  `skip_qt_widgets`; `DataGroup.name` had lost its setter; and
  `Project.load` called the classmethod `Session.load` as if it mutated the live
  session, so opening a project restored no chinet nodes at all (`Session.clear()`
  was missing too). Only `test_base.py` was a stale test — one incidental
  assertion contradicted the dedicated UUID spec, and the spec wins.
- `test/models/test_fret_line.py` asserted frozen coefficient strings and lifetime
  arrays computed on `np.logspace(np.log(1), np.log(500))` — base-10 exponents, so
  that "1–500 Å" axis really ran to ~1.6 million Å. Worse, the axis is a module
  global that nothing restored, so those tests silently changed the distance grid
  for every test that ran afterwards. Rewritten to assert the relations that
  define a FRET line, with setUp/tearDown restoring the global. The `KeyError`s
  were real: fixed model constants (`R0`, `t0`, `s(G,n)`) live in
  `parameters_all_dict`, not `parameter_dict`, which holds only free parameters.
- `test/models/test_user_models.py` tested a registry —
  `register_user_model`, `load_user_models`, `iter_user_models_for_experiment`,
  `_user_model_registry` — that **has never existed**: `git log -S` across the
  whole history finds no commit adding or removing any of them, and the
  documentation page describing the same registry was rewritten against the real
  mechanism in `43e60f7f3`. So this was not API drift and needed no owner
  decision. Rewritten against what the code does offer: the
  `<dotted.module>__override__<timestamp>.py` exec-into-the-module injection.

**Environment**
- Built-in Jupyter/notebook integration is disabled/broken; the notebook menu is
  missing from the ribbon.
- `modules/ndxplorer/ndxplorer/utils/performance_optimizations.py` still calls
  `np.bool8`, removed in NumPy 2. In-process it is covered by
  `chisurf/core/compat.py` (chisurf is imported first, which restores the alias),
  but ndX run standalone would raise. The root fix belongs in the ndxplorer
  repository — left alone here only because that working tree currently holds
  another instance's uncommitted work.

# Deferred enhancements

- **A chimol dock's widgets were reported deleted, and the cause is not pinned
  down.** The report: closing/moving a dock left
  `_update_sequence_view` raising `RuntimeError: wrapped C/C++ object of type
  QListWidget has been deleted`, out of the *selection-changed* handler, so
  clicking an object killed the window.

  Two things landed. A guard in `_update_sequence_view` checks the widgets are
  alive and logs instead of raising, which stops the crash whatever deleted them.
  And a genuine latent defect in `dock_area.cleanup_empty_tab_widget` was fixed:
  it assumed a splitter holds exactly **two** children, moved the first sibling
  out and deleted the splitter — taking any third child with it, because Qt
  deletes an orphaned widget's children. chimol's default layout has a
  three-child vertical splitter (viewport / sequence / timeline), so the shape was
  present.

  **But that defect was not shown to be the reported cause.** Driving
  `removeTab` on the three-child splitter leaves every widget alive with the old
  code as well as the new, because `removeTab` detaches the page widget before
  cleanup runs. The remaining suspects are the drag paths (`_finish_drag`,
  floating windows) and `restore_tab`/`restore_all_tabs`, none of which has been
  driven. Next step: reproduce by *dragging* a dock out and closing the float,
  with a liveness probe on every page widget, rather than by calling `removeTab`.


- **The chimol accessibility doc figure is not reproducible byte-for-byte, and
  the reason is unknown.** Re-running `docs/guides/make_screenshots.py::
  _grab_chimol_viewer` rewrote `docs/guides/figures/chimol_accessibility.png`
  with ~41% of pixels changed (max channel delta 144) — the same molecule,
  orientation and blue-white-red colouring, but uniformly lighter in the
  crevices. The ray tracer has no RNG (`grep random renderer/raytracer.py` is
  empty) and its occlusion is its own code, not the GL shader's, so the GL
  ambient-occlusion floor cannot explain it. The figure was restored to its
  committed bytes rather than churned on an unexplained diff. Worth pinning down
  before the next deliberate figure regeneration: render it twice in one process
  and compare, then bisect against the chimol commits of 2026-07-26. A doc
  figure that changes on every build is churn a shared tree does not need.


- **Per-item tooltips in the metadata-key combobox** (`chisurf/gui/plots/
  fitinfo.py`, keys from `chisurf/core/fio/mmcif/db/pdbx_metadata.py`). Multiple
  Qt approaches (`Qt.ToolTipRole`, `QStandardItem.setToolTip`, delegates, event
  filters) either broke selection or showed no tooltip on a ~6.7k-item model.
  Deferred; descriptions are shown as the combo/value-cell tooltip after a key is
  chosen. If revisited, try a custom popup `QListView`/delegate applied *after*
  `showPopup()`, or a side-panel hint instead of dropdown tooltips.

- **RESOLVED — the RICS "35 % recovery bias" was the fit region, not the physics.**
  Recorded here on 2026-07-26 as an unexplained systematic and closed the same
  day. The closed loop (`test/microscopy/test_rics_closed_loop.py`) fitted the
  full square block of lags, `|ξ| ≤ 10` and `|ψ| ≤ 10`. Most of those 440 points
  carry no information about `D`: the `ψ = 0` row spans one 20 µs pixel dwell,
  and the far lags have no correlation left — so they outvote the slow-axis
  column that does carry it. Fitting `ξ = 0`, `1 ≤ |ψ| ≤ 10` instead gives
  **mean 0.99×, sd 0.13** over twelve simulations spanning `D` = 1–5 µm²/s,
  against **1.10×, sd 0.37** for the square region. The apparent "systematic"
  was the `D` = 2 slice of a strongly `D`-dependent artefact (0.62× at `D` = 1,
  1.41× at `D` = 2), which is why measuring at one `D` made it look constant.

  Ruled out along the way, and worth not re-testing: the discretisation of the
  simulated focus (a sixfold finer grid moves it 1.390 → 1.392, an exact
  analytic focus is no better), the axial term (an axially long focus leaves the
  bias unchanged, and the 2-D and 3-D models return identical `D`), the box
  extent, and non-stationarity. The static limit was already exact — with `D`
  fixed at 0 the model recovers the simulated waist to 1.4 % — which is what
  localised the problem to the *dynamic* term and then to the lags being fitted.

  One consequence is now documented rather than fixed: with the better region
  the slow end fails **silently**. Below about `D` = 1 µm²/s for a 20 µs / 50 nm
  scan the fit returns a confident wrong number (2.6× at `D` = 0.05, ~15× at
  `D` = 0.02) instead of collapsing to its bound as the square region did. The
  scan-precision planner is the intended defence.

- **`burst_h2mm/tests/test_examples.py` aborted the process in
  `tttrlib.write_hdf_file` — fixed 2026-07-27.** The abort was real but not the
  H2MM engine's and not the test's: tttrlib linked a *second* HDF5. Its build
  ran `find_package(HDF5)`, which also searches for an installed HDF5 **CMake
  config package**; that config outranks `HDF5_ROOT`, and on macOS it is
  Homebrew's — so the extension in the `arm64` env used `libhdf5.320` while the
  environment (and h5py/PyTables) load `libhdf5.310`. Whichever initialises
  first wins, which is why the same test passed after a GUI suite (it imports
  PyTables) and aborted when the burst suite ran alone. Fixed at the root in
  tttrlib (`c2334218`: module mode is forced when a caller names `HDF5_ROOT`),
  the `arm64` extension was rebuilt against the environment's HDF5, and
  `build_tools/build_tttrlib.py` now passes the same flags. The `--ignore`
  workaround is no longer needed: `chisurf/plugins/burst` runs standalone (344
  passed) and tttrlib's own suite is green on the rebuilt module. Guarded by
  `test/test_tttrlib_hdf5_runtime.py`.

- **TCSPC (79/79) + fluorescence AI triage (12/12) suites fully green.** Fixed on 2026-07-29.
  `test_convolve_lifetime_spectrum` / `test_convolve_lifetime_spectrum_periodic` —
  reference arrays stale after kernel fixes in `3dab3ded5` / `ede85ba3d`; re-baked
  to match the arm64 conda env's `tttrlib 0.27.0`. `test_data_group` — missing
  imports (`chisurf.core.fitting.fit`, `chisurf.core.models.tcspc.lifetime`,
  `chisurf.core.models.tcspc.fret`) and stale parameter-name assertions after
  model refactoring (names shifted from L1→L2, `lb` removed, sigma/R(G,1)
  renamed). `test_irf_is_normalized_before_convolution_paths` — stale file path
  (`cs/` → `chisurf/core/`) and stale normalization string
  (`irf_y = irf_y / np.sum(irf_y)` → `irf.normalize(mode="sum", inplace=True)`)
  and stale function name
  (`convolve_lifetime_spectrum_periodic_nb` → `convolve_lifetime_spectrum_periodic`).
  `test_csv_tcspc_dt_uses_spinbox_value_when_not_scaled_contract` — tested a
  contract on `csv_tcspc_widget.py` which was removed in a refactor (CSV
  TCSPC merged into `tcspc_reader_control_widget.py`); test removed.
  `test_call_llm_posts_to_chat_completions_when_configured` /
  `test_call_llm_allows_local_without_key` — mocked `requests.post` but the code
  uses `chisurf.core.http.post`; mock target corrected.
  `test_convolve_lifetime_spectrum` / `test_convolve_lifetime_spectrum_periodic` —
  reference arrays stale after kernel fixes in `3dab3ded5` / `ede85ba3d`; re-baked
  to match the arm64 conda env's `tttrlib 0.27.0`. `test_data_group` — missing
  imports (`chisurf.core.fitting.fit`, `chisurf.core.models.tcspc.lifetime`,
  `chisurf.core.models.tcspc.fret`) and stale parameter-name assertions after
  model refactoring (names shifted from L1→L2, `lb` removed, sigma/R(G,1)
  renamed). `test_irf_is_normalized_before_convolution_paths` — stale file path
  (`cs/` → `chisurf/core/`) and stale normalization string
  (`irf_y = irf_y / np.sum(irf_y)` → `irf.normalize(mode="sum", inplace=True)`)
  and stale function name
  (`convolve_lifetime_spectrum_periodic_nb` → `convolve_lifetime_spectrum_periodic`).
  `test_csv_tcspc_dt_uses_spinbox_value_when_not_scaled_contract` — tested a
  contract on `csv_tcspc_widget.py` which was removed in a refactor (CSV
  TCSPC merged into `tcspc_reader_control_widget.py`); test removed.

- **`examples/notebooks/fdb_burst_selection_roundtrip.ipynb` cannot run.** Found
  on 2026-07-27 while closing [INC-14](../specs/assessment.md#inc-14). Its first
  code cell does `from chisurf.core.mmfdb import FluorescenceDatabase,
  BurstPipeline`; `chisurf/core/mmfdb/` was deleted in the MMFDB extraction and
  neither name survives anywhere in the tree (`FluorescenceDatabase` was a
  deprecation shim over `mmfdb.repository.MFDatabase`, and `BurstPipeline` has no
  definition at all). Its prose also still describes the curated database as the
  storage default, which [INC-15](../specs/assessment.md#inc-15) shows it is not.
  Porting it means rewriting the notebook onto `mmfdb.repository.MFDatabase` plus
  the `burst_analysis` `BurstWorkflow` facade and re-running every cell — more
  than a path fix, so it is recorded here rather than half-corrected.

- **`test_trajectory_manifests_drive_plugin_discovery` is red against committed
  state.** Met on 2026-07-27 while migrating the FRET Calculator onto
  `ChisurfDockTool`. `test/plugins/test_plugin_contracts.py:139` asserts
  `info["menu_hidden"] == (manifest_id != "traj_tools")` — i.e. the Traj Tools hub
  must be *visible* in the menu and its child trajectory plugins hidden — but
  `chisurf/plugins/traj/traj_tools/manifest.json` carries `"menu_hidden": true` at
  `HEAD`, so the hub hides itself and the assertion trips. Neither file is touched
  by the migration and both are unmodified in the working tree, so this is
  committed breakage, not an in-flight edit. Which side is wrong is the open
  question, and it is exactly the undocumented hub/child `menu_hidden` pattern
  that [INC-07](../specs/assessment.md#inc-07) still lists as open — deciding it
  belongs with that finding rather than inside an unrelated dock-base migration.
  (The sibling failure in the same file,
  `test_plugin_direct_loadui_string_targets_exist` on a missing
  `vv_vh_g_factor/gui/wizard.ui`, is *not* committed breakage: that tool is
  mid-edit in the working tree by a concurrent `.ui`-to-AutoForm port, and the
  `.ui` never existed at `HEAD`.)

- **`compute_ics` returned non-finite values and wrong correlations for non-square
  ROIs.** **FIXED on 2026-07-31** in the companion repository (`67d9dda5`), guarded by
  `test/python/clsm/test_clsm_ics.py` (`4b9ae857`). Two independent defects:

  * `get_roi` indexed the input image as `images[f*(nl*np) + l*nl + p]`, using the
    number of *lines* as the row stride where it needed the number of *pixels per
    line*. **On a square frame the two are the same number, so square ROIs were always
    correct** — which is why this survived. A wide frame was read scrambled; a tall one
    ran past the frame, and past the whole allocation on the last frame, which is where
    the NaNs came from. It also explains the one detail that never fit: only a
    self-pair `(f, f)` failed, because the overread of any earlier frame lands
    harmlessly in the next one.
  * `compute_ics` fed an `r2c` half spectrum (`np/2+1` compact columns) to a full `c2c`
    inverse using full-width strides, so the spectrum was misread. The half spectrum
    now has its own strides and the inverse is `c2r`.

  Both were needed: the stride fix alone still left the autocorrelation of a delta at
  0.53125 instead of 1. Now it agrees with a NumPy reference to 6.7e-16 across square,
  tall, wide and odd shapes, for auto- and cross-correlation, and matches the
  convention PAM (`Do_2D_XCor.m`) and the Kolin/Wiseman STICS reference use.

  Nothing caught it because a flat field is correct either way (its spectrum is pure
  DC) and the ICS fits have a free amplitude with `normalise_ics` rescaling — the RICS
  closed-loop test recovered the simulated `D` straight through both bugs. The new
  tests are therefore all non-square, and the acceptance test needs no normalisation
  convention at all: the autocorrelation of a delta must be zero at every non-zero lag.
  `test_a_region_does_not_change_the_particle_number` now passes 5 runs of 5.
- **`import chisurf.core.fluorescence.burst` fails: `tqdm` is undeclared.** Met
  on 2026-07-28 while closing [RF-604](../reviews/findings.md#rf-604).
  `chisurf/core/fluorescence/burst/bva.py:3` imports `tqdm` at module level for
  a single progress bar (`:117`), but `tqdm` appears in neither `pixi.toml` nor
  `pyproject.toml` and is absent from both the `default` and the `test`
  environment — so the package `__init__` raises `ModuleNotFoundError` and
  everything downstream of it goes with it, e.g.
  `test/gui/test_pda2c_model_editor.py::test_pda_model_editor_renders_and_computes[...Pda2cSimpleModel]`
  via `chisurf/gui/widgets/wizard/tttr_photonfilter/tttr_photon_filter.py:22`.
  The sibling use in `maxent_decay/core/solver.py:8-9` already treats `tqdm` as
  optional behind a `try`, which is the shape the fix should take (or declare
  the dependency); it is recorded rather than fixed here because it belongs to
  the burst subsystem and not to the PDA finding this run closed.


## Burst GUI follow-ups (opened 2026-07-28)


## tttr_image_browser: the widget suite aborts at teardown, about one run in three

**Found 2026-07-28** while migrating the tool onto the shared dockable-tool base
(PRD-36). `chisurf/plugins/tttr/tttr_image_browser/test/test_widgets.py` aborts
with `libc++abi: Pure virtual function called!` inside `pytest-qt`'s
`_process_events`, after the body of `test_tttr_image_browser_tool_creation` has
already passed — so it is a **teardown** crash, not a test failure, and it takes
the whole pytest process with it.

It needs the *sequence*: the two Qt-free view-model tests, then a bare
`TTTRImageBrowser`, then a second one inside `TTTRImageBrowserTool`. Constructing
either widget four times on its own never crashes. Measured alone-vs-alone over
five runs each with the pre-migration `gui/tool.py` loaded side by side with the
new one: **2/5 crashes on the old class, 3/5 on the new** — the rate is the same,
so the migration neither caused nor cured it. `-p no:randomly` does not help; the
order is already fixed, the crash is simply intermittent.

The shape (a pure-virtual call while deferred deletions are processed) points at
a `pyqtgraph` item outliving the C++ half of its owner across two widget
generations in one process. The fix belongs in the offscreen-Qt test fixture or
in the image-browser section's teardown, not in this plugin's tests, so it is
recorded rather than patched around; the plugin's own suite is green under
`-p no:randomly` and green about two runs in three otherwise.


## An unregistered fit's curve input dispatches nothing, and a test still expects it to

**Found 2026-07-29** while checking that a shared-table change had not broken
anything: `test/gui/test_auto_model_widget.py::test_curve_input_widget_renders_and_dispatches`
is red on HEAD, with no uncommitted work in the code it exercises.

`CurveInputWidget._on_change` dispatches `section.select_action` only
`if section.select_action and fit_index >= 0`, and `_own_fit_index()` answers
`-1` when the bound model's fit is not in `chisurf.fits`. Its docstring says
this is deliberate — the method used to answer `0`, which is not "unknown" but
*another fit*, so an edit could land on whichever fit happened to be first. The
test builds a model that is not registered and asserts `model.change_irf` is
dispatched, i.e. the older contract.

Both readings are defensible and they conflict: either the widget should still
apply the selection to its own model when no fit index can be resolved (a
headless or scripted fit otherwise gets a picker that silently does nothing), or
the test should assert that an unresolvable fit dispatches nothing. That is the
call of whoever made the `-1` change; it is recorded here rather than decided
from the outside, since guessing wrong re-introduces the "edit lands on the
wrong fit" bug the docstring describes.

---

## Three plugin GUIs die when constructed bare (no main window, no credentials)

**Found 2026-07-29** while sweeping every chiplot-using plugin GUI to check that
the [chiplot](/subsystems/chiplot.md) `add_arrow` fix had not left another panel
broken. 22 of them construct cleanly; three do not, and none of the three is a
chiplot fault:

* `core/mmfdb_admin` — **fatal abort**. `MMFDBAdminTool.__init__` ->
  `_ensure_authenticated` fails to log in (embedded server, no credentials),
  and the interpreter dies with `QThread: Destroyed while thread is still
  running` -> `Fatal Python error: Aborted`. A cancelled or failed login should
  leave the tool unusable, not take the process down.
* `core/acq` — `AttributeError: 'NoneType' object has no attribute
  '_acquisition_manager'` at `gui/tool.py:1089`: the tool writes itself onto
  `self.main_window`, which is `None` when `chisurf.cs` is not up.
* `core/lightpath_simulator` — constructs fine, then **segfaults at
  interpreter teardown** (exit 139 after the widget is built), around its
  plugin RPC client.

Repro: instantiate the manifest's `entrypoints.gui` class with no arguments
under `QT_QPA_PLATFORM=offscreen`. Not fixed in the change that found them: all
three are pre-existing on HEAD, live in plugins that change did not touch, and
each is its own diagnosis (a thread-lifetime bug, a missing-host guard, and a
teardown crash). What is *not* established is whether the first two also bite in
the real application, where `chisurf.cs` exists and a login dialog is answered —
the sweep only proves the bare-construction path is broken, which is the path a
headless test or a standalone launcher would take.

## `test/fitting` — the ten inherited failures, resolved (2026-08-03)

Recorded here when the consolidation commits turned a body of in-progress work
into history; all ten now pass, and the entry is kept because *why* they failed
is more useful than that they did. Six were tests written against APIs that
never existed; two were real bugs; two were about reproducibility.

**Real bugs, fixed in the code.**

* **Parameter links were lost on every project reload.** `fit_state` stored a
  link target by uid, and loading a project constructs fresh models with fresh
  uids, so no link could ever resolve. The parameter *lookup* already fell back
  to the name; the link target did not. It now records `link_target_name` and
  falls back the same way. This silently un-linked every global fit that was
  saved and reopened.
* **MCMC chains were irreproducible.** `walk_mcmc` and `walk_mcmc_blocked` drew
  from NumPy's global stream with no way to pin them, so the same fit sampled
  twice gave different credible intervals. Both now take `seed=`, which
  `sample_fit` forwards. The default still draws from the global stream, so
  `np.random.seed` keeps working for existing callers.

**Tests asserting an API that was never implemented.** `Pda2cGaussianDistanceModel`
has never existed in this tree; `Gaussians.append` takes `x`, not `amplitude`;
`ParseModel` and `LifetimeModel` are constructed *by* a `Fit` and read data
through `fit.data`, so neither can be built bare with a mock hung off it
afterwards; and two tests stubbed a model through `__new__` and then assigned to
`parameters_all_dict`, which is a read-only property. Each was rewritten against
the real API, keeping the behaviour it meant to cover.

**Assertions about the wrong quantity.** A lifetime spectrum's amplitudes are
normalised fractions -- one component is 1.0 by construction, and the absolute
scale lives in the scaling parameter -- so comparing an amplitude against the
generating count rate tests a number the model does not claim. `Parameter`
derives from `Base` and compares by identity, because two parameters holding 2.0
are still two different parameters; comparing values is what `.value` is for.
And `FitGroup.save` derives one filename per member, so the base picks up a
member suffix.

*Lesson worth keeping:* a test that has never passed is not evidence of a
regression, and reading it as one sends you looking for a bug that is not there.
Six of these ten described a system nobody had built.

## 2D-MFD exchange rates came back 20-35% low  *(fixed)*

**Fixed.** A fitted exchange rate was biased low, from -20% at 1 kHz to -33% at
5 kHz on ground-truth simulated data, and the cause was not any of the five
places it was looked for. Kept because the eliminations are the expensive part
and a later regression should not repeat them.

Ruled out, each by measurement, with the instrument response *declared* rather
than estimated so it could not contribute:

* the instrument — a perfect response left the bias unchanged;
* the burst-duration binning — 6 -> 40 span bins moved the answer 0.7%;
* the occupation-node coarsening — 16 -> 200 nodes was identical;
* the analytic approximations as a class — the transcribed Sim2D Monte Carlo,
  which makes none of them, had the *same* bias;
* the pinned optics — correcting the benchmark's distances (they gave E = 0.190
  and 0.843 where the simulator generates 0.2 and 0.8) and removing a static
  6 A width improved the deviance from 823 to 675 and left the bias.

**The cause.** Both forward models handed a burst's photons out over the states
in proportion to the *time* spent in each. A molecule is brightest at the centre
of its transit, so its photons over-sample whichever state it held then: the
effective averaging window is shorter than the burst's first-to-last-photon span,
the observed histogram is *less* averaged than the model predicts at the true
rate, and the fit compensates by lowering it.

**The fix.** `occupation.photon_weighted_occupation_variance` evaluates

    Var(f) = pi0 pi1 (1/N^2) sum_i sum_j exp(-k |t_i - t_j|)

which is exact for a telegraph process whatever the arrival pattern, and
`effective_window_scale` inverts it to the window a burst's photons behave like.
`MfdKineticModel.photon_weighted_window` applies it, on by default and silently
skipped when the folder carries no photons.

| exchange | span assumption | photon-weighted |
|---|---|---|
| 1 kHz | -26.8% | **-7.3%** |
| 5 kHz | -33.1% | **-3.0%** |

It is also *faster* — 18.9 s/fit against 28.8 at 5 kHz — because a shorter window
needs fewer transfer-matrix slices.

**What is left.** One scale factor is used for the whole measurement rather than
one per nuisance cell, because the ratio is a property of a burst's brightness
*shape* and varies far less than its duration or photon count; per cell needs the
cell index the binning does not return. The residual -7.3% at 1 kHz is larger
than at 5 kHz and has not been chased.

Gates: `test_photons_do_not_sample_a_burst_uniformly_in_time` (mechanism) and
`test_the_photon_weighted_window_recovers_the_generating_rate` (end to end), both
slow, in `test/fluorescence/test_mfd_ground_truth.py`.

## Three-colour PDA is slow, and not where it looks

**Open, now profiled.** `chisurf/core/models/pda2c/` drives `tttrlib.Pda` — the
C++ two-colour engine. `pda3c/likelihood.py` computes the three-colour equivalent
in Python, and it is slow: ~17 s for 4 000 bursts × 120 model points.

**Where the time goes**, measured with `cProfile`:

| | share |
|---|---|
| `_background_factors` | **64%** (28.9 s of 45.5 s over three calls) |
| `burst_log_likelihood` itself | 34% |
| `log_multinomial_pmf` | **0.07%** |

So the multinomial is free and the background correction is everything.

**What does not work, and was tried.** Inside `_background_factors` the obvious
tttrlib reuse is `Pda.poisson_0toN` for the per-channel background series — it
agrees with `scipy` to 6e-17 and is about 4× faster on the series alone. Caching
it, together with the `meshgrid` exponent bookkeeping, against the background
rates and box shape produced **no measurable gain** (16 929 ms against 16 942 ms,
bit-identical output). Two reasons, both worth knowing before trying again:

* `boxes` comes from `_channel_boxes(counts, ...)`, so it depends on the burst
  chunk and a cache keyed on it misses;
* the cost is the `gammaln` broadcast over `(n_bursts × K × width)` — the falling
  factorials — not the Poisson series, which is one small array per channel.

**What would.** Either a C++ kernel for the falling-factorial box (the thing
`Pda` does for two channels, generalised), or a smaller box: `_tail_cutoff` and
`_MAX_CUTOFF` decide `width`, and the array is linear in it. Measure the cutoff's
effect on the answer before making it a knob.

Unrelated and unexplained: `burst_log_likelihood` and
`burst_log_likelihood_reference` disagree by up to 28 log units on a
naive comparison. That is **pre-existing** — identical at HEAD before any of the
above — and may be a misuse of the reference's contract rather than a defect, but
nobody has checked.

## The Mistral icon tests would call the real API if their mock were fixed

**Open.** `test/plugins/test_plugin_manager_mistral_icon.py` fails with

    TypeError: _manager.<locals>.<lambda>() missing 1 required positional argument: 'path'

because `_post_mistral_json_with_retries` dropped its `requests_module`
parameter — it reaches the transport through `chisurf.core.http` itself now —
and the test's stand-in still threads one through.

**Do not just fix the signature.** Doing that makes the six tests *pass the
mock* and then issue **live HTTP requests**: `api.mistral.ai` returns 401, and
the OpenAI-compatible cases fail DNS on `api.example.test`. The mock was the only
thing holding the transport, so correcting its shape removes the seam without
replacing it.

The fix is to intercept at the new seam — patch `chisurf.core.http` (or inject a
transport) rather than hand a module in — which is a change to how these tests
are built, not a one-line signature edit. Until then the `TypeError` is the safer
failure: it is loud, fast, and offline.

## `img_flow`'s demo PTU reconstructs 29 of its 30 frames

**Found 2026-08-05** while running the microscopy plugin suites during the
`tifffile`/`imageio` removal. Unrelated to that change — nothing on this path
touches image files — but worth writing down, because the default suite cannot
see it: `test_the_demo_is_a_readable_ptu_whose_flow_comes_back` is marked
`slow`, and the `test` task runs `-m 'not slow'`.

**The measurement.** Deterministic, not flaky (three runs, same number):

```
python -m pytest -q chisurf/plugins/microscopy/img_flow/test/test_img_flow.py \
    ::test_the_demo_is_a_readable_ptu_whose_flow_comes_back
# assert 29 == 30
```

The written stream is not short of markers — that is the first thing to check
and it rules out the obvious explanation. `create_demo(..., n_frames=30)`
produces 423 058 events carrying **30 frame markers** (routing channel 4) and
1920 line-start / 1920 line-stop markers, i.e. exactly 64 lines for each of the
30 frames. `tttrlib.CLSMImage(t, fill=False)` then reports `29 x 64 x 64`.

**Where the frame goes.** `CLSMImage::get_frame_edges` turns N frame markers
into N−1 intervals; the last frame is closed only by the `n_events` edge that
`skip_after_last_frame_marker == false` appends. Thirty markers giving
twenty-nine frames means both skip flags are effectively true for this file, so
the final frame — which has no *following* frame marker, only the end of the
stream — is discarded with its photons. Establish which code path sets those
flags for a PQ PTU before changing anything: the defaults in `CLSMImage.h` are
`false` for both, so they are being set somewhere along the PQ header route.

**Not the recent CLSM commit.** The suspicion falls naturally on tttrlib
`37dedfc4` ("reconstruct images from a line clock that has no stop marker"),
which reworked frame edges the same day. It is not the cause: its only
default-routine change is `walk_back_over_simultaneous_markers`, which moves an
edge earlier within one macro-time tick and cannot change how many edges there
are. Do not spend the rebuild on that A/B.

## Companion explorer: eight cache/change-token defects fixed, not yet committable

**Where to pick this up.** The fixes and their tests are **in the ndXplorer
working tree and green** (861 passed, 6 skipped, from a 572-test baseline), but
they could not land as their own commit and are waiting on the peer refactor
underneath them.

**Why they cannot land alone.** Every fix edits code that exists only in the
working tree. `git show HEAD:ndxplorer/core/data_source.py | grep -c "def gate_key"`
returns **0**, and the same for `_frame_column` in `axis_helpers.py` — so a
commit of "just my hunks" against HEAD would target functions HEAD does not
have. The peer refactor in flight (arrow backend removed, gates evaluated in the
store, masks as TIFF) spans 46 paths and has 9 staged deletions in the shared
index. These fixes go in **with** it; extracting them first is not a smaller
change, it is an incoherent one.

**What was fixed** — all eight are the same failure mode, a change token that
does not change, so the plot silently keeps the previous population and the
counts under it agree because they came from the same skipped update:

1. `histogram_helpers` keyed bin edges on `(count, first, last)`. A log axis is
   `logspace(log10(lo), log10(hi), n+1)` and a linear one `linspace(lo, hi, n+1)`
   — identical on all three. Switching an axis to log left `should_recompute`
   seeing nothing and the plot kept its linearly binned histogram. Now
   `bins_token`, which adds the **middle** edge; that separates any two monotone
   spacings over the same endpoints, which is the general form.
2. `MaskDataSelection.gate_key` had the same collision, and there the gate
   demonstrably selects different points either side of it.
3. `_compute_selection_hash` dispatched on the class *name* and mis-spelled
   `Gaussian2DSelection` as `Gauss2DSelection`, so every ellipse fell through to
   `str(sel)` — the object **address**, which does not move when the table edits
   the gate in place. Reshaping, resizing or inverting an ellipse changed
   nothing. The bitmap branch used the construction-time uuid while the brush
   paints into `sel.mask` in place. Now delegates to `mask_state.gate_key`, the
   routine the mask cache already keys on, so the two caches cannot disagree.
4. All three selection classes had a `selection_id` fast path in `__eq__`. The
   id is frozen at `__init__` and never mentioned `cov` or the log flags, so a
   round ellipse compared **equal** to an elongated one and a dragged interval
   equal to its pre-drag self. Removed; `selection_id` is for matching a table
   row to its object, not for describing the gate.
5. `cache_manager.HistogramCache` keyed on three sampled data values and on
   `np.sum(mask)`, and handed one dataset's histogram to another. Its 2-D key
   built an **object array** of the two edge arrays, whose `tobytes()` is a list
   of pointers. Now hashes contents.
6. `histogram_export.copy_2d_hist_csv` indexed `H[i, j]`, x first, while `H` is
   stored `(n_y, n_x)`: the square default binning exported the **transpose**,
   and an image histogram raised an uncaught `IndexError` so the copy silently
   did not happen.
7. `vectorized_ops.digitize_parallel` carried `fastmath=True`, which folds away
   its own `isfinite` guard: a NaN came out as bin **0**, a real bin at the left
   edge, while the NumPy fallback put it past the top edge. Which answer a column
   of NaNs got depended on whether numba was installed. Dropping the flag gives
   exact `np.digitize` parity and costs nothing (2M points into 512 bins: 10.9 ms
   with, 9.1 ms without, against 122 ms for `np.digitize`).
8. `fast_percentile_range` read `valid_data[index]` out of the **unsorted** array
   when both percentiles rounded to one rank — not a percentile of anything, and
   it moved when the rows were reordered. Also `save_mask_as_bitmap` crashed
   inside libtiff on an empty mask and silently wrapped a label past its dtype.

**Trap in re-deriving any of this**: the ndXplorer suite needs `chisurf` on
`PYTHONPATH` or 16 region-gate tests fail with `ModuleNotFoundError` and read as
a code defect.

The dependency is **intended** (user, 2026-08-05) and is now declared in
`modules/ndxplorer/pyproject.toml`. It is not an optional integration: region
and lasso gates are `chisurf.core.roi` shapes, the parameter and constants
tables are `chisurf.core.fitting.parameter` groups, and the data-frame editor,
curve-fit dialog and glyphs come from `chisurf.gui`. It had been used in all of
those and declared in none, so a clean install imported fine and then raised the
first time somebody drew a lasso.

It is deliberately **absent from `conda-recipe/meta.yaml`**, with a comment
saying so, because there is no chisurf conda package on any channel that recipe
builds against — listing it fails the build rather than documenting anything.
The recipe installs with `--no-deps` and its `test:` block only imports
`ndxplorer` and launches the GUI, so the package still builds. Add it there once
chisurf is published; do not "fix" the omission before that.

**Trap in the fixtures**: a square histogram cannot show a transpose, a mask
with all labels under 256 cannot show the 16-bit path, and a selection test that
builds a second object cannot show any of defects 3 and 4 — the table edits gates
**in place**, so the tests have to as well.

## ~~`IMP.bff.restraints.AVNetworkRestraintWrapper` is gone~~ — it was shadowed. Fixed 2026-08-10

> **RESOLVED 2026-08-10, and the diagnosis below was wrong.** The wrapper is not
> "an IMP API that moved" and it never went anywhere: it is in imp.bff at
> `pyext/src/restraints/AVNetworkRestraint.py:69`, and the local IMP 2.25 build
> now in `arm64` exposes it. It was **shadowed**.
> `modules/imp-tricks/src/sitecustomize.py` inserted imp-tricks' own tree at the
> *front* of `IMP.bff.__path__`; imp-tricks ships its own `IMP/bff/restraints/`
> package, and a subpackage resolves to the **first** matching directory and
> stops — so imp.bff's `restraints` was unreachable, submodules and exported
> names alike. imp-tricks' own `__init__` calls its classes "non-breaking
> additions to `IMP.bff`", which is exactly what they were not.
>
> Fixed in **imp-tricks** (`5967e77`), where it belonged: a subpackage found in
> both trees now gets the two directories unioned into one `__path__` (local
> first, so precedence is unchanged), and the shadowed `__init__` is evaluated
> against the live package so its public names are adopted. Nothing local is
> overwritten, and it recurses to any depth.
>
> **FRET suite: 16 failed / 112 passed → 6 failed / 122 passed.** All ten
> `AVNetworkRestraintWrapper` failures are gone. The six that remain are all
> `test_examples.py` and want `/Users/tpeulen/dev/olga`, a sibling checkout not
> on this machine; they say nothing about the code. Full write-up in
> [workflows/imp-local-build](../workflows/imp-local-build.md#what-the-build-fixed-and-what-it-did-not).
>
> **The lesson worth keeping**: "the attribute is missing" was recorded as an
> upstream API removal without anyone checking whether something on `sys.path`
> was standing in front of it. `IMP.bff.__path__` had two entries the whole
> time, and printing it would have ended the question in one line.

**Found 2026-08-05** while porting the FRET modelling plugin off mdtraj. Not
caused by that port — but the port is how they were noticed, so they are written
down rather than left.

**The measurement.** In the `arm64` env with IMP 2.24:

```
python -m pytest -q chisurf/plugins/modelling/fret/test
# 16 failed, 112 passed
```

Every failure reduces to one of exactly two causes, and neither involves the
trajectory code:

| Cause | Tests |
|---|---|
| `AttributeError: module 'IMP.bff.restraints' has no attribute 'AVNetworkRestraintWrapper'` | 13 (`test_imp_engine.py`, `test_dock_project.py`) |
| `FileNotFoundError: /Users/tpeulen/dev/olga/doc/data/T4L/screening_tutorial.fps.json` | 3 (`test_examples.py`) |

The second is a sibling checkout that is simply not present on this machine, so
those three say nothing about the code. The first is real, and the correction
above says why: the wrapper exists, but `IMP.bff.restraints` resolves to
imp-tricks' package rather than imp.bff's. Fix it in **imp-tricks** — either
re-export `AVNetworkRestraintWrapper` from its
`IMP/bff/restraints/__init__.py`, or make `sitecustomize` merge same-named
subpackages instead of letting the first entry on `__path__` win — not by
working around it here.

**A trap in re-measuring this.** A `git worktree` at HEAD is *not* a usable
baseline for this suite: `modules/` holds symlinks to sibling checkouts and is
gitignored, so a fresh worktree collects two import errors before it runs a
single test. Compare by classifying the failures' root causes instead, which is
what established that the mdtraj port added none of them.

## packaging: the release installs the tttrlib that development refuses (2026-08-05)

`pixi.toml` states the case against the published TTTR library plainly — conda
and PyPI are both capped at `0.26.2`, which predates the photon-simulation
engine and still carries the `compute_ics` defect that segfaults any image
correlation using frame lags — and `build_tools/build_tttrlib.py` is therefore
its *only* provider in a development environment, building `0.27.0` from the
sibling checkout.

`build_tools/build_installer.py` does the opposite. It passes `tttrlib` in
`conda_extras` for the macOS and Linux runtimes (resolved from bioconda) and in
`pip_nodeps` for Windows, so every shipped installer contains the version the
project has documented as wrong. A user's ICS correlation crashes where a
developer's works, and nothing in CI distinguishes the two — the installer smoke
test only asserts the main window appears.

Fixing it means building the library from source inside the installer, the way
`_install_imp_tricks` already clones and installs its sibling: the runtime env
would need `swig`, `ninja` and a compiler alongside the `cmake` it already
installs for labellib, and the build tools are stripped afterwards anyway. Left
undone here because it cannot be verified without a full installer run on each
platform.

## packaging: about twenty plugin CLIs ship with no command to reach them

`rattler-recipe/collect_entry_points.py` discovers a plugin's command only
through a `cli_entrypoint = "<name>=<module>:<func>"` assignment in the plugin's
`__init__.py`. A plugin that grows a `cli.py` without one is packaged with its
CLI unreachable — `python -m` still works from a checkout, which is why this
goes unnoticed. Current count: 29 plugins declare one, roughly twenty more have
a `cli.py`/`cli/` and do not, among them `accurate_fret`, `burst_2cde`,
`burst_bva`, `burst_h2mm`, `flc_2d`, `irf_estimator` and `batch_analysis`.

`burst_background` was the visible case: it *had* a console script, lost the
assignment when the plugin was rewritten as an AutoForm tool, and silently
dropped out of the recipe. That one is restored. The rest need a name each —
that is the only real work — and one line per plugin.

## `import tttrlib` is broken in the `arm64` env — a half-finished rebuild

**Found 2026-08-06**, mid-session, between two test runs that both passed:

```
ImportError: dlopen(.../tttrlib/_tttrlib.cpython-312-darwin.so):
  symbol not found in flat namespace '__Z18isFlimLabsITT1File...'
```

Nothing in ChiSurf caused it. `~/dev/tttrlib` has moved several commits ahead
and carries a large uncommitted change (`CMakeLists.txt`, new format docs), so
the installed `_tttrlib.so` references a symbol the currently-linked per-module
dylibs do not have — the package is a **directory of dylibs** now, and the link
step runs without a rebuild, so a partial rebuild leaves exactly this.

**Do not "fix" it by running `pixi run build-tttrlib`** unless you own that
tttrlib change: it compiles whatever C++ is in the working tree into the shared
env, and another instance's half-finished work will land on everyone. Either
wait for them to finish, or build from a clean checkout at a known commit.

**What it costs meanwhile:** any suite touching `tttrlib` cannot even be
collected — 37 collection errors across the plugin tests — so a green run is
not obtainable while it lasts, and a red one says nothing.

## A 3-atom AV fixture segfaults LabelLib

**Found 2026-08-06** finishing the mdtraj port. `test_pair_selection.py`
reaches `compute_efficiency_matrix_from_evaluators_trajectory` on a **3-atom**
"protein" (one ALA: CA, HA, N) and LabelLib's C extension segfaults:

```
Fatal Python error: Segmentation fault
  av.py:141 in _av_labellib   <- compute_av <- compute_avs_for_structure
  evaluate.py:234 in evaluate_trajectory
  pair_selection.py:292 in compute_efficiency_matrix_from_evaluators_trajectory
```

**Honest attribution:** the crash appeared when that test's fixture moved from
an mdtraj-written XTC to a ChiSurf-written DCD, so it is *plausibly* mine — but
the coordinates round-trip correctly and the PDB carries the right element
column, so what changed is the numbers reaching an AV grid, not their meaning.
An accessible volume around three atoms is degenerate input either way, and a
segfault is never the right answer to it. **Do not assume the port is
innocent** without checking; equally, do not assume the fixture is the only
caller that can reach this.

**Where to start:** guard `_av_labellib` against a structure too small to grid
(it should raise, not crash), then re-point the fixture at a real structure —
a 3-atom AV asserts nothing useful about efficiency matrices anyway.

**This is why `mdtraj` is still declared.** Every import of it is gone from the
tree, but a suite that segfaults cannot show the removal is safe, and removing
a dependency on the strength of a crash would be backwards.

## storage: a borrowed `Column` from the columnar store is not safe to cache

**2026-08-06.** In the simulation library's `DataStore`, a `Column` handed out
by `add()` or `store[i]` is a borrowed reference into the store's column
container. A structural change can invalidate it, and the stale proxy does not
raise — it reads freed memory and answers with an empty name and an empty
array. The symptom is a column that silently goes blank, which no assertion
catches.

**The append case is fixed at the source, and is not yet in any built
environment.** The container is now one whose references survive an append
(`std::deque`, `modules/core/include/DataStore.h`) — verified by building the
library into a scratch prefix and holding a proxy across fifty `add()` calls:
name, data and write-through all intact, where the shipped build reports `''`
and `[]`. **That change is uncommitted in the library checkout and the binary in
this environment is still the old one**, so every environment here still dangles
on append until it is rebuilt.

**Removal still invalidates, and unevenly.** `remove_column` invalidates some
proxies and not others depending on the index and the container — a vector erase
at index 2 leaves index 0 readable, a deque erase does not. So *whether* a given
proxy survives is not a contract in either build.

**The rule is therefore unchanged: never cache a proxy.**
`chisurf/core/datastore.py` re-fetches through `column_at()` and
`DataStoreSource` goes through it for every access. `test/test_datastore_seam.py`
asserts the positive invariant — `column_at` answers with live data across both
an append and a removal — and passes against the shipped build *and* the fixed
one. It deliberately does **not** assert that a stale proxy breaks: that would
be pinning a bug whose presence depends on the build.

**Two smaller gaps found the same way**, both real and both worked around in
`chisurf/core/datastore.py`: a boolean column has no zero-copy view and decodes
through a per-row Python loop (so a write through the returned array is silently
lost, and filtering a large boolean column is O(n) in Python), and `mask_numpy()`
returns a copy (so a single-cell mask change is a read-modify-write of the whole
mask). Both are listed in the [columnar-store concept](../subsystems/columnar-store.md).

## build: the sibling environment gets a build it cannot load

**2026-08-06.** The photon library is built into the pixi environment and
symlinked into the sibling conda environment. The two disagree about HDF5 — pixi
solves 2.1 (`libhdf5.320`), the conda environment carries 1.14 (`libhdf5.310`) —
so the shared build is unloadable in the sibling:

```
ImportError: dlopen(...): Library not loaded: @rpath/libhdf5.320.dylib
```

**`build-tttrlib` reports success**, because it verifies the environment it
installed into and that one is fine; the sibling breaks silently and shows up
only when a suite next runs there. Worked around by giving the sibling its own
build installed as a real directory instead of a symlink (recipe in
[build and env](../workflows/build-and-env.md)) — **which the next
`build-tttrlib` undoes**, re-creating the symlink.

The durable fix is one of: pin the same HDF5 in both environments, or make the
link step verify that the extension actually *loads* in every environment it
links into rather than only in the one it installed to. Neither is done.

## storage: seven pandas HDF5 call sites are dead in a freshly solved environment — RESOLVED 2026-08-06

**Resolved** by [PRD-82](../prds/prd-82.md) stage 2: all seven writers now go
through `chisurf.core.datastore.write_table`, which writes one dataset per
column and needs no optional HDF5 package. `to_hdf` and `HDFStore` appear
nowhere in the shipped package and `test/test_pandas_hdf5_seam.py` fails on one
coming back. Kept here for the part that is **still true**.

**A file written by an EARLIER release still needs that optional package to
open.** `read_table_frame` tries the columnar layout first and falls back to the
frame reader, which needs it; where it is absent the fallback is a named
`LegacyTableError` rather than an empty table, so the failure is legible instead
of silent. That is no worse than before — those files were unreadable there
either way — but it means the removal is complete for *writing* and not for
*reading history*.

A reader for the frame layout was written inside the simulation library and
**reverted deliberately**: that library reads photon data and has no business
knowing another ecosystem's container layout. Do not propose it there again.
The remaining options, neither taken: convert old files on open (needs the
package once, on a machine that has it), or read the layout in ChiSurf, which
means a new HDF5 dependency for a legacy path. Both are worse than the named
decline until someone has a file they actually cannot open.

## globalview: two graph builders, and they have already drifted

**2026-08-06.** The parameter graph is built twice. The plugin builds it locally
(`chisurf/plugins/core/globalview/api/graph.py`); the server builds it again, by
hand, for the `graph.build` RPC (`chisurf/server/services/graph.py`,
"mirrors the client-side logic"). They are not one implementation with two
transports — they are two implementations of the same contract, and today they
were fixed twice for the same defect: a link edge resolved by parameter *name*,
which drew an arrow from a follower to every same-named parameter in the session
(three fits with a `tau1` turned one link into three arrows, two of them false).
The server copy has also never had the `group` node type the plugin grew for
out-of-fit parameter groups, so a network fetched over RPC is missing every
plugin working model that a locally built one shows.

The durable fix is to delete the server copy and have `graph.build` call the
plugin's Qt-free `api/graph.py`, which already returns plain dataclasses. It was
not done here because the plugin `api` package has not been checked for
Qt-freeness in the server's import path, and unifying it is a wider change than
the GUI work that surfaced the defect. Until then, **a change to one builder must
be made to the other**, and the record is
[core tools](../plugins/core-tools.md#global-view-the-parameter-network).

## The assistant still fabricates a citation now and then

**2026-08-06.** Over thirteen live questions on `mistral-large-latest`, two
answers named a page that does not exist — `docs/concepts/pda.md` and
`docs/guides/42_fret_from_bursts.md`. Both are plausible file names for pages
that *could* exist, which is exactly why the model wrote them. Nothing reached
the reader: `ask.verify_citations` resolves every path, strikes the dead ones
and reports them, and both the panel and the CLI say so in as many words. So
the guard works and the behaviour underneath does not.

Worth knowing before trying to fix it: the fabricated paths appear **alongside
real, opened ones** in the same answer, so "did it read anything" does not
catch it — only resolving each path does. The obvious next step is to give the
model the page list it is allowed to cite (the `related` list already in every
`read_documentation` result), or to feed the struck paths back for one
correction turn the way `READ_FIRST` does for an unread answer. Neither was
done here because the current behaviour is honest and visible, and a second
retry turn costs every answer a round trip to fix one in six.

## (closed) The documentation assistant has never answered a question from a real model

**Closed the same day** — a working key arrived and the battery was run; see
the log entry and [LLM agent](../subsystems/llm-agent.md). What follows is the
original note, kept because it says what the measurement is.

**2026-08-06.** `chisurf/plugins/core/help/api/ask.py` and everything behind it
are covered by scripted-model tests (the restricted registry, the citation
collection, the panel's rendering of an answer, a no-read answer and a
failure), and the retrieval underneath is covered by asserting *which page*
comes back for a question. What has **not** happened is one end-to-end run
against a live provider: on the machine this was built on, the configured
Mistral key expired the same day (HTTP 401, "Your API key expired on
2026-08-06") and the OpenRouter account has no credit (HTTP 402, "can only
afford 213" of the 4096 reserved tokens). Both error paths are reported
clearly, which is itself worth something, but the *answer* path has only ever
run against `ScriptedLLM`.

What that leaves unknown is not the plumbing — it is whether the prompt and the
`answer-from-docs` skill actually make a model browse before it answers rather
than answering from memory and citing nothing. The measurement is exactly the
one the panel already shows: run `csc help ask "what does the gamma factor
correct for?"` with a working key and check that `answer.pages` is non-empty
and names `docs/concepts/accurate_fret.md`. If it comes back empty, the fix is
in the skill, not in the harness.

## An in-flight rename left `test_an_ambiguous_model_name_asks_for_the_full_one` red

**2026-08-06.** `test/agent/test_tools.py` fails in the working tree, and it is
not this change: another instance is renaming the TCSPC model from
`"Lifetime (new)"` to `"Lifetime"` and applied the rename mechanically to the
ambiguity fixture, which turned a prefix-only case into an exact-match one.
With the registry `["Lifetime", "Lifetime mixer"]`, asking for `"Lifetime"` is
not ambiguous — `resolve_model_name` finds an exact match and returns it, which
is the documented and correct precedence. The test is the defect, not the code:
the fixture needs a registry where no exact match exists (`["Lifetime ",
"Lifetime mixer"]`, as it effectively was before). Left alone here because the
file has another instance's uncommitted edits in it.


## Mutagenesis resets the view, and hidden waters come back

**2026-08-07**, reported by the user against the state-based wizard
(`03a04ca07`). Two defects, both about state the wizard is not preserving.

**1. The view is reset.** Something in the mutagenesis flow still moves the
camera. The build and the rotamer step are each wrapped in
`_wizard_keeps_the_camera` (`cmd/interactions.py`), and
`test_the_wizard_never_moves_the_camera` asserts `get_view_state()` is
unchanged across `wizard target` and two `wizard rotamer, next` — so the path
that does it is **not** one of those two, and the guardrail passes while the
user sees the fault. Candidates, in the order worth checking:

* `wizard apply` and `wizard clear`/`done` — neither is wrapped. Apply
  rebuilds the source object, which is exactly the operation that re-derives
  the scene centre and radius;
* `_wizard_delete_preview` — removing an object changes the scene bounds the
  same way adding one does;
* entering the wizard at all (`wizard mutagenesis`), or the residue pick that
  precedes it.

Take the measurement the same way the earlier camera bug was finally caught:
`get_view_state()` before and after **each** command in a full session
(`wizard mutagenesis` → pick → `target` → step → `apply` → `done`), not only
the two already covered. Note the trap recorded in the parity concept: the
symptom reads as *darkness* in a screenshot, because the molecule recedes
rather than the lighting changing.

**2. Hidden waters reappear.** Visibility set before the wizard runs is lost —
`hide solvent` (or any scoped `hide`) comes back on. Almost certainly the same
root cause as the first: whatever rebuilds the source object on Apply is
restoring the representation masks from the payload rather than carrying the
object's current ones across. If so, one fix closes both, and the test should
assert the *masks* as well as the view state, since a rebuilt object with
default visibility is indistinguishable from a correct one in a mesh count.

**Tried to fix, and it does not reproduce through the command path.** Measured
on 148L, driving the whole flow as commands (`wizard mutagenesis` → `target` →
`rotamer, next` → `apply` → `done`) and printing the 18-float view state and
the per-atom masks after each:

* the view is **identical at every step**, apply included — position
  `[0, 0, -467.83]`, near/far/fov `[1.65, 660.39, -20]`. So `apply` being
  unwrapped is *not* the cause, and wrapping it would fix nothing;
* the masks resize correctly: `sticks_mask` goes 1363 → 1370 with the atom
  count when a THR becomes a TRP, rather than being dropped or left stale;
* the water half could not be exercised at all — **148L carries no waters**
  (`tot=0`), so a fixture with solvent is needed to see it.

That leaves the **GUI interaction path**, which is what the report came from
and what none of this touched. Two candidates worth taking first:

* the mouse mode itself. In 3-Button Viewing, `SnglClk` is **Cent** — a single
  click centres on the atom under the cursor. Picking the residue to mutate is
  a click, so the "reset" may be the mouse mode doing exactly what the panel
  says it does, and the fix (if any) is that picking *for the wizard* should
  not re-centre;
* whatever the object menu's **H** button emits for waters, followed by
  `_refresh_objects_from_viewer` after apply. The command spelling is
  `hide everything, solvent`; a bare `hide solvent` is rejected
  ("Unsupported representation for show/hide: solvent"), so the two paths may
  not be setting the same state.

Reproduce with a structure that has waters, driving the GUI rather than the
command line — the standing correction in the parity concept applies: a test
that calls the handler cannot see what the widget does.
