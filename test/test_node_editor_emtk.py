"""The emtk-backed node editor: the document, and the control that edits it.

None of these need a display or a Qt binding -- the whole point of moving the
editor off ``QGraphicsScene`` is that the graph and its behaviour are now
testable without one. The Qt wrapper is thin enough that what it adds is
signals, and those are covered in the GUI suite.
"""
from __future__ import annotations

import pytest

from chisurf.gui.widgets.node_editor.document import (
    GraphDocument,
    GraphEdge,
    GraphNode,
)
from chisurf.gui.widgets.node_editor.model import PortSpec

emtk = pytest.importorskip("emtk")

from chisurf.gui.widgets.node_editor.emtk_control import GraphControl  # noqa: E402

#: A graph in schema v1 with every shape the loader has to cope with: bare
#: string ports, typed object ports, config, and an edge between them.
GRAPH: dict = {
    "version": 1,
    "meta": {"purpose": "test"},
    "nodes": [
        {
            "id": "c1",
            "type": "constant",
            "title": "Constant",
            "inputs": [],
            "outputs": ["Value"],
            "config": {"value": 2.5},
            "pos": [0.0, 0.0],
        },
        {
            "id": "op",
            "type": "binary_op",
            "title": "Operation",
            "inputs": [
                {"name": "A", "type": "sF", "is_output": False},
                {"name": "B", "type": "sF", "is_output": False},
            ],
            "outputs": [{"name": "Result", "type": "sF", "is_output": True}],
            "config": {"op": "Add"},
            "pos": [300.0, 40.0],
        },
    ],
    "edges": [],
}


def _document() -> GraphDocument:
    """Build the shared fixture graph.

    Returns
    -------
    GraphDocument
    """
    return GraphDocument.from_dict(GRAPH)


# ---------------------------------------------------------------------------
# The document
# ---------------------------------------------------------------------------


def test_a_graph_survives_a_round_trip():
    """Loading and saving returns the same graph, not an approximation."""
    document = _document()
    again = GraphDocument.from_dict(document.to_dict())

    assert [n.id for n in again.nodes] == ["c1", "op"]
    assert [n.title for n in again.nodes] == ["Constant", "Operation"]
    assert again.node("op").config == {"op": "Add"}
    assert again.node("c1").pos == (0.0, 0.0)
    assert again.meta == {"purpose": "test"}


def test_an_untyped_port_round_trips_as_a_bare_string():
    """A port with nothing to say is written as its name, as it was read.

    Promoting every port to an object would rewrite every graph in the tree on
    first save, which turns "the user opened a file" into a diff.
    """
    saved = _document().to_dict()
    assert saved["nodes"][0]["outputs"] == ["Value"]
    assert saved["nodes"][1]["outputs"][0]["type"] == "sF"


def test_an_edge_to_a_port_that_is_not_there_is_dropped():
    """A dangling edge is refused at load, not carried and drawn as nothing.

    Keeping it makes the graph evaluate differently from what is on screen,
    with nothing anywhere reporting the difference.
    """
    data = dict(GRAPH)
    data = GraphDocument.from_dict(GRAPH).to_dict()
    data["edges"] = [
        {"source": "c1", "source_port": 0, "target": "op", "target_port": 9},
        {"source": "c1", "source_port": 0, "target": "nope", "target_port": 0},
        {"source": "c1", "source_port": 0, "target": "op", "target_port": 0},
    ]
    document = GraphDocument.from_dict(data)
    assert len(document.edges) == 1
    assert document.edges[0].target_port == 0


def test_a_pin_id_decodes_back_to_its_port():
    """Every pin id names exactly one (node, index, direction).

    The renderer reports a link the user drew as a pair of pin *ids*, so a
    decoding that is not exact wires the edge to the wrong port -- and the
    graph still looks plausible.
    """
    document = _document()
    for node in document.nodes:
        for index, _ in enumerate(node.inputs):
            pin = document.pin_id(node.id, index, False)
            assert document.port_for_pin(pin) == (node, index, False)
        for index, _ in enumerate(node.outputs):
            pin = document.pin_id(node.id, index, True)
            assert document.port_for_pin(pin) == (node, index, True)


def test_pin_ids_do_not_collide_across_nodes():
    """Two nodes' pins are distinct numbers, which is what makes them ids."""
    document = _document()
    seen = set()
    for node in document.nodes:
        for index in range(len(node.inputs)):
            seen.add(document.pin_id(node.id, index, False))
        for index in range(len(node.outputs)):
            seen.add(document.pin_id(node.id, index, True))
    expected = sum(len(n.inputs) + len(n.outputs) for n in document.nodes)
    assert len(seen) == expected


