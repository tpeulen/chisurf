import pytest
from qtpy import QtWidgets

pytest.importorskip("emtk")

from chisurf.gui.widgets.node_editor.widget import NodeGraphWidget

#: A small graph in schema v1 -- ``pos`` not ``position``, and an edge port
#: is an index into the node's per-direction port list.
GRAPH: dict = {
    "version": 1,
    "meta": {"purpose": "test"},
    "nodes": [
        {
            "id": "a",
            "type": "constant",
            "title": "Constant A",
            "inputs": [],
            "outputs": ["Value"],
            "config": {"value": 2.5},
            "pos": [-260.0, -80.0],
            "collapsed": False,
        },
        {
            "id": "b",
            "type": "constant",
            "title": "Constant B",
            "inputs": [],
            "outputs": ["Value"],
            "config": {"value": 4.0},
            "pos": [-260.0, 90.0],
            "collapsed": False,
        },
        {
            "id": "op",
            "type": "binary_op",
            "title": "Operation",
            "inputs": ["A", "B"],
            "outputs": ["Result"],
            "config": {},
            "pos": [60.0, 0.0],
            "collapsed": False,
        },
    ],
    "edges": [
        {"source": "a", "source_port": 0, "target": "op", "target_port": 0},
        {"source": "b", "source_port": 0, "target": "op", "target_port": 1},
    ],
}


@pytest.fixture
def app():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


@pytest.fixture
def editor(app):  # noqa: ARG001 - ensures QApplication exists
    widget = NodeGraphWidget()
    widget.load_graph_dict(GRAPH)
    return widget


def test_gui_widgets_node_edit_round_trip(editor):
    graph_dict = editor.graph_dict()
    assert graph_dict["nodes"]
    assert graph_dict["edges"]

    editor.clear_graph()
    assert not editor.graph_dict()["nodes"]
    editor.load_graph_dict(graph_dict)
    assert [n.id for n in editor.document.nodes] == ["a", "b", "op"]
    assert len(editor.document.edges) == 2


def test_gui_widgets_node_edit_json_round_trip(editor):
    json_str = editor.to_json()
    assert isinstance(json_str, str)
    assert json_str

    editor.clear_graph()
    editor.load_graph_from_json(json_str)
    assert editor.document.edges


def test_gui_widgets_node_edit_file_io(editor, tmp_path):
    path = tmp_path / "graph.json"
    editor.save_graph_to_file(str(path))
    assert path.exists()

    editor.clear_graph()
    editor.load_graph_from_file(str(path))
    assert [n.id for n in editor.document.nodes] == ["a", "b", "op"]


def test_gui_widgets_node_edit_selection_reporting(editor, qtbot):
    """Selecting a node reports it; emptying the selection reports that too.

    The report is produced by the control during its draw pass, so the test
    calls the report directly: an offscreen widget the test never shows gets
    no paint events, and an ``update()`` on an unmapped widget paints nothing.
    """
    with qtbot.waitSignal(editor.nodeSelected, timeout=2000) as selected:
        assert editor.select_node("b", reveal=False) is True
        editor.control._report_selection()
    assert selected.args[0]["id"] == "b"

    editor.control.editor.selected_nodes.clear()
    with qtbot.waitSignal(editor.selectionCleared, timeout=2000):
        editor.control._report_selection()
