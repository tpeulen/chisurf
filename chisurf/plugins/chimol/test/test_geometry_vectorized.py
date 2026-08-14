"""Parity tests for the vectorised cartoon/stick geometry kernels.

Several hot geometry builders were rewritten from per-element Python loops into
batched NumPy. Each test pins the vectorised output against a straightforward
reference implementation of the *original* loop, so a future change that alters
the produced geometry (vertices, normals, faces, colours) is caught rather than
silently shifting how molecules render.
"""

from __future__ import annotations

import numpy as np

from chimol.geometry import ambient
from chimol.geometry.cartoon import (
    _build_frames,
    _catmull_rom,
    _default_side_from_up,
    _extrude_shape,
    _sample_path,
)
from chimol.geometry.primitives import (
    _build_stick_mesh,
    _get_cylinder_template,
    _rotation_from_z,
    _rotations_from_z,
)


# --------------------------------------------------------------------------- #
# Reference implementations (the original loops), used only by these tests.
# --------------------------------------------------------------------------- #
def _ref_stick_mesh(bonds, pts, colors, radius, seg=12):
    template = _get_cylinder_template(seg)
    base_color = np.array([0.8, 0.8, 0.8, 1.0])
    bv = np.asarray(template["vertices"], float)
    bn = np.asarray(template["normals"], float)
    bf = np.asarray(template["faces"], np.int32)
    bz = np.asarray(template.get("z", bv[:, 2]), float)
    vpc = bv.shape[0]
    vl, nl, cl, fl, off = [], [], [], [], 0
    for pair in np.asarray(bonds, int):
        i0, i1 = int(pair[0]), int(pair[1])
        if i0 < 0 or i1 < 0 or i0 >= pts.shape[0] or i1 >= pts.shape[0] or i0 == i1:
            continue
        s, e = pts[i0], pts[i1]
        vec = e - s
        length = float(np.linalg.norm(vec))
        if not np.isfinite(length) or length <= 1e-5:
            continue
        rot = _rotation_from_z(vec)
        v = bv.copy()
        v[:, :2] *= radius
        v[:, 2] *= length
        vl.append(v @ rot.T + s)
        nl.append(bn @ rot.T)
        c0 = colors[i0] if colors is not None else base_color
        c1 = colors[i1] if colors is not None else base_color
        z = bz.reshape(-1, 1)
        col = c0 * (1 - z) + c1 * z
        col[:, 3] = 1.0
        cl.append(col)
        fl.append(bf + off)
        off += vpc
    if not vl:
        return None
    return (
        np.vstack(vl).astype(np.float32),
        np.vstack(nl).astype(np.float32),
        np.vstack(fl).astype(np.int32),
        np.vstack(cl).astype(np.float32),
    )


def _ref_extrude(path, frames, sv, sn, colors, *, cap_first=True, cap_last=True, vert_scale=None):
    m, s = path.shape[0], sv.shape[0]
    if m < 2 or s < 2:
        return None
    total = m * s + int(cap_first) + int(cap_last)
    verts = np.zeros((total, 3))
    norms = np.zeros_like(verts)
    cols = np.zeros((total, 4)) if (colors is not None and colors.shape[0] >= m) else None
    for i in range(m):
        base = i * s
        side, up = frames[i, :, 0], frames[i, :, 1]
        scale = float(vert_scale[i]) if vert_scale is not None else 1.0
        tv = (sv[:, 1:2] * side[None, :] + sv[:, 2:3] * up[None, :]) * scale
        tn = sn[:, 1:2] * side[None, :] + sn[:, 2:3] * up[None, :]
        tnn = np.linalg.norm(tn, axis=1, keepdims=True)
        mk = tnn[:, 0] > 1e-10
        tn[mk] /= tnn[mk]
        verts[base:base + s] = path[i:i + 1] + tv
        norms[base:base + s] = tn
        if cols is not None and i < colors.shape[0]:
            cols[base:base + s] = colors[i]
    faces = []
    for i in range(m - 1):
        i0, i1 = i * s, (i + 1) * s
        for j in range(s):
            k0, k1 = i0 + j, i0 + (j + 1) % s
            k2, k3 = i1 + j, i1 + (j + 1) % s
            faces.append([k0, k2, k1])
            faces.append([k1, k2, k3])
    nxt = m * s

    def cap(ring, rev):
        nonlocal nxt
        base = ring * s
        verts[nxt] = verts[base:base + s].mean(axis=0)
        norms[nxt] = -frames[ring, :, 2] if rev else frames[ring, :, 2]
        if cols is not None:
            cols[nxt] = colors[min(ring, colors.shape[0] - 1)]
        c = nxt
        nxt += 1
        for j in range(1, s - 1):
            v0 = base + (0 if rev else j)
            v1 = base + (s - j if rev else j + 1)
            faces.append([c, v1, v0] if rev else [c, v0, v1])

    if cap_first:
        cap(0, True)
    if cap_last:
        cap(m - 1, False)
    return verts, norms, np.asarray(faces, np.int32), cols


