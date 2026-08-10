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
from typing import Optional, Sequence

import numpy as np

from .depth_cue import fog_planes
from .lighting import LightRig, resolve_light_rig
from .pack import PackedScene
from .view_state import unpack_view_state

WGSL_DIR = pathlib.Path(__file__).with_name("wgsl")

def load_wgsl(name: str) -> str:
    """Read a shader from the shared ``wgsl`` directory.

    Parameters
    ----------
    name : str
        File name, e.g. ``"mesh.wgsl"``.

    Returns
    -------
    str
        The shader source, unmodified. It is shared with the browser backend, so
        nothing may be rewritten on the way through -- a per-backend edit here is
        exactly the drift this arrangement exists to prevent.
    """
    return (WGSL_DIR / name).read_text()


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


def view_matrix(rotation: np.ndarray, target: np.ndarray, distance: float) -> np.ndarray:
    """Build the view matrix from PyMOL's rotation, target and distance."""
    r = np.eye(4, dtype=np.float32)
    r[:3, :3] = np.asarray(rotation, dtype=np.float32).reshape(3, 3)
    t = np.eye(4, dtype=np.float32)
    t[:3, 3] = -np.asarray(target, dtype=np.float32).reshape(3)
    back = np.eye(4, dtype=np.float32)
    back[2, 3] = -float(distance)
    return back @ r @ t


