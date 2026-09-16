"""The parameter network as a widget, with the canvas's own surface.

`ParameterGraphCanvas` is what ``tool.py`` builds, and it is reached through a
small, specific set of members: :meth:`set_graph`, :meth:`refit`,
``node_radius``, ``selected_nodes_idx``, and three signals. This presents
exactly those over the emtk node editor, so the swap in ``tool.py`` is one
import and one constructor rather than a rewrite of a thousand-line window.

Deliberately a *surface*, not a subclass. The canvas is a ``QWidget`` that
paints itself; this is a host around a toolkit-free control, and the only
thing the two have in common is what the tool asks of them.
"""
from __future__ import annotations

import logging
import typing

from qtpy import QtCore, QtWidgets

from emtk import im, nodes
from emtk.qt_host import ControlHost

from chisurf.gui.widgets.node_editor.emtk_control import GraphControl
from chisurf.plugins.core.globalview.gui.emtk_view import (
    GlobalViewContent,
    apply_network_style,
    document_from_arrays,
    draw_legend,
)

__all__ = ["ParameterNetworkWidget"]

logger = logging.getLogger(__name__)

#: The pixel box a layout is fitted into before it becomes a document.
LAYOUT_EXTENT: tuple = (900.0, 620.0)


def _to_pixels(positions, spread: float) -> list:
    """Fit layout coordinates into a pixel box, keeping their aspect ratio.

    Parameters
    ----------
    positions : sequence
        ``(x, y)`` per node, **in the layout algorithm's own units**.
    spread : float
        Multiplier on the fitted extent. Above 1 the graph grows past the box
        and is read by panning, which is how a crowded network is pulled apart
        without recomputing its layout.

    Returns
    -------
    list
        ``(x, y)`` per node, in grid pixels.

    Notes
    -----
    This is the step that was missing, and its absence is not subtle: every
    layout in :mod:`chisurf.core.graph` returns coordinates in roughly
    ``-1..1``, so used raw the whole network occupies two grid units and
    every node is drawn on top of every other. Fit-to-content then computes a
    zoom from a two-unit span, hits its clamp, and leaves a single pile of
    discs in the middle of the panel -- which is exactly what it did.

    The canvas this replaces called ``_fit_to_canvas`` for the same reason.
    Fitting to a *fixed* box rather than to the widget is deliberate: the
    editor has its own fit-to-content and its own zoom, so the box only has to
    put the nodes a sensible distance apart, and a layout that changed shape
    when the panel was resized would move every node under the user.
    """
    points = [(float(x), float(y)) for x, y in positions]
    if not points:
        return []
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    span_x = max(xs) - min(xs)
    span_y = max(ys) - min(ys)
    if span_x < 1e-9 and span_y < 1e-9:
        # One node, or a degenerate layout: spreading it is meaningless and
        # dividing by the span is a crash.
        return [(0.0, index * 90.0) for index, _ in enumerate(points)]

    scale = min(
        LAYOUT_EXTENT[0] / span_x if span_x > 1e-9 else float("inf"),
        LAYOUT_EXTENT[1] / span_y if span_y > 1e-9 else float("inf"),
    ) * max(float(spread), 0.05)
    return [((x - min(xs)) * scale, (y - min(ys)) * scale) for x, y in points]


class ParameterNetworkWidget(QtWidgets.QWidget):
    """The network, drawn by emtk, behind the API ``tool.py`` already calls.

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
            on_link=self._on_link,
            on_unlink=self._on_unlink,
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
            Unused: the emtk editor keeps its pan and zoom across a load
            anyway, and refits only when asked.
        """
        del keep_view
        placed = _to_pixels(positions, spread)
        self.control.set_document(document_from_arrays(placed, edges, names, kinds),
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

    def _on_link(self, source_id: str, target_id: str) -> None:
        """Announce a link the user drew, as the tool's ``(follower, master)``.

        Parameters
        ----------
        source_id, target_id : str
            Document node ids, which here are the array indices as strings.

        Notes
        -----
        The editor reports ``(output, input)``, and an output is the end the
        drag left. In this panel the thing being *followed* is what the arrow
        points away from, so the master is the source and the follower is the
        target -- the same order ``graph_result_to_document`` derives a link
        edge in, and the order the tool's slot expects.

        The signal is all that happens. The link belongs to the fit model, so
        the panel must not add the edge itself: it would draw a relation the
        model has not accepted, and the two would disagree until the next
        refresh.
        """
        if source_id.isdigit() and target_id.isdigit():
            self.linkRequested.emit(int(target_id), int(source_id))

    def _on_unlink(self, source_id: str, target_id: str) -> None:
        """Announce a link the user broke.

        Parameters
        ----------
        source_id, target_id : str
            Document node ids. The follower is the target, as above.
        """
        if target_id.isdigit():
            self.linkRemovalRequested.emit(int(target_id))
