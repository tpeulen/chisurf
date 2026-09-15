"""A small standalone demo: ``python -m chisurf.gui.widgets.node_editor``."""
import sys

from qtpy import QtWidgets

from .widget import NodeGraphWidget

#: A three-node arithmetic graph, in the schema ``json_schema.md`` describes.
DEMO_GRAPH = {
    "version": 1,
    "meta": {"purpose": "demo"},
    "nodes": [
        {"id": "a", "type": "constant", "title": "Constant A",
         "inputs": [], "outputs": ["Value"],
         "config": {"value": 2.5}, "pos": [-260.0, -80.0], "collapsed": False},
        {"id": "b", "type": "constant", "title": "Constant B",
         "inputs": [], "outputs": ["Value"],
         "config": {"value": 4.0}, "pos": [-260.0, 90.0], "collapsed": False},
        {"id": "op", "type": "binary_op", "title": "A + B",
         "inputs": ["A", "B"], "outputs": ["Result"],
         "config": {}, "pos": [60.0, 0.0], "collapsed": False},
    ],
    "edges": [
        {"source": "a", "source_port": 0, "target": "op", "target_port": 0},
        {"source": "b", "source_port": 0, "target": "op", "target_port": 1},
    ],
}


def main():
    """Show the demo window."""
    app = QtWidgets.QApplication(sys.argv)
    window = NodeGraphWidget()
    window.setWindowTitle("Node editor (cmtk)")
    window.resize(900, 600)
    window.load_graph_dict(DEMO_GRAPH)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
