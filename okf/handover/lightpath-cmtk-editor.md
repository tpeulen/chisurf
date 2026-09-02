---
title: Handover — wire the beam path onto the cmtk node editor
status: open
group: handover
updated: 2026-09-02
---

# Handover: the beam path is the last consumer on the old editor

Everything the beam path needs is built and tested. What is left is the
window: `chisurf/plugins/core/lightpath_simulator/gui/tool.py` still builds
`NodeScene`/`NodeView`. **The plugin works today** — the `.native` crash is
fixed — so this is a port, not a repair, and a half-done swap is worse than
the current state.

## What already exists

| piece | where | state |
|---|---|---|
| the editor | `cmtk.nodes` | 41 tests |
| graph as a plain object | `node_editor/document.py` | schema v1 unchanged |
| the control | `node_editor/cmtk_control.py` | `GraphControl`, Qt-free |
| the Qt host | `node_editor/widget.py` | `NodeGraphWidget` |
| **the beam-path node bodies** | `lightpath_simulator/gui/cmtk_view.py` | `BeampathContent`, 12 tests |

`BeampathContent` already draws the three-layer spectrum through `implot` and
the category-filtered component chooser. It is not reached by the running app.

## The measurement

**42 touchpoints** in `tool.py`. Unlike globalview — which reached its canvas
through six members, so a drop-in widget covered it — this tool reaches
*through* the scene into items. That is why a widget substitution does not
work here:

* `_build_default_path` constructs `NodeGraphicsItem`/`EdgeGraphicsItem`
  directly and calls `self.scene.addItem(...)` ten times;
* `propagate_graph` does
  `[it for it in self.scene.items() if isinstance(it, NodeGraphicsItem)]` and
  writes into `it.model.config`;
* `_on_add_node_requested` builds an item from a registry type and a content
  factory;
* three `from_dict` paths (file, preset, MMFDB), plus `to_dict`, `clear`,
  `node_adder`, `view.fit_all`, `view.mapToScene`.

## The port, in order

1. **`BeampathGraphWidget`** = `NodeGraphWidget` with `content=BeampathContent()`.
   Follow `globalview/gui/network_widget.py`: present the surface `tool.py`
   already calls, do not subclass the scene.
2. **The load paths first, because they are testable on their own.** The three
   `scene.from_dict(normalize_lightpath_graph(...))` calls become
   `load_graph_dict(normalize_lightpath_graph(...))`; `view.fit_all` becomes
   `fit_graph`; `scene.to_dict()` becomes `graph_dict()`.
3. **`_build_default_path` and `_on_add_node_requested`** become document
   operations — `document.add_node(GraphNode(...))` and `add_edge` from the
   registry type — instead of constructing graphics items. This is the bulk of
   the work and the part that needs a screenshot.
4. **`propagate_graph`** becomes `document.to_dict()` → RPC → merge each
   `states[node_id]` into `document.node(id).config`. The proxy traversal and
   the `_update_plot` callback both disappear: there is no proxy to cross, and
   a body is redrawn because the next frame reads the config.
5. **Delete what that orphans** in `gui/node_types.py`: `trigger_simulator_update`
   (walks proxy → scene → view → parent), `make_combo_opaque` (patches
   `QComboBox.showPopup`), `create_node_container`/`finish_node_container`,
   `add_spectral_plot`, and the four `get_*_factory` functions. The
   `NodeType` registrations at the foot stay — they are Qt-free and
   `BeampathContent` reads them.

## Verify it like this

```bash
QT_QPA_PLATFORM=offscreen CHISURF_SETTINGS_DIR=/tmp/lp \
  python -m test.gui.node_editor_baseline after node-lightpath
```

and **read the PNG**. The baseline half is already captured at
`/tmp/chisurf-migration/node-lightpath.before.png` — eight components, each
with a spectrum in it. Judge on control inventory, not pixels: every component
present, its chooser reachable, its spectrum drawn.

## Traps, all of which have already cost time on this port

* **A fixture on the wrong schema loads as an empty canvas and reports
  nothing.** `pos` is not `position`; an edge port is an *index*, not a name.
* **Fit before show fits to a 100x30 box** and the graph renders as a speck.
  Show, drain the event queue, then fit — and the cmtk editor fits on the
  *next paint*, because a fit needs measured node sizes.
* **Nothing in a node body may take the container's full width.** A node is
  not a container: one full-width control makes the node as wide as the
  editor, fit-to-content zooms out to frame it, and the graph piles into a
  corner. It reads as a broken editor.
* **Three rounds of this port went wrong by approximating what the old code
  already did** (boxes for marks, straight lines for arcs, raw layout units
  for fitted ones). When the brief is "make it look like the old one", open
  the old one's drawing code first.

## Related

* [node-editor](../subsystems/node-editor.md) — the subsystem, and the
  globalview swap this one should imitate.
* [known-issues](../references/known-issues.md) — the `.native` entry.
