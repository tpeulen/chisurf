"""WebGPU device, pipelines and 2-D geometry for the chiplot native backend.

Why WebGPU and not OpenGL
-------------------------
macOS reports ``2.1 Metal - 90.5`` for a plain GL context — Apple deprecated
OpenGL and what is left is a 2001-era feature set emulated over Metal. A native
plot renderer built on it inherits every one of those limits (no reliable
``gl_PointSize``, ``texture1D`` that may or may not exist, a ``QPainter``/GL
compositing dance that blanks the framebuffer). WebGPU spans macOS, Linux,
Windows *and* the browser through one shader text, which is the same reason the
molecular viewer's renderer moved to it.

How a frame is drawn
--------------------
Rendering is **offscreen**, and the resulting RGBA is blitted into the widget by
``QPainter`` which then draws the axes, ticks and labels on top. That is not a
compromise, it is the point:

* there is no GPU-surface-versus-``QPainter`` compositing problem to lose the
  frame to, which is what made the OpenGL attempt come out black;
* the identical path runs with no window at all, so a headless screenshot test
  renders the real thing rather than a stand-in;
* text stays with Qt, which already knows the application's fonts.

The cost is one GPU→CPU copy per repaint — a 480x360 panel is 700 kB, and plot
panels repaint on interaction, not at 60 Hz.

Geometry
--------
WebGPU has no line width and no point size: both were fixed-function features
that went away. Strokes are therefore expanded to triangles here, in pixel space
(:func:`expand_polyline`), and markers are polygon templates instanced onto the
data points (:func:`marker_geometry`). Doing it on the CPU is also what makes
dashes and round joins possible at all, neither of which OpenGL's
``glLineWidth`` ever offered.
"""

from __future__ import annotations

import pathlib
import threading
from dataclasses import dataclass, field

import numpy as np

WGSL_DIR = pathlib.Path(__file__).with_name("wgsl")

#: Multisample count for the offscreen colour attachment. Plot strokes are thin
#: and near-diagonal, and the renderer is compared against an antialiased
#: ``QPainter`` backend, so aliased edges read as "the native backend is worse"
#: rather than as a missing setting.
SAMPLE_COUNT = 4

_device_lock = threading.Lock()
_device = None
_adapter_info: dict = {}


def load_wgsl(name: str) -> str:
    """Read a shader from the backend's ``wgsl`` directory.

    Parameters
    ----------
    name : str
        File name, e.g. ``"plot2d.wgsl"``.

    Returns
    -------
    str
        The shader source, unmodified.
    """
    return (WGSL_DIR / name).read_text()


def get_device():
    """Return the process-wide WebGPU device, creating it on first use.

    One device is shared by every plot panel: adapter enumeration costs
    hundreds of milliseconds, and a window with a dozen panels would otherwise
    pay it a dozen times.

    Returns
    -------
    wgpu.GPUDevice
        The shared device.
    """
    global _device, _adapter_info
    with _device_lock:
        if _device is None:
            import wgpu

            adapter = wgpu.gpu.request_adapter_sync(
                power_preference="high-performance")
            _adapter_info = dict(adapter.info)
            _device = adapter.request_device_sync()
        return _device


def adapter_info() -> dict:
    """Return the adapter description of the shared device (empty before use)."""
    return dict(_adapter_info)


def is_available() -> bool:
    """Return whether a WebGPU device can be created on this machine."""
    try:
        get_device()
    except Exception:
        return False
    return True


# ---------------------------------------------------------------------------
# Draw batches
# ---------------------------------------------------------------------------

@dataclass
class SolidBatch:
    """Triangles with per-vertex colour, in clip space.

    Attributes
    ----------
    verts : numpy.ndarray
        ``(N, 2)`` float32 clip-space positions.
    colors : numpy.ndarray
        ``(N, 4)`` float32 premultiplied-by-nothing RGBA in ``[0, 1]``.
    """

    verts: np.ndarray
    colors: np.ndarray


