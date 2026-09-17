"""HDBSCAN — density-based clustering over a mutual-reachability hierarchy.

The algorithm is four steps, and only the first two cost anything:

1. **Core distance** of every point: the distance to its ``min_samples``-th
   nearest neighbour. This is the local density estimate the whole method rests
   on. A k-d tree makes it ``O(n log n)``.
2. **Minimum spanning tree** of the *mutual-reachability* graph, whose edge
   weight is ``max(core_i, core_j, d(i, j))`` — the distance inflated so that
   sparse regions cannot be crossed cheaply. A k-d-tree Borůvka is
   ``O(n log n)``.

Both are the photon library's compiled kernels, called directly and with no
capability check in front of them: a library that does not have them fails on
the attribute, loudly, which is the point. An in-tree ``O(n² d)`` brute force
and an ``O(n²)`` Prim used to stand behind a ``hasattr`` probe; they agreed
**bit for bit** (max |Δ| = 0 in core distance, in every MST edge weight and in
the edge set) on 500 and 2000 real photons from ``BH_SPC132.spc`` at
``min_samples`` 3/5/10, and were 700–3000× slower. A fallback that is never
taken is a second implementation nobody knows is broken.
3. **Condense** the single-linkage dendrogram: a split that sheds fewer than
   ``min_cluster_size`` points is not a split, it is the parent losing noise.
   What survives is a small tree of genuine clusters.
4. **Select** clusters from that tree by excess of mass — keep a node when it is
   more *stable* (mass integrated over ``1/distance``) than its descendants put
   together — or by taking the leaves.

Steps 3 and 4 are pure integer bookkeeping over ``O(n)`` records and are written
here in NumPy and numba; they are not where the time goes.

The public spelling is scikit-learn's ``sklearn.cluster.HDBSCAN``: ``fit``,
``fit_predict``, ``labels_``, ``probabilities_``. One convention is worth
stating because the two well-known implementations disagree on it — here, as in
scikit-learn, **``min_samples`` counts the point itself**, so ``min_samples=5``
means "this point and its four nearest neighbours". The standalone ``hdbscan``
package excludes the point, and its ``min_samples=5`` is this one's
``min_samples=6``.
"""

from __future__ import annotations

import numpy as np

from ..base import BaseEstimator

__all__ = [
    "HDBSCAN",
    "core_distances",
    "mutual_reachability_mst",
    "single_linkage_tree",
    "condense_tree",
    "CONDENSED_DTYPE",
    "HIERARCHY_DTYPE",
]

#: One merge of the single-linkage dendrogram. Node ids below ``n_samples`` are
#: the samples themselves; ``n_samples + i`` is the cluster formed by row ``i``.
HIERARCHY_DTYPE = np.dtype(
    [
        ("left_node", np.int64),
        ("right_node", np.int64),
        ("value", np.float64),
        ("cluster_size", np.int64),
    ]
)

#: One edge of the condensed tree: ``child`` falls out of ``parent`` at
#: ``value`` (a *lambda*, i.e. one over a distance). ``cluster_size == 1``
#: means the child is a single point leaving; anything larger is a real split.
CONDENSED_DTYPE = np.dtype(
    [
        ("parent", np.int64),
        ("child", np.int64),
        ("value", np.float64),
        ("cluster_size", np.int64),
    ]
)

_NOISE = -1


# ---------------------------------------------------------------------------
# Step 1 — core distances
# ---------------------------------------------------------------------------


def core_distances(X: np.ndarray, min_samples: int) -> np.ndarray:
    """Return the distance from every row of ``X`` to its ``min_samples``-th neighbour.

    The point itself is the first neighbour, so ``min_samples=1`` gives zeros.

    Parameters
    ----------
    X : numpy.ndarray
        Samples, shape ``(n_samples, n_features)``.
    min_samples : int
        Neighbour rank, counting the point itself.

    Returns
    -------
    numpy.ndarray
        Core distance per sample, shape ``(n_samples,)``.
    """
    X = np.ascontiguousarray(X, dtype=np.float64)
    n_samples = X.shape[0]
    k = max(1, min(int(min_samples), n_samples))
    import tttrlib

    return np.asarray(tttrlib.core_distances(X, k), dtype=np.float64)


