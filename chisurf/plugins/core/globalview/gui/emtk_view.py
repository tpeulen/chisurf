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

from chisurf.gui.widgets.node_editor.document import (
    GraphDocument,
    GraphEdge,
    GraphNode,
)
from chisurf.gui.widgets.node_editor.emtk_control import NodeContentRenderer
from chisurf.gui.widgets.node_editor.model import PortSpec

__all__ = [
    "EDGE_COLOURS",
    "apply_network_style",
    "draw_legend",
    "GlobalViewContent",
    "KIND_COLOURS",
    "KIND_TITLE",
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
#: The factor-graph representation's kinds: a dataset's likelihood, a free
#: variable, and a variable two or more likelihoods share -- the one a global
#: fit is global through.
NODE_FACTOR = 5
NODE_VARIABLE = 6
NODE_SHARED = 7

#: How a node of each kind announces itself in its title bar. The glyphs are
#: from the baked atlas -- a character the atlas lacks draws as *nothing* in
#: the application while looking perfect in a screenshot.
KIND_TITLE: dict = {
    NODE_FIT: "fit",
    NODE_GROUP: "group",
    NODE_PARAM_FIXED: "fixed",
    NODE_PARAM_LINKED: "linked",
    NODE_PARAM_FREE: "free",
    NODE_FACTOR: "likelihood",
    NODE_VARIABLE: "variable",
    NODE_SHARED: "shared",
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
    NODE_FACTOR: (66, 165, 245, 255),
    NODE_VARIABLE: (171, 71, 188, 255),
    NODE_SHARED: (255, 193, 7, 255),
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
    # A likelihood reads a variable: the factor graph's own edge, brighter than
    # ownership because it is the structure, not scaffolding.
    "scope": ((150, 158, 170, 220), 1.8, False),
    # A held parameter a likelihood reads: evidence, not a variable.
    "evidence": ((110, 116, 124, 120), 1.0, False),
}

#: Disc radius per kind. Owners are larger because they are the things you
#: navigate by; a network is read outward from its fits.
KIND_RADIUS: dict = {
    NODE_FIT: 15.0,
    NODE_GROUP: 15.0,
    NODE_PARAM_FIXED: 10.0,
    NODE_PARAM_LINKED: 11.0,
    NODE_PARAM_FREE: 11.0,
    NODE_FACTOR: 13.0,
    NODE_VARIABLE: 11.0,
    NODE_SHARED: 12.0,
}

#: What the legend calls each kind.
KIND_LABELS: dict = {
    NODE_FIT: "fit",
    NODE_GROUP: "group",
    NODE_PARAM_FREE: "free parameter",
    NODE_PARAM_LINKED: "linked parameter",
    NODE_PARAM_FIXED: "fixed parameter",
    NODE_FACTOR: "likelihood (dataset)",
    NODE_VARIABLE: "variable",
    NODE_SHARED: "shared variable",
}

#: Legend order: owners first, then parameters by how much freedom they have.
LEGEND_ORDER: tuple = (
    NODE_FIT,
    NODE_GROUP,
    NODE_FACTOR,
    NODE_SHARED,
    NODE_VARIABLE,
    NODE_PARAM_FREE,
    NODE_PARAM_LINKED,
    NODE_PARAM_FIXED,
)

#: Kinds that are not parameters: nothing links to them or from them.
NOT_LINKABLE = frozenset({NODE_FIT, NODE_GROUP, NODE_FACTOR})

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
    present = [
        k for k in LEGEND_ORDER if any(int(n.config.get("kind", -1)) == k for n in document.nodes)
    ]
    if not present:
        return

    draw = im.get_window_draw_list()
    row = draw.calc_text_size("X")[1] + 3.0
    width = max(draw.calc_text_size(KIND_LABELS[k])[0] for k in present) + 34.0
    x, y = box[0] + 8.0, box[1] + 8.0
    draw.add_rect_filled((x, y), (x + width, y + row * len(present) + 8.0), (18, 20, 24, 205), 4.0)
    draw.add_rect((x, y), (x + width, y + row * len(present) + 8.0), (70, 76, 86, 180), 4.0)
    for index, kind in enumerate(present):
        centre_y = y + 4.0 + row * index + row * 0.5
        if kind == NODE_FACTOR:
            draw.add_rect_filled(
                (x + 9.0, centre_y - 5.0), (x + 19.0, centre_y + 5.0), KIND_COLOURS[kind], 2.0
            )
        else:
            draw.add_circle_filled((x + 14.0, centre_y), 5.0, KIND_COLOURS[kind])
        draw.add_text(
            (x + 24.0, centre_y - row * 0.5 + 1.0), (216, 220, 228, 255), KIND_LABELS[kind]
        )


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
        return (
            int(source.config.get("kind", -1)) not in NOT_LINKABLE
            and int(target.config.get("kind", -1)) not in NOT_LINKABLE
        )

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
        shape = emtk_nodes.NodeShape.SQUARE if kind == NODE_FACTOR else emtk_nodes.NodeShape.DISC
        return (shape, label, radius)

    def node_style(self, node: GraphNode) -> tuple | None:
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

    def link_style(self, edge: typing.Any) -> tuple | None:
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
