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
  (pyqtgraph). A migration can therefore be as small as
  `import pyqtgraph as pg` → `import chisurf.gui.chiplot as pg` and still run.
- **Instance level** — a native `Plot` proxies unknown attributes
  (`getViewBox`, `setLogMode`, …) to its underlying backend plot object.

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
*Landed so far (allow-list 76 → 57):*
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
  `Plot`/`ImageView`): a handle proxies unknown attributes to its native
  pyqtgraph item, giving **full pyqtgraph parity** (any item method chiplot
  lacks natively still works, flagged). Added `Image.clear()`. Migrated
  `autoform/phasor_section`. Deferred `burst_bva` (custom `GraphicsLayoutWidget`
  + `HistogramLUTItem`, and `pg.colormap.get` collides with chiplot's
  `colormap`).
- **Batch 7** — added `Grid` passthrough (parity for `GraphicsLayoutWidget`
  methods) and two small native params (`plot.image(axis_order=…)`,
  `plot.errorbars(beam=…)`); migrated `burst_bva`. Its plot content is clean
  chiplot (Grid panel + image + lines + errorbars); the `HistogramLUTItem` LUT
  composite stays passthrough (a flagged gap), and the `pg.colormap.get`
  collision is resolved via `cp.get_backend().raw_module().colormap.get(...)`.

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
