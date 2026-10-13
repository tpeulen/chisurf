---
type: Subsystem
title: Plotting (chiplot)
description: The single renderer-neutral 2-D plotting API every call site draws through, its backend contract, and the guard that keeps the rendering library behind it.
resource: chisurf/chiplot/
tags: [gui, plotting, chiplot, seam]
timestamp: '2026-10-13T12:00:00Z'
---

# What it is

`chisurf.chiplot` is *the* 2-D plotting API of the application. Call sites
use it; they never import a rendering library directly. The renderer is chosen
at runtime and can be swapped without touching a single call site.

**The core names no Qt (2026-10-13, S6 slice).** `chisurf.chiplot` holds every
drawing thing as an emtk control: `Panel` (the plot API over one canvas),
`PanelGrid` (panels and colour ramps in a grid -- rows, columns, spans, stretch,
a ramp's column kept narrow -- laid out and drawn as one control, input routed to
the cell under the pointer), `ImagePanel` (the image viewer: picture, colour ramp
with draggable levels, an emtk-drawn frame slider for a stack, playback, extent,
marks, brush layer, ROIs, click-to-pick; hooks `clicked`/`picked`/
`frame_changed`/`playing_changed`), the handles, the styles and the backend.
Whatever shows a control attaches itself through a duck-typed host hook
(`attach_host(host)`: `update()`, optional `size()`, `set_background(rgb)`,
`set_visible`, `set_width_range`, `detach`, `playing_changed`) or a refresh
target, so the core never knows the toolkit. `export_image` draws on emtk's CPU
rasteriser (`PilPainter`, `ScaledPainter` for `width=`), the painter
`chisurf/emtk/fit_report.py` draws the report with. Guard:
`test/test_chiplot_core_qt_free.py` greps the core's source for any Qt name
(module, binding, emtk's Qt host/painter, a `Q...` class) and exports a panel in
a fresh interpreter with Qt unloaded.

`chisurf.gui.chiplot` is the **Qt host layer** and nothing else: `host(x)` gives a
`Panel` a `PanelHost` (a `ControlHost` plus chiplot's right-click menu: export
CSV, export image painted by Qt as the widget shows it, auto-range, the panel's
own entries), an `ImagePanel` an `ImagePanelHost` (the playback timer, the
slider tooltip), a `PanelGrid` a bare `ControlHost`; plus a re-export of the
core. The Qt widgets `Plot`, `PanelPlot`, `Grid`, `ImageView` and the
never-implemented `VolumeView` are deleted: every Qt form draws a core panel and
only hosts it (`self.plot = cp.Panel(); layout.addWidget(cp.host(self.plot))`).
Colours do not go through `QColor`: names are emtk's CSS/SVG table (case and
spaces ignored, `transparent`), and `int_color` reproduces the old toolkit HSV
colour byte for byte (16-bit channels reduced by rounded `/257`, not `>>8`; the
`1-(1-f)` float form matters).

| Module (under `chisurf/chiplot/` unless named) | Holds |
|--------|-------|
| `canvas.py` | `PlotAPI` (the toolkit-free API), `Panel` (an emtk control; fit-window pages declare them with `plotbase.Plot.add_panel`) and `PanelGrid` |
| `image_panel.py` | `ImagePanel`, the image viewer as one emtk control |
| `chisurf/gui/chiplot/canvas.py` | the Qt host layer: `host`, `PanelHost`, `ImagePanelHost` |
| `handles.py` | the drawn-object protocols — `Curve`, `Scatter`, `Bars`, `ErrorBars`, `Image`, `ColorBar`, `Region`, `Marker`, `Roi`, `Arrow`, `Text` — plus the `Symbol` and `Orientation` enums |
| `style.py` | `Color`, `Pen`, `Brush`, `Colormap`, `LineStyle` and the coercers `to_color` / `to_pen` / `to_brush` / `colormap` / `to_colormap` / `int_color` |
| `backends/base.py` | the abstract `Canvas`/`Backend` contract a renderer must satisfy |
| `backends/pyqtgraph_backend.py` | the only module in the tree allowed to import pyqtgraph |
| `backends/emtk/` | the **native** renderer (in progress): chimol's emtk ([PRD-104](/prds/prd-104.md)) behind the `backends/base.py` contract — the primary plotting widget; see [#Native renderer](#the-native-renderer-is-emtk-not-webgpu) |
| `backends/wgpu/` | superseded WebGPU experiment backend, kept registered until the emtk backend exists; retired when it lands |
| `backends/opengl/` | superseded experiment backend (predates wgpu); retired with wgpu |
| `_passthrough.py` | the migration safety net and its gap recorder |

