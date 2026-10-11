---
type: Subsystem
title: Qt retirement (shell)
description: Parity ledger for moving the ChiSurf main window from Qt to one emtk surface — every Qt capability the shell uses, its emtk equivalent or gap, the allow-list by area, and the ordered slices that keep the app shippable.
resource: chisurf/emtk/main_app.py, chisurf/emtk/fit_docks.py, chisurf/emtk/fit_window.py, chisurf/emtk/session.py, chisurf/emtk/model_editor.py, chisurf/emtk/fit_controls.py, chisurf/server/services/model_svc.py, chisurf/core/server_events.py, chisurf/gui/main.py, chisurf/gui/gui.ui, chisurf/gui/main_helper.py, test/plugin_qt_allowlist.txt
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
The Qt shell is still the default and was not changed.

1. Measure: the allow-list has 245 entries. Re-derive with `grep -vc '^#' test/plugin_qt_allowlist.txt`. The
   per-area split comes from `cut -d/ -f1 test/plugin_qt_allowlist.txt | sort | uniq -c` once comments are dropped:
   chimol 111, core 76, misc 20, microscopy 7, modelling 7, ndxplorer 6, spectra_downloader 4, tttr 4, root 3,
   calculator 2, fret_line 2, cookiecutter 1, quenching_estimator 1, vv_vh_anisotropy 1. Trap: about 171 of the 245
   are **tests**. They import Qt to drive the legacy host, not because the plugin needs it. A slice removes a test
   line by porting the test to `emtk.testing.Driver`, never by deleting the test.
2. Open: model-editor sections that are still drawn as a "not drawn in this window yet" note. Measure: walk the
   `type`s of `chisurf/core/models/**/*.view.json` (44 specs) against the resolver in
   `chisurf/server/services/model_svc.py::_resolve_section`. Missing: `curve_input` 38 (the TCSPC IRF and background
   pickers), and `custom` 37 (`kappa2_controls` 8, `anisotropy_diagnostics` 8, `scalar_table` 8, `rate_matrix` 5,
   `lcurve` 4, `path_list`, `global_parameter_table`, `fit_mixer`, `background_run` 1 each). Blocks: TCSPC fits in
   the shell (no IRF), FCS kinetics rate matrices, MaxEnt L-curves, global-parameter links. Next: `curve_input`, as a
   `choice` of `dataset.list` written by the section's `select_action` through a new spec-declared RPC (the controls
   with a `set_action` are read only today). The Qt S2 inventory only had the general FCS model, so the parity test
   does not see these.
3. Open: the PDA reader (`PTU/HT3/SPC`) is the one reader without a native settings form. Its `pda_detector` rows and
   `pda_tw` time-window list are wired in the 2,070-line Qt controller
   (`chisurf/gui/widgets/experiments/pda2c/controller.py`), with `.bur` resolution and file lists. Measure:
   `KNOWN_GAPS` in `test/native_emtk/test_emtk_shell_readers.py`, where 23 of 24 readers are drawn. Next: move the
   controller's logic onto the reader, then declare the rows as view sections.
4. Open: deliberate differences left after the S2 parity. Each one needs a decision, not a port. A component table
   lists one parameter per row: the Qt editor pairs `row_width` parameters on one row (`a_b1 | τ_b1`). The parameter
   tables have no link menu (`parameter.link` exists). The sample question has no *New…*: samples are made in MMFDB
   Admin. The ⚙ dialog writes the user settings directly, because they are preferences and not session state.
5. Open: S2's allow-list lines (microscopy, tttr and ndxplorer tests) still drive the Qt host; port them to `Driver`.
6. Measure: the shell's fit pages live under `chisurf.gui`, whose package `__init__` imports `qtpy`; opening the
   first fit window (and registering the experiments) loads the Qt modules, though no `QApplication` is made and Qt
   draws nothing. The Code face (`chisurf/gui/widgets/fitting/fit_code_face.py`) is there too.
   `test_the_shell_module_does_not_import_qt` covers construction only. Blocks: S6 striking `qtpy`. Next: move the
   page classes (`chisurf/gui/plots/**`, `model_plot_specs`, `fit_code_face`) out of the Qt-importing package.