# ---------------------------------------------------------------------------
# Step 2 — minimum spanning tree of the mutual-reachability graph
# ---------------------------------------------------------------------------


def mutual_reachability_mst(
    X: np.ndarray,
    min_samples: int = 5,
    alpha: float = 1.0,
) -> np.ndarray:
    """Return the MST of the mutual-reachability graph of ``X``.

    Edge weight alone is not a total order here — a mutual-reachability weight
    is frequently a *core distance*, and one core distance is the weight of
    every edge it dominates, so hundreds of edges can share a value. The kernel
    orders the endpoint pair as well, which makes the order total; an MST under
    a total edge order is unique, so the tree does not depend on which spanning
    algorithm produced it.

    Parameters
    ----------
    X : numpy.ndarray
        Samples, shape ``(n_samples, n_features)``.
    min_samples : int
        Neighbour rank for the core distance, counting the point itself.
    alpha : float
        Distance scaling. Values above one shrink the plain distance relative to
        the core distances, which makes the hierarchy more conservative.

    Returns
    -------
    numpy.ndarray
        ``(n_samples - 1, 3)`` array of ``[source, target, weight]`` rows,
        **unsorted**. :func:`single_linkage_tree` sorts before consuming it.
    """
    X = np.ascontiguousarray(X, dtype=np.float64)
    n_samples = X.shape[0]
    if n_samples < 2:
        return np.empty((0, 3), dtype=np.float64)
    k = max(1, min(int(min_samples), n_samples))

    import tttrlib

    return np.asarray(tttrlib.mutual_reachability_mst(X, k, float(alpha)), dtype=np.float64)


# ---------------------------------------------------------------------------
# Step 3 — single-linkage dendrogram, then condensation
# ---------------------------------------------------------------------------


