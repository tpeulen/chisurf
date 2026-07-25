"""Abstract backend contract for chiplot.

A backend turns chiplot's renderer-neutral API into concrete drawing. It
supplies two widget-bearing objects — a single-panel :class:`Canvas` and a
multi-panel :class:`GridCanvas` — plus global configuration.

The public :class:`~chisurf.gui.chiplot.Plot` / :class:`~chisurf.gui.chiplot.Grid`
wrappers delegate to these. Concrete backends live alongside this module
(``pyqtgraph_backend`` today, an OpenGL backend later); only they may import a
third-party rendering library, so swapping backends never touches call sites.
"""

from __future__ import annotations

import abc

import numpy as np
from qtpy import QtWidgets

from chisurf.gui.chiplot import handles as H
from chisurf.gui.chiplot import style as S


class Canvas(abc.ABC):
    """A single plot panel: axes, a viewbox, and drawn handles.

    Subclasses implement drawing against a specific renderer and return objects
    conforming to the :mod:`chisurf.gui.chiplot.handles` protocols.
    """

    @abc.abstractmethod
    def widget(self) -> QtWidgets.QWidget:
        """Return the embeddable Qt widget for this panel."""

    # -- drawing ---------------------------------------------------------
    @abc.abstractmethod
    def add_curve(
        self,
        x: np.ndarray,
        y: np.ndarray,
        *,
        pen: S.Pen,
        name: str | None = None,
        fill: S.Brush | None = None,
        step: bool = False,
        symbol: H.Symbol | None = None,
        symbol_size: float = 7.0,
        symbol_brush: S.Brush | None = None,
        symbol_pen: S.Pen | None = None,
    ) -> H.Curve:
        """Draw a line/step curve (optionally with markers) and return its handle."""

    @abc.abstractmethod
    def add_scatter(
        self,
        x: np.ndarray,
        y: np.ndarray,
        *,
        size: float,
        pen: S.Pen | None,
        brush: S.Brush | None,
        symbol: H.Symbol,
        name: str | None = None,
    ) -> H.Scatter:
        """Draw a scatter cloud and return its handle."""

    @abc.abstractmethod
    def add_bars(
        self,
        x: np.ndarray,
        height: np.ndarray,
        *,
        width: float,
        pen: S.Pen | None,
        brush: S.Brush | None,
    ) -> H.Bars:
        """Draw a bar graph and return its handle."""

    @abc.abstractmethod
    def add_fill_between(
        self,
        lower: H.Curve,
        upper: H.Curve,
        *,
        brush: S.Brush,
    ) -> H.Handle:
        """Fill the area between two existing curve handles; return its handle."""

    @abc.abstractmethod
    def add_errorbars(
        self,
        x: np.ndarray,
        y: np.ndarray,
        *,
        height: np.ndarray | None,
        top: np.ndarray | None,
        bottom: np.ndarray | None,
        pen: S.Pen,
        beam: float | None = None,
    ) -> H.ErrorBars:
        """Draw error bars and return their handle."""

    @abc.abstractmethod
    def add_image(
        self,
        data: np.ndarray,
        *,
        colormap: S.Colormap | None,
        levels: tuple[float, float] | None,
        rect: tuple[float, float, float, float] | None,
        axis_order: str = "row-major",
    ) -> H.Image:
        """Draw an image/heatmap and return its handle."""

    @abc.abstractmethod
    def add_region(
        self,
        bounds: tuple[float, float],
        *,
        orientation: H.Orientation,
        movable: bool,
        brush: S.Brush | None,
        pen: S.Pen | None,
    ) -> H.Region:
        """Draw a draggable interval selector and return its handle."""

    @abc.abstractmethod
    def add_marker(
        self,
        pos: float,
        *,
        orientation: H.Orientation,
        movable: bool,
        pen: S.Pen,
        label: str | None,
    ) -> H.Marker:
        """Draw a movable cursor line and return its handle."""

    @abc.abstractmethod
    def add_text(
        self,
        text: str,
        pos: tuple[float, float],
        *,
        color: S.Color,
        anchor: tuple[float, float],
        draggable: bool,
    ) -> H.Text:
        """Draw a text label and return its handle."""

    @abc.abstractmethod
    def add_legend(self, *, offset: tuple[int, int]) -> None:
        """Enable a legend collecting named handles."""

    @abc.abstractmethod
    def readd(self, handle: H.Handle) -> None:
        """Re-attach a previously removed handle to this panel."""

    @abc.abstractmethod
    def remove(self, handle: H.Handle) -> None:
        """Remove a handle from this panel."""

    @abc.abstractmethod
    def clear(self) -> None:
        """Remove every handle from this panel."""

    # -- axes / view -----------------------------------------------------
    @abc.abstractmethod
    def set_labels(
        self,
        *,
        left: str | None = None,
        bottom: str | None = None,
        right: str | None = None,
        top: str | None = None,
    ) -> None:
        """Set axis labels (unset axes are left unchanged)."""

    @abc.abstractmethod
    def set_title(self, title: str | None) -> None:
        """Set the panel title."""

    @abc.abstractmethod
    def set_log(self, *, x: bool | None = None, y: bool | None = None) -> None:
        """Toggle logarithmic scaling per axis."""

    @abc.abstractmethod
    def set_range(
        self,
        *,
        x: tuple[float, float] | None = None,
        y: tuple[float, float] | None = None,
        padding: float | None = None,
    ) -> None:
        """Set visible x/y range."""

    @abc.abstractmethod
    def get_range(self) -> tuple[tuple[float, float], tuple[float, float]]:
        """Return the current ``((x0, x1), (y0, y1))`` visible range."""

    @abc.abstractmethod
    def auto_range(self) -> None:
        """Fit the view to its contents once."""

    @abc.abstractmethod
    def enable_auto_range(self, *, x: bool = True, y: bool = True) -> None:
        """Keep the view fitted to contents as data changes."""

    @abc.abstractmethod
    def set_grid(self, *, x: bool = False, y: bool = False, alpha: float = 0.3) -> None:
        """Toggle axis grid lines."""

    @abc.abstractmethod
    def set_background(self, color: S.Color | None) -> None:
        """Set the panel background color."""

    @abc.abstractmethod
    def set_aspect_locked(self, lock: bool, ratio: float = 1.0) -> None:
        """Lock the x/y pixel aspect ratio."""

    @abc.abstractmethod
    def invert_y(self, invert: bool = True) -> None:
        """Invert the y-axis direction."""

    def set_axis_visible(self, side: str, visible: bool) -> None:
        """Show or hide one axis (``"left"``/``"bottom"``/``"right"``/``"top"``).

        Default no-op; backends with axis chrome override it.
        """

    def set_menu_enabled(self, enabled: bool) -> None:
        """Enable/disable the backend's own right-click menu (default no-op)."""

    def set_interactive(self, *, mouse: bool = True, menu: bool = True) -> None:
        """Enable/disable mouse pan-zoom and the right-click menu (default no-op)."""

    def provides_native_menu(self) -> bool:
        """Whether the backend already shows its own rich right-click menu.

        When ``True`` (pyqtgraph), chiplot keeps that menu (export/CSV/image are
        already there) and only injects custom actions into it. When ``False``,
        chiplot builds its own menu.
        """
        return False

    def add_menu_action(self, label: str, callback) -> None:
        """Add a custom entry to the backend's native menu (default no-op)."""

    def export_image(self, path: str, *, width: int | None = None) -> bool:
        """Export the panel to an image file; return ``True`` on success.

        Backends without a native exporter return ``False`` so the caller can
        fall back to a widget grab.
        """
        return False

    # -- events ----------------------------------------------------------
    @abc.abstractmethod
    def on_click(self, callback) -> None:
        """Register ``callback(x, y, button)`` for clicks in data coordinates."""

    @abc.abstractmethod
    def on_mouse_move(self, callback) -> None:
        """Register ``callback(x, y)`` for pointer motion in data coordinates."""

    @property
    @abc.abstractmethod
    def native(self):
        """The backend-specific plot object (escape hatch; avoid in new code)."""


