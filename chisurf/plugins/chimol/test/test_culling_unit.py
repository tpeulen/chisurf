"""Deterministic unit tests for the off-frustum cull logic.

The two methods under test (`_geometry_bounds`, `_cull_clip`) are pure numpy
and need no GPU, so they are built on a renderer instance created without
its (adapter-touching) constructor. The trick is the same one the probe uses:
prove the *decision* is right, which is where a wrong cull would hide.
"""

import numpy as np
from chimol.core.camera.view_state import pack_view_state
from chimol.render.pack import PackedGeometry
from chimol.render.wgpu_backend import WgpuMeshRenderer


def _renderer():
    r = object.__new__(WgpuMeshRenderer)
    r._bounds_cache = {}
    return r


def _view():
    # camera at distance 20 along +z, looking at origin; fov 30deg
    vp = pack_view_state(np.eye(3), 20.0, (0.0, 0.0, 0.0), 0.1, 200.0, fov=30.0)
    # mvp: proj @ view, where view places eye at z=+20 looking toward origin
    vp = np.asarray(vp, dtype=float)
    # use the engine's own projection/view helpers via a real render for the matrix
    # is overkill; instead build a perspective matrix pointing +z at origin.
    import chimol.render.wgpu_backend as W
    from chimol.core.camera.view_state import unpack_view_state

    state = unpack_view_state(list(vp))
    view = W.view_matrix(state.rotation, state.target, state.distance, state.shift)
    proj = W.perspective(state.fov, 1.0, max(state.near, 1e-3), state.far)
    return proj @ view


def _geom(cx, cy, cz, n=10, kind="points"):
    pos = np.zeros((n, 3), dtype=np.float32)
    pos[:, 0] = cx
    pos[:, 1] = cy
    pos[:, 2] = cz
    radii = np.full((n, 1), 0.4, dtype=np.float32)
    return PackedGeometry(kind=kind, positions=pos, radii=radii, colors=None)


def test_on_screen_not_culled():
    r, mvp = _renderer(), _view()
    assert r._cull_clip(_geom(0.0, 0.0, 0.0), mvp) is False, "object at origin is culled"


def test_far_off_to_the_right_is_culled():
    r, mvp = _renderer(), _view()
    # far off to +x > 10: the 30-deg fov at distance 20 puts the viewport edge
    # near x=~5 at the far side; x=30 is comfortably outside and in front.
    assert r._cull_clip(_geom(30.0, 0.0, 0.0), mvp) is True, "object fully right of view"


def test_behind_camera_is_kept():
    r, mvp = _renderer(), _view()
    # camera looks from z=+20 toward origin; an object very far behind the
    # camera (z negative and large) has corners crossing the near plane ->
    # must NOT be culled (the conservative guard).
    assert r._cull_clip(_geom(0.0, 0.0, -50.0), mvp) is False, "camera-plane crossing culled"


def test_straddling_plane_is_kept():
    r, mvp = _renderer(), _view()
    # spans x from -20 to +20 -> crosses the viewport plane -> keep
    g = _geom(0.0, 0.0, 0.0)
    g.positions[:, 0] = np.linspace(-40, 40, g.positions.shape[0])
    assert r._cull_clip(g, mvp) is False, "an object spanning the plane is culled"


def test_bounds_are_cached_and_inflated_for_points():
    r = _renderer()
    g1 = _geom(1.0, 2.0, 3.0)
    lo1, hi1, grow1 = r._geometry_bounds(g1)
    assert np.allclose(lo1, [1.0, 2.0, 3.0])
    assert np.allclose(hi1, [1.0, 2.0, 3.0])
    assert np.allclose(grow1, 0.4), "point geometry should grow by max radius"
    lo2, hi2, grow2 = r._geometry_bounds(g1)
    assert np.allclose(lo1, lo2) and np.allclose(hi1, hi2), "bounds should be cached"


def test_distinct_geometries_do_not_collide_on_the_bounds_cache():
    r = _renderer()
    a = _geom(1.0, 2.0, 3.0)
    b = _geom(50.0, 60.0, 70.0)
    lo_a, _, _ = r._geometry_bounds(a)
    lo_b, _, _ = r._geometry_bounds(b)
    assert np.allclose(lo_a, [1.0, 2.0, 3.0]), "first geometry lost its bounds"
    assert np.allclose(lo_b, [50.0, 60.0, 70.0]), (
        "two geometries shared one cached box: the address was recycled"
    )


def test_bounds_not_inflated_for_meshes():
    r = _renderer()
    g = PackedGeometry(kind="mesh", positions=np.zeros((4, 3), dtype=np.float32), radii=None)
    _lo, _hi, grow = r._geometry_bounds(g)
    assert np.allclose(grow, 0.0), "mesh bounds must not be grown"
