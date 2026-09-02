r"""Graph layouts: coordinates for drawing a graph.

Every layout takes a graph and returns ``{node: array([x, y])}``, centred on the
origin and scaled so the widest extent reaches ``scale``. All of them are
*deterministic*: the same graph gives the same picture on every call, because a
redraw that reshuffles the nodes is unreadable to a human.

===================  =====================================================
layout               what it optimises
===================  =====================================================
:func:`circular`     nodes evenly on one circle -- structure-free, fast
:func:`shell`        concentric circles, one per group of nodes
:func:`spectral`     eigenvectors of the graph Laplacian; separates clusters
:func:`spring`       Fruchterman-Reingold: edges pull, nodes push
:func:`kamada_kawai` stress: drawn distance matches graph distance
:func:`arf`          attractive/repulsive forces, spring constant per edge
===================  =====================================================

Kamada-Kawai is the most readable for the small sparse graphs this project
draws, and is minimised here by stress majorization (SMACOF), which needs only
:mod:`numpy` and converges monotonically from a circular start.
"""

from __future__ import annotations

import typing

import numpy as np

from .algorithms import shortest_path_length
from .graph import Graph

__all__ = [
    "arf_layout",
    "circular_layout",
    "kamada_kawai_layout",
    "shell_layout",
    "spectral_layout",
    "spring_layout",
]

#: Target distance between nodes that cannot reach each other, as a multiple of
#: the widest distance that *is* defined. Far enough that the components read as
#: separate, near enough that they still share the canvas -- an "infinite"
#: separation would squash every real component to a point.
DISCONNECTED_FACTOR = 1.5


def _empty_or_single(
        graph: Graph,
        center: np.ndarray,
) -> dict[typing.Any, np.ndarray] | None:
    """Return the layout of a graph too small to lay out, or ``None``."""
    if graph.number_of_nodes() == 0:
        return {}
    if graph.number_of_nodes() == 1:
        return {next(iter(graph.nodes)): np.asarray(center, dtype=float)}
    return None


def _center(center, dim: int = 2) -> np.ndarray:
    """Return the layout centre as an array, defaulting to the origin."""
    if center is None:
        return np.zeros(dim, dtype=float)
    out = np.asarray(center, dtype=float)
    if out.shape != (dim,):
        raise ValueError(f"center must have length {dim}")
    return out


def _rescale(
        pos: np.ndarray,
        scale: float,
        center: np.ndarray,
) -> np.ndarray:
    """Centre ``pos`` on the origin, scale it to ``scale``, then shift to ``center``."""
    out = np.asarray(pos, dtype=float) - np.asarray(pos, dtype=float).mean(axis=0)
    span = float(np.abs(out).max())
    if span > 1e-12 and scale is not None:
        out = out * (float(scale) / span)
    return out + center


def _as_dict(
        graph: Graph,
        pos: np.ndarray,
) -> dict[typing.Any, np.ndarray]:
    """Return ``{node: coordinates}`` for the rows of ``pos``."""
    return {node: np.asarray(row, dtype=float) for node, row in zip(graph.nodes, pos)}


def _adjacency_matrix(graph: Graph, weight: str = "weight") -> np.ndarray:
    """Return the symmetric adjacency matrix, using ``weight`` where present."""
    nodes = list(graph.nodes)
    index = {n: i for i, n in enumerate(nodes)}
    a = np.zeros((len(nodes), len(nodes)), dtype=float)
    for u, v in graph.edges:
        w = 1.0
        if weight is not None:
            w = float(graph.get_edge_data(u, v, {}).get(weight, 1.0))
        i, j = index[u], index[v]
        a[i, j] = a[j, i] = w
    return a


def circular_layout(
        graph: Graph,
        scale: float = 1.0,
        center=None,
) -> dict[typing.Any, np.ndarray]:
    """Return positions on a single circle, in node order.

    Parameters
    ----------
    graph : Graph
        Graph to lay out.
    scale : float, optional
        Radius of the circle.
    center : array-like, optional
        Centre of the drawing; the origin by default.

    Returns
    -------
    dict
        Node to ``(x, y)``.
    """
    centre = _center(center)
    trivial = _empty_or_single(graph, centre)
    if trivial is not None:
        return trivial
    n = graph.number_of_nodes()
    theta = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
    pos = np.column_stack([np.cos(theta), np.sin(theta)]) * float(scale)
    return _as_dict(graph, pos + centre)


