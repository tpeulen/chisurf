---
type: Playbook
title: Testing
description: The non-GUI, GUI, smoke, and doctest suites and how to run a single test.
resource: pixi.toml
tags: [testing, pytest, ci]
timestamp: '2026-07-05T00:00:00Z'
---

# Environment (canonical: the `arm64` conda env)

Run all tests and any `python`/`pytest` in the project's **`arm64` conda env**,
never conda `base`. It provides the full stack the suite needs: the Qt bindings,
the compiled C++ extensions, and **IMP + IMP.bff** (`has_imp()` → True).
Since 2026-08-10 that IMP is **not** the conda package but a local build of IMP
**2.25** (`develop`) from `/Users/tpeulen/dev/imp`, with `modules/bff` symlinked
at the `../imp.bff` checkout and the build tree wired in by a single `.pth` —
see [IMP from source](imp-local-build.md). The conda `imp` package is removed
from the env; re-installing it would shadow the build.
Because IMP is present, the IMP-gated tests (the FRET plugin's
`refine`/`errors`/docking, `test_imp_engine.py`, `test_dock_project.py`) **run
here** — a `skipif not has_imp()` test only skips on a machine that lacks IMP,
not in `arm64`. As of 2026-08-10 they also **pass**: the FRET plugin suite is
6 failed / 122 passed, and the six are `test_examples.py` wanting the absent
`../olga` checkout. Until that date ten failed on
`IMP.bff.restraints.AVNetworkRestraintWrapper` — not because IMP lacked it, but
because `modules/imp-tricks/src` shadowed the package that has it; see
[IMP from source](imp-local-build.md#what-the-build-fixed-and-what-it-did-not).

```bash
source ~/.zshrc && conda activate arm64      # activate first
```

Local module sources are on `PYTHONPATH`, not installed as packages, so when
running pytest directly (outside `pixi run`) prepend them:

```bash
PYTHONPATH="modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:." \
  python -m pytest <targets> -p no:cov -o addopts="" -q
```

`-p no:cov -o addopts=""` avoids the repo coverage config (which errors with
"Can't combine branch coverage"). GUI/widget tests additionally need
`QT_QPA_PLATFORM=offscreen` and their own pytest process (mixing GUI and non-GUI
modules can segfault at Qt teardown).

# Test tasks

The pixi tasks wrap the above (CI uses pixi; they `build-extensions` first):

```bash
pixi run test           # non-GUI test suite (build-extensions first)
pixi run test-gui       # GUI/widget tests (-k 'widget or gui')
pixi run test-smoke     # fast smoke test (test/test_basic.py)
pixi run test-doctest   # doctests
```

All `test*` tasks `depends-on` `build-extensions`, so the
[compiled modules](/subsystems/compiled-modules.md) are built first.

# Single test

Run one test directly with pytest, e.g.

```bash
pytest test/test_basic.py::test_name -q
```

The `slow` marker is excluded from default runs. Tests live in `test/`, in
per-plugin `**/test/` directories, and in
`chisurf/gui/widgets/node_editor/tests`.

# Feature testing

Every feature should have a headless test path (API/CLI), not GUI-only.
Model/UI changes have a dedicated headless check via the `test-model-editor`
skill.

# Guarded imports are checked, because they fail quietly

`test/architecture/test_guarded_imports.py` walks the tree and re-resolves
every absolute import that a `try` body depends on. A `try: import x / except:
x = None` is how an optional dependency is handled *and* how a renamed module
becomes a feature that silently stops working — three such cases were live when
the test was written (ndX's reorganisation had disconnected two tools; a
renamed editor had degraded a labelling view to raw text).

Two patterns are deliberately not flagged: a handler re-importing the *same*
names is a version shim (a private SciPy symbol moving between releases), and a
nested handler is a direct-execution fallback. Anything genuinely optional goes
in the test's `OPTIONAL` map **with a reason**, so "this may be absent" is a
decision on the record rather than an anonymous `except`.

# A failure path must not open a dialog nobody can close

`QMessageBox.critical(...)` spins its own event loop until a button is pressed.
Under `QT_QPA_PLATFORM=offscreen` — every headless suite, every CI job, every
screenshot script — no button can ever be pressed, so a dialog on an `except`
branch does not report the error: it **wedges the process**, and the traceback
is never seen. That is worse than a crash, because a hung run is
indistinguishable from a slow one. The fFCS filter-calculator module was hanging
this way and had to be diagnosed with `sample(1)` and
`faulthandler.dump_traceback_later`, which is the tell: if a suite stops
producing dots and no test has failed, suspect a modal dialog before suspecting
the machine.

Report through [`chisurf/gui/dialogs.py`](../../chisurf/gui/dialogs.py) —
`report_error` / `report_warning` / `report_information`. They log
unconditionally and raise the box only when `QGuiApplication.platformName()` is
a real window system, so interactive behaviour is unchanged. The same
`is_interactive()` predicate is the right guard for any modal built by hand:
"a `QApplication` exists" is *not* the same question as "a person is there".

`test/test_headless_dialog_seam.py` fails when a **new** file calls a raw
`QMessageBox` static from inside an `except` handler, tracking the remaining
ones in `test/headless_dialog_allowlist.txt` (the same allow-list-as-tracker
convention as the pyqtgraph seam). A confirmation prompt on a button click is
deliberately not flagged: there the user is right there, which is the point.

# A test that closes the main window writes the developer's own settings

`Main.closeEvent` calls `_save_window_state()`, which writes the dock layout to
`QSettings("ChiSurf", "MainWindow")` — the **real** user preferences. Anything
that closes the window therefore edits them, including `qtbot.addWidget(win)`,
whose teardown closes every widget it was given. A test run then silently
replaces the window layout the developer had, and the *next* run of that
supposedly isolated test restores it and measures the wrong window.

Redirecting `QSettings` is not enough, and on macOS the obvious redirect does
not work at all: `QSettings.setPath` **has no effect on the native format**, so
a script that sets it goes on reading and writing
`~/Library/Preferences/com.chisurf.MainWindow.plist` while looking isolated.
Two things that do work:

* In a test — patch `QtCore.QSettings` with a subclass that ignores the
  organisation/application arguments and opens an ini file under `tmp_path`,
  **and** neutralise `_save_window_state` on the instance in the fixture's
  finalizer, because `qtbot` closes the window *after* `monkeypatch` has put the
  real class back. `test/gui/test_dock_layout.py` does both.
* In a headless script — run it with `HOME` pointed at a scratch directory. The
  native store is resolved under `$HOME`, so this isolates reads as well as
  writes without touching the code under test.

The symptom to recognise: a layout/geometry test that passes alone and drifts
in a suite, or a "default layout" screenshot that quietly stops being the
default.

# GUI work is never blind — screenshot and look at it

**Any change that touches a GUI is unfinished until the widget has been rendered
and the rendering has been *looked at*.** Passing construction tests only prove
the widget did not crash; they say nothing about clipped labels, fields that
wrapped into a nonsensical two-column pairing, a status box that swallowed the
panel, a plot drawn upside-down, or a tab bar overlapping its content. Those are
the defects users actually report, and every one of them is invisible to
assertions and obvious in a PNG.

The loop, for every GUI change:

1. Build the widget headlessly in the `arm64` env with
   `QT_QPA_PLATFORM=offscreen` — no display needed.
2. Drive it into the state a user would see (load a real test file, run the
   analysis, switch to each tab) — an empty widget hides most layout defects.
3. `widget.grab().save(...)` into the scratchpad, then **read the PNG and inspect
   it**. The agent inspects it; do not hand PNGs to the user to eyeball.
4. Fix what looks wrong and repeat until it looks right. Resize once before the
   final grab — some layout artefacts only settle after the first real resize.

**A 3-D viewport needs a different shutter.** The offscreen platform cannot
create an OpenGL context at all — it says so, once, and then every grab of a
`QOpenGLWidget` is a black rectangle, which reads as a broken renderer rather
than a broken camera. A `QOffscreenSurface` under that platform does not help:
context creation still fails.

What works is the *ordinary* platform with `WA_DontShowOnScreen`. The window is
realised — real backing store, real GL context, everything renders exactly as a
user would see it — and is never mapped onto the display, so nothing appears and
nothing steals focus. `chisurf/plugins/chimol/test/screenshot.py` wraps it:

```python
from chisurf.plugins.chimol.test.screenshot import ensure_app, shoot

app = ensure_app()          # refuses QT_QPA_PLATFORM=offscreen rather than lying
paths = shoot(window, "npc_demo")   # {"window": ..., "view": ...}
```

`grab_window` composites the GL children in at their own geometry, because
`QWidget.grab()` renders the widget tree and does *not* read back a child GL
surface — a plain whole-window grab of a 3-D application comes out with a hole
where the interesting part is. It needs a logged-in session, so it is skipped
rather than failed where there is no window server.

Until this existed, the appearance of the one part of ChiMOL where appearance
matters most was judged either through the ray tracer — a different renderer,
with no materials and no transparency — or by asking a human to look. Both were
misleading in practice: a metaball material tuned against the ray tracer looked
entirely different in the viewport.

Interactive behaviour (a dragged ROI, a picked point) is still verified by
driving the signal programmatically and asserting the model changed, not by
looking.

Screenshots that end up in `docs/guides/` are produced the same way from the real
widget — see `docs/guides/make_screenshots.py` — never as mockups.

# A migration is proven by a before/after pair

Rendering the *new* widget answers "does this look right". Replacing a
hand-written widget asks a different question: **was anything lost?** A panel can
look immaculate and be missing the one control the fit needed. So a migration —
porting a legacy widget to AutoForm, or any like-for-like replacement — is
verified as a **pair**.

The loop:

1. **Grab the legacy widget first, before touching the code.** Once it is deleted
   or aliased away the baseline is unrecoverable. Settle the comparison format
   first as well: changing what you record invalidates baselines already taken.
2. Grab the replacement in the **same state**, at the same render width — a
   different width reflows the layout and confounds the comparison.
3. Diff the control inventories, read both PNGs, and accept only on parity.

`test/gui/migration_parity.py` provides the pieces: `capture(widget, name, phase)`
writes `<name>.{before,after}.png`; `control_inventory` extracts the comparable
content; `compare_inventories` reports what was lost or gained; `layout_tripwire`
catches gross failures.

**Parity is control inventory, not pixels.** An AutoForm port *deliberately*
changes layout — a `parameter_group_table` replaces stacked labelled rows,
because that is the improvement. Any pixel-similarity or SSIM gate is therefore
either red on every migration or tuned so loose it proves nothing. Compare *what
controls exist*:

- Enumerate every control in the before-image — each parameter, its fixed/bounds
  toggles, every button, picker and toggle.
- Confirm each is present and reachable in the after-image, and that values
  round-trip identically for the same loaded data.
- Record deliberate differences ("6 stacked rows → 1 table"). A **missing**
  control is a blocker.

**Two traps that make a naive diff useless.** Both were hit on the Lifetime
migration:

- *A name that moved into a table cell reads as lost.* `findChildren(QLabel)`
  cannot see cell text, so porting to a parameter table reports every parameter
  as missing. `control_inventory` walks item-view models for exactly this reason —
  a comparison blind to table content is red on every migration.
- *Renames masquerade as losses.* `r[MHz]`→`rep`, `Linearize`→`DNL` (the same
  `correct_dnl` flag, relabelled by an old `.ui`), `curve`→`full`, `...`→`…`,
  `update`→`🔄`. Text is normalized (rich-text tags, disclosure glyphs, case,
  whitespace) before diffing, and the remainder still needs reading by a human
  who knows which control is which.

Keep the mechanical **tripwire** alongside the human read — `layout_tripwire`
checks non-empty render size, enough visible children, and nothing positioned
outside its parent. That catches the blank-panel and collapsed-layout class the
eye skims past; the inventory diff catches the semantic loss.

# Citations

[1] [Project instructions (CLAUDE.md)](/references/claude-md.md)

## Release-readiness schema and e2e foundation

The native view vocabulary is exported by emtk's readers, with extension keys
owned by the relevant preprocessor. `test/test_ui_schemas.py` now covers native
form maps/templates and tour routing as well as the legacy loader. Rejection
cases stay green; accepting a native dictionary is not permission to drop its
fields into a Qt dataclass. Source integration was 649 targeted passes; the
pinned package plus workflow/triage guards passed 677.

`build_tools/dev_utils/triage_failures.py --junit <file> [--write <report>]` groups
JUnit failures and errors by owning workstream without importing the GUI. CI
runs a separate e2e job with always-uploaded render artifacts, checks smoke
before packaging, and fails explicitly if the private chimol deploy key is
missing. The click-all harness is being verified one isolated plugin at a time.


## Isolated plugin interaction gate

`test/e2e/test_click_all_plugins.py` discovers native entrypoints and the
remaining Qt-only factories. Each plugin runs in its own process with scratch
settings, metadata, object storage and cache. Worker JSON/log/PNG artifacts
live in `renders/e2e`; their harness_sha256 must match the tested source.
Timeouts, native crashes, missing tours/tooltips and unreachable controls are
explicit failures. A failed factory cannot retain an older PNG as evidence.

Native clicks require a visible effective clip and real engine delivery to
the intended context. The recorder maps translated/scaled child painters to
global coordinates, distinguishes independent engines with identical IDs,
opens actual AutoForm folds and scrolls reachable controls. Tour checks walk
introductions and operate the first real awaited target; duplicate labels
resolve through authoritative geometry/context, and ambiguity fails.
Field text retained for interaction is private to the worker, not serialized.
OS dialogs cancel; service/network and external-process actions remain
guarded. Slow local computations must expose a working Cancel/Stop control.

Re-derive the harness regressions with
`pixi run -e test python -m pytest test/e2e/test_click_all_harness.py -q`
(36 passed), and select real plugin cases with `-k <plugin_id>` on the click-all
file. A complete plugin matrix remains a programme gate after the owning
workstreams supply tours, demos, reachable layouts and source prerequisites.
The C27 matrix and intermediate hash runs are diagnostic, not acceptance.


## Lint A/B targets

The approved lint worktree's target inventory is retained below. Select the
files relevant to a change; this list is not a command to run a full suite.
Use separate read-only revisions/archives for an A/B comparison and preserve
their working contents. Do not copy the old script's checkout loop into the
shared working tree.

Pixi remains the standard runner. For the documented arm64 alternative,
the old environment line required offscreen Qt, Agg, no bytecode and local
module source paths; use a task-specific root and cache:

```sh
READINESS_REPO_ROOT=/Users/tpeulen/dev/chisurf
QT_QPA_PLATFORM=offscreen MPLBACKEND=Agg PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=.:modules/mmfdb/src:$READINESS_REPO_ROOT/modules/chinet:$READINESS_REPO_ROOT/modules/imp-tricks/src:modules/chimol \
  NUMBA_CACHE_DIR=/private/tmp/readiness-numba-cache \
  /Users/tpeulen/mambaforge/envs/arm64/bin/python -m pytest <targeted-files> -q
```

The imp-tricks namespace startup repair is a prerequisite for this alternate
source path. Use scratch settings/MMFDB storage for every GUI judgment.

```text
chisurf/plugins/burst/accurate_fret/test
chisurf/plugins/burst/alex_suite/tests
chisurf/plugins/burst/burst_2cde/tests
chisurf/plugins/burst/burst_background/test
chisurf/plugins/burst/burst_browser/test
chisurf/plugins/burst/burst_bva/tests
chisurf/plugins/burst/burst_ebfret/tests
chisurf/plugins/burst/burst_fcs_correlator/test
chisurf/plugins/burst/burst_fusion/tests
chisurf/plugins/burst/burst_gs/test
chisurf/plugins/burst/burst_h2mm/tests
chisurf/plugins/burst/burst_irf_bg/test
chisurf/plugins/burst/burst_mle_analysis/tests
chisurf/plugins/burst/mfd_prepare/tests
chisurf/plugins/calculator/fcs_saturation_calc/tests
chisurf/plugins/calculator/fret_calculator/tests
chisurf/plugins/calculator/hub/test
chisurf/plugins/calculator/kappa2_dist/test
chisurf/plugins/calculator/kappa2_dist/tests
chisurf/plugins/calculator/phasor_calculator/tests
chisurf/plugins/calculator/psf_calculator/tests
chisurf/plugins/calculator/rics_precision/test
chisurf/plugins/calculator/rics_precision/tests
chisurf/plugins/core/batch_analysis/test
chisurf/plugins/core/boarding/test
chisurf/plugins/core/code_editor/test
chisurf/plugins/core/f_test/test
chisurf/plugins/core/globalview/tests
chisurf/plugins/core/help/test
chisurf/plugins/core/hmm/test
chisurf/plugins/core/lightpath_simulator/tests
chisurf/plugins/core/model_manager/test
chisurf/plugins/core/plot_settings/test
chisurf/plugins/core/plugin_check/test
chisurf/plugins/core/plugin_manager/test
chisurf/plugins/core/project_browser/test
chisurf/plugins/core/pto_inspector/test
chisurf/plugins/core/setup_channel_definition/test
chisurf/plugins/core/setup/test
chisurf/plugins/core/style_manager/test
chisurf/plugins/core/switch_user/test
chisurf/plugins/core/tttr_to_pto/test
chisurf/plugins/core/updater/test
chisurf/plugins/core/user_editor/test
chisurf/plugins/core/wizards/test
chisurf/plugins/fcs/fcs_calculator/test
chisurf/plugins/fcs/fcs_filter_calculator/test
chisurf/plugins/fcs/fcs_lfcs_sim/test
chisurf/plugins/fcs/fcs_merger/test
chisurf/plugins/fcs/flc_2d/test
chisurf/plugins/fluorescence_decay/irf_estimator/test
chisurf/plugins/fluorescence_decay/lifetime_analysis/test
chisurf/plugins/fluorescence_decay/lifetime_analysis/tests
chisurf/plugins/fluorescence_decay/lltf/test
chisurf/plugins/fluorescence_decay/maxent_decay/test
chisurf/plugins/fluorescence_decay/synthetic_decay/test
chisurf/plugins/fluorescence_decay/tr_anisotropy/test
chisurf/plugins/microscopy/clsm_generator/test
chisurf/plugins/microscopy/clsm/test
chisurf/plugins/microscopy/imaging_tools/test
chisurf/plugins/microscopy/img_calibration/test
chisurf/plugins/microscopy/img_coloc/test
chisurf/plugins/microscopy/img_drift/test
chisurf/plugins/microscopy/img_flow/test
chisurf/plugins/microscopy/img_frc/test
chisurf/plugins/microscopy/img_pixel_intensity/test
chisurf/plugins/microscopy/img_pixel_micro_time/test
chisurf/plugins/microscopy/img_pixel_mle/test
chisurf/plugins/microscopy/img_pixel_nb/test
chisurf/plugins/microscopy/img_pixel_phasor/test
chisurf/plugins/microscopy/img_tracking/test
chisurf/plugins/microscopy/psf_determination/test
chisurf/plugins/microscopy/psf_determination/tests
chisurf/plugins/microscopy/region_mle/test
chisurf/plugins/microscopy/spot_finder/test
chisurf/plugins/microscopy/spot_finder/tests
chisurf/plugins/misc/games/test
chisurf/plugins/modelling/hydropro/test
chisurf/plugins/modelling/structure_tools/test
chisurf/plugins/traj/fret_trajectory/test
chisurf/plugins/traj/potential_energy/test
chisurf/plugins/traj/traj_align/test
chisurf/plugins/traj/traj_convert/test
chisurf/plugins/traj/traj_join/test
chisurf/plugins/traj/traj_remove_clashes/test
chisurf/plugins/traj/traj_rotate_translate/test
chisurf/plugins/traj/traj_save_topology/test
chisurf/plugins/traj/traj_tools/test
chisurf/plugins/tttr/audifier/test
chisurf/plugins/tttr/filetools/test
chisurf/plugins/tttr/microtime_histogram/tests
chisurf/plugins/tttr/photon_table/tests
chisurf/plugins/tttr/ptu_alex_creator/test
chisurf/plugins/tttr/trace_browser/test
chisurf/plugins/tttr/tttr_count_rate_analysis/test
chisurf/plugins/tttr/tttr_count_rate_analysis/tests
chisurf/plugins/tttr/tttr_image_browser/test
chisurf/plugins/tttr/tttr_lut_tools/tests
chisurf/plugins/tttr/tttr_microtime_shifter/tests
chisurf/plugins/tttr/tttr_time_windows/tests
chisurf/plugins/tttr/tttr_toolbox/test
test/core/test_dye_definition_shipped.py
test/core/test_emtk_preview_gate.py
test/fio/test_ndxplorer_rpc_bridge.py
test/fio/test_setup_store_fresh_database.py
test/fitting/test_bff_sampler_result_boundary.py
test/gui/emtk_layout_checks.py
test/gui/emtk_port_parity.py
test/gui/test_emtk_port_parity.py
test/gui/test_metadata_editor_first_use.py
test/native_emtk/test_channel_definition.py
test/plugins/burst/test_background_diagnostics.py
test/plugins/burst/test_irf_background_window.py
test/test_build_tttrlib_sibling_envs.py
```
