---
type: Subsystem
title: Qt retirement (shell)
description: Parity ledger for moving the ChiSurf main window from Qt to one emtk surface — every Qt capability the shell uses, its emtk equivalent or gap, the allow-list by area, and the ordered slices that keep the app shippable.
resource: chisurf/emtk/main_app.py, chisurf/emtk/post_show.py, chisurf/startup/services.d/35_emtk_post_show.json, chisurf/emtk/shell_ribbon.py, chisurf/emtk/shell_session.py, chisurf/emtk/shell_log.py, chisurf/emtk/fit_report.py, chisurf/core/fitting/fit_export.py, chisurf/emtk/console.py, chisurf/emtk/fit_docks.py, chisurf/emtk/fit_window.py, chisurf/emtk/status_strip.py, chisurf/emtk/fit_pages/plots.py, chisurf/emtk/fit_pages/surface.py, chisurf/emtk/session.py, chisurf/emtk/model_editor.py, chisurf/emtk/model_sections.py, chisurf/emtk/pda_sections.py, chisurf/emtk/sample_picker.py, chisurf/emtk/fit_controls.py, chisurf/server/services/model_svc.py, chisurf/server/services/model_sections.py, chisurf/core/server_events.py, chisurf/__main__.py, chisurf/gui/__init__.py, test/test_no_qt_imports.py, okf/plugins/emtk-ports/shell/retire_qt_before.json
tags: [gui, emtk, qt-retirement, shell, parity, ledger]
timestamp: '2026-10-14T12:00:00Z'
---

# Where to pick this up

**S6 is done on branch `s6-retire-qt-shell` (2026-10-14), waiting for the owner to merge it.** The Qt
shell and every Qt module are deleted, `--qt` is gone, qtpy / pyqt / pytest-qt are struck from `pixi.toml`,
`pyproject.toml` and the recipe (the lock regenerates when the branch is merged; nothing ran `pixi install`), and
`test/test_no_qt_imports.py` rejects any Qt import under `chisurf/` with no allow-list. Until the merge, the main
line still carries the Qt shell behind `--qt` and everything below describes it; after the merge read item 9 and
the S6 paragraph in "History" first. What the merge needs: item 9.

Phase 2 of [PRD-154](../prds/prd-154.md) W9. Slice S1 is done: `python -m chisurf` opens
`chisurf/emtk/main_app.py` (the default since 2026-10-11; `--qt` opens the Qt window kept for parity). It has a manifest menu bar, Tools, Start and Log docks, and every native plugin opens as
a dock window. Slice S2 reached control parity with the Qt docks on 2026-10-11: `KNOWN_GAPS` in
`test/native_emtk/test_emtk_shell_fits.py` is empty. The Analysis dock draws each model's own `view.json` editor from
`model.editor` (`chisurf/emtk/model_editor.py`) and carries the whole fit controller. A fit window turns over to its
Code face. The session holds the Global Dataset, and a dataset row dragged onto a fit window is attached to that fit.
The model editor's curve pickers and custom sections, the PDA reader's form, the link menu, paired component rows
and *New…* sample followed the same day, at parity with the Qt model editors of ten models (item 2).
Slice S3 reached control parity for the session menus on 2026-10-11 (`chisurf/emtk/shell_session.py`): File, View
and Settings with the Qt shortcuts, save and reopen of `.cs.pto`, undo and redo, autosave, a close guard that asks
once, and a fit window `×` that asks and then removes the fit. `KNOWN_GAPS` in
`test/native_emtk/test_emtk_shell_session.py` is empty (re-checked 2026-10-13, 13 pass). Slice S4 reached parity with the Qt console the
same day: a Console dock on emtk's `TextEditor` over the Qt-free engine (`chisurf/emtk/console.py`), *Macro ▸ Record*
and *Run Macro…*, `chisurf.run` routed to it, and composed (dead-key and IME) text in every emtk text field
(`emtk.ime`). Slice S5's ribbon reached parity with the Qt ribbon the same day
(`chisurf/emtk/shell_ribbon.py` on emtk's new `emtk.ribbon`): its tabs, groups and buttons come from the manifests
through the Qt ribbon's own placement rules, and the menu bar and Tools dock list the same tree with the manifest
icons. The splash window and its startup stages landed 2026-10-12 (item 12), and S5's status strip reached control
parity with the Qt status bar on 2026-10-13 (item 5), and the Qt post-show stages that are not about the
window run in the shell the same day: `check_updates` as a post-show stage, `warmup_imports` by the session's
own startup stages (item 5): S5 is done.

1. Measure: the plugin Qt allow-list is **empty** (since the mmfdb_admin slice, 2026-10-13; 244 before the
   2026-10-12 test-port slice). Re-derive with `grep -v '^#' test/plugin_qt_allowlist.txt | grep -c .` (0); guard
   `test/test_plugin_qt_free.py`, which now rejects any Qt import under `chisurf/plugins/` (on the S6 branch the
   list is deleted and the guard is `test/test_no_qt_imports.py` over all of `chisurf/`). Every plugin is an emtk
   app the `--qt` shell hosts through `ControlHost`. A Qt importer under `chisurf/plugins/` is a new failure, so
   one-off Qt recorders stay uncommitted. The slice-by-slice record (counts, before/after evidence, what each
   twin gained, traps) is in "History" below. Trap: the arm64 env imports a non-editable emtk from
   site-packages, not `~/dev/emtk` (e.g. `NO_BUTTON` is in `emtk.events`, not `emtk.app`).
2. Measure: the model editor's curve pickers and the nine `custom` sections (plus a lifetime group's
   `lifetime_amplitude_options`) are resolved by `chisurf/server/services/model_sections.py` and drawn by
   `chisurf/emtk/model_sections.py`; writes go through `model.curve.set` / `model.curve.unload` /
   `model.section.call`, checked against the model's `view.json`. Parity:
   `test_emtk_shell_model_sections.py::test_parity_with_the_qt_model_editors` against
   `shell_s2_models_qt_inventory.json` (10 models: TCSPC with IRF and background, mixture, MaxEnt, structure, FCS
   kinetics, two PDA, global, ProteinMC; `capture_shell_s2_models_qt_before.py`, about 15 min, writes as it goes).
   `KNOWN_GAPS` is empty. Trap: the Qt inventory's dye names come from the user's MMFDB (`ENVIRONMENT` in the test).
   ProteinMC's Sample/Stop and *Structure* page work in the shell since 2026-10-12
   (`test_emtk_shell_recorded_models.py`; known issues "Lifetime mixture, FRET structure fit and the shell's recording").
3. Open: PDA reader leftovers. The form is native (`chisurf/emtk/pda_sections.py`, logic in
   `chisurf/core/experiments/pda2c/inputs.py` and `settings.py`); `KNOWN_GAPS` in `test_emtk_shell_readers.py` is
   empty. The shell's file dialog still picks one file, so several measurements go through the form's drop list or
   a folder. The Qt form's TW and drop lists stay Qt widgets inside AutoForm custom sections until S6.
4. Measure: deliberate differences after the model-section parity (each a decision, kept as such): a rate cell's
   *Fixed* is on its context menu, not a box in the cell; the link menu lists a fit's parameters flat, not grouped
   twice; a paired table shows every slot column (Qt hides some); *show r(t)* and the κ² windows are dialogs over the
   shell; the ⚙ dialog writes the user settings, because they are preferences and not session state. The link menu,
   paired component rows and *New…* sample (`chisurf/emtk/sample_picker.py::NewSampleDialog`) are ported.
