"""Graph algorithms: components, orderings, cycles, spanning trees, distances.

Everything here is plain Python over :class:`~chisurf.core.graph.graph.Graph` /
:class:`~chisurf.core.graph.graph.DiGraph` and is deterministic: results follow the
insertion order of the nodes, so the same graph always gives the same answer in
the same order.
"""

from __future__ import annotations

import heapq
import itertools
import typing

from .graph import CycleError, DiGraph, Graph

__all__ = [
    "complete_graph",
    "connected_components",
    "is_connected",
    "is_directed_acyclic_graph",
    "maximum_spanning_tree",
    "minimum_spanning_tree",
    "number_connected_components",
    "path_graph",
    "shortest_path_length",
    "simple_cycles",
    "topological_sort",
]


# -- generators -----------------------------------------------------------


def complete_graph(n) -> Graph:
    """Return the complete graph over ``n``.

    Parameters
    ----------
    n : int or iterable
        Either a node count (nodes are ``0 .. n-1``) or the nodes themselves.

    Returns
    -------
    Graph
        Every pair of distinct nodes joined by an edge.
    """
    nodes = list(range(n)) if isinstance(n, int) else list(n)
    g = Graph()
    g.add_nodes_from(nodes)
    for u, v in itertools.combinations(nodes, 2):
        g.add_edge(u, v)
    return g


def path_graph(n) -> Graph:
    """Return the path graph over ``n`` (a chain, ``n`` a count or the nodes)."""
    nodes = list(range(n)) if isinstance(n, int) else list(n)
    g = Graph()
    g.add_nodes_from(nodes)
    for u, v in zip(nodes, nodes[1:]):
        g.add_edge(u, v)
    return g


# -- connectivity ---------------------------------------------------------


def connected_components(graph: Graph) -> typing.Iterator[set]:
    """Yield the connected components of an undirected graph as sets of nodes.

    Components are yielded in the order their first node appears in the graph.

    Parameters
    ----------
    graph : Graph
        Undirected graph. A directed graph is treated as its undirected
        skeleton.

    Yields
    ------
    set
        The nodes of one component.
    """
    seen: set = set()
    for start in graph.nodes:
        if start in seen:
            continue
        component: set = set()
        stack = [start]
        seen.add(start)
        while stack:
            node = stack.pop()
            component.add(node)
            for nbr in _undirected_neighbours(graph, node):
                if nbr not in seen:
                    seen.add(nbr)
                    stack.append(nbr)
        yield component


def number_connected_components(graph: Graph) -> int:
    """Return how many connected components ``graph`` has."""
    return sum(1 for _ in connected_components(graph))


def is_connected(graph: Graph) -> bool:
    """Return whether every node of ``graph`` is reachable from every other.

    Raises
    ------
    ValueError
        If the graph is empty, where connectivity is undefined.
    """
    if graph.number_of_nodes() == 0:
        raise ValueError("connectivity is undefined for the empty graph")
    return number_connected_components(graph) == 1


def _undirected_neighbours(graph: Graph, node) -> typing.Iterator:
    """Yield the neighbours of ``node``, ignoring edge direction."""
    if graph.is_directed():
        yield from graph.successors(node)
        yield from graph.predecessors(node)
    else:
        yield from graph.neighbors(node)


# -- orderings and cycles -------------------------------------------------


def topological_sort(graph: DiGraph) -> typing.Iterator:
    """Yield the nodes of a DAG so that every edge points forwards.

    Kahn's algorithm, taking ready nodes in insertion order so the result is
    reproducible.

    Parameters
    ----------
    graph : DiGraph
        Directed graph.

    Yields
    ------
    node
        The next node in a topological order.

    Raises
    ------
    CycleError
        If the graph has a cycle, as soon as the order cannot be continued.
    """
    if not graph.is_directed():
        raise CycleError("topological sort needs a directed graph")
    in_degree = {n: graph.in_degree(n) for n in graph.nodes}
    ready = [n for n, d in in_degree.items() if d == 0]
    emitted = 0
    while ready:
        node = ready.pop(0)
        emitted += 1
        yield node
        for succ in graph.successors(node):
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                ready.append(succ)
    if emitted != graph.number_of_nodes():
        raise CycleError("graph contains a cycle; no topological order exists")


def is_directed_acyclic_graph(graph) -> bool:
    """Return whether ``graph`` is directed and free of cycles."""
    if not getattr(graph, "is_directed", lambda: False)():
        return False
    try:
        for _ in topological_sort(graph):
            pass
    except CycleError:
        return False
    return True


