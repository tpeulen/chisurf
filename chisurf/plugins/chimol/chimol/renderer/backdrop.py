"""Backdrops: a picture behind the molecule instead of one flat colour.

Transparency is invisible against a uniform background. A surface at alpha 0.4
over black is just a darker surface -- there is nothing behind it for the eye to
catch, so lowering the alpha reads as dimming rather than as *seeing through*.
Put structure back there and the same surface immediately looks like glass,
because now something recognisable is visibly bent and dimmed by it.

That is what these are for. The star field is generated rather than shipped: a
procedural sky is a few lines of numpy, costs no binary in the repository, and
can be produced at exactly the resolution the widget needs instead of being
stretched from whatever a file happened to be.
"""
from __future__ import annotations

import numpy as np

__all__ = ["BACKDROPS", "render_backdrop", "starfield"]


def _smooth_noise(shape: tuple[int, int], scale: int, rng: np.random.Generator) -> np.ndarray:
    """Value noise at one octave, bilinearly upsampled to ``shape``.

    Parameters
    ----------
    shape : tuple of int
        ``(height, width)`` of the result.
    scale : int
        Grid size the noise is drawn on before upsampling; larger is finer.
    rng : numpy.random.Generator
        Source of randomness.

    Returns
    -------
    numpy.ndarray
        ``shape`` array in ``[0, 1]``.
    """
    height, width = shape
    coarse = rng.random((max(2, scale), max(2, scale)))
    ys = np.linspace(0, coarse.shape[0] - 1, height)
    xs = np.linspace(0, coarse.shape[1] - 1, width)
    y0 = np.floor(ys).astype(int)
    x0 = np.floor(xs).astype(int)
    y1 = np.minimum(y0 + 1, coarse.shape[0] - 1)
    x1 = np.minimum(x0 + 1, coarse.shape[1] - 1)
    ty = (ys - y0)[:, None]
    tx = (xs - x0)[None, :]
    top = coarse[np.ix_(y0, x0)] * (1 - tx) + coarse[np.ix_(y0, x1)] * tx
    bottom = coarse[np.ix_(y1, x0)] * (1 - tx) + coarse[np.ix_(y1, x1)] * tx
    return top * (1 - ty) + bottom * ty


def starfield(
    width: int = 1024,
    height: int = 768,
    *,
    seed: int = 7,
    density: float = 0.00035,
    nebula: float = 0.55,
) -> np.ndarray:
    """Draw a deep-sky backdrop: dust, a faint nebula, and stars.

    Built to make transparency legible rather than to be astronomically honest.
    Three things matter for that: it is **dark**, so a surface in front still
    reads as the brighter thing; it is **structured at several scales**, so
    whatever sits behind a given patch of surface is identifiable; and the stars
    are small and sharp, which is what shows refraction-like distortion when a
    surface passes over them.

    Parameters
    ----------
    width, height : int
        Size in pixels.
    seed : int
        Fixed by default, so a screenshot taken twice is the same picture and a
        rendering change is not lost in a different sky.
    density : float
        Stars per pixel.
    nebula : float
        Strength of the coloured cloud, 0 for none.

    Returns
    -------
    numpy.ndarray
        ``(height, width, 3)`` uint8 RGB.
    """
    width = max(2, int(width))
    height = max(2, int(height))
    rng = np.random.default_rng(int(seed))

    # Two octaves of cloud, tinted along a blue-violet ramp with a warmer core.
    cloud = 0.65 * _smooth_noise((height, width), 6, rng)
    cloud += 0.35 * _smooth_noise((height, width), 14, rng)
    cloud = np.clip((cloud - 0.35) * 1.9, 0.0, 1.0) ** 1.6

    image = np.zeros((height, width, 3), dtype=float)
    image[..., 0] = 0.06 + 0.30 * cloud * nebula          # a little red in the core
    image[..., 1] = 0.05 + 0.13 * cloud * nebula
    image[..., 2] = 0.09 + 0.42 * cloud * nebula          # mostly blue

    # A dark vignette, so the middle -- where the molecule sits -- stays the
    # brightest part of the picture and the backdrop never competes with it.
    yy, xx = np.mgrid[0:height, 0:width]
    radius = np.hypot(
        (yy - height / 2) / (height / 2), (xx - width / 2) / (width / 2)
    )
    image *= np.clip(1.15 - 0.45 * radius, 0.0, 1.0)[..., None]

    # Stars: mostly faint, a few bright, each a single sharp pixel with a soft
    # halo on the brightest so they do not look like dead pixels.
    count = max(1, int(width * height * float(density)))
    sy = rng.integers(0, height, count)
    sx = rng.integers(0, width, count)
    brightness = rng.random(count) ** 3.2                  # heavy tail: few bright
    tint = 0.75 + 0.25 * rng.random((count, 3))
    np.add.at(image, (sy, sx), (brightness[:, None] * tint))

    bright = brightness > 0.55
    for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        ys = np.clip(sy[bright] + dy, 0, height - 1)
        xs = np.clip(sx[bright] + dx, 0, width - 1)
        np.add.at(image, (ys, xs), 0.22 * brightness[bright][:, None] * tint[bright])

    return (np.clip(image, 0.0, 1.0) * 255).astype(np.uint8)


#: Backdrops that can be named instead of given as a file.
BACKDROPS: dict[str, str] = {
    "stars": "a deep-sky field with a faint nebula",
    "space": "a deep-sky field with a faint nebula",
    "nebula": "the same field with a stronger cloud",
}


def render_backdrop(name: str, width: int, height: int) -> np.ndarray | None:
    """Return the named backdrop as an RGB array, or ``None`` if unknown.

    Parameters
    ----------
    name : str
        A key of :data:`BACKDROPS`.
    width, height : int
        Size in pixels.

    Returns
    -------
    numpy.ndarray or None
    """
    key = str(name or "").strip().lower()
    if key in ("stars", "space"):
        return starfield(width, height)
    if key == "nebula":
        return starfield(width, height, nebula=1.0, density=0.00020)
    return None
