---
type: Subsystem
title: Qt retirement (shell)
description: Parity ledger for moving the ChiSurf main window from Qt to one emtk surface — every Qt capability the shell uses, its emtk equivalent or gap, the allow-list by area, and the ordered slices that keep the app shippable.
resource: chisurf/emtk/main_app.py, chisurf/emtk/shell_ribbon.py, chisurf/emtk/shell_session.py, chisurf/emtk/shell_log.py, chisurf/emtk/fit_report.py, chisurf/core/fitting/fit_export.py, chisurf/emtk/console.py, chisurf/emtk/fit_docks.py, chisurf/emtk/fit_window.py, chisurf/emtk/session.py, chisurf/emtk/model_editor.py, chisurf/emtk/model_sections.py, chisurf/emtk/pda_sections.py, chisurf/emtk/sample_picker.py, chisurf/emtk/fit_controls.py, chisurf/server/services/model_svc.py, chisurf/server/services/model_sections.py, chisurf/core/server_events.py, chisurf/gui/main.py, chisurf/gui/gui.ui, chisurf/gui/main_helper.py, test/plugin_qt_allowlist.txt
tags: [gui, emtk, qt-retirement, shell, parity, ledger]
timestamp: '2026-10-11T00:00:00Z'
---

# Where to pick this up

Phase 2 of [PRD-154](../prds/prd-154.md) W9. Slice S1 is done: `python -m chisurf --emtk-shell` opens
`chisurf/emtk/main_app.py`. It has a manifest menu bar, Tools, Start and Log docks, and every native plugin opens as
a dock window. Slice S2 reached control parity with the Qt docks on 2026-10-11: `KNOWN_GAPS` in
`test/native_emtk/test_emtk_shell_fits.py` is empty. The Analysis dock draws each model's own `view.json` editor from
`model.editor` (`chisurf/emtk/model_editor.py`) and carries the whole fit controller. A fit window turns over to its
Code face. The session holds the Global Dataset, and a dataset row dragged onto a fit window is attached to that fit.
The model editor's curve pickers and custom sections, the PDA reader's form, the link menu, paired component rows
and *New…* sample followed the same day, at parity with the Qt model editors of ten models (item 2).
Slice S3 reached control parity for the session menus on 2026-10-11 (`chisurf/emtk/shell_session.py`): File, View
and Settings with the Qt shortcuts, save and reopen of `.cs.pto`, undo and redo, autosave, a close guard that asks
once, and a fit window `×` that asks and then removes the fit. `KNOWN_GAPS` in
`test/native_emtk/test_emtk_shell_session.py` keeps three items. Slice S4 reached parity with the Qt console the
same day: a Console dock on emtk's `TextEditor` over the Qt-free engine (`chisurf/emtk/console.py`), *Macro ▸ Record*
and *Run Macro…*, `chisurf.run` routed to it, and composed (dead-key and IME) text in every emtk text field
(`emtk.ime`). Slice S5's ribbon reached parity with the Qt ribbon the same day
(`chisurf/emtk/shell_ribbon.py` on emtk's new `emtk.ribbon`): its tabs, groups and buttons come from the manifests
through the Qt ribbon's own placement rules, and the menu bar and Tools dock list the same tree with the manifest
icons. The status strip of S5 is still open; the splash window and its startup stages landed 2026-10-12 (item 13). The Qt shell is still the default.

1. Measure: the allow-list has 245 entries. Re-derive with `grep -vc '^#' test/plugin_qt_allowlist.txt`. The
   per-area split comes from `cut -d/ -f1 test/plugin_qt_allowlist.txt | sort | uniq -c` once comments are dropped:
   chimol 111, core 76, misc 20, microscopy 7, modelling 7, ndxplorer 6, spectra_downloader 4, tttr 4, root 3,
   calculator 2, fret_line 2, cookiecutter 1, quenching_estimator 1, vv_vh_anisotropy 1. Trap: about 171 of the 245
   are **tests**. They import Qt to drive the legacy host, not because the plugin needs it. A slice removes a test
   line by porting the test to `emtk.testing.Driver`, never by deleting the test. Open: S2's lines (microscopy, tttr
   and ndxplorer tests) still drive the Qt host.