def _strongly_connected_components(
    nodes: list,
    succ: dict[typing.Any, list],
) -> list[list]:
    """Return the strongly connected components of a sub-graph.

    Tarjan's algorithm, written iteratively so that a deep graph cannot blow the
    Python stack.

    Parameters
    ----------
    nodes : list
        The nodes to consider, in the order they should be visited.
    succ : dict
        Node to list of successors, restricted to ``nodes``.

    Returns
    -------
    list of list
        One list of nodes per component.
    """
    index: dict[typing.Any, int] = {}
    low: dict[typing.Any, int] = {}
    on_stack: set = set()
    stack: list = []
    result: list[list] = []
    counter = itertools.count()

    for root in nodes:
        if root in index:
            continue
        work = [(root, iter(succ.get(root, ())))]
        index[root] = low[root] = next(counter)
        stack.append(root)
        on_stack.add(root)
        while work:
            node, successors = work[-1]
            advanced = False
            for nbr in successors:
                if nbr not in index:
                    index[nbr] = low[nbr] = next(counter)
                    stack.append(nbr)
                    on_stack.add(nbr)
                    work.append((nbr, iter(succ.get(nbr, ()))))
                    advanced = True
                    break
                if nbr in on_stack:
                    low[node] = min(low[node], index[nbr])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                component = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                result.append(component)
    return result


def simple_cycles(graph: DiGraph) -> typing.Iterator[list]:
    """Yield the elementary circuits of a directed graph.

    Johnson's algorithm: each cycle is reported once, as the list of its nodes
    in path order (the closing edge back to the first node is implied).
    Self-loops are reported as one-node cycles.

    Parameters
    ----------
    graph : DiGraph
        Directed graph.

    Yields
    ------
    list
        The nodes of one elementary circuit.
    """
    if not graph.is_directed():
        raise CycleError("simple_cycles needs a directed graph")

    order = {n: i for i, n in enumerate(graph.nodes)}
    succ_all = {n: list(graph.successors(n)) for n in graph.nodes}

    for node in graph.nodes:
        if node in succ_all[node]:
            yield [node]

    def _unblock(node, blocked, blocked_by):
        """Unblock ``node`` and, transitively, everything blocked because of it."""
        pending = [node]
        while pending:
            current = pending.pop()
            if current in blocked:
                blocked.discard(current)
                pending.extend(blocked_by.pop(current, ()))

    remaining = sorted(graph.nodes, key=order.get)
    while remaining:
        subgraph_nodes = set(remaining)
        succ = {n: [s for s in succ_all[n] if s in subgraph_nodes and s != n] for n in remaining}
        components = [c for c in _strongly_connected_components(remaining, succ) if len(c) > 1]
        if not components:
            break
        # Start from the smallest-index node of the component holding it, which
        # is what makes every circuit reported exactly once.
        start = min((min(c, key=order.get) for c in components), key=order.get)
        component = next(c for c in components if start in c)
        members = set(component)
        comp_succ = {n: [s for s in succ[n] if s in members] for n in component}

        path = [start]
        blocked = {start}
        blocked_by: dict[typing.Any, set] = {}
        stack = [(start, iter(comp_succ[start]))]
        closed: set = set()
        while stack:
            node, successors = stack[-1]
            found = False
            for nbr in successors:
                if nbr == start:
                    yield list(path)
                    closed.update(path)
                elif nbr not in blocked:
                    path.append(nbr)
                    blocked.add(nbr)
                    # A node re-entered on a new path starts out "not closed"
                    # again; leaving it closed from an earlier path would
                    # unblock it without a circuit and repeat work forever.
                    closed.discard(nbr)
                    stack.append((nbr, iter(comp_succ[nbr])))
                    found = True
                    break
            if found:
                continue
            stack.pop()
            if node in closed:
                _unblock(node, blocked, blocked_by)
            else:
                for nbr in comp_succ[node]:
                    blocked_by.setdefault(nbr, set()).add(node)
            path.pop()
        remaining = [n for n in remaining if n != start]


# -- spanning trees -------------------------------------------------------


