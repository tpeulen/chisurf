from __future__ import annotations

from typing import Optional, Tuple

import math

import numpy as np


def _compute_center_radius(xyz: np.ndarray) -> tuple[np.ndarray, float]:
    """Return (center, radius) bounding sphere approximation."""

    arr = np.asarray(xyz, dtype=float)
    center = arr.mean(axis=0)
    # Use max distance from center as radius
    diffs = arr - center
    dist2 = np.sum(diffs * diffs, axis=1)
    radius = float(math.sqrt(float(dist2.max()))) if dist2.size else 1.0
    if not np.isfinite(radius) or radius <= 0:
        radius = 1.0
    return center, radius


_SPHERE_TEMPLATE_CACHE: dict[int, dict[str, np.ndarray]] = {}


def _get_sphere_template(segments_lat: int = 16, segments_lon: int = 32) -> dict[str, np.ndarray]:
    """Return a cached unit-sphere mesh with normals."""
    key = (segments_lat << 16) | segments_lon
    cached = _SPHERE_TEMPLATE_CACHE.get(key)
    if cached is not None:
        return cached

    phi = np.linspace(0.0, np.pi, segments_lat)
    theta = np.linspace(0.0, 2.0 * np.pi, segments_lon, endpoint=False)
    phi, theta = np.meshgrid(phi, theta, indexing="ij")
    sin_phi = np.sin(phi)
    cos_phi = np.cos(phi)
    cos_theta = np.cos(theta)
    sin_theta = np.sin(theta)

    vertices = np.stack(
        [sin_phi * cos_theta, sin_phi * sin_theta, cos_phi], axis=-1
    ).reshape(-1, 3).astype(np.float32, copy=False)

    normals = vertices.copy()

    faces = []
    for i in range(segments_lat - 1):
        for j in range(segments_lon):
            k0 = i * segments_lon + j
            k1 = i * segments_lon + (j + 1) % segments_lon
            k2 = (i + 1) * segments_lon + j
            k3 = (i + 1) * segments_lon + (j + 1) % segments_lon
            faces.append([k0, k2, k1])
            faces.append([k1, k2, k3])
    faces_arr = np.asarray(faces, dtype=np.int32)

    template = {"vertices": vertices, "normals": normals, "faces": faces_arr}
    _SPHERE_TEMPLATE_CACHE[key] = template
    return template


def _build_sphere_mesh(
    radius: float,
    segments_lat: int = 16,
    segments_lon: int = 32,
) -> Optional[dict[str, np.ndarray]]:
    """Return a procedural sphere approximation with normals.

    Uses a cached unit-sphere template scaled to *radius*. ``segments_lat`` /
    ``segments_lon`` control the tessellation; the default (16 x 32 = 512
    vertices) is smooth for a single large sphere, but atom-ball glyphs — drawn
    thousands at a time and small on screen — should request a much coarser
    sphere so the merged mesh stays light for both the CPU build and the GPU.
    """

    r = float(radius)
    if not np.isfinite(r) or r <= 0.0:
        return None

    template = _get_sphere_template(int(segments_lat), int(segments_lon))
    verts = template["vertices"] * r
    norms = template["normals"].copy()  # unit normals stay the same
    faces = template["faces"]
    return {"vertices": verts, "normals": norms, "faces": faces}


_CYLINDER_TEMPLATE_CACHE: dict[int, dict[str, np.ndarray]] = {}


def _get_cylinder_template(segments_circle: int = 12) -> Optional[dict[str, np.ndarray]]:
    """Return cached unit-length cylinder template aligned with the +Z axis."""

    seg = max(3, int(segments_circle))
    template = _CYLINDER_TEMPLATE_CACHE.get(seg)
    if template is not None:
        return template

    angles = np.linspace(0.0, 2.0 * np.pi, seg, endpoint=False, dtype=float)
    cos = np.cos(angles)
    sin = np.sin(angles)

    bottom = np.column_stack((cos, sin, np.zeros(seg, dtype=float)))
    top = np.column_stack((cos, sin, np.ones(seg, dtype=float)))

    vertices = np.vstack((bottom, top)).astype(np.float32, copy=False)
    normals = np.vstack(
        (
            np.column_stack((cos, sin, np.zeros(seg, dtype=float))),
            np.column_stack((cos, sin, np.zeros(seg, dtype=float))),
        )
    ).astype(np.float32, copy=False)

    faces: list[list[int]] = []
    for i in range(seg):
        j = (i + 1) % seg
        faces.append([i, j, seg + i])
        faces.append([seg + i, j, seg + j])

    faces_arr = np.asarray(faces, dtype=np.int32)
    template = {
        "vertices": vertices,
        "normals": normals,
        "faces": faces_arr,
        "z": vertices[:, 2].astype(np.float32, copy=False),
    }
    _CYLINDER_TEMPLATE_CACHE[seg] = template
    return template