@dataclass
class ImageBatch:
    """A textured quad.

    Attributes
    ----------
    verts : numpy.ndarray
        ``(N, 2)`` float32 clip-space positions (a triangle list).
    uv : numpy.ndarray
        ``(N, 2)`` float32 texture coordinates.
    rgba : numpy.ndarray
        ``(H, W, 4)`` uint8 image data.
    key : object
        Identity used to cache the uploaded texture between frames; pass the
        owning handle so an unchanged image is not re-uploaded.
    version : int
        Bumped by the owner when ``rgba`` changes.
    """

    verts: np.ndarray
    uv: np.ndarray
    rgba: np.ndarray
    key: object = None
    version: int = 0


Batch = SolidBatch | ImageBatch


def solid(verts: np.ndarray, color: tuple[float, float, float, float]) -> SolidBatch:
    """Build a :class:`SolidBatch` with one colour for every vertex."""
    verts = np.ascontiguousarray(verts, dtype=np.float32)
    colors = np.tile(np.asarray(color, dtype=np.float32), (len(verts), 1))
    return SolidBatch(verts, colors)


# ---------------------------------------------------------------------------
# Geometry: clip space <-> isotropic pixel space
# ---------------------------------------------------------------------------

def to_pixel(verts: np.ndarray, size: tuple[float, float]) -> np.ndarray:
    """Scale clip-space coordinates to an isotropic pixel-sized space.

    Widths, marker sizes and dash lengths are all specified in pixels, and clip
    space is anisotropic whenever the panel is not square. Scaling by half the
    viewport gives a space where one unit is one pixel in both axes; the
    y direction still points up, which does not matter for lengths and normals.
    """
    w, h = size
    return np.column_stack([verts[:, 0] * (w / 2.0), verts[:, 1] * (h / 2.0)])


def to_clip(pts: np.ndarray, size: tuple[float, float]) -> np.ndarray:
    """Inverse of :func:`to_pixel`."""
    w, h = size
    return np.column_stack([
        pts[:, 0] / max(w / 2.0, 1e-9),
        pts[:, 1] / max(h / 2.0, 1e-9),
    ]).astype(np.float32)


def _finite_runs(pts: np.ndarray) -> list[np.ndarray]:
    """Split a point list into maximal runs of finite points."""
    ok = np.isfinite(pts).all(axis=1)
    if ok.all():
        return [pts] if len(pts) else []
    runs, start = [], None
    for i, good in enumerate(ok):
        if good and start is None:
            start = i
        elif not good and start is not None:
            if i - start >= 1:
                runs.append(pts[start:i])
            start = None
    if start is not None:
        runs.append(pts[start:])
    return runs


def _apply_dash(run: np.ndarray, pattern: tuple[float, ...]) -> list[np.ndarray]:
    """Cut a polyline into the "on" intervals of a pixel-space dash pattern."""
    seg = np.diff(run, axis=0)
    lengths = np.hypot(seg[:, 0], seg[:, 1])
    total = float(lengths.sum())
    if total <= 0:
        return []
    cycle = float(sum(pattern))
    if cycle <= 0:
        return [run]

    pieces: list[np.ndarray] = []
    # Walk the polyline once, carrying the phase within the dash cycle.
    phase = 0.0
    current: list[np.ndarray] = []
    on = True
    remaining = pattern[0]
    for i, seg_len in enumerate(lengths):
        p0, p1 = run[i], run[i + 1]
        if seg_len <= 0:
            continue
        travelled = 0.0
        while travelled < seg_len:
            step = min(remaining, seg_len - travelled)
            t0 = travelled / seg_len
            t1 = (travelled + step) / seg_len
            if on:
                a = p0 + (p1 - p0) * t0
                b = p0 + (p1 - p0) * t1
                if current and np.allclose(current[-1], a):
                    current.append(b)
                else:
                    if len(current) >= 2:
                        pieces.append(np.array(current))
                    current = [a, b]
            travelled += step
            remaining -= step
            if remaining <= 1e-9:
                if on and len(current) >= 2:
                    pieces.append(np.array(current))
                    current = []
                on = not on
                phase += 1
                remaining = pattern[int(phase) % len(pattern)]
    if len(current) >= 2:
        pieces.append(np.array(current))
    return pieces


