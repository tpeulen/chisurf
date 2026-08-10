"""Camera and the instanced sprite batcher.

Everything chigame draws in a frame goes through one :class:`SpriteBatch`, which
issues a single draw call. The shapes themselves are evaluated in
``shaders/sprite.wgsl``; this module owns the buffers, the pipeline and the
world-to-screen mapping.
"""

from __future__ import annotations

import pathlib

import numpy as np
import wgpu

#: Shape identifiers, matching the constants in ``sprite.wgsl``.
RECT = 0.0
ELLIPSE = 1.0
ROUND = 2.0
RING = 3.0
GLYPH = 4.0
GLOW = 5.0
TRI = 6.0

#: Floats per instance. Mirrors the ``Instance`` struct's std430 layout.
FLOATS_PER_INSTANCE = 16

_SHADER_PATH = pathlib.Path(__file__).parent / "shaders" / "sprite.wgsl"


class Camera:
    """An orthographic 2-D camera.

    The camera spans ``2 * half_extent`` world units. Y grows downward, which is
    the convention a tile map wants, and the shader flips it for clip space.

    Parameters
    ----------
    center : tuple of float, optional
        World-space point the view is centred on.
    height : float, optional
        World-space height the view spans. The width follows from the canvas
        aspect ratio, so a window resize changes how much is visible
        horizontally rather than stretching what is drawn.
    """

    def __init__(self, center: tuple[float, float] = (0.0, 0.0), height: float = 100.0) -> None:
        self.center = np.array(center, dtype=np.float32)
        self.height = float(height)

    def half_extent(self, aspect: float) -> np.ndarray:
        """Half the world-space size the view spans.

        Parameters
        ----------
        aspect : float
            Canvas width divided by height.

        Returns
        -------
        numpy.ndarray
            ``(half_width, half_height)`` as float32.
        """
        half_h = self.height * 0.5
        return np.array([half_h * aspect, half_h], dtype=np.float32)

    def uniform(self, aspect: float) -> np.ndarray:
        """Pack the camera into its uniform-buffer layout.

        Parameters
        ----------
        aspect : float
            Canvas width divided by height.

        Returns
        -------
        numpy.ndarray
            Four float32 values: centre then half-extent.
        """
        return np.concatenate([self.center, self.half_extent(aspect)]).astype(np.float32)

    def world_to_screen(
        self, point: tuple[float, float], size: tuple[int, int]
    ) -> tuple[float, float]:
        """Project a world point to pixel coordinates.

        Needed for picking — the minesweeper port is the first consumer.

        Parameters
        ----------
        point : tuple of float
            World-space position.
        size : tuple of int
            Canvas size in pixels.

        Returns
        -------
        tuple of float
            Pixel coordinates, origin top-left.
        """
        width, height = size
        half = self.half_extent(width / max(height, 1))
        ndc = (np.asarray(point, dtype=np.float32) - self.center) / half
        return (ndc[0] + 1.0) * 0.5 * width, (ndc[1] + 1.0) * 0.5 * height

    def screen_to_world(
        self, pixel: tuple[float, float], size: tuple[int, int]
    ) -> tuple[float, float]:
        """Invert :meth:`world_to_screen`.

        Parameters
        ----------
        pixel : tuple of float
            Pixel coordinates, origin top-left.
        size : tuple of int
            Canvas size in pixels.

        Returns
        -------
        tuple of float
            World-space position.
        """
        width, height = size
        half = self.half_extent(width / max(height, 1))
        ndc = np.array(
            [pixel[0] / width * 2.0 - 1.0, pixel[1] / height * 2.0 - 1.0], dtype=np.float32
        )
        world = ndc * half + self.center
        return float(world[0]), float(world[1])


