"""Graph containers: :class:`Graph` (undirected) and :class:`DiGraph` (directed).

The containers hold arbitrary hashable nodes and dict-valued attributes on both
nodes and edges, which is all any consumer in this project needs. Iteration
order is insertion order everywhere, so every algorithm and every layout built
on top is reproducible run to run -- a redrawn picture that reshuffles itself is
unreadable to a human.

Notes
-----
The API is deliberately the subset of the well-known Python graph-library
spelling (``add_edge``, ``G.nodes[n]``, ``G[u][v]``, ``neighbors``,
``predecessors``) so that reading code written against that vocabulary does not
require a translation table.
"""

from __future__ import annotations

import typing

__all__ = [
    "CycleError",
    "DiGraph",
    "EdgeView",
    "Graph",
    "GraphError",
    "NodeView",
]


class GraphError(Exception):
    """Base class for every error raised by :mod:`chisurf.core.graph`."""


class CycleError(GraphError):
    """Raised when an operation needs an acyclic graph but the graph has a cycle."""


class NodeView:
    """A live view of a graph's nodes and their attributes.

    Iterating yields the nodes; indexing with a node yields its (mutable)
    attribute dictionary.

    Parameters
    ----------
    nodes : dict
        The owning graph's node-to-attributes mapping. Held by reference, so the
        view follows later mutations of the graph.
    """

    __slots__ = ("_nodes",)

    def __init__(self, nodes: dict[typing.Any, dict]):
        self._nodes = nodes

    def __call__(self) -> NodeView:
        """Return the view itself, so ``G.nodes`` and ``G.nodes()`` agree."""
        return self

    def __iter__(self) -> typing.Iterator:
        """Iterate over the nodes in insertion order."""
        return iter(self._nodes)

    def __len__(self) -> int:
        """Return the number of nodes."""
        return len(self._nodes)

    def __contains__(self, node) -> bool:
        """Return whether ``node`` is in the graph."""
        return node in self._nodes

    def __getitem__(self, node) -> dict:
        """Return the attribute dictionary of ``node``."""
        return self._nodes[node]

    def get(self, node, default=None):
        """Return the attribute dictionary of ``node``, or ``default``."""
        return self._nodes.get(node, default)

    def keys(self) -> typing.KeysView:
        """Return the nodes."""
        return self._nodes.keys()

    def items(self) -> typing.ItemsView:
        """Return ``(node, attributes)`` pairs."""
        return self._nodes.items()

    def data(self, key: str = None, default=None):
        """Return ``(node, attributes)`` pairs, or ``(node, attributes[key])``."""
        if key is None:
            return list(self._nodes.items())
        return [(n, a.get(key, default)) for n, a in self._nodes.items()]

    def __repr__(self) -> str:
        """Return a short representation listing the nodes."""
        return f"NodeView({list(self._nodes)!r})"


class EdgeView:
    """A live view of a graph's edges and their attributes.

    Iterating yields ``(u, v)`` pairs -- once per edge for an undirected graph,
    in the direction they were added for a directed one. Indexing with a pair
    yields the (mutable) edge attribute dictionary.

    Parameters
    ----------
    graph : Graph
        The owning graph. Held by reference, so the view follows later
        mutations.
    """

    __slots__ = ("_graph",)

    def __init__(self, graph: Graph):
        self._graph = graph

    def __call__(self, data: bool = False):
        """Return the view, or ``(u, v, attributes)`` triples when ``data``."""
        if data:
            return [(u, v, self._graph._edge_attr(u, v)) for u, v in self]
        return self

    def __iter__(self) -> typing.Iterator[tuple]:
        """Iterate over the edges as ``(u, v)`` pairs."""
        return self._graph._iter_edges()

    def __len__(self) -> int:
        """Return the number of edges."""
        return self._graph.number_of_edges()

    def __contains__(self, edge) -> bool:
        """Return whether ``(u, v)`` is an edge of the graph."""
        try:
            u, v = edge
        except (TypeError, ValueError):
            return False
        return self._graph.has_edge(u, v)

    def __getitem__(self, edge) -> dict:
        """Return the attribute dictionary of the edge ``(u, v)``."""
        u, v = edge
        return self._graph._edge_attr(u, v)

    def data(self, key: str = None, default=None):
        """Return ``(u, v, attributes)`` triples, or ``(u, v, attributes[key])``."""
        if key is None:
            return [(u, v, self._graph._edge_attr(u, v)) for u, v in self]
        return [
            (u, v, self._graph._edge_attr(u, v).get(key, default)) for u, v in self
        ]

    def __repr__(self) -> str:
        """Return a short representation listing the edges."""
        return f"EdgeView({list(self)!r})"