class WgpuMeshRenderer:
    """Draw the mesh objects of a packed scene, offscreen.

    Parameters
    ----------
    width, height : int
        Framebuffer size in pixels.
    """

    def __init__(self, width: int = 1280, height: int = 860) -> None:
        import wgpu

        self._wgpu = wgpu
        self.width, self.height = int(width), int(height)
        adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
        self.device = adapter.request_device_sync()
        self.adapter_info = dict(adapter.info)

        module = self.device.create_shader_module(code=load_wgsl("mesh.wgsl"))
        # Non-sRGB on purpose. The swap-chain's preferred format is
        # `rgba8unorm-srgb`, which gamma-encodes on write; the OpenGL backend
        # draws to a plain framebuffer and does not. Rendering into an sRGB
        # target here would wash every colour out relative to the baseline -- a
        # clear value of 0.09 comes back as 85 instead of 23 -- and the whole
        # point of this renderer is to be comparable to that baseline.
        self.format = wgpu.TextureFormat.rgba8unorm

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
        # position(3) normal(3) colour(4) occlusion(1) = 11 floats, interleaved.
        stride = 11 * 4
        self._pipelines: dict[bool, object] = {}
        for depth_write in (True, False):
            self._pipelines[depth_write] = self._make_pipeline(
                module, layout, stride, depth_write
            )
        # Opaque geometry writes depth; transparent geometry does not, or the
        # near face of a translucent shell occludes the far face of the same
        # shell and the surface reads solid.
        self.pipeline = self._pipelines[True]
        self.pipeline_blend = self._pipelines[False]

    def _make_pipeline(self, module, layout, stride, depth_write):
        """Build the render pipeline, with or without depth writes."""
        wgpu = self._wgpu
        return self.device.create_render_pipeline(
            layout=layout,
            vertex={
                "module": module,
                "entry_point": "vs_main",
                "buffers": [
                    {
                        "array_stride": stride,
                        "step_mode": wgpu.VertexStepMode.vertex,
                        "attributes": [
                            {"format": wgpu.VertexFormat.float32x3, "offset": 0, "shader_location": 0},
                            {"format": wgpu.VertexFormat.float32x3, "offset": 12, "shader_location": 1},
                            {"format": wgpu.VertexFormat.float32x4, "offset": 24, "shader_location": 2},
                            {"format": wgpu.VertexFormat.float32, "offset": 40, "shader_location": 3},
                        ],
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
                "topology": wgpu.PrimitiveTopology.triangle_list,
                # Both faces: a cartoon ribbon is a two-sided sheet, and culling
                # it would delete the inside of every helix.
                "cull_mode": wgpu.CullMode.none,
            },
        )

    # -- interleaving --------------------------------------------------------

    @staticmethod
    def interleave(geometry) -> np.ndarray:
        """Pack one geometry's attributes into the vertex layout.

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
        if geometry.colors is not None:
            cols = geometry.colors
            out[:, 6 : 6 + min(4, cols.shape[1])] = cols[:, :4]
            if cols.shape[1] == 3:
                out[:, 9] = 1.0
        else:
            out[:, 6:10] = 1.0
        if geometry.occlusion is not None:
            out[:, 10] = geometry.occlusion[:, 0]
        return np.ascontiguousarray(out)

    def _uniforms(self, mvp, view, normal_matrix, fog_end, fog_scale, fog_color,
                  two_sided, opacity, rig: LightRig) -> bytes:
        def m(a):
            # WGSL matrices are column-major; numpy is row-major.
            return np.ascontiguousarray(np.asarray(a, np.float32).T).tobytes()

        b = bytearray()
        b += m(mvp) + m(view) + m(normal_matrix)
        b += np.array([*rig.light_dir, 0.0], np.float32).tobytes()
        b += np.array([*rig.fill_dir, 0.0], np.float32).tobytes()
        b += np.array([*fog_color, float(fog_end)], np.float32).tobytes()
        b += np.array([rig.key, rig.fill, rig.ambient, rig.specular], np.float32).tobytes()
        b += np.array(
            [rig.shininess, rig.rim_strength, rig.rim_power, float(fog_scale)],
            np.float32,
        ).tobytes()
        b += np.array([1.0 if two_sided else 0.0, float(opacity), 0.0, 0.0], np.float32).tobytes()
        return bytes(b)

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
            PyMOL's ``two_sided_lighting``.
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
        light = lighting if lighting is not None else resolve_light_rig()
        state = unpack_view_state(view_state)

        view = view_matrix(state.rotation, state.target, state.distance)
        proj = perspective(
            state.fov, self.width / max(self.height, 1), max(state.near, 1e-3), state.far
        )
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

        colour_tex = self.device.create_texture(
            size=(self.width, self.height, 1),
            format=self.format,
            usage=wgpu.TextureUsage.RENDER_ATTACHMENT | wgpu.TextureUsage.COPY_SRC,
        )
        depth_tex = self.device.create_texture(
            size=(self.width, self.height, 1),
            format=wgpu.TextureFormat.depth24plus,
            usage=wgpu.TextureUsage.RENDER_ATTACHMENT,
        )

        encoder = self.device.create_command_encoder()
        rp = encoder.begin_render_pass(
            color_attachments=[
                {
                    "view": colour_tex.create_view(),
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
        keep = []  # buffers must outlive the pass

        def _opacity(obj) -> float:
            return 1.0 if obj.material is None else float(obj.material.opacity)

        # Opaque first, then transparent. Blending is order-dependent: drawing a
        # translucent surface before the geometry behind it composites it against
        # the background instead of against what it should veil.
        drawable = [
            o
            for o in scene.objects
            if o.geometry.kind == "mesh"
            and o.geometry.indices is not None
            and o.geometry.indices.size
        ]
        ordered = sorted(
            drawable,
            key=lambda o: (_opacity(o) < 1.0 or o.render_mode == "transparent"),
        )

        current = None
        for obj in ordered:
            geom = obj.geometry
            opacity = _opacity(obj)
            blended = opacity < 1.0 or obj.render_mode == "transparent"
            pipeline = self.pipeline_blend if blended else self.pipeline
            if pipeline is not current:
                rp.set_pipeline(pipeline)
                current = pipeline
            data = self.interleave(geom)
            vbo = self.device.create_buffer_with_data(
                data=data, usage=wgpu.BufferUsage.VERTEX
            )
            ibo = self.device.create_buffer_with_data(
                data=geom.indices, usage=wgpu.BufferUsage.INDEX
            )
            ubo = self.device.create_buffer_with_data(
                data=self._uniforms(
                    mvp, view, normal_matrix, fog_end, fog_scale,
                    background, two_sided, opacity, light,
                ),
                usage=wgpu.BufferUsage.UNIFORM,
            )
            bind = self.device.create_bind_group(
                layout=self._bind_layout,
                entries=[{"binding": 0, "resource": {"buffer": ubo, "offset": 0, "size": ubo.size}}],
            )
            keep += [vbo, ibo, ubo, bind]
            rp.set_bind_group(0, bind)
            rp.set_vertex_buffer(0, vbo)
            rp.set_index_buffer(ibo, wgpu.IndexFormat.uint32)
            rp.draw_indexed(int(geom.indices.size), 1, 0, 0, 0)

        rp.end()
        self.device.queue.submit([encoder.finish()])

        raw = self.device.queue.read_texture(
            {"texture": colour_tex, "origin": (0, 0, 0)},
            {"bytes_per_row": self.width * 4, "rows_per_image": self.height},
            (self.width, self.height, 1),
        )
        img = np.frombuffer(raw, np.uint8).reshape(self.height, self.width, 4)
        return np.ascontiguousarray(img[..., :3])
