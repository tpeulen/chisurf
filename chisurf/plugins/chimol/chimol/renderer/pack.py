"""Put a :class:`~.scene.Scene` into the one layout every GPU backend can upload.

Why this exists
---------------
``Scene`` is backend-neutral by design, but "neutral" has meant "whatever the
builder happened to produce". Measured on 148L, one scene carries three different
conventions at once::

    cartoon      positions float64  normals float64  colors float64
    sticks       positions float32  normals float32  colors float32
    atoms_mesh   positions float64  normals float32  colors float64

and every index array is ``int32``. The Qt backend hides this by coercing each
array at upload time, which means the coercion is a property of that backend
rather than of the scene -- so a second backend has to reimplement it, a ray
tracer sees different numbers than the rasteriser, and a buffer handed straight
to a GPU is a silent correctness bug rather than a failure. ``float64`` is not a
vertex format WebGPU has; ``int32`` is not an index format it accepts.

Doing it once, here, gives all of them one input: **float32 attributes, uint32
indices, C-contiguous, no NaNs**. That is a precondition for zero-copy upload,
because a view onto the interpreter's heap can only be handed to the GPU if it is
already in the layout the GPU expects.

Colours stay float32 in ``[0, 1]`` rather than becoming ``uint8`` RGBA: the
shaders sample them as floats, and quantising here would throw away the
occlusion that has already been multiplied in.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .scene import Material, Scene

#: Attribute arrays, and the width each row must have. ``None`` means any width.
_VECTOR_FIELDS: dict[str, Optional[int]] = {
    "positions": 3,
    "normals": 3,
    "colors": None,  # RGB or RGBA depending on the builder
    "radii": 1,
    "occlusion": 1,
}


@dataclass
class PackedGeometry:
    """One draw call's arrays, in GPU-upload layout.

    Attributes
    ----------
    kind : str
        ``"mesh"``, ``"line"``, ``"points"`` or ``"text"``.
    positions : numpy.ndarray
        ``(n, 3)`` float32.
    indices : numpy.ndarray or None
        Flat uint32, a multiple of three for meshes.
    normals, colors, radii, occlusion : numpy.ndarray or None
        float32, ``(n, ...)``.
    meta : dict
        Carried through untouched; ``meta["labels"]`` for ``kind == "text"``.
    """

    kind: str
    positions: np.ndarray
    indices: Optional[np.ndarray] = None
    normals: Optional[np.ndarray] = None
    colors: Optional[np.ndarray] = None
    radii: Optional[np.ndarray] = None
    occlusion: Optional[np.ndarray] = None
    meta: dict = field(default_factory=dict)

    @property
    def vertex_count(self) -> int:
        """Number of vertices."""
        return int(self.positions.shape[0])

    @property
    def triangle_count(self) -> int:
        """Number of triangles, or 0 when this is not indexed mesh geometry."""
        if self.indices is None or self.kind != "mesh":
            return 0
        return int(self.indices.size // 3)


@dataclass
class PackedObject:
    """A scene object with its geometry packed."""

    id: str
    geometry: PackedGeometry
    render_mode: str = "opaque"
    material: Optional[Material] = None


@dataclass
class PackedScene:
    """A whole scene in GPU-upload layout."""

    objects: list[PackedObject] = field(default_factory=list)
    center: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float32))
    radius: float = 1.0

    @property
    def triangle_count(self) -> int:
        """Total triangles across every object."""
        return sum(o.geometry.triangle_count for o in self.objects)

    @property
    def vertex_count(self) -> int:
        """Total vertices across every object."""
        return sum(o.geometry.vertex_count for o in self.objects)


def _as_f32(value, name: str, width: Optional[int]) -> np.ndarray:
    """Return ``value`` as a C-contiguous float32 array of the expected width."""
    arr = np.ascontiguousarray(value, dtype=np.float32)
    if width is not None:
        if arr.ndim == 1 and width == 1:
            arr = arr.reshape(-1, 1)
        if arr.ndim != 2 or arr.shape[1] != width:
            raise ValueError(
                f"{name}: expected (n, {width}), got {arr.shape}"
            )
    elif arr.ndim != 2:
        raise ValueError(f"{name}: expected a 2-D array, got {arr.shape}")
    return arr


def pack_geometry(geometry) -> PackedGeometry:
    """Normalise one :class:`~.scene.Geometry` for upload.

    Parameters
    ----------
    geometry : Geometry
        The backend-neutral geometry to normalise.

    Returns
    -------
    PackedGeometry

    Raises
    ------
    ValueError
        If an array has the wrong shape, an index is out of range, or a value is
        not finite. These are raised rather than repaired: a NaN vertex is a bug
        in a builder, and silently dropping it moves the failure somewhere it
        cannot be diagnosed.
    """
    positions = _as_f32(geometry.positions, "positions", 3)
    n = positions.shape[0]

    out: dict[str, Optional[np.ndarray]] = {}
    for name, width in _VECTOR_FIELDS.items():
        if name == "positions":
            continue
        value = getattr(geometry, name, None)
        if value is None:
            out[name] = None
            continue
        arr = _as_f32(value, name, width)
        if arr.shape[0] != n:
            raise ValueError(
                f"{name}: has {arr.shape[0]} rows but positions has {n}"
            )
        out[name] = arr

    indices = None
    if geometry.indices is not None:
        raw = np.ascontiguousarray(geometry.indices).ravel()
        if raw.size:
            lo, hi = int(raw.min()), int(raw.max())
            if lo < 0 or hi >= n:
                raise ValueError(
                    f"indices reference vertices [{lo}, {hi}] but there are {n}"
                )
        # uint32, not the int32 the builders emit: WebGPU's index formats are
        # uint16 and uint32, and a signed buffer is not one of them.
        indices = raw.astype(np.uint32, copy=False)
        indices = np.ascontiguousarray(indices)
        if geometry.kind == "mesh" and indices.size % 3:
            raise ValueError(
                f"mesh has {indices.size} indices, which is not a multiple of 3"
            )

    for name, arr in (("positions", positions), *out.items()):
        if arr is not None and not np.isfinite(arr).all():
            raise ValueError(f"{name}: contains NaN or infinity")

    return PackedGeometry(
        kind=geometry.kind,
        positions=positions,
        indices=indices,
        meta=dict(getattr(geometry, "meta", {}) or {}),
        **out,
    )


def pack_scene(scene: Optional[Scene]) -> PackedScene:
    """Normalise a whole scene for upload.

    Parameters
    ----------
    scene : Scene or None
        The scene to pack. ``None`` yields an empty :class:`PackedScene`.

    Returns
    -------
    PackedScene
    """
    if scene is None:
        return PackedScene()
    objects = [
        PackedObject(
            id=obj.id,
            geometry=pack_geometry(obj.geometry),
            render_mode=obj.render_mode,
            material=obj.material,
        )
        for obj in scene.objects
    ]
    return PackedScene(
        objects=objects,
        center=np.ascontiguousarray(scene.center, dtype=np.float32).reshape(3),
        radius=float(scene.radius),
    )
