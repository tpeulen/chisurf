"""Render a packed scene with WebGPU, from the shared WGSL source.

Why WebGPU
----------
The desktop viewer and a browser viewer have to draw the same picture, and
OpenGL cannot be the common ground: macOS caps it at 4.1 while compute shaders
need 4.3, and WebGL2 has no compute at all. WebGPU is the only API that spans
macOS, Linux/Windows and the browser, so the shader in ``wgsl/`` is compiled here
through wgpu-py and, later, by a browser through the same text.

What this module is
-------------------
The offscreen half: :class:`WgpuMeshRenderer` takes a
:class:`~.pack.PackedScene` and an 18-float PyMOL camera and returns pixels. It
needs no window, which is what makes it directly comparable against the captured
OpenGL baselines -- same commands, same camera, two renderers, two images a human
can put side by side.

Embedding it in the Qt dock is a separate step; the interesting risk is whether
the shading matches, not whether a widget hosts it.
"""
from __future__ import annotations

import pathlib
from collections import OrderedDict
from typing import Optional, Sequence

import numpy as np

from .depth_cue import fog_planes
from .lighting import LightRig, resolve_light_rig
from .pack import PackedScene
from .view_state import unpack_view_state

WGSL_DIR = pathlib.Path(__file__).with_name("wgsl")

#: Prepended to every entry-point shader. WGSL has no ``#include``, and the
#: alternative -- one copy of the shading model per pipeline -- is the drift this
#: whole arrangement exists to prevent: a mesh sphere and an impostor sphere have
#: to be indistinguishable where they overlap, which is only true if one function
#: shades both.
WGSL_PRELUDE = "shading.wgsl"


def load_wgsl(name: str) -> str:
    """Read a shader from the shared ``wgsl`` directory, with the prelude.

    Parameters
    ----------
    name : str
        Entry-point file name, e.g. ``"mesh.wgsl"``. Pass
        :data:`WGSL_PRELUDE` itself to read it alone.

    Returns
    -------
    str
        The prelude followed by the shader, unmodified. Both are shared with the
        browser backend, so nothing may be rewritten on the way through -- a
        per-backend edit here is exactly the drift this arrangement prevents.
        Concatenation is the composition rule, and it is the browser's too.
    """
    source = (WGSL_DIR / name).read_text()
    if name == WGSL_PRELUDE:
        return source
    return (WGSL_DIR / WGSL_PRELUDE).read_text() + "\n" + source


def perspective(fovy_deg: float, aspect: float, near: float, far: float) -> np.ndarray:
    """Perspective projection with WebGPU's 0..1 depth range.

    OpenGL maps depth to -1..1 and WebGPU to 0..1; using a GL matrix here puts
    half the scene behind the near plane, which reads as a clipped model rather
    than as a wrong matrix.
    """
    t = 1.0 / np.tan(np.radians(max(fovy_deg, 1e-3)) * 0.5)
    m = np.zeros((4, 4), dtype=np.float32)
    m[0, 0] = t / max(aspect, 1e-6)
    m[1, 1] = t
    m[2, 2] = far / (near - far)
    m[2, 3] = near * far / (near - far)
    m[3, 2] = -1.0
    return m


def view_matrix(
    rotation: np.ndarray,
    target: np.ndarray,
    distance: float,
    shift: Optional[Sequence[float]] = None,
) -> np.ndarray:
    """Build the view matrix from PyMOL's rotation, target, distance and shift.

    The camera-space offset is applied **after** the rotation, which slides the
    image without moving the pivot. That separation is the whole of ``origin``:
    it is what lets the molecule rotate about a chosen atom while that atom sits
    off-centre. Dropping it -- which this did until the widget needed picking --
    silently re-centres every view that used ``origin``, and the give-away is
    that a click lands where the molecule *would* be without it.
    """
    r = np.eye(4, dtype=np.float32)
    r[:3, :3] = np.asarray(rotation, dtype=np.float32).reshape(3, 3)
    t = np.eye(4, dtype=np.float32)
    t[:3, 3] = -np.asarray(target, dtype=np.float32).reshape(3)
    back = np.eye(4, dtype=np.float32)
    offset = np.zeros(3) if shift is None else np.asarray(shift, dtype=float).reshape(3)
    back[0, 3] = float(offset[0])
    back[1, 3] = float(offset[1])
    back[2, 3] = float(offset[2]) - float(distance)
    return back @ r @ t



#: Above this many bytes an overlay is compared by a sampled signature rather
#: than by its whole content. Hashing 12.9 MB per frame would cost more than the
#: upload it saves.
_OVERLAY_HASH_LIMIT = 1 << 20

#: How much interleaved vertex data to keep. A quarter-million beads is 8.4 MB,
#: so this holds a large scene and its predecessor without holding every scene
#: anyone has looked at.
_VERTEX_CACHE_BYTES = 256 << 20


def _fast_signature(data: np.ndarray) -> tuple:
    """A cheap stand-in for the content of a large image.

    Parameters
    ----------
    data : numpy.ndarray
        Contiguous uint8 image.

    Returns
    -------
    tuple
        Shape, total, and a strided sample. Enough to notice a repainted panel
        and cheap enough to compute every frame.

    Notes
    -----
    Sampling, not hashing: a full hash of a retina-sized overlay costs more than
    the upload it is meant to avoid. The failure mode is a chrome change this
    misses, which would show as a stale panel for as long as the change lasts --
    so the caller *also* repaints on a timer, and the two together bound the
    staleness without either having to be exact.
    """
    flat = data.reshape(-1)
    return (data.shape, int(flat[::4099].sum()), bytes(flat[::65536][:512]))


