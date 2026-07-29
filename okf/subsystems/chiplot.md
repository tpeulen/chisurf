---
type: Subsystem
title: Plotting (chiplot)
description: The single renderer-neutral 2-D plotting API every call site draws through, its backend contract, and the guard that keeps the rendering library behind it.
resource: chisurf/gui/chiplot/
tags: [gui, plotting, chiplot, seam]
timestamp: '2026-07-29T00:00:00Z'
---

# What it is

`chisurf.gui.chiplot` is *the* 2-D plotting API of the application. Call sites
use it; they never import a rendering library directly. The renderer is chosen
at runtime and can be swapped without touching a single call site.

| Module | Holds |
|--------|-------|
| `canvas.py` | the widgets: `Plot`, `Grid` (of `PanelPlot`s, with colour bars), `ImageView` |
| `handles.py` | the drawn-object protocols — `Curve`, `Scatter`, `Bars`, `ErrorBars`, `Image`, `ColorBar`, `Region`, `Marker`, `Roi`, `Arrow`, `Text` — plus the `Symbol` and `Orientation` enums |
| `style.py` | `Color`, `Pen`, `Brush`, `Colormap`, `LineStyle` and the coercers `to_color` / `to_pen` / `to_brush` / `colormap` / `to_colormap` / `int_color` |
| `backends/base.py` | the abstract `Canvas`/`Backend` contract a renderer must satisfy |
| `backends/pyqtgraph_backend.py` | the only module in the tree allowed to import pyqtgraph |
| `_passthrough.py` | the migration safety net and its gap recorder |

`Plot` is verb-first: `plot.line(x, y, pen="red")`, `plot.scatter`, `plot.bars`,
`plot.image`, `plot.region(...).on_change(cb)`, `plot.vline` / `plot.hline`,
`plot.arrow`, `plot.text`, `plot.set_labels`, `plot.set_log`, `plot.export_csv` /
`plot.export_image`. Drawing returns a handle, and a handle is mutated through
methods (`curve.set_data`, `set_pen`, `hide`), never by assigning to a
renderer's attributes — that is what lets a second backend satisfy the same
protocol.

Angles are chiplot's, not a renderer's: `plot.arrow(x, y, angle=...)` measures
degrees counter-clockwise from `+x` — exactly `degrees(arctan2(dy, dx))` for the
edge that ends at the tip — and the backend converts to whatever its own arrow
item means by "angle". A convention that leaks to the call site is a silent bug:
a mirrored rate arrow between two states reads as the opposite transition, and
nothing raises.

# Adding to the contract

An abstract method added to `backends/base.py` **must** land with its backend
implementation in the same change. Python only reports the omission when a
canvas is instantiated — `Can't instantiate abstract class _PgCanvas without an
implementation for abstract method 'add_arrow'` — so a half-landed contract does
not break a test, it breaks *every* plot panel in the application at once, and
each tool reports it as its own load failure. `test_backend_contract_matches_implementation`
asserts each concrete class has an empty `__abstractmethods__` for that reason.

# Backend selection

`backends/__init__.py` keeps a registry (`register_backend`) and resolves the
active backend lazily from the `CHISURF_PLOT_BACKEND` environment variable,
defaulting to `pyqtgraph`; `set_backend(name)` switches it. A new renderer
registers there and becomes selectable with no call-site change. This is the
mechanism [PRD-64](/prds/prd-64.md) exists to enable: pyqtgraph is the engine
today, a native OpenGL renderer behind the same contract is the goal.

# The rule, and why it is guarded

**Plot through chiplot, never pyqtgraph.** `test/test_pyqtgraph_seam.py` fails
if a *new* file imports pyqtgraph directly, and equally if an entry in
`test/pyqtgraph_import_allowlist.txt` has already been ported. That allow-list
is a **shrinking migration tracker**, not a place to add oneself: it started at
76 files and is down to 15, of which the ChiMOL OpenGL module is owned by
[PRD-57](/prds/prd-57.md) and out of scope.

The safety net has two halves, and the object one is easy to get wrong:
`Plot.__getattr__` consults the backend's plot object **and then the widget
hosting it**, because pyqtgraph splits its API across a `PlotItem`
(`setLogMode`, `getViewBox`) and a `PlotWidget` (`getPlotItem`, `plotItem`).
`Plot.native` is the *item*, so a call site reaching for the widget half used to
get an `AttributeError` out of the one mechanism that exists to keep such calls
working. Where a query is genuinely missing, add it: `set_menu_enabled` gained
its read side, `menu_enabled()`, rather than leaving tests to ask pyqtgraph.

The reason the rule needs a guard is the safety net. `chiplot.__getattr__`
resolves any name chiplot does not define — `mkPen`, `PlotWidget`,
`LinearRegionItem`, … — from the active backend's underlying module and emits a
`ChiplotPassthroughWarning` instead of failing. A not-yet-ported module keeps
working, but a *wrong spelling* in new code does not announce itself at import
time; it breaks later, when a chiplot `Pen` reaches a pyqtgraph function that
wants a pyqtgraph one. `passthrough_gaps()` lists what fell through during a
session — that is the worklist, and the answer to a gap is to add the API to
chiplot rather than reach past the seam.

Headless coverage is `test/gui/test_chiplot.py`: every draw family, handle
updates, region/marker values, removal and re-add, grid panels, the click
signal.

# Related

* [GUI & AutoForm](/subsystems/gui-autoform.md) — AutoForm's plot-bearing
  sections (`decay_conv`, `phasor`, `waterfall`, `image`, `builtin`) are chiplot
  consumers, so the seam also covers the data-driven view layer.
* [PRD-64](/prds/prd-64.md) — the migration plan, its batch log, and the
  long-term native-renderer goal.
* [PRD-42](/prds/prd-42.md) — removes pyqtgraph's *non-plot* uses (`SpinBox`,
  `parametertree`), so the seam never has to re-expose them.
* [Tables (chitable)](/subsystems/gui-tables.md) and
  [Regions of interest](/subsystems/roi.md) — the same "one in-tree
  implementation behind one API" shape for tables and ROI geometry.
