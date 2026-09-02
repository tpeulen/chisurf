"""The graph a node editor edits, with no toolkit anywhere in it.

The editor used to keep its graph *in* its ``QGraphicsScene``: a node was a
``QGraphicsItem``, an edge was another, and "what is the graph" was answered by
walking the scene. That works until you want the same graph without a scene --
headless, in a test, in a browser, or drawn by :mod:`cmtk.nodes`, which owns no
items at all.

So the graph is a plain object here, and drawing it is somebody else's job. The
serialised form is unchanged: it is still schema v1 from ``json_schema.md``, the
same file every consumer already reads and writes, so a project saved by the Qt
editor loads into this one.

Ids, and why there are two kinds
--------------------------------
A node's id in the schema is a **string** the host chooses (``"sub1"``,
``"operation:op2"``). :mod:`cmtk.nodes` keys everything by **int**, because an
immediate-mode editor looks a node up on every frame and a string key is a
hash per node per frame for no benefit.

:class:`GraphDocument` therefore keeps a stable mapping between the two, and it
is stable across a reload: the number a node gets is derived from its position
in the document, not from a counter that walks. Handing out a fresh number each
frame would reset every node's dragged position on every repaint, and the graph
would look pinned in place with no error anywhere.
"""
from __future__ import annotations

import copy
import json
import logging
import typing

from .model import NodeModel, PortSpec

__all__ = ["GraphDocument", "GraphEdge", "GraphNode"]

logger = logging.getLogger(__name__)

#: The schema version this module reads and writes. Bumping it is a change to
#: ``json_schema.md`` and to every consumer, so it lives in one place.
SCHEMA_VERSION: int = 1


class GraphNode:
    """One node: what it is, what it is called, and where it sits.

    Parameters
    ----------
    node_id : str
        Unique within the document. The schema's ``id``.
    node_type : str
        The registry type id, e.g. ``"binary_op"``.
    title : str
        What the title bar reads.
    inputs, outputs : list of PortSpec
        Its ports, in draw order.
    config : dict
        Free-form, JSON-serialisable node configuration.
    pos : tuple
        ``(x, y)`` in grid space.
    collapsed : bool
        Whether the body is hidden, leaving only the title bar.
    """

    def __init__(
        self,
        node_id: str,
        node_type: str = "generic",
        title: str = "",
        inputs: typing.Optional[list] = None,
        outputs: typing.Optional[list] = None,
        config: typing.Optional[dict] = None,
        pos: tuple = (0.0, 0.0),
        collapsed: bool = False,
    ) -> None:
        self.id = str(node_id)
        self.type = str(node_type)
        self.title = str(title or node_id)
        self.inputs: list = list(inputs or [])
        self.outputs: list = list(outputs or [])
        self.config: dict = dict(config or {})
        self.pos: tuple = (float(pos[0]), float(pos[1]))
        self.collapsed = bool(collapsed)

    def port(self, index: int, is_output: bool) -> typing.Optional[PortSpec]:
        """Look a port up by index and direction.

        Parameters
        ----------
        index : int
            Position in the input or output list.
        is_output : bool
            Which list to look in.

        Returns
        -------
        PortSpec or None
            ``None`` when the index is out of range, which is what a graph
            referring to a port a node no longer has produces.
        """
        ports = self.outputs if is_output else self.inputs
        return ports[index] if 0 <= index < len(ports) else None

    def to_model(self) -> NodeModel:
        """Express this node as the :class:`~.model.NodeModel` consumers expect.

        Returns
        -------
        NodeModel
            A model carrying the same title, ports, type and config.
        """
        model = NodeModel(
            title=self.title,
            inputs=list(self.inputs),
            outputs=list(self.outputs),
            node_type=self.type,
            config=dict(self.config),
        )
        model.id = self.id
        return model


