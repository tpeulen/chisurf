---
type: Subsystem
title: Fit window (one emtk surface)
description: A fit window's content -- plot pages, their tabs and dock regions, the data table, the report and the Code face -- is one emtk surface hosted in the Qt MDI frame.
resource: chisurf/gui/widgets/fitting/
tags: [gui, emtk, fitting, plots, code-editor, data-table]
timestamp: '2026-10-05T00:00:00Z'
---

# Fit window

## Where to pick this up

State 2026-10-06: **no Qt below the fit window's frame and the options dock's
frame.** A page (`plotbase.Plot`) is a plain object -- not a `QWidget` -- that
declares what the surface draws (`emtk_draw` / `add_panel` / `emtk_body`); its
*Plot settings* are an AutoForm spec (`settings_view`) over a plain model, drawn
by `emtk.view_form.draw_form` in the one emtk surface of the main window's
**Plot settings** dock (`chisurf/gui/plots/emtk_settings.py`,
`PlotSettingsHost`, one per options layout via `host_in`). Qt controllers per
page, the hidden widget holder, the island overlay and the Qt-layout
translator in `emtk_page.py` are gone. Dead `MolView`, `GlobalEt`,
`_qwt_compat`, the Qt `FitTablePlot` and `table_plot.py` were deleted.
Migration evidence (control inventory before/after, PNGs, both capture
scripts): `okf/validation/fit-window-settings/`.

Open, in order:

1. **Saved state compatibility is by key, not tested on old projects.** Every
   page's `get_settings_state` keeps its old controller's keys (stored under
   `"controller"`), so a project saved before 2026-10-06 should restore; only
   the LinePlot and ProteinMC round-trips are tested. Re-derive: load an old
   `.cs.pto` with plot state through `test/gui/restore_probe/session_probe.py`.
2. **`test/test_ui_schemas.py` was red before this change (71 failures at
   `3b4f8b6db`).** The scheme is generated from the Qt loader's dataclasses and
   lagged emtk's dialect. This change taught it emtk's documented layout keys
   (`_EMTK_LAYOUT_KEYS` in `chisurf/core/dataspec/schema.py`: width, weight,
   min_width, min_chars, wrap_before, wrap_indent, elide, field, hidden_when,
   filter); every plot spec passes. Still rejected across other specs: `name`
   (127), `dock` (91), unknown section types (61), `tab`, `window`, `page`,
   `panels` -- emtk's docking/window dialect, which needs a decision on how it
   enters the scheme rather than more keys.
3. **Figure 24 of `docs/manual/reference_curves.md`** is still the Qt-era grab
   showing a "Use reference" checkbox; the text now names the **Reference**
   selector. A faithful figure needs a FRET fit with a donor-only reference
   dataset in `docs/guides/screenshots/fit_window_emtk.py`.
4. **emtk view_form: a `weight: 0` `info` leaf inside an `n_col` panel
   collapses to zero width** (seen on the ProteinMC network settings, worked
   around with `width: 70`). Fix belongs in emtk with a test.
5. **FitInfo drops only local files**: the emtk host passes local paths, so a
   dropped URL (the Qt table took text drops) is not taken.
6. **Order-dependent GUI failures, not from this change.** Run together, the
   44 page/fit-window test files fail `test_project_reset_and_ranges` (16
   setup errors), two `test_classic_tcspc_editor` tests and two
   `test_fit_window_emtk` tests (fit-range drag, read-only source) -- the same
   set on a clean worktree at `3b4f8b6db`, and every one passes in its own
   file (a deleted `Main` left in `cs.cs` by an earlier test). Only on this
   tree, once, `test_project_ui_capture_contract[inprocess-proxies]` failed in
   the combined run; it passes alone -- re-check it first if it recurs.

**Measure** -- `pytest test/gui/test_fit_window_pages_all_models.py --run-slow`
(about 17 min) opens the real science of all 42 catalogued models in a real
`Main`, visits every page and fails on a page object that is a `QWidget`, a
page that declares nothing to draw, or settings that raise while drawn
(`PlotSettingsHost.surface.last_error`); it writes a PNG of every page and of
its settings. Trap: a page that never becomes current is never built; the
probe visits each tab, which is why it is slow.

**Tried and reverted** -- the earlier attempt (`FitPlotsArea(DockArea)`,
2026-10-04) kept the Qt `DockArea` of `QTabWidget`s and Qt containers and
added an emtk `FitTabBarControl` that nothing drew; the OKF note describing it
as "an EMTK tab bar inside ControlHost" was wrong. Styling a Qt dock area dark
is not an emtk port: the test is what `findChildren(QWidget)` shows inside the
window -- now exactly one `ControlHost`.

## What it is

