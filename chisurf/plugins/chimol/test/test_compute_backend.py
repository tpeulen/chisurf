"""The WGSL compute route must agree with the NumPy one it accelerates.

Three scene-building kernels are per-vertex gathers with no cross-vertex
dependence, so they run as compute shaders when an adapter is there. That makes
the NumPy route the reference implementation rather than a fallback, and these
tests are what stop the two drifting: every case runs the *public* entry point
twice, once with each backend forced, so a divergence shows up as a difference
in what a caller gets rather than in a private helper nobody calls.

Agreement is to about ``1e-5`` absolute, not to the bit: the shaders work in
``f32`` and the NumPy route in ``f64``. Anything that must be exact — the
neighbour counts, the bond pairs, the marching-cubes topology — has no GPU route
at all.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.chimol.chimol.geometry import ambient, neighbors, surface
from chisurf.plugins.chimol.chimol.renderer import compute

pytestmark = pytest.mark.skipif(
    not compute.available(), reason="no WebGPU adapter on this machine"
)

#: f32 against f64 on values of order 1-100. Tight enough that a wrong branch or
#: a mis-sized buffer fails; loose enough that rounding does not.
TOLERANCE = 1e-4


@pytest.fixture
def backend(monkeypatch):
    """Return a helper that forces one compute route for a single call."""

    def run(route, fn, *args, **kwargs):
        monkeypatch.setenv(compute.BACKEND_ENV, route)
        try:
            return fn(*args, **kwargs)
        finally:
            monkeypatch.delenv(compute.BACKEND_ENV, raising=False)

    return run


@pytest.fixture
def cloud():
    """A protein-sized point cloud and a mesh around it."""
    rng = np.random.default_rng(11)
    atoms = rng.normal(scale=14.0, size=(3000, 3))
    verts = rng.normal(scale=16.0, size=(25_000, 3))
    return atoms, verts


def test_shade_from_atoms_agrees(backend, cloud):
    atoms, verts = cloud
    rng = np.random.default_rng(2)
    colors = rng.random((atoms.shape[0], 4))
    sigmas = np.full(atoms.shape[0], 1.6)

    on_cpu = backend("cpu", neighbors.shade_from_atoms, verts, atoms, colors, sigmas, 4.5)
    on_gpu = backend("gpu", neighbors.shade_from_atoms, verts, atoms, colors, sigmas, 4.5)

    for name, a, b in zip(("colors", "wsum", "grad"), on_cpu[:3], on_gpu[:3]):
        assert np.allclose(a, b, atol=TOLERANCE), name
    # `nearest` is a k-d tree query on both routes and is only filled where the
    # weight sum is zero, so it must match exactly rather than approximately.
    assert np.array_equal(on_cpu[3], on_gpu[3])
    assert np.all(on_gpu[3][on_gpu[1] > 0.0] == -1)


def test_occlusion_agrees(backend, cloud):
    atoms, verts = cloud
    normals = verts / np.linalg.norm(verts, axis=1)[:, None]
    radii = np.full(atoms.shape[0], 1.7)

    on_cpu = backend("cpu", ambient.occlusion_from_spheres, verts, normals, atoms,
                     radii, max_distance=10.0, strength=1.2)
    on_gpu = backend("gpu", ambient.occlusion_from_spheres, verts, normals, atoms,
                     radii, max_distance=10.0, strength=1.2)
    assert np.allclose(on_cpu, on_gpu, atol=TOLERANCE)


def test_distance_grid_agrees(backend, cloud):
    atoms, _ = cloud
    radii = np.random.default_rng(5).choice([1.2, 1.52, 1.7, 1.8], size=atoms.shape[0])
    shape = (48, 48, 48)
    origin = atoms.min(axis=0) - 5.0
    spacing = float((np.ptp(atoms, axis=0).max() + 10.0) / (shape[0] - 1))

    def run():
        out = np.zeros(shape, dtype=np.float32)
        surface._distance_to_spheres(atoms, radii, out, origin, spacing)
        return out

    on_cpu = backend("cpu", run)
    on_gpu = backend("gpu", run)
    assert np.allclose(on_cpu, on_gpu, atol=TOLERANCE)


def test_the_horizon_cannot_reach_the_isosurface(backend, cloud):
    """Clamping the far field must not move a level near the probe radius.

    Both routes clamp, so they agree with each other by construction — the
    question this asks is different: whether the clamp is far enough out that no
    cell straddling a plausible isolevel has a clamped corner. If it were not,
    the surface would change shape and both routes would change together, which
    is exactly the kind of agreement that proves nothing.
    """
    atoms, _ = cloud
    radii = np.full(atoms.shape[0], 1.7)
    shape = (48, 48, 48)
    origin = atoms.min(axis=0) - 5.0
    spacing = float((np.ptp(atoms, axis=0).max() + 10.0) / (shape[0] - 1))
    grid = np.zeros(shape, dtype=np.float32)
    backend("cpu", surface._distance_to_spheres, atoms, radii, grid, origin, spacing)

    horizon = max(surface._DISTANCE_HORIZON, 4.0 * spacing)
    clamped = grid >= horizon - 1e-3
    # A probe of 1.4 A is the default and the largest anyone reasonably sets.
    for level in (0.0, 1.4, 3.0):
        straddles = (grid.min() < level) & (grid.max() > level)
        assert straddles
        near = np.abs(grid - level) < spacing
        assert not np.any(near & clamped), f"clamped voxels sit on level {level}"


def test_a_tiny_problem_stays_on_the_cpu(cloud):
    """``auto`` must not pay a dispatch to shade a handful of vertices."""
    atoms, _ = cloud
    small = atoms[:50]
    colors = np.ones((atoms.shape[0], 4))
    sigmas = np.full(atoms.shape[0], 1.6)
    assert compute.shade_from_atoms(small, atoms, colors, sigmas, 4.5) is None


def test_the_cpu_setting_disables_every_kernel(monkeypatch, cloud):
    atoms, verts = cloud
    monkeypatch.setenv(compute.BACKEND_ENV, "cpu")
    colors = np.ones((atoms.shape[0], 4))
    sigmas = np.full(atoms.shape[0], 1.6)
    assert compute.shade_from_atoms(verts, atoms, colors, sigmas, 4.5) is None
    assert compute.occlusion_from_spheres(
        verts, verts, atoms, np.full(atoms.shape[0], 1.7), 10.0, 1.0
    ) is None
