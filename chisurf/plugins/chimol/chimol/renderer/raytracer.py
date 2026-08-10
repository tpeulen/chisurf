from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

from . import compute
from .bvh import _MAX_LEAF, build_bvh, primitive_bounds
from .view_state import unpack_view_state

@dataclass
class Sphere:
    """One traced sphere: an atom, a bead, or a line's round cap."""

    center: np.ndarray  # (3,) world position
    radius: float
    color: np.ndarray  # (3,) RGB in [0, 1]
    #: Opacity in [0, 1]; 1 is solid. The tracer composites through anything
    #: below 1, so this is what makes `transparency` reach a raytraced image.
    alpha: float = 1.0


@dataclass
class RayCamera:
    """Where the tracer looks from, and through what lens."""

    origin: np.ndarray      # (3,)
    forward: np.ndarray     # (3,) unit vector
    up: np.ndarray          # (3,) unit vector
    fov_degrees: float = 45.0
    far_clip: float = 200.0


_FOV_DEG_DEFAULT = 45.0


def _camera_from_view_state(view: List[float]) -> RayCamera:
    """Build a ray camera from an 18-float view tuple.

    The tuple layout (and the several historical variants that are still
    accepted) lives in :mod:`.view_state`, so the offscreen raytrace and the
    interactive GL widget cannot drift apart.
    """
    state = unpack_view_state(view)
    rot = state.rotation

    # Rows of the world->camera rotation are the camera axes in world space;
    # the camera sits `distance` along its own +Z (row 2) from the target.
    return RayCamera(
        origin=state.target + max(state.distance, 1.0) * rot[2],
        forward=-rot[2],
        up=rot[1],
        fov_degrees=state.fov,
        far_clip=state.far,
    )


# ------------------------------------------------------------------ #
# The tracer runs as a WGSL compute shader
# ------------------------------------------------------------------ #
#: Raised when there is no adapter to trace on.
class NoComputeDevice(RuntimeError):
    """The tracer needs a WebGPU device and this machine has none.

    Notes
    -----
    There is deliberately no CPU tracer behind this. chimol's *renderer* is
    WebGPU, so a session that can display a molecule can also trace one — a
    second implementation here would be a large body of shading code that
    nothing ever runs, which is exactly how the previous pure-NumPy twin came to
    be silently broken while every test passed.
    """


# ------------------------------------------------------------------ #
# Public API
# ------------------------------------------------------------------ #