`FitSubWindow` (`fit_subwindow.py`) is a Qt MDI sub-window: its title bar
(name, **Code**/**Plots** toggle, minimise/maximise/close) is Qt chrome. Its
content is `FitPlotsArea` (`fit_plots_area.py`): one
`emtk.qt_host.ControlHost` over `FitWindowSurface`, an `emtk.app.ImApp` that
draws

* the **pages** as windows of an `emtk.docking.DockManager`: tabs in one
  region by default; a tab dragged onto a region edge splits it, dragged off
  floats it. The layout is saved per model class
  (`~/.chisurf/fit_window_dock_layouts.ini`) and in the project
  (`dock_layout`, type `emtk_fit_window`); a Qt-era layout is ignored;
* each page's **body** with `emtk.im.host_control` (emtk `bb4cce6`): every
  page that is in view (the front tab of every region) is filled and
  refreshed, not only the current one;
* a **right-click menu** on any chiplot panel: Export data as CSV…, Export
  image…, Auto-range, plus the plot's own `add_menu_action` entries;
* the **Code face** (`fit_code_face.py`) in place of the plots when toggled.

`FitPlotsArea` keeps the call surface the rest of ChiSurf used for
`plot_tab_widget` (`addTab`, `count`, `widget`, `currentIndex`,
`setCurrentIndex`, `tabText`, `currentChanged`, `layoutChanged`,
`get/set_layout_state`, `update`), answered from the surface.

## Frame cost

Measured 2026-10-05 on the IBH sample decay, Fit page 1100x750, Qt painter:
**51 ms a frame before, 9.6 ms after (13.8 at 2x)**. The cost was emtk's line
drawing, fixed in emtk `62c7d5f` (vectorised mapping, per-pixel-column
thinning, one painter call per series, 1 px pen sweep instead of Qt's wide-pen
outline). Re-measure with a repaint loop around `FitPlotsArea.host` and a
`cProfile` of `surface.draw`; idle cost is zero frames (nothing animates).
Trap: Qt's wide antialiased/joined pens are the expensive path (126 ms on four
noisy decays at 2x, round joins 605 ms) -- keep plot pens out of it.

## Page bodies

`chisurf.gui.plots.emtk_page.page_body(page)` reads what a page declares:

| The page declares | On the surface |
|---|---|
| `emtk_draw(box)` | the page draws itself in immediate mode (MFD map, posterior pages, What-if, Data table) |
| `add_panel(...)` (`emtk_panels`) | a `PaneStack` of the declared `cp.Panel`s weighted by stretch; each canvas wrapped in `PanelItem` (box + owning panel for the right-click menu) |
| `emtk_body()` | the page's own control (LinePlot: a golden-ratio `PaneStack`, split saved in the project; FitInfo: the report's `TextEditor`) |
| nothing | reported in `missing`; the surface says so in red and the sweep fails |

## Plot settings

The main window's **Plot settings** dock holds one `PlotSettingsHost`: Qt hosts
an emtk `ImApp` that draws `page.draw_settings()` for the current page -- by
default `draw_form(settings_spec(), settings_model(), settings_form)`.
`FitSubWindow.on_change_plot` and the main window's sub-window activation call
`show_plot_settings()`; a closed window releases the dock. A page's settings
spec lives beside its module (`lineplot/lineplot_settings.view.json`,
`fitinfo_settings.view.json`, ...); what a spec cannot say is a `custom`
section the page registers (`register_settings_sections`): LinePlot's
reference-transform parameters, Distribution's option tree. Files dropped on
the dock go to the page's `on_paths_dropped` (FitInfo's External data).
A value that changes under the form (playback frame) calls
`request_settings_redraw()`.

Repaints: chiplot canvases, text views and the table page take
`set_refresh_target(callback)`; the surface installs its `request_frame`, so a
new curve shows without waiting for input.

## Pages ported with this change

* **Fit** (`LinePlot`): the Qt `DockSplitter` became a `PaneStack`; the
  golden split holds through resizes by weight (no re-apply on resize).
* **Data table**: `FitTablePlotEmtk` is the only `fit_table` page (the
  `gui.plot.fit_table` / `CHISURF_FIT_TABLE_BACKEND` selector is gone). It
  gained the Qt page's table tools: Columns, Hide empty, Shade, ∥ (shade
  scope), Export CSV, with tooltips (emtk `10de583`).
* **Parameter scan**: the single-tab Qt `DockArea` around one panel is gone;
  its tab text "Chi2-Surface" is the panel title.
* **MFD map**: a chiplot image on the real axes with emtk selectors, instead of
  the Qt `ImageMapWidget`.
* **State scheme** (`StateSchemePlot`, FCS kinetics, ICS, MFD 2D):
  `chisurf/gui/plots/state_scheme_emtk.py` -- a Qt-free `SchemeBinding`
  (scheme from the model in either shape, rates, presets, load/save) and an
  emtk `SchemeCanvas` drawing the `graph_canvas` marks (grid, gradient discs,
  curved arrows, rate badges, `k_exc`) with drag node / bend arc / pan / wheel
  zoom about the pointer, double-click a badge to type a rate (Enter writes it
  and recomputes the fit). The default layout follows the canvas size until the
  user arranges it. The AutoForm *form* section (`StateSchemeWidget`) is still
  Qt; it is not in a fit window.
* **Code face**: emtk `TextEditor` tabs (model source + its `view.json`),
  toolbar (assistant 🤖, back/forward, File:, Jump to:, Save/Apply), find bar
  (Ctrl+F), go to definition (Ctrl/Cmd-click, F12; local then imported
  module), coding assistant panel (the Code Editor's `ChatGui`). Save/Apply on
  a read-only install writes `<module>__override__<timestamp>.py`, the name
  `inject_user_models()` applies at the next start; it used to write
  `<file>_<timestamp>.py`, which nothing read, and would `exec` a saved
  `view.json` as Python.

## Evidence

Before/after PNGs and the control inventory are in the change's log entry
(`okf/log.md`, 2026-10-05). Tests: `test/gui/test_fit_window_emtk.py` (real
Qt input into the host: tab clicks, wheel zoom, region drag moving
`fit.fit_range`, bar drag saved in the project, right-click menu, a second
region's page filled, layout round-trip and per-model persistence, Code face
typing/jump/back/apply, read-only override naming),
`test/gui/test_fit_plots_area.py`, `test/gui/test_fit_first_use.py`,
`test/gui/test_table_plot_emtk.py`, `test/gui/test_mfd_surface.py`, and the
slow all-model sweep above.

Related: [chiplot](/subsystems/chiplot.md), [GUI & AutoForm](/subsystems/gui-autoform.md),
[user models](../../docs/reference/user_models.md).
