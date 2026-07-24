---
type: PRD
prd: "64"
title: "PRD-64: chiplot — single plotting seam and pyqtgraph replacement"
description: Route every plotting access through one dependency-neutral chiplot facade so pyqtgraph becomes a swappable backend, then grow chiplot into a native OpenGL/immediate-mode renderer behind the same API.
status: draft
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

Draft. Motivation, current-state inventory, facade design, phased migration, and
success criteria are specified below. No code has landed. The chiplot native
renderer (Phase 3+) is a direction, not yet a committed design.

# Goal

1. **One seam.** Exactly one module imports `pyqtgraph`; every other module
   reaches plotting through `chisurf.gui.chiplot`. Enforced by a CI guard.
2. **Zero behavioural change on landing.** The facade is a pass-through to
   pyqtgraph; rendered plots are byte-for-byte what they are today.
3. **Swappable backend.** The facade selects a backend at import time; a second
   (native chiplot) backend can be added later without touching call sites.
4. **A path to native.** Establish the API contract chiplot must satisfy so an
   OpenGL/immediate-mode renderer can replace pyqtgraph plot-by-plot.

Non-goal for the first landings: writing the native renderer. That is the
long-term payoff the seam unlocks, tracked as later phases here.

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

## Package layout

```
chisurf/gui/chiplot/
  __init__.py                 # public facade — the ONLY name call sites import
  backend/
    __init__.py               # backend selection (env/setting → module)
    pyqtgraph_backend.py       # the ONLY module allowed to `import pyqtgraph`
    # (future) native_backend.py — OpenGL/immediate-mode renderer
  types.py                    # backend-neutral typing/Protocols for items+widgets
```

- **`chisurf.gui.chiplot`** re-exports the confined symbol set from the active
  backend. Public names match pyqtgraph's (`cp.mkPen`, `cp.PlotWidget`,
  `cp.TextItem`, …) so the body of a migrated module is unchanged apart from the
  `pg.` → `cp.` prefix rename.
- **`backend/pyqtgraph_backend.py`** is a thin module that imports pyqtgraph and
  exposes exactly the confined surface (the table above). It applies ChiSurf's
  global pyqtgraph config (`setConfigOptions(...)`, background/foreground,
  antialias) in one place instead of scattered call sites.
- **`backend/__init__.py`** picks a backend from a setting/env var
  (`CHISURF_PLOT_BACKEND`, default `pyqtgraph`) so a future native backend is
  opt-in per session, then per-plot.
- **`types.py`** declares `Protocol`s for the plot widget and the item families
  (curve, scatter, region, marker, image, ROI). These are the **contract** the
  native backend must satisfy; they also give call sites real typing instead of
  `Any`.

## Why API-compatible (not a new API)

A clean, redesigned plotting API (`Figure.line(...)`, `Figure.region(...)`)
would be nicer long-term but requires rewriting all ~125 call sites and every
item-method call — high churn, high regression risk, and it blocks landing the
seam behind months of rewrite. Keeping the pyqtgraph-shaped surface makes the
seam land now with near-mechanical edits; the native renderer then implements
that same (subset) contract. The contract is small and already de-facto stable,
so this is a pragmatic, reversible choice — a cleaner API can be layered on top
of chiplot later without re-touching pyqtgraph.

## CI guard

A test (`test/test_plotting_seam.py`) greps the tree and asserts
`import pyqtgraph` (and `from pyqtgraph`) appears **only** in
`chisurf/gui/chiplot/backend/pyqtgraph_backend.py`, with an explicit,
shrinking allow-list for the ChiMOL OpenGL module (PRD-57) and any
not-yet-migrated files during the rollout. The allow-list is the migration
tracker; "done" is an empty allow-list.

# Migration plan

**Phase 1 — facade + backend (no call-site change).**
Create the `chiplot` package, `pyqtgraph_backend.py` exposing the confined
surface, backend selection, and `types.py` Protocols. Move the global
`pg.setConfigOptions(...)` initialization into the backend. Add the CI guard
seeded with the current file list as the allow-list. Add a focused unit test
that constructs a `cp.PlotWidget`, plots a curve, and adds each item family.

**Phase 2 — migrate chisurf-core GUI.**
Rewrite `chisurf/gui/**` call sites: `import pyqtgraph as pg` →
`import chisurf.gui.chiplot as cp`, and `pg.` → `cp.` within those files
(mechanical, but only in files whose `pg` is actually pyqtgraph — several
modules use `pg` as a parameter-group variable and must be skipped). Shrink the
allow-list as files move. Run `pixi run test-gui` and the headless
screenshot/qtbot verification after each cluster.

**Phase 3 — migrate plugins.**
Same rewrite across `chisurf/plugins/**`, cluster by plugin group (tttr, burst,
fcs, fluorescence_decay, microscopy, …), each cluster its own commit with its
plugin construction smoke tests (PRD-23) green.

**Phase 4 — `modules/` wave.**
Migrate `ndxplorer` and `quest` on the same contract (committed in their own
repos per the module ownership rule). Allow-list reaches empty except the
ChiMOL OpenGL entry owned by PRD-57.

**Phase 5+ — native chiplot renderer (long-term).**
Implement `native_backend.py`: an OpenGL-backed 2-D plot widget satisfying the
`types.py` contract — batched line/scatter/bar rendering, an axis/viewbox with
pan/zoom, region/marker/text overlays, and image blitting — with an
immediate-mode (imgui-style) control surface for interactive panels where it
fits. Bring plots over one family at a time (start with the highest-volume,
most GPU-favourable: large scatter/phasor clouds, waterfalls, dense decays),
gated behind `CHISURF_PLOT_BACKEND=chiplot` and A/B screenshot comparison
against the pyqtgraph backend. pyqtgraph is dropped only when the native backend
covers every used item family at parity.

# Success criteria

- `grep -rn "import pyqtgraph\|from pyqtgraph" chisurf/` returns only
  `chisurf/gui/chiplot/backend/pyqtgraph_backend.py` and the PRD-57-owned
  ChiMOL OpenGL module.
- The CI guard test passes with an empty (or ChiMOL-only) allow-list.
- `pixi run test-gui` and the headless plot-construction tests pass with no new
  failures; rendered plots are visually unchanged from pre-migration (screenshot
  parity).
- Switching `CHISURF_PLOT_BACKEND` is the *only* change required to route
  plotting through a different backend — no call site references a backend
  directly.
- (Phase 5+) A demonstrator plot family renders through the native OpenGL
  backend at output parity with pyqtgraph for the same input.

# Non-goals

- Redesigning the plotting *API* (a `Figure`-style fluent API). The facade keeps
  the pyqtgraph-shaped contract; a nicer API can be layered later.
- Subsuming ChiMOL 3-D / raw-OpenGL rendering (PRD-57 owns that).
- Re-exposing non-plot widgets through chiplot (PRD-42 removes those).
- Shipping the native renderer in the first landings — Phases 1–4 leave
  pyqtgraph as the engine; only the *access path* changes.

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
