"""Render the node editor and its consumers, as one half of a migration pair.

The PyQt node editor under ``chisurf/gui/widgets/node_editor/`` is being
replaced by one built on cmtk, and a replacement is reviewable only against a
*before*. This module renders each surface that the migration touches, so the
same script produces both halves: run it on the legacy tree for ``before`` and
on the ported tree for ``after``.

The surfaces are the three real consumers plus the editor itself:

``editor``
    :class:`~chisurf.gui.widgets.node_editor.editor.NodeEditorWidget` with its
    example graph, side panel and timeline -- the widest control inventory.
``viewer``
    :class:`~chisurf.gui.widgets.node_editor.node_viewer.NodeViewerWidget`,
    read-only, which is what the AutoForm ``node_graph`` section embeds.
``provenance``
    the editor loaded with an MMFDB-shaped provenance graph, which is how
    ``mmfdb_admin`` uses it.
``lightpath``
    the lightpath simulator's tool window, the one consumer that drives
    ``NodeScene``/``NodeView`` directly rather than through the editor widget.

Run it as::

    QT_QPA_PLATFORM=offscreen python -m test.gui.node_editor_baseline before

Images and a JSON control inventory land in ``/tmp/chisurf-migration``
(override with ``CHISURF_MIGRATION_DIR``).
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import typing

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("CHISURF_SETTINGS_DIR", "/tmp/chisurf-migration-settings")

from qtpy import QtWidgets

from test.gui.migration_parity import DEFAULT_DIR, capture, control_inventory

#: Which half of the pair is being rendered. Set from the phase in
#: :func:`main`, and read by the builders that have two implementations to
#: choose between -- so one script produces both halves rather than two scripts
#: that can drift apart.
_CMTK: bool = False

#: Every surface the migration touches, as ``name -> builder``.
SURFACES: dict = {}


def surface(name: str) -> typing.Callable:
    """Register a builder under `name`.

    Parameters
    ----------
    name : str
        The stem shared by the ``before`` and ``after`` halves of the pair.

    Returns
    -------
    typing.Callable
        A decorator that registers the builder and returns it unchanged.
    """

    def register(fn: typing.Callable) -> typing.Callable:
        SURFACES[name] = fn
        return fn

    return register


@surface("node-editor")
def _editor() -> typing.Any:
    """Build the editor widget with its example graph.

    Returns
    -------
    typing.Any
        A :class:`NodeEditorWidget` showing the built-in arithmetic example.
    """
    from chisurf.gui.widgets.node_editor.editor import NodeEditorWidget

    return NodeEditorWidget(build_example=True, show_side_panel=True, show_timeline=True)


@surface("node-viewer")
def _viewer() -> typing.Any:
    """Build the read-only viewer the AutoForm ``node_graph`` section embeds.

    Returns
    -------
    typing.Any
        A :class:`NodeViewerWidget` holding a small three-node graph.
    """
    if _CMTK:
        from chisurf.gui.widgets.node_editor.widget import NodeGraphWidget

        viewer = NodeGraphWidget(read_only=True)
    else:
        from chisurf.gui.widgets.node_editor.node_viewer import NodeViewerWidget

        viewer = NodeViewerWidget(read_only=True)
    viewer.load_graph_dict(_SMALL_GRAPH)
    return viewer


@surface("node-provenance")
def _provenance() -> typing.Any:
    """Build the editor holding an MMFDB-shaped provenance graph.

    Returns
    -------
    typing.Any
        A read-only :class:`NodeEditorWidget` showing operations and artifacts.
    """
    from chisurf.plugins.core.mmfdb_admin.gui.provenance_graph import (
        mmfdb_graph_to_node_editor_graph,
    )

    if _CMTK:
        from chisurf.gui.widgets.node_editor.widget import NodeGraphWidget

        editor = NodeGraphWidget(read_only=True)
    else:
        from chisurf.gui.widgets.node_editor.editor import NodeEditorWidget

        editor = NodeEditorWidget(
            build_example=False, read_only=True, graph_purpose="provenance"
        )
    editor.load_graph_dict(mmfdb_graph_to_node_editor_graph(_PROVENANCE_GRAPH))
    return editor


@surface("node-lightpath")
def _lightpath() -> typing.Any:
    """Build the lightpath simulator, the direct ``NodeScene``/``NodeView`` user.

    Returns
    -------
    typing.Any
        The simulator's tool widget, with whatever default graph it builds.
    """
    from chisurf.plugins.core.lightpath_simulator.gui.tool import LightPathSimulatorWidget

    widget = LightPathSimulatorWidget()
    # An empty canvas proves nothing about node rendering, and the tool opens
    # empty. Its own "Reset to Default" builds the stock optical path, which is
    # the state a user actually sees.
    for name in ("reset_to_default", "_reset_to_default", "on_reset_to_default"):
        action = getattr(widget, name, None)
        if callable(action):
            action()
            break
    else:  # pragma: no cover - the button is the fallback path
        for button in widget.findChildren(QtWidgets.QPushButton):
            if "reset" in button.text().lower():
                button.click()
                break
    return widget


#: A graph small enough to read in a screenshot and wide enough to show a node
#: body, two port kinds and an edge. It is written against the **real** schema
#: in ``node_editor/json_schema.md`` -- ``pos`` not ``position``, and an edge
#: port is an *index* into the node's port list, not its name. A fixture that
#: gets either wrong loads as an empty canvas and reports no error, which is
#: the failure that makes a baseline worthless.
_SMALL_GRAPH = {
    "version": 1,
    "nodes": [
        {
            "id": "n0",
            "type": "constant",
            "title": "Constant",
            "inputs": [],
            "outputs": ["Value"],
            "config": {"value": 2.5, "label": "Value"},
            "pos": [-320.0, -90.0],
            "collapsed": False,
        },
        {
            "id": "n1",
            "type": "constant",
            "title": "Constant",
            "inputs": [],
            "outputs": ["Value"],
            "config": {"value": 4.0, "label": "Value"},
            "pos": [-320.0, 60.0],
            "collapsed": False,
        },
        {
            "id": "n2",
            "type": "binary_op",
            "title": "Operation",
            "inputs": ["A", "B"],
            "outputs": ["Result"],
            "config": {"op": "Add"},
            "pos": [-20.0, -20.0],
            "collapsed": False,
        },
        {
            "id": "n3",
            "type": "output",
            "title": "Output",
            "inputs": ["Result"],
            "outputs": [],
            "config": {},
            "pos": [260.0, -20.0],
            "collapsed": False,
        },
    ],
    "edges": [
        {"source": "n0", "source_port": 0, "target": "n2", "target_port": 0},
        {"source": "n1", "source_port": 0, "target": "n2", "target_port": 1},
        {"source": "n2", "source_port": 0, "target": "n3", "target_port": 0},
    ],
}

#: The shape ``mmfdb_graph_to_node_editor_graph`` really consumes: nodes keyed
#: by ``node_type``/``node_id``, and edges naming those pairs as ``source_node_type``/``source_node_id``. The
#: converter drops any node missing either key **without saying so**, so a
#: fixture in the wrong shape renders a blank graph rather than an error.
_PROVENANCE_GRAPH = {
    "nodes": [
        {"node_type": "operation", "node_id": "op1", "name": "import",
         "method": "read_tttr", "timestamp": "2026-09-02"},
        {"node_type": "artifact", "node_id": "art1", "name": "raw.ptu"},
        {"node_type": "operation", "node_id": "op2", "name": "correlate",
         "method": "fcs", "timestamp": "2026-09-02"},
        {"node_type": "artifact", "node_id": "art2", "name": "g(t)"},
    ],
    "edges": [
        {"source_node_type": "operation", "source_node_id": "op1",
         "target_node_type": "artifact", "target_node_id": "art1",
         "relationship_type": "produces"},
        {"source_node_type": "artifact", "source_node_id": "art1",
         "target_node_type": "operation", "target_node_id": "op2",
         "relationship_type": "consumes"},
        {"source_node_type": "operation", "source_node_id": "op2",
         "target_node_type": "artifact", "target_node_id": "art2",
         "relationship_type": "produces"},
    ],
}


def graph_inventory(widget: typing.Any) -> dict:
    """Enumerate what the *graph* holds, which the Qt control inventory cannot.

    :func:`~test.gui.migration_parity.control_inventory` walks the ``QWidget``
    tree, and a node editor keeps nothing there: nodes, ports, edges and the
    controls embedded in a node body are items in a ``QGraphicsScene`` (or, in
    the replacement, drawn by cmtk with no ``QWidget`` at all). Comparing only
    the widget tree therefore reports the two implementations as identical
    while every node has vanished.

    What is comparable across both is the graph itself, because both serialise
    to the schema in ``node_editor/json_schema.md``. This returns that, reduced
    to what a reviewer checks: which nodes exist, what each one is called, what
    ports it carries, and which of them are wired together.

    Parameters
    ----------
    widget : typing.Any
        A surface exposing ``graph_dict()``, holding a widget that does, or
        holding a ``NodeView`` whose scene serialises.

    Returns
    -------
    dict
        ``node_titles``, ``node_types``, ``ports`` (per node title), ``edges``
        as endpoint pairs, and the counts of each. Empty when the surface holds
        no graph.
    """
    graph = None
    if hasattr(widget, "graph_dict"):
        graph = widget.graph_dict()
    else:
        for child in widget.findChildren(QtWidgets.QWidget):
            if hasattr(child, "graph_dict"):
                graph = child.graph_dict()
                break
    if graph is None:
        # The lightpath simulator drives ``NodeScene``/``NodeView`` directly and
        # has no ``graph_dict``; the scene serialises to the same schema.
        from chisurf.gui.widgets.node_editor.view import NodeView

        for view in widget.findChildren(NodeView):
            scene = view.scene()
            if scene is not None and hasattr(scene, "to_dict"):
                graph = scene.to_dict()
                break
    if graph is None:
        return {}

    nodes = list(graph.get("nodes") or [])
    by_id = {n.get("id"): n for n in nodes}

    def port_names(entries) -> list:
        """Read port names whether they are bare strings or objects."""
        out = []
        for entry in entries or []:
            out.append(entry if isinstance(entry, str) else str(entry.get("name", "")))
        return out

    return {
        "node_count": len(nodes),
        "node_titles": sorted(str(n.get("title", "")) for n in nodes),
        "node_types": sorted({str(n.get("type", "")) for n in nodes}),
        "ports": {
            str(n.get("id")): {
                "inputs": port_names(n.get("inputs")),
                "outputs": port_names(n.get("outputs")),
            }
            for n in nodes
        },
        "config_keys": sorted(
            {k for n in nodes for k in (n.get("config") or {})}
        ),
        "edge_count": len(graph.get("edges") or []),
        "edges": sorted(
            "{}:{} -> {}:{}".format(
                by_id.get(e.get("source"), {}).get("title", e.get("source")),
                e.get("source_port"),
                by_id.get(e.get("target"), {}).get("title", e.get("target")),
                e.get("target_port"),
            )
            for e in (graph.get("edges") or [])
        ),
    }


def _frame_the_graph(widget: typing.Any, app: typing.Any) -> None:
    """Fit every node view in `widget` to its contents, at its final size.

    Fitting is a transform computed from the viewport, so doing it before the
    widget has been shown and resized computes it against the default 100x30
    box: the graph then renders as a four-pixel speck in the middle of a
    1200x780 image, with nothing anywhere reporting a problem. Show, let the
    layout settle, *then* fit.

    Parameters
    ----------
    widget : typing.Any
        The surface about to be captured.
    app : typing.Any
        The running ``QApplication``, whose event queue must drain before the
        viewport reports its real size.
    """
    from chisurf.gui.widgets.node_editor.view import NodeView

    widget.show()
    app.processEvents()
    for view in widget.findChildren(NodeView):
        if view.scene() is not None and view.scene().items():
            view.fit_all()
    if hasattr(widget, "fit_graph"):
        # The cmtk editor fits on the *next* paint, because a fit needs the
        # measured size of every node and a node has no size until it has been
        # drawn once. One repaint measures, the next one frames.
        widget.fit_graph()
        app.processEvents()
        widget.repaint()
        app.processEvents()
    app.processEvents()


def main(argv: typing.Sequence[str]) -> int:
    """Render every registered surface for one half of the pair.

    Parameters
    ----------
    argv : typing.Sequence[str]
        ``argv[1]`` is the phase, ``"before"`` or ``"after"``; the rest, if
        given, restrict the run to those surface names.

    Returns
    -------
    int
        ``0`` when every requested surface rendered, ``1`` otherwise.
    """
    global _CMTK

    phase = argv[1] if len(argv) > 1 else "before"
    _CMTK = phase == "after"
    wanted = list(argv[2:]) or list(SURFACES)

    from qtpy import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    out_dir = pathlib.Path(os.environ.get("CHISURF_MIGRATION_DIR", DEFAULT_DIR))
    out_dir.mkdir(parents=True, exist_ok=True)

    inventories: dict = {}
    failed = []
    for name in wanted:
        try:
            widget = SURFACES[name]()
            widget.resize(1200, 780)
            _frame_the_graph(widget, app)
            path = capture(widget, name, phase, out_dir=out_dir, width=1200, min_height=780)
            inventories[name] = {
                "controls": control_inventory(widget),
                "graph": graph_inventory(widget),
            }
            print(f"{name}: {path}", flush=True)
        except Exception as exc:  # noqa: BLE001 - one broken surface must not hide the rest
            failed.append(name)
            print(f"{name}: FAILED {type(exc).__name__}: {exc}", flush=True)
            import traceback

            traceback.print_exc()

    # Merged, not overwritten: a run restricted to one surface must not erase
    # the other three's inventories, which is how a partial re-run silently
    # destroys the half of the pair it did not rebuild.
    record = out_dir / f"node-editor-inventory.{phase}.json"
    merged = json.loads(record.read_text()) if record.exists() else {}
    merged.update(inventories)
    record.write_text(json.dumps(merged, indent=2, sort_keys=True, default=str))
    app.processEvents()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
