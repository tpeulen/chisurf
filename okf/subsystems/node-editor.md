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