def shell_layout(
        graph: Graph,
        nlist: typing.Sequence[typing.Sequence] = None,
        scale: float = 1.0,
        center=None,
        rotate: float = None,
) -> dict[typing.Any, np.ndarray]:
    r"""Return positions on concentric circles, one circle per shell.

    Parameters
    ----------
    graph : Graph
        Graph to lay out.
    nlist : sequence of sequence, optional
        The shells, innermost first. All nodes on one circle by default.
    scale : float, optional
        Radius of the outermost shell.
    center : array-like, optional
        Centre of the drawing.
    rotate : float, optional
        Angle in radians by which each successive shell is rotated, so nodes on
        neighbouring shells do not line up radially. Defaults to
        :math:`\\pi / \\text{len(nlist)}`.

    Returns
    -------
    dict
        Node to ``(x, y)``.
    """
    centre = _center(center)
    trivial = _empty_or_single(graph, centre)
    if trivial is not None:
        return trivial
    if nlist is None:
        nlist = [list(graph.nodes)]
    shells = [list(s) for s in nlist if len(s)]
    if not shells:
        return {}
    if rotate is None:
        rotate = np.pi / len(shells)
    out: dict[typing.Any, np.ndarray] = {}
    for k, shell in enumerate(shells):
        radius = float(scale) * (k + 1) / len(shells)
        theta = np.linspace(0.0, 2.0 * np.pi, len(shell), endpoint=False)
        theta = theta + k * rotate
        points = radius * np.column_stack([np.cos(theta), np.sin(theta)])
        if len(shell) == 1:
            points = np.zeros((1, 2)) if k == 0 else points
        for node, point in zip(shell, points):
            out[node] = point + centre
    return out


def spectral_layout(
        graph: Graph,
        weight: str = "weight",
        scale: float = 1.0,
        center=None,
) -> dict[typing.Any, np.ndarray]:
    r"""Return positions from the eigenvectors of the graph Laplacian.

    The two eigenvectors of :math:`L = D - A` with the smallest non-zero
    eigenvalues minimise :math:`\\sum_{ij} A_{ij} |x_i - x_j|^2`, so adjacent
    nodes are placed close and the drawing separates loosely connected clusters.
    Deterministic and cheap; less readable than :func:`kamada_kawai_layout` for
    small graphs.

    Parameters
    ----------
    graph : Graph
        Graph to lay out.
    weight : str, optional
        Edge attribute holding the coupling strength.
    scale : float, optional
        Half-width of the drawing.
    center : array-like, optional
        Centre of the drawing.

    Returns
    -------
    dict
        Node to ``(x, y)``.
    """
    centre = _center(center)
    trivial = _empty_or_single(graph, centre)
    if trivial is not None:
        return trivial
    a = _adjacency_matrix(graph, weight)
    laplacian = np.diag(a.sum(axis=1)) - a
    values, vectors = np.linalg.eigh(laplacian)
    order = np.argsort(values)
    # The first eigenvector is constant (every node on top of every other), so
    # the drawing starts at the second.
    pos = vectors[:, order[1:3]]
    if pos.shape[1] < 2:
        pos = np.column_stack([pos, np.zeros(len(pos))])
    return _as_dict(graph, _rescale(pos, scale, centre))


