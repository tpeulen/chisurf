"""Benchmark for the in-tree HDBSCAN (:mod:`chisurf.core.ml.cluster`).

Measures the wall time of a complete clustering — core distances, the
mutual-reachability spanning tree, the condensed tree and the excess-of-mass
selection — against the two packages this replaced, wherever they happen to be
installed. Neither is a dependency any more.

Three things decide the number and none of them is the estimator's Python:

``n``
    The sample count. The spanning tree is where the time goes, and the two
    kernels available for it scale differently — a k-d-tree Borůvka in
    ``O(n log n)`` while the tree prunes, Prim in ``O(n²)`` when it does not.

``d``
    The number of features, which decides whether the tree prunes at all. Past
    about ten dimensions a bounding box overlaps the query ball in nearly every
    direction, the tree visits most of itself per query, and the plain scan
    wins. The crossover is the reason both kernels exist.

``min_samples``
    The neighbour rank for the core distance. Larger values make the core
    distances larger, which *weakens* the pruning bound — a slower run, not
    just a different answer.

The comparison is only meaningful if the answers agree, so the number of
clusters found is reported next to every time. Note the convention difference:
``min_samples`` counts the point itself here and in scikit-learn, and does not
in the standalone ``hdbscan`` package, so the reference is called with one
fewer.

Run standalone for a markdown table to paste into
``docs/development/benchmarks.md``::

    PYTHONPATH=. python test/benchmarks/benchmark_clustering.py

or as a (slow) regression test::

    pytest test/benchmarks/benchmark_clustering.py -q -m slow
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from chisurf.core.ml.cluster import HDBSCAN
from chisurf.core.ml.cluster import _hdbscan as _kernel

try:  # optional external reference, not a dependency
    import hdbscan as _reference_package
except ImportError:  # pragma: no cover - depends on the environment
    _reference_package = None

try:  # optional external reference, not a dependency
    from sklearn.cluster import HDBSCAN as _ReferenceSklearn
except ImportError:  # pragma: no cover - depends on the environment
    _ReferenceSklearn = None

#: ``(n_samples, n_features)`` per case. Two and three features are the shape a
#: burst feature space actually has; eight and sixteen are there because that is
#: where the k-d tree stops paying and the dispatch has to be right.
CASES = [
    (5_000, 2),
    (20_000, 2),
    (100_000, 2),
    (20_000, 3),
    (100_000, 3),
    (20_000, 8),
    (20_000, 16),
]

MIN_CLUSTER_SIZE = 15
MIN_SAMPLES = 5


def make_blobs(n_samples, n_features, seed=0):
    """Return three Gaussian blobs and a quarter of uniform noise.

    The noise is the point: on clean blobs every implementation is fast, and it
    is the points that belong to nothing that make the spanning tree work.
    """
    rng = np.random.default_rng(seed)
    which = rng.integers(0, 4, n_samples)
    noise = rng.uniform(-4, 12, (n_samples, n_features))
    signal = rng.normal(0, 0.4, (n_samples, n_features)) + 3.0 * which[:, None]
    return np.ascontiguousarray(np.where((which == 3)[:, None], noise, signal))


def _time(function, data, repeat=1):
    """Return ``(best seconds, result)`` over ``repeat`` runs."""
    best, result = np.inf, None
    for _ in range(repeat):
        start = time.perf_counter()
        result = function(data)
        best = min(best, time.perf_counter() - start)
    return best, result


def _n_clusters(labels):
    """Number of clusters in a labelling, noise excluded."""
    return int(labels.max()) + 1


def run_case(n_samples, n_features, compiled=True):
    """Return one row per implementation for one case."""
    data = make_blobs(n_samples, n_features)
    rows = []

    _kernel._KERNEL_CACHE.clear()
    if not compiled:
        _kernel._KERNEL_CACHE.append(None)
    try:
        seconds, fitted = _time(
            lambda x: HDBSCAN(
                min_cluster_size=MIN_CLUSTER_SIZE, min_samples=MIN_SAMPLES
            ).fit(x),
            data,
            repeat=2,
        )
    finally:
        _kernel._KERNEL_CACHE.clear()
    rows.append(
        (
            "chisurf" if compiled else "chisurf (no compiled kernel)",
            seconds,
            _n_clusters(fitted.labels_),
        )
    )

    if _reference_package is not None and compiled:
        seconds, fitted = _time(
            lambda x: _reference_package.HDBSCAN(
                min_cluster_size=MIN_CLUSTER_SIZE,
                min_samples=MIN_SAMPLES - 1,
                core_dist_n_jobs=-1,
            ).fit(x),
            data,
        )
        rows.append(("hdbscan", seconds, _n_clusters(fitted.labels_)))

    if _ReferenceSklearn is not None and compiled:
        seconds, fitted = _time(
            lambda x: _ReferenceSklearn(
                min_cluster_size=MIN_CLUSTER_SIZE, min_samples=MIN_SAMPLES
            ).fit(x),
            data,
        )
        rows.append(("scikit-learn", seconds, _n_clusters(fitted.labels_)))

    return rows


def main():
    """Print the markdown table for ``docs/development/benchmarks.md``."""
    # One warm run so numba's compilation does not land in the first case.
    HDBSCAN(min_cluster_size=MIN_CLUSTER_SIZE).fit(make_blobs(400, 3))

    print("| case | implementation | fit [s] | clusters |")
    print("| --- | --- | ---: | ---: |")
    for n_samples, n_features in CASES:
        label = f"n={n_samples:,} d={n_features}"
        for name, seconds, clusters in run_case(n_samples, n_features):
            print(f"| {label} | {name} | {seconds:.3f} | {clusters} |")
        if n_samples <= 20_000:
            for name, seconds, clusters in run_case(
                n_samples, n_features, compiled=False
            ):
                print(f"| {label} | {name} | {seconds:.3f} | {clusters} |")


@pytest.mark.slow
def test_compiled_kernel_is_not_slower_than_the_fallback():
    """The compiled kernel must earn its existence on the shape it is for.

    Two or three features is what a burst feature space has, and it is where the
    k-d tree prunes best. If the compiled path is not clearly ahead of the
    in-tree fallback there, something has stopped working — most likely OpenMP,
    which fails to be found on some toolchains and turns every parallel kernel
    in the compiled library serial without failing the build.
    """
    if _kernel._compiled_kernel() is None:
        pytest.skip("the compiled clustering kernel is not available")
    data = make_blobs(20_000, 3)

    _kernel._KERNEL_CACHE.clear()
    compiled, first = _time(
        lambda x: HDBSCAN(min_cluster_size=MIN_CLUSTER_SIZE, min_samples=MIN_SAMPLES).fit(x),
        data,
    )
    _kernel._KERNEL_CACHE.clear()
    _kernel._KERNEL_CACHE.append(None)
    try:
        fallback, second = _time(
            lambda x: HDBSCAN(
                min_cluster_size=MIN_CLUSTER_SIZE, min_samples=MIN_SAMPLES
            ).fit(x),
            data,
        )
    finally:
        _kernel._KERNEL_CACHE.clear()

    # Same answer, whichever kernel ran: that is the invariant the total edge
    # order and the disabled floating-point contraction exist to guarantee.
    np.testing.assert_array_equal(first.labels_, second.labels_)
    assert compiled < fallback, (
        f"the compiled kernel ({compiled:.3f} s) is not faster than the in-tree "
        f"fallback ({fallback:.3f} s)"
    )


if __name__ == "__main__":
    main()