def _rotation_from_z(direction: np.ndarray) -> np.ndarray:
    """Return rotation matrix that aligns the +Z axis with ``direction``."""

    dir_vec = np.asarray(direction, dtype=float)
    norm = float(np.linalg.norm(dir_vec))
    if norm <= 1e-8 or not np.isfinite(norm):
        return np.eye(3, dtype=float)
    dir_unit = dir_vec / norm
    z_axis = np.array([0.0, 0.0, 1.0], dtype=float)
    c = float(np.dot(z_axis, dir_unit))
    if c >= 0.9999:
        return np.eye(3, dtype=float)
    if c <= -0.9999:
        return np.array(
            [[1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, -1.0]],
            dtype=float,
        )

    axis = np.cross(z_axis, dir_unit)
    sin_theta = float(np.linalg.norm(axis))
    if sin_theta <= 1e-8 or not np.isfinite(sin_theta):
        return np.eye(3, dtype=float)
    axis_unit = axis / sin_theta

    kx, ky, kz = axis_unit
    K = np.array(
        [
            [0.0, -kz, ky],
            [kz, 0.0, -kx],
            [-ky, kx, 0.0],
        ],
        dtype=float,
    )

    rot = np.eye(3, dtype=float) + sin_theta * K + (1.0 - c) * (K @ K)
    return rot


def _rotations_from_z(directions: np.ndarray) -> np.ndarray:
    """Batched :func:`_rotation_from_z`: align +Z with each row of ``directions``.

    Parameters
    ----------
    directions : numpy.ndarray
        Array of shape ``(B, 3)``. Rows need not be unit length; zero-length rows
        yield the identity rotation.

    Returns
    -------
    numpy.ndarray
        Rotation matrices of shape ``(B, 3, 3)`` such that ``R @ [0, 0, 1] ``
        points along the corresponding (normalised) input direction.
    """
    dirs = np.asarray(directions, dtype=float)
    b = dirs.shape[0]
    rot = np.broadcast_to(np.eye(3, dtype=float), (b, 3, 3)).copy()

    norms = np.linalg.norm(dirs, axis=1)
    ok = np.isfinite(norms) & (norms > 1e-8)
    if not ok.any():
        return rot

    units = np.zeros_like(dirs)
    units[ok] = dirs[ok] / norms[ok, None]
    c = units[:, 2]  # cos(theta) = dot(+Z, unit)

    # Anti-parallel: a 180 deg rotation about X (diag(1, -1, -1)).
    anti = ok & (c <= -0.9999)
    flip = np.array([[1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, -1.0]])
    rot[anti] = flip

    # General case: Rodrigues about axis = cross(+Z, unit) = (-uy, ux, 0).
    gen = ok & (c < 0.9999) & (c > -0.9999)
    if gen.any():
        u = units[gen]
        cc = c[gen]
        ax = np.empty((u.shape[0], 3), dtype=float)
        ax[:, 0] = -u[:, 1]
        ax[:, 1] = u[:, 0]
        ax[:, 2] = 0.0
        sin_theta = np.linalg.norm(ax, axis=1)
        valid = sin_theta > 1e-8
        ax[valid] /= sin_theta[valid, None]
        kx, ky, kz = ax[:, 0], ax[:, 1], ax[:, 2]
        zero = np.zeros_like(kx)
        k = np.stack(
            [
                np.stack([zero, -kz, ky], axis=1),
                np.stack([kz, zero, -kx], axis=1),
                np.stack([-ky, kx, zero], axis=1),
            ],
            axis=1,
        )  # (n, 3, 3)
        kk = np.matmul(k, k)
        eye = np.eye(3, dtype=float)
        r_gen = (
            eye
            + sin_theta[:, None, None] * k
            + (1.0 - cc)[:, None, None] * kk
        )
        # Degenerate (sin_theta ~ 0) rows fall back to identity.
        r_gen[~valid] = eye
        rot[gen] = r_gen

    return rot