5. Measure: S5 ribbon parity is `test/native_emtk/test_emtk_shell_ribbon.py::test_parity_with_the_qt_ribbon`
   against `shell_s5_qt_inventory.json` (`capture_shell_s5_qt_before.py`, about a minute; PNGs in `renders/w9_s5/`).
   Tab order, group order and button order match; `KNOWN_GAPS` and `DELIBERATE` are empty. *Menu Switch* hides and
   shows the ribbon (menu bar stays; `gui.use_ribbon_interface`, shared with Qt). The pin (`emtk.ribbon`, `pin=True`)
   is Qt's pin/auto-fold: unpinned folds after each pick; pinned keeps fold and tab across sessions
   (`EmtkShellApp.export_settings()["ribbon"]`).
   One layout feeds the ribbon, the menus and the Tools tree: `shell_ribbon.plugin_tree` over
   `chisurf/core/plugin/ribbon_layout.py` (moved out of the Qt package so the shell can import it, with the maturity
   markers now in `chisurf/core/plugin/maturity.py`). The status strip (`chisurf/emtk/status_strip.py`, the
   window's bottom line) is at control parity: `test/native_emtk/test_emtk_shell_status_strip.py` against
   `shell_s5_status_qt_inventory.json` (`capture_shell_s5_status_qt_before.py`, about a minute, PNGs
   `renders/w9_s5/qt_status_*.png`) in five states (idle *Ready*, a logged warning, a startup stage, an operation
   with bar and ✕, a busy operation); `KNOWN_GAPS` is empty, one `DELIBERATE` (the startup stage is the operation's
   text beside its bar; Qt's `showMessage` hides its own startup bar). Fed by the root log handler, the shell's,
   data docks' and project's status lines, `DataDocks.job`, a sampling job (✕ calls `cancel_sampling`) and the
   session's stages (`EmtkShellApp.stage_started` forwards to splash and strip); `EmtkShellApp.begin_task` is the
   Qt status bar's progress-host contract. Trap: the shipped `log_level` is 30, so INFO records reach neither bar.
   Trap: the busy bar slides only with emtk `dc763f5` (negative `progress_bar` fraction), committed in `~/dev/emtk`
   and not pushed; the arm64 env imports an installed emtk, so it draws an empty bar until the pin moves (verify with
   `PYTHONPATH=~/dev/emtk`). Measure: the post-show stages are `services.d/35_emtk_post_show.json` (`surface="emtk"`,
   `phase="post_show"`; `chisurf/emtk/post_show.py`): only `emtk_check_updates`, run on a worker once the shell
   has adopted its session, shown on the strip. `warmup_imports` has no twin (removed 2026-10-13): measured, the
   six modules it imported were all loaded by the time the session settled except `fit_pages.surface` (3 ms), and
   a worker importing while the frame loop imports is the startup deadlock below. Startup import ordering
   (fixed 2026-10-13): about one launch in four died with `_DeadlockError: deadlock detected by
   _ModuleLock('chisurf.server')`. The session worker imported `chisurf.server` (via `chisurf.core.api`) while
   the main thread, still building the shell, imported `chisurf.server.dispatcher` for the Log dock's RPC
   monitor; `dispatcher` → `protocol` → module-level `resources.files("chisurf.server")` re-imported the
   half-initialised package on the main thread while the worker waited for `dispatcher`. Fix, three parts:
   `chisurf.emtk.session` imports the server, the API facade and the event subscriber at module level (the
   `emtk_imports` splash stage is gone), `DataDocks.start()` starts the session worker as the last step of
   `EmtkShellApp.__init__`, and `protocol` reads `server_methods.json` beside its file. Measure:
   `test/startup/test_startup_import_race.py` (subprocess; a finder parks the worker if it ever asks for the
   package itself; fails at the previous HEAD). Re-derive the deadlock at the previous HEAD by pre-importing
   `chisurf.core.project{,.recent,.lifecycle}`, `chisurf.history` and `chisurf.core.actions` on the main thread
   and parking the worker in `find_spec('chisurf.server.app')` for 1 s: about one run in six raises it. Trap: a
   plain `--screenshot` loop never reproduced it (40 runs). The main thread and the worker contend on many shared
   packages (`chisurf.core.project`, `chisurf.core.actions`, `chisurf.history`), so the main thread must not
   import while the worker runs, not only avoid `chisurf.server`. Closed 2026-10-13, for the whole class and not just this instance: `chisurf/_import_gate.py` is installed as the first statement of
   `chisurf/__init__.py`. It puts one re-entrant gate in front of `importlib._bootstrap._find_and_load`, the function every
   first import goes through (the `import` statement, `import_module`, Cython), so only one thread at a time
   imports a module for the first time. A module that is already loaded skips the gate. This covers every worker
   site: the session worker and its server thread, each `BackgroundBuild` (a hosted plugin's build via
   `open_plugin`, the post-show update check, the hubs, the settings hub, the sample picker, the shell's project
   jobs, the fit docks, chimol views), `track`ed store reads, `jobs.py`, the channel-definition and dataset-picker
   executors, background startup services, and about 90 thread or executor sites in plugins. The cost: a frame
   that first-imports while a worker is importing waits for the worker's whole import. Measure that with the
   *gate wait* column of `python -m build_tools.dev_utils.plugin_frame_times`. With the gate alone, frames waited
   up to 640 ms, on modules that emtk imports lazily (fonts, glyph tables, tooltips, tables, colormaps) and on PIL.
   `chisurf/emtk/frame_modules.py` now imports those on the UI thread, in the shell constructor, in `load_plugin`
   and in each `BackgroundBuild.start` or `track`. The list comes from recording the UI thread's first imports
   across all 120 plugins. The shell constructor also imports `child_contract`, `help_guide`, `i18n` and
   `shared_i18n`, and `fcs_saturation` now imports `native_form` at module level. After that the gate wait is 0
   for all 119 plugins measured and for the shell's session-start and plugin-open frames (benchmarks page,
   *Import gate*). Measure: `test/startup/test_startup_import_race.py::test_no_shell_worker_first_import_can_meet_the_main_threads`
   parks each of the session, plugin-build and update-check workers inside a planted package's `__init__` while
   the main thread first-imports into that package. Without the gate both the session and the plugin worker fail
   with `_DeadlockError`. To re-derive that, restore the original `_find_and_load` after `import chisurf` and run
   `SWEEP`. Ten runs in a row pass with the gate. `test/startup/test_import_gate.py` tests the bare mechanism.
   Trap: park the worker inside a module body, never in `MetaPathFinder.find_spec`. CPython calls finders while
   holding its global import lock, which serialises the threads and hides the race. Trap: `import pkg` of a
   half-initialised package silently returns the half-made module (`_lock_unlock_module` swallows the deadlock),
   so the planted submodule has to import the package by name. Rule: a module's top-level code never waits on
   another thread, because the gate is held while that code runs. After 10 s the waiting thread prints which
   import holds the gate. Open: re-run the frame table at low load. The 2026-10-13 runs were at load average
   40-60, where first frames are over 100 ms with or without the gate. a newer version asks the Qt window's *Update Available* question and *Yes* opens
   *Settings ▸ Updates*. Same updater preferences as Qt (`plugins.updater.check_on_startup`,
   `ignore_updates_on_startup`). Only the real window runs them (`make_app(persist=True)`); a test's shell
   and a headless frame never ask the update server. Test: `test/native_emtk/test_emtk_shell_post_show.py`
   (the stages import no Qt, subprocess). The other Qt post-show stages build Qt window state the shell
   makes itself (history, autosave in `shell_session.py`, plugin menus in `shell_ribbon.py`). Open: the strip's new
   strings (*Sampling…*, *Cancel failed: {error}*) wait for the queued catalogue job. Trap: tab and group captions are manifest `display_name` segments, collected for translation
   since this slice (`build_tools/i18n/extract_strings.py::_collect_menu_path`); their de/fr entries are unfinished
   until the queued translation job, so the German shell still shows *Spectroscopy*. Trap: re-extracting while
   another lane has uncommitted `tr()` edits marks their removed strings obsolete; put such entries back (S5 restored
   *Close Help*) or `test_committed_authored_ui_text_has_german_and_french_catalogue_sources` fails.
   **Retiring the import gate (2026-10-13).** The gate and `frame_modules.py` are workarounds: a cross-thread
   import deadlock needs an import *cycle* that two threads enter from opposite ends, or module-level code that
   imports behind the `import` statements' back. `test/test_import_cycles.py` bans both, with no allow-list.
   Rule 1: no cycle in the static module-level import graph (ast over `chisurf/**`, tests excluded). Rule 2: no
   module-level call that imports by name or blocks (`import_module`, `__import__`, `find_spec`,
   `resources.files`, `pkgutil`, threads `.start/.join/.submit`, `time.sleep`, `subprocess`, `urlopen`,
   `parse_args`). Measure: `python test/test_import_cycles.py`. At HEAD 0a6e81d8c there were 17 cyclic
   components (45 modules, 56 cycle edges) and 11 side effects; both counts are now 0. A runtime probe agrees:
   it imports all 2381 modules and records every request for a module that is still initialising, and it finds
   16 at the partial fix and 0 now. The probe is the `_find_and_load` / `_lock_unlock_module` hooks in
   `test_the_graph_model_matches_cpythons_module_locks`, applied to the whole tree.
   Trap, now pinned by that test: on 3.12, `import pkg.sub as s` waits on `pkg`'s lock while `pkg` is still
   initialising (the binding falls back to `PyImport_GetModule`), and so do `from . import sub` and
   `from pkg import sub`. Only `from pkg.sub import name` leaves `pkg` alone, so that is how every cycle was
   broken (chiplot, help api, chigame, structure, models, deer, dataspec, quenching core, FRET api, LUT api,
   history, chinsole, autoform, fcs, fio.structure, math.functions). `chisurf.core.dataspec` loads
   `RpcMethodView` through its module `__getattr__`. Side effects removed: the dead `find_spec("emtk")` guard in
   `emtk_analysis_form.py` (emtk is a hard dependency), `__import__("json")` in burst MLE `engine.py`, and seven
   spectra_downloader probe scripts that called FPbase and parsed `sys.argv` on import (now `main()` under
   `__main__`). Creating an executor is not a side effect, because it starts no thread.
   **Exit criterion:** both rules at zero (met), plus one residual race that no import graph shows. CPython
   takes a submodule's lock *before* importing its parent. If a worker first-imports `pkg.sub` while the main
   thread holds `pkg`'s lock but has not yet put `pkg` in `sys.modules` (the window is `pkg`'s `find_spec`),
   and `pkg/__init__` imports `pkg.sub`, the main thread raises `_DeadlockError`. Close it before deleting the
   gate. Either import every package `__init__` that a worker can reach on the UI thread before the first
   worker starts (`chisurf.core`, `chisurf.server`, `chisurf.history`, `chisurf.core.project`,
   `chisurf.core.actions`; the session's are already imported by `chisurf.emtk.session`), or measure the window
   with `test_startup_import_race.py`'s `SWEEP` with the gate off. That test's planted package imports itself by
   name, which is a deliberate cycle, so it tests the gate mechanism and is retired with it. Then delete
   `chisurf/_import_gate.py`, its install in `chisurf/__init__.py`, `test/startup/test_import_gate.py` and the
   *gate wait* column.
   **`frame_modules.py` after the gate.** Its only job is to spare a frame the gate's wait. Without the gate, a
   frame waits only when a worker is importing *that same* module, so the list goes with the gate. Until then
   the list can be derived instead of recorded: emtk's lazy imports are its function-level `import` statements,
   so an ast scan of the installed `emtk` package (function-body imports of `emtk.*`, `fontTools.*` and `PIL.*`)
   yields `FRAME_MODULES`. A test would compare the tuple with the scan, so an emtk pin bump that adds a lazy
   import fails it instead of reappearing as a gate wait in `plugin_frame_times`.
6. Measure: (done 2026-10-13) opening a fit window imports no Qt: `test/native_emtk/test_fit_window_is_qt_free.py`
   (subprocess; the full guard `test_opening_a_fit_window_imports_no_qt` passes, xfail removed, and
   `test_every_shipped_page_class_resolves_without_qt` resolves all 24 `PLOT_CLASSES` keys with `qtpy` unloaded).
   What moved: chiplot's core is `chisurf/chiplot/` (panel API `PlotAPI`/`Panel`, handles, styles, backends; no Qt
   at import, guard `test/test_chiplot_core_qt_free.py`), and `chisurf.gui.chiplot` is the Qt host layer (`Plot`,
   `Grid`, `ImageView`, `VolumeView` widgets + a re-export of the core). The page modules moved from
   `chisurf/gui/plots/` to `chisurf/emtk/fit_pages/pages/` (`StateSchemePlot` out of the autoform section into
   `pages/state_scheme_emtk.py`); `emtk_settings.py` (the Qt *Plot settings* dock host) is
   `chisurf/gui/widgets/fitting/plot_settings_host.py`; the Qt-free `glyphs` and `fitting_client` the pages needed
   are `chisurf/core/glyphs.py` and `chisurf/core/api/fitting_client.py`. No shims: every importer was rewritten.
   Parity: the 18 pages of two real fitted IBH fits (`Decay_577D` lifetime, `+577A+GTPgS` Gaussian FRET; every page,
   `chisurf.emtk.fit_report.render_fit_images(pages=None)`) are byte-identical PNGs before and after. Traps: `style`
   parsed colours with `QColor`; the Qt-free `int_color` reproduces `QColor.fromHsvF` only with Qt's own float form
   (`1-(1-f)`) and a rounded `/257` channel reduction (`>>8` and the `qt_div_257` spelling both differ by one on
   about a third of hues). Since the S6-blocker slice (same day) the core names no Qt at all (item 9; source-grep
   guard in `test/test_chiplot_core_qt_free.py`). Rejected, still: making `chisurf.gui.__init__` lazy (tests
   monkeypatch attributes on that module).
