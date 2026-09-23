---
title: The node editor
status: current
group: subsystems
updated: 2026-09-03
---

# The node editor

ChiSurf shows graphs in four places: the lightpath simulator's optical path,
MMFDB's provenance DAG, the AutoForm `node_graph` section, and the standalone
demo (`python -m chisurf.gui.widgets.node_editor`). All four are drawn by one
editor, and since 2026-09-03 that editor is
[emtk](../plugins/chimol-emtk.md) end to end. The PyQt `QGraphicsScene` editor it grew out
of is **deleted** — `editor.py`, `scene.py`, `view.py`, the graphics items, the
read-only `NodeViewerWidget`, the timeline/side-panel chrome, the eval modules
and the theme layer are gone; nothing imports them.

## What there is now

Three layers in `chisurf/gui/widgets/node_editor/`, only the last of which
imports Qt:

* **Document** (`document.py`) — the graph as a plain object, serialising to
  the schema v1 in `json_schema.md`.
* **Control** (`emtk_control.py`) — `GraphControl` draws the document through
  `emtk.nodes` and turns events into edits; `NodeContentRenderer` draws node
  bodies. Qt-free, so the editor's behaviour is testable headlessly
  (`test/test_node_editor_emtk.py`).
* **Widget** (`widget.py`) — `NodeGraphWidget`, the class consumers
  instantiate: a `ControlHost` around the control plus the Qt signals
  (`graphChanged`, `nodeSelected`, `edgeSelected`, `nodeActivated`,
  `selectionCleared`) and the programmatic surface (`load_graph_dict`,
  `graph_dict`, `select_node`, `selected_node`, `fit_graph`).

Consumers, and what they add on top:

| consumer | hosts | adds |
|---|---|---|
| lightpath simulator | `NodeGraphWidget` + `BeampathContent` | palette double-click to create nodes |
| globalview | `GraphControl` drawn inside `GlobalViewSurface` (one `ImApp` frame) | `on_link`/`on_unlink` arbitration against the fit model; discs and squares (`MARK_SHAPES`) |
| mmfdb_admin | `NodeGraphWidget(read_only=True)` | nothing — a pure viewer |
| AutoForm `node_graph` | `NodeGraphWidget(read_only=True)` | nothing — a viewer bound to a model method |

## The port-index convention, and the trap it left

Schema v1 indexes **per direction**: an edge's `source_port` counts through the
source node's `outputs`, its `target_port` through the target's `inputs`. The
deleted scene editor indexed one flat per-node list, inputs first — and so did
the lightpath easy-mode builder and the headless simulator until 2026-09-03,
which is how the first post-migration week could pass every test while
propagation silently skipped every edge leaving a node that had inputs (a
flat index below the input count decodes as an input on both sides, and the
edge was dropped). Both now speak schema v1; `test_easy_mode.py` pins the
pass-through.

Graphs **saved by the deleted editor** (flat indices) are not translated back:
on load, out-of-range edges are dropped loudly by `GraphDocument.from_dict`,
and an in-range flat index lands on the wrong pin of a multi-output node.
Rebuild those via Easy Mode or Reset to Default rather than loading them.

## Zoom

Zoom scales the nodes. emtk's canvas zoom always moved positions, pins, links
and the grid; since 2026-09-03 it scales node *contents* too: while a node
submits, the painter re-shapes its glyphs at the zoom (Qt re-renders the face
crisp) and the non-font layout metrics scale with it — and since a node's body
*is* its laid-out content, the node itself shrinks and grows. `fit_to_content`
now solves the ordinary fit equation, so a dense graph — the beam path is the
standing example — frames its whole extent in the panel instead of being
panned at 1:1. An editor that wants the old canvas-only zoom sets
`EditorContext.scale_content = False`; a host scales the pixel sizes *it*
passes into the layout (item widths, plot sizes) by `nodes.content_scale()`.

## Related

* [lightpath-emtk-editor](../handover/lightpath-emtk-editor.md) — the beam-path
  port, and the screenshot harness run it introduced.
* [chimol-emtk](../plugins/chimol-emtk.md) — the toolkit underneath.