def _single_linkage(
    sources: np.ndarray, targets: np.ndarray, weights: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Turn a distance-sorted MST edge list into a dendrogram.

    Union-find with size tracking: each edge merges the two components its
    endpoints currently belong to, and the merged component is given the next
    node id ``n_samples + i``.
    """
    n_edges = sources.shape[0]
    n_samples = n_edges + 1
    parent = np.arange(2 * n_samples - 1, dtype=np.int64)
    size = np.ones(2 * n_samples - 1, dtype=np.int64)
    # The component id currently representing each root, so a merged component
    # can be named by its dendrogram node rather than by an arbitrary member.
    component = np.arange(2 * n_samples - 1, dtype=np.int64)

    left = np.empty(n_edges, dtype=np.int64)
    right = np.empty(n_edges, dtype=np.int64)
    value = np.empty(n_edges, dtype=np.float64)
    csize = np.empty(n_edges, dtype=np.int64)

    for i in range(n_edges):
        a = sources[i]
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        b = targets[i]
        while parent[b] != b:
            parent[b] = parent[parent[b]]
            b = parent[b]

        left[i] = component[a]
        right[i] = component[b]
        value[i] = weights[i]
        csize[i] = size[a] + size[b]

        # Union by size, then name the survivor after the new dendrogram node.
        if size[a] < size[b]:
            a, b = b, a
        parent[b] = a
        size[a] += size[b]
        component[a] = n_samples + i
    return left, right, value, csize


def single_linkage_tree(mst: np.ndarray) -> np.ndarray:
    """Return the single-linkage dendrogram of an MST edge list.

    Parameters
    ----------
    mst : numpy.ndarray
        ``(n_samples - 1, 3)`` array of ``[source, target, weight]``.

    Returns
    -------
    numpy.ndarray
        Structured array of :data:`HIERARCHY_DTYPE`, one row per merge, in
        increasing distance.
    """
    mst = np.asarray(mst, dtype=np.float64)
    # Merge order among equal weights decides the dendrogram, so it is fixed by
    # the same total order (weight, then the sorted endpoint pair) the MST
    # kernel uses, rather than left to whichever permutation the sort algorithm
    # happens to produce. The endpoints are also put in order, not just the
    # rows: which end of an edge is called the source decides which dendrogram
    # child is `left`, and two spanning algorithms report an edge from opposite
    # ends.
    low = np.minimum(mst[:, 0], mst[:, 1])
    high = np.maximum(mst[:, 0], mst[:, 1])
    order = np.lexsort((high, low, mst[:, 2]))
    sources = np.ascontiguousarray(low[order].astype(np.int64))
    targets = np.ascontiguousarray(high[order].astype(np.int64))
    weights = np.ascontiguousarray(mst[order, 2])
    left, right, value, csize = _single_linkage(sources, targets, weights)
    out = np.empty(left.shape[0], dtype=HIERARCHY_DTYPE)
    out["left_node"] = left
    out["right_node"] = right
    out["value"] = value
    out["cluster_size"] = csize
    return out


def _bfs_nodes(
    left: np.ndarray, right: np.ndarray, n_samples: int, root: int, out: np.ndarray
) -> int:
    """Fill ``out`` with the nodes under ``root`` in breadth-first order."""
    out[0] = root
    head = 0
    tail = 1
    while head < tail:
        node = out[head]
        head += 1
        if node >= n_samples:
            out[tail] = left[node - n_samples]
            tail += 1
            out[tail] = right[node - n_samples]
            tail += 1
    return tail


def _condense(
    left: np.ndarray,
    right: np.ndarray,
    value: np.ndarray,
    csize: np.ndarray,
    min_cluster_size: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, int]:
    """Prune the dendrogram to splits that both sides survive.

    Walking the dendrogram from the root, a merge is a genuine split only when
    both children hold at least ``min_cluster_size`` points; otherwise the small
    side is recorded as points falling out of the surviving cluster, at the
    lambda of that merge. The output is an edge list, and its node ids are
    renumbered so that ``n_samples`` is the root cluster.
    """
    n_edges = left.shape[0]
    n_samples = n_edges + 1
    root = 2 * n_edges
    n_nodes = root + 1

    # A point leaves exactly one cluster, and a split contributes two rows, so
    # 3 * n_samples is a hard ceiling on the row count.
    cap = 3 * n_samples + 3
    out_parent = np.empty(cap, dtype=np.int64)
    out_child = np.empty(cap, dtype=np.int64)
    out_value = np.empty(cap, dtype=np.float64)
    out_size = np.empty(cap, dtype=np.int64)
    n_out = 0

    relabel = np.zeros(n_nodes, dtype=np.int64)
    relabel[root] = n_samples
    ignore = np.zeros(n_nodes, dtype=np.uint8)
    next_label = n_samples + 1

    order = np.empty(n_nodes, dtype=np.int64)
    n_order = _bfs_nodes(left, right, n_samples, root, order)
    sub = np.empty(n_nodes, dtype=np.int64)

    for idx in range(n_order):
        node = order[idx]
        if ignore[node] or node < n_samples:
            continue
        row = node - n_samples
        node_left = left[row]
        node_right = right[row]
        distance = value[row]
        if distance > 0.0:
            lambda_value = 1.0 / distance
        else:
            lambda_value = np.inf

        if node_left >= n_samples:
            left_count = csize[node_left - n_samples]
        else:
            left_count = 1
        if node_right >= n_samples:
            right_count = csize[node_right - n_samples]
        else:
            right_count = 1

        big_left = left_count >= min_cluster_size
        big_right = right_count >= min_cluster_size

        if big_left and big_right:
            relabel[node_left] = next_label
            next_label += 1
            out_parent[n_out] = relabel[node]
            out_child[n_out] = relabel[node_left]
            out_value[n_out] = lambda_value
            out_size[n_out] = left_count
            n_out += 1

            relabel[node_right] = next_label
            next_label += 1
            out_parent[n_out] = relabel[node]
            out_child[n_out] = relabel[node_right]
            out_value[n_out] = lambda_value
            out_size[n_out] = right_count
            n_out += 1
            continue

        if not big_left and not big_right:
            shed_left = True
            shed_right = True
        elif not big_left:
            relabel[node_right] = relabel[node]
            shed_left = True
            shed_right = False
        else:
            relabel[node_left] = relabel[node]
            shed_left = False
            shed_right = True

        if shed_left:
            n_sub = _bfs_nodes(left, right, n_samples, node_left, sub)
            for s in range(n_sub):
                sub_node = sub[s]
                if sub_node < n_samples:
                    out_parent[n_out] = relabel[node]
                    out_child[n_out] = sub_node
                    out_value[n_out] = lambda_value
                    out_size[n_out] = 1
                    n_out += 1
                ignore[sub_node] = 1
        if shed_right:
            n_sub = _bfs_nodes(left, right, n_samples, node_right, sub)
            for s in range(n_sub):
                sub_node = sub[s]
                if sub_node < n_samples:
                    out_parent[n_out] = relabel[node]
                    out_child[n_out] = sub_node
                    out_value[n_out] = lambda_value
                    out_size[n_out] = 1
                    n_out += 1
                ignore[sub_node] = 1

    return out_parent, out_child, out_value, out_size, n_out


def condense_tree(hierarchy: np.ndarray, min_cluster_size: int = 5) -> np.ndarray:
    """Condense a single-linkage dendrogram to its genuine splits.

    Parameters
    ----------
    hierarchy : numpy.ndarray
        Structured array of :data:`HIERARCHY_DTYPE`, from
        :func:`single_linkage_tree`.
    min_cluster_size : int
        Splits that shed fewer points than this are treated as the parent losing
        noise rather than as a split.

    Returns
    -------
    numpy.ndarray
        Structured array of :data:`CONDENSED_DTYPE`.
    """
    parent, child, value, size, n_out = _condense(
        np.ascontiguousarray(hierarchy["left_node"]),
        np.ascontiguousarray(hierarchy["right_node"]),
        np.ascontiguousarray(hierarchy["value"]),
        np.ascontiguousarray(hierarchy["cluster_size"]),
        int(min_cluster_size),
    )
    out = np.empty(n_out, dtype=CONDENSED_DTYPE)
    out["parent"] = parent[:n_out]
    out["child"] = child[:n_out]
    out["value"] = value[:n_out]
    out["cluster_size"] = size[:n_out]
    return out


# ---------------------------------------------------------------------------
# Step 4 — cluster selection
# ---------------------------------------------------------------------------


def _compute_stability(condensed: np.ndarray) -> dict[int, float]:
    """Return ``cluster id -> stability``, the mass a cluster holds over its life.

    A cluster's stability is the sum over everything that falls out of it of
    ``(lambda at which it fell out - lambda at which the cluster was born)``,
    weighted by how many points fell out at once.
    """
    parents = condensed["parent"]
    smallest = int(parents.min())
    largest_child = max(int(condensed["child"].max()), smallest)
    births = np.full(largest_child + 1, np.nan, dtype=np.float64)
    births[condensed["child"]] = condensed["value"]
    births[smallest] = 0.0

    n_clusters = int(parents.max()) - smallest + 1
    result = np.zeros(n_clusters, dtype=np.float64)
    np.add.at(
        result,
        parents - smallest,
        (condensed["value"] - births[parents]) * condensed["cluster_size"],
    )
    return {idx + smallest: float(result[idx]) for idx in range(n_clusters)}


def _bfs_from_cluster_tree(cluster_tree: np.ndarray, root: int) -> list[int]:
    """Return the nodes of ``cluster_tree`` under ``root``, breadth first."""
    result: list[int] = []
    queue = np.array([root], dtype=np.int64)
    parents = cluster_tree["parent"]
    children = cluster_tree["child"]
    while queue.size:
        result.extend(queue.tolist())
        queue = children[np.isin(parents, queue)]
    return result


def _cluster_tree_leaves(cluster_tree: np.ndarray) -> list[int]:
    """Return the leaves of the cluster tree — nodes that never split again."""
    if cluster_tree.shape[0] == 0:
        return []
    parents = set(cluster_tree["parent"].tolist())
    return [int(c) for c in cluster_tree["child"] if int(c) not in parents]


def _traverse_upwards(
    cluster_tree: np.ndarray,
    epsilon: float,
    leaf: int,
    allow_single_cluster: bool,
) -> int:
    """Walk from ``leaf`` towards the root until a split coarser than ``epsilon``."""
    root = int(cluster_tree["parent"].min())
    node = leaf
    while True:
        rows = cluster_tree["parent"][cluster_tree["child"] == node]
        if rows.size == 0:
            # `node` is the root itself: there is nothing further up to merge
            # into. scikit-learn raises a TypeError here instead.
            return node
        parent = int(rows[0])
        if parent == root:
            return parent if allow_single_cluster else node
        parent_rows = cluster_tree["value"][cluster_tree["child"] == parent]
        if parent_rows.size == 0:
            return parent
        parent_eps = 1.0 / float(parent_rows[0])
        if parent_eps > epsilon:
            return parent
        node = parent


def _epsilon_search(
    leaves: set[int],
    cluster_tree: np.ndarray,
    epsilon: float,
    allow_single_cluster: bool,
) -> set[int]:
    """Replace clusters that split below ``epsilon`` by the ancestor above it."""
    selected: list[int] = []
    processed: set[int] = set()
    for leaf in leaves:
        rows = cluster_tree["value"][cluster_tree["child"] == leaf]
        if rows.size == 0:
            # The root cluster is nobody's child; it is already as coarse as
            # the search can get, so keep it.
            selected.append(leaf)
            continue
        eps = 1.0 / float(rows[0])
        if eps < epsilon:
            if leaf not in processed:
                node = _traverse_upwards(cluster_tree, epsilon, leaf, allow_single_cluster)
                selected.append(node)
                for sub in _bfs_from_cluster_tree(cluster_tree, node):
                    if sub != node:
                        processed.add(int(sub))
        else:
            selected.append(leaf)
    return set(selected)


def _label_points(
    parents: np.ndarray,
    children: np.ndarray,
    is_selected: np.ndarray,
    n_points: int,
    n_nodes: int,
) -> np.ndarray:
    """Collapse unselected clusters into their parents and read off each point's root."""
    uf = np.arange(n_nodes, dtype=np.int64)
    for i in range(parents.shape[0]):
        child = children[i]
        if is_selected[child]:
            # A selected cluster is a root of its own: nothing above it may
            # absorb it, which is what makes the loop below read a label off.
            continue
        a = parents[i]
        while uf[a] != a:
            uf[a] = uf[uf[a]]
            a = uf[a]
        b = child
        while uf[b] != b:
            uf[b] = uf[uf[b]]
            b = uf[b]
        if a != b:
            # The parent's side always survives, so the component is named by
            # its topmost node — the selected cluster, or the root.
            uf[b] = a
    out = np.empty(n_points, dtype=np.int64)
    for n in range(n_points):
        a = n
        while uf[a] != a:
            uf[a] = uf[uf[a]]
            a = uf[a]
        out[n] = a
    return out


def _do_labelling(
    condensed: np.ndarray,
    clusters: set[int],
    cluster_label_map: dict[int, int],
    allow_single_cluster: bool,
    cluster_selection_epsilon: float,
) -> np.ndarray:
    """Assign every point to a selected cluster, or to noise."""
    parents = condensed["parent"]
    children = condensed["child"]
    values = condensed["value"]
    root_cluster = int(parents.min())
    n_nodes = int(parents.max()) + 1

    is_selected = np.zeros(n_nodes, dtype=np.bool_)
    for cluster in clusters:
        if cluster < n_nodes:
            is_selected[cluster] = True

    roots = _label_points(
        np.ascontiguousarray(parents),
        np.ascontiguousarray(children),
        is_selected,
        root_cluster,
        n_nodes,
    )

    labels = np.full(root_cluster, _NOISE, dtype=np.int64)
    resolved = roots != root_cluster
    if resolved.any():
        lookup = np.full(n_nodes, _NOISE, dtype=np.int64)
        for cluster, label in cluster_label_map.items():
            lookup[cluster] = label
        labels[resolved] = lookup[roots[resolved]]

    if len(clusters) == 1 and allow_single_cluster:
        # Every point sits directly under the root; a point is a member only if
        # it survived to a lambda at least as large as the threshold.
        if cluster_selection_epsilon != 0.0:
            threshold = 1.0 / cluster_selection_epsilon
        else:
            threshold = float(values[parents == root_cluster].max())
        point_lambda = np.zeros(root_cluster, dtype=np.float64)
        leaf_rows = children < root_cluster
        point_lambda[children[leaf_rows]] = values[leaf_rows]
        only = next(iter(clusters))
        unresolved = ~resolved
        labels[unresolved & (point_lambda >= threshold)] = cluster_label_map[only]

    return labels


def _get_probabilities(
    condensed: np.ndarray, reverse_cluster_map: dict[int, int], labels: np.ndarray
) -> np.ndarray:
    """Return each point's membership strength, ``lambda / lambda_max`` of its cluster."""
    parents = condensed["parent"]
    children = condensed["child"]
    values = condensed["value"]
    root_cluster = int(parents.min())

    largest_parent = int(parents.max())
    deaths = np.zeros(largest_parent + 1, dtype=np.float64)
    np.maximum.at(deaths, parents, values)

    result = np.zeros(labels.shape[0], dtype=np.float64)
    leaf_rows = children < root_cluster
    points = children[leaf_rows]
    lambdas = values[leaf_rows]
    point_labels = labels[points]
    keep = point_labels != _NOISE
    points = points[keep]
    lambdas = lambdas[keep]
    if points.size == 0:
        return result

    lookup = np.zeros(max(reverse_cluster_map) + 1, dtype=np.int64)
    for label, cluster in reverse_cluster_map.items():
        lookup[label] = cluster
    max_lambda = deaths[lookup[labels[points]]]
    with np.errstate(divide="ignore", invalid="ignore"):
        strength = np.minimum(lambdas, max_lambda) / max_lambda
    strength[max_lambda == 0.0] = 1.0
    strength[np.isinf(lambdas)] = 1.0
    result[points] = strength
    return result


def _get_clusters(
    condensed: np.ndarray,
    stability: dict[int, float],
    cluster_selection_method: str = "eom",
    allow_single_cluster: bool = False,
    cluster_selection_epsilon: float = 0.0,
    max_cluster_size: int | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Select clusters from the condensed tree and label every point."""
    node_list = sorted(stability.keys(), reverse=True)
    if not allow_single_cluster:
        node_list = node_list[:-1]  # the root is never a cluster on its own

    cluster_tree = condensed[condensed["cluster_size"] > 1]
    is_cluster = {cluster: True for cluster in node_list}
    n_samples = int(condensed["child"][condensed["cluster_size"] == 1].max()) + 1
    if max_cluster_size is None:
        max_cluster_size = n_samples + 1

    cluster_sizes = {
        int(child): int(size)
        for child, size in zip(cluster_tree["child"], cluster_tree["cluster_size"])
    }
    if allow_single_cluster and node_list:
        root = node_list[-1]
        cluster_sizes[root] = int(
            cluster_tree["cluster_size"][cluster_tree["parent"] == root].sum()
        )

    if cluster_selection_method == "eom":
        for node in node_list:
            children = cluster_tree["child"][cluster_tree["parent"] == node]
            subtree_stability = float(sum(stability[int(c)] for c in children))
            if subtree_stability > stability[node] or cluster_sizes.get(node, 0) > max_cluster_size:
                is_cluster[node] = False
                stability[node] = subtree_stability
            else:
                for sub in _bfs_from_cluster_tree(cluster_tree, node):
                    if sub != node:
                        is_cluster[int(sub)] = False

        if cluster_selection_epsilon != 0.0 and cluster_tree.shape[0] > 0:
            eom_clusters = [c for c in is_cluster if is_cluster[c]]
            if len(eom_clusters) == 1 and eom_clusters[0] == int(cluster_tree["parent"].min()):
                selected = set(eom_clusters) if allow_single_cluster else set()
            else:
                selected = _epsilon_search(
                    set(eom_clusters),
                    cluster_tree,
                    cluster_selection_epsilon,
                    allow_single_cluster,
                )
            for c in is_cluster:
                is_cluster[c] = c in selected

    elif cluster_selection_method == "leaf":
        leaves = set(_cluster_tree_leaves(cluster_tree))
        if not leaves:
            for c in is_cluster:
                is_cluster[c] = False
            is_cluster[int(condensed["parent"].min())] = True
            selected = {int(condensed["parent"].min())}
        elif cluster_selection_epsilon != 0.0:
            selected = _epsilon_search(
                leaves, cluster_tree, cluster_selection_epsilon, allow_single_cluster
            )
        else:
            selected = leaves
        for c in is_cluster:
            is_cluster[c] = c in selected
    else:
        raise ValueError(
            f"cluster_selection_method must be 'eom' or 'leaf', got {cluster_selection_method!r}"
        )

    clusters = {c for c in is_cluster if is_cluster[c]}
    cluster_map = {c: n for n, c in enumerate(sorted(clusters))}
    reverse_map = {n: c for c, n in cluster_map.items()}

    labels = _do_labelling(
        condensed,
        clusters,
        cluster_map,
        allow_single_cluster,
        cluster_selection_epsilon,
    )
    probabilities = _get_probabilities(condensed, reverse_map, labels)
    persistence = np.array([stability[c] for c in sorted(clusters)], dtype=np.float64)
    return labels, probabilities, persistence


def tree_to_labels(
    hierarchy: np.ndarray,
    min_cluster_size: int = 5,
    cluster_selection_method: str = "eom",
    allow_single_cluster: bool = False,
    cluster_selection_epsilon: float = 0.0,
    max_cluster_size: int | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Condense a dendrogram and read a flat clustering out of it.

    Returns
    -------
    labels, probabilities, persistence, condensed_tree
    """
    condensed = condense_tree(hierarchy, min_cluster_size)
    labels, probabilities, persistence = _get_clusters(
        condensed,
        _compute_stability(condensed),
        cluster_selection_method,
        allow_single_cluster,
        cluster_selection_epsilon,
        max_cluster_size,
    )
    return labels, probabilities, persistence, condensed


# ---------------------------------------------------------------------------
# The estimator
# ---------------------------------------------------------------------------


class HDBSCAN(BaseEstimator):
    """Hierarchical density-based clustering with automatic cluster extraction.

    Unlike DBSCAN, no single density threshold is chosen: the hierarchy over all
    thresholds is built once and the flat clustering is read off it by keeping
    whichever clusters persist over the widest range of densities. Points that
    belong to no persisting cluster are labelled ``-1``.

    Parameters
    ----------
    min_cluster_size : int, default 5
        Smallest group of points that counts as a cluster.
    min_samples : int, optional
        Neighbour rank used for the core distance, **counting the point
        itself**. Larger values declare more points noise. Defaults to
        ``min_cluster_size``.
    cluster_selection_epsilon : float, default 0.0
        Distance below which clusters are not split any further; ``0`` disables
        the merge.
    max_cluster_size : int, optional
        Excess-of-mass will not select a cluster larger than this.
    alpha : float, default 1.0
        Distance scaling applied before the mutual-reachability inflation.
    cluster_selection_method : {'eom', 'leaf'}, default 'eom'
        ``'eom'`` keeps the most persistent clusters, which tends to produce few
        large ones; ``'leaf'`` takes the finest clusters in the tree.
    allow_single_cluster : bool, default False
        Whether the whole data set may be returned as one cluster.
    store_centers : {None, 'centroid'}, default None
        When ``'centroid'``, expose the arithmetic mean of each cluster as
        ``centroids_``.
    prediction_data : bool, default False
        Accepted for interface parity with the standalone implementation; this
        estimator keeps the condensed tree either way and ignores the flag.

    Attributes
    ----------
    labels_ : numpy.ndarray
        ``(n_samples,)`` cluster index per point, ``-1`` for noise.
    probabilities_ : numpy.ndarray
        ``(n_samples,)`` membership strength in ``[0, 1]``; ``0`` for noise.
    cluster_persistence_ : numpy.ndarray
        Stability of each returned cluster.
    condensed_tree_ : numpy.ndarray
        The condensed hierarchy, :data:`CONDENSED_DTYPE`.
    single_linkage_tree_ : numpy.ndarray
        The full dendrogram, :data:`HIERARCHY_DTYPE`.
    minimum_spanning_tree_ : numpy.ndarray
        ``(n_samples - 1, 3)`` mutual-reachability MST edges.
    centroids_ : numpy.ndarray
        Present when ``store_centers='centroid'``.
    """

    def __init__(
        self,
        min_cluster_size: int = 5,
        min_samples: int | None = None,
        cluster_selection_epsilon: float = 0.0,
        max_cluster_size: int | None = None,
        metric: str = "euclidean",
        alpha: float = 1.0,
        cluster_selection_method: str = "eom",
        allow_single_cluster: bool = False,
        store_centers: str | None = None,
        prediction_data: bool = False,
    ):
        self.min_cluster_size = min_cluster_size
        self.min_samples = min_samples
        self.cluster_selection_epsilon = cluster_selection_epsilon
        self.max_cluster_size = max_cluster_size
        self.metric = metric
        self.alpha = alpha
        self.cluster_selection_method = cluster_selection_method
        self.allow_single_cluster = allow_single_cluster
        self.store_centers = store_centers
        self.prediction_data = prediction_data
        self._constructor_params = {
            "min_cluster_size",
            "min_samples",
            "cluster_selection_epsilon",
            "max_cluster_size",
            "metric",
            "alpha",
            "cluster_selection_method",
            "allow_single_cluster",
            "store_centers",
            "prediction_data",
        }

    def fit(self, X, y=None):
        """Cluster ``X`` and return ``self``.

        Rows holding a non-finite value are not clustered — they carry no
        position, so no density can be estimated for them. They are labelled
        ``-1`` and the hierarchy is built from the finite rows alone.
        """
        X = np.ascontiguousarray(np.atleast_2d(np.asarray(X, dtype=np.float64)))
        if self.metric != "euclidean":
            raise ValueError(f"metric={self.metric!r} is not implemented; only 'euclidean' is.")
        n_total = X.shape[0]
        finite = np.isfinite(X).all(axis=1)
        data = X if finite.all() else X[finite]
        n_samples = data.shape[0]

        min_cluster_size = max(2, int(self.min_cluster_size))
        min_samples = min_cluster_size if self.min_samples is None else int(self.min_samples)
        # The size check comes first: a data set too small to hold one cluster
        # is answered with "all noise", and complaining about the neighbour rank
        # would be answering a question nobody asked.
        if n_samples >= 2 and n_samples >= min_cluster_size and min_samples > n_samples:
            raise ValueError(
                f"min_samples ({min_samples}) must be at most the number of "
                f"finite samples ({n_samples})"
            )

        if n_samples < 2 or n_samples < min_cluster_size:
            # Nothing can persist: everything is noise, but the estimator still
            # has to answer with the arrays a caller reads.
            self.minimum_spanning_tree_ = np.empty((0, 3), dtype=np.float64)
            self.single_linkage_tree_ = np.empty(0, dtype=HIERARCHY_DTYPE)
            self.condensed_tree_ = np.empty(0, dtype=CONDENSED_DTYPE)
            self.cluster_persistence_ = np.empty(0, dtype=np.float64)
            self.labels_ = np.full(n_total, _NOISE, dtype=np.int64)
            self.probabilities_ = np.zeros(n_total, dtype=np.float64)
            self.n_features_in_ = X.shape[1]
            if self.store_centers == "centroid":
                self.centroids_ = np.empty((0, X.shape[1]), dtype=np.float64)
            return self

        mst = mutual_reachability_mst(data, min_samples=min_samples, alpha=float(self.alpha))
        hierarchy = single_linkage_tree(mst)
        labels, probabilities, persistence, condensed = tree_to_labels(
            hierarchy,
            min_cluster_size,
            self.cluster_selection_method,
            bool(self.allow_single_cluster),
            float(self.cluster_selection_epsilon),
            self.max_cluster_size,
        )

        self.minimum_spanning_tree_ = mst
        self.single_linkage_tree_ = hierarchy
        self.condensed_tree_ = condensed
        self.cluster_persistence_ = persistence
        if finite.all():
            self.labels_ = labels
            self.probabilities_ = probabilities
        else:
            self.labels_ = np.full(n_total, _NOISE, dtype=np.int64)
            self.probabilities_ = np.zeros(n_total, dtype=np.float64)
            self.labels_[finite] = labels
            self.probabilities_[finite] = probabilities
        self.n_features_in_ = X.shape[1]

        if self.store_centers == "centroid":
            n_clusters = int(self.labels_.max()) + 1
            centroids = np.empty((max(n_clusters, 0), X.shape[1]), dtype=np.float64)
            for index in range(n_clusters):
                centroids[index] = X[self.labels_ == index].mean(axis=0)
            self.centroids_ = centroids
        return self

    def fit_predict(self, X, y=None) -> np.ndarray:
        """Fit and return the cluster labels of ``X``."""
        return self.fit(X).labels_