7. Measure: whole-window parity, `test/native_emtk/test_emtk_shell_whole_parity.py` against
   `shell_whole_qt_inventory.json`: `KNOWN_GAPS` empty since 2026-10-11 (was 23). The fixture clicks every ribbon
   tab and the Log dock's tabs, as a user does; renamed captions (`?` → ❓ Help, `Language: English` → 🌍 EN, `P` →
   the drawn pin) are `ALIASES`, checked by drawn rectangle. Real-use tests: `test_emtk_shell_whole_gaps.py`
   (`RealisticDriver`: drop, pin, Menu Switch, Log dock, Screenshot, fit export/import, console help). S3's
   `KNOWN_GAPS` is empty too. Fit export is Qt-free (`chisurf/core/fitting/fit_export.py`; pictures drawn by emtk,
   `chisurf/emtk/fit_report.py`; RPCs `fit.export`, `fit.export_all`, `fit.export_existing`, `fit.import`); a fit is
   saved as `<data>.fit.cs.pto` and *Load Fit* adds it. Trap: `.fit.json` from older saves cannot be loaded (it never
   could: the old *Load Fit* looked for `<name>.fit.json.cs.pto`). Open: the shell's undo history is session-local,
   not written into the `.cs.pto`; login before the session (Auth row) is not built; recording/autosave failures
   with two files of one TXT/CSV reader (known issues, 2026-10-11).
   Before-halves: `test/native_emtk/capture_shell_s3_qt_before.py` and `capture_shell_s4_qt_before.py` rewrite
   the S3 and S4 before-halves (`shell_s3_qt_inventory.json`, `shell_s4_qt_inventory.json`; PNGs in
   `renders/w9_s3/`, `renders/w9_s4/`). Run S4 with the env's python directly, not `conda run` (which exited 1
   with no trace once). Trap: the ribbon replaces the Qt menu bar widget, so `QMainWindow.menuBar()` segfaults.
   The scripts read the `.ui`'s own `menuBar` attribute instead.
8. Measure: a file dropped from the OS arrives with no pointer moves (macOS sends none during a drag), so the shell
   routes it by the drop position that emtk now delivers first (`CanvasEvents.files_dropped`, emtk `ee4c76a`), to
   the dock under the pointer, not the one with the keys. `RealisticDriver.drop_files` reproduces it; the imaging
   repro is `test_a_file_dropped_on_a_plugin_dock_goes_to_the_dock_under_the_pointer`. Plugins with only an
   `action` entrypoint run from the shell (`run_plugin_action`; `menu_entries()` now 29 of 29 visible manifests).
9. Measure (branch `s6-retire-qt-shell`): S6 is done there and waits for the owner's merge. `chisurf/gui/` holds
   only data (an import-free `__init__.py`, `i18n/*.ts`, `resources/icons/`); `python -m chisurf` opens the emtk
   shell and `--help` prints the usage without opening a window; `--qt` is gone. Re-derive: `grep -rlE
   '^\s*(from|import)\s+(qtpy|PyQt|PySide|pytestqt)' chisurf | wc -l` (0; guard `test/test_no_qt_imports.py`,
   lazy imports and `emtk.qt_host` included, no allow-list); `grep -v '^#' test/ui_file_allowlist.txt | grep -c .`
   (0). The Qt shell's last control inventory is frozen in
   `okf/plugins/emtk-ports/shell/retire_qt_before.json` (recorded at 0108fa146; no control drift against
   2026-10-11) and `test_emtk_shell_whole_parity.py` passes against it with `KNOWN_GAPS` empty. Before merging:
   (a) `pixi install` (or `pixi lock`) to regenerate `pixi.lock` without qtpy / pyqt / pytest-qt / latexify-py;
   (b) the arm64 env still has PyQt5 and pytest-qt installed, and pytest-qt's plugin then imports Qt at startup
   (`qt_api` is no longer configured) -- run pytest with `-p no:pytest-qt` or uninstall it there; (c) run the
   W7 click-all on the native host (Part D gate 2 of PRD-154 names it), which this branch did not run (machine
   load ~110). Follow-ups recorded in known issues ("Qt-shell leftovers after S6"): the duck-typed main-window
   paths that read `chisurf.cs` (never assigned now) in `macros/core_fit.py`, `macros/core_data.py`,
   `core/actions/project_actions.py`, `core/project/{transition,ui_state}.py`, `server/services/projects.py`;
   `skip_qt_widgets` in the serialisation API; the manifest `gui` entrypoint field; the dead
   `controller_class` key in `experiment_configs.yaml`.