7. Open: S3, project and file actions. Menus: File (open, save, import, export project, recent), View, Macro, Settings,
   Undo and Redo. The shortcuts are Ctrl+S, Ctrl+Shift+S, Ctrl+Alt+S, Ctrl+Z, Ctrl+Y, Ctrl+Q, Ctrl+N, Ctrl+L and
   Ctrl+R. `SaveProjectDialog` and `CollisionDialog` come from `plugins/core/project_browser/gui/tool.py`. Blocks:
   the shell cannot hold a session across runs. S3's confirm dialog also decides the fit window's `×`: it closes the
   window and keeps the fit today (Qt asks, then removes the fit).
8. Open: plugins that have only an `action` entrypoint (`menu_switch`) or only a Qt `gui` entrypoint are not offered
   by the emtk shell. `execute_plugin_action` still takes the Qt main window. Measure: `menu_entries()` returns 28
   entries, against 29 visible manifests.
9. Blocked: S6 (delete the Qt shell) is blocked on W7's click-all passing on the native host
   (`test/e2e/test_click_all_plugins.py`), on S3 to S5 reaching parity, and on items 2 and 3.
10. Open: the emtk gaps listed below. **Multi-window** decides whether detached plugin windows survive the move. IME
    text input is missing. Both go into `~/dev/emtk` with tests.

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

# The shell today (Qt) and the emtk equivalent

Each row is one capability the shell uses. Evidence is given as `file:line`. "emtk" names what already exists and
"gap" names what still has to be built. The test column names the guard that proves the row.

