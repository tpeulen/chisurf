"""Abstract backend contract for chiplot.

A backend turns chiplot's renderer-neutral API into concrete drawing. It
supplies two widget-bearing objects — a single-panel :class:`Canvas` and a
multi-panel :class:`GridCanvas` — plus global configuration.

The public :class:`~chisurf.gui.chiplot.Plot` / :class:`~chisurf.gui.chiplot.Grid`
wrappers delegate to these. Concrete backends live alongside this module
(``emtk_backend`` today); only they may import a rendering library, so swapping
backends never touches call sites.
"""

from __future__ import annotations

import abc
from collections.abc import Sequence
from typing import TYPE_CHECKING

import numpy as np

from chisurf.chiplot import handles as H
from chisurf.chiplot import style as S

if TYPE_CHECKING:  # the Qt host layer only; nothing here imports Qt
    from qtpy import QtWidgets


class Canvas(abc.ABC):
    """A single plot panel: axes, a viewbox, and drawn handles.

    Subclasses implement drawing against a specific renderer and return objects
    conforming to the :mod:`chisurf.chiplot.handles` protocols.
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
        step: bool | str = False,
        symbol: H.Symbol | None = None,
        symbol_size: float = 7.0,
        symbol_brush: S.Brush | None = None,
        symbol_pen: S.Pen | None = None,
        skip_missing: bool = True,
    ) -> H.Curve:
        """Draw a line/step curve (optionally with markers) and return its handle.

        ``step`` may be a bool (``True`` = centered bins, needing ``len(x) ==
        len(y) + 1``) or one of the equal-length modes ``"left"``/``"right"``/
        ``"center"``.

        ``skip_missing`` breaks the line at non-finite samples instead of
        drawing across them, so a masked or gappy series reads as a gap.
        """

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
    def add_roi(
        self,
        *,
        kind: str = "rect",
        pos: tuple[float, float] = (0.0, 0.0),
        size: tuple[float, float] = (10.0, 10.0),
        pen: S.Pen,
        movable: bool = True,
        rotatable: bool = False,
        points: Sequence[tuple[float, float]] | None = None,
    ) -> H.Roi:
        """Draw a region-of-interest shape on the plot; return its handle.

        The 2-D counterpart of :meth:`add_region`'s interval: a gate on a joint
        histogram, a cursor round a phasor cluster. A region carries no axes, so
        the same shapes serve a plot and an image view.
        """

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
    def add_arrow(
        self,
        pos: tuple[float, float],
        *,
        angle: float,
        size: float,
        tip_angle: float,
        head_width: float | None,
        tail_length: float | None,
        tail_width: float,
        pen: S.Pen | None,
        brush: S.Brush | None,
    ) -> H.Arrow:
        """Draw an arrow head at a data coordinate and return its handle.

        ``angle`` is chiplot's convention — degrees counter-clockwise from the
        ``+x`` axis, pointing the way the tip faces. A backend whose native
        arrow measures the angle differently converts here, never at the call
        site. Lengths are in pixels: the arrow is scale-invariant, so zooming
        does not resize it.
        """

    @abc.abstractmethod
    def add_text(
        self,
        text: str,
        pos: tuple[float, float],
        *,
        color: S.Color,
        anchor: tuple[float, float],
        draggable: bool,
        fill: S.Brush | None = None,
        border: S.Pen | None = None,
        anchored: bool = False,
    ) -> H.Text:
        """Draw a text label and return its handle.

        When ``anchored`` is ``True`` the label is pinned to the panel in
        screen space (``pos`` is a pixel offset from the top-left) and does not
        move or rescale with the data — for fixed overlays like a fit-quality
        readout. When ``False`` (default) ``pos`` is a data coordinate.
        """

    @abc.abstractmethod
    def add_legend(self, *, offset: tuple[int, int]) -> None:
        """Enable a legend collecting named handles."""

    @abc.abstractmethod
    def remove_legend(self) -> None:
        """Stop showing the legend."""

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
        left_units: str | None = None,
        bottom_units: str | None = None,
        right_units: str | None = None,
        top_units: str | None = None,
    ) -> None:
        """Set text and units independently; None preserves and empty clears."""

    @abc.abstractmethod
    def set_title(self, title: str | None) -> None:
        """Set the panel title."""

    @abc.abstractmethod
    def set_log(self, *, x: bool | None = None, y: bool | None = None) -> None:
        """Toggle logarithmic scaling per axis."""

    @abc.abstractmethod
    def set_tick_spacing(
        self,
        side: str,
        *,
        major: float | None = None,
        minor: float | None = None,
    ) -> None:
        """Fix the tick interval on one axis, or restore automatic spacing.

        Parameters
        ----------
        side : str
            ``"bottom"``, ``"left"``, ``"top"`` or ``"right"``.
        major, minor : float, optional
            Interval between labelled and unlabelled ticks, in axis units
            (decades on a log axis). Passing neither restores the backend's own
            spacing.
        """

    @abc.abstractmethod
    def on_range_changed(self, callback) -> None:
        """Register ``callback(x_range, y_range)`` for view range changes.

        Fires on pan and zoom; both arguments are ``(low, high)`` tuples in
        axis units. Used to keep anything that depends on how much of an axis
        is showing -- tick density, level-of-detail decimation -- in step with
        the view.
        """

    @abc.abstractmethod
    def set_range(
        self,
        *,
        x: tuple[float, float] | None = None,
        y: tuple[float, float] | None = None,
        padding: float | None = None,
    ) -> None:
        """Set the visible x/y range, **in data units**.

        Data units on a logarithmic axis too: pass ``(1, 10000)``, not
        ``(0, 4)``. One renderer wants the exponents and another wants the
        values, so a backend converts — the API cannot, or a call site would
        have to know which renderer it is talking to. That is exactly what went
        wrong: a caller pre-computed ``log10`` for pyqtgraph and the same code
        on the native backend showed a decay spanning 0.1 to 4 counts.
        """

    @abc.abstractmethod
    def get_range(self) -> tuple[tuple[float, float], tuple[float, float]]:
        """Return the current ``((x0, x1), (y0, y1))`` visible range, in data units."""

    @abc.abstractmethod
    def is_auto_range(self) -> tuple[bool, bool]:
        """Return whether x and y still follow the data (``False`` once set or zoomed)."""

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
    def set_si_prefix(self, *, x: bool | None = None, y: bool | None = None) -> None:
        """Enable or disable the automatic SI prefix on an axis."""

    @abc.abstractmethod
    def invert_y(self, invert: bool = True) -> None:
        """Invert the y-axis direction."""

    def set_axis_visible(self, side: str, visible: bool) -> None:
        """Show or hide one axis (``"left"``/``"bottom"``/``"right"``/``"top"``).

        Default no-op; backends with axis chrome override it.
        """

    def set_axis_style(self, *, line=None, text=None) -> None:
        """Colour the axis lines (``line``) and the tick/label text (``text``).

        Default no-op; backends with axis chrome override it.
        """

    def set_tick_labels(self, side: str, ticks) -> None:
        """Label one axis with ``[(position, text), ...]`` instead of numbers.

        ``None`` restores numeric labels. Default no-op.
        """

    def set_legend_style(self, *, text=None) -> None:
        """Colour the legend text. Default no-op."""

    def set_compact(self, compact: bool = True, *, font_size: int = 8) -> None:
        """Shrink the panel's chrome so a small panel is mostly data.

        Margins, tick length, tick-label spacing, the view's default padding
        and the tick font all shrink together — they are one intent ("this
        panel is a strip, not a figure") and adjusting them one at a time is
        what drove call sites past the seam into the backend's plot item.
        Default no-op; backends with chrome override it.
        """

    def set_downsampling(self, *, auto: bool = True, mode: str = "peak") -> None:
        """Enable/disable automatic downsampling of dense curves on this panel.

        A renderer performance hint for very large series. ``mode`` selects
        the reduction strategy (``"peak"`` preserves extrema; ``"subsample"``
        takes evenly spaced points). Backends without downsampling may ignore
        this.
        """

    def set_clip_to_view(self, clip: bool = True) -> None:
        """Hint the backend to skip drawing samples outside the visible range.

        A renderer performance hint for large series. Backends without view
        culling may ignore this.
        """

    def link_x(self, other: Canvas) -> None:
        """Link this panel's x-axis to ``other`` so they pan/zoom together.

        Default no-op; backends with a shared view model override it.
        """

    def link_y(self, other: Canvas) -> None:
        """Link this panel's y-axis to ``other`` so they pan/zoom together."""

    def set_menu_enabled(self, enabled: bool) -> None:
        """Enable/disable the backend's own right-click menu (default no-op)."""

    def menu_enabled(self) -> bool:
        """Whether the right-click menu is currently offered.

        The read side of :meth:`set_menu_enabled`, so a caller (or a test) can
        ask without reaching through the seam for a renderer's own spelling.
        Backends with no menu answer ``False``.
        """
        return False

    def set_interactive(self, *, mouse: bool = True, menu: bool = True) -> None:
        """Enable/disable mouse pan-zoom and the right-click menu (default no-op)."""

    def set_auto_range_button(self, shown: bool) -> None:
        """Show (default) or never show the "A" auto-range button (default no-op)."""

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
    def add_colorbar(
        self,
        image: H.Image,
        *,
        colormap: S.Colormap | None = None,
        row: int | None = None,
        col: int | None = None,
        rowspan: int = 1,
        colspan: int = 1,
    ) -> H.ColorBar:
        """Add a colour bar / level editor bound to ``image``; return its handle."""

    @abc.abstractmethod
    def next_row(self) -> None:
        """Advance the implicit insertion cursor to the next row."""

    @abc.abstractmethod
    def clear(self) -> None:
        """Remove every panel, and reset the insertion cursor to the first cell.

        A grid whose panel *count* depends on the data — one decay per detector,
        one map per channel — has to be emptied before it is rebuilt, or the
        previous selection's panels stay below the new ones.
        """

    @abc.abstractmethod
    def set_column_stretch(self, column: int, factor: float) -> None:
        """Set the relative width of a grid column."""

    @abc.abstractmethod
    def set_row_stretch(self, row: int, factor: float) -> None:
        """Set the relative height of a grid row."""

    @property
    @abc.abstractmethod
    def native(self):
        """The backend-specific container object (escape hatch)."""


class ImageViewCanvas(abc.ABC):
    """An image viewer: image + intensity/LUT histogram + (3-D) frame slider.

    Wraps the renderer's composite image-view widget. Overlays and ROIs live on its internal view.
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

    def set_auto_range_button(self, shown: bool) -> None:
        """Show (default) or never show the "A" auto-range button (default no-op)."""

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

    # -- what an interactive image dock needs beyond showing a picture ------
    # Not abstract: a backend that cannot do one of these raises, by name,
    # instead of drawing a dock that silently ignores the request.
    def _unsupported(self, what: str):
        raise NotImplementedError(f"the {type(self).__name__} backend has no {what}")

    @property
    def frame_count(self) -> int:
        """Number of frames in the shown stack (``1`` for a single image)."""
        self._unsupported("frame stepping")

    @property
    def frame(self) -> int:
        """Index of the frame being shown."""
        self._unsupported("frame stepping")

    def set_frame(self, index: int) -> None:
        """Show frame *index* (wrapping) of the stack."""
        self._unsupported("frame stepping")

    def on_frame_changed(self, callback) -> None:
        """Call ``callback(index)`` when the shown frame changes."""
        self._unsupported("frame stepping")

    def colorbar_widget(self) -> QtWidgets.QWidget | None:
        """The colour ramp widget with draggable levels, or ``None`` without one."""
        return None

    def set_extent(self, extent) -> None:
        """Place the picture on ``(x0, x1, y0, y1)`` axes; ``None`` = pixel indices."""
        self._unsupported("extent placement")

    def set_labels(self, *, bottom=None, left=None) -> None:
        """Title the axes."""
        self._unsupported("axis titles")

    def set_axes_visible(self, visible: bool) -> None:
        """Show or hide tick numbers and titles."""
        self._unsupported("axes")

    def invert_y(self, invert: bool = True) -> None:
        """Row 0 at the top (``True``) or the bottom."""
        self._unsupported("y inversion")

    def set_aspect_locked(self, lock: bool = True) -> None:
        """Square pixels, or fill the panel."""
        self._unsupported("aspect locking")

    def auto_range(self) -> None:
        """Fit the view to the picture."""
        self._unsupported("auto range")

    def view_range(self):
        """The visible ``((x0, x1), (y0, y1))``."""
        self._unsupported("view range")

    def add_marks(self, x, y, **style) -> H.Scatter:
        """Draw symbols over the picture."""
        self._unsupported("marks")

    def add_text(self, text, pos, **style) -> H.Text:
        """Write text at a data position."""
        self._unsupported("text")

    def on_hover(self, callback) -> None:
        """Register ``callback(x, y)`` for pointer motion."""
        self._unsupported("hover reporting")

    def set_paint_handler(self, handler) -> None:
        """Hand the left drag to ``handler(phase, x, y)``."""
        self._unsupported("painting")


class VolumeViewCanvas(abc.ABC):
    """A 3-D volume renderer.

    Displays a ``(nz, ny, nx)`` scalar volume as a translucent stack the user
    can orbit. Distinct from :class:`ImageViewCanvas`, which shows one plane of
    a stack at a time behind a frame slider.
    """

    @abc.abstractmethod
    def widget(self) -> QtWidgets.QWidget:
        """Return the embeddable Qt widget."""

    @abc.abstractmethod
    def set_volume(
        self,
        data: np.ndarray,
        *,
        colormap: str = "magma",
        threshold: float = 0.0,
        gamma: float = 1.0,
    ) -> None:
        """Show a ``(nz, ny, nx)`` scalar volume.

        ``threshold`` drops voxels below a fraction of the peak, and ``gamma``
        shapes the opacity ramp; both exist because a diffraction-limited focus
        is mostly empty space and renders as fog without them.
        """

    @abc.abstractmethod
    def set_scale(self, sx: float = 1.0, sy: float = 1.0, sz: float = 1.0) -> None:
        """Set per-axis voxel scaling, so anisotropic sampling looks right."""

    @abc.abstractmethod
    def clear(self) -> None:
        """Remove the volume."""

    def set_vectors(
        self,
        segments: np.ndarray | None,
        *,
        color: tuple = (1.0, 1.0, 1.0, 0.8),
        width: float = 2.0,
    ) -> None:
        """Draw an overlay of line segments, ``(n, 2, 3)`` in voxel coordinates.

        For annotating a volume with directions -- a polarization state, a
        field, an axis. ``None`` removes the overlay. Backends without line
        support may ignore this.
        """

    @abc.abstractmethod
    def set_camera(self, distance=None, elevation=None, azimuth=None) -> None:
        """Position the orbit camera."""

    @property
    @abc.abstractmethod
    def native(self):
        """The backend-specific view object (escape hatch)."""


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

    def create_volume_view(self, **opts) -> VolumeViewCanvas:
        """Create a :class:`VolumeViewCanvas`.

        Not abstract: a backend without a 3-D renderer should say so plainly
        rather than fail to instantiate.
        """
        raise NotImplementedError(f"the {self.name!r} backend has no 3-D volume renderer")

    @abc.abstractmethod
    def configure(self, **global_opts) -> None:
        """Apply process-wide rendering options (antialiasing, defaults)."""
