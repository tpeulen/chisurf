"""Unit tests for DAG checks in node editor."""

import pytest
from qtpy import QtWidgets

from chisurf.gui.widgets.node_editor.scene import NodeScene
from chisurf.gui.widgets.node_editor.node_item import NodeGraphicsItem
from chisurf.gui.widgets.node_editor.model import NodeModel, PortSpec


class MockMouseEvent:
    def __init__(self, scene_pos=None, button=None):
        self._scene_pos = scene_pos
        self._button = button
        self._accepted = False

    def scenePos(self):
        return self._scene_pos

    def button(self):
        return self._button

    def accept(self):
        self._accepted = True

    def setScenePos(self, pos):
        self._scene_pos = pos

    def setButton(self, btn):
        self._button = btn



@pytest.fixture
def app():
    """Ensure a QApplication exists for the duration of the DAG tests."""

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


@pytest.fixture
def scene(app):  # noqa: ARG001 - app fixture ensures QApplication exists
    """Create a NodeScene for testing."""
    return NodeScene()


def test_empty_scene_dag(scene):
    """Test DAG checks on empty scene."""
    assert scene.is_directed_acyclic() is None
    assert scene.has_cycles() is False


def test_single_node_dag(scene):
    """Test DAG checks with single node."""
    model = NodeModel(
        title="Test",
        inputs=[],
        outputs=[PortSpec(name="Out", is_output=True)],
        node_type="test",
        config={}
    )
    item = NodeGraphicsItem(model)
    scene.addItem(item)

    assert scene.is_directed_acyclic() is None  # No edges
    assert scene.has_cycles() is False


def test_linear_chain_dag(scene):
    """Test acyclic linear chain."""
    # Node A -> Node B -> Node C
    models = []
    for i in range(3):
        model = NodeModel(
            title=f"Node {i}",
            inputs=[PortSpec(name="In", is_output=False)] if i > 0 else [],
            outputs=[PortSpec(name="Out", is_output=True)],
            node_type="test",
            config={}
        )
        models.append(model)
        item = NodeGraphicsItem(model)
        scene.addItem(item)

    items = [it for it in scene.items() if isinstance(it, NodeGraphicsItem)]

    # Connect A -> B -> C
    from chisurf.gui.widgets.node_editor.edge_item import EdgeGraphicsItem
    edge1 = EdgeGraphicsItem(items[0].port_items[0], items[1].port_items[0])
    scene.addItem(edge1)
    scene.register_edge(edge1)

    edge2 = EdgeGraphicsItem(items[1].port_items[1], items[2].port_items[0])
    scene.addItem(edge2)
    scene.register_edge(edge2)

    assert scene.is_directed_acyclic() is True
    assert scene.has_cycles() is False


def _port(item, name):
    """Return the port item called ``name`` on ``item``.

    ``QGraphicsScene.items()`` returns items in stacking order, not the order
    they were added, so a test that indexes into it is testing Qt's z-order
    rather than the graph.
    """
    for port in item.port_items:
        if port.spec.name == name:
            return port
    raise AssertionError(f"no port {name!r} on {item.model.title!r}")


def test_cycle_detection(scene):
    """Test cycle detection."""
    # Two nodes, each with one input and one output, so they can be wired into
    # a two-node cycle: Node 1 out -> Node 2 in, Node 2 out -> Node 1 in.
    model1 = NodeModel(
        title="Node 1",
        inputs=[PortSpec(name="In", is_output=False)],
        outputs=[PortSpec(name="Out", is_output=True)],
        node_type="test",
        config={}
    )
    model2 = NodeModel(
        title="Node 2",
        inputs=[PortSpec(name="In", is_output=False)],
        outputs=[PortSpec(name="Out", is_output=True)],
        node_type="test",
        config={}
    )

    item1 = NodeGraphicsItem(model1)
    item2 = NodeGraphicsItem(model2)
    scene.addItem(item1)
    scene.addItem(item2)

    from chisurf.gui.widgets.node_editor.edge_item import EdgeGraphicsItem
    edge1 = EdgeGraphicsItem(_port(item1, "Out"), _port(item2, "In"))
    scene.addItem(edge1)
    scene.register_edge(edge1)

    edge2 = EdgeGraphicsItem(_port(item2, "Out"), _port(item1, "In"))
    scene.addItem(edge2)
    scene.register_edge(edge2)

    assert scene.is_directed_acyclic() is False
    assert scene.has_cycles() is True
    assert [sorted(c) for c in scene.find_cycles()] == [[0, 1]]


