# Type C audit (PRD-153): screenshot, tttr_correlate, tttr_histogram

Read-only audit, no code changed. All three manifests have `entrypoints.script = "__init__.py"` and no `gui`/`emtk` entrypoint.
Plugin loader convention: the script is executed with `__name__ == "plugin"` (`chisurf/gui/misc_helpers.py:202-225`, `chisurf/macros/plugin_check.py:554`), and each `__init__.py` acts only under `if __name__ == "plugin":`.

## Summary

| plugin | entrypoint class / function | Qt? | Qt LOC | emtk equivalent | recommendation |
|---|---|---|---|---|---|
| screenshot | `_run_screenshot()` in `chisurf/plugins/core/screenshot/__init__.py:52` (headless action; one transient `QLabel` toast) | only a toast `QLabel` + clipboard + status bar, no window/dialog | 107 (whole file `__init__.py`: 158 lines) | none; nothing to port (emtk has its own screenshot helper in `emtk/testing`, unrelated) | no GUI to port |
| tttr_correlate | `CorrelateTTTR(QWidget)` in `chisurf/plugins/tttr/tttr_correlate/gui.py:367` | yes, full tool window (QWidget from .ui + QThread correlator) | 467 (gui.py) + 249 + 171 (.ui) = 887 | none for this tool. Nearest: `fcs/fcs_correlator` (also script type, Qt, has `correlator.view.json`), `burst/burst_fcs_correlator`; `tttr/tttr_toolbox` (emtk) covers burst/decays but its guide mentions correlation only as prose | port as Type B, or retire/merge into `fcs_correlator` (see section) |
| tttr_histogram | `HistogramTTTR(QWidget, CurveGroup)` in `chisurf/plugins/tttr/tttr_histogram/gui.py:33` | yes, full tool window | 211 (gui.py) + 329 + 220 (.ui) = 760 | `tttr/microtime_histogram` (manifest `entrypoints.emtk = ...gui.app:create_app`) | retire/merge into `microtime_histogram` |

## screenshot

