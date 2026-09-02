---
title: The node editor
status: in-progress
group: subsystems
updated: 2026-09-02
---

# The node editor

ChiSurf shows graphs in four places: the lightpath simulator's optical path,
MMFDB's provenance DAG, the AutoForm `node_graph` section, and the standalone
editor with its arithmetic example. All four are drawn by one editor, and that
editor is being moved off PyQt onto [cmtk](../plugins/chimol-cmtk.md).

## Where to pick this up

**2026-09-02, latest — globalview is WIRED. The beam path is not.**

`globalview/gui/tool.py` builds `ParameterNetworkWidget` now, not
`ParameterGraphCanvas`. The swap was one import and one constructor because
the new widget presents the canvas' *own* surface — `set_graph`, `refit`,
`node_radius`, `selected_nodes_idx`, and the three signals — over the cmtk
control. It is deliberately a surface and not a subclass: the canvas is a
`QWidget` that paints itself, this is a host around a toolkit-free control,
and all they share is what the tool asks of them.

Verified by opening the real `GraphWizard` offscreen, feeding it a graph and
screenshotting it: legend, discs, arced edges with the arrowhead, minimap,
and the size slider scaling every mark while keeping owners larger than
parameters.

**Two things left there**, both small and both unverified because they need a
live fit:

1. `linkRequested` / `linkRemovalRequested` are declared and never emitted.
   The wiring is `is_link_created` → `report_link(follower, master)` and
   `is_link_destroyed` → `linkRemovalRequested`, in `_on_select`'s neighbour.
   Until that lands, links can be *drawn* in the panel but the fit model is
   not told.
2. `document_from_arrays` gives every node one in and one out pin, so the
   editor will accept a link between any two marks — including two fits.
   `GraphControl._accepts` rejects same-kind ports and self-links, and that
   is all; a parameter-to-fit link should be refused too.

**The beam path is still on the old canvas**: `lightpath_simulator/gui/tool.py`
builds `NodeScene`. Its `propagate_graph` becomes `document.to_dict()` → RPC →
merge each `states[node_id]` into `document.node(id).config`; there is no proxy
to cross and no `_update_plot` callback to call any more.


**2026-09-02, latest — the edges are the diagram's, read out of the diagram's
own source rather than approximated. Read this first.**

The lesson worth carrying: *when the brief is "make it look like the old one",
open the old one's drawing code.* Two rounds were spent guessing — first boxes
instead of marks, then straight lines instead of arcs — and both were settled
in minutes by reading `chisurf/gui/widgets/graph_canvas.py`'s `curved_edge`
and `draw_arrow_head`. The three concepts it encodes are now in
`cmtk.nodes` as `LinkRouting.ARC`:

1. **Rim to rim.** `p0 = centre_i + u * r_from`, `p3 = centre_j - u * r_to`,
   along the line joining the centres. This is what removes the horizontal
   stub: a pin-routed edge always leaves sideways, so a node directly *above*
   another is joined by a curve that goes out to the right, turns round and
   comes back.
2. **A bow of 12% of the chord, clamped to 10–22px**, with the control points
   **60%** of the way from each end toward the bowed mid-point. Proportional
   because a constant offset makes a short edge a semicircle and a long one
   look straight; clamped because unclamped makes a long edge a loop. The 60%
   is what makes the curve leave and arrive along its own tangent.
3. **The arrowhead is aimed from the last control point**, 30° half-angle,
   `10 + width/2` long. Aim it from the other node's centre and it points
   somewhere the line does not arrive from.

A mutual pair is pushed 7px aside and bowed wider, or A→B and B→A land on each
other and read as one edge.

`_link_curve()` feeds the drawing, the hover test *and* the arrowhead. Three
descriptions of where a link is would be three things to keep in step, and the
one that drifts makes a link clickable somewhere it is not drawn —
`test_hover_follows_the_arc_and_not_the_pins` asserts hover at the curve's own
mid-point, which for a bowed arc is off the chord.

