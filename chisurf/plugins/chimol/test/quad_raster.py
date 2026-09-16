"""Rasterise the chrome's quad stream on the CPU, so it can be looked at.

Why a second rasteriser exists at all
-------------------------------------
:class:`~emtk.quad_painter.QuadPainter` produces vertices, not
pixels, and the thing that turns them into pixels is a GPU. That makes the
obvious test -- *does the panel still look right* -- depend on a device, a
surface and a driver, none of which is what is being tested when the question
is whether a glyph landed at the right baseline.

So this does what ``ui.wgsl`` does, in numpy: the same quad interpretation, the
same premultiplied blend, the same clip-rectangle test. It is slow and it is
not what ships. What it buys is that the chrome can be **rendered and inspected
with no GPU at all**, which is how the alignment, the clipping and the gradient
were checked before any of it was wired to a pipeline.

It samples the atlas with nearest-neighbour where the shader samples linearly,
so its text is a little harder-edged than the real thing. That is deliberate:
this is for judging *placement*, and softening it here would hide a glyph that
is half a pixel out.
"""
from __future__ import annotations

import numpy as np

__all__ = ["rasterise", "over"]


def rasterise(vertices: np.ndarray, width: int, height: int, coverage) -> np.ndarray:
    """Draw an interleaved quad stream into a premultiplied RGBA image.

    Parameters
    ----------
    vertices : numpy.ndarray
        ``(n, 12)`` float32 from :meth:`QuadPainter.vertices`.
    width, height : int
        Target size, in pixels.
    coverage : numpy.ndarray
        The atlas's alpha channel, ``(h, w)`` in ``[0, 1]``.

    Returns
    -------
    numpy.ndarray
        ``(height, width, 4)`` uint8, premultiplied.
    """
    out = np.zeros((height, width, 4), dtype=np.float64)
    if vertices.size == 0:
        return out.astype(np.uint8)

    for index in range(0, len(vertices), 6):
        top_left = vertices[index]
        top_right = vertices[index + 1]
        bottom_right = vertices[index + 2]

        x0, y0 = float(top_left[0]), float(top_left[1])
        x1, y1 = float(bottom_right[0]), float(bottom_right[1])
        cx0, cy0, cx1, cy1 = (float(v) for v in top_left[8:12])

        px0 = max(int(np.floor(min(x0, x1))), int(np.ceil(cx0)), 0)
        px1 = min(int(np.ceil(max(x0, x1))), int(np.floor(cx1)) + 1, width)
        py0 = max(int(np.floor(min(y0, y1))), int(np.ceil(cy0)), 0)
        py1 = min(int(np.ceil(max(y0, y1))), int(np.floor(cy1)) + 1, height)
        if px1 <= px0 or py1 <= py0:
            continue

        fx = np.clip(
            (np.arange(px0, px1) + 0.5 - x0) / (x1 - x0) if x1 != x0
            else np.zeros(px1 - px0),
            0.0, 1.0,
        )
        fy = np.clip(
            (np.arange(py0, py1) + 0.5 - y0) / (y1 - y0) if y1 != y0
            else np.zeros(py1 - py0),
            0.0, 1.0,
        )

        u0, v0 = float(top_left[2]), float(top_left[3])
        u1, v1 = float(bottom_right[2]), float(bottom_right[3])
        if u1 != u0 or v1 != v0:
            ui = np.clip(
                (u0 + fx[None, :] * (u1 - u0)).astype(int), 0, coverage.shape[1] - 1
            )
            vi = np.clip(
                (v0 + fy[:, None] * (v1 - v0)).astype(int), 0, coverage.shape[0] - 1
            )
            ink = coverage[vi, ui]
        else:
            ink = np.ones((py1 - py0, px1 - px0))
        ink = np.broadcast_to(ink, (py1 - py0, px1 - px0))

        # Horizontal interpolation only: the gradient is the one caller with
        # unequal corners, and it varies left to right.
        colour = (
            top_left[4:8][None, None, :] * (1 - fx)[None, :, None]
            + top_right[4:8][None, None, :] * fx[None, :, None]
        )
        colour = np.broadcast_to(colour, (py1 - py0, px1 - px0, 4))

        alpha = colour[..., 3] * ink
        source = np.empty((py1 - py0, px1 - px0, 4))
        source[..., :3] = colour[..., :3] * alpha[..., None]
        source[..., 3] = alpha
        target = out[py0:py1, px0:px1]
        out[py0:py1, px0:px1] = source + target * (1.0 - alpha[..., None])

    return (np.clip(out, 0.0, 1.0) * 255.0).astype(np.uint8)


def over(image: np.ndarray, background=(40, 40, 40)) -> np.ndarray:
    """Composite premultiplied RGBA over a flat colour, for looking at.

    Parameters
    ----------
    image : numpy.ndarray
        ``(h, w, 4)`` uint8, premultiplied.
    background : tuple of int
        The colour behind it.

    Returns
    -------
    numpy.ndarray
        ``(h, w, 3)`` uint8.
    """
    alpha = image[..., 3:4] / 255.0
    back = np.asarray(background, dtype=np.float64)[None, None, :]
    return np.clip(image[..., :3] + back * (1.0 - alpha), 0, 255).astype(np.uint8)
