"""Surface area by dot sampling, as PyMOL's ``get_area`` computes it.

Solvent accessibility is what decides where a dye can be attached and how freely
it will move, so this is one of the few numbers a viewer computes that feeds
directly into experiment design rather than into a picture.

Transcribed from ``RepDotDoNew`` (``layer2/RepDot.cpp``) in ``cRepDotAreaType``
mode. The algorithm is Shrake–Rupley, but two details are PyMOL's specifically and
both change the answer:

* **The dots are an icosahedral geodesic, not a uniform spiral.** ``dot_density``
  selects a subdivision level giving 12, 42, 162, 642 or 2562 dots. The default is
  2, i.e. 162.
* **Each dot carries its own area weight**, not ``4π/N``. ``MakeDotSphere``
  computes each spherical triangle's area from its spherical excess, divides by
  three and accumulates onto the triangle's vertices. On a geodesic sphere the
  vertices are not equivalent — the twelve original icosahedron vertices have five
  neighbours where every later vertex has six — so a uniform weight is wrong by a
  few percent, most at low density.

A dot survives if no *other* atom's inflated sphere contains it; the atom's area is
then ``r² Σ w`` over its surviving dots, with ``r = vdw + solvent_radius``.

``dot_solvent`` decides which surface is measured: off (PyMOL's default) sets the
solvent radius to zero and gives the van der Waals surface area; on gives the
solvent-accessible surface.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "DOT_COUNTS",
    "geodesic_sphere",
    "atom_surface_areas",
]

#: Dots per ``dot_density`` level -- ``Sphere_nDot`` in ``layer0/SphereData.h``.
#: An icosahedron subdivided 0-4 times.
DOT_COUNTS: tuple[int, ...] = (12, 42, 162, 642, 2562)

#: Cache of built spheres, since a level is rebuilt for every call otherwise.
_SPHERES: dict[int, tuple[np.ndarray, np.ndarray]] = {}


def _icosahedron() -> tuple[np.ndarray, np.ndarray]:
    """Return the 12 vertices and 20 faces that make PyMOL's sphere 0."""
    phi = (1.0 + 5.0**0.5) / 2.0
    verts = np.array(
        [
            [-1, phi, 0], [1, phi, 0], [-1, -phi, 0], [1, -phi, 0],
            [0, -1, phi], [0, 1, phi], [0, -1, -phi], [0, 1, -phi],
            [phi, 0, -1], [phi, 0, 1], [-phi, 0, -1], [-phi, 0, 1],
        ],
        dtype=float,
    )
    verts /= np.linalg.norm(verts, axis=1)[:, None]
    faces = np.array(
        [
            [0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11],
            [1, 5, 9], [5, 11, 4], [11, 10, 2], [10, 7, 6], [7, 1, 8],
            [3, 9, 4], [3, 4, 2], [3, 2, 6], [3, 6, 8], [3, 8, 9],
            [4, 9, 5], [2, 4, 11], [6, 2, 10], [8, 6, 7], [9, 8, 1],
        ],
        dtype=int,
    )
    return verts, faces