10. Measure: the **Workspace is where the fits live; every tool is a dock** (owner, 2026-10-13: "workspace is
    simply where the fits live, the plugins, ie, the tools go separate all are in docks"). The shell's centre is
    `Region("center", workspace=True)`; its documents are the windows added with `workspace=True` -- the fit
    windows (`fit_docks.open_window`) and *Start*, which fills it while there is no fit. They float inside it
    (clamped back in on resize) or are its tabs, and dock nowhere else. Tile (emtk `tile_grid`, `MIN_TILE`;
    overflow minimized to the strip), Cascade, Tabbed, the Windows list, Ctrl+Tab and *View ▸ Workspace* act on
    them only. Tools, the help browser and the code editor (`main_app.host_in_shell`, via
    `code_links.host_in_open_shell`) open as docks in `TOOL_REGION` ("right", right of the workspace;
    `_tool_region` re-makes it as a split of the workspace when a saved layout lacks it); they dock in any
    other region, float over the whole window, and are never workspace children. emtk enforces the rule
    (`DockWindow.workspace`, `DockManager.admits` / `target_admits`; `dock()`, `add_window()` and `restore()`
    redirect a window asked into the wrong place; emtk `410f791`, `tests/test_docking_workspace.py`).
    Re-derive: `test/native_emtk/test_emtk_shell_workspace.py` (15, one with a real fit; run with
    `PYTHONPATH=~/dev/emtk` until the pin moves past `410f791`). Figures: `docs/manual/figures/main_mdi_*.png`
    (`docs/guides/screenshots/manual_general.py mdi_tiled_and_tabbed`). Deliberate: *Start* is a workspace
    document (it is what the empty workspace shows), so Tile/Tabbed include it while it is open. Tried and
    reverted: (a) tiling by splitting the centre into regions (it multiplied regions and stacked the overflow
    as tabs inside tiles); (b) the 2026-10-13 morning rule "every unbound window lives in the Workspace"
    (tools, help, floated docks as workspace windows), which the owner rejected the same day. Decision on
    native OS windows: glfw has no owned/transient windows, so the help browser and the code editor are docks
    of the shell rather than second processes; the splash is the one separate window (`floating=True`).
    Open: detached docks on a second monitor (a second `NativeHost` sharing one app) stay unbuilt. Trap: a
    headless shell frame (`python -m chisurf --screenshot`, an offscreen canvas) used to build the shell
    persisted and rewrote `~/.chisurf/emtk/emtk_shell.docks.layout.json`; it now uses
    `make_headless_app` (nothing read or written), and `test_python_m_chisurf_opens_the_emtk_surface` runs
    with a scratch `CHISURF_SETTINGS_DIR` and asserts the real file is untouched. Trap: the docs figure
    harness (`docs/guides/screenshots/shell_emtk.py`) sets `docks.confine = False` so a dock can be floated
    anywhere to be cropped; a figure of the Workspace sets it back. emtk `410f791` (and the post-`114a011`
    commits) are local until the pin moves: `git -C ~/dev/emtk log --oneline origin/main..HEAD`.
11. Open: S4 remainders. (a) CJK draws one cell per character, narrowed to it (`emtk/dynamic_font.py`): legible at
    2x, hard at 1x. Two-cell East Asian width changes every painter's `text_width` and the editors' column
    arithmetic, so it needs a decision first. Not a release blocker: ChiSurf ships no Chinese, Japanese or Korean
    catalogue, so only user text (a file name, a typed label) reaches this path. (b) GLFW 3.4 exposes no preedit, so the native window shows the
    composition only in the OS candidate window. On macOS the keys of a composition are held back
    (`emtk.ime.MarkedTextProbe`, `hasMarkedText`); inline preedit needs GLFW's IME API upstream. The browser host's
    DOM composition events are not wired: `emtk/web/boot.js` is another lane's. (c) Deliberate console differences:
    the input is its own box, rich display is written as text, `input()` raises `EOFError`, and Ctrl+C abandons the
    input because a cell runs on the frame. (d) Not done from S4: code_editor's Qt. The Log dock is
    `chisurf/emtk/shell_log.py` over `views/log.view.json` (Logging with Filter / Level / Hide / Clear, RPC Monitor
    with Pause / Clear, History that goes to a step). Measure: `KNOWN_GAPS` in
    `test/native_emtk/test_emtk_shell_console.py` (empty).
12. Measure: the splash on the real launch. `python -m chisurf` with a fresh `CHISURF_SETTINGS_DIR`: the splash
    window draws its first frame about 0.25 s after it opens (before the shell is built), the stages advance
    Registering experiments → Starting the server and its plugins → Connecting → Preparing the
    session, the main window opens when the session worker has ended and the splash closes on the main window's
    first frame. Re-derive with a launcher that patches `SplashApp.draw` / `EmtkShellApp.draw` to log a timestamp
    and captures each window with `screencapture -o -l<NSWindow number>` (glfw `get_cocoa_window` →
    `windowNumber`); never `screencapture` the whole screen (it records the user's desktop). Traps found on the
    real launch, each now a test: (a) `DataDocks.starting` stays true until a *shell* frame adopts the session,
    and the shell is not drawn while the splash is up, so waiting on it hung the splash forever -- the splash
    waits on `session_settled` (the worker ended); (b) macOS reports a window that has just opened (or sits under
    a floating one) as occluded, rendercanvas cancels that frame and never asks again, so the main window stayed
    blank -- fixed in emtk (`NativeHost` asks again); (c) Metal offers `opaque` / `unpremultiplied` only, so a
    transparent surface asked for `premultiplied` fell back to opaque black corners -- emtk now takes
    `unpremultiplied` there (Core Animation composites premultiplied, edges checked at 4x for fringes);
    (d) the art at 2x is 1065 texels wide and emtk's default 1024 image atlas declines it (blank rectangle) --
    the splash surface has its own 2048 atlas; (e) `ShellSession.ensure_global_dataset` never recognised the
    global dataset in the API's records (dicts), so a second call (stage, then the shell's adopt) added a second
    one. Tried and reverted: drawing the splash over the whole main
    window (first version, 2026-10-12): the owner wants the art as a real splash screen, not inside a window.
    Open: Windows/Linux transparency is unverified (glfw `TRANSPARENT_FRAMEBUFFER` + Vulkan `premultiplied`
    should work; where neither mode is offered the window draws opaque with black where the art is clear); no
    taskbar suppression (macOS shows the one Dock icon of the process anyway).


# Traps for slice S2

- The server answers one request at a time, and a fit runs inside one `fit.run` call. The docks therefore make every
  call on a worker (`DataDocks._start`) and re-read their rows only while no call is under way; a read on the frame
  thread during a fit would freeze the window until the fit ends.
- `chi2r` in a fit DTO is the value the last run recorded (`None` before any run, stale after an edit). The Analysis
  dock reads `chi2r_current` from `fit.get`, which evaluates the current parameters.
- ZMQ drops PUB messages a SUB socket joined too late for. `ServerEventSubscriber.start` waits for its connect, but a
  test that publishes once right after starting must publish until the subscriber has queued something
  (`test/core/test_server_events.py::_publish_until`).
- Parameter names repeat across a model's groups: each FCS diffusion preset has its own `N` and `D`, and
  `parameters_all_dict` is keyed by name. The editor therefore addresses a parameter by its uid
  (`ChiSurfAPI.edit_parameter`, `parameter_uid` plus `owner_uid` = the fit), never by name.
- The model's `view.json` is the allow-list of the editor's writes. `model.state.set` sets only attributes a bound
  control declares, and checks fixed options. `model.component.add/remove` takes a `dynamic_group` `target`, and
  `model.action` takes a `button_row` action. A spec without the declaration cannot be written over RPC.
- A model that takes in other fits must take them from its session: `GlobalFitModel` read `chisurf.fits`, so in the
  shell's own `SessionState` its candidates were the Qt session's fits. `fit.create` now sets `fit_pool`.
- `fit.set_dataset` with data of another length broke every residual (`ModelCurve.x` could not broadcast). The
  service now attaches one curve of a one-file group and re-initialises the range, and the model curve takes the new
  length.
- The catalogue guard (`test_committed_authored_ui_text_has_german_and_french_catalogue_sources`) compares
  `git archive HEAD` with the working `.ts`. A string replaced in an uncommitted view stays live (not obsolete) in
  `chisurf_de.ts` / `chisurf_fr.ts` until the replacement is committed.

# Traps for slice S3

- The data docks own their RPC connection, and a ZMQ socket must not cross threads. The project services therefore
  open a second connection to the same server (`ProjectChannel`). The server serialises the two, so a capture made
  during a fit waits for the fit.
- `parameter.set_*` publish no event. The shell records an undo step on `fit.updated`, which the docks' edit is
  always followed by. A capture that equals the last recorded one is not recorded, so the events of an undo's own
  restore do not record a step.
- After `project.load` or `project.restore_payload` the fits are new objects with the old uids, so the docks would
  keep drawing the stale fit. The shell closes every fit window and marks the docks dirty, and the windows reopen
  over the new objects.
- A plugin menu titled like a session menu (the File tools under "File") is merged into that menu. Two `begin_menu`
  calls with one label share an id.

# Traps for slice S4

- A popup menu's rows are drawn by an overlay after the frame, so `im.get_item_rect()` after `im.menu_item` in a
  popup returns the menu title's rectangle: `item_rects["menu.<key>"]` is not where the row is. A test clicks a menu
  row by its caption (`driver.click("Record")`).
- Keyboard navigation takes Tab before the application sees it. A hosted control gets it only with `wants_tab = True`
  (the console completes with it); `im.text_editor` sets the same flag for itself.
- The console calls the session on the frame thread, and the docks call it on workers: it needs a ZMQ connection of
  its own (a socket must not cross threads).
- `Driver.type` sends one key per character with the character as text; a `"\n"` types nothing in a `TextEditor`.
  Put a multi-line cell in with `ShellConsole.set_input` and press Return.

# The shell today (Qt) and the emtk equivalent

Each row is one capability the shell uses. Evidence is given as `file:line`. "emtk" names what already exists and
"gap" names what still has to be built. The test column names the guard that proves the row.

| Capability | Qt today | emtk equivalent | Gap | Slice | Test / guard |
|---|---|---|---|---|---|
| Main window, chrome | `gui/main.py:126` `Main(QMainWindow, …mixins)`; `uic.loadUi(gui.ui)` at `main.py:1127`; `closeEvent` order at `main.py:425-477` | `EmtkShellApp` (`chisurf/emtk/main_app.py`) on `emtk.native.NativeHost` | save setup defaults on close | S1 skeleton, S3 close guard done | `test/native_emtk/test_emtk_shell.py`, `test_emtk_shell_session.py::test_the_close_guard_asks_once` |
| Central area | `QMdiArea mdiarea` (`gui.ui:44`), Tile, Tab and Cascade (`main.py:557-568`) | `emtk.docking.DockManager` centre region: tabs, split, float | tile and cascade arrangements (split presets are enough) | S1 / S2 | same |
| Docks | 6 `QDockWidget`s in `gui.ui`: Analysis :82, Plot :193, Console :342, Datasets :403, Logging :509, Read data :584; default tabified at `main.py:1490-1514` | `DockManager` regions; Read data, Datasets, Analysis, Plot settings are `chisurf/emtk/fit_docks.py` over `chisurf/emtk/views/*.view.json`; the model editor `chisurf/emtk/model_editor.py` over `model.editor`; controller dialogs `chisurf/emtk/fit_controls.py`; reader sections `chisurf/emtk/detector_cascade.py`; sample question `chisurf/emtk/sample_picker.py` | — (curve pickers and custom sections: `chisurf/emtk/model_sections.py`; PDA reader: `chisurf/emtk/pda_sections.py`); Console in S4 | S2 done (control parity), S4 | `test/native_emtk/test_emtk_shell_fits.py`, `test_emtk_shell_readers.py`, `test/server/test_model_editor_service.py` |
| Layout persistence | QSettings ("ChiSurf","MainWindow") `geometry/state/layout_version` (`main.py:330-369`); `gui/layout_state.py` | `chisurf.emtk.state.attach_native_state` → `<settings>/emtk/emtk_shell.{layout,window,settings}.json` | — | S1 done (open plugins reopen) | `test_restore_reopens_the_plugins_that_were_open` |
| Ribbon | `widgets/ribbon/**` (22 files, about 6,600 lines); `display_name` "Tab:Group:Name"; QSettings RibbonState | `emtk.ribbon.Ribbon` via `chisurf/emtk/shell_ribbon.py`: tabs, groups, large and small icon buttons, tooltips, collapse then overflow at narrow widths, search, fold toggle, help and language buttons | fold state is not persisted (the Qt pin is) | S5 done | `test_emtk_shell_ribbon.py` (vs `shell_s5_qt_inventory.json`), emtk `tests/test_ribbon.py` |
| Toolbar plugins | `main.py:944-1044` `plugins.toolbar_plugins`; `gui/plugin_toolbar.py` | the ribbon's *Main ▸ Window* group (the toolbar's window actions, *Screenshot* through `emtk.export` and `clipboard.copy_image`) | `plugins.toolbar_plugins` entries | S5 partial | `test_a_session_button_runs_its_action` |
| Plugin menus | `gui/__init__.py:850-1104` `populate_plugins` (disabled, order, experimental, `menu_hidden`, `cli_only`) | `shell_ribbon.menu_tree` over the ribbon's `plugin_layout` (`disabled_plugins`, `plugin_order`, `cli_only`, maturity markers), icon column in every menu row (emtk `MenuItem.icon`), the Tools dock a tree with a filter | Dev menu | S5 done | `test_the_tools_tree_follows_the_ribbon_and_filters` |
| Plugin launch | `misc_helpers.run_plugin_from_dir` → `registry.build_plugin_widget` → `qt_host.ControlHost(factory())`, a separate top-level window | `load_plugin` on a `BackgroundBuild` worker, drawn with `ImApp.draw_child` inside a dock | `action` entrypoints; macro or wizard `__init__.py` plugins | S1 done | `test_a_hosted_plugin_gets_its_clicks_and_keys_and_closes_with_its_window` |
| Fit windows | `main.py:2058-2125` `_open_fit_subwindow` → `FitSubWindow(CustomMdiSubWindow)`; the content is already `FitPlotsArea` → one `ControlHost(FitWindowSurface)` | `chisurf/emtk/fit_window.py`: the same `FitWindowSurface`, one dock window per fit; the active fit tab drives the Analysis and Plot settings docks | — (the Code face is the same `FitCodeFace`, writes through `model.code.apply`) | S2 done | `test_load_fit_edit_and_run_through_the_api`, `test_the_model_editor_is_the_models_view_json_written_through_the_api` |
| Server events | `gui/zmq_poller.py:36` 50 ms QTimer → `_on_server_event` (`main.py:1855`) | `chisurf/core/server_events.py` `ServerEventSubscriber`: a worker owns the SUB socket and calls `request_frame`; the shell drains on its frame | — | S2 done | `test/core/test_server_events.py`, `test_a_fit_made_elsewhere_opens_its_window_from_the_event` |
| Dialogs | `ChiSurfMessageBox` (`gui/dialogs.py:146`): `main.py` 13, `main_helper.py` 20, `gui/__init__.py` 11 sites, ribbon 6; `QInputDialog` ×2 (`main_helper.py:500/512`); custom `QDialog`s (FRET RDA axis `main.py:1686`, Data loading `:1715`, `LoginDialog`, `PasswordChangeDialog`, `SaveProjectDialog`, `CollisionDialog`) | `emtk.message_dialog.MessageDialogs` (message, confirm, choice, text; `auto_answer`), `emtk.dialog_window.DialogWindow`, AutoForm view.json forms (`chisurf/emtk/views/save_project.view.json`) | the FRET RDA axis and data-loading dialogs moved to specs; LoginDialog, PasswordChangeDialog | S3 done, S5 | emtk `test_message_dialog.py`, `test_emtk_shell_session.py::test_parity_with_the_qt_project_dialogs` |
| File dialogs | `widgets/general.py:427-519` wrappers; `main_helper.py` 4 sites; `main.py` 3 | `emtk.file_dialog.FileDialog` (open, save, folder, filters, multi-select) | — | S3 | emtk `tests/test_file_dialog.py` |
| Drag and drop of files | `label_filedrop` event filter (`main.py:1179`, `:1276-1312`) → `dataset.add` | `NativeHost` glfw file drop → `on_files_dropped`: the focused child first, else read with the selected file type | — | S2 done | `test_a_file_dropped_on_the_shell_is_read` |
| In-app drag and drop | dataset selector `drag_enabled` (`main.py:1208`) | `emtk.widgets.dragdrop` (one context per host) | dragging between two OS windows (a dataset row onto a fit window is done: emtk table `drag_call`) | S2 done | emtk `test_ui_data_table_drag.py`, `test_a_dataset_dragged_onto_a_fit_window_is_attached_to_that_fit` |
| Keyboard shortcuts | `gui.ui` actions and `configure_project_shortcuts` (`main.py:53-62`), ApplicationShortcut | `EmtkShellApp.shortcuts()` from the session menus, run before keys reach the focused child | `Ctrl+Alt+S` (fit export, resume item 7) | S3 done | `test_the_session_menus_bind_the_qt_shortcuts` |
| Console | `cs.console = QIPythonWidget(chinsole.Chinsole)` (`gui/__init__.py:589`), `gui/chinsole/**` (8 files, 3,462 lines, `QTextEdit`); the engine `chisurf.core.console` is Qt-free | `chisurf/emtk/console.py` (`ShellConsole` on `TextEditor`, hosted by `im.host_control`); *Macro ▸ Record / Run Macro…*; `chisurf.run` / `chisurf.log` / `chisurf.console` while the shell is open | rich display as text, `input()` (resume item 12) | S4 done | `test/native_emtk/test_emtk_shell_console.py` (25 behaviours vs `shell_s4_qt_inventory.json`) |
| Logging dock | `plainTextEditLog` and filter, `_LogRelay` timers (`gui/__init__.py:192-374`) | S1 Log dock (`_LogBuffer` handler) | level filter, history browser | S1 partial, S4 | — |
| Status bar | `TruncatingStatusBar` (`main.py:1216-1248`), progress bar, `StatusBarProgressHost` | `chisurf/emtk/status_strip.py`: message or *Ready*, the operation's text, bar (sliding when unknown) and ✕ | — | S5 done | `test/native_emtk/test_emtk_shell_status_strip.py` |
| Splash | `SplashScreen(QSplashScreen)` (`gui/__init__.py:443`) over `icons/splashscreen.png` | `chisurf/emtk/splash.py`: its **own** frameless window (`NativeHost(decorated=False, floating=True, transparent=True, centred=True)`, emtk 93bc456), the art at 2x (`chisurf/emtk/splash.png` from the SVG, its own 2048-texel image atlas), transparent where the art is; progress bar, stage, last log line, copyright, version, licence, contributors drawn on the art where the Qt splash puts them; the main window opens when the session has settled and the splash closes on its first frame. A separate window, not a cover inside the main one: the art is a shaped splash *screen* (owner, 2026-10-12) | — | S5 done | `test/native_emtk/test_emtk_shell_splash.py`, emtk `tests/test_native_splash_window.py` |
| Startup services | `AppStartupServiceManager` stages in `startup/services.d/20_gui_splash.json`, `30_gui_post_show.json` | the `surface="emtk"`, `phase="splash"` set `services.d/25_emtk_splash.json` (experiments, server and its plugins, connect, global dataset) run by the same manager inside `chisurf.emtk.session.start_session` on the session worker (the imports are not a stage: `chisurf.emtk.session` imports the server at module level, before the worker starts); `on_stage_start` feeds the splash; the post-show set `35_emtk_post_show.json` is the update check | `populate_plugins` has no counterpart (the shell reads manifests in its constructor); `warmup_imports` has none on purpose (item 5) | S5 done (splash phase) | `test_the_session_reports_the_declared_stages_in_order`, `test/startup/test_services.py` |
| Auth | `LoginDialog`, deferred `_run_startup_auth` | `switch_user` emtk plugin | modal login before the session | S3 open (resume item 7) | — |
| Translation | `QTranslator` (`gui/i18n.py:343`); `retranslate_from_ui(self, gui.ui)` re-reads the `.ui` (`gui/retranslate.py`) | `chisurf.emtk.i18n` reads the same `.ts`; `emtk.i18n.tr` applies on the next frame | none: an immediate-mode shell retranslates by drawing | S1 done | `test/native_emtk/*translations*` |
| Tooltips | Qt tooltips and `install_tooltip_wrapping` | `emtk.tooltip` | — | S1 done | emtk `test_tooltip.py` |
| Clipboard | Qt | `emtk.clipboard` (glfw/platform) | — | done | emtk `test_clipboard.py` |
| DPI and export | Qt scaling, `widget.grab()` | `NativeHost` ratio, `emtk.scaled_painter`, `--screenshot` | — | done | `test_emtk_shell_flag_opens_the_emtk_surface` |
| Multi-window | every plugin is its own top-level Qt window | one `NativeHost` per process; fit windows are the documents of the **Workspace** (centre region, emtk `workspace=True` on region and window): Tile / Cascade / Tabbed / Windows, minimize strip, Ctrl+Tab, clamped, persisted; every tool, the help browser and the code editor is a dock (tabbed right of the Workspace, dockable elsewhere, floating over the window), never a Workspace window and never a second process | **gap**: a second OS window sharing one app (detached docks on a second monitor) | Workspace done; second monitor open | `test/native_emtk/test_emtk_shell_workspace.py`, emtk `tests/test_docking_workspace.py` |
| Text input, IME | Qt `inputMethodEvent` | `emtk.ime`: commits as typed text, preedit in `io.preedit` drawn at the caret of `input_text`, `TextEditor`, `TextField`; `qt_host.inputMethodEvent`; native holds back a composition's keys (`MarkedTextProbe`) | inline preedit in the glfw window, the browser's composition events (resume item 12) | S4 done | emtk `tests/test_ime.py`, `test_emtk_shell_console.py::test_composed_input_types_into_the_console` |
| Molecular viewer | chimol `hosts/qt` | chimol native host (`ChimolApp`), hosted by `chisurf.plugins.chimol.app` | none (`hosts/qt` deleted in chimol a53e512) | S7: done 2026-10-13 | `chisurf/plugins/chimol/test/` (native), `test_emtk_chimol_parity.py` |
| Watermark, sparkline | `widgets/system_info_watermark.py` | chiplot or `emtk.implot` | — | S5 (or drop) | — |