def test_enforce_acyclic_flag(scene, monkeypatch):
    """Test enforce_acyclic prevents cycle-creating edges."""
    scene.enforce_acyclic = True

    # Create two nodes
    model1 = NodeModel(
        title="Node 1",
        inputs=[PortSpec(name="In", is_output=False)],
        outputs=[PortSpec(name="Out", is_output=True)],
        node_type="test",
        config={}
    )
    model2 = NodeModel(
        title="Node 2",
        inputs=[PortSpec(name="In", is_output=False)],
        outputs=[PortSpec(name="Out", is_output=True)],
        node_type="test",
        config={}
    )

    item1 = NodeGraphicsItem(model1)
    item2 = NodeGraphicsItem(model2)
    scene.addItem(item1)
    scene.addItem(item2)

    # First, connect 1 -> 2 (should work)
    from qtpy import QtCore
    from chisurf.gui.widgets.node_editor.port_item import NodePortGraphicsItem

    port1_out = item1.port_items[1]  # outputs[0] at index 1 (inputs[0] at 0)
    port2_in = item2.port_items[0]

    # Simulate mouse press on port1_out
    scene._current_edge = None
    monkeypatch.setattr(scene, "itemAt", lambda pos, tf: port1_out)
    event_press = MockMouseEvent()
    event_press.setScenePos(port1_out.scene_pos())
    event_press.setButton(QtCore.Qt.LeftButton)
    scene.mousePressEvent(event_press)

    # Simulate mouse release on port2_in
    monkeypatch.setattr(scene, "itemAt", lambda pos, tf: port2_in)
    event_release = MockMouseEvent()
    event_release.setScenePos(port2_in.scene_pos())
    event_release.setButton(QtCore.Qt.LeftButton)
    scene.mouseReleaseEvent(event_release)

    # Should have one edge
    assert len(scene.edges) == 1

    # Now try to connect 2 -> 1 (would create cycle)
    port2_out = item2.port_items[1]
    port1_in = item1.port_items[0]

    scene._current_edge = None
    monkeypatch.setattr(scene, "itemAt", lambda pos, tf: port2_out)
    event_press2 = MockMouseEvent()
    event_press2.setScenePos(port2_out.scene_pos())
    event_press2.setButton(QtCore.Qt.LeftButton)
    scene.mousePressEvent(event_press2)

    monkeypatch.setattr(scene, "itemAt", lambda pos, tf: port1_in)
    event_release2 = MockMouseEvent()
    event_release2.setScenePos(port1_in.scene_pos())
    event_release2.setButton(QtCore.Qt.LeftButton)
    scene.mouseReleaseEvent(event_release2)

    # Should still have only one edge (cycle prevented)
    assert len(scene.edges) == 1


def test_cycle_highlighting_marks_cycle_edges(scene):
    """update_cycle_highlighting should flag only edges that are in cycles."""

    from chisurf.gui.widgets.node_editor.edge_item import EdgeGraphicsItem

    # Create three nodes, each with one input and one output
    items = []
    for i in range(3):
        model = NodeModel(
            title=f"Node {i}",
            inputs=[PortSpec(name="In", is_output=False)],
            outputs=[PortSpec(name="Out", is_output=True)],
            node_type="test",
            config={},
        )
        item = NodeGraphicsItem(model)
        scene.addItem(item)
        items.append(item)

    # Build an acyclic chain: 0 -> 1 -> 2
    e1 = EdgeGraphicsItem(items[0].port_items[1], items[1].port_items[0])
    scene.addItem(e1)
    scene.register_edge(e1)

    e2 = EdgeGraphicsItem(items[1].port_items[1], items[2].port_items[0])
    scene.addItem(e2)
    scene.register_edge(e2)

    scene.update_cycle_highlighting()
    assert e1._is_in_cycle is False  # type: ignore[attr-defined]
    assert e2._is_in_cycle is False  # type: ignore[attr-defined]

    # Now add edge 2 -> 0 to form a cycle involving all three edges
    e3 = EdgeGraphicsItem(items[2].port_items[1], items[0].port_items[0])
    scene.addItem(e3)
    scene.register_edge(e3)

    scene.update_cycle_highlighting()
    assert e1._is_in_cycle is True   # type: ignore[attr-defined]
    assert e2._is_in_cycle is True   # type: ignore[attr-defined]
    assert e3._is_in_cycle is True   # type: ignore[attr-defined]