def spring_layout(
        graph: Graph,
        k: float = None,
        pos: dict = None,
        iterations: int = 50,
        threshold: float = 1e-4,
        weight: str = "weight",
        scale: float = 1.0,
        center=None,
        seed: int = 0,
) -> dict[typing.Any, np.ndarray]:
    r"""Return a Fruchterman-Reingold force-directed layout.

    Edges act as springs pulling their endpoints together while every pair of
    nodes repels, with a step size that cools linearly over the iterations.

    Parameters
    ----------
    graph : Graph
        Graph to lay out.
    k : float, optional
        Preferred edge length; :math:`1/\\sqrt{n}` by default.
    pos : dict, optional
        Starting positions; a seeded pseudo-random cloud by default.
    iterations : int, optional
        Number of cooling steps.
    threshold : float, optional
        Stop once the mean displacement per node falls below this.
    weight : str, optional
        Edge attribute holding the spring strength.
    scale : float, optional
        Half-width of the drawing.
    center : array-like, optional
        Centre of the drawing.
    seed : int, optional
        Seed of the starting cloud. Fixed by default so a redraw of the same
        graph does not reshuffle the picture.

    Returns
    -------
    dict
        Node to ``(x, y)``.
    """
    centre = _center(center)
    trivial = _empty_or_single(graph, centre)
    if trivial is not None:
        return trivial

    nodes = list(graph.nodes)
    n = len(nodes)
    a = _adjacency_matrix(graph, weight)
    if pos is None:
        rng = np.random.default_rng(seed)
        points = rng.random((n, 2))
    else:
        points = np.array(
            [np.asarray(pos.get(node, (0.0, 0.0)), dtype=float) for node in nodes]
        )
    if k is None:
        k = 1.0 / np.sqrt(n)

    # Step size: start at a tenth of the drawing's extent and cool to zero.
    t = 0.1 * max(float(np.ptp(points[:, 0])), float(np.ptp(points[:, 1])), 1e-3)
    dt = t / (iterations + 1)
    for _ in range(iterations):
        delta = points[:, None, :] - points[None, :, :]
        distance = np.linalg.norm(delta, axis=-1)
        np.clip(distance, 0.01, None, out=distance)
        # repulsion k^2/d for every pair, attraction A d/k along the edges
        force = k * k / distance**2 - a * distance / k
        displacement = np.einsum("ijd,ij->id", delta, force)
        length = np.linalg.norm(displacement, axis=-1)
        length = np.where(length < 0.01, 0.1, length)
        step = displacement * (t / length)[:, None]
        points = points + step
        t -= dt
        if float(np.linalg.norm(step)) / n < threshold:
            break
    return _as_dict(graph, _rescale(points, scale, centre))


def _distance_matrix(graph: Graph, weight: str) -> np.ndarray:
    """Return the all-pairs graph-distance matrix, in node order.

    Pairs in different components have no graph distance; they are given
    :data:`DISCONNECTED_FACTOR` times the largest distance that does exist, so
    the components are pushed apart without dominating the drawing.
    """
    nodes = list(graph.nodes)
    index = {n: i for i, n in enumerate(nodes)}
    lengths = shortest_path_length(graph, weight=weight)
    d = np.full((len(nodes), len(nodes)), np.nan, dtype=float)
    for source, targets in lengths.items():
        row = index[source]
        for target, length in targets.items():
            d[row, index[target]] = float(length)
    finite = d[np.isfinite(d)]
    reach = float(finite.max()) if finite.size else 0.0
    d[~np.isfinite(d)] = DISCONNECTED_FACTOR * reach if reach > 0.0 else 1.0
    # Directed input, or rounding, can leave the matrix a hair asymmetric; the
    # stress model is undirected, so symmetrise on the shorter path.
    d = np.minimum(d, d.T)
    np.fill_diagonal(d, 0.0)
    return d


def kamada_kawai_layout(
        graph: Graph,
        dist: np.ndarray = None,
        pos: dict = None,
        weight: str = "weight",
        scale: float = 1.0,
        center=None,
        max_iter: int = 300,
        tol: float = 1e-7,
) -> dict[typing.Any, np.ndarray]:
    r"""Return a layout whose drawn distances match the graph distances.

    Minimises the Kamada-Kawai stress

    .. math::

        \sigma(X) = \sum_{i<j} \frac{(\|x_i - x_j\| - d_{ij})^2}{d_{ij}^2}

    where :math:`d_{ij}` is the shortest-path distance, by stress majorization
    (SMACOF): each iteration solves a weighted least-squares problem whose
    solution cannot increase the stress, started from a circular layout so the
    result is reproducible.

    Parameters
    ----------
    graph : Graph
        Graph to lay out.
    dist : ndarray, optional
        Target distance matrix in node order, overriding the graph distances.
    pos : dict, optional
        Starting positions; a circle by default.
    weight : str, optional
        Edge attribute read as a *length* -- larger means further apart.
    scale : float, optional
        Half-width of the drawing.
    center : array-like, optional
        Centre of the drawing.
    max_iter : int, optional
        Maximum majorization steps.
    tol : float, optional
        Stop once the relative stress improvement falls below this.

    Returns
    -------
    dict
        Node to ``(x, y)``.
    """
    centre = _center(center)
    trivial = _empty_or_single(graph, centre)
    if trivial is not None:
        return trivial

    nodes = list(graph.nodes)
    d = np.asarray(dist, dtype=float) if dist is not None else _distance_matrix(
        graph, weight
    )
    if d.shape != (len(nodes), len(nodes)):
        raise ValueError("dist must be a square matrix in node order")

    if pos is None:
        start = np.array([circular_layout(graph)[n] for n in nodes], dtype=float)
    else:
        start = np.array(
            [np.asarray(pos[n], dtype=float) for n in nodes], dtype=float
        )

    points = _smacof(d, start, max_iter=max_iter, tol=tol)
    return _as_dict(graph, _rescale(points, scale, centre))


