from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

# Numba is required, not optional. The pure-NumPy twin that used to stand in for
# it was a second implementation of the same tracer that nothing exercised while
# numba was installed -- and it was silently broken for exactly that reason: the
# transparency work landed in both, and only the compiled one was ever run.
# A fallback nobody runs is not a safety net, it is an untested branch.
import numba as _nb
import numpy as np

from .bvh import _MAX_LEAF, STACK_SIZE, build_bvh, closest_hit, primitive_bounds
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
# Numba-accelerated kernel
# ------------------------------------------------------------------ #

_JIT_SPECDICT = {
    "nopython": True,
    "fastmath": True,
    "cache": True,
    "parallel": True,
}

@_nb.njit(**_JIT_SPECDICT)
def _jit_trace(
    centers: np.ndarray,
    radii: np.ndarray,
    col_rgb: np.ndarray,
    sph_alpha: np.ndarray,
    tri_vertices: np.ndarray,
    tri_vnormals: np.ndarray,
    tri_colors: np.ndarray,
    tri_alpha: np.ndarray,
    scene_node_min: np.ndarray,
    scene_node_max: np.ndarray,
    scene_node_left: np.ndarray,
    scene_node_start: np.ndarray,
    scene_node_count: np.ndarray,
    scene_prim_index: np.ndarray,
    cam_origin: np.ndarray,
    cam_forward: np.ndarray,
    cam_up: np.ndarray,
    fov_radians: float,
    light_dirs: np.ndarray,
    width: int,
    height: int,
    ssaa: int,
    bg_r: int,
    bg_g: int,
    bg_b: int,
    ambient: float,
    diffuse: float,
    specular: float,
    shininess: float,
    direct_spec: float,
    direct_spec_power: float,
    reflect_power: float,
    direct: float,
    direct_power: float,
    legacy_lighting: float,
    shadow_enabled: int,
    shadow_fudge: float,
    shadow_decay_factor: float,
    shadow_decay_range: float,
    depth_cue_enabled: int,
    fog_start: float,
    fog_intensity: float,
    fog_front: float,
    fog_inv_range: float,
    progress: np.ndarray,
    cancel: np.ndarray,
    max_layers: int,
) -> np.ndarray:
    """JIT-compiled ray tracing kernel with sphere + triangle support.

    Each ray walks *through* the scene rather than stopping at the first
    surface: every hit contributes its alpha and the remainder is passed
    along, so a translucent surface shows what is behind it. ``max_layers``
    bounds that walk -- a closed surface with a cartoon inside needs three
    or four, and the walk also stops on its own once the remaining
    transmittance cannot change a byte.
    """
    n_spheres: int = centers.shape[0]
    rw: int = int(width * ssaa)
    rh: int = int(height * ssaa)
    n_lights: int = light_dirs.shape[0]

    right = np.cross(cam_forward, cam_up)
    rn = _jit_length(right)
    if rn < 1e-9:
        right = np.array([1.0, 0.0, 0.0], dtype=np.float64)
    else:
        right[0] /= rn
        right[1] /= rn
        right[2] /= rn
    fw = cam_forward.copy()
    up = np.cross(right, fw)
    un = _jit_length(up)
    up[0] /= un
    up[1] /= un
    up[2] /= un

    half_h = math.tan(fov_radians * 0.5)
    aspect = float(rw) / float(max(rh, 1))
    half_w = half_h * aspect

    out = np.zeros((height, width, 3), dtype=np.float64)
    accum = np.zeros((height, width), dtype=np.float64)

    bg_f = float(bg_r) / 255.0
    bg_g_f = float(bg_g) / 255.0
    bg_b_f = float(bg_b) / 255.0

    ldirs = np.zeros((n_lights, 3), dtype=np.float64)
    for li in range(n_lights):
        ld = light_dirs[li]
        ln = math.sqrt(ld[0]*ld[0] + ld[1]*ld[1] + ld[2]*ld[2])
        if ln < 1e-9:
            ln = 1.0
        ldirs[li, 0] = ld[0] / ln
        ldirs[li, 1] = ld[1] / ln
        ldirs[li, 2] = ld[2] / ln

    spec_per_light = 1.0 / pow(float(max(n_lights - 1, 1)), 0.6)
    legacy = max(0.0, min(1.0, legacy_lighting))

    for py in _nb.prange(rh):
        if py == 0 or py == rh - 1:
            if cancel[0] != 0:
                continue
        # One scratch stack per row. Allocated inside the parallel loop so each
        # thread gets its own, and outside the pixel loop so a row's worth of
        # rays share it -- the primary walk has finished before the shadow walk
        # starts, so they cannot both be using it.
        stack = np.empty(STACK_SIZE, dtype=np.int32)
        for px in range(rw):
            u = (float(px) + 0.5) / float(max(rw - 1, 1)) - 0.5
            v = 0.5 - (float(py) + 0.5) / float(max(rh - 1, 1))

            dir_x = fw[0] + right[0] * u * 2.0 * half_w + up[0] * v * 2.0 * half_h
            dir_y = fw[1] + right[1] * u * 2.0 * half_w + up[1] * v * 2.0 * half_h
            dir_z = fw[2] + right[2] * u * 2.0 * half_w + up[2] * v * 2.0 * half_h
            dlen = math.sqrt(dir_x * dir_x + dir_y * dir_y + dir_z * dir_z)
            if dlen < 1e-9:
                dlen = 1.0
            dir_x /= dlen
            dir_y /= dlen
            dir_z /= dlen

            rox, roy, roz = cam_origin[0], cam_origin[1], cam_origin[2]

            acc_r = 0.0
            acc_g = 0.0
            acc_b = 0.0
            trans = 1.0
            t_min = 1e-6
            any_hit = False
            for _layer in range(max_layers):
                # One descent of the tree finds the nearest of both kinds: the
                # scene BVH holds spheres and triangles in one index space, so
                # this replaces a sweep of every primitive in the scene.
                best_t, best_prim = closest_hit(
                    rox, roy, roz, dir_x, dir_y, dir_z,
                    t_min, np.inf,
                    scene_node_min, scene_node_max, scene_node_left,
                    scene_node_start, scene_node_count, scene_prim_index,
                    n_spheres, centers, radii, tri_vertices,
                    -1, stack,
                )
                if best_prim < 0:
                    break
                best_is_tri = best_prim >= n_spheres
                if best_is_tri:
                    best_id = best_prim - n_spheres
                else:
                    best_id = best_prim

                # ---- hit point & normal ------
                hx = rox + dir_x * best_t
                hy = roy + dir_y * best_t
                hz = roz + dir_z * best_t

                if best_is_tri:
                    # Interpolate vertex normal via barycentric coords
                    ti = best_id
                    v0x = tri_vertices[ti, 0, 0]
                    v0y = tri_vertices[ti, 0, 1]
                    v0z = tri_vertices[ti, 0, 2]
                    v1x = tri_vertices[ti, 1, 0]
                    v1y = tri_vertices[ti, 1, 1]
                    v1z = tri_vertices[ti, 1, 2]
                    v2x = tri_vertices[ti, 2, 0]
                    v2y = tri_vertices[ti, 2, 1]
                    v2z = tri_vertices[ti, 2, 2]

                    # Compute barycentric coords of hit point
                    e1x = v1x - v0x
                    e1y = v1y - v0y
                    e1z = v1z - v0z
                    e2x = v2x - v0x
                    e2y = v2y - v0y
                    e2z = v2z - v0z
                    ppx = hx - v0x
                    ppy = hy - v0y
                    ppz = hz - v0z
                    d00 = e1x*e1x + e1y*e1y + e1z*e1z
                    d01 = e1x*e2x + e1y*e2y + e1z*e2z
                    d11 = e2x*e2x + e2y*e2y + e2z*e2z
                    d20 = ppx*e1x + ppy*e1y + ppz*e1z
                    d21 = ppx*e2x + ppy*e2y + ppz*e2z
                    denom = d00 * d11 - d01 * d01
                    if abs(denom) > 1e-12:
                        u_bc = (d11 * d20 - d01 * d21) / denom
                        v_bc = (d00 * d21 - d01 * d20) / denom
                    else:
                        u_bc = 0.0
                        v_bc = 0.0
                    w_bc = 1.0 - u_bc - v_bc

                    n0x = tri_vnormals[ti, 0, 0]
                    n0y = tri_vnormals[ti, 0, 1]
                    n0z = tri_vnormals[ti, 0, 2]
                    n1x = tri_vnormals[ti, 1, 0]
                    n1y = tri_vnormals[ti, 1, 1]
                    n1z = tri_vnormals[ti, 1, 2]
                    n2x = tri_vnormals[ti, 2, 0]
                    n2y = tri_vnormals[ti, 2, 1]
                    n2z = tri_vnormals[ti, 2, 2]

                    nx = w_bc * n0x + u_bc * n1x + v_bc * n2x
                    ny = w_bc * n0y + u_bc * n1y + v_bc * n2y
                    nz = w_bc * n0z + u_bc * n1z + v_bc * n2z
                    nl = math.sqrt(nx*nx + ny*ny + nz*nz)
                    if nl < 1e-9:
                        nl = 1.0
                    nx /= nl
                    ny /= nl
                    nz /= nl

                    cr = tri_colors[ti, 0]
                    cg = tri_colors[ti, 1]
                    cb = tri_colors[ti, 2]
                else:
                    nx = hx - centers[best_id, 0]
                    ny = hy - centers[best_id, 1]
                    nz = hz - centers[best_id, 2]
                    nl = math.sqrt(nx * nx + ny * ny + nz * nz)
                    if nl < 1e-9:
                        nl = 1.0
                    nx /= nl
                    ny /= nl
                    nz /= nl
                    cr = col_rgb[best_id, 0]
                    cg = col_rgb[best_id, 1]
                    cb = col_rgb[best_id, 2]

                vx = cam_origin[0] - hx
                vy = cam_origin[1] - hy
                vz = cam_origin[2] - hz
                vl = math.sqrt(vx * vx + vy * vy + vz * vz) + 1e-9
                vx /= vl
                vy /= vl
                vz /= vl

                reflect_sum = 0.0
                spec_sum = 0.0

                for li in range(n_lights):
                    lx = ldirs[li, 0]
                    ly = ldirs[li, 1]
                    lz = ldirs[li, 2]

                    if shadow_enabled:
                        # The surface the ray leaves from is skipped by its
                        # own unified index, so this is right for a triangle as
                        # well as a sphere. It used to pass `best_id`
                        # unconditionally, which on a triangle hit excluded
                        # whichever sphere happened to share that index.
                        lit = _jit_shadow_soft(
                            hx + lx * shadow_fudge,
                            hy + ly * shadow_fudge,
                            hz + lz * shadow_fudge,
                            lx, ly, lz,
                            centers, radii, tri_vertices,
                            scene_node_min, scene_node_max, scene_node_left,
                            scene_node_start, scene_node_count,
                            scene_prim_index,
                            n_spheres, best_prim,
                            shadow_decay_factor, shadow_decay_range,
                            stack,
                        )
                    else:
                        lit = 1.0

                    n_dot_l = nx * lx + ny * ly + nz * lz
                    if n_dot_l < 0.0:
                        n_dot_l = 0.0
                    if n_dot_l > 1.0:
                        n_dot_l = 1.0

                    if lit > 0.0 and n_dot_l > 0.0:
                        reflect_sum += lit * pow(n_dot_l, reflect_power)

                    if lit > 0.0 and n_dot_l > 0.0:
                        hnx = lx + vx
                        hny = ly + vy
                        hnz = lz + vz
                        hn = math.sqrt(hnx*hnx + hny*hny + hnz*hnz)
                        if hn > 1e-9:
                            hnx /= hn
                            hny /= hn
                            hnz /= hn
                            n_dot_h = nx*hnx + ny*hny + nz*hnz
                            if n_dot_h < 0.0:
                                n_dot_h = 0.0
                            if n_dot_h > 1.0:
                                n_dot_h = 1.0
                            spec_sum += lit * pow(n_dot_h, shininess)

                reflect_norm = reflect_sum / float(max(n_lights, 1))

                n_dot_v = nx * vx + ny * vy + nz * vz
                if n_dot_v < 0.0:
                    n_dot_v = 0.0
                if n_dot_v > 1.0:
                    n_dot_v = 1.0
                direct_cmp = pow(n_dot_v, direct_spec_power)

                if legacy > 0.0:
                    n_dot_l0 = nx * ldirs[0, 0] + ny * ldirs[0, 1] + nz * ldirs[0, 2]
                    if n_dot_l0 < 0.0:
                        n_dot_l0 = 0.0
                    legacy_bright = ambient + diffuse * n_dot_l0
                else:
                    legacy_bright = 0.0

                # PyMOL's brightness has **two** diffuse terms and chimol had
                # only one (`layer1/Ray.cpp`):
                #
                #   bright = ambient
                #          + ((1-direct_shade) + direct_shade*lit) * direct * direct_cmp
                #          + lreflect * reflect_cmp
                #
                # `direct_cmp` is `pow(surfnormal[2], power)` -- the normal's z in
                # camera space, so `direct` is a **headlight**: a surface facing
                # the viewer is lit whatever the lamps are doing. `reflect` is
                # the lamp-driven term, divided over the lights ("divide up the
                # reflected light component over all lights"), which is what
                # `reflect_norm` already is.
                #
                # Without the headlight the ceiling was ambient + diffuse =
                # 0.14 + 0.45 = 0.59, and only where a lamp faced the surface
                # squarely; PyMOL's is 0.14 + 0.45 + 0.45, clamped to 1. That
                # missing 0.45 is why a traced image came out far darker than
                # the viewport it was meant to reproduce.
                bright = ambient + direct * pow(n_dot_v, direct_power) \
                    + diffuse * reflect_norm
                if legacy > 0.0:
                    bright = bright * (1.0 - legacy) + legacy_bright * legacy
                if bright < 0.0:
                    bright = 0.0
                if bright > 1.0:
                    bright = 1.0

                excess = direct_spec * direct_cmp + specular * spec_sum * spec_per_light
                if excess < 0.0:
                    excess = 0.0
                if excess > 1.0:
                    excess = 1.0

                cr_out = cr * bright + excess
                cg_out = cg * bright + excess
                cb_out = cb * bright + excess

                if depth_cue_enabled and fog_inv_range > 0.0:
                    nd = (best_t - fog_front) * fog_inv_range
                    if nd > fog_start:
                        ffact = (nd - fog_start) / (1.0 - fog_start) * fog_intensity
                        if ffact > 1.0:
                            ffact = 1.0
                        if ffact > 0.0:
                            cr_out = cr_out * (1.0 - ffact) + bg_f * ffact
                            cg_out = cg_out * (1.0 - ffact) + bg_g_f * ffact
                            cb_out = cb_out * (1.0 - ffact) + bg_b_f * ffact

                # Front-to-back compositing. `trans` is how much of what lies
                # behind still reaches the eye; each layer takes its alpha out
                # of it. Stopping at the first surface -- which is what this
                # did -- renders a `transparency 0.6` shell as solid.
                a_hit = 1.0
                if best_is_tri:
                    a_hit = tri_alpha[best_id]
                else:
                    a_hit = sph_alpha[best_id]
                if a_hit < 0.0:
                    a_hit = 0.0
                if a_hit > 1.0:
                    a_hit = 1.0
                acc_r += trans * a_hit * cr_out
                acc_g += trans * a_hit * cg_out
                acc_b += trans * a_hit * cb_out
                any_hit = True
                trans *= (1.0 - a_hit)
                # Below ~1/255 the next layer cannot change a byte, so the walk
                # stops rather than paying for surfaces nobody will see.
                if trans < 0.004:
                    break
                # Step past this surface, or the next search finds it again.
                t_min = best_t + 1e-4

            if not any_hit:
                continue
            # Whatever is still transmitted is background, exactly as the
            # viewport blends it.
            cr_out = acc_r + trans * bg_f
            cg_out = acc_g + trans * bg_g_f
            cb_out = acc_b + trans * bg_b_f

            oy = py // ssaa
            ox = px // ssaa
            out[oy, ox, 0] += cr_out
            out[oy, ox, 1] += cg_out
            out[oy, ox, 2] += cb_out
            accum[oy, ox] += 1.0

    img = np.zeros((height, width, 3), dtype=np.uint8)
    for y in range(height):
        for x in range(width):
            w = accum[y, x]
            if w < 0.5:
                r = bg_r
                g = bg_g
                b = bg_b
            else:
                inv = 1.0 / w
                r = int(out[y, x, 0] * inv * 255.0)
                g = int(out[y, x, 1] * inv * 255.0)
                b = int(out[y, x, 2] * inv * 255.0)
                if r > 255: r = 255
                if g > 255: g = 255
                if b > 255: b = 255
                if r < 0: r = 0
                if g < 0: g = 0
                if b < 0: b = 0
            img[y, x, 0] = np.uint8(r)
            img[y, x, 1] = np.uint8(g)
            img[y, x, 2] = np.uint8(b)
    return img

