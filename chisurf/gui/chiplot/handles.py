"""Handle protocols — the contract a chiplot backend must satisfy.

A *handle* is the object returned when something is drawn on a :class:`Plot`
(a curve, a scatter cloud, a draggable region, a marker line, …). Callers keep
the handle to update or remove that element later.

These are :class:`typing.Protocol` classes: they document the behaviour every
backend's concrete handles must provide, without forcing inheritance. The
pyqtgraph backend returns thin wrappers around pyqtgraph items that conform to
these protocols; a future OpenGL backend returns its own conforming objects.

The protocols are deliberately small and verb-oriented (``set_data``,
``remove``, ``value``) rather than mirroring pyqtgraph's item API, so the
contract is renderer-agnostic.
"""

from __future__ import annotations

from enum import Enum
from typing import Protocol, runtime_checkable

import numpy as np


class Symbol(Enum):
    """Scatter marker shape."""

    CIRCLE = "o"
    SQUARE = "s"
    TRIANGLE = "t"
    DIAMOND = "d"
    PLUS = "+"
    CROSS = "x"
    STAR = "star"


class Orientation(Enum):
    """Orientation of a region or marker line."""

    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"


@runtime_checkable
class Handle(Protocol):
    """Common behaviour of every drawn element."""

    @property
    def visible(self) -> bool:
        """Whether the element is currently drawn."""
        ...

    @visible.setter
    def visible(self, value: bool) -> None: ...

    @property
    def z(self) -> float:
        """Stacking order; higher draws on top."""
        ...

    @z.setter
    def z(self, value: float) -> None: ...

    def hide(self) -> None:
        """Hide the element (convenience for ``visible = False``)."""
        ...

    def show(self) -> None:
        """Show the element (convenience for ``visible = True``)."""
        ...

    def remove(self) -> None:
        """Remove the element from its plot."""
        ...

    @property
    def native(self):
        """The backend-specific object (escape hatch; avoid in new code)."""
        ...


@runtime_checkable
class Curve(Handle, Protocol):
    """A line / step / filled curve."""

    def set_data(self, x: np.ndarray, y: np.ndarray) -> None:
        """Replace the curve's samples.

        Parameters
        ----------
        x, y : numpy.ndarray
            New coordinates.
        """
        ...

    def get_data(self) -> tuple[np.ndarray, np.ndarray]:
        """Return the curve's current ``(x, y)`` samples.

        Returns
        -------
        tuple of numpy.ndarray
        """
        ...

    def set_pen(self, pen) -> None:
        """Restyle the curve's line.

        Parameters
        ----------
        pen : pen-like
            A colour/style spec or :class:`style.Pen` (coerced via ``to_pen``).
        """
        ...

    def set_symbol(self, symbol) -> None:
        """Set (or clear with ``None``) a per-point marker on the curve.

        Parameters
        ----------
        symbol : str, Symbol, or None
            Marker shape (``"o"``, ``"s"``, …); ``None`` removes markers.
        """
        ...

    def set_symbol_size(self, size: float) -> None:
        """Set the per-point marker size in pixels.

        Parameters
        ----------
        size : float
            Marker diameter in pixels.
        """
        ...

    def set_symbol_brush(self, brush) -> None:
        """Set the per-point marker fill.

        Parameters
        ----------
        brush : brush-like
            Marker fill colour or :class:`style.Brush`.
        """
        ...

    def set_opacity(self, alpha: float) -> None:
        """Set the whole-curve opacity.

        Parameters
        ----------
        alpha : float
            Opacity in ``0.0`` (transparent) .. ``1.0`` (opaque).
        """
        ...


@runtime_checkable
class Scatter(Handle, Protocol):
    """A cloud of point markers."""

    def set_data(self, x: np.ndarray, y: np.ndarray) -> None:
        """Replace the scatter positions.

        Parameters
        ----------
        x, y : numpy.ndarray
            New point coordinates.
        """
        ...

    def get_data(self) -> tuple[np.ndarray, np.ndarray]:
        """Return the scatter's current ``(x, y)`` positions.

        Returns
        -------
        tuple of numpy.ndarray
        """
        ...


@runtime_checkable
class Bars(Handle, Protocol):
    """A bar graph."""

    def set_data(self, x: np.ndarray, height: np.ndarray) -> None:
        """Replace the bar positions/heights.

        Parameters
        ----------
        x : numpy.ndarray
            Bar center x-coordinates.
        height : numpy.ndarray
            Bar heights.
        """
        ...