class Graph:
    """An undirected graph with attributes on nodes and edges.

    Parameters
    ----------
    incoming : iterable or Graph, optional
        Edges to seed the graph with -- another graph (nodes, edges and
        attributes are copied) or an iterable of ``(u, v)`` pairs.
    **attr
        Graph-level attributes, available as :attr:`graph`.

    Examples
    --------
    >>> g = Graph()
    >>> g.add_edge("a", "b", weight=2.0)
    >>> g.add_node("c")
    >>> sorted(g.nodes)
    ['a', 'b', 'c']
    >>> g["a"]["b"]["weight"]
    2.0
    """

    def __init__(self, incoming=None, **attr):
        #: node -> attribute dict
        self._node: dict[typing.Any, dict] = {}
        #: node -> neighbour -> shared edge attribute dict
        self._adj: dict[typing.Any, dict[typing.Any, dict]] = {}
        #: graph-level attributes
        self.graph: dict = dict(attr)
        if incoming is not None:
            self._load(incoming)

    # -- construction -----------------------------------------------------

    def _load(self, incoming) -> None:
        """Seed the graph from another graph or from an iterable of edges."""
        if isinstance(incoming, Graph):
            for n, a in incoming._node.items():
                self.add_node(n, **a)
            for u, v in incoming.edges:
                self.add_edge(u, v, **incoming._edge_attr(u, v))
            self.graph.update(incoming.graph)
            return
        for edge in incoming:
            self.add_edge(*edge)

    def is_directed(self) -> bool:
        """Return ``False``; :class:`DiGraph` overrides this."""
        return False

    def add_node(self, node, **attr) -> None:
        """Add ``node``, updating its attributes if it is already present."""
        if node not in self._node:
            self._node[node] = {}
            self._adj[node] = {}
        self._node[node].update(attr)

    def add_nodes_from(self, nodes, **attr) -> None:
        """Add every node in ``nodes``, each with the shared attributes ``attr``."""
        for node in nodes:
            if isinstance(node, tuple) and len(node) == 2 and isinstance(node[1], dict):
                n, a = node
                self.add_node(n, **{**attr, **a})
            else:
                self.add_node(node, **attr)

    def add_edge(self, u, v, **attr) -> None:
        """Add an edge between ``u`` and ``v``, adding missing nodes.

        Adding an existing edge updates its attributes rather than duplicating
        it. Self-loops are stored but are ignored by :meth:`neighbors`.
        """
        self.add_node(u)
        self.add_node(v)
        data = self._adj[u].get(v)
        if data is None:
            data = {}
            self._adj[u][v] = data
            self._adj[v][u] = data
        data.update(attr)

    def add_edges_from(self, edges, **attr) -> None:
        """Add every edge in ``edges``; items may be ``(u, v)`` or ``(u, v, dict)``."""
        for edge in edges:
            if len(edge) == 3:
                u, v, data = edge
                self.add_edge(u, v, **{**attr, **data})
            else:
                u, v = edge
                self.add_edge(u, v, **attr)

    def remove_node(self, node) -> None:
        """Remove ``node`` and every edge incident to it.

        Raises
        ------
        GraphError
            If ``node`` is not in the graph.
        """
        if node not in self._node:
            raise GraphError(f"node {node!r} is not in the graph")
        for nbr in list(self._adj[node]):
            if nbr != node:
                del self._adj[nbr][node]
        del self._adj[node]
        del self._node[node]

    def remove_edge(self, u, v) -> None:
        """Remove the edge between ``u`` and ``v``.

        Raises
        ------
        GraphError
            If the edge is not in the graph.
        """
        if not self.has_edge(u, v):
            raise GraphError(f"edge ({u!r}, {v!r}) is not in the graph")
        del self._adj[u][v]
        if u != v:
            del self._adj[v][u]

    # -- access -----------------------------------------------------------

    @property
    def nodes(self) -> NodeView:
        """Return a live :class:`NodeView` of the graph's nodes."""
        return NodeView(self._node)

    @property
    def edges(self) -> EdgeView:
        """Return a live :class:`EdgeView` of the graph's edges."""
        return EdgeView(self)

    @property
    def adj(self) -> dict[typing.Any, dict[typing.Any, dict]]:
        """Return the adjacency mapping ``node -> neighbour -> attributes``."""
        return self._adj

    def __getitem__(self, node) -> dict[typing.Any, dict]:
        """Return ``node``'s adjacency mapping, so ``G[u][v]`` are edge attributes."""
        return self._adj[node]

    def __iter__(self) -> typing.Iterator:
        """Iterate over the nodes."""
        return iter(self._node)

    def __len__(self) -> int:
        """Return the number of nodes."""
        return len(self._node)

    def __contains__(self, node) -> bool:
        """Return whether ``node`` is in the graph."""
        try:
            return node in self._node
        except TypeError:  # unhashable
            return False

    def __repr__(self) -> str:
        """Return a compact summary of the graph's size."""
        return (
            f"{type(self).__name__}({self.number_of_nodes()} nodes, "
            f"{self.number_of_edges()} edges)"
        )

    def has_node(self, node) -> bool:
        """Return whether ``node`` is in the graph."""
        return node in self._node

    def has_edge(self, u, v) -> bool:
        """Return whether the graph holds an edge between ``u`` and ``v``."""
        return u in self._adj and v in self._adj[u]

    def neighbors(self, node) -> typing.Iterator:
        """Iterate over the neighbours of ``node`` (self-loops excluded).

        Raises
        ------
        GraphError
            If ``node`` is not in the graph.
        """
        if node not in self._adj:
            raise GraphError(f"node {node!r} is not in the graph")
        return iter([n for n in self._adj[node] if n != node])

    def degree(self, node=None):
        """Return the degree of ``node``, or all ``(node, degree)`` pairs."""
        if node is None:
            return [(n, self.degree(n)) for n in self._node]
        return sum(2 if nbr == node else 1 for nbr in self._adj[node])

    def number_of_nodes(self) -> int:
        """Return the number of nodes."""
        return len(self._node)

    def number_of_edges(self) -> int:
        """Return the number of edges."""
        total = sum(len(nbrs) for nbrs in self._adj.values())
        loops = sum(1 for n in self._adj if n in self._adj[n])
        return (total - loops) // 2 + loops

    def copy(self) -> Graph:
        """Return an independent copy: new attribute dicts, same node objects."""
        out = type(self)()
        for n, a in self._node.items():
            out.add_node(n, **a)
        for u, v in self.edges:
            out.add_edge(u, v, **self._edge_attr(u, v))
        out.graph.update(self.graph)
        return out

    def subgraph(self, nodes) -> Graph:
        """Return the copy induced by ``nodes`` (edges with both ends kept)."""
        keep = [n for n in nodes if n in self._node]
        wanted = set(keep)
        out = type(self)()
        for n in keep:
            out.add_node(n, **self._node[n])
        for u, v in self.edges:
            if u in wanted and v in wanted:
                out.add_edge(u, v, **self._edge_attr(u, v))
        out.graph.update(self.graph)
        return out

    def get_edge_data(self, u, v, default=None):
        """Return the attribute dictionary of edge ``(u, v)``, or ``default``."""
        if not self.has_edge(u, v):
            return default
        return self._edge_attr(u, v)

    # -- internals --------------------------------------------------------

    def _edge_attr(self, u, v) -> dict:
        """Return the attribute dictionary of edge ``(u, v)``."""
        return self._adj[u][v]

    def _iter_edges(self) -> typing.Iterator[tuple]:
        """Yield every edge once, in insertion order of the first endpoint."""
        seen: set[typing.Any] = set()
        for u, nbrs in self._adj.items():
            for v in nbrs:
                if v not in seen:
                    yield (u, v)
            seen.add(u)


