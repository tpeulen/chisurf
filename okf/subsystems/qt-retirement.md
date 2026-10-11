---
type: Subsystem
title: Qt retirement (shell)
description: Parity ledger for moving the ChiSurf main window from Qt to one emtk surface — every Qt capability the shell uses, its emtk equivalent or gap, the allow-list by area, and the ordered slices that keep the app shippable.
resource: chisurf/emtk/main_app.py, chisurf/emtk/fit_docks.py, chisurf/emtk/fit_window.py, chisurf/emtk/session.py, chisurf/core/server_events.py, chisurf/gui/main.py, chisurf/gui/gui.ui, chisurf/gui/main_helper.py, test/plugin_qt_allowlist.txt
tags: [gui, emtk, qt-retirement, shell, parity, ledger]
timestamp: '2026-10-11T00:00:00Z'
---

# Where to pick this up

Phase 2 of [PRD-154](../prds/prd-154.md) W9. Slice S1 is done: `python -m chisurf --emtk-shell` opens
`chisurf/emtk/main_app.py`. It has a manifest menu bar, Tools, Start and Log docks, and every native plugin opens as
a dock window. Slice S2 is **partial** (2026-10-11): the Read data, Datasets, Analysis and Plot settings docks and one
dock window per fit work end to end through `ChiSurfAPI` and the server's events, but the model editor and four
fitting-controller actions are still missing (items 2 and 3). The Qt shell is still the default and was not changed.

1. Measure: the allow-list has 245 entries. Re-derive with `grep -vc '^#' test/plugin_qt_allowlist.txt`. The
   per-area split comes from `cut -d/ -f1 test/plugin_qt_allowlist.txt | sort | uniq -c` once comments are dropped:
   chimol 111, core 76, misc 20, microscopy 7, modelling 7, ndxplorer 6, spectra_downloader 4, tttr 4, root 3,
   calculator 2, fret_line 2, cookiecutter 1, quenching_estimator 1, vv_vh_anisotropy 1. Trap: about 171 of the 245
   are **tests**. They import Qt to drive the legacy host, not because the plugin needs it. A slice removes a test
   line by porting the test to `emtk.testing.Driver`, never by deleting the test.
2. Open: S2's one blocker, the **model editor**. The Qt Analysis dock shows each model's `view.json` editor (structure
   choices such as the FCS *Diffusion* type, the equation, grouped parameters labelled with units such as `D [µm²/s]`,
   add/remove component, MDF outputs). The emtk Analysis dock shows every parameter in one table (name, value,
   fixed, bounds, error), edited through `ChiSurfAPI.set_parameter_*`. Measure: `KNOWN_GAPS` in
   `test/native_emtk/test_emtk_shell_fits.py` is the tracker; the parity test fails when a gap closes, so the list
   only shrinks. Blocks: S2 parity, so S6. Next: a native renderer for `parameter_group_table` (emtk
   `emtk.widgets.view_spec.unsupported_sections` names it) whose writes go through `model.state_get` /
   `model.state_set` and `parameter.*` RPCs (`chisurf/server/services/model_svc.py`), never into the live model.
3. Open: the fitting controller's other actions are missing in the emtk Analysis dock: MCTS, Sample, the ⚙ search
   fit settings, the … settings, Local first, the Dataset re-target combo and the Result index; and the fit window's
   Code face (`FitCodeFace`, `fit_subwindow.py:540`). Present: Fit, auto, First/Last, χ²ᵣ, Remove fit.
4. Open: 10 of 24 readers have no native settings form, so the Read data dock reads them with their defaults and
   says so. Measure: build `chisurf.emtk.reader_settings.ReaderSettingsApp(reader)` for every reader of
   `chisurf.experiment` after `ensure_experiments_registered(allow_widgets=False)`; it raises for `tcspc_tttr_detector`,
   `simulator_anisotropy`, `pda_detector`, `ics_detector`, `pch_detector` custom sections and for four readers with
   no `view_spec` (PDA burst table, PDA simulator, DEER, Global-Fit). The FCS readers' `fcs_columns` section is now
   drawn natively (`FCS.register_settings_sections`).
5. Open: the Qt session always holds the Global-fit pseudo-dataset; the emtk session (a fresh `SessionState` on the
   embedded server) does not, so global fits cannot be made in the emtk shell yet. The FCS reader's MMFDB sample
   picker (asked after the file dialog in Qt) is not asked either.
6. Open: S2's allow-list lines (microscopy, tttr and ndxplorer tests) still drive the Qt host; port them to `Driver`.
7. Measure: the shell's fit pages live under `chisurf.gui`, whose package `__init__` imports `qtpy`; opening the
   first fit window (and registering the experiments) loads the Qt modules, though no `QApplication` is made and Qt
   draws nothing. `test_the_shell_module_does_not_import_qt` covers construction only. Blocks: S6 striking `qtpy`.
   Next: move the page classes (`chisurf/gui/plots/**`, `model_plot_specs`) out of the Qt-importing package.
