---
type: PRD
prd: "64"
title: "PRD-64: chiplot — single plotting seam and pyqtgraph replacement"
description: Route every plotting access through one dependency-neutral chiplot facade so pyqtgraph becomes a swappable backend, then grow chiplot into a native OpenGL/immediate-mode renderer behind the same API.
status: in-progress
phase: "unassigned"
resource: chisurf/gui/chiplot/
tags: [prd, gui, plotting, architecture]
timestamp: '2026-07-24T00:00:00Z'
---

# Summary

PRD-64 introduces **chiplot**, a single facade package (`chisurf.gui.chiplot`)
through which **all** plotting is accessed. Today ~125 modules import
`pyqtgraph` directly and reach for ~40 distinct symbols (`mkPen`, `PlotWidget`,
`TextItem`, `LinearRegionItem`, …), scattering a hard third-party dependency
across the whole GUI and every plugin. This PRD collapses that surface to one
seam: call sites change from `import pyqtgraph as pg` to
`import chisurf.gui.chiplot as cp`, pyqtgraph moves behind a single backend
module that is the *only* place allowed to import it, and a CI guard keeps it
that way.

The seam is **API-compatible** with pyqtgraph (same symbol names and item
methods) so migration is mechanical and low-risk, and pyqtgraph stays the engine
initially — nothing about the rendered output changes. The long-term objective
is to grow chiplot into a **native ChiSurf plotting library** with an
OpenGL renderer (and an immediate-mode/imgui control surface where appropriate),
selectable as an alternative backend behind the identical facade, so individual
plots can flip over incrementally and pyqtgraph can eventually be dropped.

This is the plot-canvas counterpart to [PRD-42](prd-42.md), which removes
pyqtgraph's *non-plot* uses (`SpinBox`, `parametertree`). PRD-42 makes pyqtgraph
"plot-only"; PRD-64 then puts that plot-only surface behind one swappable seam.

# Status

In-progress. **Phase 1 has landed**: the `chisurf.gui.chiplot` package exists
with a clean, renderer-neutral API (`Plot`, `Grid`, style value objects, handle
protocols), a working pyqtgraph backend behind a formal `Backend` contract, a
CI guard (`test/test_pyqtgraph_seam.py`) with a shrinking allow-list migration
tracker, and headless tests. One real widget (`waterfall_plot.py`) is migrated
as proof. Phases 2–4 (migrate the remaining ~75 chisurf files + `modules/`) and
Phase 5+ (native OpenGL backend) remain.

