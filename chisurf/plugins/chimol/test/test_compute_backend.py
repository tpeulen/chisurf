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


def test_directional_occlusion_agrees(backend, cloud):
    """Each occluder counted once, by both routes and by the same rule.

    The shader lets exactly one ray step claim each occluder —
    ``floor(along / step)`` — and the cell has to be twice the step for that
    claim to be reachable, because the light is not axis-aligned. With a cell
    equal to the step this dropped 20 vertices out of 40k: nothing in the mean,
    0.39 out of 1.0 on the vertices it hit, which is exactly the kind of
    difference an image comparison would not show and this one does.
    """
    atoms, verts = cloud
    normals = verts / np.linalg.norm(verts, axis=1)[:, None]
    radii = np.full(atoms.shape[0], 1.7)
    light = np.array([0.4, 0.4, 1.0])
    light /= np.linalg.norm(light)

    common = dict(max_distance=18.0, softness=1.6, strength=2.8)
    on_cpu = backend("cpu", ambient.directional_occlusion, verts, normals, atoms,
                     radii, light, **common)
    on_gpu = backend("gpu", ambient.directional_occlusion, verts, normals, atoms,
                     radii, light, **common)
    assert np.allclose(on_cpu, on_gpu, atol=TOLERANCE)
    assert int((on_cpu > 0.01).sum()) == int((on_gpu > 0.01).sum())


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


def test_the_distance_transform_agrees(backend):
    rng = np.random.default_rng(9)
    mask = (rng.random((72, 70, 68)) > 0.8).astype(np.uint8)
    on_cpu = backend("cpu", surface._distance_transform_edt, mask)
    on_gpu = backend("gpu", surface._distance_transform_edt, mask)
    assert np.allclose(on_cpu, on_gpu, atol=1e-5)


def test_the_marching_cubes_scan_agrees_even_though_it_is_not_used(backend):
    """Correct, tested, and deliberately not wired in.

    Finding the crossings on the GPU measured *slower* end to end than the NumPy
    pass it would replace, because the grid has to be uploaded for it. It is kept
    because the reason it loses is one round trip rather than the kernel — chain
    the distance grid, the transform and this with the grid resident and it stops
    being negative. Groundwork rots without a test.
    """
    rng = np.random.default_rng(4)
    axes = [np.linspace(-1.0, 1.0, n) for n in (64, 62, 60)]
    x, y, z = np.meshgrid(*axes, indexing="ij")
    grid = np.sqrt(x * x + y * y + z * z)
    level = 0.6

    got = backend("gpu", compute.marching_cubes_active, grid, level)
    assert got is not None

    corners = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ])
    nx, ny, nz = grid.shape
    inside = grid < level
    case = np.zeros((nx - 1, ny - 1, nz - 1), dtype=np.int64)
    for bit, (ox, oy, oz) in enumerate(corners):
        case |= inside[ox:ox + nx - 1, oy:oy + ny - 1, oz:oz + nz - 1] << bit
    want = np.flatnonzero(((case != 0) & (case != 255)).ravel())
    assert np.array_equal(got, want)


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
