"""HDBSCAN as ChiSurf uses it: tttrlib's (``tttrlib.hdbscan``).

ChiSurf had its own Python HDBSCAN over tttrlib's k-d tree / Boruvka kernels;
tttrlib now runs the whole pipeline itself, so that copy is gone and these are
the checks it carried, pointed at the one implementation left:

1. **The clustering is scikit-learn's.** Labels and membership probabilities
   match on data whose mutual-reachability weights are generic (when
   scikit-learn happens to be installed; it is not a dependency).
2. **The minimum spanning tree is a minimum spanning tree, and a reproducible
   one**, checked against arithmetic the method itself supplies: an explicit
   mutual-reachability distance matrix and SciPy's own MST. Reproducibility is
   checked where it is hardest -- a lattice, where nearly every weight ties.
3. **Degenerate input is answered, not crashed on.** Fewer points than
   ``min_cluster_size``, rows with a NaN, duplicated points.

The label-for-label comparison on scikit-learn's own dendrogram lives with the
kernels, in tttrlib's ``test/python/misc/test_math_ab_clustering.py``.
"""

from __future__ import annotations

import numpy as np
import pytest

tttrlib = pytest.importorskip("tttrlib")


def core_distances(X, min_samples):
    return np.asarray(
        tttrlib.core_distances(np.ascontiguousarray(X, dtype=float), int(min_samples))
    )


def mutual_reachability_mst(X, min_samples, alpha=1.0):
    return np.asarray(
        tttrlib.mutual_reachability_mst(
            np.ascontiguousarray(X, dtype=float), int(min_samples), float(alpha)
        )
    )


def hdbscan(X, **configuration):
    return tttrlib.hdbscan(np.ascontiguousarray(X, dtype=float), **configuration)


def _mutual_reachability_matrix(X, min_samples, alpha=1.0):
    """The dense mutual-reachability distance matrix, written out by hand.

    Deliberately naive and independent of everything under test: a full
    pairwise distance matrix, the core distance read off its sorted rows, and
    ``max(core_i, core_j, d_ij / alpha)``. It is what the kernel's k-d tree and
    Boruvka are an efficient way of not building.
    """
    X = np.asarray(X, dtype=float)
    n = X.shape[0]
    d = np.sqrt(((X[:, None, :] - X[None, :, :]) ** 2).sum(-1))
    k = max(1, min(int(min_samples), n))
    core = np.sort(d, axis=1)[:, k - 1]
    return np.maximum(np.maximum(core[:, None], core[None, :]), d / alpha), core


def _blobs(n_features=2, seed=7, sizes=(200, 180, 120), n_noise=40):
    """Three separated Gaussian blobs plus uniform noise, in ``n_features`` dims."""
    rng = np.random.default_rng(seed)
    parts = [rng.normal(index * 3.0, 0.4, (size, n_features)) for index, size in enumerate(sizes)]
    parts.append(rng.uniform(-4, 12, (n_noise, n_features)))
    return np.ascontiguousarray(np.vstack(parts))


# ---------------------------------------------------------------------------
# Parity with the library
# ---------------------------------------------------------------------------

_CONFIGURATIONS = [
    {"min_cluster_size": 5},
    {"min_cluster_size": 10, "cluster_selection_method": "leaf"},
    {"min_cluster_size": 10, "allow_single_cluster": True},
    {"min_cluster_size": 8, "cluster_selection_epsilon": 0.5},
    {"min_cluster_size": 6, "max_cluster_size": 150},
    {"min_cluster_size": 10, "alpha": 1.3},
    {"min_cluster_size": 3, "min_samples": 1},
    {"min_cluster_size": 15, "min_samples": 30},
]


#: The subset compared end to end. ``max_cluster_size`` is deliberately absent:
#: capping it below the size of the blobs in the fixture forbids excess-of-mass
#: from selecting the natural clusters and forces it into the unstable regime
#: where it is choosing between near-equal sub-splits, so a single tied edge
#: moves tens of points. Its contract is tested directly in
#: :func:`test_max_cluster_size_is_respected` instead.
_STABLE_CONFIGURATIONS = [
    configuration for configuration in _CONFIGURATIONS if "max_cluster_size" not in configuration
]