`ImagePanel` (the `ImageView` widget until 2026-10-13) is the image half of the same idea, and it carries two capabilities
that used to be re-implemented per tool. `add_region(roi)` draws a
[region](/subsystems/roi.md) of any shape — every caller that had one was
converting it to `kind`/`pos`/`size` by hand, differently, and an ellipse's
radius-versus-diameter convention was wrong in more than one of them. It honours
the region's **rotation**, which matters because a Gaussian gate on a correlated
population is a tilted ellipse and an axis-aligned one is a *different gate* that
looks perfectly reasonable on screen. `enable_picking()` turns clicks into a
`picked` hook carrying a fitted spot: the gesture belongs to the thing being
clicked, while deciding where the spot actually is belongs to
`chisurf.core.roi.picking`. Before both, a tool that wanted either reached past
this seam for the click and did the geometry itself.

One thing about the image viewer is worth knowing before writing a test against
it: the backend rotates an ellipse about `pos` rather than about its centre, so a
rotation has to put the centre back by hand. (The pyqtgraph-era rule "keep views
alive until the event loop ends" is gone with pyqtgraph and Qt: an `ImagePanel` is
a Python object, and its tests run without a `QApplication`.)

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

## Static figures are `emtk.figure`, not chiplot

A picture an application *writes* -- a workflow diagnostic, a report page, a
figure an agent tool saves -- is drawn by `emtk.figure` (a Qt-free
`Figure`/`Axes` recorder rendered by implot on the CPU), not by a chiplot
`Plot`. chiplot cannot serve it: importing `chisurf.gui` imports Qt, and the
callers include the Qt-free server and `api/` modules. chiplot remains the API
for every plot *inside* a GUI. Colour tables for both come from
`emtk.colormaps` (the emtk backend's `_lut` reads them). Context:
[Retiring matplotlib](matplotlib-retirement.md).

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
active backend lazily from the `CHISURF_PLOT_BACKEND` environment variable, else
`emtk`; `set_backend(name)` switches it. `available_backends()` lists the
registered names. A new renderer registers there and becomes selectable with no
call-site change. There is **no user setting** for it any more: with one
renderer the `gui.plot.backend` choice in Settings ▸ Plots was a control that
did nothing, and the key is dropped from settings files on load (2026-10-12,
see "Settings ▸ Plots changed no plot"). This is the mechanism
[PRD-64](/prds/prd-64.md) existed to enable; pyqtgraph is gone (W8).

## The native renderer is emtk, not WebGPU

**Current direction (2026-08-14): the native renderer is chimol's emtk.** The
maintainer directed that chiplot's native backend **MUST** be emtk
([PRD-104](/prds/prd-104.md)) — the ImPlot-style plotting toolkit at
`chisurf/plugins/chimol/chimol/emtk/`, drawn through chimol's own painter —
used as the **primary plotting widget**. pyqtgraph and emtk are the **only**
backend options. A `backends/emtk/` package implements the `backends/base.py`
contract on top of emtk's `begin_plot`/`Plot.line`/… builders; chiplot is
emtk's first external consumer and drives PRD-104 Phase 2 breadth (bars, error
bars, regions, pan/zoom, image, log axes). Long term, emtk also replaces PyQt
as the UI backend behind the AutoForm seam. See [PRD-64](/prds/prd-64.md)
Phase 5+ and "Long-term direction".

**History: WebGPU superseded OpenGL, and now steps aside for emtk.** The first
native backend targeted OpenGL and could not be finished: on macOS a GL context
reports `2.1 Metal - 90.5`, because Apple deprecated OpenGL and what remains is
a 2001 feature set emulated over Metal. Everything that made that backend hard
traces back to it — no dependable `gl_PointSize`, a `texture1D` that may not
exist, and a `QPainter`-versus-GL compositing fight that painted axes onto a
black rectangle. WebGPU is one API and one shader text across macOS, Linux,
Windows *and* the browser, so `backends/wgpu/` superseded `backends/opengl/`.
Both proved the seam works (contract + handle tests ran against both) without
becoming maintainable renderers; neither is a target now — emtk is. `wgpu` and
`opengl` stay registered until the emtk backend exists, then retire
(`test/gui/test_chiplot_wgpu.py` pins `"wgpu" in available_backends()`, so the
unregistering lands with the emtk backend).

