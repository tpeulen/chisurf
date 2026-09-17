"""Small plots drawn into rich-HTML tooltips (curve previews).

Item views that list curves — the dataset list, the IRF/background/linearization
selectors, the fit list — show on hover the full file name and, below it, a
thumbnail of the curve itself. The thumbnails are painted with ``QPainter`` into a
``QPixmap`` and embedded as a base64 ``<img>``, which needs neither a display nor
a plotting backend and therefore renders headlessly and is unit-testable.

The building blocks are:

* :func:`render_series_thumbnail` — the shared renderer; draws one or more
  ``(x, y, color)`` series with axes and x ticks.
* :func:`render_curve_thumbnail` — one curve, with automatic log/linear y.
* :func:`curve_tooltip_html` — the composed tooltip: bold title (the file name)
  above, curve below.
* :class:`TooltipItem` / :class:`TooltipTreeItem` — table/tree items that build
  their HTML tooltip lazily on first hover and cache it, so listing many curves
  costs nothing until the user actually hovers one.

Whether the thumbnail is drawn at all (and how large) is configured in the
ChiSurf settings YAML under ``gui.tooltip.curve_preview`` and read through
:func:`chisurf.gui.tooltip.curve_preview_config`; with the preview disabled the
tooltip falls back to the plain title text.
"""

from __future__ import annotations

import html
import math
import typing

import numpy as np
from qtpy import QtCore, QtGui, QtWidgets

#: Default series colours (data, secondary, tertiary) used when none is given.
DEFAULT_COLORS = ("#ffa629", "#4284f5", "#d400cd")

#: Points beyond which a series is min/max decimated before painting.
_MAX_POINTS = 600


class TooltipItem(QtWidgets.QTableWidgetItem):
    """Table widget item that lazily renders an HTML tooltip on first hover.

    Parameters
    ----------
    name : str
        Display text for the cell.
    key : object
        Opaque key passed to *render_fn* (e.g. a probe id, row id, path).
    render_fn : callable or None
        ``callable(key) -> str`` returning an HTML snippet (typically a
        base64-encoded PNG). Called once and cached.
    """

    def __init__(self, name: str, key, render_fn=None):
        super().__init__(name)
        self._key = key
        self._render_fn = render_fn
        self._cached_html = None

    def data(self, role):
        """Return the cell data; lazily build and cache the tooltip HTML."""
        if role == QtCore.Qt.ToolTipRole:
            if self._cached_html is None and self._render_fn is not None:
                try:
                    html_text = self._render_fn(self._key) or ""
                except Exception:
                    html_text = ""
                self._cached_html = html_text
            return self._cached_html
        return super().data(role)


class TooltipTreeItem(QtWidgets.QTreeWidgetItem):
    """Tree widget item whose tooltip is built on first hover and then cached.

    The tree counterpart of :class:`TooltipItem`. Rendering a curve thumbnail is
    far too expensive to do for every row while populating a list, so the item
    stores the key and calls *render_fn* only when Qt asks for the tooltip.

    Parameters
    ----------
    parent : QtWidgets.QTreeWidget or QtWidgets.QTreeWidgetItem
        Parent view or parent item.
    strings : list of str
        Column texts.
    key : object
        Opaque key passed to *render_fn* (e.g. the dataset object).
    render_fn : callable or None
        ``callable(key) -> str`` returning the tooltip (HTML or plain text).
    columns : iterable of int
        Columns the tooltip is shown for. Defaults to ``(1,)`` — the name column
        of the curve/fit lists.
    """

    def __init__(self, parent, strings, key, render_fn=None, columns=(1,)):
        super().__init__(parent, list(strings))
        self._key = key
        self._render_fn = render_fn
        self._columns = tuple(columns)
        self._cached_html: str | None = None

    def data(self, column: int, role: int):
        """Return the column data; lazily build and cache the tooltip HTML."""
        if role == QtCore.Qt.ToolTipRole and column in self._columns:
            if self._cached_html is None and self._render_fn is not None:
                try:
                    self._cached_html = self._render_fn(self._key) or ""
                except Exception:
                    self._cached_html = ""
            if self._cached_html is not None:
                return self._cached_html
        return super().data(column, role)