**Still open, unchanged**: both tool windows (`globalview/gui/tool.py`,
`lightpath_simulator/gui/tool.py`) still build the old canvases.


**2026-09-02, latest — globalview draws marks, not boxes, and looks like the
canvas it replaces. Read this first.**

The first port drew every parameter as a titled box and it was unreadable: a
box per parameter is mostly padding, and twenty fill a screen that should hold
two hundred. `cmtk.nodes` grew `NodeShape.DISC` — a shaded circle with its
label on a plate underneath — and four things came with it, each because the
disc exposed something the editor could only say one way:

* `PinShape.NONE` — the pin is hit-tested and takes links, it is just not
  drawn. A disc is its own connector.
* `Style.link_straight` — the editor's curve always leaves rightwards and
  arrives leftwards, so in a Kamada-Kawai layout half the edges loop back on
  themselves and the loops hide the shape the layout computed.
* `link(arrow=True)` — a head, pointed along the curve's tangent at the tip.
  Only the *link* edge gets one: ownership and base edges are symmetric
  statements about membership and a head on them says something untrue.
* `GraphControl.set_document` **preserves the style**. It used to build a
  fresh `EditorContext`, so the first graph looked right and every graph
  loaded after it silently reverted to the defaults.

**The defect worth remembering from this round**: the disc branch in
`_draw_node` was placed *after* the title bar, so every label was drawn twice
— once by the title bar and once by the disc, a few pixels apart, in two
different colours. It reads as a font-rendering artefact rather than as two
draws, which is exactly why it survived being looked at. `RecordingPainter`
and counting `text` calls is what found it, and
`test_a_disc_label_is_drawn_once` is what keeps it found.

`apply_network_style(editor)` is the one call that makes an editor look like a
diagram: straight links, quiet grid, no node outline, a wider pin hover radius
so the pointer catches the mark rather than an undrawn dot. `draw_legend` is
called by the host *after* `end_node_editor`, because the key is not part of
the graph — it does not pan, does not zoom, and must not be box-selected.

**Still open, unchanged from below**: both tool windows (`globalview/gui/tool.py`,
`lightpath_simulator/gui/tool.py`) still build the old canvases.


**2026-09-02, latest — globalview's graph is ported, and the content renderer
grew the three hooks that made it possible. Read this first.**

`NodeContentRenderer` now has four overridables, and between them they are what
lets one editor serve graphs that mean different things:

| hook | what it decides |
|---|---|
| `draw_body(node, read_only)` | what is inside a node |
| `node_style(node)` | its title-bar colour |
| `link_style(edge)` | an edge's colour and thickness |
| `port_label(node, port, is_output)` | the text beside a pin, `""` for none |

`node_style`/`link_style` are hooks rather than fields on the document on
purpose: a colour is a *rendering* decision about a kind of thing, and the
document is what gets serialised. Writing it into the config would put a
palette into every saved file, and changing the palette would leave every
existing file painted the old way.

**globalview**: `globalview/gui/cmtk_view.py`. `graph_result_to_document`
turns the RPC's `GraphResult` into a `GraphDocument`, recovering each edge's
*kind* from what its two endpoints are — owner↔owner is a base edge,
owner↔parameter is ownership, parameter↔parameter is a link. Derived rather
than transmitted, so it cannot disagree with the graph. Node ids are the
adapter's `node_idx`, so a selection resolves back without a second mapping to
keep in step. 10 tests.

**Still open on globalview**, and this is the whole remainder:

1. **`gui/tool.py` (1047 lines) still builds `ParameterGraphCanvas`.** The
   swap needs three signals rewired: `selectionChanged` (now
   `GraphControl.on_select`), `linkRequested` (now `is_link_created`, which
   already reports `(output, input)` in a fixed order however the user
   dragged), and `linkRemovalRequested` (now `is_link_destroyed`). The
   canvas's `n_selected_nodes = 2` master/follower dance has no equivalent
   and does not need one — a link is made by dragging pin to pin.