8. Open: S3, project and file actions. Menus: File (open, save, import, export project, recent), View, Macro, Settings,
   Undo and Redo. The shortcuts are Ctrl+S, Ctrl+Shift+S, Ctrl+Alt+S, Ctrl+Z, Ctrl+Y, Ctrl+Q, Ctrl+N, Ctrl+L and
   Ctrl+R. `SaveProjectDialog` and `CollisionDialog` come from `plugins/core/project_browser/gui/tool.py`. Blocks:
   the shell cannot hold a session across runs. S3's confirm dialog also decides the fit window's `×`: it closes the
   window and keeps the fit today (Qt asks, then removes the fit).
9. Open: plugins that have only an `action` entrypoint (`menu_switch`) or only a Qt `gui` entrypoint are not offered
   by the emtk shell. `execute_plugin_action` still takes the Qt main window. Measure: `menu_entries()` returns 28
   entries, against 29 visible manifests.
10. Blocked: S6 (delete the Qt shell) is blocked on W7's click-all passing on the native host
    (`test/e2e/test_click_all_plugins.py`) and on S2 to S5 reaching parity.
11. Open: the emtk gaps listed below. **Multi-window** decides whether detached plugin windows survive the move. IME
    text input is missing. Both go into `~/dev/emtk` with tests.
12. Open: chisurf's env pins emtk `57c2fc3` (`pixi.lock`). emtk `adee696` (menu sections in popups) is local only. The
    shell does not depend on it: it draws group captions as disabled menu rows. Once the pin moves, switch those to
    `im.separator_text`.
13. Tried and reverted: `im.separator_text` inside a menu-bar menu on emtk `57c2fc3`. The captions painted onto the bar
    row under the titles, because separators did not go to the popup. emtk `adee696` fixes this; see item 12.

Traps for whoever continues S2:

- The server answers one request at a time, and a fit runs inside one `fit.run` call. The docks therefore make every
  call on a worker (`DataDocks._start`) and re-read their rows only while no call is under way; a read on the frame
  thread during a fit would freeze the window until the fit ends.
- `chi2r` in a fit DTO is the value the last run recorded (`None` before any run, stale after an edit). The Analysis
  dock reads `chi2r_current` from `fit.get`, which evaluates the current parameters.
- ZMQ drops PUB messages a SUB socket joined too late for. `ServerEventSubscriber.start` waits for its connect, but a
  test that publishes once right after starting must publish until the subscriber has queued something
  (`test/core/test_server_events.py::_publish_until`).

# The shell today (Qt) and the emtk equivalent

Each row is one capability the shell uses. Evidence is given as `file:line`. "emtk" names what already exists and
"gap" names what still has to be built. The test column names the guard that proves the row.