class TooltipListItem(QtWidgets.QListWidgetItem):
    """List widget item whose tooltip is built on first hover and then cached.

    Parameters
    ----------
    text : str
        Display text.
    key : object
        Opaque key passed to *render_fn*.
    render_fn : callable or None
        ``callable(key) -> str`` returning the tooltip (HTML or plain text).
    """

    def __init__(self, text: str, key, render_fn=None):
        super().__init__(text)
        self._key = key
        self._render_fn = render_fn
        self._cached_html: str | None = None

    def data(self, role: int):
        """Return the item data; lazily build and cache the tooltip HTML."""
        if role == QtCore.Qt.ToolTipRole:
            if self._cached_html is None and self._render_fn is not None:
                try:
                    self._cached_html = self._render_fn(self._key) or ""
                except Exception:
                    self._cached_html = ""
            return self._cached_html
        return super().data(role)


class TooltipStandardItem(QtGui.QStandardItem):
    """Model item with a lazy tooltip, for combo boxes and generic item views.

    A combo box populated with :meth:`QtWidgets.QComboBox.addItem` cannot carry a
    lazy tooltip; appending these items to its :class:`QStandardItemModel` can.

    Parameters
    ----------
    text : str
        Display text.
    key : object
        Opaque key passed to *render_fn*.
    render_fn : callable or None
        ``callable(key) -> str`` returning the tooltip (HTML or plain text).
    """

    def __init__(self, text: str, key, render_fn=None):
        super().__init__(text)
        self._key = key
        self._render_fn = render_fn
        self._cached_html: str | None = None

    def data(self, role: int = QtCore.Qt.UserRole + 1):
        """Return the item data; lazily build and cache the tooltip HTML."""
        if role == QtCore.Qt.ToolTipRole:
            if self._cached_html is None and self._render_fn is not None:
                try:
                    self._cached_html = self._render_fn(self._key) or ""
                except Exception:
                    self._cached_html = ""
            return self._cached_html
        return super().data(role)