def _build_stick_mesh(
    bonds: np.ndarray,
    atom_positions: np.ndarray,
    atom_colors: Optional[np.ndarray],
    radius: float,
    segments_circle: int = 12,
) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
    """Build a mesh for cylindrical sticks between bonded atom pairs.

    Fully vectorised over bonds: every cylinder shares the same template, so the
    per-bond rotation, scaling, colouring and face offsetting are done as batched
    array operations rather than a Python loop.
    """

    template = _get_cylinder_template(segments_circle)
    if template is None:
        return None

    pts = np.asarray(atom_positions, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 3:
        return None

    bonds_arr = np.asarray(bonds, dtype=int)
    if bonds_arr.ndim != 2 or bonds_arr.shape[1] != 2:
        return None

    radius_val = float(radius)
    if not np.isfinite(radius_val) or radius_val <= 0.0:
        return None

    colors_arr: Optional[np.ndarray]
    if atom_colors is not None:
        try:
            colors_arr = np.asarray(atom_colors, dtype=float)
            if colors_arr.shape[0] != pts.shape[0]:
                colors_arr = None
        except Exception:
            colors_arr = None
    else:
        colors_arr = None

    n_atoms = pts.shape[0]
    i0 = bonds_arr[:, 0]
    i1 = bonds_arr[:, 1]

    # Drop out-of-range and self bonds up front, vectorised.
    valid = (
        (i0 >= 0) & (i1 >= 0) & (i0 < n_atoms) & (i1 < n_atoms) & (i0 != i1)
    )
    i0 = i0[valid]
    i1 = i1[valid]
    if i0.size == 0:
        return None

    starts = pts[i0]
    vecs = pts[i1] - starts
    lengths = np.linalg.norm(vecs, axis=1)
    keep = np.isfinite(lengths) & (lengths > 1e-5)
    if not keep.any():
        return None
    i0 = i0[keep]
    i1 = i1[keep]
    starts = starts[keep]
    vecs = vecs[keep]
    lengths = lengths[keep]

    base_color = np.array([0.8, 0.8, 0.8, 1.0], dtype=float)
    base_vertices = np.asarray(template["vertices"], dtype=float)
    base_normals = np.asarray(template["normals"], dtype=float)
    base_faces = np.asarray(template["faces"], dtype=np.int32)
    base_z = np.asarray(template.get("z", base_vertices[:, 2]), dtype=float)

    n_bonds = starts.shape[0]
    verts_per_cyl = base_vertices.shape[0]

    rots = _rotations_from_z(vecs)  # (B, 3, 3)

    # Scale the shared template per bond (radius in xy, length in z), then rotate
    # and translate into world space. local: (B, V, 3), rot^T applied per bond.
    scale = np.empty((n_bonds, 1, 3), dtype=float)
    scale[:, 0, 0] = radius_val
    scale[:, 0, 1] = radius_val
    scale[:, 0, 2] = lengths
    verts_local = base_vertices[None, :, :] * scale  # (B, V, 3)
    verts_world = np.einsum("bvj,bij->bvi", verts_local, rots)
    verts_world += starts[:, None, :]
    normals_world = np.einsum("vj,bij->bvi", base_normals, rots)

    # Colour interpolates along the cylinder axis (z in [0, 1]) between endpoints.
    if colors_arr is not None:
        c0 = colors_arr[i0]
        c1 = colors_arr[i1]
    else:
        c0 = np.broadcast_to(base_color, (n_bonds, 4))
        c1 = c0
    z = base_z[None, :, None]  # (1, V, 1)
    cols = c0[:, None, :] * (1.0 - z) + c1[:, None, :] * z  # (B, V, 4)
    cols[:, :, 3] = 1.0

    # Offset the shared face template for each cylinder.
    offsets = (np.arange(n_bonds, dtype=np.int32) * verts_per_cyl)[:, None, None]
    faces = (base_faces[None, :, :] + offsets).reshape(-1, 3)

    positions = verts_world.reshape(-1, 3).astype(np.float32, copy=False)
    normals = normals_world.reshape(-1, 3).astype(np.float32, copy=False)
    colors = cols.reshape(-1, 4).astype(np.float32, copy=False)
    faces = faces.astype(np.int32, copy=False)

    return positions, normals, faces, colors


__all__ = [
    "_compute_center_radius",
    "_build_sphere_mesh",
    "_get_cylinder_template",
    "_rotation_from_z",
    "_rotations_from_z",
    "_build_stick_mesh",
]