| Capability | Qt today | emtk equivalent | Gap | Slice | Test / guard |
|---|---|---|---|---|---|
| Main window, chrome | `gui/main.py:126` `Main(QMainWindow, …mixins)`; `uic.loadUi(gui.ui)` at `main.py:1127`; `closeEvent` order at `main.py:425-477` | `EmtkShellApp` (`chisurf/emtk/main_app.py`) on `emtk.native.NativeHost` | close guard (project dirty, confirm quit, save setup defaults) | S1 skeleton, S3 close guard | `test/native_emtk/test_emtk_shell.py` |
| Central area | `QMdiArea mdiarea` (`gui.ui:44`), Tile, Tab and Cascade (`main.py:557-568`) | `emtk.docking.DockManager` centre region: tabs, split, float | tile and cascade arrangements (split presets are enough) | S1 / S2 | same |
| Docks | 6 `QDockWidget`s in `gui.ui`: Analysis :82, Plot :193, Console :342, Datasets :403, Logging :509, Read data :584; default tabified at `main.py:1490-1514` | `DockManager` regions; Read data, Datasets, Analysis, Plot settings are `chisurf/emtk/fit_docks.py` over `chisurf/emtk/views/*.view.json` | the model editor and four fitting-controller actions (resume items 2, 3); Console in S4 | S2 partial, S4 | `test/native_emtk/test_emtk_shell_fits.py` |
| Layout persistence | QSettings ("ChiSurf","MainWindow") `geometry/state/layout_version` (`main.py:330-369`); `gui/layout_state.py` | `chisurf.emtk.state.attach_native_state` → `<settings>/emtk/emtk_shell.{layout,window,settings}.json` | — | S1 done (open plugins reopen) | `test_restore_reopens_the_plugins_that_were_open` |
| Ribbon | `widgets/ribbon/**` (22 files, about 6,600 lines); `display_name` "Tab:Group:Name"; QSettings RibbonState | menu bar from the same `display_name` (`menu_entries`) and the Tools dock | ribbon tab strip with icon buttons and quick access; the [Ribbon](ribbon.md) placement guard reads the same manifests | S1 menu done; S5 ribbon | `test_shipped_menus_offer_every_visible_native_plugin` |
| Toolbar plugins | `main.py:944-1044` `plugins.toolbar_plugins`; `gui/plugin_toolbar.py` | — | a tool strip under the menu bar | S5 | — |
| Plugin menus | `gui/__init__.py:850-1104` `populate_plugins` (disabled, order, experimental, `menu_hidden`, `cli_only`) | `menu_entries()` (`menu_hidden`, emtk only, ⚠ for experimental) | `plugins.disabled_plugins`, `plugin_order`, icons, Dev menu | S1 partial, S5 | same |
| Plugin launch | `misc_helpers.run_plugin_from_dir` → `registry.build_plugin_widget` → `qt_host.ControlHost(factory())`, a separate top-level window | `load_plugin` on a `BackgroundBuild` worker, drawn with `ImApp.draw_child` inside a dock | `action` entrypoints; macro or wizard `__init__.py` plugins | S1 done | `test_a_hosted_plugin_gets_its_clicks_and_keys_and_closes_with_its_window` |
| Fit windows | `main.py:2058-2125` `_open_fit_subwindow` → `FitSubWindow(CustomMdiSubWindow)`; the content is already `FitPlotsArea` → one `ControlHost(FitWindowSurface)` | `chisurf/emtk/fit_window.py`: the same `FitWindowSurface`, one dock window per fit; the active fit tab drives the Analysis and Plot settings docks | the Code face; fit editors (`build_model_editor`) are Qt | S2 partial | `test_load_fit_edit_and_run_through_the_api` |
| Server events | `gui/zmq_poller.py:36` 50 ms QTimer → `_on_server_event` (`main.py:1855`) | `chisurf/core/server_events.py` `ServerEventSubscriber`: a worker owns the SUB socket and calls `request_frame`; the shell drains on its frame | — | S2 done | `test/core/test_server_events.py`, `test_a_fit_made_elsewhere_opens_its_window_from_the_event` |
| Dialogs | `ChiSurfMessageBox` (`gui/dialogs.py:146`): `main.py` 13, `main_helper.py` 20, `gui/__init__.py` 11 sites, ribbon 6; `QInputDialog` ×2 (`main_helper.py:500/512`); custom `QDialog`s (FRET RDA axis `main.py:1686`, Data loading `:1715`, `LoginDialog`, `PasswordChangeDialog`, `SaveProjectDialog`, `CollisionDialog`) | `emtk.dialog_window.DialogWindow`, `emtk.widgets.menus.PopupModal`, AutoForm view.json forms | a shared `message`/`confirm`/`choice`/`text` helper with the `auto_answer` headless contract | S3 | — |
| File dialogs | `widgets/general.py:427-519` wrappers; `main_helper.py` 4 sites; `main.py` 3 | `emtk.file_dialog.FileDialog` (open, save, folder, filters, multi-select) | — | S3 | emtk `tests/test_file_dialog.py` |
| Drag and drop of files | `label_filedrop` event filter (`main.py:1179`, `:1276-1312`) → `dataset.add` | `NativeHost` glfw file drop → `on_files_dropped`: the focused child first, else read with the selected file type | — | S2 done | `test_a_file_dropped_on_the_shell_is_read` |
| In-app drag and drop | dataset selector `drag_enabled` (`main.py:1208`) | `emtk.widgets.dragdrop` (one context per host) | dataset rows cannot be dragged onto a fit yet; dragging between two OS windows | S2 | emtk `test_ui_dragdrop.py` |
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
- **S2 (partial, 2026-10-11): data and fits.**
  - Read data (experiment, file type, file, Browse…, Load example, + Data, the reader's native settings), Datasets
    (datasets and fits tables, Model, + Analysis, Remove dataset), Analysis (Fit, auto, Remove fit, First/Last, χ²ᵣ,
    parameter table) and Plot settings docks: `chisurf/emtk/fit_docks.py`, specs in `chisurf/emtk/views/`.
  - Fit windows as `FitWindowSurface` docks: `chisurf/emtk/fit_window.py`.
  - The session: an in-process `ChiSurfServer` on free ports, `ChiSurfAPI` in `server` mode, events through the
    Qt-free `ServerEventSubscriber` (`chisurf/emtk/session.py`, `chisurf/core/server_events.py`). New API:
    `ChiSurfAPI.set_fit_range`; `fit.get` carries `fit_range` and `chi2r_current`.
  - Dropping a file onto the shell reads it. *Load example* writes `chisurf/core/experiments/fcs/demo.py`'s curve
    (one species, N = 2): the headless test fits it back to N = 2.00 at χ²ᵣ ≈ 0.88.
  - Parity: before-half `test/native_emtk/shell_s2_qt_inventory.json` (made by
    `test/native_emtk/capture_shell_s2_qt_before.py`; PNGs in `renders/w9_s2/`), compared in
    `test_parity_with_the_qt_docks`. Deliberate differences: MDI minimise/maximise become dock float/tab/close; the
    fit window's `×` keeps the fit (Qt asks and removes it; *Remove fit* in Analysis removes it); *+ Data* reads the
    File field (Browse… opens the dialog) instead of opening a dialog at once; the dataset context menu's remove is
    a *Remove dataset* button and Delete in the table; the parameter groups become one table with internal names.
    Lost (blocks acceptance): resume items 2 to 5.
  - Not yet: removing the microscopy, tttr and ndxplorer test lines (resume item 6).
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