def _ref_sample(coords, colors, subdivisions=5, tension=0.0):
    arr = np.asarray(coords, float)
    n = arr.shape[0]
    subdivs = max(int(subdivisions), 1)
    out_pos, out_col, col_arr = [], None, None
    if colors is not None:
        col_arr = np.asarray(colors, float)
        out_col = [] if col_arr.shape[0] == n else None
        if col_arr.shape[0] != n:
            col_arr = None
    for i in range(n - 1):
        p0 = arr[i - 1] if i > 0 else arr[i]
        p1, p2 = arr[i], arr[i + 1]
        p3 = arr[i + 2] if (i + 2) < n else arr[i + 1]
        if col_arr is not None:
            c0 = col_arr[i - 1] if i > 0 else col_arr[i]
            c1, c2 = col_arr[i], col_arr[i + 1]
            c3 = col_arr[i + 2] if (i + 2) < n else col_arr[i + 1]
        for j in range(subdivs):
            # Every segment emits its own t = 0 knot. Skipping it for i > 0
            # (as this reference and the implementation both used to) drops
            # every interior control point, so the path no longer runs through
            # the CA positions.
            t = float(j) / float(subdivs)
            out_pos.append(_catmull_rom(p0, p1, p2, p3, t, tension=tension))
            if out_col is not None and col_arr is not None:
                out_col.append(_catmull_rom(c0, c1, c2, c3, t, tension=tension))
    out_pos.append(arr[-1])
    if out_col is not None and col_arr is not None:
        out_col.append(col_arr[-1])
    return np.asarray(out_pos, float), (np.asarray(out_col, float) if out_col is not None else None)


def _ref_frames(tangents, ups):
    m = tangents.shape[0]
    frames = np.zeros((m, 3, 3))
    prev = None
    for i in range(m):
        t, up = tangents[i], ups[i]
        side = np.cross(t, up)
        sn = float(np.linalg.norm(side))
        side = _default_side_from_up(up) if sn <= 0.0 else side / sn
        if prev is not None and float(np.dot(prev, side)) < 0.0:
            side = -side
        up2 = np.cross(side, t)
        frames[i, :, 0], frames[i, :, 1], frames[i, :, 2] = side, up2, t
        prev = side
    return frames


def _make_frames(rng, m):
    t = rng.standard_normal((m, 3))
    t /= np.linalg.norm(t, axis=1, keepdims=True)
    a = rng.standard_normal((m, 3))
    side = np.cross(a, t)
    side /= np.linalg.norm(side, axis=1, keepdims=True)
    up = np.cross(t, side)
    return np.stack([side, up, t], axis=2)


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_rotations_from_z_matches_scalar():
    rng = np.random.default_rng(0)
    dirs = rng.standard_normal((300, 3))
    dirs[0] = [0, 0, 1]      # parallel
    dirs[1] = [0, 0, -1]     # anti-parallel
    dirs[2] = [0, 0, 0]      # degenerate
    batch = _rotations_from_z(dirs)
    for i in range(dirs.shape[0]):
        assert np.allclose(batch[i], _rotation_from_z(dirs[i]), atol=1e-9)


