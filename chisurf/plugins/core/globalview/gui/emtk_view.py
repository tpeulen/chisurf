"""The parameter network, as a emtk node graph.

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
at. Expressing the graph in :mod:`emtk.nodes` gets all of that, and the
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

:func:`emtk.nodes.link` takes a per-link colour for exactly this.
"""
from __future__ import annotations

import logging
import typing

from emtk import im
from emtk import nodes as emtk_nodes

from chisurf.gui.widgets.node_editor.emtk_control import NodeContentRenderer
from chisurf.gui.widgets.node_editor.document import (
    GraphDocument,
    GraphEdge,
    GraphNode,
)
from chisurf.gui.widgets.node_editor.model import PortSpec

__all__ = [
    "EDGE_COLOURS",
    "apply_network_style",
    "draw_legend",
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
#:
#: These are the *light* stop of each of the old canvas' gradients, because
#: :func:`emtk.nodes` shades a disc around the colour it is given rather than
#: between two stops -- handing it the dark stop would produce a disc darker
#: than the one it replaces.
KIND_COLOURS: dict = {
    NODE_FIT: (66, 165, 245, 255),
    NODE_GROUP: (255, 152, 0, 255),
    NODE_PARAM_FIXED: (144, 164, 174, 255),
    NODE_PARAM_LINKED: (102, 187, 106, 255),
    NODE_PARAM_FREE: (171, 71, 188, 255),
}

#: The three edge kinds, as ``(colour, thickness, arrowhead)``.
#:
#: Only the link gets a head, and that is the point: in a parameter network
#: the *direction* of a link is the information -- which parameter follows
#: which -- while ownership and base edges are symmetric statements about
#: membership. A head on all three says something untrue about two of them.
EDGE_COLOURS: dict = {
    "ownership": ((120, 126, 134, 160), 1.4, False),
    "link": ((0, 200, 235, 255), 2.6, True),
    "base": ((86, 92, 100, 110), 1.0, False),
}

#: Disc radius per kind. Owners are larger because they are the things you
#: navigate by; a network is read outward from its fits.
KIND_RADIUS: dict = {
    NODE_FIT: 15.0,
    NODE_GROUP: 15.0,
    NODE_PARAM_FIXED: 10.0,
    NODE_PARAM_LINKED: 11.0,
    NODE_PARAM_FREE: 11.0,
}

#: What the legend calls each kind.
KIND_LABELS: dict = {
    NODE_FIT: "fit",
    NODE_GROUP: "group",
    NODE_PARAM_FREE: "free parameter",
    NODE_PARAM_LINKED: "linked parameter",
    NODE_PARAM_FIXED: "fixed parameter",
}

#: Legend order: owners first, then parameters by how much freedom they have.
LEGEND_ORDER: tuple = (NODE_FIT, NODE_GROUP, NODE_PARAM_FREE,
                       NODE_PARAM_LINKED, NODE_PARAM_FIXED)

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
        Ready for :class:`~chisurf.gui.widgets.node_editor.emtk_control.GraphControl`.

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


def apply_network_style(editor: typing.Any) -> None:
    """Make the editor look like a diagram rather than like a dataflow graph.

    Parameters
    ----------
    editor : emtk.nodes.EditorContext
        The editor to restyle, in place.

    Notes
    -----
    Three changes, and each is about what this graph *is*:

    * **Rim-to-rim arcs.** The node editor's curve leaves a pin rightwards and
      arrives leftwards, which reads well when a graph flows left to right. A
      network laid out by Kamada-Kawai has nodes wherever the algorithm put
      them, so a node directly above another is joined by a curve that goes out
      sideways, turns around and comes back. An arc runs along the line joining
      the two centres, stops at each rim, and bows slightly -- which separates
      edges that would otherwise be drawn on top of each other and gives the
      eye something to follow between two distant marks.
    * **A quieter grid.** The grid is a background here, not a workspace to
      align things on; at the editor's default weight it competes with the
      thin ownership edges, which are the same width and nearly the same
      colour.
    * **No node outline.** Discs draw their own rim.
    """
    style = editor.style
    style.link_routing = emtk_nodes.LinkRouting.ARC
    style.flags &= ~emtk_nodes.StyleFlags.NODE_OUTLINE
    style.colors[emtk_nodes.Col.GRID_LINE] = (255, 255, 255, 14)
    style.colors[emtk_nodes.Col.GRID_LINE_PRIMARY] = (255, 255, 255, 24)
    style.colors[emtk_nodes.Col.GRID_BACKGROUND] = (24, 26, 31, 255)
    # A disc is its own connector, so the pointer must be able to catch it
    # anywhere on the mark rather than on a dot that is not drawn.
    style.pin_hover_radius = 14.0


def draw_legend(document: GraphDocument, box: tuple) -> None:
    """Draw the colour key, in the editor's top-left corner.

    Parameters
    ----------
    document : GraphDocument
        The graph, so the key lists only the kinds actually on screen.
    box : tuple
        The editor's screen-space rect, ``(x, y, w, h)``.

    Notes
    -----
    Only the kinds present. A key with five entries in front of a graph that
    has two of them is a key you have to read past rather than one that
    answers a question, and it takes the corner a node could be in.

    Drawn by the caller *after* ``end_node_editor`` rather than by the editor,
    because it is not part of the graph: it does not pan, it does not zoom, and
    it must not be caught by a box selection.
    """
    present = [k for k in LEGEND_ORDER
               if any(int(n.config.get("kind", -1)) == k for n in document.nodes)]
    if not present:
        return

    draw = im.get_window_draw_list()
    row = draw.calc_text_size("X")[1] + 3.0
    width = max(draw.calc_text_size(KIND_LABELS[k])[0] for k in present) + 34.0
    x, y = box[0] + 8.0, box[1] + 8.0
    draw.add_rect_filled((x, y), (x + width, y + row * len(present) + 8.0),
                         (18, 20, 24, 205), 4.0)
    draw.add_rect((x, y), (x + width, y + row * len(present) + 8.0),
                  (70, 76, 86, 180), 4.0)
    for index, kind in enumerate(present):
        centre_y = y + 4.0 + row * index + row * 0.5
        draw.add_circle_filled((x + 14.0, centre_y), 5.0, KIND_COLOURS[kind])
        draw.add_text((x + 24.0, centre_y - row * 0.5 + 1.0),
                      (216, 220, 228, 255), KIND_LABELS[kind])


class GlobalViewContent(NodeContentRenderer):
    """Marks, not boxes: the parameter network reads as a diagram.

    Every node here is a **disc** with its name under it, which is what the
    canvas this replaces drew and what a network of two hundred parameters
    needs. A titled box per parameter is mostly padding: it spends five rows
    saying what a coloured dot and a label say, and twenty of them fill a
    screen that should hold two hundred.

    The value is not in the node, therefore. It is in the tooltip and in the
    parameter table beside the graph, which is where a number is readable.
    """

    #: Multiplier on every mark's radius, driven by the tool's size slider.
    radius_scale: float = 1.0

    def __init__(self, show_values: bool = False) -> None:
        #: Kept for callers that want the value drawn under the name. Off,
        #: because two lines of label under every disc is what made the boxes
        #: unreadable in the first place.
        self.show_values = bool(show_values)

    def accepts_link(self, source: GraphNode, target: GraphNode) -> bool:
        """Only a parameter may follow a parameter.

        Parameters
        ----------
        source, target : GraphNode
            The two marks the user drew between.

        Returns
        -------
        bool
            ``False`` when either end is a fit or a group. Every mark here
            carries one in and one out pin so a link can land anywhere on it,
            which without this check lets two *fits* be wired together -- an
            edge the parameter model has no meaning for, drawn in a panel whose
            whole job is to show what follows what.
        """
        owners = {NODE_FIT, NODE_GROUP}
        return (int(source.config.get("kind", -1)) not in owners
                and int(target.config.get("kind", -1)) not in owners)

    def node_shape(self, node: GraphNode) -> tuple:
        """Every node is a disc, sized by what kind it is.

        Parameters
        ----------
        node : GraphNode
            The node.

        Returns
        -------
        tuple
            ``(shape, label, radius)``.
        """
        kind = int(node.config.get("kind", NODE_PARAM_FREE))
        label = node.title
        if self.show_values:
            value = node.config.get("value")
            if isinstance(value, (int, float)):
                label = f"{node.title} = {value:.4g}"
        radius = KIND_RADIUS.get(kind, 11.0) * self.radius_scale
        return (emtk_nodes.NodeShape.DISC, label, radius)

    def node_style(self, node: GraphNode) -> typing.Optional[tuple]:
        """Colour the disc by what kind of node this is.

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
            ``(colour, thickness, arrowhead)``.
        """
        return EDGE_COLOURS.get(str(edge.config.get("kind", "ownership")))

    def port_label(self, node: GraphNode, port: typing.Any, is_output: bool) -> str:
        """No label: a disc has no room for one and no need of it.

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
            Always empty. The pins exist to give a link somewhere to land; a
            parameter has one identity, not a set of ports.
        """
        return ""

    def draw_body(self, node: GraphNode, read_only: bool) -> bool:
        """Nothing: a disc has no interior.

        Parameters
        ----------
        node : GraphNode
            The node.
        read_only : bool
            Unused.

        Returns
        -------
        bool
            Always ``False``.
        """
        return False


def document_from_arrays(positions, edges, names, kinds) -> GraphDocument:
    """Build a document from the four parallel arrays the tool already has.

    Parameters
    ----------
    positions : sequence
        ``(x, y)`` per node, in the layout algorithm's units.
    edges : sequence
        ``(source_index, target_index)`` pairs.
    names, kinds : sequence
        Per-node label and ``NODE_*`` code.

    Returns
    -------
    GraphDocument

    Notes
    -----
    The tool computes its own layout and hands over arrays rather than a
    ``GraphResult``, so this is the second door into the same room as
    :func:`graph_result_to_document`. Kept separate rather than made to
    convert: inventing a ``GraphResult`` to throw away would put a third shape
    between the tool and the graph.
    """
    document = GraphDocument()
    for index, name in enumerate(names):
        kind = int(kinds[index]) if index < len(kinds) else NODE_PARAM_FREE
        x, y = positions[index] if index < len(positions) else (0.0, index * 90.0)
        document.add_node(GraphNode(
            node_id=str(index), node_type="parameter", title=str(name),
            inputs=[PortSpec(name=PORT_IN, is_output=False, port_type="param")],
            outputs=[PortSpec(name=PORT_OUT, is_output=True, port_type="param")],
            config={"kind": kind}, pos=(float(x), float(y)),
        ))

    owners = {NODE_FIT, NODE_GROUP}
    for source, target in edges:
        if not (0 <= source < len(names) and 0 <= target < len(names)):
            continue
        source_kind, target_kind = int(kinds[source]), int(kinds[target])
        if source_kind in owners and target_kind in owners:
            kind = "base"
        elif source_kind in owners or target_kind in owners:
            kind = "ownership"
        else:
            kind = "link"
        document.add_edge(GraphEdge(str(source), 0, str(target), 0,
                                    config={"kind": kind}))
    return document
