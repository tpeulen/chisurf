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