def minimum_spanning_tree(graph: Graph, weight: str = "weight") -> Graph:
    """Return a minimum-weight spanning forest of ``graph``.

    Parameters
    ----------
    graph : Graph
        Undirected graph. Missing ``weight`` attributes count as ``1``.
    weight : str, optional
        Edge attribute holding the weight.

    Returns
    -------
    Graph
        Every node of ``graph``, and the edges of the forest with their
        attributes. Disconnected input gives a forest, one tree per component.
    """
    return _spanning_tree(graph, weight, maximise=False)


def maximum_spanning_tree(graph: Graph, weight: str = "weight") -> Graph:
    """Return a maximum-weight spanning forest of ``graph``.

    The junction tree of a factor graph is exactly this over the clique graph
    weighted by separator size, which is what makes the running-intersection
    property hold.

    Parameters
    ----------
    graph : Graph
        Undirected graph. Missing ``weight`` attributes count as ``1``.
    weight : str, optional
        Edge attribute holding the weight.

    Returns
    -------
    Graph
        Every node of ``graph``, and the edges of the forest.
    """
    return _spanning_tree(graph, weight, maximise=True)


def _spanning_tree(graph: Graph, weight: str, maximise: bool) -> Graph:
    """Return a spanning forest by Kruskal's algorithm.

    Ties are broken by the order the edges were added, so the tree is
    reproducible even when every weight is equal.
    """
    tree = type(graph)()
    for node, attr in graph.nodes.items():
        tree.add_node(node, **attr)

    edges = [(u, v, float(graph.get_edge_data(u, v, {}).get(weight, 1.0))) for u, v in graph.edges]
    sign = -1.0 if maximise else 1.0
    ordered = sorted(range(len(edges)), key=lambda i: (sign * edges[i][2], i))

    parent: dict[typing.Any, typing.Any] = {n: n for n in graph.nodes}

    def _find(node):
        """Return the representative of ``node``'s component, path-compressing."""
        root = node
        while parent[root] != root:
            root = parent[root]
        while parent[node] != root:
            parent[node], node = root, parent[node]
        return root

    for i in ordered:
        u, v, _ = edges[i]
        ru, rv = _find(u), _find(v)
        if ru == rv:
            continue
        parent[ru] = rv
        tree.add_edge(u, v, **graph.get_edge_data(u, v, {}))
    return tree


# -- distances ------------------------------------------------------------


def shortest_path_length(
    graph: Graph,
    weight: str = None,
) -> dict[typing.Any, dict[typing.Any, float]]:
    """Return all-pairs shortest path lengths.

    Breadth-first search when the edges are unweighted, Dijkstra's algorithm
    when a weight attribute is named. Unreachable pairs are simply absent from
    the inner dictionary.

    Parameters
    ----------
    graph : Graph
        Graph to measure. Directed graphs are followed along their edges.
    weight : str, optional
        Edge attribute holding a non-negative length; missing attributes count
        as ``1``. ``None`` counts every edge as length ``1``.

    Returns
    -------
    dict
        ``source -> target -> distance``.
    """
    out = {}
    for source in graph.nodes:
        out[source] = (
            _bfs_lengths(graph, source)
            if weight is None
            else _dijkstra_lengths(graph, source, weight)
        )
    return out


def _bfs_lengths(graph: Graph, source) -> dict[typing.Any, float]:
    """Return hop counts from ``source`` by breadth-first search."""
    dist = {source: 0.0}
    frontier = [source]
    depth = 0
    while frontier:
        depth += 1
        nxt = []
        for node in frontier:
            for nbr in graph.neighbors(node):
                if nbr not in dist:
                    dist[nbr] = float(depth)
                    nxt.append(nbr)
        frontier = nxt
    return dist


def _dijkstra_lengths(
    graph: Graph,
    source,
    weight: str,
) -> dict[typing.Any, float]:
    """Return weighted distances from ``source`` by Dijkstra's algorithm."""
    dist: dict[typing.Any, float] = {}
    order = {n: i for i, n in enumerate(graph.nodes)}
    # The insertion index is a tie-break that keeps the heap from comparing the
    # nodes themselves, which need not be orderable at all.
    heap = [(0.0, order[source], source)]
    while heap:
        d, _, node = heapq.heappop(heap)
        if node in dist:
            continue
        dist[node] = d
        for nbr in graph.neighbors(node):
            if nbr in dist:
                continue
            step = float(graph.get_edge_data(node, nbr, {}).get(weight, 1.0))
            if step < 0.0:
                raise ValueError(f"negative edge weight {step!r} on ({node!r}, {nbr!r})")
            heapq.heappush(heap, (d + step, order[nbr], nbr))
    return dist