class SpriteBatch:
    """Collects quads for one frame and draws them in a single call.

    Instances are accumulated into a growable float32 array and uploaded once
    per frame. The buffer is only reallocated when a frame needs more room than
    any previous frame did, so a steady-state game allocates nothing.

    Parameters
    ----------
    context : chisurf.gui.chigame.gpu.GpuContext
        The configured canvas to draw into.
    """

    def __init__(self, context) -> None:
        self._ctx = context
        self._device = context.device
        self._instances: list[np.ndarray] = []
        # Entries may hold one quad or many, so the count is tracked rather
        # than taken from len(self._instances).
        self._count = 0
        self._capacity = 0
        self._storage = None
        self._bind_group = None
        self._atlas_view = None
        self._uniform = self._device.create_buffer(
            size=16, usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST
        )
        self._sampler = self._device.create_sampler(
            mag_filter=wgpu.FilterMode.linear, min_filter=wgpu.FilterMode.linear
        )
        self._layout = self._device.create_bind_group_layout(
            entries=[
                {
                    "binding": 0,
                    "visibility": wgpu.ShaderStage.VERTEX,
                    "buffer": {"type": wgpu.BufferBindingType.uniform},
                },
                {
                    "binding": 1,
                    "visibility": wgpu.ShaderStage.VERTEX,
                    "buffer": {"type": wgpu.BufferBindingType.read_only_storage},
                },
                {
                    "binding": 2,
                    "visibility": wgpu.ShaderStage.FRAGMENT,
                    "texture": {"sample_type": wgpu.TextureSampleType.float},
                },
                {
                    "binding": 3,
                    "visibility": wgpu.ShaderStage.FRAGMENT,
                    "sampler": {"type": wgpu.SamplerBindingType.filtering},
                },
            ]
        )
        self._pipeline = self._build_pipeline()
        self.set_atlas(None)

    def _build_pipeline(self):
        """Compile the shader and build the render pipeline.

        Returns
        -------
        wgpu.GPURenderPipeline
            The pipeline used for every draw.
        """
        shader = self._device.create_shader_module(code=_SHADER_PATH.read_text(encoding="utf-8"))
        pipeline_layout = self._device.create_pipeline_layout(bind_group_layouts=[self._layout])
        return self._device.create_render_pipeline(
            layout=pipeline_layout,
            vertex={"module": shader, "entry_point": "vs_main"},
            primitive={"topology": wgpu.PrimitiveTopology.triangle_list},
            fragment={
                "module": shader,
                "entry_point": "fs_main",
                "targets": [
                    {
                        "format": self._ctx.format,
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
        )

    def set_atlas(self, texture) -> None:
        """Bind the coverage atlas that ``GLYPH`` instances sample.

        Parameters
        ----------
        texture : wgpu.GPUTexture or None
            The atlas. ``None`` installs an opaque 1x1 texture, so a game that
            draws no text still has a valid binding.
        """
        if texture is None:
            texture = self._device.create_texture(
                size=(1, 1, 1),
                format=wgpu.TextureFormat.r8unorm,
                usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST,
            )
            self._device.queue.write_texture(
                {"texture": texture},
                np.full((1, 1), 255, dtype=np.uint8).tobytes(),
                {"bytes_per_row": 1, "rows_per_image": 1},
                (1, 1, 1),
            )
        self._atlas_view = texture.create_view()
        self._bind_group = None

    def clear(self) -> None:
        """Drop everything queued for the current frame."""
        self._instances.clear()
        self._count = 0

    def add(
        self,
        pos: tuple[float, float],
        size: tuple[float, float],
        color: tuple[float, float, float, float],
        shape: float = RECT,
        param: float = 0.0,
        rotation: float = 0.0,
        softness: float = 0.02,
        uv: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0),
    ) -> None:
        """Queue one quad.

        Parameters
        ----------
        pos : tuple of float
            Centre, in world units.
        size : tuple of float
            Full width and height, in world units.
        color : tuple of float
            Straight sRGB RGBA in 0..1. The shader converts to linear.
        shape : float, optional
            One of the shape constants in this module.
        param : float, optional
            Shape parameter: corner radius for ``ROUND``, inner radius for
            ``RING``, falloff for ``GLOW``.
        rotation : float, optional
            Rotation in radians.
        softness : float, optional
            Edge softness in local units.
        uv : tuple of float, optional
            Atlas rectangle, read only by ``GLYPH``.
        """
        self._instances.append(
            np.array(
                [
                    pos[0], pos[1], size[0], size[1],
                    color[0], color[1], color[2], color[3],
                    shape, param, rotation, softness,
                    uv[0], uv[1], uv[2], uv[3],
                ],
                dtype=np.float32,
            )
        )
        self._count += 1

    def add_array(self, instances: np.ndarray) -> None:
        """Queue many quads at once from a prepared array.

        :meth:`add` costs a Python call and a small array allocation per quad,
        which is fine for a few hundred and is the whole frame budget for a
        tile map: a screenful of ground is thousands of quads. A caller that can
        build its instances with array operations should hand them over whole.

        Parameters
        ----------
        instances : numpy.ndarray
            Shape ``(n, FLOATS_PER_INSTANCE)``, float32, laid out exactly as
            :meth:`add` builds a row.

        Raises
        ------
        ValueError
            If the array's second dimension is not the instance stride.
        """
        array = np.ascontiguousarray(instances, dtype=np.float32)
        if array.ndim != 2 or array.shape[1] != FLOATS_PER_INSTANCE:
            raise ValueError(
                f"instances must be (n, {FLOATS_PER_INSTANCE}), got {array.shape}"
            )
        if array.size:
            self._instances.append(array.reshape(-1))
            self._count += array.shape[0]

    def _ensure_capacity(self, count: int) -> None:
        """Grow the instance storage buffer if this frame needs more room.

        Parameters
        ----------
        count : int
            Number of instances in the frame.
        """
        if self._storage is not None and count <= self._capacity:
            return
        # Grow in powers of two so a game that ramps up does not reallocate
        # every frame on the way.
        capacity = max(256, 1 << (max(count, 1) - 1).bit_length())
        self._storage = self._device.create_buffer(
            size=capacity * FLOATS_PER_INSTANCE * 4,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST,
        )
        self._capacity = capacity
        self._bind_group = None

    def flush(self, render_pass, camera: Camera) -> int:
        """Upload the frame's instances and record the draw.

        Parameters
        ----------
        render_pass : wgpu.GPURenderPassEncoder
            An open render pass.
        camera : Camera
            The view to render through.

        Returns
        -------
        int
            Number of instances drawn.
        """
        count = self._count
        if count == 0:
            return 0
        self._ensure_capacity(count)

        width, height = self._ctx.size
        self._device.queue.write_buffer(
            self._uniform, 0, camera.uniform(width / max(height, 1)).tobytes()
        )
        self._device.queue.write_buffer(self._storage, 0, np.concatenate(self._instances).tobytes())

        if self._bind_group is None:
            self._bind_group = self._device.create_bind_group(
                layout=self._layout,
                entries=[
                    {"binding": 0, "resource": {"buffer": self._uniform, "offset": 0, "size": 16}},
                    {
                        "binding": 1,
                        "resource": {
                            "buffer": self._storage,
                            "offset": 0,
                            "size": self._capacity * FLOATS_PER_INSTANCE * 4,
                        },
                    },
                    {"binding": 2, "resource": self._atlas_view},
                    {"binding": 3, "resource": self._sampler},
                ],
            )

        render_pass.set_pipeline(self._pipeline)
        render_pass.set_bind_group(0, self._bind_group)
        render_pass.draw(6, count)
        return count
