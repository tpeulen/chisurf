"""Render a small LUT plot as a base64 PNG for use in Qt rich-text tooltips.

The LUT-handling box shows, on hover over an assigned per-routing-channel LUT, a
tiny plot of the cumulative TAC-linearization table (``NTAC_fract``) together
with its per-bin derivative (the correction the LUT applies). Rendering is done
with matplotlib's Agg backend so it is deterministic and needs no display, which
also makes it unit-testable headlessly.

The returned string is a ``data:`` URI ready to drop into a tooltip::

    item.setToolTip(f'<img src="{render_lut_tooltip(ntac_fract)}">')
"""

from __future__ import annotations

import base64
import hashlib

import numpy as np

# Cache rendered thumbnails by LUT signature so repeated hovers do not re-render.
_CACHE: dict[str, str] = {}
_CACHE_MAX = 128


def _signature(ntac_fract: np.ndarray) -> str:
    """Return a stable cache key for a LUT array (length + content hash)."""
    b = np.ascontiguousarray(ntac_fract, dtype=np.float64).tobytes()
    return f"{ntac_fract.size}:{hashlib.md5(b).hexdigest()}"


def render_lut_png(ntac_fract, *, width_px: int = 240, height_px: int = 140) -> bytes:
    """Render a LUT to PNG bytes (cumulative ``NTAC_fract`` + its derivative).

    Parameters
    ----------
    ntac_fract : array-like
        The cumulative fractional NTAC positions produced by
        :func:`chisurf.plugins.tttr.tttr_lut_tools.core.tac_lut.build_linearization_table`.
    width_px, height_px : int
        Thumbnail size in pixels.

    Returns
    -------
    bytes
        PNG image bytes. Empty ``NTAC_fract`` yields an empty-plot PNG.
    """
    import matplotlib

    matplotlib.use("Agg", force=False)
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    arr = np.asarray(ntac_fract, dtype=float).ravel()
    dpi = 100.0
    fig = Figure(figsize=(width_px / dpi, height_px / dpi), dpi=dpi)
    ax = fig.add_subplot(111)
    if arr.size:
        x = np.arange(arr.size)
        ax.plot(x, arr, color="#4c9be8", lw=1.2, label="NTAC_fract")
        deriv = np.diff(arr, prepend=arr[0])
        ax2 = ax.twinx()
        ax2.plot(x, deriv, color="#e8804c", lw=0.9, alpha=0.8)
        ax2.tick_params(labelsize=6)
        ax.set_title("LUT (cumulative + Δ/bin)", fontsize=7)
    else:
        ax.text(0.5, 0.5, "empty LUT", ha="center", va="center", fontsize=8)
    ax.tick_params(labelsize=6)
    fig.tight_layout(pad=0.3)

    canvas = FigureCanvasAgg(fig)
    canvas.draw()
    import io

    buf = io.BytesIO()
    canvas.print_png(buf)
    return buf.getvalue()


def render_lut_tooltip(ntac_fract) -> str:
    """Return a ``data:image/png;base64,...`` URI for a LUT thumbnail (cached)."""
    arr = np.asarray(ntac_fract, dtype=float).ravel()
    key = _signature(arr)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    png = render_lut_png(arr)
    uri = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.clear()
    _CACHE[key] = uri
    return uri
