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
| `backends/wgpu/` | the **native** renderer: `_view.py` (data↔clip↔pixel, no Qt/GPU), `_gpu.py` (device, pipelines, offscreen render, stroke/marker geometry), `_handles.py` (handles, each contributing geometry), `_canvas.py` (the Qt widget), `_colormap.py`, `wgsl/plot2d.wgsl` |
| `backends/opengl/` | superseded by `backends/wgpu/`; kept until the WebGPU backend has been through the plot families |
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
the `gui.plot.backend` setting, or defaults to `pyqtgraph`; `set_backend(name)`
switches it. `available_backends()` lists the registered names. A new renderer
registers there and becomes selectable with no call-site change. This is the
mechanism [PRD-64](/prds/prd-64.md) exists to enable: pyqtgraph is the engine
today, a native renderer behind the same contract is the goal.

## The native renderer is WebGPU, not OpenGL

The first native backend targeted OpenGL and could not be finished: on macOS a
GL context reports `2.1 Metal - 90.5`, because Apple deprecated OpenGL and what
remains is a 2001 feature set emulated over Metal. Everything that made that
backend hard traces back to it — no dependable `gl_PointSize`, a `texture1D`
that may not exist, and a `QPainter`-versus-GL compositing fight that painted
axes onto a black rectangle. WebGPU is one API and one shader text across
macOS, Linux, Windows *and* the browser, and it is what the molecular viewer's
renderer already targets, so `backends/wgpu/` is the native backend and
`backends/opengl/` is superseded.

Three decisions in it are worth keeping:

* **Rendering is offscreen, and `QPainter` blits the result.** Hosting a GPU
  surface in the widget is what created the compositing problem; rendering to
  an image removes it, keeps text with Qt, and makes a headless screenshot the
  same code path as a visible one. The cost is one GPU→CPU copy per repaint.
* **Handles contribute geometry, not draw calls.** A handle's `batches(ctx)`
  returns clip-space triangles, so its output can be asserted on with no device
  present — which is where the geometry tests live.
* **Strokes and markers are expanded to triangles on the CPU.** WebGPU has no
  line width and no point size; both were fixed-function features that went
  away. That is also what makes dashes and round joins possible at all.

`CHISURF_PLOT_BACKEND=wgpu` selects it. `test/gui/chiplot_ab_screenshots.py`
renders the same recipes through each backend for side-by-side comparison; it
runs headless unless `opengl` is named.

# The rule, and why it is guarded

**Plot through chiplot, never pyqtgraph.** `test/test_pyqtgraph_seam.py` fails
if a *new* file imports pyqtgraph directly, and equally if an entry in
`test/pyqtgraph_import_allowlist.txt` has already been ported. That allow-list
is a **shrinking migration tracker**, not a place to add oneself: it started at
76 files and is down to 12, of which the ChiMOL OpenGL module is owned by
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

## `.native` is the other way past the seam, and the invisible one

An import is loud. `Plot.native` is not: it hands back the pyqtgraph object
directly, so a call site is exactly as coupled to the renderer as an importer
while `pyqtgraph_import_allowlist.txt` sees nothing. **12 files** did this when
the second guard was added (`test/chiplot_native_allowlist.txt`, same shrinking
contract, seeded 2026-08-04).

**Most of them are not gaps.** They predate the API that now covers them, and
each was written with a comment calling itself a migration gap — which is how
an assumption survives being wrong. `fcs_lfcs_sim` reached through `.native` to
call `enableAutoSIPrefix(False)`; `Plot.set_si_prefix(x=False)` had existed the
whole time. So **check `canvas.py` before concluding anything is missing**:

| the `.native` call | the chiplot verb |
|---|---|
| `enableAutoSIPrefix` | `set_si_prefix(x=…, y=…)` |
| `hideAxis` / `showAxis` | `set_axis_visible(left=…, …)` |
| `getAxis(…).setTickSpacing` | `set_tick_spacing(side, …)` |

What is *genuinely* missing, and therefore what a porter has to add to chiplot
first — this is the worklist, in rough order of how many call sites it unblocks:

1. **Axis styling** — pen and text colour, height, tick-text offset. Three
   consumers: the lightpath node thumbnail, the node-editor PT plot, the
   spectrum viewer (which also wants the legend's text colour).
2. **Curve performance** — `setDownsampling(auto=True)` and
   `setClipToView(True)`, wanted by the LUT settings panel and by `LinePlot`,
   which already documents its use of the hatch.
3. **Handle signals and hints** — a scatter's click signal and an export hint
   (`maxent_widget`).
4. **Scene position → data coordinates**, for a crosshair readout
   (`irf_estimator`).
5. **Custom tick labels** — `setTicks` with explicit strings
   (`burst_background`), which is a different verb from tick *spacing*.

Three of the twelve are **tests** asserting on `listDataItems()`; those want a
read-side query on `Plot` (what was drawn), in the spirit of `menu_enabled()`.

**The rule this feeds:** legacy plotting you walk past is legacy you own. A
change that touches one of these files ports it in the same change and strikes
the line, rather than noting it — which is what keeps a shrinking list actually
shrinking. See the repository's `CLAUDE.md`.

## A foreground matching the background hides every axis

Reported as "plot missing axes, or colors wrong", and it was neither a missing
axis nor a plot bug: `gui.plot.pyqtgraph_config` resolved to
`foreground: k` on `background: k`, so every axis line, tick and label was drawn
in black on black. The panel still **reserves** their space, which is what makes
it read as *having no axes* rather than as a colour setting — and why it
survived in two shipped panels.

Three things kept it alive, all worth knowing:

* the Plot-settings dialog's foreground combo listed `"k"` first, so a save that
  never loaded a value wrote black;
* the dialog's live preview did not apply the chosen colours, so it looked
  correct while writing the opposite;
* user settings are copied to `~/.chisurf` **once and never refreshed**, so a
  file that acquired it kept it, and changing the shipped default fixes nobody.

The fix is therefore in code, not in settings: `PyQtGraphBackend.configure`
substitutes a contrasting foreground and warns
(`test_configure_refuses_an_invisible_axis`). The dialog now orders the combo
sanely and pushes the options before rendering its preview.

The same investigation turned up `LinePlot` passing `alpha=1.0` to `grid()` on
its two residual strips — `alpha` is opacity, not an on/off flag, so once the
foreground became visible those panels filled with solid stripes. It had been
invisible for exactly as long as the axes were.

## Chrome typography is one policy, not two defaults

The two backends sized their axis text independently: pyqtgraph inherited the
**application** font (13 pt — a UI size, on a residual strip eighty pixels
tall), and the native one hardcoded 8 pt. Switching backend visibly changed
every plot, and neither followed the user's font preference.
`style.chrome_font(role)` is now the single answer — `chrome_base_size()` takes
`gui.plot.font_size`, or the application font when that is 0 — with ticks 3 pt
under the base, labels 2 pt, and a 6 pt floor. Both backends call it.

Two native-backend parity defects surfaced while comparing the two:

* **Anchored text was placed against the widget**, not the plot rectangle, and
  its vertical anchor was inverted (`1 - ay` instead of `ay`). The fit-quality
  overlay's `(100, 0)` therefore landed in the axis margin and was clipped
  away. Anchored means "offset from the data area's top-left", as the other
  backend's parenting implies.
* **Text was drawn single-line.** The overlay is three lines (range, chi2r,
  Durbin-Watson) and `drawText(QPointF, ...)` runs them together.

And one call-site defect the comparison exposed: `LinePlot._metrics_text_alive`
asked pyqtgraph's `textItem` through `.native` whether the overlay still
existed. Any other backend answers "no", so the overlay was created and then
never written. `Handle.is_alive()` is the chiplot query both backends
implement; reach for it rather than for a renderer's liveness internals.

## The Plot-settings dialog wrote defaults over the settings it was reading

Every control's `setChecked`/`setValue` emits, and the handler applied the
**whole** dialog to `cs_settings` — the same dict the loader was reading, and
not a copy. So the first control to load wrote every not-yet-loaded control's
default over the real value: the panel opened with everything unchecked and the
sliders at zero, and pressing *Save* persisted that to `~/.chisurf`.

That is almost certainly where the black-on-black `foreground` came from, and
it explains a settings file carrying `enable_grid: false`, `label_axis: false`
and `line_width: 0.5` that nobody chose. Loading is one-directional now
(`_loading` guard), covered by
`test_loading_does_not_overwrite_what_it_is_reading`.

Settings the plots honoured but the dialog could not reach were a second half
of the same problem — a value only editable by hand is one nobody edits.
`grid_alpha`, the three per-panel grid toggles, `enable_region_selector` and
the new `font_size` are all controls now, and
`test_every_plot_setting_the_dialog_writes_is_reachable` keeps the two lists
together. `label_axis` was the reverse case: a control that had *never* been
read, so turning it off did nothing; `LinePlot` honours it.

## A panel that advertises no size gets none

`_PlotWidget` had `setMinimumSize(50, 50)` and no `sizeHint`, so Qt fell back to
the minimum: **50x450 against pyqtgraph's 600x450**. A layout hands out space in
proportion to what its children ask for, so a plot sharing a column with a form
— the TCSPC simulator preview — collapsed to a strip a few pixels tall on the
native backend and came out full height on the other. Switching backend must not
rearrange the window, so the hint matches pyqtgraph's and the floor is derived
from the axis margins rather than being a flat 50.

The same panel showed the other half of the bug: created with `set_log(y=True)`
and no data yet, its default `[0, 1]` range put `log10(0)` at the floor and the
axis spanned **three hundred decades**, first tick `1e-300`. `PixelView`
sanitises a non-positive log bound to a few decades below the top, and — this
is the part that was missed first — `visible_range()` is what the tick
generator and the grid read, so labels cannot describe a span the geometry was
never mapped against.

## `set_range` is data units, on every axis

A pyqtgraph view in log mode holds **exponents**, so a call site that wanted
1..10000 wrote `set_ylim(log10(lo), log10(hi))` and it looked right — on that
renderer. The same code on the native backend asked for a decay spanning 0.1 to
4 counts, and the simulator preview drew the noise tail with the decay off the
top of the panel.

The API cannot carry a renderer-dependent unit, or every caller has to know
which backend it is talking to. `base.Canvas.set_range` states data units and
the pyqtgraph backend converts in both directions
(`_to_axis_units`/`_from_axis_units`); the call site passes values now. Both
suites assert the round trip.

## Auto-range, and mouse behaviour worth copying

A convolved decay does not stop at the last real count — it trails through
denormals to ~1e-300, and those samples are *positive*, so an honest min/max on
a log axis spans three hundred decades and squashes the data into the top two
pixels. Auto-range drops anything more than `_AUTORANGE_DECADES` (9) below the
peak; panning and zooming still reach it.

The gestures are pyqtgraph's, because that is what the hands using this
application already know: left **and middle** drag the view — pan, or a zoom
rectangle under the `leftButtonPan` preference the other backend reads; right
drag scales about the point it started from (1.02 per pixel, x inverted); the
wheel zooms about the cursor; and the corner **[A]** button restores
auto-range.

The middle button is not a footnote. pyqtgraph handles it in the *same branch*
as the left one (`ViewBox.mouseDragEvent` tests
`button in [LeftButton, MiddleButton]`, and `GraphicsView` pans on either), and
it is how a user pans without giving up a left drag that has been rebound to a
zoom rectangle. Its *items* are the other half of the rule: `LinearRegionItem`
returns unless the button is the left one, so a middle drag pans **across** a
fit range rather than dragging it. Only the left button grabs a region, a marker
or the corner button here, for the same reason.

**The context menu belongs to a right *click*, not to a right press**, and that
distinction is not cosmetic. Qt's default policy raises the menu from the press;
the menu runs modally, so the release goes to the menu and never reaches the
panel — leaving it scaling for the rest of the session, so afterwards every
plain mouse move zoomed the view. The panel sets `PreventContextMenu` and raises
the menu itself on release, when the press travelled less than `_DRAG_PX`
(5 px, pyqtgraph's `GraphicsScene` threshold). A right drag scales and raises
nothing.

The general guard matters more than that one fix: **a move with no button held
cancels whatever the panel thought it was doing** (`_cancel_interaction`, also
called from `leaveEvent`). A press whose release lands somewhere else — a modal
dialog, another widget, a window switch — is otherwise indistinguishable from a
drag that never ends, and the same shape of bug would come back through any of
those routes. That button matters
more than it looks — a view panned away from its data otherwise has no
discoverable way back, since "double-click somewhere" is not one.

Every conversion out of log space goes through `_view.pow10`, which clamps to a
representable exponent. The exponent is not bounded by the data — it comes from
a pixel position, and a drag keeps delivering mouse events after the cursor has
left the panel, so the unclamped version raised
`OverflowError: (34, 'Result too large')` out of the move handler.

## Space, hover, and an eight-digit hex that was not the colour asked for

**Insets are measured, not reserved.** Each was a constant with a floor,
whether or not the side drew anything: a residual strip hides its bottom axis
and is eighty pixels tall, so a reserved bottom margin was a third of the panel
spent on nothing, and a stack of them became the band of empty space between
plots. A hidden axis now costs a few pixels of breathing room and no more —
measured, a strip gains 37 px of plot height out of 90.

**Hovering highlights what a press would grab**, which is the only thing that
tells a user an edge is draggable. pyqtgraph's defaults exactly: the line under
the pointer takes a red pen at its own width (`InfiniteLine`), and a region's
band doubles its brush alpha (`LinearRegionItem`). Nothing highlights mid-drag.

**The fit panels fold.** `DockSplitter` disables collapsing — right for docks,
where a vanished pane cannot be got back — so the stacked plot enables it on its
own splitter: dragging a handle onto a panel folds it away and the drag
reverses.

**`to_color("#ff000080")` returned opaque dark blue.** Qt reads an eight-digit
hex as `#AARRGGBB`; this module documents `#RRGGBBAA`, the CSS spelling, and
handed the string straight to `QColor`. Alpha became red and the colour came
back opaque — which is why a translucent teal band rendered olive. Parsed here
now, before Qt sees it, and covered by `test_eight_digit_hex_is_rrggbbaa`.

# Where to pick this up — the WebGPU backend

`backends/wgpu/` draws every family the A/B script exercises (decay on a log
axis, scatter, bars, heatmap, region, error bars) and passes 31 tests in
`test/gui/test_chiplot_wgpu.py`. **Measure it with
`python test/gui/chiplot_ab_screenshots.py` and read the PNG pairs** — that is
the only instrument that has caught anything here. The traps in taking that
measurement, both of which cost a session:

* **A backend that renders nothing still writes a PNG.** The OpenGL backend's
  every handle raised `AttributeError: 'QOpenGLShaderProgram' object has no
  attribute 'setUniformValue1i'` (that binding has only the overloaded
  `setUniformValue`), and `_paint_gl` swallowed it in a bare `except
  Exception: pass`. The axes still drew, so the output looked like a
  *rendering* problem for as long as nobody removed the swallow. Never wrap a
  paint pass in a silent except.
* **A fixture can invent the defect you are chasing.** The old decay recipe
  modelled the IRF as a bare Gaussian, which falls to `exp(-2304)` by the end
  of the window; a log axis asked to span 300 decades produced garbage ticks
  on *both* backends. The recipe now carries a constant background, as real
  data does.

Open, in the order that unblocks the most:

1. **Bring the plot families over.** The A/B script covers primitives, not the
   application's panels. Start with the highest-volume ones (TCSPC decay +
   weighted-residual pair, FCS curves, burst histograms), run each under
   `CHISURF_PLOT_BACKEND=wgpu`, and compare screenshots against pyqtgraph.
   This is what decides whether the backend can become the default.
2. **Retire `backends/opengl/`.** It is superseded and registered only so the
   comparison can still be run. Deleting it also removes the `PyOpenGL`
   dependency's last plotting use.
3. **A zero-copy surface path.** Every repaint currently reads the framebuffer
   back to the CPU. That is the right trade for plot panels, and the wrong one
   for an animated view; `rendercanvas.qt.QRenderWidget` gives a real surface,
   at the cost of losing the `QPainter` chrome pass (text would have to move to
   the GPU). Do not start this before (1) — it buys nothing until a panel is
   found that needs it.
4. **Colour bars.** `_ColorBar` stores levels and forwards them to its image
   but draws no bar; `_WgpuGrid.add_colorbar` therefore adds no widget.
5. **chimol convergence.** Both renderers are now WebGPU. Once chiplot's
   backend is through (1), chimol's standalone renderer can move onto
   chiplot's `Canvas`/`VolumeViewCanvas` contract, and the two WGSL sets can
   be considered together.

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