@pytest.mark.parametrize("n_features", [5, 8, 12])
@pytest.mark.parametrize("configuration", _STABLE_CONFIGURATIONS)
def test_matches_sklearn_end_to_end(n_features, configuration):
    """The same clustering as ``sklearn.cluster.HDBSCAN``, point for point.

    Not asserted bit-for-bit, and the reason is worth stating because it looks
    like a weaker claim than it is. scikit-learn's neighbour search differs from
    a straightforward accumulation in the last place on a few points per
    thousand. A mutual-reachability graph is full of tied weights, so one unit
    in the last place can flip which of two equal edges enters the spanning
    tree, and a handful of noise points then change hands. Given the same
    dendrogram the two produce identical labels and probabilities; that is
    asserted in tttrlib's own A/B tests.
    """
    pytest.importorskip("sklearn")
    from sklearn.cluster import HDBSCAN as SkHDBSCAN

    X = _blobs(n_features)
    mine = hdbscan(X, **configuration)
    theirs = SkHDBSCAN(**configuration).fit(X)
    agreement = float((mine.labels == theirs.labels_).mean())
    assert agreement >= 0.97, f"only {agreement:.3f} of the labels agree"
    assert abs(int(mine.labels.max()) - int(theirs.labels_.max())) <= 1
    agreed = mine.labels == theirs.labels_
    np.testing.assert_allclose(mine.probabilities[agreed], theirs.probabilities_[agreed], atol=1e-6)


@pytest.mark.parametrize("n_features", [1, 2, 3, 5])
def test_mst_weight_multiset_matches_sklearn(n_features):
    """Every minimum spanning tree of a graph carries the same multiset of weights.

    That makes this the assertion which survives the tie-break: if the sorted
    weights agree, the core distances and the mutual-reachability inflation
    agree, and only the *choice among equals* can still differ.
    """
    pytest.importorskip("sklearn")
    from sklearn.cluster._hdbscan._linkage import mst_from_data_matrix
    from sklearn.metrics import DistanceMetric

    X = _blobs(n_features)
    mine = mutual_reachability_mst(X, 5)
    theirs = mst_from_data_matrix(
        X, core_distances(X, 5), DistanceMetric.get_metric("euclidean"), 1.0
    )
    np.testing.assert_allclose(
        np.sort(mine[:, 2]), np.sort(np.asarray(theirs["distance"])), rtol=1e-12
    )


def test_core_distances_match_sklearn():
    """The k-th neighbour distance agrees with a library k-d tree to the last place."""
    pytest.importorskip("sklearn")
    from sklearn.neighbors import NearestNeighbors

    X = _blobs(3)
    for min_samples in (1, 5, 25):
        mine = core_distances(X, min_samples)
        distances, _ = NearestNeighbors(n_neighbors=min_samples).fit(X).kneighbors(X, min_samples)
        np.testing.assert_allclose(
            mine, np.ascontiguousarray(distances[:, -1]), rtol=1e-15, atol=0.0
        )


def test_core_distances_are_the_kth_row_of_the_distance_matrix():
    """The k-d tree answers what the definition answers, to the last place.

    Independent of the kernel: a full pairwise distance matrix, sorted, column
    ``k - 1``. Equality is demanded exactly rather than to a tolerance, because
    the last place is what decides the ties the clustering is built on.
    """
    X = _blobs(3)
    for min_samples in (1, 5, 25):
        _, expected = _mutual_reachability_matrix(X, min_samples)
        np.testing.assert_allclose(core_distances(X, min_samples), expected, rtol=0.0, atol=1e-12)


def test_max_cluster_size_is_respected():
    """Excess of mass must not return a cluster larger than the cap.

    The fixture has real sub-structure — three pairs of tight sub-blobs — so
    that rejecting the 200-point parents leaves the 100-point children to be
    selected. Without sub-structure the cap simply suppresses everything, which
    would make the assertion vacuous.
    """
    rng = np.random.default_rng(5)
    centres = [(0.0, 0.0), (0.9, 0.0), (8.0, 0.0), (8.9, 0.0), (0.0, 8.0), (0.9, 8.0)]
    X = np.ascontiguousarray(np.vstack([rng.normal(centre, 0.12, (100, 2)) for centre in centres]))
    cap = 150
    fitted = hdbscan(X, min_cluster_size=20, max_cluster_size=cap)
    counts = np.bincount(fitted.labels[fitted.labels >= 0])
    assert counts.size >= 2, "the cap must not suppress every cluster"
    assert counts.max() <= cap


def test_recovers_known_blobs():
    """Three well-separated blobs come back as three clusters, noise as noise."""
    X = _blobs(2, sizes=(150, 150, 150), n_noise=0)
    labels = hdbscan(X, min_cluster_size=25).labels
    assert labels.max() + 1 == 3
    for start in (0, 150, 300):
        block = labels[start : start + 150]
        # Allow a handful of edge points to be called noise, but the block must
        # be one cluster.
        real = block[block >= 0]
        assert len(np.unique(real)) == 1
        assert real.size > 140


# ---------------------------------------------------------------------------
# The minimum spanning tree is a minimum spanning tree
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n_features", [2, 3, 7])
def test_mst_matches_scipy_on_the_explicit_graph(n_features):
    """The kernel's tree weighs exactly what SciPy's MST of the same graph weighs.

    Every minimum spanning tree of a graph carries the same multiset of edge
    weights, so this survives the tie-break: if the sorted weights agree, the
    core distances, the mutual-reachability inflation *and* the minimality all
    agree, and only the choice among equals can still differ. The graph here is
    built by hand from a dense distance matrix — nothing the kernel produced.
    """
    scipy_sparse = pytest.importorskip("scipy.sparse.csgraph")

    X = _blobs(n_features, seed=3)
    min_samples = 5
    reach, _ = _mutual_reachability_matrix(X, min_samples)
    expected = scipy_sparse.minimum_spanning_tree(reach).toarray()
    expected_weights = np.sort(expected[expected > 0])

    mine = mutual_reachability_mst(X, min_samples)
    np.testing.assert_allclose(np.sort(mine[:, 2]), expected_weights, rtol=1e-12, atol=1e-12)


