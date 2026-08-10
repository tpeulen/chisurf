"""Resolve a chiplot colormap identity to a lookup table.

:class:`~chisurf.gui.chiplot.style.Colormap` deliberately carries only a name
and a namespace — resolving it is the backend's job, which is what lets Qt-free
code ask for ``"viridis"`` without importing a renderer. The pyqtgraph backend
asks pyqtgraph; this one asks matplotlib, and keeps a small built-in table so a
heatmap still renders (in the right *kind* of colours) when a name belongs to a
namespace that is not installed.
"""

from __future__ import annotations

import warnings

import numpy as np

from chisurf.gui.chiplot import style as S

#: Anchor colours for the fallback maps, interpolated linearly.
_BUILTIN: dict[str, list[tuple[float, float, float]]] = {
    "viridis": [(0.267, 0.005, 0.329), (0.188, 0.408, 0.557),
                (0.208, 0.718, 0.473), (0.993, 0.906, 0.144)],
    "magma": [(0.001, 0.000, 0.014), (0.446, 0.123, 0.506),
              (0.929, 0.412, 0.352), (0.987, 0.991, 0.749)],
    "inferno": [(0.001, 0.000, 0.014), (0.578, 0.148, 0.404),
                (0.965, 0.559, 0.098), (0.988, 0.998, 0.645)],
    "gray": [(0.0, 0.0, 0.0), (1.0, 1.0, 1.0)],
    "hot": [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (1.0, 1.0, 1.0)],
    "rdbu": [(0.404, 0.0, 0.121), (0.957, 0.647, 0.510), (0.969, 0.969, 0.969),
             (0.404, 0.663, 0.812), (0.019, 0.188, 0.380)],
    "coolwarm": [(0.230, 0.299, 0.754), (0.865, 0.865, 0.865),
                 (0.706, 0.016, 0.150)],
    "turbo": [(0.190, 0.072, 0.232), (0.098, 0.669, 0.888),
              (0.573, 0.988, 0.325), (0.984, 0.596, 0.146), (0.479, 0.012, 0.011)],
}

_warned: set[str] = set()
_cache: dict[tuple[str, str, int], np.ndarray] = {}


def _interpolate(anchors, n: int) -> np.ndarray:
    """Expand anchor colours to an ``(n, 4)`` uint8 table."""
    a = np.asarray(anchors, dtype=np.float64)
    src = np.linspace(0.0, 1.0, len(a))
    dst = np.linspace(0.0, 1.0, n)
    rgb = np.column_stack([np.interp(dst, src, a[:, i]) for i in range(3)])
    return np.column_stack([rgb * 255.0, np.full(n, 255.0)]).astype(np.uint8)


def lookup_table(cmap: S.Colormap | str | None, n: int = 256) -> np.ndarray | None:
    """Return an ``(n, 4)`` uint8 RGBA lookup table for *cmap*.

    Parameters
    ----------
    cmap : Colormap or str or None
        The colormap to resolve. ``None`` returns ``None``.
    n : int
        Number of entries.

    Returns
    -------
    numpy.ndarray or None
        The table, or ``None`` when *cmap* is ``None``.
    """
    if cmap is None:
        return None
    cm = S.to_colormap(cmap)
    key = (cm.name, cm.source or "", int(n))
    hit = _cache.get(key)
    if hit is not None:
        return hit

    table = _from_matplotlib(cm.name, n)
    if table is None:
        anchors = _BUILTIN.get(cm.name.lower().removesuffix("_r"))
        if anchors is None:
            if cm.name not in _warned:
                _warned.add(cm.name)
                warnings.warn(
                    f"chiplot: colormap {cm.name!r} is not available to the wgpu "
                    f"backend; falling back to viridis",
                    RuntimeWarning, stacklevel=2)
            anchors = _BUILTIN["viridis"]
        table = _interpolate(anchors, n)
        if cm.name.lower().endswith("_r"):
            table = table[::-1]
    _cache[key] = table
    return table


def _from_matplotlib(name: str, n: int) -> np.ndarray | None:
    """Resolve *name* through matplotlib, or ``None`` if it cannot."""
    try:
        import matplotlib

        try:
            cmap = matplotlib.colormaps[name]
        except (AttributeError, KeyError):
            cmap = matplotlib.cm.get_cmap(name)
    except Exception:
        return None
    values = cmap(np.linspace(0.0, 1.0, n))
    return (np.asarray(values) * 255.0).astype(np.uint8)