def expand_polyline(
    verts: np.ndarray,
    size: tuple[float, float],
    width: float,
    *,
    dash: tuple[float, ...] | None = None,
    join_segments: int = 8,
) -> np.ndarray:
    """Expand a clip-space polyline into a triangle list of the given pixel width.

    WebGPU draws every line one pixel wide, so a stroke has to become geometry.
    Each segment becomes a quad in pixel space and each interior vertex a small
    round join, which is what keeps a steep TCSPC decay from showing a notch at
    every sample.

    Parameters
    ----------
    verts : numpy.ndarray
        ``(N, 2)`` clip-space polyline; non-finite points break the line.
    size : tuple of float
        Viewport ``(width, height)`` in pixels.
    width : float
        Stroke width in pixels.
    dash : tuple of float, optional
        On/off pattern in pixels. ``None`` draws solid.
    join_segments : int
        Facets used to round an interior join.

    Returns
    -------
    numpy.ndarray
        ``(M, 2)`` float32 clip-space triangle list (may be empty).
    """
    if len(verts) < 2:
        return np.zeros((0, 2), dtype=np.float32)
    half = max(float(width), 0.75) / 2.0
    pts_all = to_pixel(np.asarray(verts, dtype=np.float64), size)

    runs: list[np.ndarray] = []
    for run in _finite_runs(pts_all):
        if len(run) < 2:
            continue
        # Drop repeated points: a zero-length segment has no normal.
        keep = np.concatenate([[True], (np.diff(run, axis=0) != 0).any(axis=1)])
        run = run[keep]
        if len(run) < 2:
            continue
        runs.extend(_apply_dash(run, dash) if dash else [run])

    tris: list[np.ndarray] = []
    for run in runs:
        seg = np.diff(run, axis=0)
        lengths = np.hypot(seg[:, 0], seg[:, 1])
        good = lengths > 0
        if not good.any():
            continue
        seg, lengths = seg[good], lengths[good]
        p0 = run[:-1][good]
        p1 = run[1:][good]
        nrm = np.column_stack([-seg[:, 1], seg[:, 0]]) / lengths[:, None] * half
        a, b, c, d = p0 + nrm, p0 - nrm, p1 - nrm, p1 + nrm
        quad = np.stack([a, b, c, a, c, d], axis=1).reshape(-1, 2)
        tris.append(quad)

        if half > 0.75 and len(run) > 2:
            # Round join at every interior vertex.
            ang = np.linspace(0.0, 2.0 * np.pi, join_segments, endpoint=False)
            ring = np.column_stack([np.cos(ang), np.sin(ang)]) * half
            centers = p1[:-1]
            fan_a = centers[:, None, :] + ring[None, :, :]
            fan_b = centers[:, None, :] + np.roll(ring, -1, axis=0)[None, :, :]
            fan_c = np.broadcast_to(centers[:, None, :], fan_a.shape)
            join = np.stack([fan_c, fan_a, fan_b], axis=2).reshape(-1, 2)
            tris.append(join)

    if not tris:
        return np.zeros((0, 2), dtype=np.float32)
    return to_clip(np.concatenate(tris, axis=0), size)


def _marker_template(symbol: str, size: float) -> np.ndarray:
    """Return the outline of one marker, in pixels, centred on the origin."""
    r = max(float(size), 1.0) / 2.0
    sym = (symbol or "o").lower()
    if sym in ("o", "circle"):
        ang = np.linspace(0.0, 2.0 * np.pi, 16, endpoint=False)
        return np.column_stack([np.cos(ang), np.sin(ang)]) * r
    if sym in ("s", "square"):
        return np.array([[-r, -r], [r, -r], [r, r], [-r, r]])
    if sym in ("t", "triangle", "t1"):
        return np.array([[0.0, r], [-r, -r], [r, -r]])
    if sym in ("t2", "triangle_down"):
        return np.array([[0.0, -r], [r, r], [-r, r]])
    if sym in ("d", "diamond"):
        return np.array([[0.0, r], [r, 0.0], [0.0, -r], [-r, 0.0]])
    if sym in ("+", "plus"):
        t = r / 3.0
        return np.array([
            [-t, -r], [t, -r], [t, -t], [r, -t], [r, t], [t, t],
            [t, r], [-t, r], [-t, t], [-r, t], [-r, -t], [-t, -t],
        ])
    if sym in ("x", "cross"):
        t = r / 3.0
        base = np.array([
            [-t, -r], [t, -r], [t, -t], [r, -t], [r, t], [t, t],
            [t, r], [-t, r], [-t, t], [-r, t], [-r, -t], [-t, -t],
        ])
        ca, sa = np.cos(np.pi / 4), np.sin(np.pi / 4)
        return base @ np.array([[ca, -sa], [sa, ca]])
    if sym in ("star",):
        ang = np.linspace(np.pi / 2, np.pi / 2 + 2 * np.pi, 11)[:-1]
        rad = np.where(np.arange(10) % 2 == 0, r, r * 0.45)
        return np.column_stack([np.cos(ang) * rad, np.sin(ang) * rad])
    ang = np.linspace(0.0, 2.0 * np.pi, 16, endpoint=False)
    return np.column_stack([np.cos(ang), np.sin(ang)]) * r