# Allow-list by area and the slice that removes it

`test/test_plugin_qt_free.py` fails on any `qtpy|PyQt|PySide` import under `chisurf/plugins/**` that is outside the
**shrinking** `test/plugin_qt_allowlist.txt`. It also fails when an entry no longer imports Qt. Role counts below come
from a regex heuristic, not a manual review: host = mentions `ControlHost`, `qt_host` or `EmtkEmbed`; widget =
defines a Q* class; test = lives under a `test(s)/` directory.

| Area | Lines | Host | Widget / dialog | Test | Other | Removed by |
|---|---|---|---|---|---|---|
| chimol | 4 (111 before 2026-10-13) | 0 | 0 | 3 + 1 capture script | 0 | S7: tests on the native host (done); the 4 Qt captures/prompt go when chimol drops `hosts/qt` (item 1) |
| core / mmfdb_admin | 0 (30 before 2026-10-13) | 0 | 0 | 0 | 0 | done: the Qt window retired, its tests on the emtk app |
| core / code_editor | 12 | 1 | 6 | 4 | 1 | S4: the console and editor share `TextEditor` |
| core / acq | 9 | 0 | 4 | 1 | 4 (device wrappers that use Qt signals) | S5: device wrappers move to plain callbacks or `emtk.tasks` |
| core / help | 8 | 1 | 3 | 4 | 0 | S5: the Qt help `gui/tool.py` is deleted, since the native help browser exists |
| core / project_browser | 4 | 0 | 1 | 3 | 0 | S3: `SaveProjectDialog` and `CollisionDialog` move to emtk |
| core / globalview, lightpath_simulator | 6 | 2 | 2 | 2 | 0 | S1 follow-up: their Qt `gui` entrypoint becomes redundant once the shell docks the emtk twin |
| core / f_test, setup_channel_definition, batch_analysis, switch_user, updater | 7 | 0 | 2 | 5 | 0 | S3 / S5 |
| misc / games | 20 | 0 | 5 | 9 | 6 | S5: emtk twins exist (W6f); delete the Qt games |
| microscopy | 7 | 1 | 0 | 6 | 0 | S2: port the tests to `Driver` |
| modelling / hydropro | 7 | 0 | 2 | 4 | 1 | S5: AutoForm port |
| ndxplorer | 6 | 1 | 1 | 3 | 1 | S2: ndX docks in the shell (`window.py` host) |
| spectra_downloader, fret_line | 6 | 0 | 6 | 0 | 0 | S5 |
| tttr | 4 | 1 | 0 | 3 | 0 | S2 |
| plugins root, calculator, quenching_estimator, vv_vh_anisotropy, cookiecutter | 8 | 0 | 0 | 5 | 3 | S5; `plugins/__init__.py` and `icon_utils.py` go with the Qt menus in S6 |

# Slices

Each slice keeps the Qt shell as the default until S6. A slice is accepted only on **control parity**, following the
[testing workflow](../workflows/testing.md):

1. grab the Qt shell area **before** the code changes, in a realistic state;
2. grab the emtk equivalent in the same state;
3. enumerate the controls in the before-image (`test/gui/migration_parity.py`);
4. confirm that each one is present and reachable in the after-image, and write down the deliberate differences.

A missing control blocks the slice.

- **S1 (done, 2026-10-11): skeleton.**
  - `chisurf/emtk/main_app.py`, reached with `python -m chisurf --emtk-shell`. The module does not import Qt (a
    guard test checks this).
  - Menu bar from manifests, plus Tools, Start and Log docks.
  - Plugins open as dock windows, built on worker threads. Input is routed to the plugin under the pointer, and keys
    go to the plugin pressed last.
  - Closing a window with `×` closes the plugin.
  - Layout, size and the list of open plugins persist.
  - Screenshot: `test_real_plugins_render_inside_the_shell` writes `emtk_shell.png` (About and Calculators docked).
