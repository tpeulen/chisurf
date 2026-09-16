---
title: Handover — wire the beam path onto the emtk node editor
status: done
group: handover
updated: 2026-09-02
---

# Handover: the beam path is the last consumer on the old editor

**Done 2026-09-02.** `lightpath_simulator/gui/tool.py` now builds
`NodeGraphWidget(content=BeampathContent(...))` instead of `NodeScene`/
`NodeView`; `node_types.py` lost the five Qt widget-factory functions
(`trigger_simulator_update`, `make_combo_opaque`, `create_node_container`/
`finish_node_container`, `add_spectral_plot`, and the four `get_*_factory`s) and
is now Qt-free — just the registry. Verified: all 56 `lightpath_simulator`
tests pass; `python -m test.gui.node_editor_baseline after node-lightpath`
(run today as `python -m test.gui.node_editor_baseline node-lightpath`, the
phase argument having gone with the old editor)
renders with the same 8-node/7-edge topology as the `before` capture
(`node-editor-inventory.{before,after}.json` agree exactly once the port index
convention is translated) and the same control counts (7 buttons, 9 controls,
14 tables). `node_types.py` no longer belongs on
`test/chiplot_native_allowlist.txt` and has been struck from it.

**Superseded 2026-09-03:** the departure described below is undone. emtk's
zoom now scales node *contents* — while a node submits, the painter re-shapes
its glyphs at the zoom and the non-font layout metrics follow, so a node's
pixel size is no longer fixed — and `fit_to_content` solves the ordinary fit
equation. `_build_default_path` still centres on the sample for the first
paint (a node has no size until it has been drawn once) and then calls
`_fit_view()`: the whole 8-node path lands in the panel, nodes and all.

One deliberate departure from the plan below: **`_build_default_path` pans
instead of fitting.** emtk kept a node's pixel size fixed regardless of zoom,
so fitting this 8-node, plot-heavy graph to the panel only shrank the
*spacing* between nodes, never their fixed-size bodies — every zoom that made
the whole graph fit also made adjacent nodes overlap. The Qt version had the
same problem and solved it the same way: `view.centerOn(550, 200)`, a 1:1 view
the user pans, never a fit. The port did the same (`_centre_view`, zoom held
at 1.0). It centred on the **sample**, not the splitter: the source and the
sample are the only two nodes with a spectrum before a component is assigned
downstream, so those are what a first look should show — verify this against a
real backend, not the no-server smoke test, because a screenshot with nothing
behind `simulate()` looks identical whether the centring is right or wrong (no
node has a spectrum either way). Wire one up in five lines the same way
`test_headless.py::test_lightpath_api_client_unwraps_rpc_envelope` does:
`LightPathClient(InProcessClient(ServiceDispatcher(SessionState())))` after
`register_services(dispatcher)`, no ZMQ, no timeout.

**Closed 2026-09-03:** `mmfdb_admin/gui/tool.py` builds
`NodeGraphWidget(read_only=True)` now — the "interactive editor" note below
turned out to be stale, the dock only ever instantiated it read-only — and the
old scene editor itself is deleted. See
[subsystems/node-editor](../subsystems/node-editor.md).

---

Everything the beam path needs is built and tested. What is left is the
window: `chisurf/plugins/core/lightpath_simulator/gui/tool.py` still builds
`NodeScene`/`NodeView`. **The plugin works today** — the `.native` crash is
fixed — so this is a port, not a repair, and a half-done swap is worse than
the current state.

## What already exists

| piece | where | state |
|---|---|---|
| the editor | `emtk.nodes` | 41 tests |
| graph as a plain object | `node_editor/document.py` | schema v1 unchanged |
| the control | `node_editor/emtk_control.py` | `GraphControl`, Qt-free |
| the Qt host | `node_editor/widget.py` | `NodeGraphWidget` |
| **the beam-path node bodies** | `lightpath_simulator/gui/emtk_view.py` | `BeampathContent`, 12 tests |

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
  python -m test.gui.node_editor_baseline node-lightpath
```

and **read the PNG** — eight components, each with a spectrum in it. Judge on
control inventory, not pixels: every component present, its chooser reachable,
its spectrum drawn. (The `before`/`after` phase argument is gone with the old
editor; the harness renders the current state plain.)

## Traps, all of which have already cost time on this port

* **A fixture on the wrong schema loads as an empty canvas and reports
  nothing.** `pos` is not `position`; an edge port is an *index*, not a name.
* **Fit before show fits to a 100x30 box** and the graph renders as a speck.
  Show, drain the event queue, then fit — and the emtk editor fits on the
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
