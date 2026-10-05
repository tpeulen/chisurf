"""Structure clustering runs on tttrlib's UPGMA, and still gives scipy's answer.

``chisurf.core.structure.cluster.cluster`` moved from ``scipy.cluster.hierarchy``
to ``tttrlib.linkage``/``tttrlib.fcluster``. Cluster *numbers* are what a caller
keeps (they name the states), so the check is identity of the linkage matrix and
of the assignments against scipy, which stays the test oracle.

Found on the way: the scipy call passed ``preserve_input=True``, which scipy
1.18 no longer accepts -- the old path raised ``TypeError`` on the installed
scipy, so structure clustering had been broken before the port.
"""

import numpy as np
import pytest

from chisurf.core.structure.cluster import cluster

sh = pytest.importorskip("scipy.cluster.hierarchy")


@pytest.mark.parametrize("criterion,threshold", [("maxclust", 3), ("maxclust", 5000), ("distance", 1.5)])
def test_cluster_from_distances_matches_scipy(criterion, threshold):
    rng = np.random.default_rng(7)
    n = 25
    distances = rng.random(n * (n - 1) // 2) * 4.0
    distances[::5] = np.round(distances[::5])  # tied distances: merge order must still agree

    Z, clusters, assignments, _ = cluster([None] * n, threshold=threshold, criterion=criterion,
                                          distances=distances)

    z_ref = sh.linkage(distances, method="average")
    np.testing.assert_array_equal(Z, z_ref)
    np.testing.assert_array_equal(assignments, sh.fcluster(z_ref, t=threshold, criterion=criterion))
    assert sorted(i for members in clusters.values() for i in members) == list(range(n))
