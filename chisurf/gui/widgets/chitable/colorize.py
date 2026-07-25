"""Value-scaled cell backgrounds for :mod:`chisurf.gui.widgets.chitable`.

This restores the one feature the retired third-party table editor was genuinely
liked for: a cell's background encodes where its value sits within the column's
range, so an outlier in a residuals or error column is visible without reading a
single number.

Two details matter and are inherited from that editor's design:

* the ramp is computed in HSV so the text stays legible — saturation and value
  are fixed, only the hue moves, and the colour is laid down at moderate alpha;
* the expensive part is the per-column min/max reduce, not the painting, so the
  whole feature switches itself off above :attr:`ValueColorScheme.max_cells`.

Colouring is applied through the model's ``BackgroundRole`` rather than a
delegate on purpose: a column can only have one delegate, and the numeric,
boolean and rich-text delegates already occupy that slot.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from qtpy import QtGui

#: Hue assigned to the largest value in a range (blue).
MIN_HUE = 0.66
#: Hue span swept from the largest to the smallest value.
HUE_RANGE = 0.33
#: Fixed HSV saturation of the ramp.
SATURATION = 0.7
#: Fixed HSV value of the ramp.
VALUE = 1.0
#: Default cell count above which colouring turns itself off.
DEFAULT_MAX_CELLS = 5_000_000


def _hsv_color(fraction: float, alpha: float) -> QtGui.QColor:
    """Return the ramp colour for a normalised position.

    Parameters
    ----------
    fraction : float
        Position within the range, ``0.0`` at the maximum and ``1.0`` at the
        minimum (the ordering the historic ramp used).
    alpha : float
        Alpha channel in ``[0, 1]``.

    Returns
    -------
    qtpy.QtGui.QColor
    """
    hue = MIN_HUE + HUE_RANGE * float(np.clip(fraction, 0.0, 1.0))
    hue = abs(hue) % 1.0
    return QtGui.QColor.fromHsvF(hue, SATURATION, VALUE, float(np.clip(alpha, 0.0, 1.0)))


def _lut_color(lut: np.ndarray, fraction: float, alpha: float) -> QtGui.QColor:
    """Look a normalised position up in an RGB lookup table.

    Parameters
    ----------
    lut : numpy.ndarray
        ``(N, 3)`` array of ``uint8`` RGB entries.
    fraction : float
        Position within the range, ``0.0`` at the minimum.
    alpha : float
        Alpha channel in ``[0, 1]``.

    Returns
    -------
    qtpy.QtGui.QColor
    """
    idx = int(np.clip(fraction, 0.0, 1.0) * (len(lut) - 1))
    r, g, b = (int(c) for c in lut[idx][:3])
    return QtGui.QColor(r, g, b, int(np.clip(alpha, 0.0, 1.0) * 255))


def resolve_lut(name: str) -> np.ndarray | None:
    """Resolve a colormap name to an ``(N, 3)`` ``uint8`` lookup table.

    Tries the chiplot colormap registry first (so a table honours whatever
    backend the plots use), then matplotlib. Returns ``None`` when neither can
    supply the map, in which case the caller falls back to the built-in HSV
    ramp — a table must never drag a plotting backend in just to paint a cell.

    Parameters
    ----------
    name : str
        Colormap identifier, e.g. ``"viridis"``.

    Returns
    -------
    numpy.ndarray or None
    """
    if not name:
        return None
    try:
        from chisurf.gui.chiplot.style import colormap

        cmap = colormap.get(name)
        lut = cmap.getLookupTable(nPts=256)
        arr = np.asarray(lut, dtype=np.uint8)
        if arr.ndim == 2 and arr.shape[1] >= 3:
            return arr[:, :3]
    except Exception:
        pass
    try:
        import matplotlib.cm as mpl_cm

        cmap = mpl_cm.get_cmap(name, 256)
        arr = (np.asarray([cmap(i / 255.0) for i in range(256)])[:, :3] * 255).astype(np.uint8)
        return arr
    except Exception:
        return None


@dataclass
class ValueColorScheme:
    """Policy for value-scaled cell backgrounds.

    Parameters
    ----------
    enabled : bool
        Master switch. Off by default — the plain table is the quiet default and
        colouring is a deliberate act.
    colormap : str
        Colormap name. Empty selects the built-in HSV ramp, which needs no
        plotting backend.
    scope : str
        ``"column"`` scales each column against its own range;
        ``"global"`` scales every numeric column against one shared range.
    alpha : float
        Background alpha, kept low enough that cell text stays readable in both
        light and dark palettes.
    max_cells : int
        Row × column product above which colouring disables itself.
    """

    enabled: bool = False
    colormap: str = ""
    scope: str = "column"
    alpha: float = 0.55
    max_cells: int = DEFAULT_MAX_CELLS

    def __post_init__(self) -> None:
        """Initialise the lazily-resolved lookup-table cache."""
        self._lut: np.ndarray | None = None
        self._lut_name: str | None = None

    def lut(self) -> np.ndarray | None:
        """Return the resolved lookup table for :attr:`colormap`.

        Returns
        -------
        numpy.ndarray or None
            ``None`` when the built-in HSV ramp should be used.
        """
        if self._lut_name != self.colormap:
            self._lut_name = self.colormap
            self._lut = resolve_lut(self.colormap)
        return self._lut

    def affordable(self, n_rows: int, n_cols: int) -> bool:
        """Return whether a table of this size may be coloured.

        Parameters
        ----------
        n_rows : int
            Number of rows.
        n_cols : int
            Number of columns.

        Returns
        -------
        bool
        """
        return int(n_rows) * int(n_cols) <= int(self.max_cells)

    def color(self, value: float, vmin: float, vmax: float) -> QtGui.QColor | None:
        """Return the background colour for one numeric value.

        Parameters
        ----------
        value : float
            The cell's value.
        vmin : float
            Range minimum.
        vmax : float
            Range maximum.

        Returns
        -------
        qtpy.QtGui.QColor or None
            ``None`` for non-finite values or an unusable range, so the cell
            keeps the palette default.
        """
        try:
            v = float(value)
        except (TypeError, ValueError):
            return None
        if not np.isfinite(v) or vmin is None or vmax is None:
            return None
        if not np.isfinite(vmin) or not np.isfinite(vmax):
            return None
        if vmax == vmin:
            # Degenerate range: nudge the minimum so every cell lands mid-ramp
            # instead of dividing by zero.
            vmin = vmin - 1.0
        span = vmax - vmin
        lut = self.lut()
        if lut is not None:
            return _lut_color(lut, (v - vmin) / span, self.alpha)
        return _hsv_color((vmax - v) / span, self.alpha)
