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

Done 2026-10-05: emtk pushed at `d8caa62` and `pixi.lock` pinned to it
(chisurf `91a18474d`). On the way: emtk `689f9d9` had wrongly taken back
another lane's committed selectable-icon work (reverted in `649d47b`), and its
atlas guard was red since `601d02d` (fixed in `d8caa62`).

0. **Exit crash of `test/gui/test_fit_window_emtk.py`** (all tests pass, then
   SIGSEGV/SIGBUS at interpreter exit). Native backtrace (lldb):
   `dealloc_QApplication -> sip_api_visit_wrappers -> cleanup_qobject` reading
   freed memory: some Qt wrapper outlives a Python object it needs at session
   teardown. Intermittent on a clean HEAD worktree (1 in 2 at `09673456f`),
   every run with other lanes' uncommitted work in the tree. Not from the grid
   toolbar (A/B), not the top-level guard test (excluded, still crashes).
   **Tried and reverted:** flushing `DeferredDelete` in the fixture teardown --
   made it worse (2 errors + crash). Next: run under lldb with
   `PYTHONMALLOC=debug`, find which wrapper's type is freed (the runtime-built
   `ControlHost` class from `emtk.qt_host.host_class()` is the suspect).
1. **Port `ProteinMCStructurePlot`** (ProteinMC). Its `Viewer` is a 3-D OpenGL
   widget, also an island today. Offscreen grabs of it are black, before and
   after this change, so judge it on a display or port it to chimol's emtk
   viewer first.
2. **Remaining Qt inside a plot page object.** Pages are still built as
   `plotbase.Plot` `QWidget`s whose chiplot panels sit in hidden Qt layouts.
   The surface reads that composition (`chisurf/gui/plots/emtk_page.py`), so
   a page needs no code to appear. The next step is Qt-free page objects that
   declare their panels directly. Measure with the sweep: every page's
   `missing` list is `[]` except the two islands.
3. **Plot controllers** (the "Plot settings" dock: `LinePlotControl` `.ui`,
   `ParameterScanWidget`, `DistributionPlotControl`, the FitInfo Analysis/
   Metadata/External/Export tabs) live in the main window's options panel,
   *outside* the fit window, and are still Qt. They were out of this change's
   scope ("plots in fit windows"); they are the next GUI surface to move.

**Measure** -- `pytest test/gui/test_fit_window_pages_all_models.py --run-slow`
(about 12 min) opens the real science of all 42 catalogued models in a real
`Main`, visits every page, and fails on any page not drawn in emtk unless its
plot class is in `QT_PAGES`. On 2026-10-05: 236 pages, 15 plot classes, every
page drawn by emtk except `ProteinMCStructurePlot` (1 model).
`StateSchemePlot` was ported the same day (below). Trap: a page that never becomes current is never
built; the probe visits each tab, which is why it is slow.

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

`chisurf.gui.plots.emtk_page.page_body(page)` turns a plot page into one emtk
control, reading the page's existing composition:

| In the page | On the surface |
|---|---|
| chiplot `Plot` (emtk backend) | its `EmtkCanvas`, wrapped in `PanelItem` (box + owning plot for the menu; fills the panel background its host used to) |
| `QBoxLayout` / `QSplitter` | `emtk.widgets.PaneStack` (emtk `4bfdadf`) weighted by stretch / sizes |
| `QGridLayout`, chiplot `Grid` | rows of side-by-side panes, weighted by the grid's stretch factors |
| `EmtkTextView` | its `TextEditor` |
| any emtk `ControlHost` | the control it hosts (e.g. `FitTablePlotEmtk`) |
| `emtk_body()` | the page's own control (LinePlot: a golden-ratio `PaneStack`, split saved in the project) |
| `emtk_draw(box)` | the page draws itself in immediate mode (MFD map: channel/colormap combos over the panel) |
| anything else | reported in `missing`; the page becomes an island |

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
