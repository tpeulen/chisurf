"""Cartoon geometry builders for Chimol.

Architecture
------------
The cartoon pipeline matches PyMOL's ``RepCartoon`` design:

1. **Sampler** — smooth a CA backbone path with Catmull-Rom splines and
   propagate up-vectors (:func:`_sample_path`, :func:`_propagate_ups`).
2. **Segmenter** — split the smoothed path into contiguous blocks of the
   same secondary-structure type (helix, strand, loop).
3. **Shape + Extruder** — for each block, build the appropriate cross-section
   shape (oval for helices, rectangle for strands, circle for loops) and
   extrude it along the path, adding an arrowhead at the C-terminus of
   strands.

The public entry point :func:`_generate_cartoon_tube_arrays` dispatches
per SS block and merges the results.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Optional, Tuple

import numpy as np

try:  # sibling modules in the geometry package
    from .ambient import _estimate_ambient_occlusion
    from .guide_frames import build_guide_frames
    from .spline import sample_cartoon_curve
except Exception:  # pragma: no cover - standalone/file-path loading (see tests)
    _estimate_ambient_occlusion = None  # type: ignore[assignment]
    build_guide_frames = None  # type: ignore[assignment]
    sample_cartoon_curve = None  # type: ignore[assignment]

# Numba is required. The `_HAVE_NUMBA` guard it replaces made every kernel
# here optional and every fallback beside it unexercised -- which is how the
# ray tracer's pure-NumPy twin came to be silently broken while every test
# passed.
import numba as nb

# Two consecutive ribbon normals count as a genuine 180-degree flip (rather
# than an honest rotation of the ribbon) only when they are close to
# antiparallel. cos(155 deg); see ``_refine_orientations`` step 3.
_ANTIPARALLEL_DOT = 0.9

# How far a beta-strand arrowhead flares beyond the strand body, as a multiple
# of the body's half-breadth. Measured from PyMOL's exported 148L cartoon:
# body ~1.0 A, arrow base ~2.2 A.
_ARROW_BREADTH_SCALE = 2.2


#: Whether it is safe to write numba's on-disk cache from this module.
#:
#: A cached entry records the name of the module that compiled it, and numba
#: re-*imports* that name when it loads the entry back. This file is also loaded
#: by path (``spec_from_file_location``) by the standalone render tests, where
#: the name is a synthetic one no import can resolve. The cache key does not
#: include the module name, so the entry that load wrote was then handed to
#: ordinary runs -- and ``add_structure`` on any protein died in numba's own
#: cache loader with ``ModuleNotFoundError: No module named '<dynamic>'``.
#:
#: ``__package__`` is the parent package on a real import and empty on a
#: by-path load, which is exactly the distinction that matters here.
_NB_CACHE = bool(__package__)



@nb.jit(nopython=True, nogil=True, cache=_NB_CACHE)  # type: ignore[misc]
def _extrude_rings_nb(path, side, up, scale, shape_verts, shape_norms,
                      verts, norms):
    """Place every ring vertex and its normal, with no temporaries.

    The NumPy form of this broadcasts to ``(m, s, 3)``, which is the right
    shape for the arithmetic and the wrong one for the sizes involved: a
    cartoon extrudes about sixty segments per frame, each a handful of rings
    of a dozen vertices, so the per-call dispatch and the intermediate
    allocations cost more than the multiplications do.
    """
    m = path.shape[0]
    s = shape_verts.shape[0]
    for i in range(m):
        px, py, pz = path[i, 0], path[i, 1], path[i, 2]
        sx, sy, sz = side[i, 0], side[i, 1], side[i, 2]
        ux, uy, uz = up[i, 0], up[i, 1], up[i, 2]
        ks, ku = scale[i, 0], scale[i, 1]
        # Normals transform by the inverse transpose, i.e. the reciprocal of
        # each axis scale -- without it a flared arrowhead is lit as if it
        # were still the un-flared rectangle.
        inv_s = 1.0 / ks if abs(ks) > 1e-9 else 1.0
        inv_u = 1.0 / ku if abs(ku) > 1e-9 else 1.0
        base = i * s
        for j in range(s):
            a = shape_verts[j, 1] * ks
            b = shape_verts[j, 2] * ku
            row = base + j
            verts[row, 0] = px + a * sx + b * ux
            verts[row, 1] = py + a * sy + b * uy
            verts[row, 2] = pz + a * sz + b * uz
            na = shape_norms[j, 1] * inv_s
            nb_ = shape_norms[j, 2] * inv_u
            nx = na * sx + nb_ * ux
            ny = na * sy + nb_ * uy
            nz = na * sz + nb_ * uz
            length = math.sqrt(nx * nx + ny * ny + nz * nz)
            if length > 1e-10:
                nx /= length
                ny /= length
                nz /= length
            norms[row, 0] = nx
            norms[row, 1] = ny
            norms[row, 2] = nz

@nb.jit(nopython=True, nogil=True, cache=_NB_CACHE)  # type: ignore[misc]
def _propagate_ups_nb(tangents, hint, has_hint, ups):
    """Parallel transport along the path: genuinely sequential, so a loop.

    Each up vector is carried from the one before it, which is the whole
    point of parallel transport and the reason this cannot be vectorised.
    Compiled instead.
    """
    m = tangents.shape[0]
    have_prev = False
    px = py = pz = 0.0
    for i in range(m):
        tx, ty, tz = tangents[i, 0], tangents[i, 1], tangents[i, 2]
        ox = oy = oz = 0.0
        found = False
        for source in range(2):
            if source == 0:
                if not has_hint:
                    continue
                vx, vy, vz = hint[i, 0], hint[i, 1], hint[i, 2]
            else:
                if not have_prev:
                    continue
                vx, vy, vz = px, py, pz
            d = vx * tx + vy * ty + vz * tz
            cx, cy, cz = vx - d * tx, vy - d * ty, vz - d * tz
            length = math.sqrt(cx * cx + cy * cy + cz * cz)
            if length > 1e-8:
                ox, oy, oz = cx / length, cy / length, cz / length
                found = True
                break
        if not found:
            # Whichever axis is least parallel to the tangent, projected and
            # then projected again -- the second pass is what the helper pair
            # did, kept so the arithmetic matches to the last bit.
            fx, fy, fz = 0.0, 1.0, 0.0
            for axis in range(3):
                if axis == 0:
                    ax, ay, az = 0.0, 0.0, 1.0
                elif axis == 1:
                    ax, ay, az = 0.0, 1.0, 0.0
                else:
                    ax, ay, az = 1.0, 0.0, 0.0
                d = ax * tx + ay * ty + az * tz
                cx, cy, cz = ax - d * tx, ay - d * ty, az - d * tz
                if math.sqrt(cx * cx + cy * cy + cz * cz) > 1e-6:
                    fx, fy, fz = cx, cy, cz
                    break
            d = fx * tx + fy * ty + fz * tz
            cx, cy, cz = fx - d * tx, fy - d * ty, fz - d * tz
            length = math.sqrt(cx * cx + cy * cy + cz * cz)
            if length > 1e-8:
                ox, oy, oz = cx / length, cy / length, cz / length
            else:
                ox, oy, oz = 0.0, 1.0, 0.0
        if have_prev and (px * ox + py * oy + pz * oz) < 0.0:
            ox, oy, oz = -ox, -oy, -oz
        ups[i, 0] = ox
        ups[i, 1] = oy
        ups[i, 2] = oz
        px, py, pz = ox, oy, oz
        have_prev = True


def _batch_cross(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Row-wise 3-vector cross product for ``(N, 3)`` arrays.

    ``numpy.cross`` carries heavy per-call ``moveaxis``/axis-normalisation
    overhead; for the tight cartoon frame loops the explicit component form is
    an order of magnitude cheaper.
    """
    ax, ay, az = a[:, 0], a[:, 1], a[:, 2]
    bx, by, bz = b[:, 0], b[:, 1], b[:, 2]
    return np.stack(
        [ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx], axis=1
    )


def _catmull_rom(
    p0: np.ndarray,
    p1: np.ndarray,
    p2: np.ndarray,
    p3: np.ndarray,
    t: float,
    tension: float = 0.0,
) -> np.ndarray:
    t = float(np.clip(t, 0.0, 1.0))
    tau = float(np.clip(tension, 0.0, 1.0))
    m1 = (1.0 - tau) * 0.5 * (p2 - p0)
    m2 = (1.0 - tau) * 0.5 * (p3 - p1)
    t2 = t * t
    t3 = t2 * t
    h00 = 2.0 * t3 - 3.0 * t2 + 1.0
    h10 = t3 - 2.0 * t2 + t
    h01 = -2.0 * t3 + 3.0 * t2
    h11 = t3 - t2
    return h00 * p1 + h10 * m1 + h01 * p2 + h11 * m2


def _sample_path(
    coords: np.ndarray,
    colors: Optional[np.ndarray],
    subdivisions: int = 5,
    tension: float = 0.0,
) -> tuple[np.ndarray, Optional[np.ndarray]]:
    arr = np.asarray(coords, dtype=float)
    if arr.ndim != 2 or arr.shape[0] < 2:
        return arr, colors
    n = arr.shape[0]
    subdivs = max(int(subdivisions), 1)
    if subdivs <= 1:
        return arr, colors
    col_arr = None
    if colors is not None:
        col_arr = np.asarray(colors, dtype=float)
        if col_arr.shape[0] != n:
            col_arr = None

    # Vectorised Catmull-Rom. For every segment i in [0, n-2] the four control
    # points are gathered by clamped index shifts, and all t = j/subdivs samples
    # are evaluated at once via the Hermite basis.
    seg = np.arange(n - 1)
    i0 = np.clip(seg - 1, 0, None)          # p0 = arr[i-1] (arr[0] at the start)
    i1 = seg                                # p1 = arr[i]
    i2 = seg + 1                            # p2 = arr[i+1]
    i3 = np.minimum(seg + 2, n - 1)         # p3 = arr[i+2] (clamped at the end)

    tau = float(np.clip(tension, 0.0, 1.0))
    j = np.arange(subdivs)
    t = j.astype(float) / float(subdivs)
    t2 = t * t
    t3 = t2 * t
    h00 = (2.0 * t3 - 3.0 * t2 + 1.0)[None, :, None]
    h10 = (t3 - 2.0 * t2 + t)[None, :, None]
    h01 = (-2.0 * t3 + 3.0 * t2)[None, :, None]
    h11 = (t3 - t2)[None, :, None]

    def _hermite(vals: np.ndarray) -> np.ndarray:
        p0 = vals[i0][:, None, :]
        p1 = vals[i1][:, None, :]
        p2 = vals[i2][:, None, :]
        p3 = vals[i3][:, None, :]
        m1 = (1.0 - tau) * 0.5 * (p2 - p0)
        m2 = (1.0 - tau) * 0.5 * (p3 - p1)
        return h00 * p1 + h10 * m1 + h01 * p2 + h11 * m2  # (n-1, subdivs, C)

    # Every segment contributes its t = 0 sample, which *is* its own control
    # point: segment i covers t in [0, 1) and so never emits arr[i+1] itself.
    # Dropping j == 0 for segments after the first (as this did originally) does
    # not remove a duplicate — it removes every interior control point, so the
    # ribbon stopped passing through the CA positions and drifted ~0.3 A off
    # them. PyMOL's cartoon runs within ~0.1 A of every CA. Keeping the knots
    # also makes the residue-to-sample mapping exact (residue i lands on sample
    # i * subdivs), which is what the secondary-structure block boundaries and
    # the round-helix pass rely on.
    # Row-major (segment outer, sample inner) order.
    pos = _hermite(arr).reshape(-1, arr.shape[1])
    pos_arr = np.vstack([pos, arr[-1][None, :]])
    if col_arr is not None:
        col = _hermite(col_arr).reshape(-1, col_arr.shape[1])
        col_out_arr = np.vstack([col, col_arr[-1][None, :]])
    else:
        col_out_arr = None
    return pos_arr, col_out_arr


def _sample_orientations(
    ups: np.ndarray,
    subdivisions: int = 5,
) -> np.ndarray:
    """Densify per-residue ribbon normals along the spline by slerp.

    The companion to :func:`_sample_path`: it produces one orientation per
    sampled path point, in the same layout (``subdivisions`` samples per
    segment, duplicate knots dropped, closing on the last residue).

    A Catmull-Rom spline must **not** be used here. Orientations are unit
    vectors and inside an alpha helix they sweep ~100 degrees per residue; a
    cubic fitted through four such vectors overshoots the arc and can very
    nearly cancel, which collapses the ribbon frame. Spherical linear
    interpolation moves along the shortest great-circle arc between the two
    residue normals, so the intermediate frames stay on the cone the helix
    actually traces.

    Parameters
    ----------
    ups : np.ndarray
        Per-residue orientation vectors, shape ``(N, 3)``; need not be unit.
    subdivisions : int, optional
        Samples generated per residue-to-residue segment.

    Returns
    -------
    np.ndarray
        Unit orientation vectors, shape ``(M, 3)``, matching ``_sample_path``.
    """
    arr = np.asarray(ups, dtype=float)
    if arr.ndim != 2 or arr.shape[0] < 2:
        return arr
    subdivs = max(int(subdivisions), 1)
    if subdivs <= 1:
        return arr

    ln = np.linalg.norm(arr, axis=1, keepdims=True)
    unit = arr / np.where(ln > 1e-12, ln, 1.0)

    a = unit[:-1]                      # (n-1, 3) segment start
    b = unit[1:]                       # (n-1, 3) segment end
    dot = np.clip(np.sum(a * b, axis=1), -1.0, 1.0)
    omega = np.arccos(dot)             # (n-1,)
    sin_omega = np.sin(omega)

    t = (np.arange(subdivs, dtype=float) / float(subdivs))[None, :]  # (1, k)
    om = omega[:, None]
    so = sin_omega[:, None]

    # slerp where the arc is well conditioned, plain lerp when the two vectors
    # are almost parallel (sin(omega) -> 0 makes the slerp weights blow up).
    near = so < 1e-6
    w_a = np.where(near, 1.0 - t, np.sin((1.0 - t) * om) / np.where(near, 1.0, so))
    w_b = np.where(near, t, np.sin(t * om) / np.where(near, 1.0, so))

    samples = w_a[:, :, None] * a[:, None, :] + w_b[:, :, None] * b[:, None, :]
    out = np.vstack([samples.reshape(-1, 3), unit[-1][None, :]])

    ln_out = np.linalg.norm(out, axis=1, keepdims=True)
    return out / np.where(ln_out > 1e-12, ln_out, 1.0)


