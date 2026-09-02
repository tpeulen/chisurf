"""The parameter network, as a cmtk node graph.

This replaces ``graph_canvas.py``'s ``ParameterGraphCanvas`` -- a hand-painted
``QWidget`` that drew its own discs, arrows, hit tests and drag handling. The
graph it draws is the same one: the fits and out-of-fit groups being analysed,
every parameter they own, and the links between parameters that make a global
fit global.

Why a node editor rather than a diagram
---------------------------------------
The old canvas drew *marks*: a disc per node, a curve per edge, and a hand-rolled
hit test to find out which one the pointer was on. That is a node editor with
the parts that make one usable left out -- no pan, no zoom, no box select, no
sticking, and a link made by dragging one disc onto another with no pin to aim
at. Expressing the graph in :mod:`cmtk.nodes` gets all of that, and the
per-node body gets somewhere to put a parameter's actual value.

The three kinds of edge, which are three different claims
---------------------------------------------------------
This is the part that must survive the port, because drawing them alike is not
a cosmetic loss -- it is a claim the picture makes that the model does not:

``ownership``
    parameter to its fit or group. Scaffolding: thin and grey.
``link``
    follower to master. The relation the user came here to see and to edit, so
    it is the bright one.
``base``
    owner to owner, the *Connect base* option. Dim, because it says only
    "these are the things links can run between".

:func:`cmtk.nodes.link` takes a per-link colour for exactly this.
"""
from __future__ import annotations

import logging
import typing

from cmtk import im

from chisurf.gui.widgets.node_editor.cmtk_control import NodeContentRenderer
from chisurf.gui.widgets.node_editor.document import (
    GraphDocument,
    GraphEdge,
    GraphNode,
)
from chisurf.gui.widgets.node_editor.model import PortSpec

__all__ = [
    "EDGE_COLOURS",
    "GlobalViewContent",
    "KIND_COLOURS",
    "KIND_TITLE",
    "graph_result_to_document",
]

logger = logging.getLogger(__name__)

#: Node kind codes as the adapter produces them, kept identical so the two
#: implementations read the same data and a screenshot of one can be compared
#: with the other.
NODE_FIT = 0
NODE_PARAM_FIXED = 1
NODE_PARAM_LINKED = 2
NODE_PARAM_FREE = 3
NODE_GROUP = 4

#: How a node of each kind announces itself in its title bar. The glyphs are
#: from the baked atlas -- a character the atlas lacks draws as *nothing* in
#: the application while looking perfect in a screenshot.
KIND_TITLE: dict = {
    NODE_FIT: "fit",
    NODE_GROUP: "group",
    NODE_PARAM_FIXED: "fixed",
    NODE_PARAM_LINKED: "linked",
    NODE_PARAM_FREE: "free",
}

#: Title-bar colour per kind, matching ``graph_canvas.KIND_COLOURS`` so the two
#: graphs in ChiSurf keep reading as one idea.
KIND_COLOURS: dict = {
    NODE_FIT: (41, 98, 173, 255),
    NODE_GROUP: (180, 95, 6, 255),
    NODE_PARAM_FIXED: (96, 108, 116, 255),
    NODE_PARAM_LINKED: (46, 125, 74, 255),
    NODE_PARAM_FREE: (108, 60, 140, 255),
}

#: The three edge kinds, as ``(colour, thickness)``.
EDGE_COLOURS: dict = {
    "ownership": ((120, 126, 134, 150), 1.5),
    "link": ((90, 180, 250, 255), 3.0),
    "base": ((90, 96, 104, 110), 1.0),
}

#: Pin names. Every node carries exactly one of each, because a link here joins
#: two *nodes* rather than two of a node's several outputs -- a parameter has
#: one identity, not a set of ports.
PORT_IN = "in"
PORT_OUT = "out"


def _node_kind(entry: typing.Any) -> int:
    """Classify one graph node the way the adapter's colour map does.

    Parameters
    ----------
    entry : object
        A ``GraphNode`` from :mod:`~chisurf.plugins.core.globalview.api.graph`.

    Returns
    -------
    int
        One of the ``NODE_*`` codes.
    """
    if entry.node_type == "fit":
        return NODE_FIT
    if entry.node_type == "group":
        return NODE_GROUP
    if entry.fixed:
        return NODE_PARAM_FIXED
    if entry.is_linked:
        return NODE_PARAM_LINKED
    return NODE_PARAM_FREE