class GraphEdge:
    """One directed edge, from an output port to an input port.

    Parameters
    ----------
    source : str
        Id of the node the edge leaves.
    source_port : int
        Index into that node's ``outputs``.
    target : str
        Id of the node it arrives at.
    target_port : int
        Index into that node's ``inputs``.
    config : dict
        Free-form edge configuration; the provenance view puts a colour here.
    """

    def __init__(
        self,
        source: str,
        source_port: int,
        target: str,
        target_port: int,
        config: typing.Optional[dict] = None,
    ) -> None:
        self.source = str(source)
        self.source_port = int(source_port)
        self.target = str(target)
        self.target_port = int(target_port)
        self.config: dict = dict(config or {})

    def key(self) -> tuple:
        """A hashable identity for this edge.

        Returns
        -------
        tuple
            ``(source, source_port, target, target_port)`` -- the four things
            that make an edge the same edge. Deliberately not including
            ``config``: two edges between the same ports are one edge whatever
            metadata is hung off them.
        """
        return (self.source, self.source_port, self.target, self.target_port)


class GraphDocument:
    """A graph, its serialisation, and the int ids the renderer needs.

    Attributes
    ----------
    nodes : list of GraphNode
        In insertion order, which is also draw order and therefore stacking
        order.
    edges : list of GraphEdge
        In insertion order.
    meta : dict
        The schema's free-form ``meta`` block, carried through untouched.
    """

    def __init__(self) -> None:
        self.nodes: list = []
        self.edges: list = []
        self.meta: dict = {}

    # -- lookup ---------------------------------------------------------

    def node(self, node_id: str) -> typing.Optional[GraphNode]:
        """Find a node by its string id.

        Parameters
        ----------
        node_id : str
            The id to look for.

        Returns
        -------
        GraphNode or None
        """
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def index_of(self, node_id: str) -> int:
        """Find a node's position in :attr:`nodes`.

        Parameters
        ----------
        node_id : str
            The id to look for.

        Returns
        -------
        int
            The index, or ``-1``.
        """
        for index, node in enumerate(self.nodes):
            if node.id == node_id:
                return index
        return -1

    # -- integer ids for the renderer -----------------------------------
    #
    # cmtk.nodes keys nodes, pins and links by int. The three ranges must not
    # collide with each other *within their own kind*, and a pin's number has
    # to be recoverable back to (node, port index, direction) because that is
    # what a link the user drew reports.

    #: How many pin ids one node reserves. A node with more ports than this
    #: would have its pins collide with the next node's, so the number is
    #: checked rather than assumed -- see :meth:`pin_id`.
    PINS_PER_NODE: int = 512

    def node_number(self, node_id: str) -> int:
        """The int id :mod:`cmtk.nodes` uses for a node.

        Parameters
        ----------
        node_id : str
            The node's string id.

        Returns
        -------
        int
            Its index plus one, so no node is ever numbered zero -- a falsy id
            reads as "no node" at half the call sites that handle one.
        """
        return self.index_of(node_id) + 1

    def node_for_number(self, number: int) -> typing.Optional[GraphNode]:
        """Recover the node a renderer id refers to.

        Parameters
        ----------
        number : int
            As returned by :meth:`node_number`.

        Returns
        -------
        GraphNode or None
        """
        index = int(number) - 1
        return self.nodes[index] if 0 <= index < len(self.nodes) else None

    def pin_id(self, node_id: str, port_index: int, is_output: bool) -> int:
        """The int id for one port of one node.

        Parameters
        ----------
        node_id : str
            The owning node.
        port_index : int
            Position in that node's input or output list.
        is_output : bool
            Which list.

        Returns
        -------
        int
            A number unique across the document, and decodable by
            :meth:`port_for_pin`.

        Raises
        ------
        ValueError
            When the node has more ports than :attr:`PINS_PER_NODE` leaves room
            for. Silently wrapping would give two different ports the same id,
            and the symptom -- a link that appears on the wrong node -- points
            nowhere near here.
        """
        if not 0 <= port_index < self.PINS_PER_NODE // 2:
            raise ValueError(
                f"port index {port_index} exceeds PINS_PER_NODE//2 = "
                f"{self.PINS_PER_NODE // 2}; raise PINS_PER_NODE"
            )
        base = self.node_number(node_id) * self.PINS_PER_NODE
        return base + port_index * 2 + (1 if is_output else 0)

    def port_for_pin(self, pin: int) -> typing.Optional[tuple]:
        """Decode a pin id back to the port it names.

        Parameters
        ----------
        pin : int
            As returned by :meth:`pin_id`.

        Returns
        -------
        tuple or None
            ``(GraphNode, port_index, is_output)``, or ``None`` when the id
            names a node that is not in the document.
        """
        node = self.node_for_number(int(pin) // self.PINS_PER_NODE)
        if node is None:
            return None
        offset = int(pin) % self.PINS_PER_NODE
        return (node, offset // 2, bool(offset % 2))

    def link_id(self, edge_index: int) -> int:
        """The int id for an edge.

        Parameters
        ----------
        edge_index : int
            Position in :attr:`edges`.

        Returns
        -------
        int
            The index plus one, for the same reason node numbers start at one.
        """
        return int(edge_index) + 1

    def edge_for_link(self, link: int) -> typing.Optional[GraphEdge]:
        """Recover the edge a link id refers to.

        Parameters
        ----------
        link : int
            As returned by :meth:`link_id`.

        Returns
        -------
        GraphEdge or None
        """
        index = int(link) - 1
        return self.edges[index] if 0 <= index < len(self.edges) else None

    # -- editing --------------------------------------------------------

    def add_node(self, node: GraphNode) -> GraphNode:
        """Append a node, renaming it if its id is taken.

        Parameters
        ----------
        node : GraphNode
            The node to add. Its ``id`` is changed in place if it collides.

        Returns
        -------
        GraphNode
            The node, for chaining.
        """
        if self.node(node.id) is not None:
            stem, suffix = node.id, 2
            while self.node(f"{stem}_{suffix}") is not None:
                suffix += 1
            node.id = f"{stem}_{suffix}"
        self.nodes.append(node)
        return node

    def remove_node(self, node_id: str) -> None:
        """Delete a node and every edge touching it.

        Parameters
        ----------
        node_id : str
            The node to remove. Unknown ids are ignored.

        Notes
        -----
        The edges go too. Leaving them turns them into edges naming a node that
        is not there, which the renderer draws as nothing -- so the graph looks
        right and evaluates wrong.
        """
        self.nodes = [n for n in self.nodes if n.id != node_id]
        self.edges = [
            e for e in self.edges if e.source != node_id and e.target != node_id
        ]

    def add_edge(self, edge: GraphEdge) -> bool:
        """Add an edge unless it is a duplicate or names a missing endpoint.

        Parameters
        ----------
        edge : GraphEdge
            The edge to add.

        Returns
        -------
        bool
            ``True`` when it was added.
        """
        if self.node(edge.source) is None or self.node(edge.target) is None:
            return False
        if any(existing.key() == edge.key() for existing in self.edges):
            return False
        self.edges.append(edge)
        return True

    def remove_edge(self, edge: GraphEdge) -> None:
        """Delete one edge, matched by :meth:`GraphEdge.key`.

        Parameters
        ----------
        edge : GraphEdge
            The edge to remove.
        """
        key = edge.key()
        self.edges = [e for e in self.edges if e.key() != key]

    def clear(self) -> None:
        """Empty the document."""
        self.nodes = []
        self.edges = []
        self.meta = {}

    # -- serialisation --------------------------------------------------

    @staticmethod
    def _port_from_entry(entry, is_output: bool) -> typing.Optional[PortSpec]:
        """Read one port, in either of the two spellings the schema allows.

        Parameters
        ----------
        entry : str or dict
            A bare name, or an object with ``name`` and optional type fields.
        is_output : bool
            Which direction the port faces. Taken from the list the entry came
            out of rather than from the entry, because the entry's own
            ``is_output`` is optional and half the graphs in the tree omit it.

        Returns
        -------
        PortSpec or None
            ``None`` for an entry with no usable name.
        """
        if isinstance(entry, str):
            return PortSpec(name=entry, is_output=is_output)
        if not isinstance(entry, dict):
            return None
        name = entry.get("name")
        if not name:
            return None
        return PortSpec(
            name=str(name),
            is_output=is_output,
            port_type=str(entry.get("type", entry.get("port_type", "")) or ""),
            fixed=bool(entry.get("fixed", False)),
            min_value=entry.get("min_value"),
            max_value=entry.get("max_value"),
        )

    @staticmethod
    def _port_to_entry(port: PortSpec):
        """Write one port back, as a bare name when it carries nothing else.

        Parameters
        ----------
        port : PortSpec
            The port to serialise.

        Returns
        -------
        str or dict
            A string when the port is untyped and unconstrained, so a simple
            graph round-trips to the simple spelling it was written in.
        """
        if not port.port_type and not port.fixed \
                and port.min_value is None and port.max_value is None:
            return port.name
        entry: dict = {"name": port.name, "is_output": port.is_output}
        if port.port_type:
            entry["type"] = port.port_type
        if port.fixed:
            entry["fixed"] = True
        if port.min_value is not None:
            entry["min_value"] = port.min_value
        if port.max_value is not None:
            entry["max_value"] = port.max_value
        return entry

    @classmethod
    def from_dict(cls, data: dict) -> "GraphDocument":
        """Build a document from schema v1.

        Parameters
        ----------
        data : dict
            A graph in the format ``json_schema.md`` describes.

        Returns
        -------
        GraphDocument

        Notes
        -----
        Edges naming a node or a port that is not there are **dropped**, not
        kept. An edge to a missing endpoint has nowhere to draw, so keeping it
        produces a graph that looks smaller than it is and evaluates
        differently from what is on screen.
        """
        document = cls()
        document.meta = dict((data or {}).get("meta") or {})
        for entry in (data or {}).get("nodes") or []:
            node = GraphNode(
                node_id=entry.get("id", ""),
                node_type=entry.get("type", "generic"),
                title=entry.get("title", entry.get("id", "")),
                config=entry.get("config") or {},
                pos=tuple(entry.get("pos") or entry.get("position") or (0.0, 0.0)),
                collapsed=bool(entry.get("collapsed", False)),
            )
            for is_output, key in ((False, "inputs"), (True, "outputs")):
                for port_entry in entry.get(key) or []:
                    port = cls._port_from_entry(port_entry, is_output)
                    if port is not None:
                        (node.outputs if is_output else node.inputs).append(port)
            if node.id:
                document.add_node(node)

        for entry in (data or {}).get("edges") or []:
            edge = GraphEdge(
                source=entry.get("source", ""),
                source_port=int(entry.get("source_port", 0) or 0),
                target=entry.get("target", ""),
                target_port=int(entry.get("target_port", 0) or 0),
                config=entry.get("config") or {},
            )
            source, target = document.node(edge.source), document.node(edge.target)
            reason = None
            if source is None or target is None:
                reason = "names a node that is not in the graph"
            elif source.port(edge.source_port, True) is None:
                reason = (
                    f"source port {edge.source_port} is not one of "
                    f"{len(source.outputs)} outputs"
                )
            elif target.port(edge.target_port, False) is None:
                reason = (
                    f"target port {edge.target_port} is not one of "
                    f"{len(target.inputs)} inputs"
                )
            if reason is not None:
                # Loud, because this is how a producer using the *other* port
                # convention presents: the nodes all load, the edges all
                # vanish, and the graph looks like it simply has none. The old
                # scene indexed one flat list of inputs-then-outputs; the
                # schema indexes each direction separately, and a graph written
                # to the first convention loses exactly its output-side edges.
                logger.warning("dropping edge %s -> %s: %s",
                               edge.source, edge.target, reason)
                continue
            document.add_edge(edge)
        return document

    def to_dict(self) -> dict:
        """Serialise to schema v1.

        Returns
        -------
        dict
            A graph in the format ``json_schema.md`` describes.
        """
        return {
            "version": SCHEMA_VERSION,
            "meta": copy.deepcopy(self.meta),
            "nodes": [
                {
                    "id": node.id,
                    "type": node.type,
                    "title": node.title,
                    "inputs": [self._port_to_entry(p) for p in node.inputs],
                    "outputs": [self._port_to_entry(p) for p in node.outputs],
                    "config": copy.deepcopy(node.config),
                    "pos": [node.pos[0], node.pos[1]],
                    "collapsed": node.collapsed,
                }
                for node in self.nodes
            ],
            "edges": [
                {
                    "source": edge.source,
                    "source_port": edge.source_port,
                    "target": edge.target,
                    "target_port": edge.target_port,
                    **({"config": copy.deepcopy(edge.config)} if edge.config else {}),
                }
                for edge in self.edges
            ],
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialise to a JSON string.

        Parameters
        ----------
        indent : int
            Passed to :func:`json.dumps`.

        Returns
        -------
        str
        """
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_json(cls, text: str) -> "GraphDocument":
        """Parse a JSON string into a document.

        Parameters
        ----------
        text : str
            JSON in schema v1.

        Returns
        -------
        GraphDocument
        """
        return cls.from_dict(json.loads(text))