def _smooth_backbone_points(
    pts: np.ndarray, cycles: int = 2, window: int = 1
) -> np.ndarray:
    """PyMOL ``RepCartoonSmoothLoops``-style Laplacian smoothing of control points.

    Each interior point is replaced by the unweighted mean over a symmetric
    window of ``2*window+1`` points; the first/last ``window`` points are
    preserved so chain termini and chain breaks do not contract inward. The
    caller applies this per already-chain-split segment, so it never bridges
    chains. Uses an O(n) cumulative-sum moving average.

    Parameters
    ----------
    pts : np.ndarray
        Control-point coordinates, shape ``(N, 3)``.
    cycles : int, optional
        Number of smoothing passes (PyMOL default 2).
    window : int, optional
        Half-window ``f``; ``window=1`` is a 3-point average.

    Returns
    -------
    np.ndarray
        Smoothed coordinates, shape ``(N, 3)``. Returns the input unchanged
        when there are too few points or ``cycles < 1``.
    """
    arr = np.asarray(pts, dtype=float)
    n = arr.shape[0]
    f = max(int(window), 1)
    if n < (2 * f + 1) or int(cycles) < 1:
        return arr
    width = 2 * f + 1
    out = arr.copy()
    for _ in range(int(cycles)):
        csum = np.cumsum(np.vstack([np.zeros((1, 3)), out]), axis=0)
        avg = (csum[width:] - csum[:-width]) / width  # rows f .. n-f-1
        tmp = out.copy()
        tmp[f:n - f] = avg
        out = tmp
    return out


def _flip_for_sign_continuity(vectors: np.ndarray) -> np.ndarray:
    """Negate each vector that opposes the one before it, in place.

    Reads as a sequential scan -- residue ``i`` is compared against the
    *already flipped* ``i - 1`` -- but it is not one. Writing the flip as a sign
    ``s[i]``, the rule ``s[i] = -1 if s[i-1] * dot(u[i-1], u[i]) < 0 else +1``
    is exactly ``s[i] = s[i-1] * sign(dot(u[i-1], u[i]))``, so the whole chain
    is a running product and ``cumprod`` does it at once.

    The one case where the identity fails is an exactly perpendicular pair,
    where the original leaves the sign at ``+1`` rather than carrying it; that
    is taken by the scan, since guessing there would be a behaviour change
    rather than a speed-up.
    """
    n = vectors.shape[0]
    if n < 2:
        return vectors
    pairwise = np.einsum("ij,ij->i", vectors[:-1], vectors[1:])
    if np.any(pairwise == 0.0):
        for i in range(1, n):
            if float(np.dot(vectors[i - 1], vectors[i])) < 0.0:
                vectors[i] = -vectors[i]
        return vectors
    sign = np.empty(n, dtype=float)
    sign[0] = 1.0
    np.cumprod(np.where(pairwise < 0.0, -1.0, 1.0), out=sign[1:])
    vectors *= sign[:, None]
    return vectors


def _propagate_ups(
    path: np.ndarray,
    ups_hint: Optional[np.ndarray],
) -> tuple[np.ndarray, np.ndarray]:
    """Tangents and parallel-transported up vectors along a sampled path.

    The up vectors are genuinely sequential -- each one is carried from its
    predecessor, which is the whole point of parallel transport -- so the loop
    stays. What does not stay is NumPy inside it: at three floats per point a
    ``np.linalg.norm`` call spends all its time on dispatch, and this ran two
    projections per point over every sampled point of every segment. The
    arithmetic is written out on Python floats instead, and the tangents, which
    are *not* sequential, are computed for the whole path at once.
    """
    pts = np.asarray(path, dtype=float)
    m = pts.shape[0]
    if m == 0:
        return np.zeros((0, 3), dtype=float), np.zeros((0, 3), dtype=float)
    if m == 1:
        # Previously an IndexError: the i == 0 branch reached for pts[1].
        return (
            np.array([[0.0, 0.0, 1.0]], dtype=float),
            np.array([[0.0, 1.0, 0.0]], dtype=float),
        )

    # Central differences, one-sided at the ends -- no dependence between
    # points, so the whole path at once.
    tangents = np.empty((m, 3), dtype=float)
    tangents[0] = pts[1] - pts[0]
    tangents[-1] = pts[-1] - pts[-2]
    if m > 2:
        tangents[1:-1] = pts[2:] - pts[:-2]
    lengths = np.sqrt(np.einsum("ij,ij->i", tangents, tangents))
    degenerate = lengths <= 0.0
    if np.any(degenerate):
        tangents[degenerate] = (0.0, 0.0, 1.0)
        lengths[degenerate] = 1.0
    tangents /= lengths[:, None]

    hint = None
    if ups_hint is not None:
        try:
            hint = np.asarray(ups_hint, dtype=float)
            if hint.shape[0] != m or hint.shape[1:] != (3,):
                hint = None
        except Exception:
            hint = None

    ups = np.empty((m, 3), dtype=float)
    _propagate_ups_nb(
        np.ascontiguousarray(tangents),
        np.ascontiguousarray(hint if hint is not None else tangents),
        hint is not None,
        ups,
    )
    return tangents, ups

def _default_up_from_tangent(tangent: np.ndarray) -> np.ndarray:
    axis_candidates = (
        np.array([0.0, 0.0, 1.0], dtype=float),
        np.array([0.0, 1.0, 0.0], dtype=float),
        np.array([1.0, 0.0, 0.0], dtype=float),
    )
    for axis in axis_candidates:
        proj = axis - np.dot(axis, tangent) * tangent
        if float(np.linalg.norm(proj)) > 1e-6:
            return proj
    return np.array([0.0, 1.0, 0.0], dtype=float)


def _default_side_from_up(up_vec: np.ndarray) -> np.ndarray:
    axis = np.array([1.0, 0.0, 0.0], dtype=float)
    if abs(float(np.dot(axis, up_vec))) > 0.9:
        axis = np.array([0.0, 1.0, 0.0], dtype=float)
    side = np.cross(up_vec, axis)
    sn = float(np.linalg.norm(side))
    if sn <= 0.0:
        return np.array([0.0, 0.0, 1.0], dtype=float)
    return side / sn


# ---------------------------------------------------------------------------
# Frame basis  (3x3 orthonormal frame at each path point)
# ---------------------------------------------------------------------------

def _build_frames(
    tangents: np.ndarray,
    up_vectors: np.ndarray,
) -> np.ndarray:
    """Build 3x3 orthonormal frames along the path.

    Each frame has columns ``[side, up, tangent]`` so that transforming a
    shape vertex ``(sx, sy, sz=0)`` gives::

        point + sx * side + sy * up

    Returns
    -------
    frames : (M, 3, 3)  orthonormal basis matrices.
    """
    t = np.asarray(tangents, dtype=float)
    up_in = np.asarray(up_vectors, dtype=float)
    m = t.shape[0]

    # side = normalize(cross(tangent, up)); the cross products are independent
    # per point, so batch them. Only the sign-continuity flip below is truly
    # sequential, and it is a cheap scalar loop with no vector math.
    side = _batch_cross(t, up_in)
    sn = np.linalg.norm(side, axis=1)
    good = sn > 0.0
    side[good] /= sn[good, None]
    for i in np.nonzero(~good)[0]:
        side[i] = _default_side_from_up(up_in[i])

    _flip_for_sign_continuity(side)

    up = _batch_cross(side, t)  # re-orthogonalise

    frames = np.zeros((m, 3, 3), dtype=float)
    frames[:, :, 0] = side
    frames[:, :, 1] = up
    frames[:, :, 2] = t
    return frames


# ---------------------------------------------------------------------------
# Shape constructors  (cross-section profiles)
# ---------------------------------------------------------------------------

