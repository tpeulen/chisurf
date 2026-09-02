"""The node editor as a ``QWidget``, for the places ChiSurf still needs one.

The editor itself is :class:`~.cmtk_control.GraphControl`, which knows nothing
about Qt. This module is the twelve lines that put it in a window: a
:func:`cmtk.qt_host.ControlHost` around the control, plus the Qt signals the
existing consumers connect to.

Keeping the split is the point of the rewrite. The same control is what a
browser host draws and what a headless test drives, so there is one editor
rather than one per surface -- which is exactly what the ``QGraphicsScene``
version could not offer, since every one of its nodes *was* a Qt object.
"""
from __future__ import annotations

import json
import logging
import typing

from qtpy import QtCore, QtWidgets

from cmtk.qt_host import ControlHost

from .cmtk_control import GraphControl, NodeContentRenderer
from .document import GraphDocument

__all__ = ["NodeGraphWidget"]

logger = logging.getLogger(__name__)

#: Point size the editor's text is drawn at. The controls inside a node are
#: monospaced, as cmtk's are throughout.
DEFAULT_FONT_PT: float = 9.0

#: The editor's backdrop. cmtk's node editor paints its own grid over this, so
#: it only shows through where the grid does not reach.
DEFAULT_BACKGROUND: tuple = (30, 32, 38, 255)


class NodeGraphWidget(QtWidgets.QWidget):
    """A node editor in a widget, over one :class:`~.document.GraphDocument`.

    Parameters
    ----------
    parent : QtWidgets.QWidget, optional
        Qt parent.
    read_only : bool
        Refuse edits. Navigation and selection still work.
    content : NodeContentRenderer, optional
        What to draw inside node bodies.
    show_minimap : bool
        Draw the corner minimap.

    Attributes
    ----------
    graphChanged : QtCore.Signal
        Emitted after any edit that changed the graph.
    nodeSelected : QtCore.Signal
        Emitted with the selected node's serialised form.
    edgeSelected : QtCore.Signal
        Emitted with the selected edge's serialised form.
    """

    graphChanged = QtCore.Signal()
    nodeSelected = QtCore.Signal(dict)
    edgeSelected = QtCore.Signal(dict)

    def __init__(
        self,
        parent: typing.Optional[QtWidgets.QWidget] = None,
        *,
        read_only: bool = False,
        content: typing.Optional[NodeContentRenderer] = None,
        show_minimap: bool = True,
    ) -> None:
        super().__init__(parent)
        self.control = GraphControl(
            GraphDocument(),
            read_only=read_only,
            content=content,
            on_change=self._on_control_changed,
            on_select=self._on_control_selected,
        )
        self.control.show_minimap = bool(show_minimap)

        self.host = ControlHost(
            self.control,
            font_pt=DEFAULT_FONT_PT,
            background=DEFAULT_BACKGROUND,
            parent=self,
        )
        # Focus so the editor can receive Delete and the fit shortcut; without
        # it the keys go to whatever had focus last and the editor looks
        # unresponsive to the keyboard.
        self.host.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.host.setMouseTracking(True)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.host)

    # -- what the consumers call ----------------------------------------

    @property
    def document(self) -> GraphDocument:
        """The graph currently loaded.

        Returns
        -------
        GraphDocument
        """
        return self.control.document

    def load_graph_dict(self, data: dict) -> None:
        """Replace the graph from schema v1.

        Parameters
        ----------
        data : dict
            A graph as ``json_schema.md`` describes it.
        """
        self.control.set_document(GraphDocument.from_dict(data or {}))
        self.host.update()

    def load_graph_from_json(self, text: str) -> None:
        """Replace the graph from a JSON string.

        Parameters
        ----------
        text : str
            JSON in schema v1.
        """
        self.load_graph_dict(json.loads(text))

    def load_graph_from_file(self, path) -> None:
        """Replace the graph from a JSON file.

        Parameters
        ----------
        path : str or pathlib.Path
            The file to read.
        """
        with open(path, "r", encoding="utf-8") as handle:
            self.load_graph_from_json(handle.read())

    def graph_dict(self) -> dict:
        """Serialise the graph.

        Returns
        -------
        dict
            Schema v1.
        """
        return self.control.document.to_dict()

    def to_json(self) -> str:
        """Serialise the graph to a JSON string.

        Returns
        -------
        str
        """
        return self.control.document.to_json()

    def save_graph_to_file(self, path) -> None:
        """Write the graph to a JSON file.

        Parameters
        ----------
        path : str or pathlib.Path
            The file to write.
        """
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(self.to_json())

    def clear_graph(self) -> None:
        """Empty the graph."""
        self.control.set_document(GraphDocument(), fit=False)
        self.host.update()

    def fit_graph(self) -> None:
        """Frame the whole graph.

        Notes
        -----
        Takes effect on the next repaint, not on this call: fitting needs the
        measured size of every node, and a node has no size until it has been
        drawn. Calling this before the first paint and expecting it to have
        happened is what renders a graph as a speck in the middle of the view.
        """
        self.control.fit()
        self.host.update()

    def set_read_only(self, read_only: bool) -> None:
        """Allow or refuse edits.

        Parameters
        ----------
        read_only : bool
            ``True`` to refuse them.
        """
        self.control.read_only = bool(read_only)
        self.control._sync_positions()
        self.host.update()

    def selected_node(self) -> dict:
        """The selected node's serialised form.

        Returns
        -------
        dict
            Empty when nothing is selected.
        """
        from cmtk import nodes

        chosen = nodes.get_selected_nodes(self.control.editor)
        if not chosen:
            return {}
        node = self.control.document.node_for_number(chosen[0])
        return self.control._node_payload(node) if node is not None else {}

    def selected_edge(self) -> dict:
        """The selected edge's serialised form.

        Returns
        -------
        dict
            Empty when nothing is selected.
        """
        from cmtk import nodes

        chosen = nodes.get_selected_links(self.control.editor)
        if not chosen:
            return {}
        edge = self.control.document.edge_for_link(chosen[0])
        return self.control._edge_payload(edge) if edge is not None else {}

    # -- bridges from the control ---------------------------------------

    def _on_control_changed(self) -> None:
        """Repaint and tell the host the graph moved."""
        self.host.update()
        self.graphChanged.emit()

    def _on_control_selected(self, kind: str, payload: dict) -> None:
        """Re-emit a selection as the Qt signal consumers connect to.

        Parameters
        ----------
        kind : str
            ``"node"`` or ``"edge"``.
        payload : dict
            The selected object's serialised form.
        """
        if kind == "node":
            self.nodeSelected.emit(payload)
        elif kind == "edge":
            self.edgeSelected.emit(payload)