@_nb.njit(fastmath=True, cache=True)
def _jit_length(v: np.ndarray) -> float:
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])

@_nb.njit(fastmath=True, cache=True)
def _jit_shadow_soft(
    hx: float, hy: float, hz: float,
    lx: float, ly: float, lz: float,
    centers: np.ndarray,
    radii: np.ndarray,
    tri_vertices: np.ndarray,
    node_min: np.ndarray,
    node_max: np.ndarray,
    node_left: np.ndarray,
    node_start: np.ndarray,
    node_count: np.ndarray,
    prim_index: np.ndarray,
    n_spheres: int,
    skip_idx: int,
    decay_factor: float,
    decay_range: float,
    stack: np.ndarray,
) -> float:
    """How much of one light reaches a point: 1 fully lit, 0 fully shadowed.

    Every primitive casts, which is what PyMOL does. This used to walk a
    sphere-only tree, so a cartoon -- the display chimol and PyMOL both start
    with -- cast no shadow at all and ``ray_shadow`` did nothing on it. Testing
    the whole scene was unaffordable while a shadow ray cost a sweep of it; with
    the BVH it is one more descent.

    The occluder taken is the **nearest** one. PyMOL does the same, and only
    when the decay is on -- ``nearest_shadow = (shadow_decay != _0)`` in
    ``layer1/Ray.cpp`` -- because the decay is a function of how far the
    occluder is, so any other occluder answers a different question. This used
    to return whichever sphere came first in the array, which made how soft a
    shadow came out depend on the order the scene happened to be built in.
    """
    if node_count.shape[0] == 0:
        return 1.0
    t, prim = closest_hit(
        hx, hy, hz, lx, ly, lz,
        1e-6, np.inf,
        node_min, node_max, node_left, node_start, node_count, prim_index,
        n_spheres, centers, radii, tri_vertices,
        skip_idx, stack,
    )
    if prim < 0:
        return 1.0
    if decay_factor > 0.0:
        d = t - decay_range
        if d <= 0.0:
            return 1.0
        occlusion = 1.0 - math.exp(-d * decay_factor)
        if occlusion >= 1.0:
            return 0.0
        return 1.0 - occlusion
    return 0.0


# ------------------------------------------------------------------ #
# Public API (falls back if Numba unavailable)
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

    img = _jit_trace(
        centers, radii_arr, colors_arr, sph_alpha_arr,
        tverts, tnorms, tcols, talpha,
        *scene_bvh,
        camera.origin.astype(np.float64).copy(),
        camera.forward.astype(np.float64).copy(),
        camera.up.astype(np.float64).copy(),
        float(fov_rad),
        lds,
        int(width), int(height), int(ssaa),
        int(bg_r), int(bg_g), int(bg_b),
        float(ambient), float(diffuse), float(specular), float(shininess),
        float(direct_specular), float(direct_specular_power),
        float(reflect_power), float(direct), float(direct_power),
        float(legacy_lighting),
        int(shadow), float(shadow_fudge),
        float(shadow_decay_factor), float(shadow_decay_range),
        int(depth_cue), float(fog_start), float(fog_intensity),
        float(front), float(fog_inv_range),
        progress,
        cancel,
        int(max(1, max_layers)),
    )

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
