"""The WebGPU constants the engine uses, written out once.

Why these are values here rather than a re-export
-------------------------------------------------
Every constant below is fixed by the **WebGPU specification**, not by the Python
binding: the string enums are the spec's own kebab-case spellings and the usage
flags are the spec's own bit values. ``wgpu-py`` reports exactly these, and so
does a browser -- ``GPUBufferUsage.VERTEX`` is 32 in both places.

That is worth stating because it decides the shape of the whole seam. Of the
thirty-eight ``wgpu.*`` names the engine touches, thirty-four are these
constants and three more appear only in docstrings, which leaves **one** name
that a backend actually has to provide (see :mod:`.native`). Delegating the
constants to a backend would have implied a translation step that does not
exist, and would have put a per-frame attribute lookup in front of values that
never change.

:mod:`chimol.renderer.gpu.test_matches_wgpu`'s counterpart in the test suite
asserts these against the installed binding, so a drift on either side fails
rather than silently rendering something else.

The names are spelled as ``wgpu-py`` spells them -- ``triangle_list`` for
``"triangle-list"`` -- so that call sites read the same before and after the
seam went in.
"""
from __future__ import annotations

__all__ = [
    "BlendFactor",
    "BlendOperation",
    "BufferBindingType",
    "BufferUsage",
    "CompareFunction",
    "CullMode",
    "FilterMode",
    "IndexFormat",
    "LoadOp",
    "PrimitiveTopology",
    "SamplerBindingType",
    "ShaderStage",
    "StoreOp",
    "TextureFormat",
    "TextureSampleType",
    "TextureUsage",
]


class BlendFactor:
    """Blend-equation factors."""

    one = "one"
    src_alpha = "src-alpha"
    one_minus_src_alpha = "one-minus-src-alpha"


class BlendOperation:
    """Blend-equation operators."""

    add = "add"


class BufferBindingType:
    """How a shader may bind a buffer."""

    uniform = "uniform"
    storage = "storage"
    read_only_storage = "read-only-storage"


class BufferUsage:
    """Buffer usage flags. Bit values, combined with ``|``."""

    COPY_SRC = 4
    COPY_DST = 8
    INDEX = 16
    VERTEX = 32
    UNIFORM = 64
    STORAGE = 128


class CompareFunction:
    """Depth/stencil comparison functions."""

    less = "less"


class CullMode:
    """Face culling."""

    none = "none"


class FilterMode:
    """Sampler filtering."""

    nearest = "nearest"


class IndexFormat:
    """Index buffer element type.

    ``uint32`` and ``uint16`` are the only two WebGPU accepts, which is why
    :func:`chimol.renderer.pack.pack_geometry` casts the builders' ``int32``.
    """

    uint32 = "uint32"


class LoadOp:
    """What a render pass does with an attachment's existing contents."""

    clear = "clear"
    load = "load"


class PrimitiveTopology:
    """Primitive assembly."""

    triangle_list = "triangle-list"
    line_list = "line-list"


class SamplerBindingType:
    """How a shader may bind a sampler."""

    filtering = "filtering"
    non_filtering = "non-filtering"


class ShaderStage:
    """Shader stage flags. Bit values, combined with ``|``."""

    VERTEX = 1
    FRAGMENT = 2
    COMPUTE = 4


class StoreOp:
    """What a render pass does with an attachment's results."""

    store = "store"


class TextureFormat:
    """Texture formats.

    ``bgra8unorm`` and ``rgba8unorm`` are here because they are what a canvas
    reports as its preferred format -- on the desktop and in a browser alike.
    Neither is an ``-srgb`` variant, and that is not an oversight to correct:
    the shaders write colours the baseline renderer wrote to a plain
    framebuffer, and an sRGB target gamma-encodes on write, so a clear value of
    0.09 comes back as 85 instead of 23 and every colour washes out.
    """

    rgba8unorm = "rgba8unorm"
    bgra8unorm = "bgra8unorm"
    depth24plus = "depth24plus"


class TextureSampleType:
    """How a shader samples a bound texture."""

    float = "float"
    depth = "depth"


class TextureUsage:
    """Texture usage flags. Bit values, combined with ``|``.

    ``RENDER_ATTACHMENT | TEXTURE_BINDING`` together are load-bearing: the
    second pass reads the depth the first pass wrote, so the depth texture has
    to be both drawn into and sampled. A backend that offers only
    ``RENDER_ATTACHMENT`` cannot run this engine's silhouette pass at all.
    """

    COPY_SRC = 1
    COPY_DST = 2
    TEXTURE_BINDING = 4
    RENDER_ATTACHMENT = 16