def test_build_stick_mesh_parity():
    rng = np.random.default_rng(1)
    n = 800
    pts = rng.standard_normal((n, 3)) * 20
    bonds = np.stack([rng.integers(0, n, 1500), rng.integers(0, n, 1500)], axis=1)
    bonds[0], bonds[1], bonds[2] = [5, 5], [-1, 3], [3, n + 10]  # self / invalid / oor
    for colors in (rng.random((n, 4)), None):
        ref = _ref_stick_mesh(bonds, pts, colors, 0.15)
        new = _build_stick_mesh(bonds, pts, colors, 0.15)
        assert (ref is None) == (new is None)
        for a, b in zip(ref, new):
            assert a.shape == b.shape
            assert np.allclose(a, b, atol=1e-5)


def test_extrude_shape_parity():
    rng = np.random.default_rng(2)
    for m, s, caps, use_col, use_scale in [
        (40, 12, (True, True), True, False),
        (25, 18, (True, False), True, True),
        (30, 8, (False, True), False, False),
    ]:
        path = np.cumsum(rng.standard_normal((m, 3)), axis=0)
        frames = _make_frames(rng, m)
        sv = rng.standard_normal((s, 3))
        sv[:, 0] = 0
        sn = rng.standard_normal((s, 3))
        sn[:, 0] = 0
        colors = rng.random((m, 4)) if use_col else None
        vscale = (0.5 + rng.random(m)) if use_scale else None
        ref = _ref_extrude(path, frames, sv, sn, colors, cap_first=caps[0], cap_last=caps[1], vert_scale=vscale)
        new = _extrude_shape(path, frames, sv, sn, colors, cap_first=caps[0], cap_last=caps[1], vert_scale=vscale)
        for a, b in zip(ref, new):
            if a is None:
                assert b is None
                continue
            assert a.shape == b.shape
            assert np.allclose(a, b, atol=1e-9)


def test_sample_path_parity():
    rng = np.random.default_rng(3)
    for n, sub, tau, col in [(50, 7, 0.0, True), (30, 5, 0.3, True), (20, 3, 0.5, False)]:
        coords = np.cumsum(rng.standard_normal((n, 3)), axis=0)
        colors = rng.random((n, 4)) if col else None
        rp, rc = _ref_sample(coords, colors, sub, tau)
        np_, nc = _sample_path(coords, colors, sub, tau)
        assert np_.shape == rp.shape
        assert np.allclose(np_, rp, atol=1e-9)
        if rc is None:
            assert nc is None
        else:
            assert np.allclose(nc, rc, atol=1e-9)


def test_build_frames_parity():
    rng = np.random.default_rng(4)
    for m in [60, 25, 5]:
        tang = rng.standard_normal((m, 3))
        tang /= np.linalg.norm(tang, axis=1, keepdims=True)
        ups = rng.standard_normal((m, 3))
        ups[3] = tang[3] * 2.0  # parallel up -> zero cross -> default-side branch
        assert np.allclose(_ref_frames(tang, ups), _build_frames(tang, ups), atol=1e-9)


def test_ambient_occlusion_matches_brute_force():
    """The indexed AO must be bit-identical to the O(n^2) reference.

    The estimator counts neighbours through a k-d tree; the full distance matrix
    is the exact reference. They must agree across sparse and dense point clouds
    and different radius/cap settings — including the strict ``<`` boundary,
    which is why the reference below uses ``<`` and not ``<=``.
    """
    rng = np.random.default_rng(5)
    for n, r, mn in [(500, 4.0, 32), (1500, 6.0, 24), (400, 3.0, 16), (3000, 5.0, 32)]:
        pts = rng.standard_normal((n, 3)) * 15.0
        got = ambient._estimate_ambient_occlusion(pts, r, mn)
        delta = pts[:, None, :] - pts[None, :, :]
        inside = np.einsum("ijk,ijk->ij", delta, delta) < r * r
        np.fill_diagonal(inside, False)
        ref = np.clip(inside.sum(axis=1) / float(mn), 0.0, 1.0)
        assert got is not None
        assert np.array_equal(got, ref), f"AO mismatch n={n} r={r}: {np.abs(got - ref).max()}"


def test_ambient_occlusion_edge_cases():
    assert ambient._estimate_ambient_occlusion(np.zeros((0, 3)), 4.0, 32) is None
    assert ambient._estimate_ambient_occlusion(np.zeros((1, 3)), 4.0, 32).shape == (1,)
    # non-positive radius is rejected
    assert ambient._estimate_ambient_occlusion(np.zeros((5, 3)), 0.0, 32) is None