def trace(
    spheres: List[Sphere],
    camera: RayCamera,
    light_directions: np.ndarray,
    width: int = 800,
    height: int = 600,
    *,
    background: Tuple[int, int, int] = (25, 25, 25),
    ambient: float = 0.14,
    diffuse: float = 0.45,
    specular: float = 0.25,
    shininess: float = 40.0,
    ssaa: int = 2,
    direct_specular: float = 0.30,
    direct_specular_power: float = 55.0,
    reflect_power: float = 1.0,
    #: PyMOL's `direct` and `power`: the headlight term and its exponent.
    direct: float = 0.45,
    direct_power: float = 1.0,
    legacy_lighting: float = 0.0,
    shadow: bool = True,
    shadow_fudge: float = 0.001,
    shadow_decay_factor: float = 0.2,
    shadow_decay_range: float = 1.8,
    gamma: float = 2.2,
    depth_cue: bool = True,
    fog_start: float = 0.45,
    fog_intensity: float = 1.0,
    fog_front: float | None = None,
    fog_back: float | None = None,
    color_blend: bool = True,
    color_blend_red: float = 0.17,
    color_blend_green: float = 0.25,
    color_blend_blue: float = 0.14,
    # Triangle mesh data (optional)
    tri_vertices: np.ndarray | None = None,
    tri_vnormals: np.ndarray | None = None,
    tri_colors: np.ndarray | None = None,
    tri_alpha: np.ndarray | None = None,
    # How many surfaces a ray may pass through. Four covers the common case --
    # front and back of a translucent shell, plus what is inside it -- and the
    # walk stops early anyway once too little light is still coming through.
    max_layers: int = 4,
    # Progress / cancellation
    progress: Optional[np.ndarray] = None,
    cancel: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Return an (H, W, 3) uint8 raytraced image of spheres and triangles.

    Parameters
    ----------
    spheres : list of Sphere
        Spheres to render.
    camera : RayCamera
        Camera viewpoint.
    light_directions : np.ndarray
        Direction vectors of light sources, shape (N, 3).
    width, height : int
        Output image dimensions.
    tri_vertices : np.ndarray or None
        Triangle vertices, shape (T, 3, 3).
    tri_vnormals : np.ndarray or None
        Per-vertex normals, shape (T, 3, 3).
    tri_colors : np.ndarray or None
        Per-triangle RGB colors, shape (T, 3).
    tri_alpha : np.ndarray or None
        Per-triangle opacity, shape (T,); 1 is solid. ``None`` means every
        triangle is opaque, which is what an RGB mesh carries.
    max_layers : int, optional
        How many surfaces a ray may pass through before it stops. Four covers a
        translucent shell seen front and back with something inside it. Costs
        nothing when the scene is opaque -- the walk ends at the first solid hit
        -- and the transmittance early-out usually ends it sooner than this
        bound anyway.
    fog_front, fog_back : float or None
        Distances from the camera the depth cue runs between: no fog at
        ``fog_front``, full fog at ``fog_back``. PyMOL normalises over its
        front-to-back *clipping* range -- ``ffact = (front - dist) /
        (front - back)`` in ``layer1/Ray.cpp`` -- and those planes are fitted
        around the object, so its fog spans the molecule and nothing else.

        This used to be ``best_t / camera.far_clip``, measured from the *camera*
        to a far plane that is not fitted to anything. A molecule 1730 units away
        inside a 2442-unit far plane then sat at 0.58-0.83 of the range and was
        fogged 24-69 % *everywhere*, with no unfogged pixel anywhere in the
        image: a depth cue that reads as a dimmer. Callers that know where the
        scene is should say so; ``None`` keeps the old range (``0`` to
        ``camera.far_clip``).

    All other parameters are as in :func:`render_scene`.
    """
    bg_r, bg_g, bg_b = background
    if gamma > 0.0 and gamma != 1.0:
        bg_norm = np.array([bg_r, bg_g, bg_b], dtype=float) / 255.0
        inp = bg_norm.mean()
        if inp > 1e-6:
            sig = pow(float(inp), float(gamma)) / float(inp)
            linear_bg = np.clip(bg_norm * sig * 255.0, 0.0, 255.0)
            bg_r = int(round(linear_bg[0]))
            bg_g = int(round(linear_bg[1]))
            bg_b = int(round(linear_bg[2]))

    has_any = bool(spheres)
    n_tri = 0
    if tri_vertices is not None:
        n_tri = tri_vertices.shape[0]
        has_any = has_any or (n_tri > 0)

    if not has_any:
        img = np.full((height, width, 3), [bg_r, bg_g, bg_b], dtype=np.uint8)
        if color_blend:
            img = _apply_color_blend(img, color_blend_red, color_blend_green, color_blend_blue, _gamma=gamma)
        return img

    n = len(spheres)
    centers = np.zeros((n, 3), dtype=np.float64)
    radii_arr = np.zeros(n, dtype=np.float64)
    colors_arr = np.zeros((n, 3), dtype=np.float64)
    sph_alpha_arr = np.ones(n, dtype=np.float64)
    for i, s in enumerate(spheres):
        centers[i] = s.center
        radii_arr[i] = float(s.radius)
        colors_arr[i] = np.clip(s.color, 0.0, 1.0)
        sph_alpha_arr[i] = min(1.0, max(0.0, float(getattr(s, "alpha", 1.0))))

    tverts = np.zeros((n_tri, 3, 3), dtype=np.float64)
    tnorms = np.zeros((n_tri, 3, 3), dtype=np.float64)
    tcols = np.zeros((n_tri, 3), dtype=np.float64)
    talpha = np.ones(max(n_tri, 1), dtype=np.float64)
    if n_tri > 0:
        tverts[:] = tri_vertices.astype(np.float64)
        tnorms[:] = tri_vnormals.astype(np.float64) if tri_vnormals is not None else 0.0
        tcols[:] = tri_colors.astype(np.float64) if tri_colors is not None else 0.5
        talpha = np.ones(n_tri, dtype=np.float64)
        if tri_alpha is not None:
            ta = np.asarray(tri_alpha, dtype=np.float64).reshape(-1)
            if ta.shape[0] == n_tri:
                talpha[:] = np.clip(ta, 0.0, 1.0)

    lds = np.asarray(light_directions, dtype=np.float64)
    if lds.ndim == 1:
        lds = lds.reshape(1, 3)
    elif lds.ndim != 2 or lds.shape[1] != 3:
        lds = lds.reshape(-1, 3)
    for i in range(lds.shape[0]):
        ln = np.linalg.norm(lds[i])
        if ln > 1e-9:
            lds[i] /= ln
        else:
            lds[i] = np.array([0.0, 0.0, 1.0], dtype=np.float64)

    fov_rad = math.radians(camera.fov_degrees)

    front = 0.0 if fog_front is None else float(fog_front)
    back = float(camera.far_clip) if fog_back is None else float(fog_back)
    fog_inv_range = 1.0 / (back - front) if back > front else 0.0

    if progress is None:
        progress = np.zeros(1, dtype=np.int64)
    else:
        progress = np.asarray(progress, dtype=np.int64)
    if cancel is None:
        cancel = np.zeros(1, dtype=np.int64)
    else:
        cancel = np.asarray(cancel, dtype=np.int64)

    # One tree, walked by both the primary rays and the shadow rays. It used to
    # be two: a second, sphere-only tree existed because only spheres cast a
    # shadow, which meant a cartoon -- the default display -- cast none at all
    # and `ray_shadow` did nothing on it. PyMOL shadows every primitive. Testing
    # the whole scene was unaffordable while a shadow ray cost a sweep of it;
    # with the tree it is one more descent, so the second tree is not an
    # optimisation any more, only a thing that made the picture wrong.
    prim_min, prim_max = primitive_bounds(centers, radii_arr, tverts)
    scene_bvh = build_bvh(prim_min, prim_max, _MAX_LEAF)
    ray_scene = compute.RayScene(centers, radii_arr, tverts, scene_bvh)

    sphere_rgba = np.concatenate([colors_arr, sph_alpha_arr[:, None]], axis=1)
    tri_rgba = np.concatenate([tcols, talpha[:n_tri, None]], axis=1) if n_tri else \
        np.zeros((0, 4), dtype=np.float64)

    background = np.array([bg_r, bg_g, bg_b], dtype=np.float64) / 255.0
    settings = {
        "width": int(width), "height": int(height), "ssaa": int(ssaa),
        "max_layers": int(max(1, max_layers)),
        "background": background,
        "ambient": float(ambient), "diffuse": float(diffuse),
        "specular": float(specular), "shininess": float(shininess),
        "direct_specular": float(direct_specular),
        "direct_specular_power": float(direct_specular_power),
        "reflect_power": float(reflect_power),
        "direct": float(direct), "direct_power": float(direct_power),
        "legacy": float(legacy_lighting),
        "shadow_enabled": bool(shadow), "shadow_fudge": float(shadow_fudge),
        "shadow_decay_factor": float(shadow_decay_factor),
        "shadow_decay_range": float(shadow_decay_range),
        "depth_cue_enabled": bool(depth_cue),
        "fog_start": float(fog_start), "fog_intensity": float(fog_intensity),
        "fog_front": float(front), "fog_inv_range": float(fog_inv_range),
    }

    frame = compute.raytrace(
        ray_scene, camera, lds, sphere_rgba, tnorms, tri_rgba, settings
    )
    if frame is None:
        raise NoComputeDevice(
            "the ray tracer needs a WebGPU adapter and none could be obtained"
        )
    progress[0] = int(height)

    # A pixel nothing was hit in keeps the background exactly, rather than a
    # rounded version of it -- the shader reports the hit mask so the host does
    # not have to compare against a colour that may have been gamma-adjusted.
    rgb = np.clip(frame[:, :, :3] * 255.0, 0.0, 255.0)
    img = np.where(
        frame[:, :, 3:4] > 0.5, rgb, np.array([bg_r, bg_g, bg_b], dtype=np.float64)
    ).astype(np.uint8)

    if color_blend:
        img = _apply_color_blend(img, color_blend_red, color_blend_green, color_blend_blue,
                                 _gamma=gamma)

    return img


def _apply_color_blend(
    img: np.ndarray,
    red_blend: float,
    green_blend: float,
    blue_blend: float,
    _gamma: float = 2.2,
) -> np.ndarray:
    out = img.astype(np.float64)
    r_part = red_blend * out[:, :, 0]
    g_part = green_blend * out[:, :, 1]
    b_part = blue_blend * out[:, :, 2]
    r_min = np.maximum(g_part, b_part)
    g_min = np.maximum(r_part, b_part)
    b_min = np.maximum(g_part, r_part)
    out[:, :, 0] = np.maximum(out[:, :, 0], r_min)
    out[:, :, 1] = np.maximum(out[:, :, 1], g_min)
    out[:, :, 2] = np.maximum(out[:, :, 2], b_min)
    return np.clip(np.round(out), 0, 255).astype(np.uint8)





#: Sides in the prism a line segment becomes. The tracer has a sphere and a
#: triangle primitive and no cylinder, so a line's shaft is tessellated while its
#: round caps stay spheres -- which the tracer intersects exactly, so only the
#: shaft is faceted. Eight sides stops reading as a polygon at the widths a line
#: is actually drawn at (one to three pixels).
_LINE_SIDES = 8

#: Geometry kinds :func:`render_scene` turns into traced primitives. ``text`` is
#: the one it cannot: a label is rasterised glyphs, and the tracer has no glyph.
TRACEABLE_KINDS = ("points", "mesh", "line")


def traceable_geometry_counts(scene) -> dict[str, int]:
    """Count a scene's geometry by kind, so a caller can say what it dropped.

    Parameters
    ----------
    scene : Scene or None
        Scene to inspect.

    Returns
    -------
    dict
        Vertex count per geometry kind, kinds with nothing omitted. Keys outside
        :data:`TRACEABLE_KINDS` are what a render will leave out.
    """
    counts: dict[str, int] = {}
    for obj in getattr(scene, "objects", None) or ():
        geom = getattr(obj, "geometry", None)
        if geom is None or geom.positions is None:
            continue
        n = int(np.asarray(geom.positions).reshape(-1, 3).shape[0])
        if n:
            counts[geom.kind] = counts.get(geom.kind, 0) + n
    return counts


def _triangle_alpha(cols, first_vertex_index, n_tris: int) -> np.ndarray:
    """One opacity per triangle, taken where its colour is taken.

    A mesh carries colour per *vertex*, and the tracer shades a triangle with a
    single flat colour read from its first vertex -- so the alpha has to come
    from the same place, or a translucent surface would be shaded with an
    opacity its own colour does not have.

    Parameters
    ----------
    cols : numpy.ndarray or None
        Vertex colours, ``(N, 3)`` or ``(N, 4)``.
    first_vertex_index : numpy.ndarray
        Index of each triangle's first vertex.
    n_tris : int
        How many triangles.

    Returns
    -------
    numpy.ndarray
        ``(n_tris,)`` opacities; all ones when the mesh carries no alpha, which
        is what an RGB mesh means.
    """
    if cols is None:
        return np.ones(n_tris, dtype=float)
    arr = np.asarray(cols, dtype=float)
    if arr.ndim != 2 or arr.shape[1] < 4:
        return np.ones(n_tris, dtype=float)
    idx = np.asarray(first_vertex_index, dtype=int)
    if idx.shape[0] != n_tris or idx.max(initial=-1) >= arr.shape[0]:
        return np.ones(n_tris, dtype=float)
    return np.clip(arr[idx, 3], 0.0, 1.0)


def _line_segments(geom) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Split a ``kind="line"`` geometry into segments and endpoint colours.

    Parameters
    ----------
    geom : Geometry
        Geometry whose ``kind`` is ``"line"``. ``meta["mode"]`` selects between
        consecutive pairs (the ``GL_LINES`` default) and a connected
        ``"line_strip"``, matching what the GL backend draws -- reading the same
        key, so the traced picture cannot disagree with the drawn one.

    Returns
    -------
    tuple of ndarray
        ``(p0, p1, c0, c1)`` -- segment endpoints, shape ``(S, 3)``, and the
        colour at each end, shape ``(S, 3)``.
    """
    pos = np.asarray(geom.positions, dtype=float).reshape(-1, 3)
    n = pos.shape[0]
    if n < 2:
        empty = np.zeros((0, 3), dtype=float)
        return empty, empty, empty, empty

    mode = (geom.meta or {}).get("mode", "lines")
    if mode == "line_strip":
        i0 = np.arange(n - 1)
    else:
        i0 = np.arange(0, n - 1, 2)
    i1 = i0 + 1

    cols = geom.colors
    if cols is None:
        rgb = np.full((n, 3), 0.8, dtype=float)
    else:
        rgb = np.asarray(cols, dtype=float).reshape(-1, np.asarray(cols).shape[-1])[:, :3]
        if rgb.shape[0] != n:  # one colour for the whole geometry
            rgb = np.repeat(rgb[:1], n, axis=0)
    return pos[i0], pos[i1], np.clip(rgb[i0], 0.0, 1.0), np.clip(rgb[i1], 0.0, 1.0)


def _sausages(
    p0: np.ndarray,
    p1: np.ndarray,
    c0: np.ndarray,
    c1: np.ndarray,
    radius: float,
    sides: int = _LINE_SIDES,
) -> tuple[list[Sphere], np.ndarray, np.ndarray, np.ndarray]:
    """Turn line segments into round-capped cylinders the tracer can hit.

    PyMOL ray-traces a line as ``ray->sausage3fv(v0, v1, lineradius, c0, c2)``
    (``layer1/CGO.cpp``, ``CGO_LINE``) and splits a two-coloured one at its
    midpoint into two capped cylinders rather than blending across it
    (``CGO_SPLITLINE``). Both halves are emitted here unconditionally: where the
    endpoint colours agree the two halves *are* one cylinder, so there is no
    branch that can pick wrong.

    Parameters
    ----------
    p0, p1 : ndarray
        Segment endpoints, shape ``(S, 3)``.
    c0, c1 : ndarray
        RGB at each endpoint, shape ``(S, 3)``.
    radius : float
        Shaft radius in world units.
    sides : int
        Faces around the shaft.

    Returns
    -------
    tuple
        ``(cap_spheres, tri_vertices, tri_vnormals, tri_colors)``, in the layout
        :func:`trace` expects.
    """
    empty = (np.zeros((0, 3, 3)), np.zeros((0, 3, 3)), np.zeros((0, 3)))
    if p0.shape[0] == 0 or radius <= 0.0:
        return ([], *empty)

    axis = p1 - p0
    length = np.linalg.norm(axis, axis=1)
    keep = length > 1e-9
    p0, p1, c0, c1, axis = p0[keep], p1[keep], c0[keep], c1[keep], axis[keep]
    length = length[keep]
    s = p0.shape[0]
    if s == 0:
        return ([], *empty)

    unit = axis / length[:, None]
    # A frame around the axis: cross it with whichever world axis it leans on
    # least, so the cross product never collapses on an axis-aligned segment --
    # and axis-aligned is the common case in a wireframe, not the rare one.
    helper = np.zeros_like(unit)
    helper[np.arange(s), np.argmin(np.abs(unit), axis=1)] = 1.0
    u = np.cross(unit, helper)
    u /= np.linalg.norm(u, axis=1)[:, None]
    v = np.cross(unit, u)

    theta = np.linspace(0.0, 2.0 * math.pi, sides, endpoint=False)
    # (S, sides, 3): each ring vertex's radial direction, which is also its
    # normal -- shading from radial normals is what makes an eight-sided shaft
    # read as round instead of as a prism.
    radial = (
        np.cos(theta)[None, :, None] * u[:, None, :]
        + np.sin(theta)[None, :, None] * v[:, None, :]
    )
    mid = 0.5 * (p0 + p1)
    nxt = (np.arange(sides) + 1) % sides

    verts, norms, cols = [], [], []
    for a, b, colour in ((p0, mid, c0), (mid, p1, c1)):
        ring_a = a[:, None, :] + radius * radial
        ring_b = b[:, None, :] + radius * radial
        tri = np.concatenate(
            [
                np.stack([ring_a, ring_b, ring_a[:, nxt]], axis=2),
                np.stack([ring_a[:, nxt], ring_b, ring_b[:, nxt]], axis=2),
            ],
            axis=1,
        ).reshape(-1, 3, 3)
        nrm = np.concatenate(
            [
                np.stack([radial, radial, radial[:, nxt]], axis=2),
                np.stack([radial[:, nxt], radial, radial[:, nxt]], axis=2),
            ],
            axis=1,
        ).reshape(-1, 3, 3)
        verts.append(tri)
        norms.append(nrm)
        cols.append(np.repeat(colour, 2 * sides, axis=0))

    caps = [Sphere(center=p0[i], radius=radius, color=c0[i]) for i in range(s)]
    caps += [Sphere(center=p1[i], radius=radius, color=c1[i]) for i in range(s)]
    return (
        caps,
        np.concatenate(verts, axis=0),
        np.concatenate(norms, axis=0),
        np.concatenate(cols, axis=0),
    )


def line_radius_for_camera(
    camera: RayCamera,
    height: int,
    depth: float,
    line_width: float = 1.0,
    line_radius: float = 0.0,
) -> float:
    """Return the world radius a line of ``line_width`` pixels should be drawn at.

    PyMOL's rule is ``radius = line_radius`` when that setting is positive and
    ``PixelRadius * line_width / 2`` otherwise (``layer1/CGO.cpp``,
    ``LINEWIDTH_FOR_LINES``), where ``PixelRadius`` is the world size of one
    output pixel. A line therefore comes out ``line_width`` *pixels* wide at any
    image resolution, which is the property worth carrying over: a wireframe
    rendered at 2000 px would otherwise be hairline.

    PyMOL measures that pixel at the front clipping plane, because its ray volume
    is fitted to the object. ChiMOL's near plane is a camera setting and can sit
    well in front of the molecule, so the pixel is measured at ``depth`` -- the
    plane the scene occupies -- and the width is right where it is looked at.

    Parameters
    ----------
    camera : RayCamera
        Camera being rendered from; supplies the field of view.
    height : int
        Output image height in pixels.
    depth : float
        Distance from the camera to the plane the lines sit on.
    line_width : float
        Width in pixels, PyMOL's ``line_width`` setting.
    line_radius : float
        World radius, PyMOL's ``line_radius``. A positive value wins outright.

    Returns
    -------
    float
        Shaft radius in world units.
    """
    if line_radius > 0.0:
        return float(line_radius)
    half_h = math.tan(math.radians(camera.fov_degrees) * 0.5)
    pixel = 2.0 * max(float(depth), 1e-6) * half_h / max(int(height), 1)
    return pixel * max(float(line_width), 0.0) / 2.0


def render_scene(
    scene,
    camera: RayCamera,
    light_directions: np.ndarray,
    width: int,
    height: int,
    background: tuple = (25, 25, 25),
    ambient: float = 0.14,
    diffuse: float = 0.45,
    specular: float = 0.25,
    shininess: float = 40.0,
    depth_cue: bool = True,
    fog_start: float = 0.45,
    fog_intensity: float = 1.0,
    line_width: float = 1.0,
    line_radius: float = 0.0,
    **kwargs
) -> np.ndarray:
    """Render a Scene object by extracting all renderable geometry.

    Handles ``points`` geometry (spheres), ``mesh`` geometry (triangles) and
    ``line`` geometry (round-capped cylinders, as PyMOL's ray does). ``text`` is
    the one kind it cannot trace; :func:`traceable_geometry_counts` is how a
    caller finds that out and says so, rather than dropping labels in silence.
    The result is passed to :func:`trace` with both sphere and triangle data.
    """
    spheres: list[Sphere] = []
    tri_vertices_list: list[np.ndarray] = []
    tri_vnormals_list: list[np.ndarray] = []
    tri_colors_list: list[np.ndarray] = []
    tri_alpha_list: list[np.ndarray] = []

    # One radius for every line in the picture, as PyMOL uses one `lineradius`
    # per CGO: measured where the scene is, not per segment, so a wireframe does
    # not taper across the molecule.
    scene_depth = float(
        np.dot(np.asarray(getattr(scene, "center", np.zeros(3)), dtype=float) - camera.origin, camera.forward)
    )
    shaft_radius = line_radius_for_camera(
        camera, height, scene_depth, line_width=line_width, line_radius=line_radius
    )

    # The depth cue runs across the *scene*, front to back of its bounding
    # sphere, the way PyMOL's runs across its object-fitted clipping planes. Left
    # to the camera's far plane it grades over a range the molecule occupies a
    # slice of, and comes out as a flat dimming (see `trace`).
    scene_radius = float(getattr(scene, "radius", 0.0) or 0.0)
    kwargs.setdefault("fog_front", max(0.0, scene_depth - scene_radius))
    kwargs.setdefault("fog_back", scene_depth + scene_radius)

    for obj in scene.objects:
        geom = obj.geometry
        if geom.kind == "points":
            positions = np.asarray(geom.positions, dtype=float)
            colors = np.asarray(geom.colors, dtype=float) if geom.colors is not None else None
            radii_arr = np.asarray(geom.radii, dtype=float) if geom.radii is not None else None
            meta_radius = geom.meta.get("radius", 0.5) if isinstance(geom.meta, dict) else 0.5
            for i in range(positions.shape[0]):
                r = float(radii_arr[i]) if radii_arr is not None else float(meta_radius)
                c = np.clip(colors[i, :3], 0.0, 1.0) if colors is not None else np.array([0.8, 0.8, 0.8])
                a = (
                    float(colors[i, 3])
                    if colors is not None and colors.shape[1] > 3
                    else 1.0
                )
                spheres.append(Sphere(center=positions[i], radius=r, color=c, alpha=a))

        elif geom.kind == "mesh" and (geom.meta or {}).get("spheres") is not None:
            # A mesh that is really a pile of spheres says so, and the tracer
            # intersects those exactly -- faster than its own triangles by more
            # than two orders of magnitude, and without their facets.
            balls = geom.meta["spheres"]
            centres = np.asarray(balls["centers"], dtype=float)
            ball_radii = np.asarray(balls["radii"], dtype=float)
            ball_cols = np.asarray(balls["colors"], dtype=float)
            for i in range(centres.shape[0]):
                spheres.append(Sphere(
                    center=centres[i],
                    radius=float(ball_radii[i]),
                    color=np.clip(ball_cols[i, :3], 0.0, 1.0),
                    alpha=(
                        float(ball_cols[i, 3]) if ball_cols.shape[1] > 3 else 1.0
                    ),
                ))

        elif geom.kind == "mesh":
            verts = np.asarray(geom.positions, dtype=float)
            norms = np.asarray(geom.normals, dtype=float) if geom.normals is not None else None
            cols = np.asarray(geom.colors, dtype=float) if geom.colors is not None else None
            idx = np.asarray(geom.indices, dtype=np.int32) if geom.indices is not None else None

            if idx is not None and idx.shape[1] == 3:
                # Indexed triangle mesh
                t = np.stack([verts[idx[:, 0]], verts[idx[:, 1]], verts[idx[:, 2]]], axis=1)
                if norms is not None and norms.shape == verts.shape:
                    tn = np.stack([norms[idx[:, 0]], norms[idx[:, 1]], norms[idx[:, 2]]], axis=1)
                elif norms is not None:
                    tn = np.tile(norms, (idx.shape[0], 1, 1))
                else:
                    tn = np.zeros_like(t)
                if cols is not None and cols.shape[0] == verts.shape[0]:
                    tc = cols[idx[:, 0], :3] if cols.ndim == 2 else cols[idx[:, 0]]
                elif cols is not None:
                    tc = cols[:3] if cols.ndim == 1 else cols[0, :3]
                else:
                    tc = np.full((idx.shape[0], 3), 0.8)
                tri_vertices_list.append(t)
                tri_vnormals_list.append(tn)
                tri_colors_list.append(tc)
                tri_alpha_list.append(_triangle_alpha(cols, idx[:, 0], idx.shape[0]))

            else:
                # Non-indexed triangles (N*3 vertices in triangle order)
                n_tris = verts.shape[0] // 3
                t = verts.reshape(n_tris, 3, 3)
                if norms is not None:
                    tn = norms.reshape(n_tris, 3, 3)
                else:
                    tn = np.zeros((n_tris, 3, 3), dtype=float)
                if cols is not None and cols.shape[-1] >= 3:
                    tc = cols.reshape(n_tris, 3, -1)[:, 0, :3]
                else:
                    tc = np.full((n_tris, 3), 0.8)
                tri_vertices_list.append(t)
                tri_vnormals_list.append(tn)
                tri_colors_list.append(tc)
                tri_alpha_list.append(
                    _triangle_alpha(cols, np.arange(0, n_tris * 3, 3), n_tris)
                )

        elif geom.kind == "line":
            caps, lv, ln, lc = _sausages(*_line_segments(geom), shaft_radius)
            if lv.shape[0]:
                spheres.extend(caps)
                tri_vertices_list.append(lv)
                tri_vnormals_list.append(ln)
                tri_colors_list.append(lc)
                # A wireframe is opaque; `_sausages` builds its own geometry and
                # carries no alpha of its own.
                tri_alpha_list.append(np.ones(lv.shape[0], dtype=float))

    # Concatenate all triangle data. The alpha list is built alongside the
    # colours at every append site, so a mismatch means one was missed -- which
    # is what happened when `line` grew triangles and no opacity, and surfaced
    # far away as "need at least one array to concatenate".
    assert len(tri_alpha_list) == len(tri_colors_list), (
        "every triangle chunk needs an opacity chunk"
    )
    if tri_vertices_list:
        all_verts = np.concatenate(tri_vertices_list, axis=0)
        all_norms = np.concatenate(tri_vnormals_list, axis=0)
        all_cols = np.concatenate(tri_colors_list, axis=0)
        all_alpha = np.concatenate(tri_alpha_list, axis=0)
    else:
        all_verts = np.zeros((0, 3, 3), dtype=float)
        all_norms = np.zeros((0, 3, 3), dtype=float)
        all_cols = np.zeros((0, 3), dtype=float)
        all_alpha = np.zeros(0, dtype=float)

    return trace(
        spheres=spheres,
        camera=camera,
        light_directions=light_directions,
        width=width,
        height=height,
        background=background,
        ambient=ambient,
        diffuse=diffuse,
        specular=specular,
        shininess=shininess,
        depth_cue=depth_cue,
        fog_start=fog_start,
        fog_intensity=fog_intensity,
        tri_vertices=all_verts,
        tri_vnormals=all_norms,
        tri_colors=all_cols,
        tri_alpha=all_alpha,
        **kwargs
    )
