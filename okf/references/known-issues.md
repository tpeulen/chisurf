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

**Found 2026-07-26 while making the tcPDA rate matrix fittable.** A rate fitted
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
`TcPdaModel._mean_channel_probabilities`: each state is collapsed to its
distance-averaged per-photon probability vector *before* the occupation-time
mixing, so the intra-state distance spread contributes to the predicted
burst-to-burst width differently than it does to real bursts. Fixing it properly
means carrying the distance quadrature through the dynamic average (nodes x
occupancy nodes x bursts), which is a real cost increase and a design decision
about where to truncate — hence recorded rather than fixed in the change that
found it. Until then, `tcpda.py`, the concept page and the guide all say to read
a fitted rate as an exchange **timescale**, not a rate measurement; comparisons
between conditions are sound.

Note this was invisible before, because the rate matrix was a plain array
attribute nobody could fit — the bias only became reachable when the rates
became parameters.

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
- ~~`test_group_polarization_any_size.py` errors at collection.~~ — fixed
  2026-07-26.

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

- **`vm_rt_to_vv_vh` puts the g-factor in the one place that is not
  invertible.** `chisurf/core/fluorescence/anisotropy/decay.py`. It computes
  `vh = vm · (1 − g·r)`, while its sibling `calculcate_spectrum` — the one the
  fitting models actually call — computes `g · vm · (1 − r)`. Only the latter
  satisfies `r = (I_VV − I_VH/g) / (I_VV + 2 I_VH/g)`; a detection sensitivity
  scales the whole perpendicular channel, not just its depolarization term, so
  the two agree only at `g = 1`. Not changed on the spot because it is a
  numerical change to a public helper and the same formula is repeated in
  `docs/concepts/anisotropy.md` and
  [anisotropy-theory](/references/anisotropy-theory.md); the fix is one line plus
  those two doc updates plus a `g ≠ 1` test, and belongs in its own change.
  Harmless meanwhile: the only in-tree callers are its doctest and
  `test_vm_vv_vh`, both at the default `g = 1`.

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
- `test/core/test_rename.py` breaks collection of the **whole** `test/core`
  package on any machine that is not the original Windows one: it is not a test
  but an ad-hoc tttrlib file-locking script that runs at import time and opens a
  hardcoded `e:\dev\chisurf\test\data\clsm\Leica_SP8.ptu`, so
  `pytest test/core` stops at `FileNotFoundError` before running anything. It
  carries no test function and no assertion; it was swept in by the
  package-layout reorganisation (`e56240187`). The fix is to delete it or turn
  it into a real test over `test/data/clsm/`. Left alone here only because this
  run was scoped to a single review finding (RF-001) in a shared working tree —
  workaround: `pytest test/core --ignore=test/core/test_rename.py`.
- Four test modules import `chisurf.gui.widgets.yaml_utils`, which **has never
  existed** — `git log -S` finds no commit adding or removing it. They fail at
  collection with `ModuleNotFoundError`, taking `test/plugins` down with them:
  `test/plugins/test_plugins_list_format.py`, `test/settings/test_yaml.py`,
  `test/settings/test_real_settings.py`, `test/gui/test_list_editor_fix.py`.
  Neither `dump_yaml` nor `prepare_for_yaml` is defined anywhere in `chisurf/`,
  so these tests never ran against real code — they are the same
  never-existed-API class as `test/models/test_user_models.py` below and need
  rewriting against the settings serializer or deleting, not a re-import. Left
  alone here only because this run was scoped to one PRD-36 tool migration.

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
  but ndXplorer run standalone would raise. The root fix belongs in the ndxplorer
  repository — left alone here only because that working tree currently holds
  another instance's uncommitted work.

# Deferred enhancements

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
