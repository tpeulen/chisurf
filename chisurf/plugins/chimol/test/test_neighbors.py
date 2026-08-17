"""Tests for the radius neighbour queries and the EDT.

Each query is checked against the full distance matrix. That reference is
deliberately the dumbest possible one — no index, no cutoff, no cleverness — so
a bug in the k-d tree route cannot also be a bug in what it is compared against.
The boundary conventions differ between queries and are part of what is pinned:
:func:`count_within_radius` is strict, :func:`within_distance_mask` inclusive.
"""

from __future__ import annotations

import numpy as np

from chimol.geometry.neighbors import (
    ball_lists,
    blocked_cross_pairs,
    count_within_radius,
    cross_pairs_within,
    self_ball_lists,
    self_pairs_within,
    shade_from_atoms,
    within_distance_mask,
)
from chimol.geometry.surface import _distance_transform_edt


def test_count_within_radius_matches_brute_force():
    rng = np.random.default_rng(0)
    pts = rng.standard_normal((1500, 3)) * 20.0
    r = 4.0
    got = count_within_radius(pts, r)
    d2 = np.sum((pts[:, None, :] - pts[None, :, :]) ** 2, axis=2)
    np.fill_diagonal(d2, np.inf)
    ref = np.count_nonzero(d2 < r * r, axis=1)
    assert np.array_equal(got, ref)


def test_within_distance_mask_matches_brute_force():
    rng = np.random.default_rng(1)
    coords = rng.standard_normal((2000, 3)) * 20.0
    targets = coords[rng.choice(2000, 40, replace=False)]
    d = 5.0
    got = within_distance_mask(coords, targets, d)
    dmin2 = np.min(np.sum((coords[:, None, :] - targets[None, :, :]) ** 2, axis=2), axis=1)
    assert np.array_equal(got, dmin2 <= d * d)


def test_shade_from_atoms_matches_brute_force():
    rng = np.random.default_rng(2)
    atoms = rng.standard_normal((500, 3)) * 15.0
    colors = rng.random((500, 4))
    sigmas = np.full(500, 1.8)
    verts = atoms[rng.choice(500, 1200)] + rng.standard_normal((1200, 3))
    cutoff = float(sigmas.max() * 2.5)

    col_sum, wsum, grad, nearest = shade_from_atoms(verts, atoms, colors, sigmas, cutoff)
    mesh = np.where(wsum[:, None] > 0, col_sum / np.where(wsum > 0, wsum, 1)[:, None], colors[nearest])

    ref = np.zeros((1200, 4))
    for i in range(1200):
        diff = verts[i] - atoms
        dd = np.einsum("ij,ij->i", diff, diff)
        within = dd < cutoff * cutoff
        if within.any():
            s2 = sigmas[within] ** 2
            w = np.exp(-dd[within] / (2.0 * s2))
            ref[i] = (colors[within] * w[:, None]).sum(0) / w.sum()
        else:
            ref[i] = colors[int(np.argmin(dd))]
    assert np.allclose(mesh, ref, atol=1e-9)


def test_count_within_radius_is_strict_at_the_boundary():
    """A point at exactly the radius does not count.

    Grid-aligned input is where this stops being hypothetical -- a
    marching-cubes vertex set has exact distances in it -- and the queries below
    it were calibrated against a cell list that tested ``d2 < r2``.
    """
    pts = np.array([[0.0, 0.0, 0.0], [3.0, 0.0, 0.0], [2.999, 0.0, 0.0]])
    # The 0-1 pair sits exactly on the radius and is excluded; 0-2 and 1-2 are
    # inside it. Widen the radius by a hair and the excluded pair joins in.
    assert np.array_equal(count_within_radius(pts, 3.0), [1, 1, 2])
    assert np.array_equal(count_within_radius(pts, 3.0001), [2, 2, 2])


def test_within_distance_mask_is_inclusive_at_the_boundary():
    coords = np.array([[0.0, 0.0, 0.0], [5.0, 0.0, 0.0]])
    targets = np.array([[0.0, 0.0, 0.0]])
    assert np.array_equal(within_distance_mask(coords, targets, 5.0), [True, True])
    assert np.array_equal(within_distance_mask(coords, targets, 4.999), [True, False])


def test_self_pairs_within_matches_brute_force():
    rng = np.random.default_rng(4)
    pts = rng.standard_normal((600, 3)) * 12.0
    r = 3.0
    got = self_pairs_within(pts, r)

    d2 = np.sum((pts[:, None, :] - pts[None, :, :]) ** 2, axis=2)
    upper = np.triu(np.ones_like(d2, dtype=bool), k=1)
    ref = np.argwhere(upper & (d2 <= r * r))
    assert np.array_equal(got, ref)