def _subdivide(
    verts: np.ndarray, faces: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Split every triangle into four, projecting new vertices to the sphere."""
    vertex_list = [v for v in verts]
    midpoints: dict[tuple[int, int], int] = {}

    def midpoint(a: int, b: int) -> int:
        key = (min(a, b), max(a, b))
        if key not in midpoints:
            point = vertex_list[a] + vertex_list[b]
            vertex_list.append(point / np.linalg.norm(point))
            midpoints[key] = len(vertex_list) - 1
        return midpoints[key]

    new_faces = []
    for a, b, c in faces:
        ab, bc, ca = midpoint(a, b), midpoint(b, c), midpoint(c, a)
        new_faces += [[a, ab, ca], [b, bc, ab], [c, ca, bc], [ab, bc, ca]]
    return np.array(vertex_list, dtype=float), np.array(new_faces, dtype=int)


def _spherical_excess(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    """Area of spherical triangles on the unit sphere, by their excess.

    Van Oosterom and Strackee's formula rather than three separate angle
    computations: one ``atan2`` per triangle and no cancellation near degenerate
    triangles, which the subdivided sphere is full of.
    """
    numerator = np.abs(np.einsum("ij,ij->i", a, np.cross(b, c)))
    denominator = (
        1.0
        + np.einsum("ij,ij->i", a, b)
        + np.einsum("ij,ij->i", b, c)
        + np.einsum("ij,ij->i", a, c)
    )
    return 2.0 * np.arctan2(numerator, denominator)


def geodesic_sphere(density: int = 2) -> tuple[np.ndarray, np.ndarray]:
    """Return the dot directions and their area weights for a ``dot_density``.

    Parameters
    ----------
    density : int, optional
        PyMOL's ``dot_density``, clamped to 0-4. The default of 2 gives 162 dots.

    Returns
    -------
    tuple
        ``(dots, weights)`` -- ``(n, 3)`` unit vectors and ``(n,)`` solid angles
        summing to ``4π``. Multiply a weight by ``r²`` for the area it stands for.
    """
    level = int(np.clip(density, 0, 4))
    if level in _SPHERES:
        return _SPHERES[level]

    verts, faces = _icosahedron()
    for _ in range(level):
        verts, faces = _subdivide(verts, faces)

    areas = _spherical_excess(
        verts[faces[:, 0]], verts[faces[:, 1]], verts[faces[:, 2]]
    )
    # A third of each triangle to each of its corners, as MakeDotSphere does.
    weights = np.zeros(len(verts), dtype=float)
    np.add.at(weights, faces.reshape(-1), np.repeat(areas / 3.0, 3))

    _SPHERES[level] = (verts, weights)
    return verts, weights


def atom_surface_areas(
    coords: np.ndarray,
    radii: np.ndarray,
    *,
    solvent_radius: float = 1.4,
    dot_solvent: bool = False,
    dot_density: int = 2,
    mask: np.ndarray | None = None,
) -> np.ndarray:
    """Per-atom surface area in square Angstrom.

    Parameters
    ----------
    coords : numpy.ndarray
        ``(n, 3)`` atom positions in Angstrom.
    radii : numpy.ndarray
        ``(n,)`` van der Waals radii.
    solvent_radius : float, optional
        Probe radius, used only when ``dot_solvent`` is set.
    dot_solvent : bool, optional
        False (PyMOL's default) measures the van der Waals surface; True inflates
        every atom by the probe and measures the solvent-accessible surface.
    dot_density : int, optional
        Sampling level, 0-4.
    mask : numpy.ndarray, optional
        Atoms to compute an area *for*. Every atom still occludes, which is the
        point: the area of a residue in a protein is not its area in isolation.

    Returns
    -------
    numpy.ndarray
        ``(n,)`` areas, zero for atoms outside ``mask``.
    """
    xyz = np.asarray(coords, dtype=float)
    vdw = np.asarray(radii, dtype=float)
    if xyz.ndim != 2 or xyz.shape[1] != 3 or vdw.shape[0] != xyz.shape[0]:
        raise ValueError("coords must be (n, 3) with one radius per atom")

    probe = float(solvent_radius) if dot_solvent else 0.0
    inflated = vdw + probe
    dots, weights = geodesic_sphere(dot_density)

    wanted = (
        np.ones(len(xyz), dtype=bool) if mask is None
        else np.asarray(mask, dtype=bool)
    )
    out = np.zeros(len(xyz), dtype=float)
    if not wanted.any():
        return out

    from scipy.spatial import cKDTree

    tree = cKDTree(xyz)
    # The furthest an occluding centre can be from a dot of the largest atom.
    reach = float(inflated.max()) * 2.0

    for index in np.nonzero(wanted)[0]:
        radius = inflated[index]
        if radius <= 0.0:
            continue
        surface = xyz[index] + radius * dots

        neighbours = tree.query_ball_point(xyz[index], reach)
        neighbours = [j for j in neighbours if j != index]
        if not neighbours:
            out[index] = radius * radius * weights.sum()
            continue

        others = xyz[neighbours]
        limits = inflated[neighbours]
        # A dot is buried if it lies inside *any* other inflated sphere.
        distances = np.linalg.norm(
            surface[:, None, :] - others[None, :, :], axis=2
        )
        exposed = ~np.any(distances < limits[None, :], axis=1)
        out[index] = radius * radius * weights[exposed].sum()

    return out
