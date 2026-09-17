"""Tests for the self-contained marching cubes (no scikit-image / scipy).

These checks are dependency-free: the triangle table is validated against the
edge table (internal consistency across all 256 cases), and the mesher is
exercised on an analytic sphere where the answer is known.
"""

from __future__ import annotations

import numpy as np
from chimol.geometry.marching_cubes import (
    _EDGE_TABLE,
    _TRI_TABLE,
    marching_cubes,
)


def test_tri_table_consistent_with_edge_table():
    """Every case's triangles must use exactly the edges the edge table marks."""
    for case in range(256):
        row = _TRI_TABLE[case]
        used = set(int(e) for e in row if e != -1)
        expected = {b for b in range(12) if (_EDGE_TABLE[case] >> b) & 1}
        assert used == expected, f"case {case}: edges {used} != {expected}"
        # triangle count must be a whole number of triangles
        n = int(np.count_nonzero(row != -1))
        assert n % 3 == 0, f"case {case}: {n} edge refs is not a multiple of 3"


def test_all_nontrivial_cases_produce_a_surface():
    """Cases 1..254 cross the isolevel and must emit at least one triangle."""
    corners = np.array(
        [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]]
    )
    for case in range(256):
        g = np.ones((2, 2, 2), dtype=float)
        for c in range(8):
            if (case >> c) & 1:
                g[tuple(corners[c])] = 0.0  # inside == value < level
        _, faces, _ = marching_cubes(g, 0.5)
        if case in (0, 255):
            assert faces.shape[0] == 0
        else:
            assert faces.shape[0] > 0, f"case {case} produced no surface"


def test_sphere_geometry_and_outward_normals():
    """A radial density field must mesh to a sphere with outward unit normals."""
    n = 48
    xs = np.arange(n) - (n - 1) / 2.0
    x, y, z = np.meshgrid(xs, xs, xs, indexing="ij")
    r = np.sqrt(x**2 + y**2 + z**2)
    grid = 18.0 - r  # inside (value < level) is the shell exterior
    verts, faces, normals = marching_cubes(grid, 3.0)  # radius ~15
    assert verts.shape[0] > 0 and faces.shape[0] > 0

    center = np.array([(n - 1) / 2.0] * 3)
    radii = np.linalg.norm(verts - center, axis=1)
    assert abs(radii.mean() - 15.0) < 0.3
    assert radii.std() < 0.3

    # welded + connected: far fewer vertices than 3 per triangle
    assert verts.shape[0] < faces.shape[0] * 3 * 0.6
    assert int(faces.max()) < verts.shape[0]

    # gradient normals are unit and point outward (up the radial gradient)
    assert np.allclose(np.linalg.norm(normals, axis=1), 1.0, atol=1e-4)
    outward = np.sum(normals * (verts - center), axis=1) > 0
    assert outward.mean() > 0.98


def test_spacing_scales_vertices():
    n = 24
    xs = np.arange(n) - (n - 1) / 2.0
    x, y, z = np.meshgrid(xs, xs, xs, indexing="ij")
    grid = 8.0 - np.sqrt(x**2 + y**2 + z**2)
    v1, _, _ = marching_cubes(grid, 2.0, (1.0, 1.0, 1.0))
    v2, _, _ = marching_cubes(grid, 2.0, (2.0, 2.0, 2.0))
    # doubling the spacing doubles the extent
    ext1 = v1.max(0) - v1.min(0)
    ext2 = v2.max(0) - v2.min(0)
    assert np.allclose(ext2, 2.0 * ext1, rtol=1e-6)


def test_empty_when_level_out_of_range():
    grid = np.zeros((10, 10, 10))
    verts, faces, normals = marching_cubes(grid, 5.0)
    assert verts.shape[0] == 0 and faces.shape[0] == 0 and normals.shape[0] == 0