def _smacof(
        d: np.ndarray,
        start: np.ndarray,
        max_iter: int = 300,
        tol: float = 1e-7,
) -> np.ndarray:
    """Minimise weighted stress by majorization, starting from ``start``.

    Parameters
    ----------
    d : ndarray
        Target distances, symmetric with a zero diagonal.
    start : ndarray
        Initial ``(n, 2)`` coordinates.
    max_iter : int, optional
        Maximum iterations.
    tol : float, optional
        Relative stress improvement below which to stop.

    Returns
    -------
    ndarray
        The ``(n, 2)`` coordinates found.
    """
    with np.errstate(divide="ignore", invalid="ignore"):
        w = np.where(d > 0.0, 1.0 / np.maximum(d, 1e-12) ** 2, 0.0)
    np.fill_diagonal(w, 0.0)

    v = -w.copy()
    np.fill_diagonal(v, 0.0)
    np.fill_diagonal(v, -v.sum(axis=1))
    # V is singular by construction (a layout is fixed only up to translation),
    # so the majorization step uses its pseudo-inverse.
    v_pinv = np.linalg.pinv(v)

    points = np.array(start, dtype=float)
    previous = None
    for _ in range(max_iter):
        current = np.linalg.norm(points[:, None, :] - points[None, :, :], axis=-1)
        stress = float(0.5 * (w * (current - d) ** 2).sum())
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(current > 1e-12, d / np.maximum(current, 1e-12), 0.0)
        b = -w * ratio
        np.fill_diagonal(b, 0.0)
        np.fill_diagonal(b, -b.sum(axis=1))
        points = v_pinv @ (b @ points)
        if previous is not None and abs(previous - stress) <= tol * max(previous, 1e-12):
            break
        previous = stress
    return points


def arf_layout(
        graph: Graph,
        pos: dict = None,
        scaling: float = 1.0,
        a: float = 1.1,
        etol: float = 1e-6,
        dt: float = 1e-3,
        max_iter: int = 1000,
        scale: float = 1.0,
        center=None,
) -> dict[typing.Any, np.ndarray]:
    """Return an attractive/repulsive force layout.

    Every pair of nodes attracts with a force proportional to their separation
    -- more strongly, by the factor ``a``, when they share an edge -- and repels
    with a force of constant magnitude ``scaling``. The equilibrium places
    adjacent nodes about ``scaling / a`` apart and non-adjacent ones about
    ``scaling`` apart, which keeps clusters compact without letting the rest of
    the drawing collapse.

    Parameters
    ----------
    graph : Graph
        Graph to lay out.
    pos : dict, optional
        Starting positions; a circle by default.
    scaling : float, optional
        Strength of the repulsion, and so the natural node separation.
    a : float, optional
        Extra spring strength on an edge; must exceed 1.
    etol : float, optional
        Stop once the total residual force falls below this.
    dt : float, optional
        Integration step.
    max_iter : int, optional
        Maximum steps.
    scale : float, optional
        Half-width of the drawing. ``None`` leaves the raw equilibrium sizes.
    center : array-like, optional
        Centre of the drawing.

    Returns
    -------
    dict
        Node to ``(x, y)``.
    """
    if a <= 1.0:
        raise ValueError(f"the spring constant a must exceed 1, got {a!r}")
    centre = _center(center)
    trivial = _empty_or_single(graph, centre)
    if trivial is not None:
        return trivial

    nodes = list(graph.nodes)
    index = {node: i for i, node in enumerate(nodes)}
    n = len(nodes)

    k = np.ones((n, n), dtype=float) - np.eye(n)
    for u, v in graph.edges:
        i, j = index[u], index[v]
        if i != j:
            k[i, j] = k[j, i] = a

    if pos is None:
        points = np.array([circular_layout(graph)[node] for node in nodes])
    else:
        points = np.array(
            [np.asarray(pos[node], dtype=float) for node in nodes], dtype=float
        )

    for _ in range(max_iter):
        delta = points[None, :, :] - points[:, None, :]
        distance = np.linalg.norm(delta, axis=-1)
        np.fill_diagonal(distance, 1.0)
        unit = delta / distance[..., None]
        force = (k[..., None] * delta - scaling * unit).sum(axis=1)
        points = points + force * dt
        if float(np.linalg.norm(force, axis=-1).sum()) < etol:
            break
    return _as_dict(graph, _rescale(points, scale, centre))