**Design decision (revised).** The seam is *not* a pyqtgraph-shaped re-export.
Per the maintainer's direction, chiplot exposes a **clean, purpose-built API**
that can genuinely replace pyqtgraph — verb-first drawing, color-likes
everywhere, behaviour flags instead of item subclassing, backend-neutral
events — see [Design](#design). This raises migration churn versus a re-export
but is the whole point: the goal is to *get rid of* pyqtgraph, not to enshrine
its API.

# Goal

1. **One seam.** Exactly one module imports `pyqtgraph`
   (`backends/pyqtgraph_backend.py`); every other module reaches plotting
   through `chisurf.gui.chiplot`. Enforced by a CI guard.
2. **A clean API worth keeping.** chiplot's surface is designed for ChiSurf's
   real plotting patterns, not inherited from pyqtgraph — so it remains the API
   after pyqtgraph is gone.
3. **Swappable backend.** The facade selects a backend at import time
   (`CHISURF_PLOT_BACKEND`); a native chiplot backend can be added later without
   touching call sites.
4. **A path to native.** The handle/canvas Protocols *are* the contract the
   OpenGL/immediate-mode renderer must satisfy to replace pyqtgraph plot-by-plot.

Non-goal for the first landings: writing the native renderer. That is the
long-term payoff the seam unlocks, tracked as Phase 5+ here.

# Motivation

- **Dependency blast radius.** A hard, heavy third-party library is imported in
  ~125 files. Any version pin, API break, Qt-binding incompatibility, or
  packaging problem in pyqtgraph touches the entire GUI with no chokepoint to
  adapt at. A single seam turns "125 edits" into "one edit."
- **Import cost & coupling.** Plot uses and (historically) non-plot uses of
  pyqtgraph are interleaved through the widget tree, making the dependency hard
  to reason about and slow to import. PRD-42 removes the non-plot uses; PRD-64
  isolates the rest.
- **No room to evolve rendering.** pyqtgraph is CPU/QPainter-based. Large
  TCSPC/FCS/burst datasets and imaging overlays (waterfalls, phasor clouds,
  scatter with 10^5–10^6 points) are exactly where a GPU renderer wins. Today
  there is nowhere to put an alternative renderer without editing every plot.
- **Precedent.** [PRD-57](prd-57.md) already migrates the ChiMOL 3-D renderer to
  an immediate-mode GUI backend behind a Qt-free controller/scene contract. The
  same "controller/scene behind a stable contract, renderer swappable" shape is
  what chiplot brings to 2-D plotting.

# Current state — the surface to confine

`import pyqtgraph as pg` appears across the codebase (chisurf core GUI,
every plugin group, `modules/ndxplorer` and `modules/quest`, and tests). The
symbols actually used cluster into a small, stable API:

| Category | Symbols (usage-ranked) |
|----------|------------------------|
| Pen/brush/color factories | `mkPen`, `mkBrush`, `mkColor`, `intColor`, `colormap` |
| Config / app | `setConfigOptions`, `setConfigOption`, `getConfigOption`, `mkQApp`, `Point` |
| Plot containers/widgets | `PlotWidget`, `GraphicsLayoutWidget`, `PlotItem`, `ViewBox`, `GraphicsView`, `AxisItem` |
| Line/scatter/bar data items | `PlotDataItem`, `PlotCurveItem`, `ScatterPlotItem`, `BarGraphItem`, `ErrorBarItem`, `FillBetweenItem`, `GraphItem` |
| Annotation/interaction items | `TextItem`, `LinearRegionItem`, `InfiniteLine`, `InfLineLabel`, `ArrowItem`, `LabelItem`, `LegendItem` |
| Image items | `ImageItem`, `ImageView`, `HistogramLUTItem` |
| ROIs | `RectROI`, `CircleROI`, `ROI` |
| Subclassing base classes | `GraphicsObject`, `GraphicsItem`, `GraphicsWidget` |
| Misc | `exporters`, `graphicsItems`, `QtCore` |

Instance-level API in wide use (must be preserved by any backend):
`PlotWidget.plot()`, `.addItem()/.removeItem()`, `.clear()`, `.setLabel()`,
`.setLogMode()`, `.setXRange()/.setYRange()/.setRange()`, `.enableAutoRange()`,
`.autoRange()`, `.showGrid()`, `.addLegend()`, `.setBackground()`,
`.getPlotItem()`, `.getViewBox()`, `.setTitle()`; item `.setData()`,
`.setPen()`, `.setBrush()`, `.setImage()`, `.setRegion()`, and signals
(`sigRegionChanged`, `sigClicked`, …).

### Cases handled outside this PRD

- **DockArea** — already wrapped by `chisurf.gui.widgets.dock_area.dock_area`;
  call sites use that, not `pyqtgraph.dockarea` directly. No change needed; the
  wrapper simply becomes another chiplot consumer.
- **Raw OpenGL / 3-D** — confined to the ChiMOL plugin
  (`pyqtgraph.opengl`), whose renderer migration is owned by
  [PRD-57](prd-57.md). Out of scope here; chiplot 2-D does not subsume it,
  though both share the OpenGL direction.
- **Non-plot widgets** (`SpinBox`, `parametertree`) — owned by
  [PRD-42](prd-42.md). PRD-64 assumes those are gone (or in flight) and does
  **not** re-expose them through the plotting facade.
- **`modules/` (`ndxplorer`, `quest`)** — separate source trees with their own
  git repos. They migrate to chiplot on the same contract but are tracked as a
  follow-up wave, not gated with the chisurf-core landings.

# Design

## Package layout (as built)

```
chisurf/gui/chiplot/
  __init__.py                 # public API: Plot, Grid, styles, enums, configure()
  style.py                    # Color, Pen, Brush, Colormap, LineStyle + coercers
  handles.py                  # Protocols: Curve, Scatter, Bars, ErrorBars, Image,
                              #   Region, Marker, Text (+ Symbol, Orientation)
  canvas.py                   # Plot(QWidget), Grid(QWidget), PanelPlot
  backends/
    __init__.py               # backend registry + selection (CHISURF_PLOT_BACKEND)
    base.py                   # Backend / Canvas / GridCanvas ABCs — the contract
    pyqtgraph_backend.py       # the ONLY module allowed to `import pyqtgraph`
    # (future) opengl_backend.py — native OpenGL / immediate-mode renderer
```

- **`style.py`** — small immutable value objects replacing `mkPen`/`mkBrush`/
  `mkColor`/`intColor`/`colormap`. `to_color` accepts names, `#rrggbbaa` hex,
  0–255 or 0–1 tuples, packed ints, `QColor`, and the pyqtgraph/matplotlib
  single-letter codes (`"r"`, `"g"`, `"c"`, …) for painless migration. No
  rendering import — usable from Qt-free code.
- **`handles.py`** — `Protocol`s for each drawn element (verb-oriented:
  `set_data`, `remove`, `value`/`bounds`, `on_change`), **not** a mirror of
  pyqtgraph's item classes. These are the renderer contract.
- **`canvas.py`** — `Plot`/`Grid` `QWidget`s that embed the active backend's
  canvas, so they drop in wherever a `pg.PlotWidget` went. Fluent, chainable
  axis setters; `clicked`/`mouse_moved` Qt signals in **data coordinates**.
- **`backends/base.py`** — the `Backend`/`Canvas`/`GridCanvas` ABCs a renderer
  implements. **`backends/pyqtgraph_backend.py`** is the sole pyqtgraph importer;
  it also centralises global config via `configure(...)`.

## What the clean API looks like (vs pyqtgraph)

| Task | pyqtgraph (before) | chiplot (after) |
|------|--------------------|-----------------|
| Line | `pw.plot(x, y, pen=pg.mkPen("r", width=2))` | `plot.line(x, y, pen="r", width=2)` |
| Region + signal | `r = pg.LinearRegionItem(...)`; `pw.addItem(r)`; `r.sigRegionChangeFinished.connect(cb)` | `r = plot.region((a, b))`; `r.on_change(cb)` |
| Movable cursor | `pg.InfiniteLine(angle=0, movable=True, pen=pg.mkPen("y"))` | `plot.hline(y, movable=True, pen="y")` |
| Draggable text | subclass `pg.TextItem`, override 3 mouse events | `plot.text(s, pos, draggable=True)` |
| Click in data coords | `pw.scene().sigMouseClicked` + `vb.mapSceneToView(...)` | `plot.clicked.connect(cb)` |
| Multi-panel | `pg.GraphicsLayoutWidget`; `.addPlot(row, col)` | `Grid()`; `.add_plot(row=…, col=…)` |

Behaviours that previously *required subclassing pyqtgraph items* (draggable
text, custom-styled `GraphicsLayoutWidget`s) become **flags/methods**, which is
what lets a non-pyqtgraph backend satisfy the same contract.

## Rich right-click menu + export

Every `Plot` carries a rich context menu at pyqtgraph parity. On the pyqtgraph
backend chiplot **keeps** the native viewbox menu (which already offers
Export → CSV / image / SVG / Matplotlib) and *injects* its own
`Export data as CSV…` / `Export image…` entries plus any
`plot.add_menu_action(label, cb)` custom entries into it. A backend that ships
no native menu (a future OpenGL renderer) gets an equivalent chiplot-built menu
via `contextMenuEvent`. Programmatic `plot.export_csv(path)` (every drawn
line/scatter series, padded columns) and `plot.export_image(path)` (backend
`ImageExporter`, else a widget grab) back the actions and are usable headlessly.

## Passthrough (migration safety net)

chiplot's native surface does not yet cover every pyqtgraph feature in use.
Rather than block migration on full coverage, **anything chiplot does not offer
natively falls through to the backend's raw library — flagged**:

- **Module level** — `chisurf.gui.chiplot.__getattr__` resolves unknown names
  (`mkPen`, `PlotWidget`, `LinearRegionItem`, …) from `Backend.raw_module()`
  (pyqtgraph).
- **Instance level** — a native `Plot`/`ImageView`/`Grid` and every handle proxy
  unknown attribute *reads/calls* (`getViewBox`, `setLogMode`, `.setData`, …) to
  their underlying backend object.

**Coverage — near-total for real usage.** Passthrough forwards to the native
object: (a) all *reads/calls* chiplot lacks natively (`.setData`, `.getViewBox`,
`.sigClicked`, …); (b) *attribute assignment on handles* (`item.attr = x`);
(c) *container/dunder protocols on handles* (`len`, `[]`, iteration; `bool` is
always `True`). The one shadowed name that real code hits — `colormap` — is a
**hybrid**: `cp.colormap("viridis")` returns a chiplot `Colormap` while
`cp.colormap.get(...)` proxies to pyqtgraph. Two deliberate, unused-in-practice
exceptions remain: attribute *assignment on the `Plot`/`Grid`/`ImageView` widget
wrappers* is not forwarded (overriding `__setattr__` on a live `QWidget` risks
native-teardown segfaults, and pyqtgraph code sets attributes on *items*, not
the plot widget), and chiplot's own `Color`/`ImageView` class identity differs
from pyqtgraph's (no call site does `isinstance(x, pg.Color/pg.ImageView)`). The
migration path is still a real port to the chiplot API with `.native` for the
rare pyqtgraph-specific case; passthrough keeps a partially-ported file running
at parity.

Every fall-through raises a `ChiplotPassthroughWarning` **once per symbol** and
is recorded; `chiplot.passthrough_gaps()` returns the exact set of pyqtgraph
features still lacking a native equivalent — the concrete worklist for growing
the API and a natural companion to the allow-list. When a fully native backend
(Phase 5) returns `raw_module() is None`, any remaining passthrough is a hard
`AttributeError` — so the gaps must all be closed before pyqtgraph is dropped.

## Handle mutation is method-based (guard interop)

Handle *reads* are properties (`marker.value`, `region.bounds`) but *writes* are
methods (`marker.set_value(x)`, `region.set_bounds(lo, hi)`) — deliberately.
The repo's forbidden-communication guard (`test/test_forbidden_communication.py`)
reserves assignment to `value`/`bounds`/`fixed`/`link` attributes for fit-
parameter mutations; a property setter on a chiplot handle would collide as a
false positive across every marker/region call site. Method-based mutation keeps
chiplot orthogonal to that guard.

## Backend swap & escape hatch

`get_backend()` instantiates the backend named by `CHISURF_PLOT_BACKEND`
(default `pyqtgraph`) once per process; `set_backend(name)` overrides it.
During migration a handful of advanced call sites may still need the raw
pyqtgraph object — every `Plot`/handle exposes a `.native` escape hatch for
that, which the CI guard treats as the seam (the object comes from the backend,
not a direct import). New code must not use `.native`.

## CI guard

`test/test_pyqtgraph_seam.py` scans `chisurf/` and asserts `import pyqtgraph` /
`from pyqtgraph` appears **only** in `backends/pyqtgraph_backend.py`, with every
other current importer listed in `test/pyqtgraph_import_allowlist.txt`. Two
assertions keep the tracker honest: a **new** direct importer not on the list
fails (regression guard), and a listed file that no longer imports pyqtgraph
fails (stale-entry guard, forcing the list to shrink as files migrate). "Done"
is an empty allow-list (bar the ChiMOL OpenGL module owned by PRD-57).

# Migration plan

**Phase 1 — clean API + pyqtgraph backend + guard. ✅ DONE.**
Built the `chiplot` package (`style`, `handles`, `canvas`, `backends/{base,
pyqtgraph_backend}`), backend selection via `CHISURF_PLOT_BACKEND`, the CI guard
(`test/test_pyqtgraph_seam.py`) seeded with the current importer list
(`test/pyqtgraph_import_allowlist.txt`, 76 files), and headless tests
(`test/gui/test_chiplot.py`) exercising every draw family, handle updates,
region/marker values, removal/re-add, grid panels, and the click signal.
Migrated `chisurf/gui/widgets/waterfall_plot.py` end-to-end as proof.

**Phase 2 — migrate chisurf-core GUI. 🚧 IN PROGRESS.**
Rewrite `chisurf/gui/**` call sites onto the chiplot API. This is a genuine
port, not a prefix rename: `pw.plot(x, y, pen=pg.mkPen(...))` → `plot.line(...)`,
`LinearRegionItem`+`addItem`+signal → `plot.region(...).on_change(...)`,
subclassed items → behaviour flags. Only files whose `pg` is actually pyqtgraph
are touched (some modules use `pg` as a parameter-group variable). Remove each
file from the allow-list as it lands. Run `pixi run test-gui` and the headless
screenshot/qtbot verification after each cluster.
*Landed so far (allow-list 76 → 25):*
- **Batch 1** — centralised the global pyqtgraph config (`gui/__init__.py`,
  `plots/__init__.py`) onto `cp.configure(...)`; migrated the single-plot preview
  widgets (PCH, TCSPC simulator, TCSPC TTTR-reader, FCS correlator wizard).
- **Batch 2** — moved the pyqtgraph `autoRangeEnabled` compat shim out of
  `gui_tweaks.py` into the pyqtgraph backend (applied on backend load); dropped
  dead/near-dead pyqtgraph imports (`gui_tweaks`, `misc_helpers` warmup,
  `experiments/widgets.py`); migrated the `plots/lcurve` and `plots/wr_plot`
  diagnostic plots. Grew the native API with **line markers**
  (`plot.line(..., symbol=…)`) as a real call site (lcurve) demanded it.
  Deferred `plots/av_plot.py` — it is 3-D `pyqtgraph.opengl` + dockarea, owned by
  [PRD-57](prd-57.md), not 2-D chiplot.
- **Batch 3** — migrated the FCS MaxEnt L-curve model widget (`maxent_widget`)
  and the micro-time `shift_dialog`. Grew the native API with handle
  `hide()`/`show()` and `Curve.get_data()` as those call sites needed them, and
  rewired MaxEnt's scene-click onto the `Plot.clicked(x, y)` signal.
- **Batch 4** — migrated the `plots/deer_pr` P(r) confidence-band plot and the
  TCSPC `anisotropy` decay dialog. Grew the native API with
  `plot.fill_between(lower, upper, brush=…)` (confidence bands) for deer_pr.
  Deferred (need chiplot API growth, not yet ported): `plots/distribution` +
  `plots/lineplot` + `plots/residual_image` (shared draggable HTML text,
  multi-panel PlotItems, `stepMode='right'`); `experiments/rics` (`ImageView` +
  `RectROI` composites); `widgets/spectrum_view` (axis/legend theming);
  `plots/parameter_scan` (`pyqtgraph.dockarea`).
- **Batch 5** — added the **`ImageView`** capability (image + LUT histogram +
  frame slider, wrapping `pg.ImageView`) and **`Roi`** handles (`add_roi`,
  pos/size, `on_change`, overlay images, `set_interactive`,
  `set_histogram_width`); migrated `experiments/rics` onto it. This unblocks the
  remaining ImageView consumers (`autoform/builtin`, `burst_bva`, microscopy).
- **Batch 6** — extended the flagged passthrough to **every handle** (not just
  `Plot`/`ImageView`): a handle proxies unknown attribute *reads/calls* to its
  native pyqtgraph item (any item method chiplot lacks natively still works,
  flagged). This is **read-passthrough parity, not total parity** — it does not
  cover attribute *assignment*, dunder/container protocols, or the names chiplot
  shadows (`colormap`/`Color`/`ImageView`); see the [Passthrough](#passthrough-migration-safety-net)
  scope. Added `Image.clear()`. Migrated
  `autoform/phasor_section`. Deferred `burst_bva` (custom `GraphicsLayoutWidget`
  + `HistogramLUTItem`, and `pg.colormap.get` collides with chiplot's
  `colormap`).
- **Batch 7** — added `Grid` passthrough (parity for `GraphicsLayoutWidget`
  methods) and two small native params (`plot.image(axis_order=…)`,
  `plot.errorbars(beam=…)`); migrated `burst_bva`. Its plot content is clean
  chiplot (Grid panel + image + lines + errorbars); the `HistogramLUTItem` LUT
  composite stays passthrough (a flagged gap), and the `pg.colormap.get`
  collision is resolved via `cp.get_backend().raw_module().colormap.get(...)`.
- **Batch 8** (Phase 3 opener, allow-list 57 → 51) — migrated a cluster of
  single-plot plugin/widget tools with clean, uniform pyqtgraph use onto the
  native API: `plugins/pch` (region + log-hist + line/scatter),
  `plugins/fret_line` (E/τ_X overlays + diagonal reference),
  `plugins/tttr/tttr_microtime_shifter` (movable trigger `hline`/`vline` +
  step-histograms + `int_color`), `plugins/vv_vh_g_factor` (dual decay/anisotropy
  plots + signal/background `region`s), and `widgets/models/tcspc/kappa2_helpers`
  (κ²/R_app dialogs with `plot.text(...)` labels). No new native API needed —
  every call mapped to existing chiplot verbs (`line`/`scatter`/`region`/
  `vline`/`hline`/`text`/`set_log`/`legend`/`grid`). Marker/region interaction
  ports from raw `sigPositionChanged` + `blockSignals` to `handle.on_change(...,
  final=…)` (drag-only, so the block-signals dance disappears). Optional-pyqtgraph
  guards (`pg is None`) became backend-availability probes (`cp.get_backend()`).
  `plugins/tttr/tttr_time_windows` (trace + window `vline`s) was migrated the
  same way; it landed in a follow-up combined commit because its file also
  carried a concurrent i18n string-wrapping edit from another working-tree
  instance (already backed by that instance's committed `.qm`/`.ts`).
- **Batch 9** (allow-list 51 → 49) — migrated the two TTTR curve-viewer tools
  `plugins/tttr/tttr_histogram` and `plugins/tttr/tttr_correlate` onto the native
  API. Both share the same `pg.PlotWidget` + `getPlotItem().addLegend()` +
  per-refresh `plot()`/`setLogMode`/`showGrid` idiom, mapped to
  `cp.Plot()` + `plot.line(...)` + `set_log`/`grid` + `legend()`. The only API
  work was making the backend's `legend()` **idempotent** — it now removes any
  legend from a prior call before adding a fresh one, so the clear→legend→redraw
  refresh loop no longer stacks orphaned legend boxes in the scene (previously
  each tool had to `legend.close()` the old one by hand).
- **Batch 10** (allow-list 49 → 45) — migrated the microtime-histogram wizard
  (`plugins/tttr/microtime_histogram`) and the three FCS-correlator panels
  (`plugins/fcs/fcs_correlator/{correlator,filter,merger}_panel`). The
  histogram/merger tools follow the same `PlotWidget`→`cp.Plot` + `line`/
  `set_log`/`legend` map as Batch 9; `merger_panel` also dropped its hand-rolled
  `{solid,dash,dot}`→`Qt.PenStyle` table in favour of `plot.line(style="dash")`.
  `correlator_panel` used pyqtgraph only for `intColor` to tag a series dict
  consumed by the AutoForm `plot` section (still-passthrough `builtin.py`), so it
  now emits `cp.int_color(...).as_tuple()` — a plain RGBA both `cp.to_pen` and the
  legacy `pg.mkPen` renderer accept, decoupling it without touching the renderer.
  Two native additions, both driven by real call sites: **`Plot.set_menu_enabled`**
  (both filter/merger panels disabled the pyqtgraph viewbox menu via
  `getPlotItem().getViewBox().setMenuEnabled` — now a first-class seam method over
  the backend's existing `set_menu_enabled`), and **signal-safe programmatic
  mutation** — `Region.set_bounds`/`Marker.set_value` now block the native item's
  signals during the move, so `filter_panel`'s per-refresh region repositioning no
  longer needs the manual `blockSignals` dance and cannot re-enter its own
  `on_change` handler. New regression tests in `test/gui/test_chiplot.py`
  (idempotent-legend refresh loop, `set_menu_enabled`, signal-safe
  `set_bounds`/`set_value`, the union of migrated draw verbs, and import-clean of
  all four modules).
- **Batch 11** (allow-list 45 → 42) — migrated three decay/anisotropy tools:
  `plugins/fcs/fcs_lfcs_sim` (log-x FCS preview), `plugins/fluorescence_decay/`
  `tr_anisotropy` IRF background-region selector, and `plugins/vv_vh_anisotropy`
  (dual decay + r(t) plots with an r∞ region). All standard `PlotWidget`→`cp.Plot`
  + `line`/`set_log`/`set_ylim`/`legend`/`grid` + `region` verbs; the two region
  tools drop their manual `blockSignals` dance now that `set_bounds` is
  signal-safe (Batch 10), and both region callbacks take the handle's
  `(lo, hi)` directly. `fcs_lfcs_sim` keeps one flagged pyqtgraph passthrough via
  `plot.native.getAxis("bottom").enableAutoSIPrefix(False)` — an axis cosmetic
  chiplot has no native verb for yet (candidate for a future `set_auto_si_prefix`
  when a second call site appears). Import-clean test extended to all three;
  vv_vh_anisotropy constructed headless with its full redraw + region-drag path
  exercised.
- **Batch 12** (allow-list 42 → 41) — migrated the ① Compute-LUT interactive
  section (`plugins/tttr/tttr_lut_tools/gui/sections.py`). Its
  `_ComputePlotSection` subclassed `pg.GraphicsLayoutWidget` with two stacked
  plots + a draggable region and offset/threshold `InfiniteLine`s; it now
  subclasses **`cp.Grid`** and builds the panels with `add_plot(...)`, the region
  via `panel.region(...)`, and the two lines via `panel.vline`/`panel.hline`.
  Redraw replaces only the tracked data curve (`remove` + re-`line`) so the
  draggable items survive, and the model→plot sync uses signal-safe
  `set_bounds`/`set_value` — the bespoke `_syncing` re-entrancy guard is gone. New
  `test_grid_panel_region_and_markers` covers region/marker-on-panel + the
  curve-churn-keeps-items pattern; import-clean test extended. `settings_panel.py`
  (the other tttr_lut_tools file) is a separate, larger migration left for its own
  batch.
- **Batch 13** (allow-list 41 → 40) — migrated the other tttr_lut_tools file,
  `gui/settings_panel.py` (the LUT-settings dock: a microtime histogram with
  per-channel curves + two LUT-preview plots). `nice_pen` now returns a chiplot
  `Pen`; the three `pg.PlotWidget`s become `cp.Plot`s; per-channel curves are
  tracked handles updated with `set_data`/`set_pen`/`.z` and removed with
  `remove`; the "No LUT" `pg.TextItem` becomes `plot.text(...)`. Grew the handle
  contract with **`Curve.set_pen`** (real call site: the panel re-colours and
  emphasises the active channel), coercing any pen-like via `to_pen`. The
  pyqtgraph render optimisations `setDownsampling`/`setClipToView` (plot- and
  curve-level) have no chiplot verb yet and stay as flagged `.native`
  passthroughs. New `test_curve_set_pen_restyles`; import-clean extended; panel
  constructed headless with the LUT-preview redraw exercised. tttr_lut_tools now
  fully off pyqtgraph.
- **Batch 14** (allow-list 40 → 37) — migrated the AutoForm `decay_conv` section
  (`gui/autoform/sections/decay_conv_section.py`, a decay+IRF plot with three
  draggable regions — conv/IRF/BG) and the FCS-merger wizard pair
  (`gui/widgets/wizard/fcs_merger/{fcs_merger,fcs_merger_ui}.py`, two log-x FCS
  plots). `decay_conv` maps its three curves + three regions onto
  `line`/`set_data` + `region`/`set_bounds`, and — because `set_bounds` is
  signal-safe — drops its `_updating` re-entrancy flag entirely; region callbacks
  take `(start, stop)`. `fcs_merger_ui` drops the `getPlotItem()` split (chiplot's
  `Plot` exposes drawing directly, so `plot_item_*` just aliases the widget) and
  `fcs_merger` maps its per-curve `mkPen` (incl. the dashed grey "unused" pen) to
  `line(pen=…, width=…, style=…)`. Import-clean test extended to all three;
  `DecayConvWidget` constructed headless with its three region drags exercised.
- **Batch 15** (allow-list 37 → 35) — migrated the FRET-docking plugin's two
  plot widgets: `plugins/modelling/fret/gui/dock_tool.py` (per-trial score-vs-step
  curves; `pg.intColor`→`cp.int_color`, `plot`→`line`, `setData`→`set_data`) and
  `pair_selection_wizard.py` (a single ⟨RMSD⟩-vs-pairs curve). Both plain
  `PlotWidget`→`cp.Plot` + `set_labels`/`grid`/`line` maps. Import-clean extended.
- **Batch 16** (allow-list 35 → 34) — migrated the lightpath-simulator node
  spectral thumbnail (`plugins/core/lightpath_simulator/gui/node_types.py`): a
  compact per-node preview plot. Grew the seam with **`Plot.set_interactive(mouse=,
  menu=)`** (the backend already implemented it for `ImageView`; now on the Plot
  canvas too), so the thumbnail disables pan/zoom + menu in one call rather than
  reaching for the viewbox. Also removed a `TYPE_CHECKING`-only `import pyqtgraph`
  (the seam regex counts it) that no annotation used. The compact-axis cosmetics
  (`hideAxis`, bottom-axis pen/height/style) have no chiplot verb yet and stay as
  flagged `.native` passthroughs. New `test_set_interactive_returns_self`;
  `add_spectral_plot` exercised headless.
- **Batch 17** (allow-list 34 → 33) — migrated `plugins/burst/burst_2cde/gui/tool.py`
  (2CDE-vs-E scatter / histogram fallback). Plain `PlotWidget`→`cp.Plot`; the
  `plot(pen=None, symbol="o")` scatter becomes `scatter(...)` and the histogram
  `plot(stepMode=False)` becomes `line(...)`. Import-clean extended.
- **Batch 18** (allow-list 33 → 32) — migrated the node-editor
  `gui/widgets/node_editor/widgets/pt_plot_widget.py` (a small themed PT preview
  plot, an optional-pyqtgraph widget). The `pg is None` guard became a
  `_plotting_available()` backend probe; viewbox background uses
  `set_background(to_color(bg).with_alpha(a))`; grid/line/set_data map natively;
  the themed axis pens (foreground colour on bottom/left) stay a flagged `.native`
  axis-theming passthrough. **First batch verified by GUI screenshot** — the
  widget was rendered headless (offscreen `grab()`) with a damped sine and
  inspected: white curve on the themed dark background, foreground title/axes,
  subtle grid, correct 0–12 / ±0.5 ranges. New `test_pt_plot_widget_renders`
  (curve build + set_data/clear round-trip).
- **Batch 19** (allow-list 32 → 31) — migrated the reusable
  `gui/widgets/spectrum_view.py` (absorption/emission spectral overlay, also an
  AutoForm `spectrum_view` section). Trace dicts map onto `line(pen=color,
  width=, style=, name=)`; the `{solid,dash,dot,dashdot}` names now map to chiplot
  pen styles (`dashdot`→`dash_dot`); the "no spectra" `pg.TextItem` becomes
  `plot.text(...)`; `set_background(None)`, `legend()`, `grid`, units folded into
  `set_labels`. The heavy pyqtgraph theming (per-axis pen/text-pen, SI-prefix off,
  legend label colour) stays a flagged `.native`/`raw.mkPen` passthrough.
  **GUI-screenshot verified** — three overlaid spectra rendered headless and
  inspected: distinct solid/dash/dot lines, light-grey legend + axis labels, grid,
  correct 400–700 nm / 0–1 ranges. New `test_spectrum_view_plots_traces`.
- **Batch 20** (allow-list 31 → 30) — migrated `plugins/burst/burst_background/`
  `gui/sections.py` (a log-log inter-photon-time distribution with points + a
  fitted tail, and a per-detector background-rate bar chart). **Fixed a real
  chiplot bug found by GUI-screenshot inspection:** `scatter()` was backed by a
  raw `pg.ScatterPlotItem`, which **ignores log mode** — on a log plot the points
  landed at linear positions and blew the auto-range out to ~500 decades (garbage
  10²⁷³ axis labels). `add_scatter` now uses a **log-aware `PlotDataItem`** (no
  line + a symbol), so scatters transform correctly under `set_log`; this also
  retroactively fixes `filter_panel`'s log-y dt-scatter (Batch 10). The bar chart
  draws one `bars()` call per detector (chiplot `bars` takes a single brush) to
  keep per-bar colours, with detector-name tick labels via a flagged `.native`
  `setTicks`. New `test_scatter_is_log_aware`; both sections
  screenshot-verified (decaying points + tail-fit line on clean log-log axes;
  green/red/yellow coloured bars with named ticks).
- **Batch 21** (allow-list 30 → 29) — migrated `plugins/burst/burst_browser/`
  `gui/sections.py` (the per-column burst histogram is the only plotting section;
  the rest are combos/tables). `pg.PlotWidget`→`cp.Plot`, the `pg.BarGraphItem`
  becomes `plot.bars(centers, counts, width=, brush="b", pen="k")`. Import-clean
  extended; screenshot-verified (blue Gaussian FRET-E histogram, black outlines,
  correct axes). The acq cluster (`core/acq/{__init__,gui/tool,gui/windows}`) is
  deferred like maxent — windows create curves that the 3000-line `tool.py` drives
  via `setData`/`InfiniteLine`, so it needs a dedicated coordinated pass.
- **Batch 22** (allow-list 29 → 28) — migrated the self-contained
  `plugins/burst/burst_fcs_correlator/wizard.py` (a per-pair FCS browser: a log-x
  correlation plot with data markers + fit line + a diffusion-time inset label,
  and a log-x P(τ_D) distribution plot). Curves → `line(...)`/`set_data`; the
  `pg.TextItem` inset → `plot.text(...)` with the `_Text` handle's `text`
  property + `set_position`. **Second real chiplot bug found by screenshot:** the
  inset text, placed at a raw data coordinate on a log-x axis, drove the view
  auto-range out to ~10¹⁷³ (I'd dropped the original's `ignoreBounds=True`).
  Fixed at the seam — `add_text` now adds every label with `ignoreBounds=True`,
  so annotations never stretch the range. New `test_text_does_not_drive_autorange`;
  screenshot-verified (FCS correlation decay G 1.8→1.0 on a clean log-x axis).
  (The wizard imports IMP, which segfaults alongside the other heavy extensions in
  the shared chiplot test process, so it is verified standalone, not in the
  import-clean sweep.)
- **Batch 23** (allow-list 28 → 27) — migrated the legacy burst selector
  `plugins/burst/burst_selection/gui/legacy/burst_selector.py` (a per-feature
  histogram with an overlaid GMM fit). `pg.PlotWidget`→`cp.Plot`; the
  `pg.BarGraphItem(alpha=0.7)` becomes `bars(..., brush=(0,0,255,178))` (alpha
  folded into the brush); the GMM sum + dashed per-component lines use
  `line(..., style="dash")` with `cp.int_color`; `set_title`/`set_labels`/
  `legend`. Screenshot-verified (bimodal blue histogram, red GMM fit, dashed
  component curves, legend).
- **Batch 24** (allow-list 27 → 26) — migrated the self-contained
  `plugins/fluorescence_decay/irf_estimator/gui/tool.py` (1087L; a single log-y
  decay/IRF plot with mouse-tracking crosshairs and a draggable fit-range region).
  Curves → `line(...)` (solid/dashed via `style="dash"`); crosshairs → non-movable
  `vline`/`hline` with `set_value`; the range selector → `region` with
  `on_change(final=False)` + `set_bounds`, its show/hide tracked by a
  `_range_in_plot` flag (replacing `x in main_plot.items()` membership tests) and
  re-added after `clear()`. The pyqtgraph mouse-tracking internals
  (`scene().sigMouseMoved`, `sceneBoundingRect`, `getViewBox().mapSceneToView`)
  stay flagged `.native` passthroughs. Screenshot-verified (blue decay + cyan
  dashed BG-corrected + green IRF on a log-y axis, three-entry legend). Imports IMP
  transitively → verified standalone, kept out of the shared import-clean sweep.
- **`pyqtgraph.dockarea` deprecated repo-wide** — every `Dock`/`DockArea` usage now
  goes through the chisurf dock implementation
  (`chisurf.gui.widgets.dock_area.dock_area`): `plots/parameter_scan` and
  `plots/av_plot` (single-panel) use `DockArea.addTab`; `plots/lineplot`'s vertical
  residuals/a-corr/data stack uses a `DockSplitter` (titles are hidden by default,
  so it matches exactly). A new `test_no_pyqtgraph_dockarea` seam guard forbids
  reintroducing `pyqtgraph.dockarea` anywhere (incl. the sanctioned backend).
  Before/after screenshots confirmed the layouts are unchanged. (These files still
  import pyqtgraph for plots / `pyqtgraph.opengl`, so they remain allow-listed —
  only the dock system moved.)
- **Batch 25** (allow-list 26 → 25) — finished `gui/plots/parameter_scan` (its
  dockarea was already moved above). `pg.PlotWidget`→`cp.Plot`; the χ²-surface
  curve → `line`/`set_data`; the confidence-interval overlays (a horizontal
  threshold `InfiniteLine` + vertical crossing lines, dashed/dash-dot) → `hline`/
  `vline` with `label=` and module-level `cp.to_pen` pens; overlay add/remove use
  `add`/`remove` handles. The pyqtgraph `labelOpts` position hints have no chiplot
  equivalent and were dropped (labels still render at the default position).
  Screenshot-verified (χ² parabola + orange 68% threshold + green crossing lines
  at 1.40/2.20, in a chisurf DockArea tab).

**Phase 3 — migrate plugins.**
Same port across `chisurf/plugins/**`, cluster by plugin group (tttr, burst,
fcs, fluorescence_decay, microscopy, …); each cluster its own commit with its
plugin construction smoke tests (PRD-23) green. Add any missing handle
capability to the contract + pyqtgraph backend as real call sites surface it
(e.g. ROIs, histogram-LUT panels) rather than speculatively.

**Phase 4 — `modules/` wave.**
Migrate `ndxplorer` and `quest` on the same contract (committed in their own
repos per the module ownership rule). Allow-list reaches empty except the
ChiMOL OpenGL entry owned by PRD-57.

**Phase 5+ — native chiplot renderer (long-term, the actual goal).**
Implement `backends/opengl_backend.py`: an OpenGL-backed 2-D renderer satisfying
the `backends/base.py` contract — batched line/scatter/bar rendering, an
axis/viewbox with pan/zoom, region/marker/text overlays, and image blitting —
with an immediate-mode (imgui-style) control surface for interactive panels
where it fits. Bring plots over one family at a time (start with the
highest-volume, most GPU-favourable: large scatter/phasor clouds, waterfalls,
dense decays), gated behind `CHISURF_PLOT_BACKEND=opengl` and A/B screenshot
comparison against the pyqtgraph backend, re-running `test/gui/test_chiplot.py`
against it. pyqtgraph is dropped only when the native backend covers every used
handle family at parity — at which point the allow-list and this dependency are
both gone.

# Success criteria

- `grep -rn "import pyqtgraph\|from pyqtgraph" chisurf/` returns only
  `chisurf/gui/chiplot/backends/pyqtgraph_backend.py` and the PRD-57-owned
  ChiMOL OpenGL module.
- The CI guard test passes with an empty (or ChiMOL-only) allow-list. *(Phase 1:
  guard is in place and green against the 76-file starting allow-list.)*
- `pixi run test-gui` and the headless plot-construction tests pass with no new
  failures; rendered plots are visually unchanged from pre-migration (screenshot
  parity).
- Switching `CHISURF_PLOT_BACKEND` is the *only* change required to route
  plotting through a different backend — no call site references a backend
  directly. *(Phase 1: selection + `Backend` contract in place.)*
- (Phase 5+) A demonstrator plot family renders through the native OpenGL
  backend at output parity with pyqtgraph for the same input.

# Non-goals

- Subsuming ChiMOL 3-D / raw-OpenGL rendering (PRD-57 owns that).
- Re-exposing non-plot widgets through chiplot (PRD-42 removes those).
- Speculatively over-building the handle contract — capabilities are added when
  a real call site needs them during Phases 2–4, not up front.
- Shipping the native renderer in the first landings — Phases 1–4 leave
  pyqtgraph as the *engine* behind the clean API; only Phase 5+ replaces it.

# Relationships

- Complements [PRD-42](prd-42.md): PRD-42 makes pyqtgraph plot-only by removing
  `SpinBox`/`parametertree`; PRD-64 puts the remaining plot-only surface behind
  one swappable seam. PRD-42 should land first (or concurrently) so the facade
  never has to re-expose non-plot symbols.
- Shares the renderer-behind-a-stable-contract shape and OpenGL/immediate-mode
  direction with [PRD-57](prd-57.md) (ChiMOL renderer migration); the two stay
  separate (2-D vs 3-D) but can share GL infrastructure later.
- Interacts with [PRD-40](prd-40.md)/[PRD-38](prd-38.md) AutoForm: AutoForm plot
  sections (`decay_conv`, `phasor`, `waterfall`, `image`, `builtin`) become
  chiplot consumers, so the seam also covers the data-driven view layer.
- Advances the [GUI & AutoForm](/subsystems/gui-autoform.md) direction and the
  clean-dependency goal in the [assessment backlog](/specs/assessment.md).