def test_cross_pairs_within_matches_brute_force_and_keeps_zero_distances():
    rng = np.random.default_rng(5)
    a = rng.standard_normal((200, 3)) * 8.0
    b = np.concatenate([rng.standard_normal((150, 3)) * 8.0, a[:5]])
    r = 2.5
    i, j = cross_pairs_within(a, b, r)

    d2 = np.sum((a[:, None, :] - b[None, :, :]) ** 2, axis=2)
    ref = np.argwhere(d2 <= r * r)
    got = np.stack((i, j), axis=1)
    order = np.lexsort((got[:, 1], got[:, 0]))
    assert np.array_equal(got[order], ref)
    # The five duplicated points sit at distance zero, which a sparse-matrix
    # output type would drop as a structural zero.
    assert (d2[got[:, 0], got[:, 1]] == 0.0).sum() == 5


def test_blocked_cross_pairs_covers_every_pair_whatever_the_budget():
    rng = np.random.default_rng(6)
    a = rng.standard_normal((400, 3)) * 6.0
    b = rng.standard_normal((300, 3)) * 6.0
    r = 3.0
    expected = np.argwhere(
        np.sum((a[:, None, :] - b[None, :, :]) ** 2, axis=2) <= r * r
    )

    for budget in (17, 1000, 10_000_000):
        rows = []
        for start, _stop, i, j in blocked_cross_pairs(a, b, r, budget=budget):
            rows.append(np.stack((i + start, j), axis=1))
        got = np.concatenate(rows) if rows else np.zeros((0, 2), dtype=np.int64)
        order = np.lexsort((got[:, 1], got[:, 0]))
        assert np.array_equal(got[order], expected), f"budget={budget}"


def test_distance_transform_edt_matches_brute_force():
    rng = np.random.default_rng(3)
    fb = (rng.random((18, 16, 14)) > 0.65).astype(np.uint8)
    got = _distance_transform_edt(fb)

    # Brute force: distance from each voxel to the nearest zero voxel.
    zeros = np.argwhere(fb == 0).astype(float)
    idx = np.argwhere(np.ones_like(fb)).astype(float)
    d = np.sqrt(((idx[:, None, :] - zeros[None, :, :]) ** 2).sum(2)).min(1)
    ref = d.reshape(fb.shape)
    assert np.allclose(got, ref, atol=1e-9)


def test_pair_indices_are_intp_so_bincount_accepts_them():
    """The index dtype is ``intp``, and that is a portability requirement.

    ``np.bincount`` takes only ``intp``, and every caller here counts pairs with
    it. On a 64-bit desktop ``intp`` *is* ``int64``, so an int64 index array is
    indistinguishable -- and in WebAssembly ``intp`` is 32-bit, where the same
    array raises "cannot cast ... according to the rule 'safe'" from inside the
    cell table. It surfaced as a structure that would not load in the browser,
    with nothing in the message about integers.
    """
    import numpy as np

    from chimol.geometry.grid_pairs import (
        pairs_within,
        self_pairs_within_grid,
    )

    points = np.random.default_rng(0).random((64, 3)) * 10.0
    first, second = pairs_within(points, points, 3.0)
    assert first.dtype == np.intp and second.dtype == np.intp
    assert self_pairs_within_grid(points, 3.0).dtype == np.intp
    # The operation that would raise, run for real.
    assert np.bincount(first, minlength=len(points)).sum() == first.size


def test_ball_lists_match_query_ball_point():
    """The per-point neighbour lists the last scipy callers wanted, from the grid.

    ``get_area``, ``distance`` and ``h_bonds`` were the four remaining
    ``cKDTree.query_ball_point`` sites; in a page scipy is a 14 MB download,
    and ``get_area`` failed the measure demo with "No module named scipy".
    """
    rng = np.random.default_rng(6)
    a = rng.standard_normal((300, 3)) * 10.0
    b = rng.standard_normal((200, 3)) * 10.0
    r = 3.0
    got = ball_lists(a, b, r)
    assert len(got) == len(a)
    d = np.linalg.norm(a[:, None, :] - b[None, :, :], axis=2)
    for i in range(len(a)):
        assert np.array_equal(np.sort(got[i]), np.nonzero(d[i] <= r)[0])
    # Empty inputs keep the shape contract: one list per point, none for none.
    assert ball_lists(np.zeros((0, 3)), b, r) == []
    assert all(len(x) == 0 for x in ball_lists(a, np.zeros((0, 3)), r))


def test_self_ball_lists_exclude_the_point_itself():
    rng = np.random.default_rng(7)
    a = rng.standard_normal((250, 3)) * 10.0
    r = 3.0
    got = self_ball_lists(a, r)
    d = np.linalg.norm(a[:, None, :] - a[None, :, :], axis=2)
    np.fill_diagonal(d, np.inf)
    for i in range(len(a)):
        assert np.array_equal(np.sort(got[i]), np.nonzero(d[i] <= r)[0])