- **S2 (control parity, 2026-10-11): data and fits.**
  - Read data (experiment, file type, file, Browse…, Load example, + Data, the reader's native settings), Datasets
    (datasets and fits tables, Model, + Analysis, Remove dataset, rows dragged onto a fit window), Analysis and Plot
    settings docks: `chisurf/emtk/fit_docks.py`, specs in `chisurf/emtk/views/`.
  - Analysis = the fit controller (Fit, MCTS, Sample, ⚙, auto, …, Remove fit, Dataset, Result, First/Last and the 2-D
    pair, Local first, Search fit settings) and the model's own editor (`chisurf/emtk/model_editor.py`): the server
    resolves the `view.json` against the model (`model.editor`); choices write `model.state.set`, cells
    `parameter.*` by uid, *add*/*del* `model.component.*`, buttons `model.action`. The equation is typeset
    (`emtk.im.math`), labels draw sub/superscripts (emtk table column `display: "script"`).
  - Fit windows as `FitWindowSurface` docks with a *Code* / *Plots* strip: `chisurf/emtk/fit_window.py`; the Code face
    is `FitCodeFace` over `model.code.files` / `model.code.apply` (only the model folder's files are written).
  - Controller RPCs: `fit.model_search(.available)`, `fit.set_grid_range`, `fit.run(local_first)`, plus the existing
    `fit.range.auto`, `fit.set_result_idx`, `fit.set_dataset`, `fit.sample.*`, `fit.group.select_member`. Dialogs
    (⚙ settings, `…` dataset picker) in `chisurf/emtk/fit_controls.py`; the settings model moved Qt-free to
    `chisurf/core/fitting/optimization_settings.py`.
  - The session: an in-process `ChiSurfServer` on free ports, `ChiSurfAPI` in `server` mode, events through the
    Qt-free `ServerEventSubscriber` (`chisurf/emtk/session.py`, `chisurf/core/server_events.py`). It adds the Global
    Dataset on adoption; a *Global fit* takes its local fits from the session (`GlobalFitModel.fit_pool`).
  - Readers: 23 of 24 have a native form (the detector cascade and ICS ROI in `chisurf/emtk/detector_cascade.py`,
    the TCSPC simulator's own app, new specs for DEER, three-colour PDA and the global-fit reader). A measurement
    reader (`asks_sample`) asks for the MMFDB sample after Browse (`chisurf/emtk/sample_picker.py`).
  - Dropping a file onto the shell reads it. *Load example* writes `chisurf/core/experiments/fcs/demo.py`'s curve
    (one species, N = 2): the headless test fits it back to N = 2.00 at χ²ᵣ ≈ 0.88.
  - Parity: before-half `test/native_emtk/shell_s2_qt_inventory.json` (made by
    `test/native_emtk/capture_shell_s2_qt_before.py`; PNGs in `renders/w9_s2/`), compared in
    `test_parity_with_the_qt_docks`; `KNOWN_GAPS` is empty. Deliberate differences: MDI minimise/maximise become dock
    float/tab/close; the fit window's `×` kept the fit until S3 (it now asks and removes it, as in Qt); *+ Data* reads the File field (Browse… opens the dialog) instead of opening a dialog at once; the dataset
    context menu's remove is a *Remove dataset* button and Delete in the table; check boxes instead of
    `true`/`false` cell text; `N/A` instead of `nan`; resume item 4.
  - Fixed on the way (Qt shell too): *Local first* never reached the run; `fit.set_dataset` with a curve of another
    length; `dataset.group` over RPC raised; the global fit's *Remove*; the global fit listing itself as a
    candidate; a fit range starting at lag 0 on a log axis drew an infinite region; the DEER reader had no settings.
  - Not yet: removing the microscopy, tttr and ndxplorer test lines (resume item 5).
- **S3 (control parity for the session menus, 2026-10-11): session.**
  - `chisurf/emtk/shell_session.py` (`ShellProject`). *File*: Add dataset (`Ctrl+N`), Save Project (`Ctrl+S`),
    Export Project… (`Ctrl+Shift+S`, save as), Open Project…, Import Project…, Close Fit, Close all fits, Close
    Project, Reinitialize (`Ctrl+R`), Recent Projects, Quit (`Ctrl+Q`). *View*: the dock toggles, Tile, Tab and
    Cascade, Reset Layout, Undo (`Ctrl+Z`) and Redo (`Ctrl+Y`). *Settings*: Edit (the Settings tool), FRET RDA
    axis…, Data loading…, and the four resets. A plugin menu with a session menu's title joins it.
  - Project files go through `project.capture`, `project.load`, `project.restore_payload` and `session.restore`
    with `chisurf.core.project.storage`. The document baseline is `ProjectDocument`, as in the Qt shell. On a
    configured MMFDB deployment the Save Project form (`views/save_project.view.json`) saves versions and
    *Import* asks the collision question, through the new Qt-free `storage.database_client`, `import_preview` and
    `import_database`, which the Qt shell now calls too. The recent list is `chisurf/core/project/recent.py`,
    shared with the Qt shell.
  - Undo and redo use an `OperationHistory` of the shell's own (`step_target` added), captured and published
    through the server.
  - The close guard asks once: Save / Don't Save / Cancel for unsaved work, "Quit ChiSurf?" for an empty session
    (`gui.confirm_close_program`), nothing for a saved one. It covers *Quit*, the window's close button (emtk
    `Surface.on_close_request` / control `close_request`), Open, Close Project and Reinitialize.
  - Autosave runs on the frame clock (`next_frame_in`), with the Qt settings and target.
  - The fit window's `×` asks, then removes the fit (`gui.confirm_close_fit`; off, it only closes the window).
  - Dialogs: `emtk.message_dialog` (emtk `5e8223c`).
  - Parity: before-half `shell_s3_qt_inventory.json`, compared in `test_emtk_shell_session.py`. Deliberate
    differences: Qt's submenus Project, Fits, Recent Projects and Docks are captioned sections; `...` is `…`; the
    dock toggles carry the docks' own titles (Dataset → Read data, Fit → Analysis, Plot-options → Plot settings);
    the empty Qt Designer submenu "Type Here" is gone; `Ctrl+F4` (Qt's MDI system menu) has no counterpart.
  - Fixed on the way: `Ctrl+L` was bound to a `gui.ui` action with no handler and in no menu, and the action is
    deleted. The Qt MMFDB import built two clients for one import; it now builds one. The data-loading settings
    model and its spec moved out of the Qt module (`chisurf/core/fio/staging_settings.py`). `apply_fret_rda_axis`
    is now Qt-free.
- **S4 (control parity with the Qt console, 2026-10-11): console, macros, IME.**
  - `chisurf/emtk/console.py`: `ShellConsole` (engine, transcript, history walk and search, completion list, calltip,
    pager, kill ring, session log, macro recording) and `ConsoleControl` (transcript, pager and input `TextEditor`s
    in one hosted control). Namespace `cs`, `gui` (the shell), `np`, `os` and `api`, the session's `ChiSurfAPI` on
    a connection of the console's own (`ProjectChannel`). The Qt-free console settings moved to
    `chisurf/core/console/settings.py`; the guide and help are the Qt console's files.
  - The shell: a Console dock beside Log, a *Macro* menu (Record, checkable; Run Macro…) through the shell's file
    dialog (`ShellProject.open_file_dialog(filters=...)`), console chords win over the menu shortcuts while it has
    the keys, `chisurf.run` from any thread runs in the console on the next frame and records `run command: …` in
    `chisurf.history` and as the next undo step's name (`ShellProject.note_command`).
  - emtk: `emtk.ime` (commit as text, preedit, `MarkedTextProbe`, `committed_text` keeps the zero-width joiner),
    `Surface.on_text_compose`, `ImApp.compose` / `ime_caret`, `Driver.compose` / `commit`, `qt_host` input method,
    `host_control` forwarding `compose` and giving Tab to a control with `wants_tab`; rasterised glyphs inside their
    advance (CJK overlapped its neighbours).
  - Parity: before-half `shell_s4_qt_inventory.json` (25 behaviours driven with keys, the console dock inventory,
    the Macro menu), compared in `test_parity_with_the_qt_console`; `KNOWN_GAPS` is empty. Deliberate differences:
    resume item 12 (c); *Run Macro…* is new (the Qt shell ran macros from the code editor).
  - Fixed on the way (Qt shell too): the Qt console's Up kept the old prefix after a walk back to the draft, so
    "pri" + Up recalled the last line (`Chinsole.walk_history`, test `test_a_new_walk_filters_by_what_is_typed_then`);
    in the emtk shell `chisurf.run` was the identity function, so every `cs.run(...)` macro line did nothing.
  - Not yet: code_editor's Qt, the Log dock's filter (resume item 12 (d)).
- **S5: ribbon, toolbar, status, startup.**
  - Done 2026-10-11: the ribbon (resume item 5), the plugin menus and Tools tree from the same layout, every plugin
    manifest carrying an icon (`test/plugins/test_plugin_icon_manifest.py`: every non-library manifest has one,
    listed plugins have distinct ones), the language switch (`chisurf.emtk.i18n.choose_language`).
  - Open: toolbar plugins, status strip, `surface="emtk"` startup stages.
  - Delete the remaining Qt plugin tools (games, help, mmfdb_admin, hydropro, spectra_downloader, fret_line).
- **S6 (done on branch `s6-retire-qt-shell`, 2026-10-14): switch and delete.** Record in "History".
  - `python -m chisurf` launches the emtk shell.
  - Delete `gui/main.py`, `main_helper.py`, `gui.ui`, `retranslate.py`, the ribbon, `widgets/tools/**` and
    `gui/chinsole/**` Qt views.
  - Strike `qtpy`, `pyqt` and `QT_API` from `pixi.toml`.
  - Gate: W7 click-all is green on the native host, and startup is no slower than the Qt baseline.
- **S7: chimol.** Drop `hosts/qt`, and port the 110 chimol tests to the native host.

# History

Slice records moved out of "Where to pick this up" on 2026-10-14, unchanged except for re-wrapping; the
resume items now carry only the current measurement.

**S6, the Qt shell retired (2026-10-14, branch `s6-retire-qt-shell`, not merged).** Before anything was deleted,
the whole Qt main window was captured one last time (`capture_shell_whole_qt_before.py` at 0108fa146, offscreen,
scratch settings): no control added or lost against the 2026-10-11 record, three ribbon tooltips follow edited
manifests. Frozen in `okf/plugins/emtk-ports/shell/retire_qt_before.json`; `test_emtk_shell_whole_parity.py`
4 passed against it, `KNOWN_GAPS` empty, so no control had to be added to the emtk shell first. Deleted: 309
tracked files under `chisurf/gui/` (the Qt main window `main.py`, `main_helper.py`, `gui.ui`, the ribbon, the Qt
AutoForm renderer and its sections, every Qt widget, the Qt console `chinsole`, the `chiplot` Qt host layer, the
legacy chigame engine and its five Game adapters, `.qm` catalogues, `.qss` style sheets, compiled resources),
`startup/gui_services.py` with `services.d/20_gui_splash.json` / `30_gui_post_show.json`, `macros/plugin_check.py`
(an unused Qt plugin runner), the plugin registry's Qt launch path (`build_plugin_widget`,
`select_gui_entrypoint`, `_show_plugin`, `apply_manifest_statefulness`, `register_gui`), every plugin's
`if __name__ == "plugin":` Qt launch block, the Qt hosts left in plugins (code_editor, help, quenching_estimator,
`trace_browser/__plugin__.py`, `create_host` of microtime_histogram and vv_vh_g_factor, the tttr_to_pto drop
guard, `setup_channel_definition/wizard.py`). Moved, being Qt-free and used: `autoform/state.py` ->
`chisurf/core/dataspec/form_state.py`, node-editor `validation.py` -> `chisurf/emtk/node_editor/`, its three
tests -> `test/node_editor/`, the console's `guide.json` / `help.md` -> `chisurf/core/console/`, globalview's
`FittingClientParamMutator` -> `plugins/core/globalview/gui/parameter_mutator.py`. Made Qt-free in place: the
experiment bootstrap (no QApplication, `allow_widgets` removed; `controller_class` entries null), the reader's
sample prompt (the shell's picker asks; files stay in `_pending_sample_files`), the agent CLI and ACP server
(`--no-qt` gone), `doc_links` / `code_links` (emtk routing only), `node_editor.style_settings.refresh_open_graphs`
(walks the shell's hosted apps), the env bootstrap (no Qt plugin path, no vispy backend), the settings (no style
sheet). One live path needed a native replacement: the CSV reader's *G-factor…* opened the calculator in a Qt
host window; it now asks the shell for a dock through the new `reader_calibration` hand-off of `vv_vh_g_factor`
(`chisurf.emtk.reader_settings.receive_reader_calibration`) and applies G, VH shift and mixing when it closes
(`test/native_emtk/test_csv_reader_settings.py`, 5 passed). The model/view boundary's four `KNOWN_LEAKS` closed
(`test/architecture/test_model_ui_boundary.py`, register now empty). Dependencies struck: qtpy, pyqt, sip,
pytest-qt, `qt_api`, `QT_API` / `QT_QPA_PLATFORM` task env, the Qt mypy override, the `i18n-compile` (lrelease)
task, and latexify-py (its only importer was the Qt parse-model widget). The translation extractor
merged through Qt's `pylupdate5`; the merge is now Python (`build_tools/i18n/extract_strings.py::merge_catalogue`,
tested; no catalogue regenerated). The Qt `init_setups` fallback for a stale `global` reader moved into the
bootstrap (`test/agent/test_bootstrap.py`). Tests: Qt-only tests retired, behaviour
tests ported to the emtk apps or the Qt-free API; the list is in the branch's commit bodies. Verified with Qt
blocked by a meta-path finder: `import chisurf`, `python -m chisurf --help`, a headless shell frame (inspected),
`test_emtk_shell.py` 11 passed, and the guard files one at a time.

**Plugin Qt allow-list, 244 → 0 (former item 1).** Measure: the allow-list is **empty** since the mmfdb_admin slice (2026-10-13; 30 entries at chisurf 7e0514d95, all mmfdb_admin, 33 at 96d3b6f1d, 52 when the ndX/chimol-leftovers slice started,
64 before the parallel 2026-10-13 slices, 171 before the chimol slice, 184 before the Trace Browser host went
(186 before that), 210 before the 2026-10-13 leftovers slice, 211 before the S6-blocker
slice, 221 before the 2026-10-13 slice, 244 before the 2026-10-12 test-port slice). Re-derive with
`grep -v '^#' test/plugin_qt_allowlist.txt | grep -c .`; per area `grep -v '^#' test/plugin_qt_allowlist.txt |
cut -d/ -f3 | sort | uniq -c`: 0 everywhere. `test/test_plugin_qt_free.py` now rejects any Qt import under
`chisurf/plugins/`.
**mmfdb_admin slice (2026-10-13, 30 lines → 0).** The Qt `MMFDBWidget` (`gui/tool.py`, 7078 lines), its mixins,
entity/metadata docks, generic form, AutoForm entity form, login dialog, the six workflow views, eLabFTW view and
the optical-component dock/detail form/duplicates dialog/SpectrumView shim are deleted; the manifest names only
`entrypoints.emtk`. Evidence: the Qt half re-captured live before any change (459 controls,
`okf/plugins/emtk-ports/mmfdb_admin/retire_qt_before.json`), an audit of every *reachable* Qt action against the
twin (no backend call lost), and the after inventory (`retire_compare.json`). What the twin lacked was added, not
explained away: Enter in a connection field logs in, Enter in the eLabFTW search lists, Spectra search as you type
with **Auto**, the Spectra row menu (Open details, copy row/cell, check/uncheck selected, select all, clear
selection), Find Duplicates progress + Cancel, a click on a provenance **edge** shows its record (a node click
showed nothing either: the payload is a dict), the entity row's UUID on hover, the rail pictograms, **Open in ndX**
on Processed Products (`open_in_ndx` + `record_burst_ids_against_product`, hidden in Qt), and **Demo data…** (the
Qt ten-clicks-on-the-header population, never wired). Every Qt widget test (12 files, ~70 tests) is ported to the
app and the emtk Driver; `test/gui/test_mmfdb_demo_captions.py` too. Found and fixed at the root: emtk forms shared
widget ids across forms (toolbar `import_file` swallowed the panel's *Import file* press; emtk 0.1.12 scopes ids
per `FormState`), emtk value fields had no Enter action nor search-as-you-type (`enter_call`, `live`, emtk 0.1.11),
mmfdb read stored spectra bytes with `json.loads` so export validation failed for any sample with a measured
spectrum (mmfdb 2180b1a), and the twin then skipped validation silently (now it says so and asks).
Deliberate differences: the entity table's live filter has no *Auto* toggle (the emtk filter is client-side), and
window geometry is the host's (the app keeps the panel and its splits).
**ndX + chimol leftovers slice (2026-10-13, 8 lines → 0).** *ndX*: ChiSurf's Qt `NdxWindow`
(`plugins/ndxplorer/window.py`, the app in a `ChisurfDockTool`) is deleted; the manifest names only
`entrypoints.emtk` (`gui/app.py:make_app`) and declares window statefulness, so the `--qt` shell hosts the app
generically (`build_plugin_widget` → `ControlHost`) and keeps its geometry. What the window added is Qt-free:
`open_in_ndx` / `show_table_in_ndx` (hand-off in the emtk shell, else the open app, else the ChiSurf window
opens the plugin), `selection_provenance.record_burst_ids_against_product` (the MMFDB admin's *Open in ndX*),
close-on-host-detach and the Global View slot (already `make_app`'s). `find_ndx_windows` returned nothing for
the Qt window (it looked for `constants`/`data_source` on top-level widgets), so Accurate FRET's *Load from /
Push to ndX* never found it; it now returns the `"ndx"` session sources. Before/after on ndX's MFD fixture
(12237 bursts): 66 drawn / 39 interactive controls equal (`okf/plugins/emtk-ports/ndxplorer/retire_*`).
*chimol*: the display-defaults prompt is chimol's in-viewport question (`chimol.ui.dialogs.choice` +
`display_defaults`, chimol 19444d1), asked by `ChimolApp.run` and by ChiSurf's `make_app`; before/after in
`okf/plugins/emtk-ports/chimol/retire_prompt_*` (every control present; no icon, singular grammar, ASCII
arrow). `screenshot.py` grabs the offscreen canvas (`grab_window` / `grab_view` / `save_png`, refuses uniform
images); `chrome_baseline.capture` paints through the `QuadPainter` + `quad_raster` into `renders/chrome_quads`
and keeps `renders/chrome_baseline` (the QPainter half, byte-checked against the live QPainter just before) frozen;
the reachable-control inventory test passes against it. Both chimol benchmarks and `test_occlusion_switch`
(which had always skipped offscreen) run on `ChimolApp`.
**chimol slice (2026-10-13, 111 → 4).** The 110 test files under `chisurf/plugins/chimol/test/` drove
`chimol.hosts.qt.MolViewPluginWindow` (or a Qt-bound `Viewer()`) and pumped a `QApplication`; they now drive the
toolkit-free host every embedder uses -- `ChimolApp` on the offscreen canvas -- through the helper
`chisurf/plugins/chimol/test/native_window.py` (`NativeWindow`, `native_viewer`, `process_events`): pointer
events go to the renderer's `on_pointer_press/move/release` (what emtk's `CanvasEvents` delivers), wheels to
`on_wheel`, frames come back from `draw_frame`. Mouse selection runs for real (25 tests: click, ctrl-shift click,
shift box, middle box, pan, pivot). The Qt *window* went with them: the manifest has no `gui` entry, both shells
open `app:make_app` (the `--qt` shell hosts it in a `ControlHost`) and `chisurf/plugins/chimol/__init__.py`
imports no Qt. Before/after (148L, 1RTD, 1200x800; Qt half from a worktree of chimol `b2a3f2b`) in
`okf/plugins/emtk-ports/chimol/retire_*`: menus, toolbar, objects, panel rows and sequence rows equal, nothing
lost; the Qt half's only Qt controls were the hosting widgets. The Qt facts are frozen in
`chimol/test/qt_reference.json` (`test_emtk_chimol_parity.py`). Porting found the toolkit-free host short of the
Qt window in six places, each fixed in chimol rather than in the test: no structure reader (ChiSurf's
`Structure` now injected via `chimol.io.structure.set_structure_factory`, so Rg and sequence metadata appear),
no 3-D labels and no rubber-band box on screen (now emtk quads, `chimol/viewport/screen_overlays.py`; a
`distance` showed its dashes and no number), no chain markers / `seq_view` / hidden-object rule in the sequence
strip (`hosts/base.py::sequence_rows_for_object`), no degraded-load report, no canvas `resize`, a backdrop path
that was never validated. The 4 left then (the display-defaults prompt test, `chrome_baseline.py`,
`screenshot.py`, `test_screenshot_helper.py`) went in the leftovers slice above. Two lighting pixel tests ran for the first time (they had always skipped
on the Qt offscreen platform) and are strict xfails: silhouettes and the depth cue move no pixels in the
toolkit-free frame (`okf/references/known-issues.md`).
A test line goes by porting the test to the native app (or `emtk.testing.Driver`), never by deleting it; a Qt
host module goes when the emtk shell opens its twin (the manifest drops `gui`; the `--qt` window then hosts the
emtk app in a `ControlHost`, as for trace_browser). Each retirement re-captures before/after with
`python -m test.gui.emtk_port_parity before|after|compare <id> --out DIR` before the code is touched, and keeps
`retire_qt_before.json` / `retire_compare.json` in `okf/plugins/emtk-ports/<id>/` (PNGs there are gitignored).
**"Cannot be frozen" did not survive** (2026-10-13 leftovers slice): a live-Qt fact is frozen as
`qt_reference.json` beside the test, recorded once from the live widget and named by `_recorded.source_commit`.
Facts that follow `docs/` are frozen as a *rule*: help's `qt_home_links` / `qt_breadcrumb` restate the Qt start
page and breadcrumb Qt-free, and the record holds the widget's output beside the rule's output on the same
tree. Fresh ids are normalised (`<project NAME>`, `<version NAME vN>`, `<timestamp>`, `<user>`: project_browser).
Per-case dialogs are recorded per case (switch_user: 15 `LoginDialog` cases through the test's own `world`
fixture). The recorders are throwaway scripts and are not committed: a Qt importer under `chisurf/plugins/` is a
new allow-list entry. Retired that slice: the games' Qt hub and four Qt game containers (each was a chigame canvas
plus a *Sound* button; the `capture_qt.py` scripts went because the Qt renders are committed under
`games/*/test/renders/`), the F-test `FTestTool`, the Global View `GraphWizard` host and `wizard.py`, and the
Project Browser `ProjectBrowserTool` (its `SaveProjectDialog` / `CollisionDialog` are the Qt window's File-menu
dialogs and moved to `chisurf/gui/widgets/project_dialogs.py`, which goes with the Qt window).
**Trace Browser host retired (2026-10-13)** by a general **plugin hand-off**: a plugin calls
`chisurf.core.plugin.handoff.hand_off(plugin_id, kind, payload)`; the shell (`EmtkShellApp.hand_off`, installed as
the process's host) opens the target as a dock and, once `BackgroundBuild` has made its app, calls the receive hook
the target declares in its manifest `accepts` (`HandoffSpec`: `name`, `receive` = `module:function(app, payload)`,
`required` keys). Declared: Intensity Trace `tttr_trace`, TTTR Time Window `tttr_files`, ndX `open_path` + `table`.
Routed through it: Trace Browser HMM/TW/NDX (`gui/handoffs.py`, replacing `host.py` + `host_lookup.py`), H2MM
*dwells → ndX*, Burst Selection *send to ndX* (via `mmfdb_launcher.open_path_in_ndxplorer`) and the sampling
diagnostics page (`ndxplorer.gui.app.open_in_ndx`); each keeps its old path only when no shell is open. Evidence in
`okf/plugins/emtk-ports/trace_browser/`: `retire_qt_before.json` (the Qt adapter's three windows, recorded live
before the change), `retire_after.json`, `retire_compare.json` (0 controls lost in the browser and in each target;
deliberate: window → dock, one dock per tool so a second press re-delivers, file shown in the tool rather than the
window title). The T5 test is ported to the real shell driven by `emtk.testing.Driver` (real clicks, real
`BH_SPC132.spc`, three hand-offs asserted and rendered); mechanism tests in `test/core/test_plugin_handoff.py`.
Trap: a hosted child's `form.rects` are local to its dock box (`host_child` draws with `local_coordinates`), so a
click is `hosted.box` origin + rect. Not routed yet (other lanes' files): help/code_editor's `host_in_shell` page/file opening (could become `accepts` kinds
`open_page` / `open_file`). Under `--qt` the three buttons are now greyed (no Qt adapter); the Qt window is legacy.
**HydroPro, Code Editor and Help retired (2026-10-13, 25 lines struck; HEAD then has 159 with the Trace
Browser's 2).** HydroPro: the 12 parity cases frozen from the live tool with the fake HYDRO program
(`hydropro/test/qt_reference.json`, paths as `<home>`), Qt tool, dialogs, `hydrogui.py` and the QSettings
isolation deleted; the real-state guard runs the native capture and `chisurf.emtk.state` round trip. Help: the
Qt `HelpWidget`, Ask panel and figure dialog deleted, `gui/tool.py` keeps only the Qt host `HelpEmtkTool`;
`api/theme.py` takes emtk's palette (`from_tokens`). Code Editor: control parity first (lost `[]`,
`okf/plugins/emtk-ports/code_editor/parity_*`), out of `emtk_preview.json` (now empty), then the six Qt modules
deleted. Every Qt widget test was ported to the emtk app, and each behaviour the twin lacked was added to it,
not explained away (search ranking, reading measure, figure viewer, Shift+wheel zoom, Ask texts; menus,
Symbols/Kernel docks, project table, regex find, assistant file writes and modes, notebook terminal mirroring
and output clamp). Both plugins declare hand-offs (`help` `open_page`, `code_editor` `open_file`) and
`chisurf/emtk/{doc,code}_links.py` route through `chisurf.core.plugin.handoff`. Open from this slice: emtk
`38d6f8a` (0.1.10, regex find) is committed, not pushed, and `EMTK_MIN_VERSION` stays 0.1.8 -- the arm64 env's
emtk 0.1.9 shows "Regex search needs emtk 0.1.10" in the find bar until the pin moves; the assistant reports
validation issues but no longer re-prompts the model to fix them (known issues). Traps met: a Driver click
after a model change needs a frame first (rects are from the last frame); `im.begin_menu` has no nested
submenus (File > Open Notebook... is a picker); emtk tooltips need a hover delay, so tests read a state
(`hovered_figure`) instead; the global `gui.editor.enable_lsp` now starts pylsp in every editor app built.
Left, and why (each reason re-checked against the challenge):
Open: **ndX window** (`ndxplorer/window.py`, `calibration_bridge.py`, `__init__.py`, `tests/test_window_routes.py`):
  the Qt window is still the `gui` entry; its routes test goes with it once the shell's ndX twin owns the routes.
Done 2026-10-13: **mmfdb_admin** (30 lines; see the slice paragraph at the top of this item).
Done 2026-10-13 (acq/lightpath/batch/number_quest/plugins-root slice, −14): **acq** device dialogs (fa6f18819;
  BH 40→90, BrickMic 10→61, PicoQuant 12→58, simulation 61→118 controls, lost [], `emtk-ports/acq/retire_*`;
  `test_setup_widgets.py` drives the emtk dialog); **lightpath_simulator** Qt host + Qt Easy Mode (7e0514d95;
  helpers in `core/easy_config.py`; Easy Mode 49→125 controls, lost []; the comparison found `_graph_to_config`
  reading pre-schema port numbers, so Easy Mode had shown no dichroic, splitter spectrum or bandpass; parity
  frozen in `tests/qt_reference.json`); **batch_analysis** Qt run (3b978b173; Qt run frozen in
  `test/qt_reference.json`; the per-run fit picture in the DOCX, lost in the first port, is back: the template
  fit's `FitWindow` on the CPU rasteriser, drawn on the polling thread); **number_quest** Qt container
  (5d6b6bf8b); plugins root (89a74df47): `icon_utils.py` → `chisurf/gui/plugin_icons.py` (Qt shell code), the
  QtSvg rasteriser and the `qapp` fixture (pytest-qt supplies it) deleted, the cookiecutter template generates an
  emtk + AutoForm plugin (rendered and its tests run). Follow-up the same day closed the leftovers: acq BH/PicoQuant/BrickMic cards are view.json specs (655a57efd), lightpath detector names, the Detector Wizard's last-config write and a missed-completion race behind three click-test failures (26367e91e).
Trap: the arm64 env imports a non-editable emtk from site-packages, not `~/dev/emtk` (e.g. `NO_BUTTON` is in
`emtk.events`, not `emtk.app`).

**S6-blocker slice and chimol `hosts/qt` (former item 9).** Done 2026-10-13
(S6-blocker slice, chisurf 6300bcb8f, baf8e7f75, 23004c834, 94c945927 and the test port): chiplot's core
names no Qt -- panels, `PanelGrid` and the image viewer `ImagePanel` are emtk controls, hosts attach through a
duck-typed hook, `export_image` draws on emtk's CPU rasteriser -- and the `chisurf.gui.chiplot` widgets
(`Plot`, `PanelPlot`, `Grid`, `ImageView`, `VolumeView`) are deleted: every Qt form that showed one draws a
core panel and only hosts it with `cp.host()` (AutoForm sections decay_conv, phasor, quiver, waterfall, image,
plot, L-curve, the r(t) window; decay_panel, the PCH/TCSPC/ICS reader previews, the κ² dialogs,
spectrum_view, waterfall_plot, the photon-filter wizard); before/after from the HEAD snapshot, 14 of 17 widget
pairs pixel-equal, the three image viewers at control parity with the frame `QSlider`/`QLabel` drawn by emtk
inside the viewer (`chisurf/chiplot/image_panel.py`). What blocks deleting `gui/main.py` and `gui.ui` now: item 1
(the Qt hosts and tests on the allow-list, 64), and the Qt forms of the `--qt` reference shell that host
panels (the Qt AutoForm renderer and its sections, the Qt reader widgets, the κ² dialogs), whose emtk twins
exist; `chisurf.gui.chiplot` (`host`, `PanelHost`, `ImagePanelHost`) goes with them. Striking `qtpy` needs both,
and the owner's call. **chimol: `hosts/qt/` deleted (2026-10-13, chimol a53e512).** `Viewer` is never a
widget: it sits on `hosts/toolkit.py`'s stand-ins, which no longer import qtpy (`HeadlessViewer` is an alias),
and `Viewer()` with no `renderer_factory` builds into `SceneSink` (every host passes its own renderer). Gone
with it: the lazy `MolViewPluginWindow` export, `python -m chimol --qt` (it now says the Qt window was retired
and opens the desktop window), the Qt type hints in `commands/`, the mock viewer's `QObject` base, and
ChiSurf's unused Qt AutoForm `chimol` section (`chisurf/gui/autoform/sections/chimol_section.py`; no
`view.json` used it, and it embedded `Viewer` as a `QWidget`). Measure: `python tools/check_imports.py` in
chimol (299 modules import with Qt blocked, 0 allowed failures); `tests/test_viewer_is_toolkit_free.py`;
ChiSurf `chisurf/plugins/chimol/test/qt_import_allowlist.txt` is empty and `test_qt_seam.py` asserts
`hosts/qt` stays gone. Before/after: `okf/plugins/emtk-ports/chimol/retire_hostqt_*` -- ChiSurf's emtk ChiMOL
app on 148L and 1RTD at 1200x800 is pixel-identical with chimol 07a9b28 and a53e512, and its control inventory
matches the Qt before-grab `retire_qt_before_148l.png` (lost: none). Tests: the five chimol tests and the
ChiSurf chimol tests that imported the Qt host were ported (menu tables from `chimol.ui.menus.bar`,
`grouped_display_order` / `sequence_rows_for_object` from `chimol.hosts.base`, host checks on `ChimolApp` +
`Page`); `test/console/test_command_dispatch_rule.py` now drives `chimol.repl` + `ChimolDispatcher` with no
toolkit. **Retired** because they tested only the Qt window: `test_migrated_tool_windows.py::
test_chimol_window_constructs`, `test_object_list_groups.py::test_the_qt_window_uses_the_shared_builder`,
`test_render_appearance.py::test_the_default_layout_sizes_are_pixels` (Qt dock splitter sizes),
`test_keyboard_layout.py::test_the_qt_host_passes_the_character_qt_produced`, `test_dropped_files.py::test_the_qt_widget_accepts_dropped_files` and
`test_the_qt_host_describes_itself_at_all`,
`test_canvas_cadence.py`'s two Qt `resolve_present_method` tests, and `test_wgpu_view.py`'s Qt
`default_renderer` selection (replaced by a `Viewer()` -> `SceneSink` test). Leftovers closed the same day
(chimol a245145): the widget stand-ins moved from `hosts/toolkit.py` to `core/toolkit.py`, so
`chimol.core` imports nothing from `chimol.hosts` (guard `tests/test_core_layering.py`); the dead
`CHIMOL_TOOLKIT=none` settings are gone from chimol's tests, AGENTS.md, `tools/check_imports.py` and the ChiSurf
chimol tests; and the desktop (`CanvasView`) and browser (`Page`) hosts both declare `labels` and `ray_image`,
which both draw through `CanvasRenderer.frame_arguments` (label quads in `chrome`, a traced frame in
`overlay`; `tests/test_host_features.py` checks the frame, `test_browser_picking.py` keeps the two sets equal).

## Merge into mcts-native-baseline (2026-10-17)

S6 landed: `s6-retire-qt-shell` merged as 855e54604 (43 conflicts resolved: S6's
deletions stand; the branch's own leftovers fixed in 4715fdfd4 — the four tests whose
probes drove the Qt Main now carry strict xfail naming the remaining port: an emtk-shell
session/history probe that saves and reopens `.cs.pto` widget facts. The acquisition
screenshot test followed its probe out; its five-live-pages contract is covered by the
acq plugin's native tests).

Open ports from the merge, in priority order:
1. emtk-shell session restore + history (undo/redo across reopen) probes — the two
   strict-xfail pairs in test_project_window_restore / test_project_history_restore.
2. Licence axis: chisurf is planned to go MIT. Qt is out of the code (zero imports;
   the three remaining grep hits are guards that assert Qt stays out). The GPL
   LICENSE file and the `GPL-3.0-or-later AND CC-BY-SA-4.0` pyproject field remain
   and are the owner's legal act. PyMOL is no dependency (no imports); the vendored
   constants transcribed from PyMOL (atomic masses = IUPAC values, vdW radii, camera
   constants measured from PyMOL) should be regenerated from primary sources and the
   provenance comments re-worded before relicensing.

# Citations

[1] [PRD-154 W9](../prds/prd-154.md)
[2] [GUI & AutoForm, long-term direction](gui-autoform.md)
[3] [Fit window](fit-window.md)
[4] [Ribbon and hubs](ribbon.md)