def _make_circle_shape(
    n_verts: int,
    radius: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (shape_vertices, shape_normals) for a circle.

    PyMOL analog: ``ExtrudeCircle``

    Returns
    -------
    verts : (n_verts, 3)  `(0, side, up)` offsets — built-in z=0.
    norms : (n_verts, 3)  radial normals.
    """
    angles = np.linspace(0.0, 2.0 * math.pi, n_verts, endpoint=False)
    cos_a = np.cos(angles)
    sin_a = np.sin(angles)
    verts = np.column_stack([np.zeros_like(cos_a), cos_a * radius, sin_a * radius])
    norms = np.column_stack([np.zeros_like(cos_a), cos_a, sin_a])
    return verts, norms


def _make_oval_shape(
    n_verts: int,
    width: float,
    length: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (shape_vertices, shape_normals) for a helix oval.

    PyMOL analog: ``ExtrudeOval`` driven by ``cartoon_oval_width`` /
    ``cartoon_oval_length``.

    Parameters
    ----------
    n_verts : int
        Number of vertices around the oval.
    width : float
        Half-thickness of the ribbon, measured **along the frame's up axis** —
        i.e. along the residue orientation vector, which for a helix is the
        radial direction away from the helix axis. PyMOL's
        ``cartoon_oval_width`` (0.25).
    length : float
        Half-breadth of the ribbon, measured **along the frame's side axis**
        (``tangent x up``), which for a helix runs essentially parallel to the
        helix axis. PyMOL's ``cartoon_oval_length`` (1.35).

    Notes
    -----
    The axis assignment is load-bearing: ``_extrude_shape`` maps a shape's y
    component onto ``side`` and its z component onto ``up``, so the broad
    ``length`` extent belongs on **y** and the thin ``width`` extent on **z**.
    Swapping the two rotates every ribbon 90 degrees about its own path, which
    turns helices into edge-on twisted tape and stands beta strands on their
    side.
    """
    angles = np.linspace(0.0, 2.0 * math.pi, n_verts, endpoint=False)
    cos_a = np.cos(angles)
    sin_a = np.sin(angles)
    verts = np.column_stack([np.zeros_like(cos_a), cos_a * length, sin_a * width])
    norms = np.column_stack([
        np.zeros_like(cos_a),
        cos_a * width,
        sin_a * length,
    ])
    norm_n = np.linalg.norm(norms[:, 1:], axis=1)
    nonzero = norm_n > 0.0
    norms[nonzero, 1] /= norm_n[nonzero]
    norms[nonzero, 2] /= norm_n[nonzero]
    return verts, norms


def _make_rectangle_shape(
    width: float,
    length: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (shape_vertices, shape_normals) for a flat strand ribbon.

    PyMOL analog: ``ExtrudeRectangle`` (mode=0, 8 vertices), driven by
    ``cartoon_rect_width`` / ``cartoon_rect_length``.

    The rectangle has 8 vertices — 4 corners, each split into two
    vertices with different normals (one per adjacent face).

    Parameters
    ----------
    width : float
        Half-thickness along the frame's up axis (the strand's face normal).
    length : float
        Half-breadth along the frame's side axis (across the ribbon).

    See :func:`_make_oval_shape` for why ``length`` lives on the y component.
    """
    c = float(math.cos(math.pi / 4))
    s = float(math.sin(math.pi / 4))
    half_breadth = c * length
    half_thick = s * width

    vdata = np.array([
        [0.0,  half_breadth, -half_thick],
        [0.0,  half_breadth,  half_thick],
        [0.0,  half_breadth,  half_thick],
        [0.0, -half_breadth,  half_thick],
        [0.0, -half_breadth,  half_thick],
        [0.0, -half_breadth, -half_thick],
        [0.0, -half_breadth, -half_thick],
        [0.0,  half_breadth, -half_thick],
    ])

    ndata = np.array([
        [0.0, 1.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        [0.0, 0.0, 1.0],
        [0.0, -1.0, 0.0],
        [0.0, -1.0, 0.0],
        [0.0, 0.0, -1.0],
        [0.0, 0.0, -1.0],
    ])

    return vdata, ndata


# ---------------------------------------------------------------------------
# Generic extruder
# ---------------------------------------------------------------------------

def _extrude_shape(
    path: np.ndarray,
    frames: np.ndarray,
    shape_verts: np.ndarray,
    shape_norms: np.ndarray,
    colors: Optional[np.ndarray],
    *,
    cap_ends: bool = True,
    cap_first: bool = True,
    cap_last: bool = True,
    vert_scale: Optional[np.ndarray] = None,
) -> Optional[tuple[np.ndarray, np.ndarray, np.ndarray, Optional[np.ndarray]]]:
    """Extrude a 2-D cross-section shape along a 3-D path.

    PyMOL analog: ``ExtrudeCGOSurfaceTube`` / ``ExtrudeCGOSurfacePolygon``.

    Parameters
    ----------
    path : (M, 3)
    frames : (M, 3, 3)  orthonormal bases ``[side, up, tangent]``.
    shape_verts : (S, 3)  cross-section vertices in (z, side, up) order, z=0.
    shape_norms : (S, 3)  cross-section normals in same order.
    colors : (M, 4) or None
    cap_ends : bool
        Add flat end caps.
    vert_scale : (M,), (M, 2) or None
        Per-point scale for the cross-section (used for putty and for strand
        arrowheads). A 1-D array scales the profile uniformly; an ``(M, 2)``
        array scales the ``side`` (breadth) and ``up`` (thickness) axes
        independently, which is what an arrowhead needs — it flares sideways
        and tapers to a point without ever getting thicker.
    """
    m = path.shape[0]
    s = shape_verts.shape[0]
    if m < 2 or s < 2:
        return None

    total_verts = m * s + int(cap_first) + int(cap_last)

    verts = np.zeros((total_verts, 3), dtype=float)
    norms = np.zeros_like(verts)
    cols_arr: Optional[np.ndarray] = None
    if colors is not None and colors.shape[0] >= m:
        cols_arr = np.zeros((total_verts, 4), dtype=float)

    # Transform the cross-section at every path point at once. For point i,
    # ring vertex j is  path[i] + (sv1[j]*side[i] + sv2[j]*up[i]) * scale[i],
    # which broadcasts over (m, s, 3) without a Python loop.
    side = frames[:, :, 0]  # (m, 3)
    up = frames[:, :, 1]    # (m, 3)
    if vert_scale is None:
        scale = np.ones((m, 2), dtype=float)
    else:
        scale_in = np.asarray(vert_scale, dtype=float)
        if scale_in.ndim == 1:
            scale = np.repeat(scale_in.reshape(-1, 1)[:m], 2, axis=1)
        else:
            scale = scale_in[:m, :2]
    _extrude_rings_nb(
        np.ascontiguousarray(path, dtype=float),
        np.ascontiguousarray(side, dtype=float),
        np.ascontiguousarray(up, dtype=float),
        np.ascontiguousarray(scale, dtype=float),
        np.ascontiguousarray(shape_verts, dtype=float),
        np.ascontiguousarray(shape_norms, dtype=float),
        verts,
        norms,
    )
    if cols_arr is not None and colors is not None:
        cols_arr[:m * s] = np.repeat(colors[:m], s, axis=0)
    return _finish_extrusion(
        verts, norms, cols_arr, colors, frames, m, s, cap_first, cap_last
    )

def _finish_extrusion(verts, norms, cols_arr, colors, frames, m, s,
                      cap_first, cap_last):
    """Cap centres and connectivity, shared by both extrusion paths.

    Which vertices a cap fans over is topology and comes from the memoised
    table; where the centre sits is geometry and is computed here.
    """
    next_offset = m * s
    for ring_idx, reverse in ((0, True), (m - 1, False)):
        if not (cap_first if reverse else cap_last):
            continue
        base = ring_idx * s
        verts[next_offset] = verts[base:base + s].mean(axis=0)
        norms[next_offset] = (
            -frames[ring_idx, :, 2] if reverse else frames[ring_idx, :, 2]
        )
        if cols_arr is not None:
            ci = min(ring_idx, colors.shape[0] - 1) if colors is not None else 0
            cols_arr[next_offset] = colors[ci] if colors is not None else np.ones(4)
        next_offset += 1

    faces_arr = _extrusion_faces(m, s, bool(cap_first), bool(cap_last))
    if faces_arr.shape[0] == 0:
        return None
    return verts, norms, faces_arr, cols_arr


@lru_cache(maxsize=256)
def _extrusion_faces(
    m: int, s: int, cap_first: bool, cap_last: bool
) -> np.ndarray:
    """Triangle indices for an extrusion, which depend only on its *shape*.

    An extruded ribbon's connectivity is fixed by how many rings it has and how
    many vertices are in each -- not by where any of them are. So this is the
    same array on every frame of a trajectory, and rebuilding it per segment per
    frame (with a Python loop over the cap fans) was pure repetition: a cartoon
    extrudes about sixty segments, twice over for the two caps.

    Returned **read-only**, since callers share one cached array.
    """
    ii = np.arange(m - 1)[:, None]
    jj = np.arange(s)[None, :]
    i0 = ii * s
    i1 = (ii + 1) * s
    k0 = i0 + jj
    k1 = i0 + (jj + 1) % s
    k2 = i1 + jj
    k3 = i1 + (jj + 1) % s
    tri1 = np.stack([k0, k2, k1], axis=-1)  # (m-1, s, 3)
    tri2 = np.stack([k1, k2, k3], axis=-1)
    strip_faces = np.stack([tri1, tri2], axis=2).reshape(-1, 3)

    fans: list[np.ndarray] = []
    centre = m * s
    for ring_idx, reverse in ((0, True), (m - 1, False)):
        if not (cap_first if reverse else cap_last):
            continue
        base = ring_idx * s
        j = np.arange(1, s - 1)
        if j.size:
            if reverse:
                fan = np.stack(
                    [np.full(j.shape, centre), base + (s - j), np.full(j.shape, base)],
                    axis=1,
                )
            else:
                fan = np.stack(
                    [np.full(j.shape, centre), base + j, base + j + 1], axis=1
                )
            fans.append(fan)
        centre += 1

    if fans:
        faces = np.concatenate(
            [strip_faces.astype(np.int32)] + [f.astype(np.int32) for f in fans], axis=0
        )
    else:
        faces = strip_faces.astype(np.int32)
    faces.flags.writeable = False
    return faces


def _extrude_arrowhead(
    path: np.ndarray,
    frames: np.ndarray,
    shape_verts: np.ndarray,
    shape_norms: np.ndarray,
    colors: Optional[np.ndarray],
    arrow_sampling: int,
) -> Optional[tuple[np.ndarray, np.ndarray, np.ndarray, Optional[np.ndarray]]]:
    """Extrude a strand with an arrowhead at the C-terminus.

    PyMOL analog: ``ExtrudeCGOSurfaceStrand``.

    The first ``m - arrow_sampling`` path points use the plain rectangle; over
    the remaining points the profile steps out to
    :data:`_ARROW_BREADTH_SCALE` times the body breadth and then tapers
    linearly to a point at the C-terminal tip, while its thickness stays
    constant. A flat back face closes the step at the base of the arrow.

    Measured against PyMOL's own exported cartoon mesh for 148L, a strand body
    has a half-breadth of ~1.0 A, the base of the arrow ~2.2 A and the tip
    ~0.3 A — an arrow that flares to about twice the body and comes to a point.
    An earlier version here widened to only 1.5x *at the base* and tapered back
    to 1.0x at the tip, so strands ended in a blunt stub with no arrow at all.
    """
    m = path.shape[0]
    s = shape_verts.shape[0]
    if m < 2 or s < 2 or arrow_sampling < 1:
        return None

    subN = m - arrow_sampling  # first index of arrow region
    if subN < 0:
        subN = 0

    # Breadth scales sideways over the arrow region; thickness is untouched.
    scale = np.ones((m, 2), dtype=float)
    span = max(float(m - 1 - subN), 1.0)
    for i in range(subN, m):
        frac = float(i - subN) / span          # 0 at the base, 1 at the tip
        scale[i, 0] = _ARROW_BREADTH_SCALE * (1.0 - frac)

    # Body + arrow in one extrusion; the caps are added below.
    body = _extrude_shape(
        path, frames, shape_verts, shape_norms,
        colors, cap_ends=False, vert_scale=scale,
    )
    if body is None:
        return None

    verts_b, norms_b, faces_b, cols_b = body

    # Arrowhead flat back face at subN (the "cut" plane)
    # We need to add a triangle fan at the subN ring to close the arrow
    frame_sub = frames[subN]
    base_sub = subN * s
    center_sub = verts_b[base_sub:base_sub + s].mean(axis=0)

    # Extend arrays
    extra_verts_per_side = s // 2 - 1  # triangle fan verts
    extra_total = 1 + 2 * extra_verts_per_side  # center + two sides fan

    verts_out = np.zeros((verts_b.shape[0] + extra_total, 3), dtype=float)
    verts_out[:verts_b.shape[0]] = verts_b
    norms_out = np.zeros_like(verts_out)
    norms_out[:norms_b.shape[0]] = norms_b
    cols_out = None
    if cols_b is not None:
        cols_out = np.zeros((cols_b.shape[0] + extra_total, 4), dtype=float)
        cols_out[:cols_b.shape[0]] = cols_b

    face_list = faces_b.tolist()
    off = verts_b.shape[0]

    # Back face normal = -tangent at subN
    back_normal = -frame_sub[:, 2]

    # Vertex colors at subN ring
    c0 = colors[subN] if colors is not None and subN < colors.shape[0] else np.ones(4)
    c1 = colors[subN] if colors is not None and subN < colors.shape[0] else np.ones(4)

    # Side 1: use shape_verts indices with positive side component
    side1_idx = [j for j in range(s) if shape_verts[j, 1] >= 0]
    if len(side1_idx) >= 2:
        verts_out[off] = center_sub
        norms_out[off] = back_normal
        if cols_out is not None:
            cols_out[off] = c0
        center_idx = off
        off += 1
        for jj in range(1, len(side1_idx) - 1):
            v0 = base_sub + side1_idx[0]
            v1 = base_sub + side1_idx[jj]
            v2 = base_sub + side1_idx[jj + 1]
            face_list.append([center_idx, v0, v1])
            face_list.append([center_idx, v1, v2])

    # Side 2: shape_verts indices with negative side component
    side2_idx = [j for j in range(s) if shape_verts[j, 1] < 0]
    if len(side2_idx) >= 2:
        verts_out[off] = center_sub
        norms_out[off] = back_normal
        if cols_out is not None:
            cols_out[off] = c1
        center_idx = off
        off += 1
        for jj in range(1, len(side2_idx) - 1):
            v0 = base_sub + side2_idx[0]
            v1 = base_sub + side2_idx[jj]
            v2 = base_sub + side2_idx[jj + 1]
            face_list.append([center_idx, v0, v1])
            face_list.append([center_idx, v1, v2])

    faces_arr = np.asarray(face_list, dtype=np.int32)

    # Trim unused storage
    if off < verts_out.shape[0]:
        verts_out = verts_out[:off]
        norms_out = norms_out[:off]
        if cols_out is not None:
            cols_out = cols_out[:off]

    return verts_out, norms_out, faces_arr, cols_out


# ---------------------------------------------------------------------------
# SS-based segmenter
# ---------------------------------------------------------------------------

def _segment_ss(
    ss_codes: Optional[np.ndarray],
) -> list[dict]:
    """Split the residue indices into contiguous SS blocks.

    Returns a list of dicts with ``start``, ``end`` (residue indices) and
    ``ss_type`` (``'H'``, ``'E'``, ``'C'``).
    """
    if ss_codes is None or ss_codes.size < 1:
        return []

    codes = np.asarray(ss_codes)
    if codes.dtype.kind in "US":
        first = np.char.upper(np.char.strip(codes.astype(str)).astype("U1"))
    else:
        first = np.array(
            [str(code).strip().upper()[:1] for code in codes], dtype="U1"
        )
    types = np.where(first == "H", "H", np.where(first == "E", "E", "C"))

    # Block boundaries are wherever the type changes -- one comparison over the
    # whole array rather than a scan that visits every residue in Python.
    n = types.shape[0]
    breaks = np.flatnonzero(types[1:] != types[:-1]) + 1
    starts = np.concatenate(([0], breaks))
    ends = np.concatenate((breaks, [n]))
    return [
        {"start": int(a), "end": int(b), "ss_type": str(types[a])}
        for a, b in zip(starts, ends)
    ]


def _residue_to_path_index(
    res_idx: int,
    n_residues: int,
    n_path: int,
) -> int:
    """Map a residue index to the closest path index."""
    if n_residues <= 1:
        return 0
    return int(round(float(res_idx) * (n_path - 1) / (n_residues - 1)))


def _contiguous_runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Return ``[(start, stop), ...]`` half-open spans where ``mask`` is True."""
    flags = np.asarray(mask, dtype=bool)
    if flags.size == 0:
        return []
    padded = np.concatenate([[False], flags, [False]])
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    return [(int(a), int(b)) for a, b in zip(edges[::2], edges[1::2])]


def _rotate_about(vec: np.ndarray, axis: np.ndarray, angle: float) -> np.ndarray:
    """Rotate ``vec`` about the unit ``axis`` by ``angle`` radians (Rodrigues)."""
    c = math.cos(angle)
    s = math.sin(angle)
    out = vec * c + np.cross(axis, vec) * s + axis * float(np.dot(axis, vec)) * (1.0 - c)
    n = float(np.linalg.norm(out))
    return out / n if n > 1e-12 else vec


def _rotate_about_batch(
    vectors: np.ndarray, axis: np.ndarray, angles: np.ndarray
) -> np.ndarray:
    """Rotate each row about one shared unit ``axis``, by its own angle.

    The row-wise form of :func:`_rotate_about`. Used to extrapolate a helix run's
    radials past the residues that could be measured -- once per missing residue,
    which at a single 3-vector a time is all NumPy dispatch overhead.
    """
    c = np.cos(angles)[:, None]
    s = np.sin(angles)[:, None]
    axis = np.asarray(axis, dtype=float).reshape(3)
    out = (
        vectors * c
        + _batch_cross(np.broadcast_to(axis, vectors.shape), vectors) * s
        + axis[None, :] * (vectors @ axis)[:, None] * (1.0 - c)
    )
    lengths = np.sqrt(np.einsum("ij,ij->i", out, out))
    good = lengths > 1e-12
    result = np.array(vectors, dtype=float, copy=True)
    result[good] = out[good] / lengths[good][:, None]
    return result


def _helix_twist(
    radial: np.ndarray,
    valid: np.ndarray,
) -> tuple[Optional[np.ndarray], float]:
    """Estimate a helix run's rotation axis and its twist per residue.

    The radial vectors of consecutive helix residues differ by a rotation about
    the helix axis. Averaging ``cross(r[k], r[k+1])`` recovers that axis with the
    right sign, and the mean angle between consecutive radials is the twist.

    Parameters
    ----------
    radial : np.ndarray
        Per-residue outward radial vectors, shape ``(N, 3)``.
    valid : np.ndarray
        Indices into ``radial`` that hold a well-defined vector, ascending.

    Returns
    -------
    tuple
        ``(axis, twist)`` with ``axis`` a unit vector (or ``None`` when the run
        is too short to tell) and ``twist`` the per-residue angle in radians.
    """
    if valid.size < 2:
        return None, 0.0
    first = valid[:-1].astype(np.int64)
    second = valid[1:].astype(np.int64)
    adjacent = (second - first) == 1
    first = first[adjacent]
    second = second[adjacent]
    if first.size == 0:
        return None, 0.0

    r0 = radial[first]
    r1 = radial[second]
    # One batched cross for the whole run. Called per helix run per rebuild, and
    # `np.cross` on a single 3-vector spends over ten microseconds in axis
    # bookkeeping before it multiplies anything.
    crossed = _batch_cross(r0, r1)
    lengths = np.sqrt(np.einsum("ij,ij->i", crossed, crossed))
    usable = lengths > 1e-9
    if not np.any(usable):
        return None, 0.0

    axes = crossed[usable] / lengths[usable][:, None]
    angles = np.arctan2(lengths[usable], np.einsum("ij,ij->i", r0[usable], r1[usable]))

    axis = axes.mean(axis=0)
    ln = float(math.sqrt(axis[0] ** 2 + axis[1] ** 2 + axis[2] ** 2))
    if ln <= 1e-9:
        return None, 0.0
    return axis / ln, float(angles.mean())


def _helix_radials(
    ca: np.ndarray,
    is_helix: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Outward radial direction of the local helix cylinder, per residue.

    For three consecutive CAs on a helix the bisector
    ``normalize(ca[i-1]-ca[i]) + normalize(ca[i+1]-ca[i])`` points from the CA
    straight at the axis, exactly, so the outward radial is its negation. This
    beats estimating the axis from a chord such as ``ca[i+2]-ca[i-2]``: at ~100
    degrees of twist per residue that chord still carries a large radial
    component, and near the ends of a helix the window has to be clamped, which
    is where such an estimate goes 40-60 degrees wrong and makes the last turn
    of every helix flare out.

    The first and last residue of a run have no all-helix neighbourhood, so
    their radial is *extrapolated* rather than copied: a helix advances its
    radial by a fixed twist per residue, and copying a neighbour's vector
    verbatim would leave the end ring a full turn-step out of phase.

    Parameters
    ----------
    ca : np.ndarray
        CA coordinates, shape ``(N, 3)``.
    is_helix : np.ndarray
        Boolean mask of helical residues, shape ``(N,)``.

    Returns
    -------
    tuple of np.ndarray
        ``(radial, has_radial)`` — unit outward vectors and the mask of
        residues for which one could be established.
    """
    n = ca.shape[0]
    radial = np.zeros((n, 3), dtype=float)
    has_radial = np.zeros(n, dtype=bool)

    # Every interior residue whose two neighbours are also helical, at once.
    if n >= 3:
        interior = np.zeros(n, dtype=bool)
        interior[1:-1] = is_helix[:-2] & is_helix[1:-1] & is_helix[2:]
        rows = np.nonzero(interior)[0]
        if rows.size:
            a = ca[rows - 1] - ca[rows]
            b = ca[rows + 1] - ca[rows]
            an = np.sqrt(np.einsum("ij,ij->i", a, a))
            bn = np.sqrt(np.einsum("ij,ij->i", b, b))
            ok = (an > 1e-6) & (bn > 1e-6)
            if np.any(ok):
                rows = rows[ok]
                bisector = a[ok] / an[ok][:, None] + b[ok] / bn[ok][:, None]
                bl = np.sqrt(np.einsum("ij,ij->i", bisector, bisector))
                good = bl > 1e-6
                if np.any(good):
                    rows = rows[good]
                    radial[rows] = -bisector[good] / bl[good][:, None]
                    has_radial[rows] = True

    # Every helix run's axis and twist in one pass, then one rotation for all
    # the residues that need extrapolating. Per run this was two NumPy calls on
    # a handful of vectors each, about twenty times a frame, which is all
    # dispatch: `_helix_twist` and the rotation were the largest remaining pair
    # in the profile once the sequential loops had been compiled.
    runs = list(_contiguous_runs(is_helix))
    if not runs:
        return radial, has_radial

    axes, twists = _helix_twist_per_run(radial, has_radial, runs)

    need_rows: list[np.ndarray] = []
    from_rows: list[np.ndarray] = []
    axis_rows: list[np.ndarray] = []
    angle_rows: list[np.ndarray] = []
    copy_need: list[np.ndarray] = []
    copy_from: list[np.ndarray] = []
    for run_index, (run_lo, run_hi) in enumerate(runs):
        idx = np.arange(run_lo, run_hi)
        inside = has_radial[idx]
        valid = idx[inside]
        if valid.size == 0:
            continue
        need = idx[~inside]
        if need.size == 0:
            continue
        # Nearest measured residue for each one still missing; `argmin` takes the
        # first minimum, so a tie goes to the lower index as the loop did.
        nearest = valid[np.argmin(np.abs(valid[None, :] - need[:, None]), axis=1)]
        axis_u = axes[run_index]
        if axis_u is None:
            copy_need.append(need)
            copy_from.append(nearest)
        else:
            need_rows.append(need)
            from_rows.append(nearest)
            axis_rows.append(np.broadcast_to(axis_u, (need.shape[0], 3)))
            angle_rows.append(twists[run_index] * (need - nearest).astype(float))
        has_radial[need] = True

    if copy_need:
        radial[np.concatenate(copy_need)] = radial[np.concatenate(copy_from)]
    if need_rows:
        rows = np.concatenate(need_rows)
        radial[rows] = _rotate_about_rows(
            radial[np.concatenate(from_rows)],
            np.concatenate(axis_rows),
            np.concatenate(angle_rows),
        )

    return radial, has_radial


def _helix_twist_per_run(
    radial: np.ndarray,
    has_radial: np.ndarray,
    runs: list[tuple[int, int]],
) -> tuple[list[Optional[np.ndarray]], list[float]]:
    """Rotation axis and per-residue twist for every helix run at once.

    The batched form of :func:`_helix_twist`. Each run's axis is the mean of
    ``cross(r[k], r[k+1])`` over its adjacent measured residues and its twist the
    mean angle between them; doing every run's crosses in one call and reducing
    per run afterwards replaces a handful of tiny NumPy calls per run.

    Returns
    -------
    tuple
        ``(axes, twists)``, one entry per run, with ``None`` for a run too short
        or too degenerate to tell -- exactly what :func:`_helix_twist` returns.
    """
    n_runs = len(runs)
    axes: list[Optional[np.ndarray]] = [None] * n_runs
    twists: list[float] = [0.0] * n_runs

    first_rows: list[np.ndarray] = []
    second_rows: list[np.ndarray] = []
    owner_rows: list[np.ndarray] = []
    for run_index, (run_lo, run_hi) in enumerate(runs):
        idx = np.arange(run_lo, run_hi)
        valid = idx[has_radial[idx]]
        if valid.size < 2:
            continue
        first = valid[:-1]
        second = valid[1:]
        adjacent = (second - first) == 1
        if not np.any(adjacent):
            continue
        first_rows.append(first[adjacent])
        second_rows.append(second[adjacent])
        owner_rows.append(np.full(int(adjacent.sum()), run_index, dtype=np.int64))
    if not first_rows:
        return axes, twists

    first = np.concatenate(first_rows)
    second = np.concatenate(second_rows)
    owner = np.concatenate(owner_rows)
    r0 = radial[first]
    r1 = radial[second]
    crossed = _batch_cross(r0, r1)
    lengths = np.sqrt(np.einsum("ij,ij->i", crossed, crossed))
    usable = lengths > 1e-9
    if not np.any(usable):
        return axes, twists

    owner = owner[usable]
    unit_axes = crossed[usable] / lengths[usable][:, None]
    angles = np.arctan2(
        lengths[usable], np.einsum("ij,ij->i", r0[usable], r1[usable])
    )

    counts = np.bincount(owner, minlength=n_runs)
    summed = np.zeros((n_runs, 3), dtype=float)
    for axis in range(3):
        summed[:, axis] = np.bincount(
            owner, weights=unit_axes[:, axis], minlength=n_runs
        )
    angle_sum = np.bincount(owner, weights=angles, minlength=n_runs)

    present = counts > 0
    mean_axes = np.zeros((n_runs, 3), dtype=float)
    mean_axes[present] = summed[present] / counts[present][:, None]
    norms = np.sqrt(np.einsum("ij,ij->i", mean_axes, mean_axes))
    for run_index in np.nonzero(present)[0]:
        if norms[run_index] <= 1e-9:
            continue
        axes[run_index] = mean_axes[run_index] / norms[run_index]
        twists[run_index] = float(angle_sum[run_index] / counts[run_index])
    return axes, twists


def _rotate_about_rows(
    vectors: np.ndarray, axes: np.ndarray, angles: np.ndarray
) -> np.ndarray:
    """Rotate each row about *its own* unit axis, by its own angle.

    The per-row-axis generalisation of :func:`_rotate_about_batch`, so that every
    helix run's extrapolation can go through a single call.
    """
    c = np.cos(angles)[:, None]
    s = np.sin(angles)[:, None]
    out = (
        vectors * c
        + _batch_cross(axes, vectors) * s
        + axes * np.einsum("ij,ij->i", vectors, axes)[:, None] * (1.0 - c)
    )
    lengths = np.sqrt(np.einsum("ij,ij->i", out, out))
    good = lengths > 1e-12
    result = np.array(vectors, dtype=float, copy=True)
    result[good] = out[good] / lengths[good][:, None]
    return result


def _helix_cylinder_radii(
    ca: np.ndarray,
    is_helix: np.ndarray,
    radial: np.ndarray,
    has_radial: np.ndarray,
) -> np.ndarray:
    """Radius of the local helix cylinder at each helical residue.

    Taken as the circumradius of the three consecutive CAs after projecting
    them onto the plane perpendicular to the local helix axis; for an ideal
    alpha helix that is exactly the ~2.3 A CA radius.

    Returns
    -------
    np.ndarray
        Per-residue radii, shape ``(N,)``; zero where undefined.
    """
    n = ca.shape[0]
    radii = np.zeros(n, dtype=float)

    for run_lo, run_hi in _contiguous_runs(is_helix):
        idx = np.arange(run_lo, run_hi)
        valid = idx[has_radial[idx]]
        if valid.size < 2:
            continue
        axis_u, _ = _helix_twist(radial, valid)
        if axis_u is None:
            continue
        # The circumradius of each residue's own triple, for the whole run at
        # once. The middle point of a triple is the residue itself, so it sits
        # at the origin after the shift and drops out of the algebra.
        rows = idx[(idx - 1 >= run_lo) & (idx + 1 < run_hi)]
        if rows.size:
            before = ca[rows - 1] - ca[rows]
            after = ca[rows + 1] - ca[rows]
            first = before - (before @ axis_u)[:, None] * axis_u
            third = after - (after @ axis_u)[:, None] * axis_u
            side_a = np.sqrt(np.einsum("ij,ij->i", first, first))
            side_b = np.sqrt(np.einsum("ij,ij->i", third, third))
            span = third - first
            side_c = np.sqrt(np.einsum("ij,ij->i", span, span))
            crossed = _batch_cross(-first, span)
            area = 0.5 * np.sqrt(np.einsum("ij,ij->i", crossed, crossed))
            usable = area > 1e-9
            if np.any(usable):
                radii[rows[usable]] = (
                    side_a[usable] * side_b[usable] * side_c[usable]
                    / (4.0 * area[usable])
                )
        # carry the nearest measured radius into the run's end residues
        measured = idx[radii[idx] > 0.0]
        if measured.size == 0:
            continue
        for i in idx:
            if radii[i] <= 0.0:
                radii[i] = radii[int(measured[np.argmin(np.abs(measured - i))])]

    return radii


def _unit(vectors: np.ndarray) -> np.ndarray:
    """Row-wise unit vectors, leaving degenerate rows unchanged."""
    lengths = np.linalg.norm(vectors, axis=1, keepdims=True)
    return np.divide(vectors, lengths, out=np.array(vectors, dtype=float),
                     where=lengths > 1e-12)


def _interpolate_residue_colors(
    colors: Optional[np.ndarray],
    weights: np.ndarray,
    sampling: int,
    n_residues: int,
) -> Optional[np.ndarray]:
    """Blend per-residue colours along the sampled curve.

    ``weights`` gives each sample's eased position between the two residues it
    lies between, so the colour follows the same easing the geometry does and a
    residue boundary does not land in a different place for colour than for
    shape.
    """
    if colors is None:
        return None
    arr = np.asarray(colors, dtype=float)
    if arr.shape[0] != n_residues or n_residues < 2:
        return colors

    m = weights.shape[0]
    segment = np.minimum(np.arange(m) // max(int(sampling), 1), n_residues - 2)
    lo = arr[segment]
    hi = arr[segment + 1]
    w = weights[:, None]
    return (1.0 - w) * lo + w * hi


def _orthogonalise_ups(
    tangents: np.ndarray, ups: np.ndarray
) -> np.ndarray:
    """Re-square the up-vectors against tangents that have since changed.

    Replacing a spline tangent with a guide-frame one (at a strand tip) leaves
    the ribbon's face no longer perpendicular to it, which shears the profile.
    """
    axis = _unit(tangents)
    along = np.einsum("ij,ij->i", ups, axis)
    out = _unit(ups - along[:, None] * axis)
    # Where the two were parallel the projection collapses; keep the original.
    degenerate = np.linalg.norm(out, axis=1) < 1e-6
    out[degenerate] = ups[degenerate]
    return out


def _flatten_sheet_path(
    ca: np.ndarray,
    is_sheet: np.ndarray,
    cycles: int = 4,
    ups: Optional[np.ndarray] = None,
) -> tuple[np.ndarray, Optional[np.ndarray]]:
    """De-pleat the backbone through beta strands (PyMOL ``cartoon_flat_sheets``).

    A beta strand's CAs zig-zag by ~1.9 A about the strand axis. Splining
    straight through them gives a ribbon that has to writhe to follow the pleat,
    which is why chimol's strands rolled from face-on to edge-on along their
    length while PyMOL's stay flat.

    This follows ``RepCartoonFlattenSheets`` (``layer2/RepCartoon.cpp``) rather
    than approximating it. Per strand run, for ``cartoon_flat_cycles`` passes:

    1. replace each interior position by the **uniform** average of itself and
       its two neighbours -- PyMOL's ``scale3f(t0, 1/(f*2+1))`` with ``f = 1``,
       not a weighted kernel;
    2. average the **orientation vectors** the same way, which an earlier version
       here omitted -- smoothing the path while leaving the ribbon's up-vectors
       pleated keeps half the twist;
    3. re-orthogonalise each orientation against the local tangent
       ``normalize(p[b+1] - p[b-1])`` and renormalise, so the ribbon's face stays
       perpendicular to the path it now follows.

    Residues outside a strand are left in place, so the joins to the flanking
    loops do not move.

    Parameters
    ----------
    ca : np.ndarray
        Control points, shape ``(N, 3)``; not modified in place.
    is_sheet : np.ndarray
        Boolean mask of strand residues, shape ``(N,)``.
    cycles : int, optional
        Number of passes; PyMOL's ``cartoon_flat_cycles`` default is 4.
    ups : np.ndarray, optional
        Per-residue ribbon up-vectors, shape ``(N, 3)``, smoothed alongside.

    Returns
    -------
    tuple
        The smoothed control points and up-vectors (the latter ``None`` when
        none were given).
    """
    n = ca.shape[0]
    out = np.array(ca, dtype=float, copy=True)
    out_ups = None if ups is None else np.array(ups, dtype=float, copy=True)
    if n < 3 or cycles <= 0 or not np.any(is_sheet):
        return out, out_ups

    for start, stop in _contiguous_runs(np.asarray(is_sheet, dtype=bool)):
        # PyMOL smooths first+f .. last-f with f = 1, so a run's own end points
        # are anchors and a run shorter than three residues cannot move.
        lo, hi = start + 1, stop - 1
        if hi - lo < 1:
            continue
        for _ in range(int(cycles)):
            out[lo:hi] = (
                out[lo - 1:hi - 1] + out[lo:hi] + out[lo + 1:hi + 1]
            ) / 3.0
            if out_ups is None:
                continue
            out_ups[lo:hi] = (
                out_ups[lo - 1:hi - 1] + out_ups[lo:hi] + out_ups[lo + 1:hi + 1]
            ) / 3.0
            # Re-orthogonalise against the path the points now follow.
            tangent = _unit(out[lo + 1:hi + 1] - out[lo - 1:hi - 1])
            along = np.einsum("ij,ij->i", out_ups[lo:hi], tangent)
            out_ups[lo:hi] = _unit(
                out_ups[lo:hi] - along[:, None] * tangent
            )
    return out, out_ups


def _smooth_loop_path(
    ca: np.ndarray,
    is_loop: np.ndarray,
    cycles: int = 2,
    first: int = 1,
    last: int = 1,
    ups: Optional[np.ndarray] = None,
) -> tuple[np.ndarray, Optional[np.ndarray]]:
    """Round off the coil between elements (PyMOL ``cartoon_smooth_loops``).

    ``RepCartoonSmoothLoops``. The same uniform box average as the sheet pass,
    but over **loop** runs, and with two differences that matter:

    * the run is **widened by one residue at each end**, into the helix or strand
      it joins, so the smoothing does not stop dead at the junction and leave a
      crease there;
    * the orientations are renormalised but **not** re-orthogonalised against the
      tangent, unlike the sheet pass -- a loop has no face to keep flat.

    PyMOL runs it for each window width from ``cartoon_smooth_first`` to
    ``cartoon_smooth_last`` (both 1 by default, so one width), ``smooth_cycles``
    times each. It is **off** by default there, and off here.

    Parameters
    ----------
    ca : np.ndarray
        Control points, shape ``(N, 3)``; not modified in place.
    is_loop : np.ndarray
        Boolean mask of coil residues.
    cycles : int, optional
        ``cartoon_smooth_cycles``.
    first, last : int, optional
        ``cartoon_smooth_first`` / ``cartoon_smooth_last``: the range of
        half-window widths to sweep.
    ups : np.ndarray, optional
        Per-residue up-vectors, smoothed alongside.

    Returns
    -------
    tuple
        The smoothed control points and up-vectors.
    """
    n = ca.shape[0]
    out = np.array(ca, dtype=float, copy=True)
    out_ups = None if ups is None else np.array(ups, dtype=float, copy=True)
    if n < 3 or cycles <= 0 or not np.any(is_loop):
        return out, out_ups

    mask = np.asarray(is_loop, dtype=bool)
    for start, stop in _contiguous_runs(mask):
        # Widen into the flanking element, as PyMOL does, so the join is smooth.
        run_start = max(start - 1, 0)
        run_stop = min(stop + 1, n - 1)
        for f in range(max(int(first), 1), max(int(last), int(first)) + 1):
            lo, hi = run_start + f, run_stop - f
            if hi - lo < 1:
                continue
            width = 2 * f + 1
            for _ in range(int(cycles)):
                window = sum(
                    out[lo + e:hi + e] for e in range(-f, f + 1)
                )
                out[lo:hi] = window / float(width)
                if out_ups is None:
                    continue
                window_ups = sum(
                    out_ups[lo + e:hi + e] for e in range(-f, f + 1)
                )
                out_ups[lo:hi] = _unit(window_ups / float(width))
    return out, out_ups


def _path_parameterisation(
    n: int,
    subdivisions: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Return, for every sample :func:`_sample_path` emits, its segment and ``t``.

    Mirrors that function's layout exactly: ``subdivisions`` samples per
    residue-to-residue segment covering ``t`` in ``[0, 1)``, with the final
    control point appended.

    Returns
    -------
    tuple of np.ndarray
        ``(segment, t)``, both of length ``M``; ``segment[k]`` is the index of
        the control point the sample starts from and ``t[k]`` its fraction
        along that segment.
    """
    subdivs = max(int(subdivisions), 1)
    if n < 2 or subdivs <= 1:
        return np.arange(max(n, 0)), np.zeros(max(n, 0), dtype=float)

    seg = np.repeat(np.arange(n - 1), subdivs)
    t = np.tile(np.arange(subdivs, dtype=float) / float(subdivs), n - 1)
    return (np.append(seg, n - 2), np.append(t, 1.0))


def _round_helix_path(
    path: np.ndarray,
    ca: np.ndarray,
    is_helix: np.ndarray,
    subdivisions: int,
) -> np.ndarray:
    """Lift the sampled path back onto the helix cylinder (PyMOL round helices).

    A Catmull-Rom spline through alpha-helix CAs cuts the corner badly: with
    ~100 degrees of turn per residue its midpoint sits at about 0.83x the CA
    radius, so every turn of the ribbon is visibly pinched inward. PyMOL's
    ``cartoon_round_helices`` (on by default) avoids this; measured on 148L its
    ribbon centerline stays at radius 2.17 A midway between residues whose CAs
    are at 2.23 A, whereas with the setting off it drops to 1.88 A.

    Inside a helix this replaces the spline with the actual helical arc:
    the axis point and cylinder radius are interpolated linearly between the two
    bracketing residues while the outward radial is slerped, which reproduces a
    constant-radius sweep and still passes exactly through every CA, so the
    joins to the flanking loops stay continuous.

    Parameters
    ----------
    path : np.ndarray
        Sampled path, shape ``(M, 3)``; not modified in place.
    ca : np.ndarray
        The control points the path was sampled from, shape ``(N, 3)``.
    is_helix : np.ndarray
        Boolean mask over the control points.
    subdivisions : int
        The sampling used to build ``path``.

    Returns
    -------
    np.ndarray
        The corrected path, shape ``(M, 3)``.
    """
    n = ca.shape[0]
    if n < 3 or not np.any(is_helix):
        return path

    radial, has_radial = _helix_radials(ca, is_helix)
    radii = _helix_cylinder_radii(ca, is_helix, radial, has_radial)

    seg, tt = _path_parameterisation(n, subdivisions)
    if seg.shape[0] != path.shape[0]:
        # sampling layout changed under us; leave the path alone rather than
        # corrupting it
        return path

    out = np.array(path, dtype=float, copy=True)
    # axis point for each residue: the CA pulled inward by one radius
    axis_pt = ca - radial * radii[:, None]

    usable = has_radial & (radii > 1e-6) & is_helix
    # Every sampled point is independent of every other, so the slerp runs over
    # the whole path at once rather than a point at a time.
    i = seg.astype(np.int64)
    j = i + 1
    take = j < n
    take[take] &= usable[i[take]] & usable[j[take]]
    if not np.any(take):
        return out
    k = np.nonzero(take)[0]
    i = i[k]
    j = j[k]
    t = tt[k].astype(float)[:, None]

    r0 = radial[i]
    r1 = radial[j]
    dot = np.clip(np.einsum("ij,ij->i", r0, r1), -1.0, 1.0)
    omega = np.arccos(dot)[:, None]
    so = np.sin(omega)
    # Linear where the two radials are nearly parallel: the slerp is 0/0 there,
    # and the chord and the arc agree to well past float precision anyway.
    flat = so < 1e-6
    safe = np.where(flat, 1.0, so)
    rad_t = np.where(
        flat,
        (1.0 - t) * r0 + t * r1,
        (np.sin((1.0 - t) * omega) * r0 + np.sin(t * omega) * r1) / safe,
    )

    length = np.sqrt(np.einsum("ij,ij->i", rad_t, rad_t))
    good = length > 1e-9
    if not np.any(good):
        return out
    k = k[good]
    i = i[good]
    j = j[good]
    t = t[good]
    rad_t = rad_t[good] / length[good][:, None]

    centre = (1.0 - t) * axis_pt[i] + t * axis_pt[j]
    radius = (1.0 - t[:, 0]) * radii[i] + t[:, 0] * radii[j]
    out[k] = centre + radius[:, None] * rad_t
    return out


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def _normalised_ss(ss_codes, n: int):
    """One-character upper-case secondary-structure codes, or ``None``.

    Called on every rebuild with the same codes -- secondary structure is
    assigned once and does not change as a trajectory moves -- so the per-residue
    ``str(...).upper()[:1]`` comprehension this replaces was several hundred
    string operations a frame for an answer that was already known. NumPy does
    the whole array at once when the codes are already strings; anything else
    (a list holding ``None``, say) still takes the careful path.
    """
    if ss_codes is None:
        return None
    try:
        codes = np.asarray(ss_codes)
        if codes.shape[0] != n:
            return None
        if codes.dtype.kind in "US":
            return np.char.upper(codes.astype("U1"))
        return np.array(
            [str(code).upper()[:1] if code is not None else "" for code in ss_codes]
        )
    except Exception:
        return None


def _refine_orientations(
    ca: np.ndarray,
    vo: np.ndarray,
    ss_codes: Optional[np.ndarray],
) -> np.ndarray:
    """PyMOL-style per-residue ribbon-orientation refinement.

    Turns the raw peptide-plane orientations into smooth, untwisted ribbon
    normals, replicating the three mechanisms that stop PyMOL cartoons from
    twisting:

    * **Round helices** — a helix residue's orientation is recomputed as the
      outward radial direction of the local helix cylinder, so the oval circles
      a smooth axis instead of wobbling with each carbonyl.
    * **Flat sheets** — orientations across a strand are box-averaged
      (``cartoon_flat_cycles`` = 4, 3-point window) so a whole β-strand shares
      one consistent up-vector and lies flat.
    * **Refine normals** — every orientation is forced perpendicular to the
      tangent and its sign propagated forward (no 180° flips) to kill twist.

    Returns the refined orientation vectors (shape ``(n, 3)``).
    """
    n = ca.shape[0]
    vo = np.array(vo, dtype=float, copy=True)
    if n < 3:
        return vo

    # Unit CA differences and head-to-tail tangents.
    diff = ca[1:] - ca[:-1]
    dl = np.linalg.norm(diff, axis=1, keepdims=True)
    unit = diff / np.where(dl > 1e-9, dl, 1.0)
    tang = np.zeros((n, 3), dtype=float)
    tang[1:-1] = unit[1:] + unit[:-1]
    tang[0] = unit[0]
    tang[-1] = unit[-1]
    tl = np.linalg.norm(tang, axis=1, keepdims=True)
    tang = tang / np.where(tl > 1e-9, tl, 1.0)

    ss = _normalised_ss(ss_codes, n)
    is_helix = (ss == "H") if ss is not None else np.zeros(n, dtype=bool)
    is_sheet = np.isin(ss, ["S", "E"]) if ss is not None else np.zeros(n, dtype=bool)

    # 1. Round helices: point the ribbon normal radially outward from the local
    #    helix cylinder, so the oval circles a smooth axis.
    radial, has_radial = _helix_radials(ca, is_helix)
    take = is_helix & has_radial
    if np.any(take):
        vo[take] = radial[take]

    # 2. Flat sheets: 4 cycles of a 3-point box average within strands.
    if is_sheet.any():
        inner = np.zeros(n, dtype=bool)
        inner[1:-1] = is_sheet[:-2] & is_sheet[1:-1] & is_sheet[2:]
        rows = np.nonzero(inner)[0]
        if rows.size:
            for _ in range(4):
                # Every window is read from the *unmodified* vo and written
                # afterwards, so the cycle is a simultaneous update and the
                # whole strand can be averaged at once.
                acc = vo[rows - 1] + vo[rows] + vo[rows + 1]
                length = np.sqrt(np.einsum("ij,ij->i", acc, acc))
                ok = length > 1e-6
                if np.any(ok):
                    vo[rows[ok]] = acc[ok] / length[ok][:, None]

    # 3. Refine normals: force perpendicular to the tangent, then propagate the
    #    sign so a ribbon does not flip over between neighbouring residues.
    dot_t = np.sum(vo * tang, axis=1, keepdims=True)
    vo = vo - dot_t * tang
    ln = np.linalg.norm(vo, axis=1, keepdims=True)
    vo = vo / np.where(ln > 1e-9, ln, 1.0)

    # The sign propagation must skip helices. Inside an alpha helix the ribbon
    # normal is radial, so it genuinely rotates by ~100 degrees per residue and
    # consecutive normals have dot ~ cos(100 deg) = -0.17. A plain "dot < 0 ->
    # negate" rule therefore flips *every* helix residue, turning the smooth
    # radial field into an alternating zig-zag; once that is interpolated along
    # the spline the up-vectors partly cancel and the helix renders as pinched,
    # edge-on tape instead of a coil. A real 180 degree flip is nearly
    # antiparallel, so only correct those.
    # Sequential -- each step compares against the neighbour it just wrote -- but
    # it does not need NumPy to compare three floats. The helix threshold is what
    # stops this being a running product like the other sign sweeps here.
    rows = vo.tolist()
    helix = is_helix.tolist()
    for i in range(1, n):
        previous = rows[i - 1]
        current = rows[i]
        d = (previous[0] * current[0] + previous[1] * current[1]
             + previous[2] * current[2])
        threshold = -_ANTIPARALLEL_DOT if (helix[i] or helix[i - 1]) else 0.0
        if d < threshold:
            rows[i] = [-current[0], -current[1], -current[2]]
    vo[:] = rows
    return vo


def _putty_vert_scale(
    path: np.ndarray, cfg: dict, values: Optional[np.ndarray]
) -> Optional[np.ndarray]:
    """Per-path-point radius multipliers for a putty tube.

    The values arrive per *residue* while the path is subdivided, so they are
    resampled onto the path before smoothing — smoothing the residue-level
    factors instead would blur over a different length scale depending on the
    sampling, and the tube would change shape when ``cartoon_sampling`` changed.

    Parameters
    ----------
    path : numpy.ndarray
        ``(M, 3)`` spline points.
    cfg : dict
        The cartoon config, read for the ``putty_*`` settings.
    values : numpy.ndarray or None
        One number per residue. ``None`` gives a uniform tube rather than an
        error: a structure with no b-factors is not a failure.

    Returns
    -------
    numpy.ndarray or None
        ``(M,)`` multipliers, or ``None`` when there is nothing to scale by.
    """
    from ..analysis.putty import putty_scale_factors, smooth_scale_factors

    if values is None:
        return None
    per_residue = np.asarray(values, dtype=float).ravel()
    if per_residue.size == 0:
        return None

    m = int(path.shape[0])
    if per_residue.size == 1:
        resampled = np.full(m, per_residue[0], dtype=float)
    else:
        resampled = np.interp(
            np.linspace(0.0, 1.0, m),
            np.linspace(0.0, 1.0, per_residue.size),
            per_residue,
        )

    scale = putty_scale_factors(
        resampled,
        transform=str(cfg.get("putty_transform", "normalized_nonlinear")),
        scale_power=float(cfg.get("putty_scale_power", 1.5)),
        scale_range=float(cfg.get("putty_range", 2.0)),
        scale_min=float(cfg.get("putty_scale_min", 0.6)),
        scale_max=float(cfg.get("putty_scale_max", 4.0)),
    )
    return smooth_scale_factors(scale, window=int(cfg.get("putty_window", 1)))


def _generate_cartoon_tube_arrays(
    coords: np.ndarray,
    colors: Optional[np.ndarray],
    trace_ups: Optional[np.ndarray] = None,
    base_radius: float = 0.5,
    segments_circle: int = 14,
    subdivisions: int = 6,
    *,
    style: str = "tube",
    ss_codes: Optional[np.ndarray] = None,
    config: Optional[dict] = None,
    putty_values: Optional[np.ndarray] = None,
) -> Optional[tuple[np.ndarray, np.ndarray, np.ndarray, Optional[np.ndarray]]]:
    """Return (vertices, normals, faces, colors) for the cartoon mesh.

    When ``style='ribbon'`` (the default), the cartoon uses PyMOL-style
    per-secondary-structure shapes: oval helices, rectangular strands
    with arrowheads, and round loop tubes.

    When ``style='tube'``, a uniform tube is used for all residues.
    """
    style_l = str(style or "tube").lower()

    arr = np.asarray(coords, dtype=float)
    if arr.ndim != 2 or arr.shape[0] < 2:
        return None

    n = arr.shape[0]
    col_arr: Optional[np.ndarray] = None
    if colors is not None:
        col_arr = np.asarray(colors, dtype=float)
        if col_arr.shape[0] != n:
            col_arr = None

    cfg = config or {}
    coordinate_scale = float(cfg.get("coordinate_scale", 1.0))
    subdivisions = int(cfg.get("cartoon_sampling", cfg.get("subdivisions", subdivisions)))
    segments_circle = int(cfg.get("tube_quality", cfg.get("segments_circle", segments_circle)))

    # -- Secondary-structure codes, needed before sampling so the strand path
    #    can be de-pleated first --
    ss_arr: Optional[np.ndarray] = None
    if ss_codes is not None:
        try:
            candidate = np.array(
                [str(s).upper()[:1] if s is not None else "" for s in ss_codes]
            )
            if candidate.shape[0] == n:
                ss_arr = candidate
        except Exception:
            ss_arr = None

    # -- Per-residue orientations, read before the smoothing passes so they can
    #    be smoothed alongside the path, as PyMOL does --
    ups_arr: Optional[np.ndarray] = None
    if trace_ups is not None:
        try:
            candidate_ups = np.asarray(trace_ups, dtype=float)
            if candidate_ups.shape[0] == n:
                ups_arr = candidate_ups
        except Exception:
            ups_arr = None

    # -- Smooth loops: PyMOL's ``cartoon_smooth_loops``, off by default, and run
    #    before the sheet pass as in RepCartoonGeneratePoints --
    if ss_arr is not None and bool(cfg.get("smooth_loops", False)):
        arr, ups_arr = _smooth_loop_path(
            arr,
            ~np.isin(ss_arr, ["H", "S", "E"]),
            cycles=int(cfg.get("smooth_cycles", 2)),
            first=int(cfg.get("smooth_first", 1)),
            last=int(cfg.get("smooth_last", 1)),
            ups=ups_arr,
        )

    # -- Flat sheets: smooth the beta-strand backbone before anything is
    #    derived from it, so both the ribbon path and its tangents come from the
    #    de-pleated trace (PyMOL's ``cartoon_flat_sheets``) --
    if ss_arr is not None and bool(cfg.get("flat_sheets", True)):
        arr, ups_arr = _flatten_sheet_path(
            arr,
            np.isin(ss_arr, ["S", "E"]),
            cycles=int(cfg.get("flat_cycles", 4)),
            ups=ups_arr,
        )

    # -- Per-residue guide frames, computed before sampling because PyMOL's
    #    curve is thrown along the *tangents* -- so the strand-tip re-aiming and
    #    the orientation refinement feed through into the drawn shape --
    guide = None
    if ups_arr is not None and build_guide_frames is not None:
        try:
            guide = build_guide_frames(
                arr,
                _refine_orientations(arr, ups_arr, ss_codes),
                is_helix=None if ss_arr is None else (ss_arr == "H"),
                is_sheet=None if ss_arr is None else np.isin(ss_arr, ["S", "E"]),
                refine_normals_enabled=bool(cfg.get("refine_normals", True)),
                refine_tips=float(cfg.get("refine_tips", 10.0)),
            )
        except Exception:
            guide = None

    # -- Stage 1: Sample path --
    #
    # PyMOL's curve is a linear blend with a tangent-driven throw whose size
    # scales with the segment length, not a Catmull-Rom spline; see
    # :mod:`.spline`. It is used whenever a guide frame is available, since the
    # throw needs the per-residue tangents. Catmull-Rom remains the fallback for
    # geometry that has no orientation data at all (raw coordinate objects).
    path_colors = col_arr
    ups_path: Optional[np.ndarray] = None
    tangent_path: Optional[np.ndarray] = None
    if guide is not None and sample_cartoon_curve is not None:
        try:
            path, ups_path, weights = sample_cartoon_curve(
                arr,
                guide.tangents,
                sampling=subdivisions,
                orientations=guide.orientations,
                throw=float(cfg.get("throw", 1.35)),
                power=float(cfg.get("power", 2.0)),
                power_b=float(cfg.get("power_b", 0.52)),
            )
            path_colors = _interpolate_residue_colors(
                col_arr, weights, subdivisions, arr.shape[0]
            )
            tangent_path = _sample_orientations(
                guide.tangents, subdivisions=subdivisions
            )
        except Exception:
            guide = None

    if guide is None or ups_path is None:
        tension = float(cfg.get("spline_tension", 0.0))
        try:
            path, path_colors = _sample_path(
                arr, col_arr, subdivisions=subdivisions, tension=tension
            )
        except Exception:
            path = arr
            path_colors = col_arr

    m = path.shape[0]
    if m < 2:
        return None

    # -- Round helices: lift the spline back onto the helix cylinder so the
    #    ribbon does not pinch inward between residues (PyMOL's
    #    ``cartoon_round_helices``, on by default) --
    if ss_arr is not None and bool(cfg.get("round_helices", True)):
        path = _round_helix_path(path, arr, ss_arr == "H", subdivisions)

    # -- Build frames --
    tangents, up_vectors = _propagate_ups(path, ups_path)
    if tangent_path is not None and tangent_path.shape[0] == tangents.shape[0]:
        # Blend the per-residue tangents in where they are defined: the spline's
        # own tangent is smooth and correct in the interior, but it knows nothing
        # about the strand-tip aiming, which only the guide frame carries.
        valid = np.linalg.norm(tangent_path, axis=1) > 1e-9
        tangents[valid] = tangent_path[valid]
        up_vectors = _orthogonalise_ups(tangents, up_vectors)
    frames = _build_frames(tangents, up_vectors)

    if style_l in ("tube", "putty"):
        segments = max(int(segments_circle), 6)
        if style_l == "putty":
            # A putty tube is the same extrusion with a per-point radius, which
            # is why `_extrude_shape` takes `vert_scale` at all.
            tube_radius = (
                float(cfg.get("putty_radius", 0.4)) * coordinate_scale
            )
            vert_scale = _putty_vert_scale(path, cfg, putty_values)
        else:
            tube_radius = (
                float(cfg.get("tube_radius", base_radius)) * coordinate_scale
            )
            vert_scale = None
        sv, sn = _make_circle_shape(segments, tube_radius)
        return _extrude_shape(
            path, frames, sv, sn, path_colors, cap_ends=True,
            vert_scale=vert_scale,
        )

    # -- Ribbon / PyMOL-style automatic --
    n_segments = max(int(cfg.get("profile_segments", 10)), 6)
    oval_quality = max(int(cfg.get("oval_quality", n_segments)), 6)
    loop_quality = max(int(cfg.get("loop_quality", 8)), 4)

    oval_width = float(cfg.get("oval_width", 0.25)) * coordinate_scale
    oval_length = float(cfg.get("oval_length", 1.35)) * coordinate_scale
    rect_width = float(cfg.get("rect_width", 0.4)) * coordinate_scale
    rect_length = float(cfg.get("rect_length", 1.4)) * coordinate_scale
    loop_radius = float(cfg.get("loop_radius", 0.2)) * coordinate_scale
    arrow_sampling_residues = max(int(cfg.get("arrow_sampling", 2)), 1)

    # Also support legacy ss_shapes config for backward compatibility. Prefer
    # modern fixed scene-unit keys when present so cartoon thickness does not
    # grow with molecule radius.
    ss_shapes = cfg.get("ss_shapes") or {}
    modern_keys = {"oval_width", "oval_length", "rect_width", "rect_length", "loop_radius"}
    if ss_shapes and not modern_keys.intersection(cfg):
        h_cfg = ss_shapes.get("helix", {})
        oval_width = float(h_cfg.get("width", 0.25)) * coordinate_scale
        oval_length = float(h_cfg.get("thickness", 1.35)) * coordinate_scale
        s_cfg = ss_shapes.get("strand", {})
        rect_width = float(s_cfg.get("width", 0.4)) * coordinate_scale
        rect_length = float(s_cfg.get("thickness", 1.4)) * coordinate_scale
        c_cfg = ss_shapes.get("coil", {})
        loop_radius = float(c_cfg.get("width", 0.2)) * coordinate_scale

    # -- Build shapes --
    oval_sv, oval_sn = _make_oval_shape(oval_quality, oval_width, oval_length)
    rect_sv, rect_sn = _make_rectangle_shape(rect_width, rect_length)
    loop_sv, loop_sn = _make_circle_shape(loop_quality, loop_radius)

    # -- Segment by SS (or fallback to uniform tube) --
    segments = _segment_ss(ss_codes)

    if not segments:
        # No SS data — use a uniform tube
        n_seg = max(int(segments_circle), 6)
        tube_radius = float(cfg.get("tube_radius", base_radius)) * coordinate_scale
        sv, sn = _make_circle_shape(n_seg, tube_radius)
        return _extrude_shape(
            path, frames, sv, sn, path_colors, cap_ends=True,
        )

    # -- Extrude each segment --
    all_verts: list[np.ndarray] = []
    all_norms: list[np.ndarray] = []
    all_faces: list[np.ndarray] = []
    all_cols: list[np.ndarray] = []
    vert_offset = 0

    for seg in segments:
        ss_t = seg["ss_type"]
        s_res = seg["start"]
        e_res = seg["end"]
        if e_res - s_res < 1:
            continue
        s_path = _residue_to_path_index(s_res, n, m)
        # Match PyMOL's sampling across cartoon-type boundaries: a block
        # covers the segment up to the next residue anchor, otherwise the
        # interpolated samples between SS blocks are dropped and gaps appear.
        e_anchor = min(e_res, n - 1)
        e_path = _residue_to_path_index(e_anchor, n, m) + 1
        if e_path - s_path < 2:
            continue

        seg_path = path[s_path:e_path]
        seg_frames = frames[s_path:e_path]
        seg_colors = path_colors[s_path:e_path] if path_colors is not None else None

        if ss_t == "E":
            # Strand: rectangle + arrowhead. ``arrow_sampling`` is expressed in
            # residues, but the arrow is cut out of the *sampled* path, so it
            # has to be converted to path points — otherwise a 2 means two
            # spline samples (a fraction of one residue) and the arrow is too
            # small to see. Leave at least two points for the body.
            seg_points = e_path - s_path
            arrow_samp = int(round(arrow_sampling_residues * max(subdivisions, 1)))
            arrow_samp = max(min(arrow_samp, seg_points - 2), 1)
            result = _extrude_arrowhead(
                seg_path, seg_frames, rect_sv, rect_sn,
                seg_colors, arrow_samp,
            )
        elif ss_t == "H":
            # Helix: oval
            result = _extrude_shape(
                seg_path, seg_frames, oval_sv, oval_sn,
                seg_colors, cap_first=(s_res == 0), cap_last=(e_res >= n),
            )
        else:
            # Loop: tube
            result = _extrude_shape(
                seg_path, seg_frames, loop_sv, loop_sn,
                seg_colors, cap_first=(s_res == 0), cap_last=(e_res >= n),
            )

        if result is not None:
            v, nrm, f, c = result
            f = f + vert_offset
            all_verts.append(v)
            all_norms.append(nrm)
            all_faces.append(f)
            if c is not None:
                all_cols.append(c)
            vert_offset += v.shape[0]

    if not all_verts:
        return None

    out_verts = np.concatenate(all_verts, axis=0)
    out_norms = np.concatenate(all_norms, axis=0)
    out_faces = np.concatenate(all_faces, axis=0)
    out_cols = np.concatenate(all_cols, axis=0) if all_cols else None

    return out_verts, out_norms, out_faces, out_cols


# ---------------------------------------------------------------------------
# Trace path (simple smoothed line)
# ---------------------------------------------------------------------------

def _generate_trace_arrays(
    coords: np.ndarray,
    colors: Optional[np.ndarray],
    subdivisions: int = 5,
) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    return _sample_path(coords, colors, subdivisions=subdivisions)


# ---------------------------------------------------------------------------
# Up-vector builder
# ---------------------------------------------------------------------------

def backbone_index_map(
    atoms: np.ndarray,
    res_ids: Optional[np.ndarray],
    chain_ids: Optional[np.ndarray] = None,
) -> Optional[np.ndarray]:
    """Locate each residue's N, C and O atoms once, as an index array.

    Which atom of ``atoms`` is residue *i*'s backbone nitrogen is a fact about
    **topology**, not about coordinates: it is the same in every frame of a
    trajectory. Separating it out is what lets :func:`_build_trace_ups` be a
    handful of array operations on a moving structure instead of a per-residue
    Python loop -- the loop it replaces compared every atom's residue id against
    every residue's, which is ``n_res * n_atoms`` comparisons per frame, plus a
    full ``astype(str)`` pass over the atom names.

    Parameters
    ----------
    atoms : numpy.ndarray
        Structured atom array with at least ``res_id`` and ``atom_name``.
    res_ids : numpy.ndarray
        Residue ids, in the order the cartoon walks them.
    chain_ids : numpy.ndarray, optional
        Chain of each residue. Needed whenever residue numbering restarts per
        chain, which is the normal case.

    Returns
    -------
    numpy.ndarray or None
        ``(n_res, 3)`` of atom indices in ``N, C, O`` order, ``-1`` where the
        residue does not have that atom. ``None`` when the atom array cannot
        supply the fields.
    """
    if res_ids is None or not isinstance(atoms, np.ndarray):
        return None
    fields = set(atoms.dtype.fields or {})
    if not {"res_id", "atom_name"}.issubset(fields):
        return None
    try:
        atom_res_id = np.asarray(atoms["res_id"]).astype(np.int64, copy=False)
        atom_names = np.char.strip(atoms["atom_name"].astype(str))
    except Exception:
        return None

    n = len(res_ids)
    try:
        res_id_arr = np.asarray(res_ids).astype(np.int64, copy=False)
    except Exception:
        return None

    # Fold (chain, res_id) into one integer key so residues can be matched with
    # a single searchsorted rather than a mask per residue. Chains are encoded
    # over the union of both sides so the codes agree.
    if "chain" in fields and chain_ids is not None:
        try:
            atom_chain = np.char.strip(atoms["chain"].astype(str))
            res_chain = np.char.strip(np.asarray(chain_ids).astype(str))
            _codes, inverse = np.unique(
                np.concatenate([atom_chain, res_chain]), return_inverse=True
            )
            atom_chain_code = inverse[: atom_chain.shape[0]].astype(np.int64)
            res_chain_code = inverse[atom_chain.shape[0]:].astype(np.int64)
        except Exception:
            atom_chain_code = np.zeros(atom_res_id.shape[0], dtype=np.int64)
            res_chain_code = np.zeros(n, dtype=np.int64)
    else:
        atom_chain_code = np.zeros(atom_res_id.shape[0], dtype=np.int64)
        res_chain_code = np.zeros(n, dtype=np.int64)

    if atom_res_id.size == 0 or n == 0:
        return np.full((n, 3), -1, dtype=np.int64)
    lo = int(min(atom_res_id.min(), res_id_arr.min()))
    span = int(max(atom_res_id.max(), res_id_arr.max())) - lo + 1
    atom_key = atom_chain_code * span + (atom_res_id - lo)
    res_key = res_chain_code * span + (res_id_arr - lo)

    out = np.full((n, 3), -1, dtype=np.int64)
    atom_index = np.arange(atom_key.shape[0], dtype=np.int64)
    # Looked up residue -> atom, not atom -> residue. The distinction matters
    # whenever two residues share a key, which happens for every multi-chain
    # structure whose chains are not being distinguished (1RTD: 2028 residues,
    # 554 distinct numbers). Each of them takes the same first matching atom,
    # as the per-residue mask did; an atom -> residue map would instead hand the
    # atoms to one row and leave the others without a backbone.
    for column, name in enumerate(("N", "C", "O")):
        sel = atom_names == name
        if not np.any(sel):
            continue
        keys = atom_key[sel]
        indices = atom_index[sel]
        # Sorted by key, then by atom index, so the leftmost hit is the first
        # such atom in file order -- which is the one the loop picked.
        order = np.lexsort((indices, keys))
        keys = keys[order]
        indices = indices[order]
        pos = np.searchsorted(keys, res_key, side="left")
        in_range = pos < keys.shape[0]
        found = np.zeros(n, dtype=bool)
        found[in_range] = keys[pos[in_range]] == res_key[in_range]
        out[found, column] = indices[pos[found]]
    return out


def _build_trace_ups(
    atoms: np.ndarray,
    res_ids: Optional[np.ndarray],
    ca_coords: Optional[np.ndarray],
    chain_ids: Optional[np.ndarray] = None,
    index_map: Optional[np.ndarray] = None,
) -> Optional[np.ndarray]:
    """Per-residue ribbon orientation from the peptide plane.

    ``vo = normalize((N - C) x (N - O))``, as PyMOL's
    ``RepCartoonGeneratePASS1`` does. Far more stable than the raw C->O
    carbonyl direction, and it is what lets the downstream round-helix and
    flat-sheet refinement produce untwisted ribbons. Falls back to C->O, then
    ``+Z``, where backbone atoms are missing.

    Parameters
    ----------
    index_map : numpy.ndarray, optional
        Result of :func:`backbone_index_map`. Pass it across the frames of a
        trajectory -- it depends only on topology, and recomputing it is what
        made this the most expensive step of a frame change.
    """
    if res_ids is None or ca_coords is None:
        return None
    if not isinstance(atoms, np.ndarray):
        return None
    fields = set(atoms.dtype.fields or {})
    if not {"res_id", "atom_name", "xyz"}.issubset(fields):
        return None
    try:
        atom_xyz = np.asarray(atoms["xyz"], dtype=float)
    except Exception:
        return None

    n = len(res_ids)
    if index_map is None or getattr(index_map, "shape", None) != (n, 3):
        index_map = backbone_index_map(atoms, res_ids, chain_ids)
    if index_map is None:
        return None

    idx_n = index_map[:, 0]
    idx_c = index_map[:, 1]
    idx_o = index_map[:, 2]
    ups = np.zeros((n, 3), dtype=float)
    ups[:, 2] = 1.0  # the fallback, overwritten wherever the backbone allows

    # Peptide-plane normal, for every residue that has all three atoms, in one
    # batched cross product.
    full = (idx_n >= 0) & (idx_c >= 0) & (idx_o >= 0)
    if np.any(full):
        rows = np.nonzero(full)[0]
        nn = atom_xyz[idx_n[rows]]
        cc = atom_xyz[idx_c[rows]]
        oo = atom_xyz[idx_o[rows]]
        plane = _batch_cross(nn - cc, nn - oo)
        good = np.sqrt(np.einsum("ij,ij->i", plane, plane)) > 1e-8
        ups[rows[good]] = plane[good]
        full[rows[~good]] = False  # degenerate plane -> fall through to C->O

    # C->O for the rest, where both atoms are present.
    carbonyl = (~full) & (idx_c >= 0) & (idx_o >= 0)
    if np.any(carbonyl):
        rows = np.nonzero(carbonyl)[0]
        ups[rows] = atom_xyz[idx_c[rows]] - atom_xyz[idx_o[rows]]

    lengths = np.sqrt(np.einsum("ij,ij->i", ups, ups))
    zero = lengths <= 0.0
    if np.any(zero):
        ups[zero] = (0.0, 0.0, 1.0)
        lengths[zero] = 1.0
    ups /= lengths[:, None]

    # Global sign continuity only; the per-SS refinement (round helices, flat
    # sheets, anti-twist propagation) happens in _refine_orientations once the
    # secondary structure is known.
    #
    # Sequential in appearance, but not in fact: flipping residue i whenever it
    # opposes the *already flipped* i-1 makes the sign a running product of the
    # raw pairwise signs, so a cumprod does the whole scan at once.
    _flip_for_sign_continuity(ups)
    return ups


def _newell_normal(coords: np.ndarray) -> np.ndarray:
    """Calculate the normal vector of a polygon using Newell's method.

    Parameters
    ----------
    coords : np.ndarray
        Array of shape (N, 3) representing the coordinates of the polygon.

    Returns
    -------
    np.ndarray
        A unit normal vector of shape (3,).
    """
    normal = np.zeros(3, dtype=float)
    n = len(coords)
    for i in range(n):
        curr = coords[i]
        nxt = coords[(i + 1) % n]
        normal[0] += (curr[1] - nxt[1]) * (curr[2] + nxt[2])
        normal[1] += (curr[2] - nxt[2]) * (curr[0] + nxt[0])
        normal[2] += (curr[0] - nxt[0]) * (curr[1] + nxt[1])
    norm = float(np.linalg.norm(normal))
    if norm > 1e-6:
        return normal / norm
    return np.array([0.0, 0.0, 1.0], dtype=float)


def _generate_prism_mesh(
    coords: np.ndarray,
    thickness: float,
    color: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Generate a 3D prism mesh from a flat polygon.

    Parameters
    ----------
    coords : np.ndarray
        Coordinates of the polygon vertices, shape (N, 3).
    thickness : float
        Thickness of the extruded prism.
    color : np.ndarray
        RGBA color vector, shape (4,).

    Returns
    -------
    tuple of np.ndarray
        Tuple of (vertices, normals, faces, colors).
    """
    n = len(coords)
    normal = _newell_normal(coords)

    half_thick = thickness / 2.0
    verts_top = coords + normal * half_thick
    verts_bottom = coords - normal * half_thick

    center = coords.mean(axis=0)
    center_top = center + normal * half_thick
    center_bottom = center - normal * half_thick

    verts = []
    norms = []
    faces = []

    # 1. Top cap
    idx_center_top = 0
    verts.append(center_top)
    norms.append(normal)
    for v in verts_top:
        verts.append(v)
        norms.append(normal)
    for i in range(1, n):
        faces.append([idx_center_top, i, i + 1])
    faces.append([idx_center_top, n, 1])

    # 2. Bottom cap
    idx_center_bottom = len(verts)
    verts.append(center_bottom)
    norms.append(-normal)
    for v in verts_bottom:
        verts.append(v)
        norms.append(-normal)
    for i in range(1, n):
        faces.append([idx_center_bottom, idx_center_bottom + i + 1, idx_center_bottom + i])
    faces.append([idx_center_bottom, idx_center_bottom + 1, idx_center_bottom + n])

    # 3. Side faces
    for i in range(n):
        i_next = (i + 1) % n
        v_top_curr = verts_top[i]
        v_top_next = verts_top[i_next]

        edge = v_top_next - v_top_curr
        side_norm = np.cross(edge, normal)
        sn = float(np.linalg.norm(side_norm))
        if sn > 1e-6:
            side_norm /= sn
        else:
            side_norm = np.array([0.0, 1.0, 0.0], dtype=float)

        idx_vt_curr = len(verts)
        verts.append(v_top_curr)
        norms.append(side_norm)

        idx_vt_next = len(verts)
        verts.append(v_top_next)
        norms.append(side_norm)

        idx_vb_curr = len(verts)
        verts.append(verts_bottom[i])
        norms.append(side_norm)

        idx_vb_next = len(verts)
        verts.append(verts_bottom[i_next])
        norms.append(side_norm)

        faces.append([idx_vb_curr, idx_vt_curr, idx_vt_next])
        faces.append([idx_vb_curr, idx_vt_next, idx_vb_next])

    verts_arr = np.asarray(verts, dtype=float)
    norms_arr = np.asarray(norms, dtype=float)
    faces_arr = np.asarray(faces, dtype=np.int32)
    colors_arr = np.tile(color, (len(verts), 1))

    return verts_arr, norms_arr, faces_arr, colors_arr


def _generate_cylinder(
    p1: np.ndarray,
    p2: np.ndarray,
    radius: float,
    color: np.ndarray,
    segments: int = 8,
) -> Optional[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
    """Generate a capped cylinder connecting two points.

    Parameters
    ----------
    p1 : np.ndarray
        Start coordinate, shape (3,).
    p2 : np.ndarray
        End coordinate, shape (3,).
    radius : float
        Cylinder radius.
    color : np.ndarray
        RGBA color vector, shape (4,).
    segments : int, optional
        Number of circle segments for the cylinder.

    Returns
    -------
    tuple of np.ndarray, or None
        Tuple of (vertices, normals, faces, colors).
    """
    d = p2 - p1
    dn = float(np.linalg.norm(d))
    if dn <= 1e-6:
        return None
    direction = d / dn

    up = _default_up_from_tangent(direction)
    side = np.cross(direction, up)
    sn = float(np.linalg.norm(side))
    if sn > 0.0:
        side /= sn
    else:
        side = np.array([0.0, 1.0, 0.0], dtype=float)
    up = np.cross(side, direction)

    frame = np.column_stack([side, up, direction])
    frames = np.array([frame, frame])
    path = np.array([p1, p2])

    sv, sn_shape = _make_circle_shape(segments, radius)
    colors = np.array([color, color])

    res = _extrude_shape(path, frames, sv, sn_shape, colors, cap_ends=True)
    return res


def _uv_sphere(
    center: np.ndarray,
    radius: float,
    color: np.ndarray,
    lat: int = 3,
    lon: int = 6,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Small UV sphere used to round the joints of a ring rim."""
    verts = []
    norms = []
    ncols = lon + 1
    for i in range(lat + 1):
        theta = math.pi * i / lat
        st, ct = math.sin(theta), math.cos(theta)
        for j in range(lon + 1):
            phi = 2.0 * math.pi * j / lon
            nrm = np.array([st * math.cos(phi), ct, st * math.sin(phi)], dtype=float)
            verts.append(center + radius * nrm)
            norms.append(nrm)
    faces = []
    for i in range(lat):
        for j in range(lon):
            a = i * ncols + j
            b = a + ncols
            faces.append([a, b, a + 1])
            faces.append([a + 1, b, b + 1])
    v = np.asarray(verts, dtype=float)
    n = np.asarray(norms, dtype=float)
    f = np.asarray(faces, dtype=np.int32)
    c = np.tile(color, (len(v), 1))
    return v, n, f, c


def _generate_filled_ring_mesh(
    coords: np.ndarray,
    thickness: float,
    color: np.ndarray,
    rim_radius: float,
    rim_segments: int = 8,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """PyMOL ``cartoon_ring_mode`` 3-style base ring.

    A flat filled polygon (both faces) plus a rounded tube tracing the ring
    perimeter with a small sphere at each vertex, so the base reads as a solid
    tile with a beveled edge rather than a thin flat sheet.

    Parameters
    ----------
    coords : np.ndarray
        Ring vertex coordinates ordered around the perimeter, shape ``(N, 3)``.
    thickness : float
        Thickness of the flat filled interior.
    color : np.ndarray
        RGBA colour, shape ``(4,)``.
    rim_radius : float
        Radius of the rounded perimeter tube.
    rim_segments : int
        Circular segments for the perimeter cylinders.
    """
    parts: list[tuple] = []
    fill = _generate_prism_mesh(coords, thickness, color)
    if fill is not None:
        parts.append(fill)

    n = len(coords)
    for i in range(n):
        p1 = coords[i]
        p2 = coords[(i + 1) % n]
        cyl = _generate_cylinder(p1, p2, rim_radius, color, segments=rim_segments)
        if cyl is not None:
            parts.append(cyl)
        parts.append(_uv_sphere(np.asarray(p1, dtype=float), rim_radius, color))

    if not parts:
        return None

    all_v, all_n, all_f, all_c = [], [], [], []
    off = 0
    for v, nrm, f, c in parts:
        all_v.append(v)
        all_n.append(nrm)
        all_f.append(np.asarray(f) + off)
        all_c.append(c)
        off += len(v)
    return (
        np.concatenate(all_v, axis=0),
        np.concatenate(all_n, axis=0),
        np.concatenate(all_f, axis=0),
        np.concatenate(all_c, axis=0),
    )


def _generate_nucleic_cartoon_arrays(
    atoms: np.ndarray,
    coords_all: np.ndarray,
    res_ids: np.ndarray,
    chain_ids: np.ndarray,
    colors: Optional[np.ndarray],
    config: Optional[dict] = None,
) -> Optional[tuple[np.ndarray, np.ndarray, np.ndarray, Optional[np.ndarray]]]:
    """Generate ladders and rings for nucleic acids (DNA/RNA).

    Parameters
    ----------
    atoms : np.ndarray
        Structured array of all atoms in the structure.
    coords_all : np.ndarray
        Scaled and centered coordinates of all atoms, shape (N, 3).
    res_ids : np.ndarray
        Residue IDs along the backbone trace.
    chain_ids : np.ndarray
        Chain IDs along the backbone trace.
    colors : np.ndarray or None
        RGBA colors for each residue in the trace.
    config : dict, optional
        Display config dictionary.

    Returns
    -------
    tuple of np.ndarray, or None
        Tuple of (vertices, normals, faces, colors).
    """
    if atoms is None or coords_all is None or res_ids is None or len(res_ids) == 0:
        return None

    # Deduplicate residues to avoid processing the same residue multiple times
    # (this can happen when the CA trace includes multiple backbone atoms per residue)
    if len(res_ids) > 0 and chain_ids is not None:
        seen = set()
        unique_indices = []
        for i in range(len(res_ids)):
            key = (res_ids[i], chain_ids[i])
            if key not in seen:
                seen.add(key)
                unique_indices.append(i)
        res_ids = np.asarray(res_ids)[unique_indices]
        chain_ids = np.asarray(chain_ids)[unique_indices] if chain_ids is not None else None
        # Note: we don't deduplicate coords_all here because it's used for atom lookup below

    cfg = config or {}
    coordinate_scale = float(cfg.get("coordinate_scale", 1.0))
    ladder_radius = float(cfg.get("ladder_radius", 0.12)) * coordinate_scale
    ring_thickness = float(cfg.get("ring_thickness", 0.09)) * coordinate_scale
    # BUGFIX: do NOT pre-scale the backbone radius here. It is forwarded as
    # ``base_radius`` to ``_generate_cartoon_tube_arrays``, whose tube branch
    # applies ``coordinate_scale`` once. Pre-scaling caused a double scale
    # (``base * scale**2``), bloating the DNA/RNA backbone tube.
    backbone_radius = float(cfg.get("backbone_radius", 0.4))
    backbone_quality = int(cfg.get("backbone_quality", 18))
    smooth_cycles = int(cfg.get("backbone_smooth_cycles", 2))
    smooth_window = int(cfg.get("backbone_smooth_window", 1))
    tension = float(cfg.get("spline_tension", 0.3))
    trace_atoms = list(
        cfg.get(
            "nucleic_trace_atoms",
            # C4' first (NGL: smoother than the zig-zagging P); star-notation
            # variants (C4*) included because PDBs mix ' and * sugar naming.
            ["C4'", "C4*", "C3'", "C3*", "C5'", "C5*", "O5'", "O5*",
             "P", "O3'", "O3*", "C1'", "C1*"],
        )
    )
    ao_radius = float(cfg.get("nucleic_ao_radius", 6.0)) * coordinate_scale
    ao_max = int(cfg.get("nucleic_ao_max_neighbors", 16))
    ao_strength = float(cfg.get("nucleic_ao_strength", 0.4))
    # Base-ring style: "pymol" = filled ring + rounded perimeter rim
    # (cartoon_ring_mode 3 look); "filled" = plain flat plate.
    ring_style = str(cfg.get("ring_style", "pymol")).lower()
    ring_rim_radius = float(cfg.get("ring_rim_radius", 0.08)) * coordinate_scale
    rim_quality = int(cfg.get("ring_rim_quality", 8))

    def _ring_mesh(ring_coords):
        if ring_style == "pymol":
            return _generate_filled_ring_mesh(
                ring_coords, ring_thickness, res_color,
                rim_radius=ring_rim_radius, rim_segments=rim_quality,
            )
        return _generate_prism_mesh(ring_coords, ring_thickness, res_color)



    fields = set(atoms.dtype.fields or {})
    if not {"res_id", "atom_name"}.issubset(fields):
        return None

    atom_res_ids = np.asarray(atoms["res_id"])
    try:
        atom_names = np.char.strip(atoms["atom_name"].astype(str))
    except Exception:
        atom_names = np.array([str(n).strip() for n in atoms["atom_name"]])

    try:
        atom_names_u = np.char.upper(atom_names)
    except Exception:
        atom_names_u = np.array([str(t).upper() for t in atom_names])

    if "chain" in fields:
        try:
            atom_chains = np.char.strip(atoms["chain"].astype(str))
        except Exception:
            atom_chains = np.array([str(c).strip() for c in atoms["chain"]])
    else:
        atom_chains = np.array([""] * len(atoms), dtype=object)

    all_verts = []
    all_norms = []
    all_faces = []
    all_colors = []
    vert_offset = 0

    def add_mesh(v, n, f, c):
        nonlocal vert_offset
        if v is not None and len(v) > 0:
            all_verts.append(v)
            all_norms.append(n)
            all_faces.append(f + vert_offset)
            if c is not None:
                all_colors.append(c)
            vert_offset += len(v)

    pyr_ring_names = ["N1", "C2", "N3", "C4", "C5", "C6"]
    pur_ring6_names = ["N1", "C2", "N3", "C4", "C5", "C6"]
    pur_ring5_names = ["C4", "C5", "N7", "C8", "N9"]
    
    # Collect backbone coordinates (C4' or P) for backbone trace
    backbone_coords = []
    backbone_colors = []
    backbone_chains = []

    # --- AO pre-pass: one representative point per residue (base-ring centroid,
    #     else C1', else atom mean) so stacked/paired bases self-shade, matching
    #     the protein cartoon path. View-independent, no shader change. ---
    base_ring_all = ["N1", "C2", "N3", "C4", "C5", "C6", "N7", "C8", "N9"]
    rep_pts: list[np.ndarray] = []
    rep_idx: list[int] = []
    for i, rid in enumerate(res_ids):
        chain_id = str(chain_ids[i]).strip() if chain_ids is not None else ""
        mask = (atom_res_ids == rid) & (atom_chains == chain_id)
        if not np.any(mask):
            continue
        names_i = atom_names_u[mask]
        coords_i = coords_all[mask]
        lut = {nm: c for nm, c in zip(names_i, coords_i)}
        ring = [lut[n] for n in base_ring_all if n in lut]
        if ring:
            rep = np.mean(ring, axis=0)
        elif "C1'" in lut:
            rep = lut["C1'"]
        else:
            rep = coords_i.mean(axis=0)
        rep_pts.append(rep)
        rep_idx.append(i)

    shade_by_i: dict[int, float] = {}
    if len(rep_pts) >= 2 and ao_strength > 0.0 and _estimate_ambient_occlusion is not None:
        try:
            occ = _estimate_ambient_occlusion(
                np.asarray(rep_pts, dtype=float),
                radius=ao_radius,
                max_neighbors=ao_max,
            )
        except Exception:
            occ = None
        if occ is not None and len(occ) == len(rep_idx):
            occ = np.asarray(occ, dtype=float)
            for k, i in enumerate(rep_idx):
                shade_by_i[i] = (1.0 - ao_strength) + ao_strength * (1.0 - occ[k])

    for i, rid in enumerate(res_ids):
        chain_id = str(chain_ids[i]).strip() if chain_ids is not None else ""

        mask = (atom_res_ids == rid) & (atom_chains == chain_id)
        if not np.any(mask):
            continue

        res_atom_names = atom_names_u[mask]
        res_coords = coords_all[mask]

        atom_to_coord = {}
        for name, coord in zip(res_atom_names, res_coords):
            atom_to_coord[name] = coord

        # Select backbone trace atom. NGL traces the sugar C4'/C3' (smoother
        # than the zig-zagging P atom); P is kept as a fallback. Order is
        # configurable via ``nucleic_trace_atoms``.
        backbone_atom_name = None
        for cand in trace_atoms:
            if cand in atom_to_coord:
                backbone_atom_name = cand
                break

        if backbone_atom_name is None:
            continue

        # Get backbone atom coordinate
        backbone_coord = atom_to_coord[backbone_atom_name]
        res_color = colors[i] if colors is not None else np.array([1.0, 1.0, 1.0, 1.0])
        # Apply per-residue ambient-occlusion shade to backbone tube, ladder
        # and base rings (all inherit ``res_color``).
        shade = shade_by_i.get(i, 1.0)
        if shade != 1.0:
            res_color = np.asarray(res_color, dtype=float).copy()
            res_color[:3] = np.clip(res_color[:3] * shade, 0.0, 1.0)

        # Collect backbone coordinates (P primary, sugar fallback)
        backbone_coords.append(backbone_coord.copy())
        backbone_colors.append(res_color.copy())
        backbone_chains.append(chain_id)
        
        # For ladder and base rings, we need C1' or C1* atom (sugar to base)
        c1_name = None
        for cand in ["C1'", "C1*"]:  # Use sugar atoms for ladder connection
            if cand in atom_to_coord:
                c1_name = cand
                break

        if not c1_name:
            # If we don't have C1'/C1*, skip ladder/rings for this residue
            continue

        c1_coord = atom_to_coord[c1_name]

        is_purine = False
        is_pyrimidine = False
        base_anchor_name = None

        if "N9" in atom_to_coord:
            is_purine = True
            base_anchor_name = "N9"
        elif "N1" in atom_to_coord:
            is_pyrimidine = True
            base_anchor_name = "N1"

        if not base_anchor_name:
            continue

        base_anchor_coord = atom_to_coord[base_anchor_name]

        # Rung: backbone trace point -> C1' (sugar) -> base anchor. C1' sits far
        # off the tube centerline, so a rung that starts at C1' alone looks
        # detached; starting at the backbone trace atom keeps the base visually
        # attached to the tube, and routing through C1' follows the real sugar.
        for seg_a, seg_b in (
            (backbone_coord, c1_coord),
            (c1_coord, base_anchor_coord),
        ):
            cyl = _generate_cylinder(seg_a, seg_b, ladder_radius, res_color)
            if cyl is not None:
                add_mesh(*cyl)
        add_mesh(*_uv_sphere(np.asarray(c1_coord, dtype=float), ladder_radius, res_color))

        if is_purine:
            if all(n in atom_to_coord for n in pur_ring6_names):
                coords6 = np.array([atom_to_coord[n] for n in pur_ring6_names])
                add_mesh(*_ring_mesh(coords6))
            if all(n in atom_to_coord for n in pur_ring5_names):
                coords5 = np.array([atom_to_coord[n] for n in pur_ring5_names])
                add_mesh(*_ring_mesh(coords5))
        elif is_pyrimidine:
            if all(n in atom_to_coord for n in pyr_ring_names):
                coords6 = np.array([atom_to_coord[n] for n in pyr_ring_names])
                add_mesh(*_ring_mesh(coords6))

    # Generate backbone tube (PyMOL mode 4 style — P trace with 5'/3' sugar fallback)
    # Split at chain boundaries so the tube doesn't connect across chains
    if len(backbone_coords) >= 2:
        bb_coords = np.array(backbone_coords, dtype=float)
        bb_colors_arr = np.array(backbone_colors, dtype=float) if backbone_colors else None
        subdivisions = int(cfg.get("cartoon_sampling", 7))

        # Build segment boundaries at chain breaks
        seg_starts = [0]
        for j in range(1, len(backbone_chains)):
            if backbone_chains[j] != backbone_chains[j - 1]:
                seg_starts.append(j)
        seg_starts.append(len(backbone_chains))

        for si in range(len(seg_starts) - 1):
            s, e = seg_starts[si], seg_starts[si + 1]
            if e - s < 2:
                continue
            seg_coords = bb_coords[s:e]
            seg_colors = bb_colors_arr[s:e] if bb_colors_arr is not None else None

            # Pre-smooth control points (PyMOL-style) before splining so the
            # trace doesn't kink between residues, then apply spline tension.
            seg_coords = _smooth_backbone_points(
                seg_coords, cycles=smooth_cycles, window=smooth_window
            )
            bb_smooth, bb_colors_smooth = _sample_path(
                seg_coords, seg_colors, subdivisions=subdivisions, tension=tension
            )

            backbone_arrays = _generate_cartoon_tube_arrays(
                bb_smooth,
                bb_colors_smooth,
                None,
                base_radius=backbone_radius,
                style="tube",
                ss_codes=None,
                config={"coordinate_scale": coordinate_scale, "tube_quality": backbone_quality},
            )

            if backbone_arrays is not None:
                bb_verts, bb_norms, bb_faces, bb_cols = backbone_arrays
                add_mesh(bb_verts, bb_norms, bb_faces, bb_cols)
    
    if not all_verts:
        return None

    out_verts = np.concatenate(all_verts, axis=0)
    out_norms = np.concatenate(all_norms, axis=0)
    out_faces = np.concatenate(all_faces, axis=0)
    out_colors = np.concatenate(all_colors, axis=0) if all_colors else None

    return out_verts, out_norms, out_faces, out_colors


# ---------------------------------------------------------------------------
# Legacy aliases
# ---------------------------------------------------------------------------

_smooth_backbone = _sample_path
_extrude_sweep = _extrude_shape
_build_profile = lambda *a, **kw: {}


__all__ = [
    "_build_trace_ups",
    "backbone_index_map",
    "_generate_cartoon_tube_arrays",
    "_generate_nucleic_cartoon_arrays",
    "_sample_path",
    "_sample_orientations",
    "_generate_trace_arrays",
    "_build_profile",
    "_extrude_sweep",
    "_propagate_ups",
]