2. Measure: the model editor's curve pickers and the nine `custom` sections (plus a lifetime group's
   `lifetime_amplitude_options`) are resolved by `chisurf/server/services/model_sections.py` and drawn by
   `chisurf/emtk/model_sections.py`; writes go through `model.curve.set` / `model.curve.unload` /
   `model.section.call`, checked against the model's `view.json`. Parity:
   `test_emtk_shell_model_sections.py::test_parity_with_the_qt_model_editors` against
   `shell_s2_models_qt_inventory.json` (10 models: TCSPC with IRF and background, mixture, MaxEnt, structure, FCS
   kinetics, two PDA, global, ProteinMC; `capture_shell_s2_models_qt_before.py`, about 15 min, writes as it goes).
   `KNOWN_GAPS` is empty. Trap: the Qt inventory's dye names come from the user's MMFDB (`ENVIRONMENT` in the test).
   Open: `background_run` (ProteinMC start/stop) is drawn but no test presses it; the ProteinMC *Structure* page fails
   in the shell (chimol gets a `DataCurve`); see known issues "Lifetime mixture" and "FRET: Structure fit".
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
   markers now in `chisurf/core/plugin/maturity.py`). Open: the S5 status strip (progress) and a `surface="emtk"`
   startup stage set. Trap: tab and group captions are manifest `display_name` segments, collected for translation
   since this slice (`build_tools/i18n/extract_strings.py::_collect_menu_path`); their de/fr entries are unfinished
   until the queued translation job, so the German shell still shows *Spectroscopy*. Trap: re-extracting while
   another lane has uncommitted `tr()` edits marks their removed strings obsolete; put such entries back (S5 restored
   *Close Help*) or `test_committed_authored_ui_text_has_german_and_french_catalogue_sources` fails.
6. Measure: the shell's fit pages live under `chisurf.gui`, whose package `__init__` imports `qtpy`; opening the
   first fit window (and registering the experiments) loads the Qt modules, though no `QApplication` is made and Qt
   draws nothing. The Code face (`chisurf/gui/widgets/fitting/fit_code_face.py`) is there too.
   `test_the_shell_module_does_not_import_qt` covers construction only. Blocks: S6 striking `qtpy`. Next: move the
   page classes (`chisurf/gui/plots/**`, `model_plot_specs`, `fit_code_face`) out of the Qt-importing package.
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
8. Measure: a file dropped from the OS arrives with no pointer moves (macOS sends none during a drag), so the shell
   routes it by the drop position that emtk now delivers first (`CanvasEvents.files_dropped`, emtk `ee4c76a`), to
   the dock under the pointer, not the one with the keys. `RealisticDriver.drop_files` reproduces it; the imaging
   repro is `test_a_file_dropped_on_a_plugin_dock_goes_to_the_dock_under_the_pointer`. Plugins with only an
   `action` entrypoint run from the shell (`run_plugin_action`; `menu_entries()` now 29 of 29 visible manifests).