2. **The parameter tables are still `QTableWidget`.** This is where the user's
   "may need additional table features in cmtk" lands. `cmtk.widgets.tables`
   has `DataTable` with sizing policies, resize, reorder, multi-sort, hiding
   and frozen panes; what it is missing for this panel is **editable cells**
   bound to a model attribute. Check that before writing anything: the port is
   there and only the write path may be absent.
3. **`graph_canvas.py` also serves the state-scheme diagram**, so deleting it
   is not part of retiring globalview's use of it. Check `grep -rn
   "graph_canvas"` before removing anything.


**2026-09-02, later — four defects fixed and the beam path's node bodies are
written. Read this before the older list below, which it partly retires.**

Fixed, all four in cmtk (`~/dev/cmtk`, commits `d1f96a9` and `7ccc19f`), and
all four found by rendering a node and *looking* rather than by a failing test:

1. **The title bar covered the first body row.** The bar is the title text
   expanded by the node padding, so its bottom edge is one padding below the
   text; the layout cursor put the next row one *item spacing* below, which is
   smaller. imnodes' `EndNodeTitleBar` moves the cursor to the content origin
   for exactly this reason and the port only measured.
2. **`set_cursor_screen_pos` discarded the group's extents**, because it routed
   through `Layout.reset` — the *frame* reset. A group containing a cursor move
   measured only what came after it, so fixing (1) made a node narrower than
   its own title. There is a `Layout.move_cursor_to` now.
3. **`PushItemWidth` behaved as a one-shot**, so only the first control in a
   node got the pushed width and every one after it filled the row. In a panel
   that is invisible; in a node the second control stretches the node across
   the viewport, fit-to-content zooms out to frame it, and the whole graph
   piles into the corner. **This is the one to remember**: it presents as "the
   editor is broken", and the cause is one missing fallback. It also rebaked
   `tests/golden/imgui_knobs.png`, whose old image had the entire second knob
   off-screen — the golden was pinning the defect.
4. **`implot` painted through `ctx.p`** while every `im_widgets` control paints
   through the drawlist. Identical until something splits the drawlist to draw
   out of order — which a node editor does — and then an embedded plot is
   painted first and the node body is replayed over it. The plot was simply
   absent. Also, `ImPlotFlags_NoLegend` was accepted and ignored, so a plot two
   inches wide had its curves covered by a key naming them.

**Nodes now stick like windows.** `EditorContext.stick_to_nodes` (on) and
`EditorContext.snap_to_grid` (off) are separate switches: the grid is a tidy
layout, sticking is *these two nodes touching*, and sticking wins where both
apply. Modelled on chimol's `_snap_to_windows` — an edge sticks to a
neighbour's facing edge only when the two overlap along the other axis, which
is what stops a node in a distant row catching a column it is nowhere near.
The tolerance is screen pixels converted to grid units, or the stick reaches
further the more you zoom out until everything catches everything. A hint
outlines what was caught. **A multi-node drag snaps once**, for the node under
the pointer, and applies that offset to the selection — snapping each node
separately tears the group apart.

**The beam path's node bodies are done** and are the template for every other
node type: `lightpath_simulator/gui/cmtk_view.py`, `BeampathContent`. It draws
the three-layer spectrum (input dotted grey, output white, the component's own
characteristic coloured on top, each normalised separately because they are
different physical quantities) through `implot`, plus the probe chooser
filtered by category. 12 tests, no display needed. What it replaces in
`gui/node_types.py` is worth reading as the argument for the whole move: a
function that patches `QComboBox.showPopup` to force an opaque background,
another that walks proxy → scene → view → parent to find something with a
`propagate_graph` method, and a "hack to trigger node resize" reaching into a
node item's private `_build_path`.

**Still open on the beam path**: the tool window itself
(`lightpath_simulator/gui/tool.py`) still builds `NodeScene`/`NodeView`. The
wiring it needs is small now — `propagate_graph` becomes
`document.to_dict()` → RPC → merge each `states[node_id]` into
`document.node(id).config` — because there is no proxy to cross and no
`_update_plot` callback to call. `easy_mode.py` (1912 lines) is a separate
dialog and does not touch the graph canvas.


**2026-09-02 — the new editor exists, is tested, and three of four consumers
have not been switched to it yet.** In order:

1. **`NodeViewerWidget` and `NodeEditorWidget` still wrap the Qt scene.**
   `chisurf/gui/widgets/node_editor/widget.py` (`NodeGraphWidget`) is the
   replacement and is drop-in for the methods those two expose — `load_graph_dict`,
   `load_graph_from_json`, `load_graph_from_file`, `graph_dict`, `to_json`,
   `save_graph_to_file`, `clear_graph`, `fit_graph`, `set_read_only`,
   `selected_node`, `selected_edge`, and the `graphChanged`/`nodeSelected`/
   `edgeSelected` signals. What it does **not** have yet, and what has to be
   decided before the swap rather than discovered after it:
   * the **side panel** — the widget palette tree and the Load/Save/Evaluate
     JSON pane. Those are ordinary Qt and should stay Qt, beside the host
     rather than inside it.
   * the **timeline transport** at the foot of the editor (`timeline_widget.py`).
   * **undo/redo** (`state_tracker.py`, `SceneStateTracker`). The document is a
     plain object now, so undo is a stack of `to_dict()` snapshots rather than
     a `QUndoCommand` per gesture — simpler, and it has to be written.
   * the **context menu** (add node by type, duplicate, align, auto-layout).
     `scene.py` has ~600 lines of it; the registry it reads is Qt-free already.
2. **The lightpath simulator is the hard one and should be done last.** It is
   the only consumer that drives `NodeScene`/`NodeView`/`NodeGraphicsItem`
   directly rather than through a widget, and its nodes embed **plots** — the
   spectra visible in `node-lightpath.before.png`. cmtk has `implot`, so the
   plots have a home; the work is that `NodeContentRenderer` needs a
   per-node-type dispatch (a `dict` from `node.type` to a body function) rather
   than the generic config walk it does today.
3. **Measure the swap against the captured pair, do not eyeball it.**
   `test/gui/node_editor_baseline.py` renders all four surfaces and takes the
   phase as its argument, so `before` and `after` come out of one script:

   ```bash
   QT_QPA_PLATFORM=offscreen python -m test.gui.node_editor_baseline before
   QT_QPA_PLATFORM=offscreen python -m test.gui.node_editor_baseline after
   ```

   It writes PNGs and a **graph inventory** — node titles, per-node port names,
   edges as endpoint pairs — to `/tmp/chisurf-migration`. The graph inventory
   is the one that matters: `control_inventory` walks the `QWidget` tree, and a
   node editor keeps nothing there, so it reports the Qt and cmtk versions as
   identical while every node has vanished.

   **The trap in taking that measurement**, which cost real time here: a
   fixture written against the wrong schema loads as an empty canvas and
   reports no error. `pos` is not `position`, and an edge port is an *index*,
   not a name. The `before` half was captured twice for this reason.

   **The second trap**: `fit_graph` computes a transform from the viewport, so
   calling it before the widget has been shown and resized fits to the default
   100x30 box and the graph renders as a four-pixel speck in the middle of a
   1200x780 image. Show, drain the event queue, *then* fit. For the cmtk
   editor there is a further step — it fits on the next *paint*, because a fit
   needs measured node sizes and a node has no size until it has been drawn.

4. **Two cosmetic gaps, neither blocking.** Output port labels are
   left-aligned where the Qt editor right-aligned them (imnodes leaves the
   alignment to the caller, and node width is not known during submission).
   And the minimap shows a faint diagonal in some views that has not been run
   down — it is a new feature the Qt editor did not have, so it is not a
   regression.

## Which node editor, and why

Five ImGui node editors were measured before one was adopted — the whole "Node
Editors" section of Dear ImGui's *Useful Extensions* page, each run through
cmtk's `tools/autoport` and counted. The table lives in `cmtk/nodes.py`'s
module docstring, which is where someone reading the code will look for it.
The short form: **Nelarius/imnodes** wins, because it is dependency-free, uses
only the public ImGui API plus `ImDrawList`, and carries the widest feature set
that stays small (4.2 kloc, 11 templates, no smart pointers, no inheritance).
thedmd/imgui-node-editor is richer and three times the size with its own canvas
and drawlist-splitter machinery; ImNodeFlow is retained and template-driven, so
a port is a rewrite; VisualNodeSystem needs glm and jsoncpp; rokups/ImNodes is
unmaintained and too thin.

`cmtk.nodes` is a **re-implementation** of that design rather than the
mechanical port, in the same relationship cmtk as a whole has to Dear ImGui.
The one thing taken from the candidate that lost is the pan/zoom canvas, which
imnodes does not have.

**The zoom scales the canvas, not the glyphs**, and that is a property of cmtk
rather than a shortcut: both shipped painters report a fixed glyph cell, so
`push_font(font, size)` changes no measurement and a node's pixel size is the
same at every zoom. Zooming out spreads the nodes apart and shrinks nothing
inside them. `fit_to_content` solves for that explicitly — the graph's screen
extent is `zoom x origin_span + node_size`, part scaling and part constant, and
a fit that divides by the whole extent leaves the outermost nodes off screen.

## How it is put together

| file | what it is |
|---|---|
| `document.py` | the graph as a plain object: nodes, edges, schema v1 I/O, and the string↔int id mapping the renderer needs. No Qt, no cmtk. |
| `cmtk_control.py` | the editor: draws a document through `cmtk.nodes` and edits it. Implements cmtk's control contract (`draw`/`press`/`drag`/`release`/`hover`/`scroll`/`key`), so the same object serves a Qt host, a browser host and a headless test. |
| `widget.py` | `NodeGraphWidget` — a `ControlHost` around the control plus the Qt signals. Twelve lines of Qt. |
| `model.py`, `registry.py`, `validation.py`, `graph.py` | unchanged, and already Qt-free. |
| `scene.py`, `view.py`, `node_item.py`, `edge_item.py`, `port_item.py`, `node_viewer.py`, `editor.py` | the PyQt editor being replaced. Still live: three consumers use them. |

The serialised form does not change. It is still schema v1 from
`json_schema.md`, so a project saved by the Qt editor loads into the new one.

### Ids

A node's id in the schema is a string the host chooses; `cmtk.nodes` keys
everything by int. `GraphDocument` maps between them, and the number is derived
from the node's **position in the document** rather than from a counter — a
fresh number each frame would reset every node's dragged position on every
repaint, with nothing reporting a problem. The consequence to remember is that
**deleting a node renumbers the ones after it**, so the renderer's pool has to
be rebuilt at the same time or the survivors move onto the deleted node's
coordinates.

## Two things this uncovered

**The port index had two conventions.** `json_schema.md` says `source_port`
indexes the node's `outputs` and `target_port` its `inputs`. `scene.py` indexed
a single flat list of inputs-then-outputs, and
`mmfdb_admin/gui/provenance_graph.py` wrote `"source_port": 1` to match it. A
reader that follows the schema finds no output 1 and drops the edge — so the
provenance graph rendered as four nodes with nothing joining them. The
converter now writes `0`, and `GraphDocument.from_dict` **logs** every edge it
drops with the reason, because the failure mode is silent and total: all the
nodes load and all the edges disappear.

**Two cmtk seams were wrong** and are fixed upstream in `~/dev/cmtk` (see that
repo's commit `2ae83b7`): the drawlist's channel splitter recorded `text_width`
and `line_height` as if they were drawing calls, so any widget inside a channel
measured `None`; and `end_group` updated the layout's last item but not the
context's, so `get_item_rect_min`/`max` after a group described the last widget
inside it rather than the group. Both are the kind that produce a wrong picture
rather than an exception.

## Related

* [cmtk](../plugins/chimol-cmtk.md) — the toolkit this is built on.
* [chiplot](chiplot.md) — the other cmtk consumer, for plots.
* [testing](../workflows/testing.md) — the before/after migration rule this
  followed.
