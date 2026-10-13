"""The reading column: how wide it is, how a figure is sized in it, and opened out of it.

A maximised help window is over a thousand pixels of text per line, about twice what is
comfortable to read, so the column is at most :data:`MAX_TEXT_WIDTH` wide and centred
(:func:`measure_margin`); in a narrow window the window *is* the column and only
:data:`MIN_GUTTER` is kept. The measure follows the window when it narrows: it is computed
every frame, never frozen at the width the page was first drawn at.

Two figure defects this covers, both carried over from the retired Qt viewer and both
invisible to a construction test:

* a plot narrower than the reading column was drawn at its own pixel size, so a 470-pixel
  figure sat in an 860-pixel measure looking like a thumbnail; :func:`figure_size` enlarges it
  to the column, but never past :data:`MAX_UPSCALE` times its own pixels (a raster figure is just
  soft beyond that) and never an inline image;
* there was no way to see a figure bigger than the column, which for a four-panel figure is
  not big enough to read the axes; :class:`FigureViewer` opens the file's own pixels, fitted,
  at 100 % or zoomed.

Toolkit-free: the viewer is drawn with emtk (``draw``) and tested through its state.
"""

from __future__ import annotations

import base64
import binascii
import logging
import pathlib

from emtk import im
from emtk.i18n import tr
from emtk.texture import Texture

_LOGGER = logging.getLogger(__name__)

#: Furthest a raster figure is enlarged to fill the column, as a multiple of its own pixels.
MAX_UPSCALE = 2.0
#: Zoom limits of the figure viewer.
MIN_ZOOM, MAX_ZOOM = 0.1, 8.0


#: Widest reading column, in logical pixels at zoom 1 (it grows with the reader's zoom).
MAX_TEXT_WIDTH = 860
#: Smallest gutter a page keeps, so text never touches the scrollbar.
MIN_GUTTER = 10