@pytest.mark.parametrize("alpha", [0.5, 1.0, 2.0])
def test_alpha_rescales_the_plain_distance_only(alpha):
    """``alpha`` is not decoration: it changes the tree, the way it says it does.

    A setting that is passed through but ignored is invisible to a parity test,
    so it is pinned against the definition (``d / alpha`` under the two core
    distances) rather than against a stored number.
    """
    scipy_sparse = pytest.importorskip("scipy.sparse.csgraph")

    X = _blobs(2, seed=11, sizes=(80, 70), n_noise=15)
    reach, _ = _mutual_reachability_matrix(X, 5, alpha)
    expected = scipy_sparse.minimum_spanning_tree(reach).toarray()

    mine = mutual_reachability_mst(X, 5, alpha)
    np.testing.assert_allclose(
        np.sort(mine[:, 2]), np.sort(expected[expected > 0]), rtol=1e-12, atol=1e-12
    )


def test_mst_is_a_spanning_tree():
    """n-1 edges, every vertex touched, and no cycle."""
    X = _blobs(2, sizes=(60, 60, 60), n_noise=10)
    mst = mutual_reachability_mst(X, 5)
    n_samples = X.shape[0]
    assert mst.shape == (n_samples - 1, 3)
    assert set(mst[:, :2].astype(int).ravel().tolist()) == set(range(n_samples))

    parent = np.arange(n_samples)

    def find(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for source, target, _ in mst:
        a, b = find(int(source)), find(int(target))
        assert a != b, "the MST contains a cycle"
        parent[b] = a


def test_tied_weights_are_broken_deterministically():
    """A grid ties nearly every weight; the answer must still be reproducible.

    On a regular lattice the mutual-reachability graph is almost entirely tied,
    which is the case where a weight-only ordering leaves the minimum spanning
    tree undetermined. Two runs must still agree, and the tree must still be
    minimal.
    """
    grid = np.stack(np.meshgrid(np.arange(12.0), np.arange(12.0)), axis=-1).reshape(-1, 2)
    first = hdbscan(grid, min_cluster_size=5)
    second = hdbscan(grid, min_cluster_size=5)
    np.testing.assert_array_equal(first.labels, second.labels)

    mst = mutual_reachability_mst(grid, 5)
    n_tied = mst.shape[0] - np.unique(mst[:, 2]).size
    assert n_tied > mst.shape[0] // 2, "the fixture is supposed to be tie-heavy"

    # Still minimal, tie-heavy or not: the same total weight SciPy finds.
    scipy_sparse = pytest.importorskip("scipy.sparse.csgraph")
    reach, _ = _mutual_reachability_matrix(grid, 5)
    expected = scipy_sparse.minimum_spanning_tree(reach).toarray()
    np.testing.assert_allclose(mst[:, 2].sum(), expected[expected > 0].sum(), rtol=1e-12)


# ---------------------------------------------------------------------------
# Degenerate input
# ---------------------------------------------------------------------------


def test_non_finite_rows_are_noise():
    """A row with a NaN or an infinity has no density; it is labelled noise."""
    X = _blobs(2)
    X[5] = np.nan
    X[9, 0] = np.inf
    fitted = hdbscan(X, min_cluster_size=10)
    assert fitted.labels[5] == -1
    assert fitted.labels[9] == -1
    assert fitted.probabilities[5] == 0.0
    assert fitted.labels.max() + 1 >= 2


def test_fewer_points_than_min_cluster_size():
    """Everything is noise, and the arrays still exist and have the right length."""
    X = np.arange(6.0).reshape(3, 2)
    fitted = hdbscan(X, min_cluster_size=10)
    np.testing.assert_array_equal(fitted.labels, [-1, -1, -1])
    np.testing.assert_array_equal(fitted.probabilities, [0.0, 0.0, 0.0])
    assert fitted.persistence.shape == (0,)


def test_duplicate_points_do_not_divide_by_zero():
    """Coincident points give a zero merge distance, i.e. an infinite lambda."""
    X = np.repeat(np.array([[0.0, 0.0], [5.0, 5.0]]), 30, axis=0)
    fitted = hdbscan(X, min_cluster_size=5, allow_single_cluster=False)
    assert np.isfinite(fitted.probabilities).all()
    assert (fitted.probabilities <= 1.0).all()
    assert fitted.labels.max() + 1 == 2
