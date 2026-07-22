"""Tests for the numba cell-list neighbour queries and the EDT (no scipy).

Each kernel is checked against a brute-force NumPy reference, so the suite has no
scipy / scikit-image dependency.
"""

from __future__ import annotations

import numpy as np

from chisurf.plugins.chimol.chimol.geometry.neighbors import (
    count_within_radius,
    shade_from_atoms,
    within_distance_mask,
)
from chisurf.plugins.chimol.chimol.geometry.surface import _distance_transform_edt


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