def test_too_many_ports_is_an_error_rather_than_a_wrap():
    """A node beyond the pin budget raises instead of aliasing another node.

    Wrapping silently gives two ports the same id, and the symptom -- a link
    that appears on a different node -- points nowhere near the cause.
    """
    document = _document()
    with pytest.raises(ValueError):
        document.pin_id("c1", GraphDocument.PINS_PER_NODE, True)


def test_removing_a_node_takes_its_edges():
    """An edge with no endpoint is not left behind."""
    document = _document()
    document.add_edge(GraphEdge("c1", 0, "op", 0))
    assert len(document.edges) == 1

    document.remove_node("c1")
    assert document.edges == []


def test_adding_a_node_whose_id_is_taken_renames_it():
    """Two nodes cannot share an id, so the second one gets a new one."""
    document = _document()
    added = document.add_node(GraphNode("c1", title="Another"))
    assert added.id != "c1"
    assert len({n.id for n in document.nodes}) == len(document.nodes)


# ---------------------------------------------------------------------------
# The control
# ---------------------------------------------------------------------------


def _draw(control, box=(0, 0, 800, 400), frames=1):
    """Draw the control into a recording painter.

    Parameters
    ----------
    control : GraphControl
        The control to draw.
    box : tuple
        The box to draw into.
    frames : int
        How many frames to run; interaction needs at least two, since the
        first is what measures the nodes the second one hit-tests.
    """
    from emtk.testing import RecordingPainter

    painter = RecordingPainter()
    for _ in range(frames):
        control.draw(painter, *box)
    return painter


def test_the_control_draws_a_graph_without_a_display():
    """The editor renders through a painter that opens no window."""
    control = GraphControl(_document())
    painter = _draw(control)
    assert painter.calls, "nothing was drawn"


def test_a_node_position_survives_a_frame():
    """Positions come out of the document and go back into it unchanged."""
    control = GraphControl(_document())
    control.set_document(control.document, fit=False)
    _draw(control, frames=2)
    assert control.document.node("op").pos == (300.0, 40.0)


def test_a_read_only_control_refuses_a_link():
    """Read-only means read-only: an edge the user draws is not added."""
    control = GraphControl(_document(), read_only=True)
    control.set_document(control.document, fit=False)
    _draw(control, frames=2)

    document = control.document
    control.editor._link_created = (
        document.pin_id("c1", 0, True),
        document.pin_id("op", 0, False),
    )
    assert control._apply_interactions() is False
    assert document.edges == []


def test_a_link_between_incompatible_ports_is_refused():
    """An untyped port matches only another untyped one.

    The typed/untyped distinction used to be invisible because every untyped
    port defaulted to the literal string "spectral", so everything matched
    everything. It is a real check now, and this is what pins it.
    """
    control = GraphControl(_document())
    document = control.document
    # "Value" is untyped; "A" is sF.
    assert control._accepts(GraphEdge("c1", 0, "op", 0)) is False

    document.node("c1").outputs[0] = PortSpec(name="Value", is_output=True, port_type="sF")
    assert control._accepts(GraphEdge("c1", 0, "op", 0)) is True


def test_an_input_takes_only_one_edge():
    """A second edge into the same input is refused, not silently ignored."""
    control = GraphControl(_document())
    document = control.document
    document.node("c1").outputs[0] = PortSpec(name="Value", is_output=True, port_type="sF")
    document.add_edge(GraphEdge("c1", 0, "op", 0))

    assert control._accepts(GraphEdge("c1", 0, "op", 0)) is False
    assert control._accepts(GraphEdge("c1", 0, "op", 1)) is True


def test_a_node_cannot_link_to_itself():
    """A self-edge is not a graph edge."""
    control = GraphControl(_document())
    assert control._accepts(GraphEdge("op", 0, "op", 0)) is False


def test_deleting_a_selection_renumbers_without_moving_the_survivors():
    """Removing a node must not shift the remaining nodes' positions.

    Node ids in the renderer are *positions in the list*, so a delete
    renumbers everything after it. Reusing the old pool would move each
    survivor onto the coordinates of whichever node used to hold its number.
    """
    from emtk import nodes

    control = GraphControl(_document())
    control.set_document(control.document, fit=False)
    _draw(control, frames=2)
    before = control.document.node("op").pos

    nodes.select_node(control.editor, control.document.node_number("c1"))
    assert control.delete_selection() is True

    _draw(control, frames=2)
    assert [n.id for n in control.document.nodes] == ["op"]
    assert control.document.node("op").pos == before


def test_the_content_key_changes_when_the_graph_does():
    """A cached repaint must be invalidated by anything the picture shows.

    A key that misses a change produces a correct picture of an older moment,
    which reads to a user as "the editor does not work".
    """
    control = GraphControl(_document())
    before = control.content_key()

    control.document.node("op").title = "Renamed"
    assert control.content_key() != before

    moved = control.content_key()
    control.document.node("op").pos = (10.0, 10.0)
    assert control.content_key() != moved