class GridCanvas(abc.ABC):
    """A grid of :class:`Canvas` panels sharing one widget."""

    @abc.abstractmethod
    def widget(self) -> QtWidgets.QWidget:
        """Return the embeddable Qt widget for the whole grid."""

    @abc.abstractmethod
    def add_panel(
        self,
        *,
        row: int | None = None,
        col: int | None = None,
        rowspan: int = 1,
        colspan: int = 1,
        title: str | None = None,
    ) -> Canvas:
        """Add and return a panel at the given grid cell."""

    @abc.abstractmethod
    def next_row(self) -> None:
        """Advance the implicit insertion cursor to the next row."""

    @property
    @abc.abstractmethod
    def native(self):
        """The backend-specific container object (escape hatch)."""


class ImageViewCanvas(abc.ABC):
    """An image viewer: image + intensity/LUT histogram + (3-D) frame slider.

    Wraps the renderer's composite image-view widget (pyqtgraph ``ImageView``
    today). Overlays and ROIs live on its internal view.
    """

    @abc.abstractmethod
    def widget(self) -> QtWidgets.QWidget:
        """Return the embeddable Qt widget."""

    @abc.abstractmethod
    def set_image(
        self,
        data: np.ndarray,
        *,
        auto_levels: bool = True,
        axes: dict | None = None,
    ) -> None:
        """Show an image or ``(t, y, x)`` stack (``axes`` maps dimensions)."""

    @abc.abstractmethod
    def set_colormap(self, name: str, source: str = "matplotlib") -> None:
        """Apply a named colormap to the image."""

    @abc.abstractmethod
    def clear(self) -> None:
        """Clear the image and overlays."""

    @abc.abstractmethod
    def set_histogram_width(self, width: int | None) -> None:
        """Constrain (or free, with ``None``) the LUT histogram panel width."""

    @abc.abstractmethod
    def set_interactive(self, *, mouse: bool = True, menu: bool = True) -> None:
        """Toggle view pan/zoom (``mouse``) and the right-click menu."""

    @abc.abstractmethod
    def add_overlay(
        self,
        data: np.ndarray,
        *,
        colormap: S.Colormap | None = None,
    ) -> H.Image:
        """Overlay a second image item on the view; return its handle."""

    @abc.abstractmethod
    def add_roi(
        self,
        *,
        kind: str = "rect",
        pos: tuple[float, float] = (0.0, 0.0),
        size: tuple[float, float] = (10.0, 10.0),
        pen: S.Pen,
        movable: bool = True,
        rotatable: bool = False,
    ) -> H.Roi:
        """Add a region-of-interest to the view; return its handle."""

    @abc.abstractmethod
    def on_click(self, callback) -> None:
        """Register ``callback(x, y)`` for clicks in image coordinates."""

    @property
    @abc.abstractmethod
    def native(self):
        """The backend-specific image-view object (escape hatch)."""


class Backend(abc.ABC):
    """Factory that produces canvases and applies global configuration."""

    name: str = "abstract"

    @abc.abstractmethod
    def create_canvas(self, **opts) -> Canvas:
        """Create a single-panel :class:`Canvas`."""

    @abc.abstractmethod
    def create_grid(self, **opts) -> GridCanvas:
        """Create a multi-panel :class:`GridCanvas`."""

    @abc.abstractmethod
    def create_image_view(self, **opts) -> ImageViewCanvas:
        """Create an :class:`ImageViewCanvas`."""

    @abc.abstractmethod
    def configure(self, **global_opts) -> None:
        """Apply process-wide rendering options (antialiasing, defaults)."""

    def raw_module(self):
        """Return the underlying rendering library module, or ``None``.

        This is the passthrough target: symbols chiplot does not natively offer
        are resolved from here (flagged) so migration can proceed before every
        pyqtgraph feature has a chiplot equivalent. A fully native backend that
        has no third-party library to fall through to returns ``None``.
        """
        return None