def graph_result_to_document(
    result: typing.Any,
    positions: typing.Optional[dict] = None,
    include_fixed: bool = True,
) -> GraphDocument:
    """Turn the RPC's graph into a document the node editor can draw.

    Parameters
    ----------
    result : object
        A ``GraphResult`` -- nodes with ``node_idx``/``node_type``/``name`` and
        edges of source and target indices.
    positions : dict, optional
        ``node_idx -> (x, y)`` from
        :func:`~chisurf.plugins.core.globalview.gui.adapter.compute_layout`.
        Nodes with no entry are stacked in a column rather than piled at the
        origin, so a missing layout is visible as a column instead of as one
        node with everything hidden behind it.
    include_fixed : bool
        Keep parameters that are held rather than estimated. Turning them off
        is how a large global fit is made readable.

    Returns
    -------
    GraphDocument
        Ready for :class:`~chisurf.gui.widgets.node_editor.cmtk_control.GraphControl`.

    Notes
    -----
    Node ids are the adapter's ``node_idx`` as a string, so a selection made in
    the graph resolves back to the fit or parameter it names without a second
    mapping to keep in step.

    The edge *kinds* are recovered here rather than carried by the RPC, which
    reports only source and target. An edge between a parameter and its owner
    is ownership; between two parameters it is a link; between two owners it is
    a base edge. That is a rule about what the endpoints *are*, so it cannot
    disagree with the graph the way a separately-transmitted label could.
    """
    document = GraphDocument()
    kinds: dict = {}
    kept: set = set()

    for index, entry in enumerate(result.nodes):
        kind = _node_kind(entry)
        if kind == NODE_PARAM_FIXED and not include_fixed:
            continue
        kinds[entry.node_idx] = kind
        kept.add(entry.node_idx)

        position = (positions or {}).get(entry.node_idx)
        if position is None:
            position = (0.0, float(len(kept)) * 90.0)

        node = GraphNode(
            node_id=str(entry.node_idx),
            node_type=entry.node_type,
            title=str(entry.name),
            inputs=[PortSpec(name=PORT_IN, is_output=False, port_type="param")],
            outputs=[PortSpec(name=PORT_OUT, is_output=True, port_type="param")],
            config={
                "kind": kind,
                "value": entry.value,
                "fixed": bool(entry.fixed),
                "is_linked": bool(entry.is_linked),
                "link_name": entry.link_name,
                "fit_name": entry.fit_name,
                "param_uid": entry.param_uid,
                "owner_uid": entry.owner_uid,
            },
            pos=(float(position[0]), float(position[1])),
        )
        document.add_node(node)

    owners = {NODE_FIT, NODE_GROUP}
    for edge in result.edges:
        if edge.source not in kept or edge.target not in kept:
            # An edge to a parameter that was filtered out. Dropped rather than
            # drawn to nowhere -- "hide fixed parameters" must hide their edges
            # too, or the graph keeps lines running off to nothing.
            continue
        source_kind, target_kind = kinds[edge.source], kinds[edge.target]
        if source_kind in owners and target_kind in owners:
            kind = "base"
        elif source_kind in owners or target_kind in owners:
            kind = "ownership"
        else:
            kind = "link"
        document.add_edge(GraphEdge(
            source=str(edge.source), source_port=0,
            target=str(edge.target), target_port=0,
            config={"kind": kind},
        ))
    return document


class GlobalViewContent(NodeContentRenderer):
    """Node bodies for the parameter network: what the parameter currently is.

    Attributes
    ----------
    show_values : bool
        Draw each parameter's value in its body. Off makes the graph a pure
        topology picture, which is what a network of two hundred parameters
        wants.
    """

    def __init__(self, show_values: bool = True) -> None:
        self.show_values = bool(show_values)

    def draw_body(self, node: GraphNode, read_only: bool) -> bool:
        """Draw one node's body.

        Parameters
        ----------
        node : GraphNode
            The fit, group or parameter.
        read_only : bool
            Draw but do not accept. The network is a *view* of live fits, so
            this is normally ``True``: the value shown is owned by the fitting
            model, and editing it here without going through the model's own
            setter would be a second path into state that has one.

        Returns
        -------
        bool
            ``True`` when the user changed something.
        """
        kind = int(node.config.get("kind", NODE_PARAM_FREE))
        im.text(KIND_TITLE.get(kind, "node"))

        if kind in (NODE_FIT, NODE_GROUP):
            fit_name = node.config.get("fit_name")
            if fit_name:
                im.text(str(fit_name))
            return False

        if self.show_values:
            value = node.config.get("value")
            im.text(f"= {value:.6g}" if isinstance(value, (int, float)) else "= -")
        if node.config.get("is_linked") and node.config.get("link_name"):
            # Named as well as drawn: the arrow says *that* it follows
            # something, and at any useful zoom it does not say what.
            im.text(f"-> {node.config['link_name']}")
        return False


    def port_label(self, node: GraphNode, port: typing.Any, is_output: bool) -> str:
        """No label: every node here has the same one input and one output.

        Parameters
        ----------
        node : GraphNode
            The node.
        port : PortSpec
            The port.
        is_output : bool
            Which side it is on.

        Returns
        -------
        str
            Always empty. A parameter has one identity, not a set of ports, so
            the pins exist only to give a link somewhere to land -- and
            "in [param]" written on every node twice is two rows per node
            saying what the arrow already says.
        """
        return ""

    def node_style(self, node: GraphNode) -> typing.Optional[tuple]:
        """Colour the title bar by what kind of node this is.

        Parameters
        ----------
        node : GraphNode
            The node about to be drawn.

        Returns
        -------
        tuple or None
            ``(r, g, b, a)``.
        """
        return KIND_COLOURS.get(int(node.config.get("kind", -1)))

    def link_style(self, edge: typing.Any) -> typing.Optional[tuple]:
        """Colour an edge by which of the three claims it makes.

        Parameters
        ----------
        edge : GraphEdge
            The edge about to be drawn.

        Returns
        -------
        tuple or None
            ``(colour, thickness)``.
        """
        return EDGE_COLOURS.get(str(edge.config.get("kind", "ownership")))