- Manifest: `chisurf/plugins/core/screenshot/manifest.json` -> `"script": "__init__.py"`. Directory holds only `__init__.py`, `icon.svg`, `manifest.json`.
- Launch: `if __name__ == "plugin": _run_screenshot()` (`__init__.py:157-158`). `_run_screenshot` (l.52-153) calls `_find_main_window()` (l.21-49), `app.processEvents()`, `win.grab()` (l.69), `QApplication.clipboard().setPixmap` (l.73), `statusBar().showMessage(...)` (l.78), and a 500 ms frameless toast `QLabel` (l.87-135).
- Qt: no QWidget/QDialog/QMainWindow subclass, no file dialog or message box (the docstring/manifest say "message box" but the code uses a status-bar message plus the QLabel toast). Widgets touched: the existing main window (found via `isinstance(w, chisurf.gui.main.Main)` / `QMainWindow`), one throwaway `QLabel`. About 107 lines of Qt-touching code, all in one file.
- Headless action, not a window. emtk replacement: none needed; the action grabs the Qt main window, which only exists in the Qt host (an emtk host would use its own screenshot/`testing` facility).
- chisurf.gui dependencies: `from chisurf.gui import QtWidgets` (l.18), `from chisurf.gui import QtCore` (l.84), `from chisurf.gui.main import Main` (l.25, lazy). Also `import chisurf as cs` for logging.
- emtk equivalent: none in plugins (grep `grab()|clipboard|screenshot` over `chisurf/plugins` finds only burst tools' unrelated uses and this plugin).
- Tests: none for this plugin (grep for `screenshot` over `test/` and plugin test dirs finds only docs/ndx screenshot tooling and render json files, none of which import this plugin).
- Recommendation: **no GUI to port.** Keep as a Qt-host utility; leave until the main window itself is ported.
- Commands: `cat -n chisurf/plugins/core/screenshot/__init__.py`; `git status --short -- chisurf/plugins/core/screenshot` (clean, empty output); `grep -n screenshot okf/agent-board.md` (no claim on this plugin; hits at l.1170-2183 are docs screenshots / ndx io work).

## tttr_correlate

- Manifest: `chisurf/plugins/tttr/tttr_correlate/manifest.json` -> `"script": "__init__.py"`.
- Launch: `__init__.py:30-34`: `window = CorrelateTTTR(); window.show()` (import l.22 from `gui.py`). `CorrelateTTTR` is at `gui.py:367`, decorated `@persist_plugin_state("tttr_correlate")`, built from `tttr_correlate.ui` via `@cs.gui.decorators.init_with_ui` (l.429).
- Qt: yes, a full tool window. Widgets: `CorrelateTTTR` (QWidget: QSplitter, 2 QDockWidget, QScrollArea from `tttr_correlate.ui`), embedded `SpcFileWidget` (file loader), `CorrelatorWidget` (gui.py:~238, from `correlatorWidget.ui`: 3 QSpinBox, 3 QComboBox, 2 QLineEdit channel fields, QCheckBox fine, QProgressBar, Run QPushButton), `ExperimentalDataSelector` (curve list), `cp.Plot()` (log-x G(tau) plot). `Correlator(QThread)` (l.36-194) runs the tttrlib correlation. No QFileDialog/QMessageBox directly (the file dialog is inside `SpcFileWidget`).
- Qt LOC: `gui.py` 467 + `tttr_correlate.ui` 171 + `correlatorWidget.ui` 249 = 887. About 190 of gui.py is correlation science (`Correlator.run`, `weight`) not UI.
- Not headless; a real window.
- chisurf.gui imports (gui.py:18-26): `chisurf.gui.decorators`, `chisurf.gui.widgets`, `chisurf.gui.widgets.experiments`, `chisurf.gui.widgets.fio` (`SpcFileWidget`, 273 lines in `chisurf/gui/widgets/fio/fio.py`), `from chisurf.gui import QtCore, QtWidgets`, `from chisurf.gui import chiplot as cp`, `chisurf.gui.autoform.sections.progress_section.adopt_progress_bar`, `chisurf.gui.misc_helpers.persist_plugin_state`.
- emtk equivalent: none for exactly this. Related: `fcs/fcs_correlator` (manifest `entrypoints.script = "wizard.py"`, Qt, but has `correlator.view.json`/`filter.view.json`/`merger.view.json` and `core.py`, so it is the closer port candidate and does the same job on files); `burst/burst_fcs_correlator` (Qt). `tttr/tttr_toolbox` (emtk) does not expose a correlator.
- Tests: `test/gui/test_gui_correlator.py` (87 lines, 4 tests; `tool` fixture constructs `CorrelateTTTR()` at l.32-34, runs correlator thread synchronously on a test photon file, checks curve and split averaging; so it constructs the Qt GUI). Also `test/gui/test_chiplot.py:518` lists `tttr_correlate.gui` among modules whose `cp.Plot` calls are covered (import/AST coverage).
- Recommendation: **retire/merge into `fcs/fcs_correlator`** (same function, TTTR file -> correlation curve, and it is already spec-based) unless the owner wants it kept; if kept, **port as Type B** (spec form for controls, one emtk plot, the `Correlator` logic moved to a QThread-free function reusing the l.74-190 science; roughly 2-3 days, blocked on the `SpcFileWidget` replacement and `ExperimentalDataSelector`). Decide before anyone ports; fcs_correlator being Type C too means it should be audited first.
- Commands: `cat -n .../tttr_correlate/{__init__,gui}.py`; `wc -l` on .ui files; `grep -o 'class="Q[A-Za-z]*"' *.ui | sort | uniq -c`; `git status --short -- chisurf/plugins/tttr/tttr_correlate` (clean); board grep: no claim.

## tttr_histogram

- Manifest: `chisurf/plugins/tttr/tttr_histogram/manifest.json` -> `"script": "__init__.py"` (display name "TTTR:Generate Decay").
- Launch: `__init__.py:29-33`: `window = HistogramTTTR(); window.show()`. `HistogramTTTR` at `gui.py:33` (`@persist_plugin_state`, `@init_with_ui("tttr_histogram.ui")`, bases `QWidget` and `chisurf.core.curve.CurveGroup`).
- Qt: yes, a full window. Widgets: `HistogramTTTR` (QSplitter, 2 QDockWidget, QScrollArea from `tttr_histogram.ui`), `TcspcTTTRWidget` (gui.py:95, `tcspcTTTRWidget.ui`: selection-expression QLineEdit, dt-min QDoubleSpinBox + QCheckBox, inverted QCheckBox, TAC-divider QComboBox, read-only QLineEdits for nTAC/dt/photons/channels, "make decay" QPushButton), `SpcFileWidget`, `ExperimentalDataSelector` (tcspc-type), `cp.Plot()` (log-y decay plot). No QFileDialog/QMessageBox in this file.
- Qt LOC: `gui.py` 211 + `tttr_histogram.ui` 220 + `tcspcTTTRWidget.ui` 329 = 760. The histogram science is `TcspcTTTRWidget.make_histogram` (gui.py:151-183, about 30 lines).
- Not headless; a real window.
- chisurf.gui imports (gui.py:13-18): `chisurf.gui.decorators`, `chisurf.gui.widgets.experiments.widgets`, `chisurf.gui.widgets.fio` (`SpcFileWidget`), `from chisurf.gui import QtWidgets`, `from chisurf.gui import chiplot as cp`, `chisurf.gui.misc_helpers.persist_plugin_state`.
- emtk equivalent: exists. `chisurf/plugins/tttr/microtime_histogram` has `entrypoints.emtk = chisurf.plugins.tttr.microtime_histogram.gui.app:create_app` (plus Qt `wizard:MicrotimeHistogram` and cli). Also `tttr_toolbox` (emtk) covers decays. Functionally the same: TTTR file + channel/routing selection -> microtime (decay) histogram curve. Not line-by-line verified: whether `microtime_histogram` exposes the selection expression (`ROUT==n`) and the inter-photon-gap mask (dt-min / inverted) of `make_histogram`; check before retiring.
- Tests: `test/gui/test_gui_tools.py:13,24-25,73-86` (constructs `HistogramTTTR()` via qtbot, loads BH132 .spc, clicks make-decay button); `test/gui/test_gui_tool_tttr_histogram.py` (49 lines, `Tests.setUp` constructs `HistogramTTTR()` at l.27-29, same scenario); `test/gui/test_chiplot.py:517` lists the module. All three construct the Qt GUI.
- Recommendation: **retire/merge into `tttr/microtime_histogram`** (emtk app already exists); first confirm it covers the selection-expression and min-gap filter, and if not add those controls there rather than porting this tool. No separate port.
- Commands: `cat -n .../tttr_histogram/{__init__,gui}.py`; `.ui` class counts as above; `grep -A4 entrypoints chisurf/plugins/tttr/microtime_histogram/manifest.json`; `git status --short -- chisurf/plugins/tttr/tttr_histogram` (clean); board grep: no claim.

## Context

- `git status --short` for all three plugin directories returned empty: tree is clean, no other agent's work in them.
- `grep -nE "screenshot|tttr_correlate|tttr_histogram" okf/agent-board.md`: no claim on any of the three ids (matches are docs-screenshot and ndxplorer io entries).
- PRD wording asked for two lines in `okf/plugins/emtk-migration-inventory.md` "Where to pick this up"; that file was deliberately not edited (another stream's untracked file). The summary table above is the material for those lines.

## Reviewer notes (2026-09-30)

Verified against the source: the launch classes and line numbers (`screenshot/__init__.py:52`,
`tttr_correlate/gui.py:367`, `tttr_histogram/gui.py:33`), both script launch hooks
(`if __name__ == "plugin"`), and that `tttr/microtime_histogram` declares `entrypoints.emtk`.

**"Retire `tttr_histogram`" is not yet proven.** `grep -n "ROUT\|selection\|expression"` over
`microtime_histogram/gui/app.py` finds routing channels and burst selections only, no selection
expression (`ROUT==n`) and no min-gap mask. Until feature parity is checked control by control
(`test.gui.emtk_port_parity` inventory of both tools), treat the recommendation as "merge
candidate", not "retire". `fcs_correlator` must be audited before `tttr_correlate` is decided.