class DiGraph(Graph):
    """A directed graph with attributes on nodes and edges.

    Successors and predecessors are tracked separately; :meth:`neighbors` means
    successors, matching the usual convention.

    Examples
    --------
    >>> g = DiGraph()
    >>> g.add_edge(1, 2)
    >>> list(g.successors(1)), list(g.predecessors(2))
    ([2], [1])
    """

    def __init__(self, incoming=None, **attr):
        #: node -> successor -> edge attribute dict
        self._succ: dict[typing.Any, dict[typing.Any, dict]] = {}
        #: node -> predecessor -> edge attribute dict (the same dict objects)
        self._pred: dict[typing.Any, dict[typing.Any, dict]] = {}
        super().__init__(incoming, **attr)
        # Inherited code that reaches for ``_adj`` means "what this node points
        # at", which for a directed graph is its successors.
        self._adj = self._succ

    def is_directed(self) -> bool:
        """Return ``True``."""
        return True

    def add_node(self, node, **attr) -> None:
        """Add ``node``, updating its attributes if it is already present."""
        if node not in self._node:
            self._node[node] = {}
            self._succ[node] = {}
            self._pred[node] = {}
        self._node[node].update(attr)

    def add_edge(self, u, v, **attr) -> None:
        """Add a directed edge ``u -> v``, adding missing nodes."""
        self.add_node(u)
        self.add_node(v)
        data = self._succ[u].get(v)
        if data is None:
            data = {}
            self._succ[u][v] = data
            self._pred[v][u] = data
        data.update(attr)

    def remove_node(self, node) -> None:
        """Remove ``node`` and every edge incident to it."""
        if node not in self._node:
            raise GraphError(f"node {node!r} is not in the graph")
        for succ in list(self._succ[node]):
            self._pred[succ].pop(node, None)
        for pred in list(self._pred[node]):
            self._succ[pred].pop(node, None)
        del self._succ[node]
        del self._pred[node]
        del self._node[node]

    def remove_edge(self, u, v) -> None:
        """Remove the directed edge ``u -> v``."""
        if not self.has_edge(u, v):
            raise GraphError(f"edge ({u!r}, {v!r}) is not in the graph")
        del self._succ[u][v]
        del self._pred[v][u]

    @property
    def adj(self):
        """Return the successor mapping ``node -> successor -> attributes``."""
        return self._succ

    @property
    def pred(self):
        """Return the predecessor mapping ``node -> predecessor -> attributes``."""
        return self._pred

    def __getitem__(self, node):
        """Return ``node``'s successor mapping, so ``G[u][v]`` are edge attributes."""
        return self._succ[node]

    def has_edge(self, u, v) -> bool:
        """Return whether the directed edge ``u -> v`` exists."""
        return u in self._succ and v in self._succ[u]

    def successors(self, node) -> typing.Iterator:
        """Iterate over the successors of ``node``."""
        if node not in self._succ:
            raise GraphError(f"node {node!r} is not in the graph")
        return iter(list(self._succ[node]))

    def predecessors(self, node) -> typing.Iterator:
        """Iterate over the predecessors of ``node``."""
        if node not in self._pred:
            raise GraphError(f"node {node!r} is not in the graph")
        return iter(list(self._pred[node]))

    def neighbors(self, node) -> typing.Iterator:
        """Iterate over the successors of ``node``."""
        return self.successors(node)

    def in_degree(self, node=None):
        """Return the in-degree of ``node``, or all ``(node, in-degree)`` pairs."""
        if node is None:
            return [(n, len(self._pred[n])) for n in self._node]
        return len(self._pred[node])

    def out_degree(self, node=None):
        """Return the out-degree of ``node``, or all ``(node, out-degree)`` pairs."""
        if node is None:
            return [(n, len(self._succ[n])) for n in self._node]
        return len(self._succ[node])

    def degree(self, node=None):
        """Return in-degree plus out-degree, for ``node`` or for every node."""
        if node is None:
            return [(n, self.degree(n)) for n in self._node]
        return len(self._succ[node]) + len(self._pred[node])

    def number_of_edges(self) -> int:
        """Return the number of directed edges."""
        return sum(len(s) for s in self._succ.values())

    def to_undirected(self) -> Graph:
        """Return an undirected copy, merging opposite edges into one."""
        out = Graph()
        for n, a in self._node.items():
            out.add_node(n, **a)
        for u, v in self.edges:
            out.add_edge(u, v, **self._edge_attr(u, v))
        out.graph.update(self.graph)
        return out

    # -- internals --------------------------------------------------------

    def _edge_attr(self, u, v) -> dict:
        """Return the attribute dictionary of the directed edge ``u -> v``."""
        return self._succ[u][v]

    def _iter_edges(self) -> typing.Iterator[tuple]:
        """Yield every directed edge in insertion order."""
        for u, succs in self._succ.items():
            for v in succs:
                yield (u, v)