| Capability | Qt today | emtk equivalent | Gap | Slice | Test / guard |
|---|---|---|---|---|---|
| Main window, chrome | `gui/main.py:126` `Main(QMainWindow, …mixins)`; `uic.loadUi(gui.ui)` at `main.py:1127`; `closeEvent` order at `main.py:425-477` | `EmtkShellApp` (`chisurf/emtk/main_app.py`) on `emtk.native.NativeHost` | close guard (project dirty, confirm quit, save setup defaults) | S1 skeleton, S3 close guard | `test/native_emtk/test_emtk_shell.py` |
| Central area | `QMdiArea mdiarea` (`gui.ui:44`), Tile, Tab and Cascade (`main.py:557-568`) | `emtk.docking.DockManager` centre region: tabs, split, float | tile and cascade arrangements (split presets are enough) | S1 / S2 | same |
| Docks | 6 `QDockWidget`s in `gui.ui`: Analysis :82, Plot :193, Console :342, Datasets :403, Logging :509, Read data :584; default tabified at `main.py:1490-1514` | `DockManager` regions; Read data, Datasets, Analysis, Plot settings are `chisurf/emtk/fit_docks.py` over `chisurf/emtk/views/*.view.json`; the model editor `chisurf/emtk/model_editor.py` over `model.editor`; controller dialogs `chisurf/emtk/fit_controls.py`; reader sections `chisurf/emtk/detector_cascade.py`; sample question `chisurf/emtk/sample_picker.py` | `curve_input` and nine `custom` model sections, the PDA reader (resume items 2, 3); Console in S4 | S2 done (control parity), S4 | `test/native_emtk/test_emtk_shell_fits.py`, `test_emtk_shell_readers.py`, `test/server/test_model_editor_service.py` |
| Layout persistence | QSettings ("ChiSurf","MainWindow") `geometry/state/layout_version` (`main.py:330-369`); `gui/layout_state.py` | `chisurf.emtk.state.attach_native_state` → `<settings>/emtk/emtk_shell.{layout,window,settings}.json` | — | S1 done (open plugins reopen) | `test_restore_reopens_the_plugins_that_were_open` |
| Ribbon | `widgets/ribbon/**` (22 files, about 6,600 lines); `display_name` "Tab:Group:Name"; QSettings RibbonState | menu bar from the same `display_name` (`menu_entries`) and the Tools dock | ribbon tab strip with icon buttons and quick access; the [Ribbon](ribbon.md) placement guard reads the same manifests | S1 menu done; S5 ribbon | `test_shipped_menus_offer_every_visible_native_plugin` |
| Toolbar plugins | `main.py:944-1044` `plugins.toolbar_plugins`; `gui/plugin_toolbar.py` | — | a tool strip under the menu bar | S5 | — |
| Plugin menus | `gui/__init__.py:850-1104` `populate_plugins` (disabled, order, experimental, `menu_hidden`, `cli_only`) | `menu_entries()` (`menu_hidden`, emtk only, ⚠ for experimental) | `plugins.disabled_plugins`, `plugin_order`, icons, Dev menu | S1 partial, S5 | same |
| Plugin launch | `misc_helpers.run_plugin_from_dir` → `registry.build_plugin_widget` → `qt_host.ControlHost(factory())`, a separate top-level window | `load_plugin` on a `BackgroundBuild` worker, drawn with `ImApp.draw_child` inside a dock | `action` entrypoints; macro or wizard `__init__.py` plugins | S1 done | `test_a_hosted_plugin_gets_its_clicks_and_keys_and_closes_with_its_window` |
| Fit windows | `main.py:2058-2125` `_open_fit_subwindow` → `FitSubWindow(CustomMdiSubWindow)`; the content is already `FitPlotsArea` → one `ControlHost(FitWindowSurface)` | `chisurf/emtk/fit_window.py`: the same `FitWindowSurface`, one dock window per fit; the active fit tab drives the Analysis and Plot settings docks | — (the Code face is the same `FitCodeFace`, writes through `model.code.apply`) | S2 done | `test_load_fit_edit_and_run_through_the_api`, `test_the_model_editor_is_the_models_view_json_written_through_the_api` |
| Server events | `gui/zmq_poller.py:36` 50 ms QTimer → `_on_server_event` (`main.py:1855`) | `chisurf/core/server_events.py` `ServerEventSubscriber`: a worker owns the SUB socket and calls `request_frame`; the shell drains on its frame | — | S2 done | `test/core/test_server_events.py`, `test_a_fit_made_elsewhere_opens_its_window_from_the_event` |
| Dialogs | `ChiSurfMessageBox` (`gui/dialogs.py:146`): `main.py` 13, `main_helper.py` 20, `gui/__init__.py` 11 sites, ribbon 6; `QInputDialog` ×2 (`main_helper.py:500/512`); custom `QDialog`s (FRET RDA axis `main.py:1686`, Data loading `:1715`, `LoginDialog`, `PasswordChangeDialog`, `SaveProjectDialog`, `CollisionDialog`) | `emtk.dialog_window.DialogWindow`, `emtk.widgets.menus.PopupModal`, AutoForm view.json forms | a shared `message`/`confirm`/`choice`/`text` helper with the `auto_answer` headless contract | S3 | — |
| File dialogs | `widgets/general.py:427-519` wrappers; `main_helper.py` 4 sites; `main.py` 3 | `emtk.file_dialog.FileDialog` (open, save, folder, filters, multi-select) | — | S3 | emtk `tests/test_file_dialog.py` |
| Drag and drop of files | `label_filedrop` event filter (`main.py:1179`, `:1276-1312`) → `dataset.add` | `NativeHost` glfw file drop → `on_files_dropped`: the focused child first, else read with the selected file type | — | S2 done | `test_a_file_dropped_on_the_shell_is_read` |
| In-app drag and drop | dataset selector `drag_enabled` (`main.py:1208`) | `emtk.widgets.dragdrop` (one context per host) | dragging between two OS windows (a dataset row onto a fit window is done: emtk table `drag_call`) | S2 done | emtk `test_ui_data_table_drag.py`, `test_a_dataset_dragged_onto_a_fit_window_is_attached_to_that_fit` |
| Keyboard shortcuts | `gui.ui` actions and `configure_project_shortcuts` (`main.py:53-62`), ApplicationShortcut | `ImApp.key` | a shell shortcut table that runs before keys are forwarded to the focused plugin | S3 | — |
| Console | `cs.console = QIPythonWidget(chinsole.Chinsole)` (`gui/__init__.py:589`), `gui/chinsole/**` (8 files, 3,462 lines, `QTextEdit`); the engine `chisurf.core.console` is Qt-free | `emtk.widgets.text_editor.TextEditor`, `emtk.widgets.command_line` | a console view on the Qt-free engine (completion, pager, history) | S4 | — |
| Logging dock | `plainTextEditLog` and filter, `_LogRelay` timers (`gui/__init__.py:192-374`) | S1 Log dock (`_LogBuffer` handler) | level filter, history browser | S1 partial, S4 | — |
| Status bar | `TruncatingStatusBar` (`main.py:1216-1248`) and progress bar | S1 Start dock status line | a status strip with progress | S5 | — |
| Splash | `SplashScreen(QSplashScreen)` (`gui/__init__.py:443`) | none: the first frame is under 100 ms ([GUI startup](../architecture/gui-startup.md)) | startup service stages need a native runner instead of `BackgroundStartupRunner` QTimer chaining | S5 | benchmarks page |
| Startup services | `AppStartupServiceManager` stages in `startup/services.d/20_gui_splash.json`, `30_gui_post_show.json` | — | a `surface="emtk"` stage set (no `setup_ipython`, `startup_interface`, `arrange_widgets`) | S5 | — |
| Auth | `LoginDialog`, deferred `_run_startup_auth` | `switch_user` emtk plugin | modal login before the session | S3 | — |
| Translation | `QTranslator` (`gui/i18n.py:343`); `retranslate_from_ui(self, gui.ui)` re-reads the `.ui` (`gui/retranslate.py`) | `chisurf.emtk.i18n` reads the same `.ts`; `emtk.i18n.tr` applies on the next frame | none: an immediate-mode shell retranslates by drawing | S1 done | `test/native_emtk/*translations*` |
| Tooltips | Qt tooltips and `install_tooltip_wrapping` | `emtk.tooltip` | — | S1 done | emtk `test_tooltip.py` |
| Clipboard | Qt | `emtk.clipboard` (glfw/platform) | — | done | emtk `test_clipboard.py` |
| DPI and export | Qt scaling, `widget.grab()` | `NativeHost` ratio, `emtk.scaled_painter`, `--screenshot` | — | done | `test_emtk_shell_flag_opens_the_emtk_surface` |
| Multi-window | every plugin is its own top-level Qt window | one `NativeHost` per process; floating docks inside one surface | **gap**: a second OS window sharing one app (detached docks on a second monitor) | S6 decision | — |
| Text input, IME | Qt `inputMethodEvent` | `native.py` key and layout-aware `char` events | **gap**: no IME preedit/composition | S4 (console needs it) | — |
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
    float/tab/close; the fit window's `×` keeps the fit (Qt asks and removes it; *Remove fit* in Analysis removes
    it); *+ Data* reads the File field (Browse… opens the dialog) instead of opening a dialog at once; the dataset
    context menu's remove is a *Remove dataset* button and Delete in the table; check boxes instead of
    `true`/`false` cell text; `N/A` instead of `nan`; resume item 4.
  - Fixed on the way (Qt shell too): *Local first* never reached the run; `fit.set_dataset` with a curve of another
    length; `dataset.group` over RPC raised; the global fit's *Remove*; the global fit listing itself as a
    candidate; a fit range starting at lag 0 on a log axis drew an infinite region; the DEER reader had no settings.
  - Not yet: removing the microscopy, tttr and ndxplorer test lines (resume item 5).
- **S3: session.**
  - File, Project, Undo/Redo, Settings and Macro menus, with the shortcut table.
  - Message, confirm and input dialogs with the `auto_answer` headless contract.
  - Project dialogs, the close guard, login.
- **S4: console and log.**
  - Chinsole on `TextEditor` over `chisurf.core.console`, plus the emtk IME gap.
  - Removes code_editor's Qt.
- **S5: ribbon, toolbar, status, startup.**
  - Ribbon tab strip, toolbar plugins, status strip, `surface="emtk"` startup stages.
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