def _decimate(x: np.ndarray, y: np.ndarray, n_out: int = _MAX_POINTS):
    """Reduce a series to at most *n_out* points, keeping per-bucket min/max.

    Plain striding would drop narrow peaks (a TCSPC rise, a burst spike); taking
    the extrema of each bucket keeps the visual envelope of the curve.
    """
    n = x.size
    if n <= n_out:
        return x, y
    edges = np.linspace(0, n, max(2, n_out // 2) + 1).astype(int)
    idx: list[int] = []
    for a, b in zip(edges[:-1], edges[1:]):
        if b <= a:
            continue
        seg = y[a:b]
        i_lo = a + int(np.argmin(seg))
        i_hi = a + int(np.argmax(seg))
        idx.extend(sorted((i_lo, i_hi)) if i_lo != i_hi else (i_lo,))
    take = np.asarray(sorted(set(idx)), dtype=int)
    return x[take], y[take]


def _nice_ticks(x_min: float, x_max: float, n: int = 4) -> list[float]:
    """Return up to ``n + 1`` "nice" (1/2/5·10ᵏ) tick positions in ``[x_min, x_max]``."""
    span = float(x_max) - float(x_min)
    if not np.isfinite(span) or span <= 0:
        return [float(x_min)]
    raw = span / max(1, n)
    mag = 10.0 ** math.floor(math.log10(raw))
    step = mag * 10.0
    for m in (1.0, 2.0, 5.0):
        if raw <= m * mag:
            step = m * mag
            break
    start = math.ceil(x_min / step) * step
    ticks: list[float] = []
    v = start
    while v <= x_max + 1e-9 * span:
        ticks.append(v)
        v += step
    return ticks


def _format_tick(value: float, step: float) -> str:
    """Format a tick label with just enough decimals for the tick spacing."""
    if step >= 1:
        return f"{value:.0f}"
    decimals = min(4, max(1, int(math.ceil(-math.log10(step)))))
    return f"{value:.{decimals}f}"


def _pixmap_to_html(pixmap: QtGui.QPixmap) -> str:
    """Encode a pixmap as an HTML ``<img>`` tag with an inline base64 PNG."""
    ba = QtCore.QByteArray()
    buf = QtCore.QBuffer(ba)
    buf.open(QtCore.QIODevice.WriteOnly)
    pixmap.save(buf, "PNG")
    buf.close()
    b64 = ba.toBase64().data().decode()
    return (
        f'<img src="data:image/png;base64,{b64}" '
        f'width="{pixmap.width()}" height="{pixmap.height()}">'
    )


def render_series_thumbnail(
    series: typing.Iterable[tuple[typing.Any, typing.Any, str]],
    *,
    width: int = 300,
    height: int = 140,
    x_tick_step: float = None,
    log_y: bool = False,
    share_y: bool = False,
    caption: str = None,
) -> str:
    """Render one or more ``(x, y, color)`` series as an HTML ``<img>`` thumbnail.

    Every series is normalized to its own maximum, so curves of very different
    magnitude (an IRF and a decay, absorption and emission spectra) stay
    comparable in shape. Series that must be compared quantitatively — data and
    the model fitted to it — are drawn with ``share_y=True`` instead.

    Parameters
    ----------
    series : iterable of (array-like, array-like, str)
        The ``(x, y, color)`` triples to draw. Non-finite samples are dropped.
    width, height : int
        Thumbnail size in pixels.
    x_tick_step : float, optional
        Fixed tick spacing on the x-axis; by default "nice" ticks are computed.
    log_y : bool
        Draw the y-axis logarithmically (non-positive samples are clipped to
        1e-6 of the series maximum).
    share_y : bool
        Scale all series with one common y range instead of individually.
    caption : str, optional
        Short text drawn in the top-right corner (e.g. the y-axis scaling).

    Returns
    -------
    str
        An ``<img src="data:image/png;base64,...">`` tag, or ``""`` when there is
        nothing to draw.
    """
    cleaned: list[tuple[np.ndarray, np.ndarray, str]] = []
    for i, item in enumerate(series):
        x, y, color = item
        x = np.asarray(x, dtype=float).ravel()
        y = np.asarray(y, dtype=float).ravel()
        n = min(x.size, y.size)
        if n < 2:
            continue
        x, y = x[:n], y[:n]
        ok = np.isfinite(x) & np.isfinite(y)
        if ok.sum() < 2:
            continue
        x, y = _decimate(x[ok], y[ok])
        cleaned.append((x, y, color or DEFAULT_COLORS[i % len(DEFAULT_COLORS)]))
    if not cleaned:
        return ""

    x_min = min(float(x.min()) for x, _, _ in cleaned)
    x_max = max(float(x.max()) for x, _, _ in cleaned)
    if not np.isfinite(x_min) or not np.isfinite(x_max) or x_max <= x_min:
        x_max = x_min + 1.0

    pixmap = QtGui.QPixmap(width, height)
    pixmap.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pixmap)
    try:
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        ml, mr, mt, mb = 10, 10, 6, 16
        pw = width - ml - mr
        ph = height - mt - mb

        def to_px_x(v):
            return ml + (v - x_min) / (x_max - x_min) * pw

        painter.setPen(QtGui.QPen(QtGui.QColor("#888")))
        painter.drawLine(ml, mt, ml, height - mb)
        painter.drawLine(ml, height - mb, width - mr, height - mb)

        common: tuple[float, float] = None
        if share_y:
            common = (
                min(float(np.min(y)) for _, y, _ in cleaned),
                max(float(np.max(y)) for _, y, _ in cleaned),
            )
        for x, y, color in cleaned:
            if log_y:
                y_max = common[1] if common else float(np.max(y))
                if y_max <= 0:
                    continue
                floor = y_max * 1e-6
                scaled = np.log10(np.clip(y, floor, None) / floor) / 6.0
            else:
                y_lo, y_hi = common if common else (float(np.min(y)), float(np.max(y)))
                y_lo = min(y_lo, 0.0)
                span = y_hi - y_lo
                if span <= 0:
                    span = 1.0
                scaled = (y - y_lo) / span
            points = [
                QtCore.QPointF(to_px_x(xi), height - mb - float(si) * ph)
                for xi, si in zip(x, scaled)
            ]
            painter.setPen(QtGui.QPen(QtGui.QColor(color), 1.3))
            painter.drawPolyline(QtGui.QPolygonF(points))

        font = painter.font()
        font.setPointSize(7)
        painter.setFont(font)
        painter.setPen(QtGui.QPen(QtGui.QColor("#aaa")))
        if x_tick_step:
            start = math.ceil(x_min / x_tick_step) * x_tick_step
            ticks = list(np.arange(start, x_max + 1e-9, x_tick_step))
            step = x_tick_step
        else:
            ticks = _nice_ticks(x_min, x_max)
            step = ticks[1] - ticks[0] if len(ticks) > 1 else (x_max - x_min)
        for tick in ticks:
            if tick < x_min or tick > x_max:
                continue
            px = int(to_px_x(tick))
            painter.drawLine(px, height - mb, px, height - mb + 3)
            text = _format_tick(float(tick), float(step))
            rect = painter.boundingRect(QtCore.QRect(0, 0, 0, 0), QtCore.Qt.AlignCenter, text)
            painter.drawText(px - rect.width() // 2, height - 3, text)
        if caption:
            rect = painter.boundingRect(QtCore.QRect(0, 0, 0, 0), QtCore.Qt.AlignCenter, caption)
            painter.drawText(width - mr - rect.width(), mt + rect.height() - 2, caption)
    finally:
        painter.end()

    return _pixmap_to_html(pixmap)


def _prefers_log(y) -> bool:
    """Return whether *y* is better shown logarithmically (spans ≥ 2 decades).

    A TCSPC decay drops by three or four decades; drawn linearly in a 140 px tall
    thumbnail everything but the peak collapses onto the baseline.
    """
    arr = np.asarray(y, dtype=float).ravel()
    finite = arr[np.isfinite(arr)]
    positive = finite[finite > 0]
    return bool(positive.size > 1 and positive.max() / positive.min() >= 100)


def render_curve_thumbnail(
    x, y, *, width: int = 300, height: int = 140, color: str = DEFAULT_COLORS[0], log_y: bool = None
) -> str:
    """Render a single ``(x, y)`` curve as an HTML ``<img>`` thumbnail.

    Parameters
    ----------
    x, y : array-like
        The curve samples.
    width, height : int
        Thumbnail size in pixels.
    color : str
        Line colour.
    log_y : bool, optional
        Force log/linear y. By default a logarithmic axis is chosen when the
        positive samples span at least two decades — which is what makes a TCSPC
        decay readable in a 140 px tall image.

    Returns
    -------
    str
        An ``<img ...>`` tag, or ``""`` when the curve cannot be drawn.
    """
    if log_y is None:
        log_y = _prefers_log(y)
    return render_series_thumbnail(
        [(x, y, color)],
        width=width,
        height=height,
        log_y=log_y,
        caption="log" if log_y else None,
    )


def curve_tooltip_html(title: str, x=None, y=None, *, wrap: bool = True) -> str:
    """Compose the standard curve tooltip: bold *title* above, curve below.

    The title (typically the full file name) is word-folded with the app-wide
    tooltip wrapper so long paths do not render as one very wide line. When the
    curve preview is disabled in the settings, or the curve cannot be drawn, the
    plain (non-HTML) title is returned so the tooltip still shows the file name.

    Parameters
    ----------
    title : str
        Tooltip heading, usually the full file name of the dataset.
    x, y : array-like, optional
        Curve samples to draw below the title.
    wrap : bool
        Fold the title to the configured tooltip width.

    Returns
    -------
    str
        Rich-text tooltip HTML, or plain text when no plot is drawn.
    """
    from chisurf.gui.tooltip import curve_preview_config, wrap_tooltip

    title = str(title or "")
    folded = wrap_tooltip(title) if wrap else title

    cfg = curve_preview_config()
    img = ""
    if cfg["enabled"] and x is not None and y is not None:
        try:
            img = render_curve_thumbnail(x, y, width=cfg["width"], height=cfg["height"])
        except Exception:
            img = ""
    if not img:
        return folded
    heading = html.escape(folded).replace("\n", "<br>")
    return f"<b>{heading}</b><br>{img}"


def curve_of(obj) -> tuple[typing.Any, typing.Any]:
    """Return ``(x, y)`` of a dataset/curve object, or ``(None, None)``.

    Accepts anything exposing ``x``/``y`` arrays (:class:`~chisurf.core.curve.Curve`,
    :class:`~chisurf.core.data.DataCurve`) and curve groups/lists, in which case
    the first member that has data is used.

    Parameters
    ----------
    obj : object
        Dataset, curve, or group of curves.
    """
    if obj is None:
        return None, None
    x = getattr(obj, "x", None)
    y = getattr(obj, "y", None)
    if x is not None and y is not None:
        try:
            if len(x) > 1 and len(y) > 1:
                return x, y
        except TypeError:
            return None, None
    if isinstance(obj, (list, tuple)):
        for member in obj:
            mx, my = curve_of(member)
            if mx is not None:
                return mx, my
    return None, None


def dataset_tooltip_html(dataset, title: str = None) -> str:
    """Return the hover tooltip for a dataset: file name plus a curve preview.

    Parameters
    ----------
    dataset : object
        The dataset (curve, data curve, or group) shown in the row.
    title : str, optional
        Heading; by default the dataset's file name (falling back to its name).
    """
    if title is None:
        title = dataset_title(dataset)
    x, y = curve_of(dataset)
    return curve_tooltip_html(title, x, y)


def plot_color(name: str, default: str) -> str:
    """Return a colour from ``gui.plot.colors`` in the settings (or *default*).

    Tooltip previews use the same data/model/IRF colours as the real plots so a
    hovered thumbnail is recognizable next to the fit window.
    """
    try:
        from chisurf.core.settings import cs_settings

        colors = cs_settings.get("gui", {}).get("plot", {}).get("colors", {})
        return str(colors.get(name, default))
    except Exception:
        return default


def fit_tooltip_html(fit, title: str = None) -> str:
    """Return the hover tooltip for a fit: its name plus data and model curves.

    Parameters
    ----------
    fit : object
        A fit exposing ``data`` and (optionally) ``model`` curves.
    title : str, optional
        Heading; by default the fit's name.

    Returns
    -------
    str
        Rich-text tooltip HTML, or the plain title when nothing can be drawn.
    """
    from chisurf.gui.tooltip import curve_preview_config, wrap_tooltip

    if title is None:
        title = str(getattr(fit, "name", "") or "")
    folded = wrap_tooltip(title)
    cfg = curve_preview_config()
    if not cfg["enabled"]:
        return folded

    series = []
    data_x, data_y = curve_of(getattr(fit, "data", None))
    if data_x is not None:
        series.append((data_x, data_y, plot_color("data", DEFAULT_COLORS[0])))
    model_x, model_y = curve_of(getattr(fit, "model", None))
    if model_x is not None:
        series.append((model_x, model_y, plot_color("model", DEFAULT_COLORS[2])))
    if not series:
        return folded

    log_y = _prefers_log(series[0][1])
    try:
        img = render_series_thumbnail(
            series,
            width=cfg["width"],
            height=cfg["height"],
            log_y=log_y,
            share_y=True,
            caption="log" if log_y else None,
        )
    except Exception:
        img = ""
    if not img:
        return folded
    heading = html.escape(folded).replace("\n", "<br>")
    return f"<b>{heading}</b><br>{img}"


def dataset_title(dataset) -> str:
    """Return the best available full name of a dataset for a tooltip heading.

    Prefers the file name recorded in the metadata, then ``filename``, then the
    dataset name — placeholders such as ``"None"``/``"No file"`` are skipped.
    """
    meta = getattr(dataset, "meta_data", None)
    if isinstance(meta, dict) and meta.get("filename"):
        return str(meta["filename"])
    filename = str(getattr(dataset, "filename", "") or "")
    if filename and filename not in ("None", "No file"):
        return filename
    return str(getattr(dataset, "name", "") or "")