@runtime_checkable
class ErrorBars(Handle, Protocol):
    """Symmetric or asymmetric error bars."""

    def set_data(
        self,
        x: np.ndarray,
        y: np.ndarray,
        *,
        height: np.ndarray | None = None,
        top: np.ndarray | None = None,
        bottom: np.ndarray | None = None,
    ) -> None:
        """Replace error-bar geometry.

        Parameters
        ----------
        x, y : numpy.ndarray
            Bar anchor positions.
        height : numpy.ndarray, optional
            Total (symmetric) bar height; mutually exclusive with
            ``top``/``bottom``.
        top, bottom : numpy.ndarray, optional
            Asymmetric extents above/below each point.
        """
        ...


@runtime_checkable
class Image(Handle, Protocol):
    """A 2-D image / heatmap."""

    def set_image(
        self,
        data: np.ndarray,
        *,
        levels: tuple[float, float] | None = None,
    ) -> None:
        """Replace the image data.

        Parameters
        ----------
        data : numpy.ndarray
            2-D (grayscale) or 3-D (RGB/RGBA) array.
        levels : tuple of float, optional
            ``(min, max)`` mapped to the colormap ends; autoscaled if ``None``.
        """
        ...

    def set_levels(self, low: float, high: float) -> None:
        """Set the intensity range mapped to the colormap ends.

        Distinct from ``set_image(..., levels=…)``: a contrast control restyles
        the *same* data, so re-uploading the array only to change the window is
        wasted work on a large image.

        Parameters
        ----------
        low, high : float
            Intensity values mapped to the first and last colormap entry.
        """
        ...

    def set_colormap(self, colormap) -> None:
        """Recolour an image already on the canvas.

        Parameters
        ----------
        colormap : str, style.Colormap or None
            Colormap name or reference; ``None`` restores the grayscale ramp.
        """
        ...

    def set_rect(self, x: float, y: float, w: float, h: float) -> None:
        """Place the image in data coordinates.

        Parameters
        ----------
        x, y : float
            Lower-left corner.
        w, h : float
            Width and height in data units.
        """
        ...

    def clear(self) -> None:
        """Clear the image data."""
        ...


@runtime_checkable
class ColorBar(Handle, Protocol):
    """A colour bar with interactive level handles, bound to an image."""

    def set_colormap(self, colormap) -> None:
        """Apply a colormap to the bar and the image it drives.

        Parameters
        ----------
        colormap : colormap-like
            Name or :class:`~chisurf.gui.chiplot.style.Colormap`; ``None`` keeps
            the current one.
        """
        ...

    def set_levels(self, low: float, high: float) -> None:
        """Set the intensity range mapped onto the colormap.

        Parameters
        ----------
        low, high : float
            Intensities mapped to the colormap ends.
        """
        ...

    def get_levels(self) -> tuple[float, float]:
        """Return the mapped ``(low, high)`` intensity range."""
        ...

    def on_levels_changed(self, callback) -> None:
        """Register ``callback(low, high)`` for user level changes.

        Parameters
        ----------
        callback : callable
            Called with the new ``(low, high)`` when the user drags the handles.
        """
        ...


@runtime_checkable
class Region(Handle, Protocol):
    """A draggable interval selector (vertical or horizontal band)."""

    @property
    def bounds(self) -> tuple[float, float]:
        """The ``(low, high)`` edges of the region in data coordinates."""
        ...

    # Mutation is a method, not a ``bounds`` property setter, on purpose: the
    # repo's forbidden-communication guard reserves assignment to a ``bounds``
    # attribute for fit-parameter mutations. Do not re-add a property setter.
    def set_bounds(self, low: float, high: float) -> None:
        """Move the region to new ``(low, high)`` edges.

        Parameters
        ----------
        low, high : float
            New edges in data coordinates.
        """
        ...

    def set_limits(self, low: float, high: float) -> None:
        """Constrain how far the region can be dragged (its allowed range).

        This bounds *where the region may go*, not its current position (that is
        :meth:`set_bounds`). Programmatic; blocks the native item's signals so it
        never re-enters an :meth:`on_change` drag callback.

        Parameters
        ----------
        low, high : float
            Minimum and maximum draggable edges in data coordinates.
        """
        ...

    def on_change(self, callback, *, final: bool = True) -> None:
        """Register a callback fired when the user drags the region.

        Parameters
        ----------
        callback : callable
            Called with ``(low, high)`` when the region moves.
        final : bool
            If ``True`` fire only when dragging finishes; if ``False`` fire
            continuously while dragging.
        """
        ...


