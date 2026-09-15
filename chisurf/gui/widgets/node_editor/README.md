# Node editor

The graph editor ChiSurf shows graphs with — the lightpath simulator's optical
path, MMFDB's provenance DAG, the AutoForm `node_graph` section, and the
standalone demo. One editor for all four, drawn by
[cmtk](https://github.com/tpeulen/cmtk) rather than a `QGraphicsScene`.

## Architecture

Three layers, only the last of which knows Qt exists:

- **Document** — `document.py`. The graph as a plain object: `GraphNode`,
  `GraphEdge`, `GraphDocument`, with `from_dict`/`to_dict` for the schema v1
  JSON in `json_schema.md`. An edge's `source_port` indexes the source node's
  `outputs`, its `target_port` the target's `inputs` — per direction, not one
  flat list.
- **Control** — `cmtk_control.py`. `GraphControl` draws the document through
  `cmtk.nodes` and turns pointer/keyboard events into edits. Read-only mode
  refuses edits but keeps navigation and selection. `NodeContentRenderer`
  draws what goes *inside* a node body (plots, choosers, tables).
- **Widget** — `widget.py`. `NodeGraphWidget` puts the control in a window via
  `cmtk.qt_host.ControlHost` and re-emits its callbacks as Qt signals
  (`graphChanged`, `nodeSelected`, `edgeSelected`, `nodeActivated`,
  `selectionCleared`). This is the class consumers instantiate.

Supporting modules: `model.py`/`registry.py`/`validation.py` (Qt-free), and
`widgets/widget_palette.py` (the one Qt widget a host may want beside the
canvas — the lightpath tool hosts it).

## Usage

```python
from chisurf.gui.widgets.node_editor import NodeGraphWidget

editor = NodeGraphWidget(read_only=False)
editor.load_graph_dict(graph_dict)   # schema v1, see json_schema.md
editor.nodeSelected.connect(lambda node: print(node["id"]))
```

Standalone demo: `python -m chisurf.gui.widgets.node_editor`.

## Testing

```bash
pytest chisurf/gui/widgets/node_editor/tests/ test/test_node_editor_cmtk.py
```

The document and control need no display, which is the point of the cmtk
split: the editor's behaviour is testable headlessly.
