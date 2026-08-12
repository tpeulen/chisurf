"""Export the drawn scene as a 3-D model: STL, WRL (VRML) and glTF.

What a figure pipeline outside chimol needs is not the molecule but the
*picture of it*: the meshes actually on screen, in a format another program
opens. Three cover the destinations that matter:

* **glTF** (``.glb``, the GL Transmission Format's binary container) — the
  one for **PowerPoint**: Insert ▸ 3D Models places it as a rotatable object
  on the slide. Also what web viewers and Blender ingest first.
* **STL** — printing and CAD. Triangles only, no colour; that is the format.
* **WRL** (VRML 2.0) — the classic exchange format, with per-vertex colours.

What is exported is the scene as drawn: every triangle mesh, with spheres and
sticks — analytic impostors on screen — tessellated back into triangles for
the file. Lines, labels and the translucent `solid` fog are skipped: the
first two have no surface, and a plane-stack of per-vertex alpha is an
artefact of this renderer, not a model another program can light.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

__all__ = ["scene_mesh_objects", "write_glb", "write_stl", "write_wrl"]

#: Tessellation used when an analytic sphere or stick has to become triangles
#: again. Finer than the screen needs, because a file outlives a frame.
_SPHERE_LAT, _SPHERE_LON = 12, 18
_CYLINDER_SEGMENTS = 16


def _colors_for(geometry, count: int) -> np.ndarray:
    """Per-vertex RGBA for ``geometry``, opaque light grey when it has none."""
    colors = getattr(geometry, "colors", None)
    if colors is None or len(colors) == 0:
        return np.tile(
            np.array([0.8, 0.8, 0.8, 1.0], dtype=np.float32), (count, 1)
        )
    colors = np.asarray(colors, dtype=np.float32)
    if colors.shape[1] == 3:
        colors = np.concatenate(
            [colors, np.ones((colors.shape[0], 1), dtype=np.float32)], axis=1
        )
    if colors.shape[0] != count:
        colors = np.tile(colors[:1], (count, 1))
    return colors


def _sphere_objects(geometry, *, hollow: bool = False) -> dict | None:
    """Tessellate an impostor point cloud back into sphere triangles.

    Parameters
    ----------
    geometry : object
        The point geometry.
    hollow : bool, optional
        Drop particles :func:`exterior_mask` judges buried, **before**
        tessellating. Before, because each particle costs a whole sphere's
        worth of triangles and vertices; filtering afterwards would already
        have paid for them.
    """
    from ..geometry.primitives import _get_sphere_template  # noqa: PLC0415

    centers = np.asarray(geometry.positions, dtype=np.float32)
    if centers.size == 0:
        return None
    radii = getattr(geometry, "radii", None)
    if radii is None:
        radii = np.full(centers.shape[0], 0.3, dtype=np.float32)
    radii = np.asarray(radii, dtype=np.float32).reshape(-1)
    colors = _colors_for(geometry, centers.shape[0])

    if hollow:
        keep = exterior_mask(centers, radii)
        # Never return nothing. A threshold that happens to bury every particle
        # would otherwise write an empty file and report success.
        if keep.any() and not keep.all():
            centers = centers[keep]
            radii = radii[keep]
            colors = colors[keep]

    template = _get_sphere_template(_SPHERE_LAT, _SPHERE_LON)
    unit_v = np.asarray(template["vertices"], dtype=np.float32)
    unit_f = np.asarray(template["faces"], dtype=np.int64)
    per = unit_v.shape[0]

    verts = (
        centers[:, None, :] + radii[:, None, None] * unit_v[None, :, :]
    ).reshape(-1, 3)
    normals = np.tile(unit_v, (centers.shape[0], 1))
    faces = (
        unit_f[None, :, :] + (np.arange(centers.shape[0]) * per)[:, None, None]
    ).reshape(-1, 3)
    vertex_colors = np.repeat(colors, per, axis=0)
    return dict(verts=verts, normals=normals.astype(np.float32),
                colors=vertex_colors, faces=faces)


def _cylinder_objects(geometry) -> dict | None:
    """Tessellate bond cylinders (two rows per bond) back into triangles."""
    from ..geometry.primitives import (  # noqa: PLC0415
        _get_cylinder_template,
        _rotations_from_z,
    )

    ends = np.asarray(geometry.positions, dtype=np.float32)
    if ends.shape[0] < 2:
        return None
    ends = ends[: (ends.shape[0] // 2) * 2]
    start, stop = ends[0::2], ends[1::2]
    axis = stop - start
    length = np.linalg.norm(axis, axis=1)
    keep = length > 1e-6
    if not keep.any():
        return None
    start, stop, axis, length = start[keep], stop[keep], axis[keep], length[keep]

    radii = getattr(geometry, "radii", None)
    if radii is None:
        radii = np.full(ends.shape[0], 0.15, dtype=np.float32)
    radii = np.asarray(radii, dtype=np.float32).reshape(-1)[0::2][keep]
    colors = _colors_for(geometry, ends.shape[0])[0::2][keep]

    template = _get_cylinder_template(_CYLINDER_SEGMENTS)
    if template is None:
        return None
    unit_v = np.asarray(template["vertices"], dtype=np.float32)   # z in [0, 1]
    unit_n = np.asarray(template["normals"], dtype=np.float32)
    unit_f = np.asarray(template["faces"], dtype=np.int64)
    per = unit_v.shape[0]

    rotations = _rotations_from_z(axis / length[:, None])
    scaled = unit_v[None, :, :] * np.stack(
        [radii, radii, length], axis=1
    )[:, None, :]
    verts = (
        np.einsum("bij,bvj->bvi", rotations, scaled) + start[:, None, :]
    ).reshape(-1, 3)
    normals = np.einsum(
        "bij,vj->bvi", rotations, unit_n
    ).reshape(-1, 3)
    faces = (
        unit_f[None, :, :] + (np.arange(start.shape[0]) * per)[:, None, None]
    ).reshape(-1, 3)
    vertex_colors = np.repeat(colors, per, axis=0)
    return dict(verts=verts.astype(np.float32), normals=normals.astype(np.float32),
                colors=vertex_colors, faces=faces)


#: Neighbourhood radius for the hollow-out test, as a multiple of the median
#: particle radius. Wide enough that a surface particle still sees its
#: neighbours, narrow enough that the count says something local.
HOLLOW_RADIUS_SCALE = 2.5

#: How many neighbours inside that radius mean "buried". Close packing puts 12
#: spheres in contact, so a particle well past that is enclosed on every side.
HOLLOW_MIN_NEIGHBORS = 18


def exterior_mask(positions, radii=None, *, radius_scale=None, min_neighbors=None):
    """Which particles are on the outside, roughly and quickly.

    A mesoscale model exports enormous: every particle becomes a tessellated
    sphere, and for the 234,184-bead nuclear pore that is millions of triangles
    -- most of them **inside**, where no camera will ever see them. Dropping the
    buried ones before tessellation is the whole saving, and it has to happen
    here rather than in the writer, because the cost is created by the
    tessellation, not by the file format.

    The test is deliberately crude: **count the neighbours within a few radii,
    and call a particle buried when it has too many.** That is the same signal
    ambient occlusion already uses to darken crowded beads, which is a good
    sign -- what looks enclosed to the shading is enclosed.

    It is **not** a visibility computation and makes no claim to be one. It has
    no camera, so it cannot know what a particular view hides; it will keep a
    particle in an interior cavity, because a cavity wall is a surface; and it
    will drop a particle in a dense but genuinely exposed patch. For an export
    meant to be looked at, those are the right trades -- an exact answer costs
    ray casting per particle and this costs one neighbour search.

    Parameters
    ----------
    positions : array_like
        ``(n, 3)`` particle centres.
    radii : array_like, optional
        Per-particle radii. The median sets the neighbourhood size, so a bead
        model and an all-atom model both get a sensible one.
    radius_scale, min_neighbors : float, int, optional
        Override :data:`HOLLOW_RADIUS_SCALE` and :data:`HOLLOW_MIN_NEIGHBORS`.

    Returns
    -------
    numpy.ndarray
        Boolean ``(n,)``, ``True`` for particles to keep. All ``True`` when
        there is nothing to gain or the neighbour search is unavailable -- an
        export that silently lost its surface would be far worse than a large
        one.
    """
    from ..geometry.neighbors import count_within_radius  # noqa: PLC0415

    pts = np.asarray(positions, dtype=float)
    if pts.ndim != 2 or pts.shape[0] < 3:
        return np.ones(max(pts.shape[0], 0), dtype=bool)

    if radius_scale is None or min_neighbors is None:
        from ..config import _DISPLAY_CONFIG  # noqa: PLC0415

        section = _DISPLAY_CONFIG.get("export")
        section = section if isinstance(section, dict) else {}
        if radius_scale is None:
            radius_scale = section.get("hollow_radius_scale", HOLLOW_RADIUS_SCALE)
        if min_neighbors is None:
            min_neighbors = section.get("hollow_min_neighbors", HOLLOW_MIN_NEIGHBORS)
    try:
        scale = float(radius_scale)
        limit = int(min_neighbors)
    except (TypeError, ValueError):
        scale, limit = HOLLOW_RADIUS_SCALE, HOLLOW_MIN_NEIGHBORS
    if limit <= 0:
        return np.ones(pts.shape[0], dtype=bool)

    if radii is None or len(np.asarray(radii)) != pts.shape[0]:
        # No radii: fall back to the typical nearest-neighbour spacing, which
        # for a packed model is about the particle diameter anyway.
        span = np.ptp(pts, axis=0).max()
        typical = span / max(pts.shape[0] ** (1.0 / 3.0), 1.0)
    else:
        typical = float(np.median(np.asarray(radii, dtype=float))) * 2.0
    radius = float(typical) * scale
    if not np.isfinite(radius) or radius <= 0.0:
        return np.ones(pts.shape[0], dtype=bool)

    try:
        counts = count_within_radius(pts, radius)
    except Exception:  # noqa: BLE001 - keeping everything is the safe answer
        return np.ones(pts.shape[0], dtype=bool)
    return np.asarray(counts) < limit


def scene_mesh_objects(scene, *, hollow: bool | None = None) -> list[dict]:
    """Collect the scene as triangle meshes, one entry per exportable object.

    Parameters
    ----------
    scene : object
        The packed scene.
    hollow : bool, optional
        Drop buried particles before tessellating -- see :func:`exterior_mask`.
        ``None`` reads the ``export.hollow`` display setting, which is **on**:
        a mesoscale model exported whole is dominated by geometry inside it,
        and the file is routinely too large to open. Applies to particles only;
        a contoured surface is already a shell.

    Returns
    -------
    list of dict
        ``{"name", "verts", "normals", "colors", "faces"}`` per object —
        float32 ``(n, 3)`` / ``(n, 4)`` arrays and int ``(m, 3)`` faces.
    """
    if hollow is None:
        from ..config import _DISPLAY_CONFIG  # noqa: PLC0415

        section = _DISPLAY_CONFIG.get("export")
        hollow = bool(section.get("hollow", True)) if isinstance(section, dict) else True
    exported: list[dict] = []
    for obj in getattr(scene, "objects", []) or []:
        geometry = obj.geometry
        kind = getattr(geometry, "kind", "")
        entry = None
        if kind == "mesh" and geometry.indices is not None:
            faces = np.asarray(geometry.indices, dtype=np.int64).reshape(-1, 3)
            if faces.size == 0:
                continue
            verts = np.asarray(geometry.positions, dtype=np.float32)
            normals = getattr(geometry, "normals", None)
            if normals is None or len(normals) != len(verts):
                normals = np.zeros_like(verts)
            if geometry.meta.get("map_solid"):
                # The translucent fog is a renderer artefact -- hundreds of
                # stacked alpha planes -- not a surface another program can
                # light. Contour the map instead and export that.
                continue
            entry = dict(
                verts=verts,
                normals=np.asarray(normals, dtype=np.float32),
                colors=_colors_for(geometry, verts.shape[0]),
                faces=faces,
            )
        elif kind == "points" and geometry.meta.get("glyph") != "selection":
            entry = _sphere_objects(geometry, hollow=hollow)
        elif kind == "cylinders":
            entry = _cylinder_objects(geometry)
        if entry is None:
            continue
        entry["name"] = str(getattr(obj, "id", "object")) or "object"
        exported.append(entry)
    return exported


# --------------------------------------------------------------------------- #
# STL
# --------------------------------------------------------------------------- #
def write_stl(path, objects) -> int:
    """Write binary STL; returns the triangle count.

    Face normals are recomputed from the winding -- STL has no vertex
    normals, and a printer only trusts the geometry anyway.
    """
    tris = []
    for entry in objects:
        tris.append(entry["verts"][entry["faces"].reshape(-1)].reshape(-1, 3, 3))
    if not tris:
        raise ValueError("nothing to export: the scene has no triangles")
    corners = np.concatenate(tris).astype(np.float32)

    edge1 = corners[:, 1] - corners[:, 0]
    edge2 = corners[:, 2] - corners[:, 0]
    face_normals = np.cross(edge1, edge2)
    lengths = np.linalg.norm(face_normals, axis=1, keepdims=True)
    face_normals = (face_normals / np.where(lengths > 1e-12, lengths, 1.0)
                    ).astype(np.float32)

    count = corners.shape[0]
    record = np.zeros(
        count,
        dtype=np.dtype([
            ("normal", np.float32, 3),
            ("v0", np.float32, 3), ("v1", np.float32, 3), ("v2", np.float32, 3),
            ("attr", np.uint16),
        ]),
    )
    record["normal"] = face_normals
    record["v0"], record["v1"], record["v2"] = (
        corners[:, 0], corners[:, 1], corners[:, 2]
    )
    with Path(path).open("wb") as handle:
        handle.write(b"chimol scene export".ljust(80, b" "))
        handle.write(struct.pack("<I", count))
        handle.write(record.tobytes())
    return count


# --------------------------------------------------------------------------- #
# WRL (VRML 2.0)
# --------------------------------------------------------------------------- #
def write_wrl(path, objects) -> int:
    """Write VRML 2.0 with per-vertex colours; returns the triangle count."""
    if not objects:
        raise ValueError("nothing to export: the scene has no triangles")
    pieces = ["#VRML V2.0 utf8", "# chimol scene export"]
    total = 0
    for entry in objects:
        verts, colors, faces = entry["verts"], entry["colors"], entry["faces"]
        total += faces.shape[0]
        points = ", ".join(
            f"{v[0]:.4f} {v[1]:.4f} {v[2]:.4f}" for v in verts
        )
        shades = ", ".join(
            f"{c[0]:.3f} {c[1]:.3f} {c[2]:.3f}" for c in colors
        )
        index = ", ".join(
            f"{f[0]}, {f[1]}, {f[2]}, -1" for f in faces
        )
        pieces.append(
            "Shape {\n"
            "  appearance Appearance { material Material { } }\n"
            "  geometry IndexedFaceSet {\n"
            "    solid FALSE\n"
            f"    coord Coordinate {{ point [ {points} ] }}\n"
            f"    color Color {{ color [ {shades} ] }}\n"
            "    colorPerVertex TRUE\n"
            f"    coordIndex [ {index} ]\n"
            "  }\n"
            "}"
        )
    Path(path).write_text("\n".join(pieces))
    return total


# --------------------------------------------------------------------------- #
# glTF (binary container, .glb)
# --------------------------------------------------------------------------- #
def _pad(blob: bytes, pad: bytes = b"\x00") -> bytes:
    return blob + pad * (-len(blob) % 4)


def write_glb(path, objects) -> int:
    """Write a binary glTF 2.0 (.glb); returns the triangle count.

    The container PowerPoint's Insert ▸ 3D Models takes. One node per scene
    object; positions, normals, per-vertex ``COLOR_0`` and 32-bit indices in
    a single buffer; a matte double-sided material so the colours read as the
    viewport showed them rather than as plastic.
    """
    if not objects:
        raise ValueError("nothing to export: the scene has no triangles")

    binary = bytearray()
    buffer_views: list[dict] = []
    accessors: list[dict] = []
    meshes: list[dict] = []
    nodes: list[dict] = []
    total = 0

    def _add_view(blob: bytes, target: int) -> int:
        offset = len(binary)
        binary.extend(_pad(blob))
        buffer_views.append({
            "buffer": 0, "byteOffset": offset, "byteLength": len(blob),
            "target": target,
        })
        return len(buffer_views) - 1

    for entry in objects:
        verts = np.ascontiguousarray(entry["verts"], dtype=np.float32)
        normals = np.ascontiguousarray(entry["normals"], dtype=np.float32)
        lengths = np.linalg.norm(normals, axis=1, keepdims=True)
        normals = (normals / np.where(lengths > 1e-12, lengths, 1.0)
                   ).astype(np.float32)
        colors = np.ascontiguousarray(
            np.clip(entry["colors"], 0.0, 1.0), dtype=np.float32
        )
        faces = np.ascontiguousarray(entry["faces"], dtype=np.uint32)
        total += faces.shape[0]

        position_view = _add_view(verts.tobytes(), 34962)
        normal_view = _add_view(normals.tobytes(), 34962)
        color_view = _add_view(colors.tobytes(), 34962)
        index_view = _add_view(faces.tobytes(), 34963)

        base = len(accessors)
        accessors.extend([
            {"bufferView": position_view, "componentType": 5126,
             "count": int(verts.shape[0]), "type": "VEC3",
             "min": [float(v) for v in verts.min(axis=0)],
             "max": [float(v) for v in verts.max(axis=0)]},
            {"bufferView": normal_view, "componentType": 5126,
             "count": int(normals.shape[0]), "type": "VEC3"},
            {"bufferView": color_view, "componentType": 5126,
             "count": int(colors.shape[0]), "type": "VEC4"},
            {"bufferView": index_view, "componentType": 5125,
             "count": int(faces.size), "type": "SCALAR"},
        ])
        meshes.append({
            "name": entry["name"],
            "primitives": [{
                "attributes": {
                    "POSITION": base, "NORMAL": base + 1, "COLOR_0": base + 2,
                },
                "indices": base + 3,
                "material": 0,
            }],
        })
        nodes.append({"mesh": len(meshes) - 1, "name": entry["name"]})

    document = {
        "asset": {"version": "2.0", "generator": "chimol"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "meshes": meshes,
        "materials": [{
            "name": "chimol-vertex-colors",
            "pbrMetallicRoughness": {
                "baseColorFactor": [1.0, 1.0, 1.0, 1.0],
                "metallicFactor": 0.0,
                "roughnessFactor": 0.9,
            },
            "doubleSided": True,
        }],
        "bufferViews": buffer_views,
        "accessors": accessors,
        "buffers": [{"byteLength": len(binary)}],
    }

    json_chunk = _pad(json.dumps(document, separators=(",", ":")).encode(), b" ")
    bin_chunk = _pad(bytes(binary))
    length = 12 + 8 + len(json_chunk) + 8 + len(bin_chunk)
    with Path(path).open("wb") as handle:
        handle.write(struct.pack("<III", 0x46546C67, 2, length))     # 'glTF'
        handle.write(struct.pack("<II", len(json_chunk), 0x4E4F534A))  # JSON
        handle.write(json_chunk)
        handle.write(struct.pack("<II", len(bin_chunk), 0x004E4942))   # BIN
        handle.write(bin_chunk)
    return total