class WgpuMeshRenderer:
    """Draw the mesh objects of a packed scene, offscreen.

    Parameters
    ----------
    width, height : int
        Framebuffer size in pixels.
    """

    def __init__(
        self,
        width: int = 1280,
        height: int = 860,
        *,
        format: Optional[str] = None,
        device=None,
    ) -> None:
        import wgpu

        self._wgpu = wgpu
        self.width, self.height = int(width), int(height)
        if device is None:
            adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
            self.device = adapter.request_device_sync()
            self.adapter_info = dict(adapter.info)
        else:
            # A canvas configures its context against a device it already has,
            # and a texture from one device cannot be drawn into by another.
            self.device = device
            self.adapter_info = dict(getattr(device.adapter, "info", {}) or {})

        # Non-sRGB by default, on purpose. The swap-chain's preferred format is
        # `rgba8unorm-srgb`, which gamma-encodes on write; the OpenGL backend
        # draws to a plain framebuffer and does not. Rendering into an sRGB
        # target here would wash every colour out relative to the baseline -- a
        # clear value of 0.09 comes back as 85 instead of 23 -- and the whole
        # point of the offscreen renderer is to be comparable to that baseline.
        # A window passes whatever format its surface was configured with, and
        # the pipelines are built for it.
        self.format = format or wgpu.TextureFormat.rgba8unorm
        #: Interleaved vertex data, per geometry. A rotating camera redraws the
        #: same geometry sixty times a second, and rebuilding the interleaved
        #: array and re-uploading it was 9 ms of a 21 ms frame on a
        #: quarter-million beads. Keyed on the arrays' identity *and* their
        #: buffer addresses, and holding a reference to the geometry so its
        #: `id` cannot be recycled under the entry.
        self._vertex_cache: "OrderedDict[tuple, tuple]" = OrderedDict()
        self._overlay_cache = None
        #: Uniform buffers and bind groups, by draw position. Rewritten each
        #: frame rather than reallocated; see :meth:`_uniform_slot`.
        self._uniform_pool: list = []

        self._bind_layout = self.device.create_bind_group_layout(
            entries=[
                {
                    "binding": 0,
                    "visibility": wgpu.ShaderStage.VERTEX | wgpu.ShaderStage.FRAGMENT,
                    "buffer": {"type": wgpu.BufferBindingType.uniform},
                }
            ]
        )
        layout = self.device.create_pipeline_layout(
            bind_group_layouts=[self._bind_layout]
        )

        # One pipeline per (geometry kind, depth-write). Opaque geometry writes
        # depth; transparent geometry does not, or the near face of a
        # translucent shell occludes the far face of the same shell and the
        # surface reads solid.
        self._pipelines: dict[tuple[str, bool], object] = {}
        for kind, spec in self._PIPELINES.items():
            module = self.device.create_shader_module(code=load_wgsl(spec["shader"]))
            for depth_write in (True, False):
                self._pipelines[(kind, depth_write)] = self._make_pipeline(
                    module, layout, spec, depth_write
                )
        self._overlay_pipeline = None
        self._overlay_layout = None
        self._silhouette_pipeline = None

    #: Size of the shared uniform block, in floats: four 4x4 matrices and six
    #: vec4s. Named because the chrome pass has to bind a block it never reads,
    #: and a short buffer there is a validation error rather than a blank frame.
    UNIFORM_FLOATS = 4 * 16 + 6 * 4

    #: Vertex layout and topology per geometry kind. ``attributes`` are
    #: ``(format, float count)`` in order; the stride follows from them, so a
    #: layout change cannot leave a stale byte offset behind.
    _PIPELINES: dict[str, dict] = {
        # position(3) normal(3) colour(4) occlusion(1)
        "mesh": {
            "shader": "mesh.wgsl",
            "attributes": [("float32x3", 3), ("float32x3", 3), ("float32x4", 4), ("float32", 1)],
            "topology": "triangle-list",
            "step_mode": "vertex",
        },
        # sphere(4: xyz centre + radius) colour(4) occlusion(1), one per instance
        "impostor": {
            "shader": "impostor.wgsl",
            "attributes": [("float32x4", 4), ("float32x4", 4), ("float32", 1)],
            "topology": "triangle-list",
            "step_mode": "instance",
        },
        # position(3) colour(4)
        "line": {
            "shader": "line.wgsl",
            "attributes": [("float32x3", 3), ("float32x4", 4)],
            "topology": "line-list",
            "step_mode": "vertex",
        },
    }

    def _make_pipeline(self, module, layout, spec: dict, depth_write: bool):
        """Build one render pipeline from a :data:`_PIPELINES` entry."""
        wgpu = self._wgpu
        attributes, offset = [], 0
        for location, (fmt, count) in enumerate(spec["attributes"]):
            attributes.append(
                {"format": fmt, "offset": offset, "shader_location": location}
            )
            offset += count * 4
        return self.device.create_render_pipeline(
            layout=layout,
            vertex={
                "module": module,
                "entry_point": "vs_main",
                "buffers": [
                    {
                        "array_stride": offset,
                        "step_mode": spec["step_mode"],
                        "attributes": attributes,
                    }
                ],
            },
            depth_stencil={
                "format": wgpu.TextureFormat.depth24plus,
                "depth_write_enabled": depth_write,
                "depth_compare": wgpu.CompareFunction.less,
            },
            fragment={
                "module": module,
                "entry_point": "fs_main",
                "targets": [
                    {
                        "format": self.format,
                        # Straight alpha over the destination. Without this a
                        # surface at `transparency 0.5` draws solid, and the
                        # setting looks unimplemented rather than unblended.
                        "blend": {
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
                        },
                    }
                ],
            },
            primitive={
                "topology": spec["topology"],
                # Both faces: a cartoon ribbon is a two-sided sheet, and culling
                # it would delete the inside of every helix.
                "cull_mode": wgpu.CullMode.none,
            },
        )

    # -- interleaving --------------------------------------------------------

    @staticmethod
    def _rgba(geometry) -> np.ndarray:
        """Colours as ``(n, 4)`` float32, opaque where the builder gave RGB."""
        n = geometry.vertex_count
        out = np.ones((n, 4), dtype=np.float32)
        if geometry.colors is not None:
            cols = geometry.colors
            out[:, : min(4, cols.shape[1])] = cols[:, :4]
        return out

    @classmethod
    def interleave(cls, geometry) -> np.ndarray:
        """Pack one mesh geometry into the mesh vertex layout.

        Missing attributes are filled rather than branched on in the shader: a
        mesh with no occlusion is a mesh with zero occlusion, and a second
        pipeline for that case would be a second thing to keep at parity.
        """
        n = geometry.vertex_count
        out = np.zeros((n, 11), dtype=np.float32)
        out[:, 0:3] = geometry.positions
        if geometry.normals is not None:
            out[:, 3:6] = geometry.normals
        else:
            out[:, 5] = 1.0
        out[:, 6:10] = cls._rgba(geometry)
        if geometry.occlusion is not None:
            out[:, 10] = geometry.occlusion[:, 0]
        return np.ascontiguousarray(out)

    @classmethod
    def interleave_impostors(cls, geometry) -> np.ndarray:
        """Pack point geometry into the per-instance impostor layout.

        A radius comes from one of two places, and they mean different things.
        ``radii`` is a distance in the model -- a bead's own size, which grows as
        the camera approaches. ``meta["size"]`` is the OpenGL backend's
        ``gl_PointSize``, a **diameter in pixels**, which is why it is halved
        here: the shader intersects a sphere and a sphere is described by its
        radius, so converting at the boundary keeps one convention inside.

        Parameters
        ----------
        geometry : PackedGeometry
            ``kind == "points"``.

        Returns
        -------
        numpy.ndarray
            ``(n, 9)`` float32: centre xyz, radius, RGBA, occlusion.
        """
        n = geometry.vertex_count
        out = np.zeros((n, 9), dtype=np.float32)
        out[:, 0:3] = geometry.positions
        if geometry.radii is not None:
            out[:, 3] = geometry.radii[:, 0]
        else:
            size = float(geometry.meta.get("size", 2.0 * cls.DEFAULT_POINT_RADIUS))
            out[:, 3] = 0.5 * size
        out[:, 4:8] = cls._rgba(geometry)
        if geometry.occlusion is not None:
            out[:, 8] = geometry.occlusion[:, 0]
        return np.ascontiguousarray(out)

    @classmethod
    def interleave_lines(cls, geometry) -> np.ndarray:
        """Pack line geometry into the line vertex layout: position, RGBA."""
        n = geometry.vertex_count
        out = np.zeros((n, 7), dtype=np.float32)
        out[:, 0:3] = geometry.positions
        out[:, 3:7] = cls._rgba(geometry)
        return np.ascontiguousarray(out)

    def _uniforms(self, mvp, view, proj, normal_matrix, fog_end, fog_scale,
                  fog_color, two_sided, opacity, point_scale, world_radius,
                  rig: LightRig) -> bytes:
        def m(a):
            # WGSL matrices are column-major; numpy is row-major.
            return np.ascontiguousarray(np.asarray(a, np.float32).T).tobytes()

        b = bytearray()
        b += m(mvp) + m(view) + m(proj) + m(normal_matrix)
        b += np.array([*rig.light_dir, 0.0], np.float32).tobytes()
        b += np.array([*rig.fill_dir, 0.0], np.float32).tobytes()
        b += np.array([*fog_color, float(fog_end)], np.float32).tobytes()
        b += np.array([rig.key, rig.fill, rig.ambient, rig.specular], np.float32).tobytes()
        b += np.array(
            [rig.shininess, rig.rim_strength, rig.rim_power, float(fog_scale)],
            np.float32,
        ).tobytes()
        b += np.array(
            [
                1.0 if two_sided else 0.0,
                float(opacity),
                float(point_scale),
                1.0 if world_radius else 0.0,
            ],
            np.float32,
        ).tobytes()
        return bytes(b)

    def _build_overlay_pipeline(self):
        """Build the screen-space chrome pipeline, once, on first use.

        Lazily, because a headless comparison never draws chrome and the
        texture bind-group layout is the only thing in this class that a
        molecule-only render does not need.
        """
        wgpu = self._wgpu
        if self._overlay_pipeline is not None:
            return self._overlay_pipeline

        self._overlay_layout = self.device.create_bind_group_layout(
            entries=[
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
            ]
        )
        module = self.device.create_shader_module(code=load_wgsl("overlay.wgsl"))
        self._overlay_pipeline = self.device.create_render_pipeline(
            layout=self.device.create_pipeline_layout(
                # Group 0 is the shared uniform block. The chrome does not read
                # it, but the layouts must line up with the shared prelude's
                # `@group(0) @binding(0)` declaration, which every shader gets.
                bind_group_layouts=[self._bind_layout, self._overlay_layout]
            ),
            vertex={"module": module, "entry_point": "vs_overlay", "buffers": []},
            # No depth attachment: this runs in the second pass, which samples
            # the depth buffer the first one wrote and therefore cannot have it
            # attached.
            fragment={
                "module": module,
                "entry_point": "fs_overlay",
                "targets": [
                    {
                        "format": self.format,
                        # Premultiplied: Qt paints into a premultiplied buffer,
                        # and `src_alpha` on top of that would darken every
                        # antialiased glyph edge twice.
                        "blend": {
                            "color": {
                                "src_factor": wgpu.BlendFactor.one,
                                "dst_factor": wgpu.BlendFactor.one_minus_src_alpha,
                                "operation": wgpu.BlendOperation.add,
                            },
                            "alpha": {
                                "src_factor": wgpu.BlendFactor.one,
                                "dst_factor": wgpu.BlendFactor.one_minus_src_alpha,
                                "operation": wgpu.BlendOperation.add,
                            },
                        },
                    }
                ],
            },
            primitive={"topology": wgpu.PrimitiveTopology.triangle_list},
        )
        self._overlay_sampler = self.device.create_sampler(
            mag_filter=wgpu.FilterMode.nearest, min_filter=wgpu.FilterMode.nearest
        )
        return self._overlay_pipeline

    def _build_silhouette_pipeline(self):
        """Build the depth-outline pipeline, once, on first use."""
        wgpu = self._wgpu
        if self._silhouette_pipeline is not None:
            return self._silhouette_pipeline

        self._silhouette_uniform_layout = self.device.create_bind_group_layout(
            entries=[
                {
                    "binding": 0,
                    "visibility": wgpu.ShaderStage.FRAGMENT,
                    "buffer": {"type": wgpu.BufferBindingType.uniform},
                }
            ]
        )
        self._silhouette_depth_layout = self.device.create_bind_group_layout(
            entries=[
                {
                    "binding": 0,
                    "visibility": wgpu.ShaderStage.FRAGMENT,
                    # A depth texture, not a colour one: sampling it as `float`
                    # is a validation error, and the message names the binding
                    # rather than the format.
                    "texture": {"sample_type": wgpu.TextureSampleType.depth},
                },
                {
                    "binding": 1,
                    "visibility": wgpu.ShaderStage.FRAGMENT,
                    "sampler": {"type": wgpu.SamplerBindingType.non_filtering},
                },
            ]
        )
        module = self.device.create_shader_module(code=load_wgsl("silhouette.wgsl"))
        self._silhouette_pipeline = self.device.create_render_pipeline(
            layout=self.device.create_pipeline_layout(
                bind_group_layouts=[
                    self._silhouette_uniform_layout,
                    self._silhouette_depth_layout,
                ]
            ),
            vertex={"module": module, "entry_point": "vs_outline", "buffers": []},
            fragment={
                "module": module,
                "entry_point": "fs_outline",
                "targets": [
                    {
                        "format": self.format,
                        "blend": {
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
                        },
                    }
                ],
            },
            primitive={"topology": wgpu.PrimitiveTopology.triangle_list},
        )
        self._silhouette_sampler = self.device.create_sampler(
            mag_filter=wgpu.FilterMode.nearest, min_filter=wgpu.FilterMode.nearest
        )
        return self._silhouette_pipeline

    @staticmethod
    def _silhouette_params(state, config: Optional[dict]) -> Optional[dict]:
        """Resolve the outline settings, or ``None`` when it is switched off.

        ``None`` reads the live ``silhouette`` display-config section, which is
        the same store ``set silhouette, on`` writes and the OpenGL post-pass
        reads -- one store, read where it is used, is what makes the setting
        mean something rather than being accepted and inert.
        """
        if config is None:
            from ..config import _DISPLAY_CONFIG

            section = _DISPLAY_CONFIG.get("silhouette")
            config = section if isinstance(section, dict) else {}
        if not bool(config.get("enabled", False)):
            return None
        near, far = max(float(state.near), 1e-6), max(float(state.far), 1e-5)
        return {
            "depth_jump": float(config.get("depth_jump", 0.03)),
            # The near/far ratio is what linearises the depth comparison, so
            # `depth_jump` stays a fraction of the scene at every distance.
            "near_far": near / far,
            "thickness": float(config.get("thickness", 1.0)),
            "color": tuple(
                float(c) for c in config.get("color", [0.0, 0.0, 0.0, 1.0])
            ),
        }

    def _draw_silhouette(self, render_pass, depth_texture, params: dict) -> list:
        """Draw the depth outline; returns the resources to keep alive."""
        wgpu = self._wgpu
        pipeline = self._build_silhouette_pipeline()
        data = np.array(
            [
                params["depth_jump"], params["near_far"], params["thickness"], 0.0,
                *params["color"],
                1.0 / max(self.width, 1), 1.0 / max(self.height, 1), 0.0, 0.0,
            ],
            dtype=np.float32,
        )
        ubo = self.device.create_buffer_with_data(
            data=data, usage=wgpu.BufferUsage.UNIFORM
        )
        uniforms = self.device.create_bind_group(
            layout=self._silhouette_uniform_layout,
            entries=[
                {"binding": 0, "resource": {"buffer": ubo, "offset": 0, "size": ubo.size}}
            ],
        )
        depth = self.device.create_bind_group(
            layout=self._silhouette_depth_layout,
            entries=[
                {"binding": 0, "resource": depth_texture.create_view()},
                {"binding": 1, "resource": self._silhouette_sampler},
            ],
        )
        render_pass.set_pipeline(pipeline)
        render_pass.set_bind_group(0, uniforms)
        render_pass.set_bind_group(1, depth)
        render_pass.draw(6, 1, 0, 0)
        return [ubo, uniforms, depth]

    def _draw_overlay(self, render_pass, overlay: np.ndarray) -> list:
        """Composite the chrome image; returns the resources to keep alive."""
        wgpu = self._wgpu
        pipeline = self._build_overlay_pipeline()
        texture = self.upload_overlay(overlay)
        bind = self.device.create_bind_group(
            layout=self._overlay_layout,
            entries=[
                {"binding": 0, "resource": texture.create_view()},
                {"binding": 1, "resource": self._overlay_sampler},
            ],
        )
        # The chrome ignores the uniform block, but group 0 is declared by the
        # shared prelude every shader carries, so it must still be bound.
        ubo = self.device.create_buffer_with_data(
            data=np.zeros(self.UNIFORM_FLOATS, dtype=np.float32),
            usage=wgpu.BufferUsage.UNIFORM,
        )
        group0 = self.device.create_bind_group(
            layout=self._bind_layout,
            entries=[
                {"binding": 0, "resource": {"buffer": ubo, "offset": 0, "size": ubo.size}}
            ],
        )
        render_pass.set_pipeline(pipeline)
        render_pass.set_bind_group(0, group0)
        render_pass.set_bind_group(1, bind)
        render_pass.draw(6, 1, 0, 0)
        return [texture, bind, ubo, group0]

    @staticmethod
    def _geometry_signature(geom, kind: str) -> tuple:
        """What must be unchanged for a cached vertex buffer to still be right.

        Parameters
        ----------
        geom : PackedGeometry
            The geometry about to be drawn.
        kind : str
            Which interleave it takes.

        Returns
        -------
        tuple

        Notes
        -----
        Array *addresses*, not contents. The scene builder produces new arrays
        whenever anything changes -- numpy operations do not write in place --
        so an address is a sound identity and hashing tens of megabytes per
        frame would cost more than the work it saves. In-place mutation of an
        array a geometry already holds would defeat it; nothing in the builder
        does that, and `clear_caches` is there for anything that starts to.
        """
        def address(array):
            return None if array is None else (array.ctypes.data, array.shape)

        return (
            id(geom), kind,
            address(geom.positions), address(geom.colors), address(geom.radii),
            address(geom.normals), address(geom.indices),
            geom.meta.get("size"), bool(geom.meta.get("world_radius", False)),
        )

    def _uniform_slot(self, index: int, values: np.ndarray):
        """A uniform buffer and its bind group for the ``index``-th draw.

        Parameters
        ----------
        index : int
            Position in this frame's draw order.
        values : bytes or numpy.ndarray
            The uniform block's contents.

        Returns
        -------
        tuple
            ``(buffer, bind_group)``, both reused across frames.

        Notes
        -----
        Rotating a molecule changes one matrix. Everything else the frame needs
        -- the vertices, the colours, the overlay -- is already on the device and
        unchanged, so the only honest per-frame work is writing that matrix and
        encoding the pass. Creating a fresh uniform buffer and a fresh bind group
        for every object of every frame is neither: it is an allocation and a
        descriptor build sixty times a second to carry two hundred bytes that
        could have been written in place.

        Pooled by draw position rather than by object, because the contents are
        rewritten wholesale anyway and a pool indexed by position needs no
        invalidation at all -- the worst a stale slot can do is be overwritten.
        """
        wgpu = self._wgpu
        payload = memoryview(values).cast("B") if isinstance(values, (bytes, bytearray)) else values
        size_needed = len(values) if isinstance(values, (bytes, bytearray)) else int(values.nbytes)
        while len(self._uniform_pool) <= index:
            buffer = self.device.create_buffer(
                size=size_needed,
                usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
            )
            group = self.device.create_bind_group(
                layout=self._bind_layout,
                entries=[{
                    "binding": 0,
                    "resource": {"buffer": buffer, "offset": 0, "size": buffer.size},
                }],
            )
            self._uniform_pool.append((buffer, group, size_needed))

        buffer, group, size = self._uniform_pool[index]
        if size != size_needed:
            # The block only changes size if the shader's layout does, which is
            # a code change, not a frame-to-frame event.
            self._uniform_pool[index] = (buffer, group, size) = (
                *self._uniform_slot_rebuild(size_needed), size_needed
            )
        self.device.queue.write_buffer(buffer, 0, payload)
        return buffer, group

    def _uniform_slot_rebuild(self, size_needed: int):
        """Allocate a replacement uniform buffer and bind group."""
        wgpu = self._wgpu
        buffer = self.device.create_buffer(
            size=int(size_needed),
            usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
        )
        group = self.device.create_bind_group(
            layout=self._bind_layout,
            entries=[{
                "binding": 0,
                "resource": {"buffer": buffer, "offset": 0, "size": buffer.size},
            }],
        )
        return buffer, group

    def _vertex_buffer(self, geom, kind: str):
        """The interleaved vertex buffer for a geometry, built once.

        Parameters
        ----------
        geom : PackedGeometry
            Geometry to draw.
        kind : str
            ``"impostor"``, ``"line"`` or ``"mesh"``.

        Returns
        -------
        wgpu.GPUBuffer
        """
        wgpu = self._wgpu
        key = self._geometry_signature(geom, kind)
        hit = self._vertex_cache.get(key)
        if hit is not None:
            self._vertex_cache.move_to_end(key)
            return hit[1]

        if kind == "impostor":
            data = self.interleave_impostors(geom)
        elif kind == "line":
            data = self.interleave_lines(geom)
        else:
            data = self.interleave(geom)
        buffer = self.device.create_buffer_with_data(
            data=data, usage=wgpu.BufferUsage.VERTEX
        )
        self._vertex_cache[key] = (geom, buffer, data.nbytes)
        held = sum(entry[2] for entry in self._vertex_cache.values())
        while len(self._vertex_cache) > 1 and held > _VERTEX_CACHE_BYTES:
            _, evicted = self._vertex_cache.popitem(last=False)
            held -= evicted[2]
        return buffer

    def clear_caches(self) -> None:
        """Drop every cached buffer and texture.

        For a caller that mutates geometry arrays in place, and for tests that
        want the next frame to be built from scratch.
        """
        self._vertex_cache.clear()
        self._overlay_cache = None
        self._uniform_pool.clear()

    def upload_overlay(self, image: np.ndarray):
        """Upload a premultiplied RGBA chrome image and return its texture.

        Parameters
        ----------
        image : numpy.ndarray
            ``(h, w, 4)`` uint8, **premultiplied**, the size of the target.

        Returns
        -------
        wgpu.GPUTexture
        """
        wgpu = self._wgpu
        data = np.ascontiguousarray(image, dtype=np.uint8)
        height, width = data.shape[:2]
        # The chrome is 12.9 MB at a retina viewport and is usually the *same*
        # 12.9 MB as last frame -- the panel cannot change while the camera is
        # being dragged. Re-uploading it was 4.2 ms of a 21 ms frame.
        signature = (width, height, data.tobytes() if data.nbytes <= _OVERLAY_HASH_LIMIT
                     else _fast_signature(data))
        if self._overlay_cache is not None and self._overlay_cache[0] == signature:
            return self._overlay_cache[1]
        texture = self.device.create_texture(
            size=(width, height, 1),
            format=wgpu.TextureFormat.rgba8unorm,
            usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST,
        )
        self.device.queue.write_texture(
            {"texture": texture, "origin": (0, 0, 0)},
            data,
            {"bytes_per_row": width * 4, "rows_per_image": height},
            (width, height, 1),
        )
        self._overlay_cache = (signature, texture)
        return texture

    def resize(self, width: int, height: int) -> None:
        """Change the framebuffer size the projection and point scale assume.

        The pipelines do not depend on it, so nothing is rebuilt; only the
        aspect ratio and the pixels-per-world-unit conversion change.
        """
        self.width, self.height = max(int(width), 1), max(int(height), 1)

    #: Radius, in pixels, for point geometry the builder gave no ``radii`` -- the
    #: `dots` representation and the selection glyphs. Matches the OpenGL
    #: backend's ``pointSize`` default.
    DEFAULT_POINT_RADIUS = 3.0

    @staticmethod
    def pipeline_for(geometry) -> Optional[str]:
        """Which pipeline draws ``geometry``, or ``None`` if nothing does yet.

        Routing by ``kind`` rather than by object id, so a new builder that emits
        points gets impostors without touching this backend.

        Returns
        -------
        str or None
            ``"mesh"``, ``"impostor"``, ``"line"``, or ``None`` for geometry this
            renderer cannot draw. ``kind == "text"`` is the live gap -- labels are
            skipped entirely, which is a missing feature rather than a decision.
        """
        kind = geometry.kind
        if kind == "mesh":
            has_indices = geometry.indices is not None and geometry.indices.size
            return "mesh" if has_indices else None
        if kind == "points":
            return "impostor" if geometry.vertex_count else None
        if kind == "line":
            # A line list needs pairs; an odd count would drop its last vertex
            # into a line with no end, which wgpu reports as nothing drawn.
            return "line" if geometry.vertex_count >= 2 else None
        return None

    def point_scale(self, fov: float, height: Optional[float] = None) -> float:
        """Pixels per unit of world radius at unit depth.

        Half the viewport height over ``tan(fov / 2)``, which is the OpenGL
        backend's ``pointScale``: a sphere impostor's radius is a distance in the
        model, so it has to grow as the camera approaches the way a mesh sphere
        does. Kept as a method because the impostor shader needs the same number
        the GL point-sprite path uses, and a second derivation of it is a second
        thing that can disagree.

        Parameters
        ----------
        fov : float
            Vertical field of view in degrees.
        height : float, optional
            Viewport height in pixels; defaults to the whole surface.
        """
        half = np.radians(max(float(fov), 1e-3)) * 0.5
        h = self.height if height is None else float(height)
        return 0.5 * h / max(np.tan(half), 1e-6)

    def render(
        self,
        scene: PackedScene,
        view_state: Sequence[float],
        *,
        background: Sequence[float] = (0.0, 0.0, 0.0),
        two_sided: bool = False,
        lighting: Optional[LightRig] = None,
        depth_cue: Optional[dict] = None,
        target_radius: Optional[float] = None,
        viewport: Optional[Sequence[float]] = None,
        overlay: Optional[np.ndarray] = None,
        silhouette: Optional[dict] = None,
    ) -> np.ndarray:
        """Render ``scene`` from ``view_state`` and return an ``(h, w, 3)`` uint8 image.

        Parameters
        ----------
        scene : PackedScene
            Already in upload layout; see :mod:`.pack`.
        view_state : sequence of float
            The 18-float PyMOL camera, so this frames identically to the OpenGL
            backend and to the ray tracer.
        background : sequence of float
            Clear colour, linear RGB in ``[0, 1]``.
        two_sided : bool
            Force PyMOL's ``two_sided_lighting`` on for every object. Geometry
            that asks for it in its own ``meta`` gets it regardless -- that is
            how the setting reaches the OpenGL backend, and how a scene that
            sets it ends up looking different from one that does not.
        lighting : LightRig, optional
            The light rig. ``None`` resolves it from the display config, the
            same section the OpenGL backend reads.
        depth_cue : dict, optional
            The ``depth_cue`` display-config section. ``None`` reads the live
            config, which is what makes this match the OpenGL backend by
            default; pass ``{"enabled": False}`` to render without the cue.
        target_radius : float, optional
            Radius the camera is framed on, which is the span the cue is
            measured over. Defaults to the scene's own radius.

        Returns
        -------
        numpy.ndarray
            ``(height, width, 3)`` uint8.
        """
        wgpu = self._wgpu
        colour_tex = self.device.create_texture(
            size=(self.width, self.height, 1),
            format=self.format,
            usage=wgpu.TextureUsage.RENDER_ATTACHMENT | wgpu.TextureUsage.COPY_SRC,
        )
        self.render_into(
            colour_tex.create_view(),
            scene,
            view_state,
            background=background,
            two_sided=two_sided,
            lighting=lighting,
            depth_cue=depth_cue,
            target_radius=target_radius,
            viewport=viewport,
            overlay=overlay,
            silhouette=silhouette,
        )
        raw = self.device.queue.read_texture(
            {"texture": colour_tex, "origin": (0, 0, 0)},
            {"bytes_per_row": self.width * 4, "rows_per_image": self.height},
            (self.width, self.height, 1),
        )
        img = np.frombuffer(raw, np.uint8).reshape(self.height, self.width, 4)
        return np.ascontiguousarray(img[..., :3])

    def render_into(
        self,
        target_view,
        scene: PackedScene,
        view_state: Sequence[float],
        *,
        background: Sequence[float] = (0.0, 0.0, 0.0),
        two_sided: bool = False,
        lighting: Optional[LightRig] = None,
        depth_cue: Optional[dict] = None,
        target_radius: Optional[float] = None,
        viewport: Optional[Sequence[float]] = None,
        overlay: Optional[np.ndarray] = None,
        silhouette: Optional[dict] = None,
    ) -> None:
        """Draw ``scene`` into an existing texture view.

        This is the half a window needs. :meth:`render` allocates its own target
        and reads it back; a canvas hands over the texture the compositor is
        about to present, and everything between the two is identical -- which is
        the point, because it means the windowed viewer and the offscreen
        comparison cannot drift into drawing different pictures.

        Parameters
        ----------
        target_view : wgpu.GPUTextureView
            Colour attachment, in :attr:`format`, sized :attr:`width` x
            :attr:`height`.
        viewport : sequence of float, optional
            ``(x, y, width, height)`` in target pixels, for a window that gives
            part of its surface to chrome -- the object panel is a column down
            the right and the sequence strip a band across the top, and the
            molecule belongs *beside* them, not under them. The clear still
            covers the whole attachment, so the reserved area is background
            rather than stale pixels. Defaults to the full target.
        overlay : numpy.ndarray, optional
            ``(height, width, 4)`` uint8 **premultiplied** RGBA, composited over
            the whole target after the scene: the object panel, the sequence
            strip, and eventually labels.

        See Also
        --------
        render : the offscreen convenience wrapper, which returns pixels.
        """
        wgpu = self._wgpu
        light = lighting if lighting is not None else resolve_light_rig()
        state = unpack_view_state(view_state)

        vx, vy, vw, vh = (
            (0.0, 0.0, float(self.width), float(self.height))
            if viewport is None
            else tuple(float(v) for v in viewport)
        )
        vw, vh = max(vw, 1.0), max(vh, 1.0)

        view = view_matrix(state.rotation, state.target, state.distance, state.shift)
        # The aspect is the *scene column's*, not the surface's: projecting with
        # the full width and then drawing into a narrower viewport stretches the
        # same picture into less room, which is the squashed molecule a panel
        # produces the first time one is added.
        proj = perspective(state.fov, vw / vh, max(state.near, 1e-3), state.far)
        mvp = proj @ view
        # Normals need the inverse transpose; the view here is a rigid motion, so
        # its rotation block is orthonormal and the inverse transpose is itself.
        normal_matrix = view.copy()
        normal_matrix[:3, 3] = 0.0

        # The same planes the GL backend uses, from the same rule, fitted around
        # the scene rather than taken from the clipping planes. Leaving the cue
        # out is not a neutral simplification: it fogs towards the *background*,
        # so a missing cue is invisible against black and reads as a much darker
        # model against white -- which is exactly how it was first reported.
        radius = scene.radius if target_radius is None else float(target_radius)
        fog_end, fog_scale = fog_planes(state.distance, radius, depth_cue)

        # Sampleable, because the silhouette pass reads it. A depth attachment
        # cannot be sampled while it is attached, so the outline is a *second*
        # pass -- which is also why the chrome is composited there and not here.
        depth_tex = self.device.create_texture(
            size=(self.width, self.height, 1),
            format=wgpu.TextureFormat.depth24plus,
            usage=(
                wgpu.TextureUsage.RENDER_ATTACHMENT | wgpu.TextureUsage.TEXTURE_BINDING
            ),
        )

        encoder = self.device.create_command_encoder()
        rp = encoder.begin_render_pass(
            color_attachments=[
                {
                    "view": target_view,
                    "clear_value": (*background, 1.0),
                    "load_op": wgpu.LoadOp.clear,
                    "store_op": wgpu.StoreOp.store,
                }
            ],
            depth_stencil_attachment={
                "view": depth_tex.create_view(),
                "depth_clear_value": 1.0,
                "depth_load_op": wgpu.LoadOp.clear,
                "depth_store_op": wgpu.StoreOp.store,
            },
        )
        rp.set_viewport(vx, vy, vw, vh, 0.0, 1.0)
        keep = []  # buffers must outlive the pass

        def _opacity(obj) -> float:
            return 1.0 if obj.material is None else float(obj.material.opacity)

        # From the viewport's height, not the surface's: a pixel size is a
        # fraction of what is actually drawn into.
        point_scale = self.point_scale(state.fov, height=vh)

        # Opaque first, then transparent. Blending is order-dependent: drawing a
        # translucent surface before the geometry behind it composites it against
        # the background instead of against what it should veil.
        drawable = [(o, k) for o in scene.objects if (k := self.pipeline_for(o.geometry))]
        ordered = sorted(
            drawable,
            key=lambda pair: (_opacity(pair[0]) < 1.0 or pair[0].render_mode == "transparent"),
        )

        current = None
        slot_index = 0
        for obj, kind in ordered:
            geom = obj.geometry
            opacity = _opacity(obj)
            blended = opacity < 1.0 or obj.render_mode == "transparent"
            pipeline = self._pipelines[(kind, not blended)]
            if pipeline is not current:
                rp.set_pipeline(pipeline)
                current = pipeline

            vbo = self._vertex_buffer(geom, kind)
            ubo, bind = self._uniform_slot(
                slot_index,
                self._uniforms(
                    mvp, view, proj, normal_matrix, fog_end, fog_scale,
                    background,
                    # Per object, as in GL: `two_sided_lighting` reaches the
                    # renderer as geometry metadata, because it is the flat
                    # nucleic base plates and the translucent shells that need
                    # it and not the whole frame. Taking it as one flag for the
                    # scene made the `two_sided_on` baseline compare identical
                    # to the one without it -- a row that could only ever pass.
                    two_sided or bool(geom.meta.get("two_sided", False)),
                    opacity, point_scale,
                    bool(geom.meta.get("world_radius", False)), light,
                ),
            )
            slot_index += 1
            rp.set_bind_group(0, bind)
            rp.set_vertex_buffer(0, vbo)

            if kind == "impostor":
                # Six vertices derived from the index, one instance per sphere:
                # two triangles per atom against the ~270 a tessellated sphere
                # costs. No index buffer and no per-corner vertex buffer -- the
                # quad is a function of `vertex_index`.
                rp.draw(6, geom.vertex_count, 0, 0)
                continue
            if kind == "line":
                rp.draw(geom.vertex_count, 1, 0, 0)
                continue

            ibo = self.device.create_buffer_with_data(
                data=geom.indices, usage=wgpu.BufferUsage.INDEX
            )
            keep.append(ibo)
            rp.set_index_buffer(ibo, wgpu.IndexFormat.uint32)
            rp.draw_indexed(int(geom.indices.size), 1, 0, 0, 0)

        rp.end()

        # -- second pass: the silhouette, then the chrome ---------------------
        # Separate, because the outline samples the depth buffer the first pass
        # wrote and a depth attachment cannot be sampled while attached. The
        # chrome rides along rather than taking a third pass, and it goes last:
        # an outline drawn over the object panel would trace the panel.
        outline = self._silhouette_params(state, silhouette)
        if outline is not None or (overlay is not None and overlay.size):
            rp2 = encoder.begin_render_pass(
                color_attachments=[
                    {
                        "view": target_view,
                        "load_op": wgpu.LoadOp.load,
                        "store_op": wgpu.StoreOp.store,
                    }
                ],
            )
            if outline is not None:
                keep += self._draw_silhouette(rp2, depth_tex, outline)
            if overlay is not None and overlay.size:
                keep += self._draw_overlay(rp2, overlay)
            rp2.end()

        self.device.queue.submit([encoder.finish()])