def marker_geometry(
    verts: np.ndarray,
    size_px: float,
    symbol: str,
    viewport: tuple[float, float],
) -> np.ndarray:
    """Instance a marker outline onto every point, as a triangle list.

    Parameters
    ----------
    verts : numpy.ndarray
        ``(N, 2)`` clip-space point positions.
    size_px : float
        Marker diameter in pixels.
    symbol : str
        Marker name (see :func:`_marker_template`).
    viewport : tuple of float
        Viewport ``(width, height)`` in pixels.

    Returns
    -------
    numpy.ndarray
        ``(M, 2)`` float32 clip-space triangles.
    """
    pts = np.asarray(verts, dtype=np.float64)
    ok = np.isfinite(pts).all(axis=1)
    pts = pts[ok]
    if not len(pts):
        return np.zeros((0, 2), dtype=np.float32)
    centers = to_pixel(pts, viewport)
    tmpl = _marker_template(symbol, size_px)
    k = len(tmpl)
    # Triangulate the outline as a fan around its first vertex; every template
    # here is convex or (for plus/cross) star-shaped about the centre, so a fan
    # from the centre is safe — use the centre rather than vertex 0 for that.
    fan = np.empty((k, 3, 2))
    fan[:, 0] = 0.0
    fan[:, 1] = tmpl
    fan[:, 2] = np.roll(tmpl, -1, axis=0)
    quads = centers[:, None, None, :] + fan[None, :, :, :]
    return to_clip(quads.reshape(-1, 2), viewport)


def outline_geometry(
    verts: np.ndarray,
    viewport: tuple[float, float],
    width: float,
) -> np.ndarray:
    """Stroke a closed polygon (clip space) as a triangle list of pixel width."""
    if len(verts) < 2:
        return np.zeros((0, 2), dtype=np.float32)
    closed = np.vstack([verts, verts[:1]])
    return expand_polyline(closed, viewport, width)


def fill_between_geometry(
    x: np.ndarray, lo: np.ndarray, hi: np.ndarray,
) -> np.ndarray:
    """Triangulate the band between two y-series as a strip.

    A triangle *fan* — the obvious shortcut — is only correct for a convex
    polygon, and a band under a decay curve is not one; it produces a filled
    wedge that spills across the panel. Pairing the two series into quads is
    both correct and O(n).
    """
    x = np.asarray(x, dtype=np.float64)
    lo = np.asarray(lo, dtype=np.float64)
    hi = np.asarray(hi, dtype=np.float64)
    n = min(len(x), len(lo), len(hi))
    if n < 2:
        return np.zeros((0, 2), dtype=np.float32)
    x, lo, hi = x[:n], lo[:n], hi[:n]
    ok = np.isfinite(x) & np.isfinite(lo) & np.isfinite(hi)
    x, lo, hi = x[ok], lo[ok], hi[ok]
    if len(x) < 2:
        return np.zeros((0, 2), dtype=np.float32)
    a = np.column_stack([x[:-1], lo[:-1]])
    b = np.column_stack([x[1:], lo[1:]])
    c = np.column_stack([x[1:], hi[1:]])
    d = np.column_stack([x[:-1], hi[:-1]])
    return np.stack([a, b, c, a, c, d], axis=1).reshape(-1, 2).astype(np.float64)


def quad_geometry(x0: float, y0: float, x1: float, y1: float) -> np.ndarray:
    """Return the two triangles of an axis-aligned rectangle."""
    return np.array([
        [x0, y0], [x1, y0], [x1, y1],
        [x0, y0], [x1, y1], [x0, y1],
    ], dtype=np.float64)


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