@runtime_checkable
class Marker(Handle, Protocol):
    """A movable infinite line (vertical or horizontal cursor)."""

    @property
    def value(self) -> float:
        """The line position in data coordinates."""
        ...

    # Mutation is a method, not a ``value`` property setter, on purpose: the
    # repo's forbidden-communication guard reserves assignment to a ``value``
    # attribute for fit-parameter mutations. Do not re-add a property setter.
    def set_value(self, value: float) -> None:
        """Move the marker to a new position.

        Parameters
        ----------
        value : float
            New position in data coordinates.
        """
        ...

    def on_change(self, callback, *, final: bool = True) -> None:
        """Register a callback fired when the user drags the marker.

        Parameters
        ----------
        callback : callable
            Called with the new position when the marker moves.
        final : bool
            If ``True`` fire only when dragging finishes; else continuously.
        """
        ...


@runtime_checkable
class Roi(Handle, Protocol):
    """A draggable/resizable region of interest over an image.

    Rectangle, circle, ellipse or polygon. The first three are described by
    :attr:`pos` and :attr:`size`; a polygon by :attr:`points`, which the others
    also answer (with their corners) so a caller need not branch on the kind.
    """

    @property
    def pos(self) -> tuple[float, float]:
        """The ``(x, y)`` lower-left corner in image coordinates."""
        ...

    @property
    def size(self) -> tuple[float, float]:
        """The ``(w, h)`` size in image coordinates."""
        ...

    @property
    def points(self) -> list[tuple[float, float]]:
        """The vertices in image coordinates.

        For a polygon these are its handles, mapped out of the ROI's own frame
        so they stay correct after the whole shape is dragged. For the box-like
        kinds they are the four corners.
        """
        ...

    def set_pos(self, x: float, y: float) -> None:
        """Move the ROI's lower-left corner.

        Parameters
        ----------
        x, y : float
            New corner position in image coordinates.
        """
        ...

    def set_size(self, w: float, h: float) -> None:
        """Resize the ROI.

        Parameters
        ----------
        w, h : float
            New width and height in image coordinates.
        """
        ...

    def set_pen(self, pen, **overrides) -> None:
        """Restyle the ROI's outline.

        Parameters
        ----------
        pen : pen-like
            A colour/style spec or :class:`style.Pen`.
        **overrides
            ``width``, ``style``, … applied on top (see ``style.to_pen``).
        """
        ...

    def on_change(self, callback, *, final: bool = True) -> None:
        """Register a no-argument callback fired when the ROI is dragged/resized.

        Parameters
        ----------
        callback : callable
            Called (no args) when the ROI geometry changes; query
            :attr:`pos`/:attr:`size` inside it.
        final : bool
            If ``True`` fire only when the drag finishes; else continuously.
        """
        ...


@runtime_checkable
class Arrow(Handle, Protocol):
    """A scale-invariant arrow head placed at a data coordinate.

    The arrow's tip sits at :attr:`position` and it points along
    :attr:`angle` — degrees counter-clockwise from the ``+x`` axis, the same
    convention as :func:`numpy.arctan2` on ``(dy, dx)``. Drawing a directed
    edge is therefore ``plot.arrow(x1, y1, angle=degrees(arctan2(dy, dx)))``,
    with no renderer-specific sign flip at the call site.
    """

    @property
    def position(self) -> tuple[float, float]:
        """The ``(x, y)`` tip position in data coordinates."""
        ...

    @property
    def angle(self) -> float:
        """Pointing direction in degrees counter-clockwise from ``+x``."""
        ...

    def set_position(self, x: float, y: float) -> None:
        """Move the arrow tip.

        Parameters
        ----------
        x, y : float
            New tip position in data coordinates.
        """
        ...

    def set_angle(self, angle: float) -> None:
        """Re-aim the arrow.

        Parameters
        ----------
        angle : float
            New pointing direction, degrees counter-clockwise from ``+x``.
        """
        ...


@runtime_checkable
class Text(Handle, Protocol):
    """A text label anchored in data coordinates."""

    @property
    def text(self) -> str:
        """The displayed string."""
        ...

    @text.setter
    def text(self, value: str) -> None: ...

    def set_position(self, x: float, y: float) -> None:
        """Move the label.

        Parameters
        ----------
        x, y : float
            New anchor position in data coordinates.
        """
        ...
