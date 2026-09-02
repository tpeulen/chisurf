"""The parameter network as a widget, with the canvas's own surface.

`ParameterGraphCanvas` is what ``tool.py`` builds, and it is reached through a
small, specific set of members: :meth:`set_graph`, :meth:`refit`,
``node_radius``, ``selected_nodes_idx``, and three signals. This presents
exactly those over the cmtk node editor, so the swap in ``tool.py`` is one
import and one constructor rather than a rewrite of a thousand-line window.

Deliberately a *surface*, not a subclass. The canvas is a ``QWidget`` that
paints itself; this is a host around a toolkit-free control, and the only
thing the two have in common is what the tool asks of them.
"""
from __future__ import annotations

import logging
import typing

from qtpy import QtCore, QtWidgets

from cmtk import im, nodes
from cmtk.qt_host import ControlHost

from chisurf.gui.widgets.node_editor.cmtk_control import GraphControl
from chisurf.plugins.core.globalview.gui.cmtk_view import (
    GlobalViewContent,
    apply_network_style,
    document_from_arrays,
    draw_legend,
)

__all__ = ["ParameterNetworkWidget"]

logger = logging.getLogger(__name__)


class ParameterNetworkWidget(QtWidgets.QWidget):
    """The network, drawn by cmtk, behind the API ``tool.py`` already calls.

    Attributes
    ----------
    selectionChanged : QtCore.Signal
        Node indices currently selected, oldest first.
    linkRequested : QtCore.Signal
        ``(follower, master)`` -- a parameter was dragged onto another.
    linkRemovalRequested : QtCore.Signal
        The follower whose link the user broke.
    node_radius : float
        Kept because the tool writes it from a slider. It scales the marks.
    """

    selectionChanged = QtCore.Signal(list)
    linkRequested = QtCore.Signal(int, int)
    linkRemovalRequested = QtCore.Signal(int)

    def __init__(self, parent: typing.Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._content = GlobalViewContent()
        self.control = GraphControl(
            content=self._content,
            on_select=self._on_select,
        )
        apply_network_style(self.control.editor)
        # Read-only in the sense that node *config* is not edited here; links
        # are still made and broken, which is the whole point of the panel.
        self.control.read_only = False

        self.host = ControlHost(self._Painter(self), font_pt=9.0,
                                background=(24, 26, 31, 255), parent=self)
        self.host.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.host.setMouseTracking(True)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.host)

        self._node_radius = 11.0
        self._selected: list = []

    class _Painter:
        """Draws the control and then the legend, which is not part of the graph.

        Parameters
        ----------
        owner : ParameterNetworkWidget
            The widget whose control and document to draw.

        Notes
        -----
        A thin adapter rather than a method on the widget because the host
        takes an object with the control contract, and the legend has to be
        drawn *after* ``end_node_editor`` -- it must not pan, zoom, or be
        caught by a box selection.
        """

        def __init__(self, owner: "ParameterNetworkWidget") -> None:
            self._owner = owner

        def draw(self, painter, x: float, y: float, w: float, h: float) -> None:
            """Draw the graph and its key."""
            control = self._owner.control
            box = (x, y, w, h)
            control._box = box
            with im.frame(painter, box, io=control.io, storage=control.storage):
                control._draw_graph(box)
                draw_legend(control.document, box)

        def __getattr__(self, name: str):
            """Forward press/drag/release/hover/scroll/key to the control."""
            return getattr(self._owner.control, name)

    # -- the surface tool.py calls --------------------------------------

    @property
    def node_radius(self) -> float:
        """Mark radius, as the tool's slider sets it."""
        return self._node_radius

    @node_radius.setter
    def node_radius(self, value: float) -> None:
        """Scale every mark, keeping the owner/parameter size difference."""
        # Scaled rather than set: the kinds have different radii on purpose --
        # a network is read outward from its fits -- so one absolute value for
        # every mark would flatten that away.
        self._node_radius = float(value)
        self._content.radius_scale = self._node_radius / 11.0
        self.host.update()

    @property
    def selected_nodes_idx(self) -> list:
        """The selected nodes, as indices into the arrays the tool passed."""
        return list(self._selected)

    def set_graph(self, positions, edges, names, kinds, *, spread: float = 1.0,
                  keep_view: bool = True) -> None:
        """Replace the graph.

        Parameters
        ----------
        positions, edges, names, kinds : sequence
            As :class:`ParameterGraphCanvas.set_graph` takes them.
        spread : float
            Multiplier on the layout's extent, so a crowded graph can be
            pulled apart without recomputing it.
        keep_view : bool
            Unused: the cmtk editor keeps its pan and zoom across a load
            anyway, and refits only when asked.
        """
        del keep_view
        scaled = [(float(x) * spread, float(y) * spread) for x, y in positions]
        self.control.set_document(document_from_arrays(scaled, edges, names, kinds),
                                  fit=True)
        self._selected = []
        self.host.update()

    def refit(self) -> None:
        """Frame the whole graph at the next repaint."""
        self.control.fit()
        self.host.update()

    def update_graph(self) -> None:
        """Repaint. The canvas' ``update`` under a name that is not Qt's."""
        self.host.update()

    # -- bridges --------------------------------------------------------

    def _on_select(self, kind: str, payload: dict) -> None:
        """Re-emit a selection as the indices the tool works in.

        Parameters
        ----------
        kind : str
            ``"node"`` or ``"edge"``.
        payload : dict
            The selected object's serialised form.
        """
        if kind != "node":
            return
        chosen = nodes.get_selected_nodes(self.control.editor)
        self._selected = [
            int(node.id)
            for node in (self.control.document.node_for_number(n) for n in chosen)
            if node is not None and node.id.isdigit()
        ]
        self.selectionChanged.emit(list(self._selected))

    def report_link(self, follower: int, master: int) -> None:
        """Announce a link the user drew.

        Parameters
        ----------
        follower, master : int
            Node indices.
        """
        self.linkRequested.emit(int(follower), int(master))