Three decisions from the wgpu era are worth keeping as lessons:

* **Rendering offscreen, and `QPainter` blits the result.** Hosting a GPU
  surface in the widget is what created the compositing problem; rendering to
  an image removes it, keeps text with Qt, and makes a headless screenshot the
  same code path as a visible one. The cost is one GPU→CPU copy per repaint.
* **Handles contribute geometry, not draw calls.** A handle's `batches(ctx)`
  returns clip-space triangles, so its output can be asserted on with no device
  present — which is where the geometry tests live.
* **Strokes and markers are expanded to triangles on the CPU.** WebGPU has no
  line width and no point size; both were fixed-function features that went
  away. That is also what makes dashes and round joins possible at all.

`CHISURF_PLOT_BACKEND=wgpu` selects the experiment backend. `test/gui/chiplot_ab_screenshots.py`
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

*Historical (2026-10-13): `style.chrome_font` / `chrome_base_size` had no caller left and
were deleted with the Qt-free core; the emtk backend sizes its chrome from
`chisurf.core.plotting.appearance.font_size`.*

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

## Settings ▸ Plots changed no plot — 2026-10-12

Reported as "plot config not good … may be a real bug". It was: rendering a real
`LinePlot` after each change the panel applies (the documented contract — plots
built after Apply use the settings) showed **every colour, the region colour and
alpha, the line width, the axis font size, the grid strength and "Grid" off had no
effect**, and switching the fit-range band off **crashed** the next plot
(`AttributeError: 'LinePlot' object has no attribute 'region'`). Only the legend
and axis-name switches worked. One mode explains most of it:

* **snapshots taken at import.** `lineplot.py` held `colors = …["colors"]` at
  module level and its `director` (curve colour/width per name) was a class
  attribute built from it; the panel's Apply *replaced* the `colors` dict, so the
  snapshot kept the start-up palette for the whole session. `distribution.py`,
  `proteinMC.py` and the photon-filter wizard did the same. Every reader now goes
  through `chisurf/core/plotting/appearance.py`, read when the plot is built
  (Qt-free; the panel's preview reads the same functions, so it cannot drift).
* **width overridden by name.** The director's hard-coded `lw` beat
  `line_width` for every named curve; now the line width, the data trace at half.
* **chiplot accepted and ignored.** `grid(alpha=…)` was dropped by the emtk
  backend (gridline colours were emtk constants: emtk `Plot.grid_opacity`, a factor
  on the theme's alpha, added in emtk 1dfa2b5; `appearance.grid_strength` maps
  0 → none, 0.3 → theme, 1 → solid), and a panel's grid was on unless told off, so
  "Grid" off never reached it (`LinePlot` now sets every panel's grid either way).
  `gui.plot.font_size` was read only by the Qt `chrome_font`, which nothing calls;
  `EmtkCanvas.draw` now scales its axis text by it (`painter.set_font_scale`).
* **dead keys.** `pyqtgraph_config` (antialias, left-button pan, background,
  foreground) went to `chiplot.configure()`, a no-op on emtk; `hideTitle` was read
  by nothing; `backend` had one choice. Removed from the shipped settings and the
  panel; `settings_utils.RETIRED_KEYS` drops them from old user files on load
  (`FORMER_DEFAULTS` moves the never-honoured `inactive_transparency: 0.2` and
  `grid_alpha: 0.35` to the values the plots actually drew, 0.4 and 0.3).
  `active/inactive_transparency` were read by nothing either — the grouped-fit
  opacities were a hard-coded 1.0 / 0.4 — and now are those opacities.

Measured with a probe that applies each change through the panel's model, builds
`LinePlot(_simulated_fit())` and diffs the exported panels: 19/19 settings change
the picture now (was 2/19). Guards: `test/gui/test_plot_appearance_live.py`,
`test/core/test_plot_appearance.py`, `test_no_setting_or_ui_string_names_pyqtgraph`
in `test/test_pyqtgraph_seam.py`. The panel itself (live apply + save like
Settings ▸ Fonts, a preview laid out like a fit window on a simulated convolved
decay) is `chisurf/plugins/core/plot_settings/`.

**Open:** a fit window already on screen keeps the curves it built (colours,
widths, band) until it is re-plotted — the panel says so. Re-styling open
`LinePlot`s live needs `LinePlot` to re-apply `director` to its existing handles
(`set_pen`, `set_opacity`, the region brush) on a settings-changed signal; only the
axis text size and node graphs follow at once today.

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

**The [A] button is every emtk plot's, by default** (emtk aea9d8b,
`emtk/widgets/auto_range.py`). One module places (lower-left, *inside* the plot
area, 15 px, 3 px inset), draws and hit-tests it and owns the tooltip
`tr("Auto-range: fit the view to the data")`; both stacks call it: `emtk.implot`
(shown while an enabled, non-locked axis has `follow == False`; tested before the
plot's own input so a press on it never pans; the click is a double-click fit) and
chiplot's `EmtkCanvas` (shown while `is_auto_range()` is not `(True, True)`; a
press on it calls `auto_range()`, which also resets linked x panels). Deliberate
differences from pyqtgraph: it shows whenever the view is not auto-ranged, not
only on hover, and a caller's `set_range` counts as "not auto-ranged" there too.
**Opt out** only for a view that must stay where the code put it:
`Plot.set_auto_range_button(False)` / `ImageView.set_auto_range_button(False)`,
or `implot.FLAGS_NO_AUTO_RANGE_BUTTON`; it is also hidden on a non-interactive
panel (`set_interactive(mouse=False)`, `FLAGS_NO_INPUTS`). Guards:
`emtk/tests/test_auto_range_button.py`, `test/gui/test_chiplot_auto_range_button.py`,
the fit-window case in `test/gui/test_fit_window_emtk.py`, and the click-all sweep's
`auto_range` phase (`test/e2e/test_click_all_plugins.py`: every plot drawn on the
first frame and after the tour must show A after a wheel or drag and hide it after
a click; results in each plugin's JSON under `auto_range`). Open edge: an implot
plot with **no data** keeps its zoomed limits after the click (there is nothing to
fit), though the A hides.

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

## A panel's floor, and the golden split

The two are the same problem seen from opposite ends: how little room a panel
will accept, and how the room is shared.

**The floor is a small constant, not the current margins.** Margins are measured
during a paint; a layout asks for `minimumSizeHint` *before* the first one, and
Qt's default size constraint then freezes whatever it got onto the parent
widget. A panel therefore stayed stuck at a fully-labelled plot's floor even
after hiding its axes — and three stacked strips at 62-99 px each need more than
a short fit window has, so the splitter refused to shrink and the *data* panel
was what got clipped, axis and all. Three panels now fit in 109 px.

**The stack is split at the golden ratio**: the data panel takes
`φ/(1+φ) ≈ 0.618`, the two residual strips share the rest. Setting absolute
sizes once is not enough — a splitter rescales them and the proportion drifts —
so it is re-applied on every resize, until `splitterMoved` says the user has
chosen a split of their own, after which theirs stands. Measured at 1.619 /
1.613 / 1.625 for window heights of 600 / 400 / 260; below about 200 px the
strips reach their floor and the ratio necessarily gives way.

## The menu is the backend's, and the legend moves

`provides_native_menu()` returns **True** for the native backend, which is what
the flag was built for: chiplot then injects its CSV and image exports into the
backend's menu instead of drawing a small one of its own. Reporting `False`
meant a right-click gave two entries where pyqtgraph gives a page of them.

The menu mirrors pyqtgraph's: *View all*; an **X** and a **Y** submenu with
mouse-enabled, auto/manual (with the min/max editors in the submenu, where
editing one switches the axis to manual), invert and log; *Mouse mode* with
3-button and 1-button; and plot options grouping the grid toggles, grid opacity
and a curve-alpha slider. Mouse-enabled is genuinely **per axis** — pan, wheel
and right-drag all consult it — because pinning one axis while exploring the
other is the point of the option.

Mouse mode is set on the *panel*, not written to the settings file: a
right-click is a per-plot choice, and persisting it would change every other
panel behind the user's back.

**The legend is draggable**, as `LegendItem` is. It is grabbed before the pan
gesture, so moving it never pans the view underneath, and it is clamped back
inside the plot rectangle when the panel shrinks under it. `LinePlot` only
*creates* one when `gui.plot.show_legend` says so — another checkbox the
settings dialog wrote and no plot read, which is why "the legend drag is broken"
was really "there is no legend".

### Test the seam the application uses, not the one that is convenient

Both of those shipped broken with a green suite, for the same reason: the tests
built a **bare canvas**, and the application builds a `Plot`. A bare canvas has
no host, so nothing could see that the canvas forwarded the menu to its hosting
`Plot` while the `Plot` — seeing `provides_native_menu` — deferred straight
back. Both deferred, a right-click raised nothing, and no test could tell.
`test_a_right_click_on_a_hosted_plot_shows_the_menu` goes through `Plot`, and
has to pin the active backend to do it: the rest of the module constructs
canvases from the backend directly, which is exactly what let the seam go
unexercised.

# Where to pick this up — the emtk backend

**Plot settings reach the plots (2026-10-12):** see "Settings ▸ Plots changed no plot". Next:
re-style *open* fit windows when a plot setting changes (the one gap left; it needs `LinePlot`
to re-apply its director to existing handles). Re-measure with the probe described there before
and after — a setting that changes the preview but not an exported `LinePlot` panel is the
failure mode this closed.

**Auto-range "A" button (2026-10-12):** done on both stacks (see "Auto-range, and mouse
behaviour worth copying"). Next: run the full click-all sweep and read each plugin JSON's
`auto_range` list — a plot reported "shows no A after zoom/pan" is one whose wheel and drag a
parent takes (the known "wheel does not reach docked widgets" gap), not a button bug; and decide
whether an implot plot with no data should return to its default limits on the click (today the
limits stay, the A hides).

**W8 state (2026-10-10, closed): pyqtgraph is gone.** No file under `chisurf/` imports it,
the `pyqtgraph` backend and `_passthrough.py` are deleted, `pixi.toml` / `pyproject.toml` /
`rattler-recipe/recipe.yaml` no longer declare it, and both allow-lists are retired
(`test/pyqtgraph_import_allowlist.txt` deleted; `test/chiplot_native_allowlist.txt` stays, empty).
`test/test_pyqtgraph_seam.py` now bans the import outright, checks the three manifests, and checks
that `CHISURF_PLOT_BACKEND=pyqtgraph` (and, until 2026-10-12, `gui.plot.backend`) raises a `KeyError` saying
the backend was removed. chiplot has **no passthrough**: an unknown attribute on `Plot`, `Grid`,
`ImageView` or the package is an `AttributeError` where it is written, `chiplot.colormap` is a
plain function, `Backend.raw_module` is gone.

What W8 added to chiplot (emtk backend; the base contract names each so a backend that cannot do
one raises by name):

* `ImageView` is now a real image dock, so the AutoForm `image` section (`ImageMapWidget`, ~800
  lines of `pg.ImageView`) is ~500 lines over it: frames (`frame_count`, `frame`, `set_frame`,
  `frame_changed`, a slider shown only for stacks, `play(fps, loop=)` / `pause` / `stop` /
  `set_fps` / `set_loop`, `playing_changed`; a stack keeps **one** colour scale across frames),
  `set_extent((x0, x1, y0, y1))` + `pixel_at(x, y)` (axes carry the quantity; clicks map back
  to a pixel), `set_labels`, `set_axes_visible`, `invert_y`, `set_aspect_locked` (equal pixels:
  the plot box shrinks to the range's proportions), `auto_range`, `view_range`, `marks(x, y,
  symbol=, size=, pen=, brush=)` and `label(text, x, y)` drawn **over** the picture, `on_hover`,
  a colour ramp with draggable levels (`set_histogram_width`), `add_roi(..., resizable=True)`
  (corner grips that keep the opposite corner fixed even when crossed), RGB(A) overlays, and
  **brush painting**: `enable_brush(kernel, on_stroke=)` / `brush_mask` / `set_brush_mask` /
  `disable_brush` (a kernel stamped along the stroke, interpolated so a fast drag leaves no gaps,
  floored at zero so a negative kernel erases; the overlay layer is translucent; a drag that
  starts on a shape still moves the shape). Backend side: `EmtkCanvas.set_paint_handler`,
  `add_marks`, `set_aspect_locked`; images are blitted as an **underlay** now, so curves, marks and
  shapes are no longer hidden behind the picture (they were: images used to be painted after
  `plot.draw`); the post-plot drawing is clipped to the plot box so a panned picture cannot spill; ellipse, polygon and rotated shapes now draw a 1.5 px outline (they were a faint fill only, which hid the fitted circle's edge).
* `Plot.set_interactive(menu=...)` now honours the flag on a backend with no menu of its own
  (the "static preview" plots in the ICS preview still popped chiplot's right-click menu).
* Differences from the pyqtgraph dock, deliberate: the LUT **histogram** became a colour ramp with
  draggable levels (no histogram); a stroke on the brush layer is clipped at zero (pyqtgraph let an
  erase push a pixel negative, which `selection_array` then had to special-case); the pick ring and
  the detected-point markers follow the slice for a stack (the pick ring did not before); the
  default gate rectangle is the central half of the *image* (x = a column) where it used the
  transposed shape.

Tests: `test/gui/test_chiplot_image_dock.py` (28, the view alone), `test/gui/test_image_section_features.py`
(19, every option of the section through a model), `test/gui/test_image_section_axes.py`,
`test/gui/test_chiplot_api.py` (the old pyqtgraph-pinned `test_chiplot.py` ported to emtk: 50
tests, the ones that asserted pyqtgraph internals dropped), and the guard above.

`tttr/intensity_trace/qt_tool.py` and the Trace Browser Qt oracle (`trace_browser/widget.py`,
`gui/tool.py`, `test_widgets.py`) were **retired together**: the native apps have parity (functional
parity audit); every test that compared against the Qt widget now compares against the values it
produced (recorded 2026-10-10 in the test files: `QT_DERIVED`, `QT_ROWS`, `QT_CSV` with a sha256,
the series totals); the hand-off `open_intensity_trace` opens the native app in a Qt host window.
Both manifests dropped `"gui"`.

**Where to pick this up**

0. **Qt out of chiplot — done 2026-10-13** (see "What it is"; [qt-retirement](/subsystems/qt-retirement.md)
   items 6 and 9). Measure: `grep -rnE "\bQt|qtpy|PyQt|PySide|qt_host|qt_painter|ControlHost|\bQ[A-Z][a-zA-Z]+"
   chisurf/chiplot` is empty (the guard's own regex); `grep -rnE "cp\.(Plot|Grid|ImageView)\b" chisurf test` is empty.
   Export pair (scratch `export_pairs.py`, real IBH decays, an image, bars; HEAD snapshot vs tree): a Qt-hosted
   panel's export is **byte-identical** (9 of 9, still painted by Qt in `PanelHost`); a core `Panel`'s export is
   **not pixel-equal** and cannot be -- another rasteriser: same content, curves 1 px where Qt's antialiased
   pen drew ~2 px, bars/image within antialiasing (1.8-6.4 % of pixels). Trap found: at the previous HEAD a core
   `Panel.export_image` painted a `QImage` and **segfaulted without a `QApplication`**; and the fit window's
   right-click *Export image…* / *Export data as CSV…* called `_on_export_*`, which a core `Panel` lacks
   (`AttributeError` since the pages moved to the core) -- both now go through emtk's save dialog
   (`test/native_emtk/test_fit_window_panel_export.py`). Open: the Qt forms that host panels (`PanelHost`,
   `ImagePanelHost`) are the last reason the host layer exists; it goes with them in S6.
1. ~~"Advanced: pyqtgraph Configuration" in Settings ▸ Plots~~ — **done 2026-10-12**: all four
   options dropped (emtk antialiases and pans with the left button always; plots follow the
   theme), the key removed with a load-time migration (`settings_utils.RETIRED_KEYS`), strings
   re-extracted and translated (de/fr). See "Settings ▸ Plots changed no plot".
2. `okf/validation/release-readiness-w6g/plugin-inventory.md` is stale (the `plugin_inventory.py
   --write` record): two plugins lost their Qt entry here, and other lanes' ports changed it too.
3. Not tried / not done: an emtk **histogram** beside the colour ramp of `ImageView`; `Grid` image panels
   with the new frame slider (only the standalone `ImageView` has one); the `image` section's `add_roi`
   rotation (`rotatable` is accepted and ignored: emtk draws no rotation grip).

**Current verified contract (2026-10-07):** the native backend already exists
in `chisurf/gui/chiplot/backends/emtk_backend.py`; the older package-design
text below is historical and awaits W0 reconciliation. Axis units now travel
through `set_labels(left_units=..., bottom_units=..., right_units=...,
top_units=...)`: `None` preserves metadata and an empty string clears it.
`set_si_prefix` changes displayed ticks/label prefixes without scaling source
data. The pyqtgraph adapter enforces SI-off even after label updates; emtk
renders actual unit/SI labels on its existing left/bottom axes. Right/top
metadata is retained but those axes are not yet rendered by emtk.

`Curve.get_data()` returns original samples on both backends, including log
and downsampling modes; empty curves return empty arrays. Parent111 targeted
cases and959 available Part A guards pass (16 expected skips). All eight
measured before/after scenes were inspected; the legacy PG unit image is
byte-identical and all200 BH count-rate samples retain their hashes. Source
typing45before/45after is an explicit inherited W0 gate, not fixed here.
[Acceptance](../validation/release-readiness-w1/chiplot-axis-units/receipt.json).
Next immediate caller: Burst Selection's28 plotting references; use this API
and preserve its old SI settings before removing its direct-import allowance.

The native backend to build is **chimol's emtk** ([PRD-104](/prds/prd-104.md);
ChiSurf direction 2026-08-14): a `chisurf/gui/chiplot/backends/emtk/` package
implementing the `backends/base.py` contract on top of emtk's
`begin_plot`/`Plot.line`/`Plot.scatter`/… builders (`Canvas`, `GridCanvas`,
`ImageViewCanvas` + every handle protocol). chiplot is emtk's first external
consumer; the gaps PRD-104 Phase 2 must close first are **log axes, bars,
error bars, regions, pan/zoom, image**. **Measure a backend with
`python test/gui/chiplot_ab_screenshots.py` and read the PNG pairs** — that is
the only instrument that has caught anything here. The A/B traps, both of which
cost a session:

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

1. **Read emtk first.** `chisurf/plugins/chimol/chimol/emtk/` (`plot.py`,
   `axis.py`, its Phase 1 line/scatter) plus PRD-104's reading order; grow
   emtk's Phase 2 breadth as the chiplot contract demands it, in-tree, rather
   than reaching past the seam.
2. **Bring the plot families over.** The A/B script covers primitives, not the
   application's panels. Start with the highest-volume ones (TCSPC decay +
   weighted-residual pair, FCS curves, burst histograms), compare screenshots
   against pyqtgraph. This is what decides whether the backend can become the
   default.
3. **Retire `backends/wgpu/` and `backends/opengl/` together.** They are
   superseded experiments, kept registered only until the emtk backend exists
   (`test/gui/test_chiplot_wgpu.py` pins `"wgpu" in available_backends()`; the
   flip lands with the emtk backend). Deleting `opengl/` also removes
   `PyOpenGL`'s last plotting use, and `wgpu` + `rendercanvas` join it off the
   dependency graph (`pixi.toml`). The three "worth keeping" lessons from the wgpu era — offscreen
   render + `QPainter` blit, handles contribute geometry, CPU-expanded strokes
   — are recorded in [the native-renderer section](#the-native-renderer-is-emtk-not-webgpu).
4. **A zero-copy surface path** (from the wgpu era; deferred): every repaint
   read the framebuffer back to the CPU. That is the right trade for plot
   panels, and the wrong one for an animated view. Do not start this before
   (2) — it buys nothing until a panel is found that needs it.
5. **Long-term convergence.** emtk (the **Embeddable iMmediate-mode ToolKit**, formerly cmtk), living
   inside chimol; ChiSurf reaches it via chimol (chimol independence comes
   first — see [chimol-relocation.md](/plugins/chimol-relocation.md)) — so
   the 2-D convergence is by construction: chiplot draws through emtk; no
   second GL
   stack. chimol's 3-D surface ([PRD-57](/prds/prd-57.md)) stays its own. The
   further-horizon move (emtk replacing PyQt as the UI backend behind AutoForm,
   for a web-capable ChiSurf and licence-clean Qt-free status) is recorded in
   [PRD-64](/prds/prd-64.md)'s "Long-term direction".

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

## Histogram ranges and caption cleanup — 2026-10-08

Actual Burst plot migration exposed two owning renderer gaps: pinned PG text
survived clear, and native bar-only ranges ignored bar rectangles. Both now
have real regression guards; raw data remains unchanged, native extents include
bin edges and zero baseline, and log transforms belong to the renderer.
Caller set_ylim receives data coordinates, preventing a second log transform.
Parent116plot-family cases pass; all six old/PG/native panel scenes inspected.
The two renderer type baselines18/18 remain unchanged (W0); no native escape,
passthrough allowance or dependency was added.