9. Blocked: S6 (delete the Qt shell) waits for the owner's call. Owner decision 2026-10-11: the emtk shell is the
   default window (`python -m chisurf`, the installers' launchers too); the Qt shell stays, behind
   `python -m chisurf --qt`, as the reference the emtk shell is measured against until parity ("the qt is there
   for achieving parity"). `--emtk-shell` is still accepted. Guard: `test/native_emtk/test_emtk_shell.py`
   (`test_python_m_chisurf_opens_the_emtk_surface`, `test_qt_flag_opens_the_qt_window_kept_for_parity`). When
   S6 is reopened, item 6 (page classes under the Qt-importing `chisurf.gui`) is the first step.
10. Open: **multi-window** (the emtk gap below) decides whether detached plugin windows survive the move; it goes into
    `~/dev/emtk` with tests. emtk is pushed up to `9931996` (pin, drop position, Driver caption on top) and
    `pixi.lock` pins it. Measure: `git -C ~/dev/emtk log --oneline origin/main..HEAD`.
11. Measure: `test/native_emtk/capture_shell_s3_qt_before.py` and `capture_shell_s4_qt_before.py` rewrite the S3 and
    S4 before-halves (`shell_s3_qt_inventory.json`, `shell_s4_qt_inventory.json`; PNGs in `renders/w9_s3/`,
    `renders/w9_s4/`). Run S4 with the env's python directly, not `conda run` (which exited 1 with no trace once).
    Trap: the ribbon replaces the Qt menu bar widget, so `QMainWindow.menuBar()` segfaults. The scripts read the
    `.ui`'s own `menuBar` attribute instead.
12. Open: S4 remainders. (a) CJK draws one cell per character, narrowed to it (`emtk/dynamic_font.py`): legible at
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
13. Measure: the splash on the real launch. `python -m chisurf` with a fresh `CHISURF_SETTINGS_DIR`: the splash
    window draws its first frame about 0.25 s after it opens (before the shell is built), the stages advance
    Loading modules → Registering experiments → Starting the server and its plugins → Connecting → Preparing the
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
| Status bar | `TruncatingStatusBar` (`main.py:1216-1248`) and progress bar | S1 Start dock status line | a status strip with progress | S5 | — |
| Splash | `SplashScreen(QSplashScreen)` (`gui/__init__.py:443`) over `icons/splashscreen.png` | `chisurf/emtk/splash.py`: its **own** frameless window (`NativeHost(decorated=False, floating=True, transparent=True, centred=True)`, emtk 93bc456), the art at 2x (`chisurf/emtk/splash.png` from the SVG, its own 2048-texel image atlas), transparent where the art is; progress bar, stage, last log line, copyright, version, licence, contributors drawn on the art where the Qt splash puts them; the main window opens when the session has settled and the splash closes on its first frame. A separate window, not a cover inside the main one: the art is a shaped splash *screen* (owner, 2026-10-12) | — | S5 done | `test/native_emtk/test_emtk_shell_splash.py`, emtk `tests/test_native_splash_window.py` |
| Startup services | `AppStartupServiceManager` stages in `startup/services.d/20_gui_splash.json`, `30_gui_post_show.json` | the `surface="emtk"`, `phase="splash"` set `services.d/25_emtk_splash.json` (imports, experiments, server and its plugins, connect, global dataset) run by the same manager inside `chisurf.emtk.session.start_session` on the session worker; `on_stage_start` feeds the splash | the Qt post-show stages (`populate_plugins`, `check_updates`, `warmup_imports`) have no emtk counterpart yet: the shell reads manifests in its constructor and checks no updates | S5 done (splash phase) | `test_the_session_reports_the_declared_stages_in_order`, `test/startup/test_services.py` |
| Auth | `LoginDialog`, deferred `_run_startup_auth` | `switch_user` emtk plugin | modal login before the session | S3 open (resume item 7) | — |
| Translation | `QTranslator` (`gui/i18n.py:343`); `retranslate_from_ui(self, gui.ui)` re-reads the `.ui` (`gui/retranslate.py`) | `chisurf.emtk.i18n` reads the same `.ts`; `emtk.i18n.tr` applies on the next frame | none: an immediate-mode shell retranslates by drawing | S1 done | `test/native_emtk/*translations*` |
| Tooltips | Qt tooltips and `install_tooltip_wrapping` | `emtk.tooltip` | — | S1 done | emtk `test_tooltip.py` |
| Clipboard | Qt | `emtk.clipboard` (glfw/platform) | — | done | emtk `test_clipboard.py` |
| DPI and export | Qt scaling, `widget.grab()` | `NativeHost` ratio, `emtk.scaled_painter`, `--screenshot` | — | done | `test_emtk_shell_flag_opens_the_emtk_surface` |
| Multi-window | every plugin is its own top-level Qt window | one `NativeHost` per process; floating docks inside one surface | **gap**: a second OS window sharing one app (detached docks on a second monitor) | S6 decision | — |
| Text input, IME | Qt `inputMethodEvent` | `emtk.ime`: commits as typed text, preedit in `io.preedit` drawn at the caret of `input_text`, `TextEditor`, `TextField`; `qt_host.inputMethodEvent`; native holds back a composition's keys (`MarkedTextProbe`) | inline preedit in the glfw window, the browser's composition events (resume item 12) | S4 done | emtk `tests/test_ime.py`, `test_emtk_shell_console.py::test_composed_input_types_into_the_console` |
| Molecular viewer | chimol `hosts/qt` | chimol native host | chimol's 110 Qt-driven tests | S7 | — |
| Watermark, sparkline | `widgets/system_info_watermark.py` | chiplot or `emtk.implot` | — | S5 (or drop) | — |

# Allow-list by area and the slice that removes it

`test/test_plugin_qt_free.py` fails on any `qtpy|PyQt|PySide` import under `chisurf/plugins/**` that is outside the
**shrinking** `test/plugin_qt_allowlist.txt`. It also fails when an entry no longer imports Qt. Role counts below come
from a regex heuristic, not a manual review: host = mentions `ControlHost`, `qt_host` or `EmtkEmbed`; widget =
defines a Q* class; test = lives under a `test(s)/` directory.

| Area | Lines | Host | Widget / dialog | Test | Other | Removed by |
|---|---|---|---|---|---|---|
| chimol | 111 | 0 | 1 (`chimol/__init__.py`) | 110 | 0 | S7: chimol tests move to the native host, chimol drops `hosts/qt` |
| core / mmfdb_admin | 30 | 0 | 17 | 12 | 1 | S5: legacy admin widgets go once the emtk app covers them |
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
- **S6: switch and delete.**
  - `python -m chisurf` launches the emtk shell.
  - Delete `gui/main.py`, `main_helper.py`, `gui.ui`, `retranslate.py`, the ribbon, `widgets/tools/**` and
    `gui/chinsole/**` Qt views.
  - Strike `qtpy`, `pyqt` and `QT_API` from `pixi.toml`.
  - Gate: W7 click-all is green on the native host, and startup is no slower than the Qt baseline.
- **S7: chimol.** Drop `hosts/qt`, and port the 110 chimol tests to the native host.

# Citations

[1] [PRD-154 W9](../prds/prd-154.md)
[2] [GUI & AutoForm, long-term direction](gui-autoform.md)
[3] [Fit window](fit-window.md)
[4] [Ribbon and hubs](ribbon.md)