def measure_margin(available: float, maximum: float, minimum: float = MIN_GUTTER) -> float:
    """Return the gutter that holds a text column of *maximum* inside *available*.

    Parameters
    ----------
    available : float
        Reader width in pixels.
    maximum : float
        Widest text column to allow, in pixels.
    minimum : float, optional
        Gutter kept even when the reader is narrower than *maximum*.

    Returns
    -------
    float
        Margin to leave on each side.
    """
    return max(minimum, (available - maximum) // 2)


def figure_size(
    width: float,
    height: float,
    column: float,
    *,
    upscale: bool = True,
    max_upscale: float = MAX_UPSCALE,
    max_height: float | None = None,
) -> tuple[float, float]:
    """The size a figure of ``width x height`` is drawn at in a column *column* wide.

    Parameters
    ----------
    width, height : float
        The figure's own size in logical pixels.
    column : float
        Width of the reading column.
    upscale : bool, optional
        Enlarge a figure narrower than the column (a block figure); an inline image is never
        enlarged, because it would tower over the line it sits in.
    max_upscale : float, optional
        Largest enlargement, as a multiple of the figure's own size.
    max_height : float, optional
        Height cap; the width shrinks with it, keeping the aspect ratio.

    Returns
    -------
    tuple of float
        ``(w, h)``; never wider than *column*.
    """
    if width <= 0 or height <= 0 or column <= 0:
        return (max(0.0, float(width)), max(0.0, float(height)))
    ceiling = width * max_upscale if upscale else width
    w = min(ceiling, float(column))
    h = height * w / width
    if max_height is not None and h > max_height > 0:
        w *= max_height / h
        h = float(max_height)
    return (float(w), float(h))


def load_figure(name: str, base: pathlib.Path | None = None) -> Texture | None:
    """A texture for a figure reference: a file path or a ``data:image/...;base64,`` URI.

    Parameters
    ----------
    name : str
        The reference. A relative path is resolved against *base* first.
    base : pathlib.Path, optional
        Folder of the page that names it.

    Returns
    -------
    Texture or None
        ``None`` for an empty, missing or unreadable reference -- never an exception.
    """
    text = str(name or "").strip()
    if not text:
        return None
    if text.startswith("data:"):
        _header, _, payload = text.partition(",")
        try:
            return Texture.from_bytes(base64.b64decode(payload))
        except (binascii.Error, ValueError, OSError) as error:
            _LOGGER.debug("unreadable inline figure: %s", error)
            return None
        except Exception as error:  # PIL raises its own UnidentifiedImageError
            _LOGGER.debug("unreadable inline figure: %s", error)
            return None
    path = pathlib.Path(text)
    candidates = [path] if path.is_absolute() or base is None else [base / path, path]
    for candidate in candidates:
        if candidate.is_file():
            try:
                svg = candidate.suffix.lower() in (".svg", ".svgz")
                return Texture.from_file(candidate, svg_scale=2.0 if svg else 1.0)
            except Exception as error:
                _LOGGER.debug("unreadable figure %s: %s", candidate, error)
                return None
    return None


class FigureViewer:
    """A figure opened out of the page: the file's own pixels, fitted, at 100 % or zoomed.

    Parameters
    ----------
    texture : Texture
        The figure.
    title : str, optional
        Window title (the file name).
    scale : float, optional
        Logical pixels per texel (0.5 for an SVG rasterised at twice its size).

    Attributes
    ----------
    mode : str
        ``"fit"`` (the whole figure in the window) or ``"zoom"`` (:attr:`zoom_factor` times its
        own size; 1.0 is *Actual size*).
    """

    def __init__(self, texture: Texture, title: str = "", scale: float = 1.0) -> None:
        self.texture = texture
        self.title = title
        self.scale = float(scale)
        self.mode = "fit"
        self.zoom_factor = 1.0
        self.open = True
        self._fit_factor = 0.0

    @property
    def natural_size(self) -> tuple[float, float]:
        """The figure's own size in logical pixels."""
        return (self.texture.width * self.scale, self.texture.height * self.scale)

    def fit(self) -> None:
        """Show the whole figure in the window."""
        self.mode = "fit"

    def actual_size(self) -> None:
        """Show the figure at its own pixels."""
        self.mode, self.zoom_factor = "zoom", 1.0

    def zoom(self, factor: float) -> None:
        """Multiply the current magnification by *factor* (clamped)."""
        if self.mode == "fit":
            self.zoom_factor = self._fit_factor or 1.0
        self.mode = "zoom"
        self.zoom_factor = max(MIN_ZOOM, min(MAX_ZOOM, self.zoom_factor * float(factor)))

    def displayed_size(self, available: tuple[float, float]) -> tuple[float, float]:
        """The drawn size inside *available* ``(w, h)``."""
        w, h = self.natural_size
        if w <= 0 or h <= 0:
            return (0.0, 0.0)
        if self.mode == "fit":
            factor = min(available[0] / w, available[1] / h, MAX_UPSCALE)
            self._fit_factor = max(factor, 0.0)
            return (w * self._fit_factor, h * self._fit_factor)
        return (w * self.zoom_factor, h * self.zoom_factor)

    def draw(self, box: tuple[float, float, float, float]) -> None:
        """Draw the viewer's toolbar and the figure into *box* (a window's content region)."""
        if im.small_button(tr("Fit to window")):
            self.fit()
        im.set_item_tooltip(tr("Show the whole figure in the window"))
        im.same_line()
        if im.small_button(tr("Actual size")):
            self.actual_size()
        im.set_item_tooltip(tr("Show the figure at its own pixels (100 %)"))
        im.same_line()
        if im.small_button(tr("Zoom out")):
            self.zoom(1 / 1.25)
        im.set_item_tooltip(tr("Show the figure smaller"))
        im.same_line()
        if im.small_button(tr("Zoom in")):
            self.zoom(1.25)
        im.set_item_tooltip(tr("Show the figure larger"))
        im.same_line()
        w, h = self.natural_size
        im.text_disabled(f"{int(round(w))} × {int(round(h))} px")
        x, y = im.get_cursor_screen_pos()
        avail = (max(20.0, box[0] + box[2] - x), max(20.0, box[1] + box[3] - y))
        size = self.displayed_size(avail)
        im.begin_child((x, y, avail[0], avail[1]), child_id="figure_view")
        im.image(self.texture, size=size, align_center=size[0] < avail[0])
        im.end_child()