@dataclass
class _Target:
    """Cached render targets for one framebuffer size."""

    width: int
    height: int
    color: object
    resolve: object
    color_view: object = field(default=None)
    resolve_view: object = field(default=None)


class PlotRenderer:
    """Renders 2-D plot batches offscreen and returns RGBA pixels.

    One renderer per canvas; the GPU device underneath is shared.
    """

    def __init__(self):
        import wgpu

        self._wgpu = wgpu
        self.device = get_device()
        self.format = wgpu.TextureFormat.rgba8unorm
        module = self.device.create_shader_module(code=load_wgsl("plot2d.wgsl"))
        self._module = module

        blend = {
            "color": {
                "src_factor": wgpu.BlendFactor.src_alpha,
                "dst_factor": wgpu.BlendFactor.one_minus_src_alpha,
                "operation": wgpu.BlendOperation.add,
            },
            "alpha": {
                "src_factor": wgpu.BlendFactor.one,
                "dst_factor": wgpu.BlendFactor.one_minus_src_alpha,
                "operation": wgpu.BlendOperation.add,
            },
        }

        self._solid_pipeline = self.device.create_render_pipeline(
            layout=self.device.create_pipeline_layout(bind_group_layouts=[]),
            vertex={
                "module": module,
                "entry_point": "vs_solid",
                "buffers": [{
                    "array_stride": 6 * 4,
                    "step_mode": wgpu.VertexStepMode.vertex,
                    "attributes": [
                        {"format": wgpu.VertexFormat.float32x2, "offset": 0, "shader_location": 0},
                        {"format": wgpu.VertexFormat.float32x4, "offset": 8, "shader_location": 1},
                    ],
                }],
            },
            fragment={
                "module": module,
                "entry_point": "fs_solid",
                "targets": [{"format": self.format, "blend": blend}],
            },
            primitive={
                "topology": wgpu.PrimitiveTopology.triangle_list,
                "cull_mode": wgpu.CullMode.none,
            },
            multisample={"count": SAMPLE_COUNT},
        )

        self._image_bind_layout = self.device.create_bind_group_layout(entries=[
            {
                "binding": 0,
                "visibility": wgpu.ShaderStage.FRAGMENT,
                "texture": {"sample_type": wgpu.TextureSampleType.float},
            },
            {
                "binding": 1,
                "visibility": wgpu.ShaderStage.FRAGMENT,
                "sampler": {"type": wgpu.SamplerBindingType.filtering},
            },
        ])
        self._image_pipeline = self.device.create_render_pipeline(
            layout=self.device.create_pipeline_layout(
                bind_group_layouts=[self._image_bind_layout]),
            vertex={
                "module": module,
                "entry_point": "vs_image",
                "buffers": [{
                    "array_stride": 4 * 4,
                    "step_mode": wgpu.VertexStepMode.vertex,
                    "attributes": [
                        {"format": wgpu.VertexFormat.float32x2, "offset": 0, "shader_location": 0},
                        {"format": wgpu.VertexFormat.float32x2, "offset": 8, "shader_location": 1},
                    ],
                }],
            },
            fragment={
                "module": module,
                "entry_point": "fs_image",
                "targets": [{"format": self.format, "blend": blend}],
            },
            primitive={
                "topology": wgpu.PrimitiveTopology.triangle_list,
                "cull_mode": wgpu.CullMode.none,
            },
            multisample={"count": SAMPLE_COUNT},
        )
        self._sampler = self.device.create_sampler(
            mag_filter=wgpu.FilterMode.nearest,
            min_filter=wgpu.FilterMode.linear,
        )
        self._target: _Target | None = None
        self._textures: dict[int, tuple[int, object, object]] = {}

    # -- targets --------------------------------------------------------
    def _get_target(self, width: int, height: int) -> _Target:
        wgpu = self._wgpu
        t = self._target
        if t is not None and t.width == width and t.height == height:
            return t
        color = self.device.create_texture(
            size=(width, height, 1),
            format=self.format,
            sample_count=SAMPLE_COUNT,
            usage=wgpu.TextureUsage.RENDER_ATTACHMENT,
        )
        resolve = self.device.create_texture(
            size=(width, height, 1),
            format=self.format,
            usage=wgpu.TextureUsage.RENDER_ATTACHMENT | wgpu.TextureUsage.COPY_SRC,
        )
        t = _Target(width, height, color, resolve,
                    color.create_view(), resolve.create_view())
        self._target = t
        return t

    def _texture_for(self, batch: ImageBatch):
        """Upload (or reuse) the texture backing an image batch."""
        wgpu = self._wgpu
        key = id(batch.key) if batch.key is not None else id(batch)
        cached = self._textures.get(key)
        rgba = np.ascontiguousarray(batch.rgba, dtype=np.uint8)
        h, w = rgba.shape[:2]
        if cached is not None:
            version, tex, view = cached
            if version == batch.version and tex.size[0] == w and tex.size[1] == h:
                return view
        tex = self.device.create_texture(
            size=(w, h, 1),
            format=wgpu.TextureFormat.rgba8unorm,
            usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST,
        )
        self.device.queue.write_texture(
            {"texture": tex, "origin": (0, 0, 0)},
            rgba,
            {"bytes_per_row": w * 4, "rows_per_image": h},
            (w, h, 1),
        )
        view = tex.create_view()
        self._textures[key] = (batch.version, tex, view)
        return view

    def render(
        self,
        batches: list,
        width: int,
        height: int,
        background: tuple[float, float, float, float] = (0, 0, 0, 1),
    ) -> np.ndarray:
        """Render *batches* and return an ``(h, w, 4)`` uint8 RGBA array.

        Parameters
        ----------
        batches : list
            :class:`SolidBatch` / :class:`ImageBatch` instances, in draw order.
        width, height : int
            Framebuffer size in physical pixels.
        background : tuple of float
            Clear colour, RGBA in ``[0, 1]``.

        Returns
        -------
        numpy.ndarray
            ``(height, width, 4)`` uint8 RGBA, top row first.
        """
        wgpu = self._wgpu
        width = max(int(width), 1)
        height = max(int(height), 1)
        target = self._get_target(width, height)

        encoder = self.device.create_command_encoder()
        rp = encoder.begin_render_pass(color_attachments=[{
            "view": target.color_view,
            "resolve_target": target.resolve_view,
            "clear_value": tuple(float(c) for c in background),
            "load_op": wgpu.LoadOp.clear,
            "store_op": wgpu.StoreOp.store,
        }])

        keep = []  # GPU resources must outlive the pass
        for batch in batches:
            if isinstance(batch, SolidBatch):
                if not len(batch.verts):
                    continue
                data = np.empty((len(batch.verts), 6), dtype=np.float32)
                data[:, 0:2] = batch.verts
                data[:, 2:6] = batch.colors
                vbo = self.device.create_buffer_with_data(
                    data=np.ascontiguousarray(data), usage=wgpu.BufferUsage.VERTEX)
                keep.append(vbo)
                rp.set_pipeline(self._solid_pipeline)
                rp.set_vertex_buffer(0, vbo)
                rp.draw(len(batch.verts), 1, 0, 0)
            elif isinstance(batch, ImageBatch):
                if not len(batch.verts):
                    continue
                view = self._texture_for(batch)
                data = np.empty((len(batch.verts), 4), dtype=np.float32)
                data[:, 0:2] = batch.verts
                data[:, 2:4] = batch.uv
                vbo = self.device.create_buffer_with_data(
                    data=np.ascontiguousarray(data), usage=wgpu.BufferUsage.VERTEX)
                bind = self.device.create_bind_group(
                    layout=self._image_bind_layout,
                    entries=[
                        {"binding": 0, "resource": view},
                        {"binding": 1, "resource": self._sampler},
                    ],
                )
                keep += [vbo, bind]
                rp.set_pipeline(self._image_pipeline)
                rp.set_bind_group(0, bind)
                rp.set_vertex_buffer(0, vbo)
                rp.draw(len(batch.verts), 1, 0, 0)

        rp.end()
        self.device.queue.submit([encoder.finish()])

        raw = self.device.queue.read_texture(
            {"texture": target.resolve, "origin": (0, 0, 0)},
            {"bytes_per_row": width * 4, "rows_per_image": height},
            (width, height, 1),
        )
        return np.frombuffer(raw, np.uint8).reshape(height, width, 4).copy()
