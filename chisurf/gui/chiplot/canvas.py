"""chiplot's Qt host layer: :func:`host`, and the ``QWidget`` wrappers :class:`Plot`,
:class:`Grid` and :class:`ImageView`.

Everything that draws is in the toolkit-free core (:mod:`chisurf.chiplot`): a
panel, a grid and an image view are emtk controls there. This module only
*hosts* them in Qt -- an ``emtk.qt_host.ControlHost`` per control, attached
through the core's duck-typed host hook (``attach_host``) -- and adds what is
Qt's: signals, the right-click menu with its file dialogs, a grid layout, the
frame slider. It goes when the last Qt caller does
(``okf/subsystems/chiplot.md``); new code draws a :class:`~chisurf.chiplot.Panel`
on an emtk surface, or, inside a legacy Qt form, hosts one with :func:`host`.
"""

from __future__ import annotations

import numpy as np
from qtpy import QtCore, QtWidgets

from chisurf.chiplot import handles as H
from chisurf.chiplot import style as S
from chisurf.chiplot.backends import get_backend
from chisurf.chiplot.canvas import _UNSET, Panel, PlotAPI, _Hook

__all__ = ["Grid", "ImageView", "Panel", "PanelPlot", "Plot", "PlotAPI", "_Hook", "host"]


class _QtHost:
    """The core's host hook (``update``/``size``/``set_background``/...) over a ``ControlHost``."""

    def __init__(self, control, *, background=(30, 32, 38), parent=None) -> None:
        from emtk.qt_host import ControlHost

        self.widget = ControlHost(control, background=background, parent=parent)

    def update(self) -> None:
        self.widget.update()

    def size(self) -> tuple[int, int]:
        return self.widget.width(), self.widget.height()

    def set_background(self, rgb) -> None:
        self.widget.background = tuple(rgb[:3])

    def set_visible(self, visible: bool) -> None:
        self.widget.setVisible(bool(visible))

    def set_width_range(self, least: int, most: int) -> None:
        if least == most:
            self.widget.setFixedWidth(int(least))
        else:
            self.widget.setMinimumWidth(int(least))
            self.widget.setMaximumWidth(int(most))

    def detach(self) -> None:
        self.widget.setParent(None)


def _hosted(control, parent=None) -> QtWidgets.QWidget:
    """A ``ControlHost`` showing *control* (a core canvas, ramp or grid), attached to it."""
    background = getattr(control, "_background", None) or getattr(control, "background", None)
    adapter = _QtHost(control, background=background or (30, 32, 38), parent=parent)
    attach = getattr(control, "attach_host", None)
    if callable(attach):
        attach(adapter)
    else:  # a grid: repaint requests come back through its refresh target
        control.set_refresh_target(adapter.update)
    adapter.widget._chiplot_host = adapter
    return adapter.widget


def host(panel, parent=None) -> QtWidgets.QWidget:
    """Host a toolkit-free chiplot panel in a Qt layout.

    For a legacy Qt form that shows a :class:`~chisurf.chiplot.Panel` (or an
    image view's or grid's control): the panel stays an emtk control drawn by
    emtk, and the widget returned only hosts it.

    Parameters
    ----------
    panel : Panel or control
        A :class:`~chisurf.chiplot.Panel` (its :meth:`~chisurf.chiplot.Panel.control`
        is hosted), or any control with ``draw``.
    parent : QWidget, optional
        Qt parent.

    Returns
    -------
    QWidget
    """
    control = panel.control() if callable(getattr(panel, "control", None)) else panel
    return _hosted(control, parent)


def _export_qt(canvas, widget, path, width) -> bool:
    """Paint *canvas* into a ``QImage`` at *widget*'s size: what a Qt-hosted panel exports."""
    from emtk.qt_painter import QtPainter
    from qtpy import QtGui

    w, h = widget.width(), widget.height()
    scale = float(width) / max(w, 1) if width else 1.0
    image = QtGui.QImage(
        max(int(w * scale), 1), max(int(h * scale), 1), QtGui.QImage.Format_ARGB32
    )
    image.fill(QtGui.QColor(*canvas._background))
    painter = QtGui.QPainter(image)
    try:
        painter.scale(scale, scale)
        canvas.draw(QtPainter(painter), 0.0, 0.0, float(w), float(h))
    finally:
        painter.end()
    return bool(image.save(str(path)))


class Plot(PlotAPI, QtWidgets.QWidget):
    """A single plot panel with a verb-first drawing API.

    Parameters
    ----------
    parent : QWidget, optional
        Qt parent.
    title : str, optional
        Panel title.
    background : color-like, optional
        Background color of the whole panel widget (data rectangle *and* axis
        margins). An explicit ``None`` means transparent.
    **backend_opts
        Passed through to the backend canvas factory.

    Signals
    -------
    clicked(float, float)
        Emitted with the ``(x, y)`` data coordinates of a left click.
    mouse_moved(float, float)
        Emitted with the ``(x, y)`` data coordinates under the pointer.
    """

    clicked = QtCore.Signal(float, float)
    mouse_moved = QtCore.Signal(float, float)

    def __init__(self, parent=None, *, title: str | None = None, background=_UNSET, **backend_opts):
        super().__init__(parent)
        self._canvas = get_backend().create_canvas(**backend_opts)
        # (name, handle) of exportable x/y series, for the CSV context action.
        self._series: list = []
        self._extra_menu_actions: list = []
        self._context_menu_enabled = True
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._host_widget = _hosted(self._canvas)
        layout.addWidget(self._host_widget)
        if title is not None:
            self._canvas.set_title(title)
        if background is not _UNSET:
            self._canvas.set_background(None if background is None else S.to_color(background))
        self._canvas.on_click(lambda x, y, btn: self.clicked.emit(x, y) if btn == "left" else None)
        self._canvas.on_mouse_move(lambda x, y: self.mouse_moved.emit(x, y))
        # If the backend already ships a rich menu (pyqtgraph: Export/CSV/image),
        # keep it for parity and inject custom actions into it; otherwise chiplot
        # builds its own menu via contextMenuEvent.
        self._native_menu = self._canvas.provides_native_menu()
        if self._native_menu:
            self._install_native_export_actions()

    def _install_native_export_actions(self) -> None:
        """Add chiplot's CSV/image export entries to the backend's native menu."""
        self._canvas.add_menu_action("Export data as CSV…", self._on_export_csv)
        self._canvas.add_menu_action("Export image…", self._on_export_image)

    def _on_export_csv(self):
        """File-dialog + write for the CSV export menu action."""
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            None, "Export data as CSV", "", "CSV files (*.csv)"
        )
        if path:
            self.export_csv(path)

    def _on_export_image(self):
        """File-dialog + write for the image export menu action."""
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            None, "Export image", "", "Images (*.png *.svg *.jpg)"
        )
        if path:
            self.export_image(path)

    def export_image(self, path: str, *, width: int | None = None) -> None:
        """Save the panel as an image, painted by Qt as the widget shows it.

        A Qt-hosted panel keeps the picture Qt draws on screen; a toolkit-free
        :class:`~chisurf.chiplot.Panel` exports through emtk's CPU rasteriser.
        """
        if not _export_qt(self._canvas, self._host_widget, path, width):
            raise OSError(f"chiplot: the plot could not be exported to {path}")

    def contextMenuEvent(self, event):  # noqa: N802 (Qt override)
        """Show chiplot's right-click menu (export data/image, auto-range).

        Skipped when the backend already shows its own rich menu (pyqtgraph),
        so the two never double up.
        """
        if not self._context_menu_enabled or getattr(self, "_native_menu", False):
            event.ignore()
            return
        menu = QtWidgets.QMenu(self)
        menu.addAction("Export data as CSV…", self._on_export_csv)
        menu.addAction("Export image…", self._on_export_image)
        menu.addSeparator()
        menu.addAction("Auto-range", lambda: self.autoscale())
        if self._extra_menu_actions:
            menu.addSeparator()
            for label, cb in self._extra_menu_actions:
                menu.addAction(label, cb)
        menu.exec_(event.globalPos())


class Grid(QtWidgets.QWidget):
    """A grid of :class:`Plot`-style panels sharing one widget.

    Replaces ``pg.GraphicsLayoutWidget``. Use :meth:`add_plot` to add panels.

    Parameters
    ----------
    parent : QWidget, optional
        Qt parent.
    **backend_opts
        Passed to the backend grid factory.
    """

    def __init__(self, parent=None, **backend_opts):
        super().__init__(parent)
        self._grid = get_backend().create_grid(**backend_opts)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        # The core grid is a control that lays itself out; a Qt host places its
        # cells in a grid layout instead, one host widget per panel or ramp.
        self._cells = QtWidgets.QWidget()
        self._layout = QtWidgets.QGridLayout(self._cells)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)
        self._placed: list = []
        layout.addWidget(self._cells)

    def _place_last(self):
        """Host the cell the core grid just added, where it says it goes."""
        item, row, col, rowspan, colspan = self._grid.cells()[-1]
        widget = _hosted(item)
        self._layout.addWidget(widget, row, col, rowspan, colspan)
        self._placed.append(widget)
        return item

    def add_plot(self, *, row=None, col=None, rowspan=1, colspan=1, title=None) -> PanelPlot:
        """Add and return a panel at the given grid cell.

        Parameters
        ----------
        row, col : int, optional
            Target cell (implicit next cell if omitted).
        rowspan, colspan : int
            Cell span.
        title : str, optional
            Panel title.

        Returns
        -------
        PanelPlot
        """
        self._grid.add_panel(row=row, col=col, rowspan=rowspan, colspan=colspan, title=title)
        return PanelPlot(self._place_last())

    def set_column_stretch(self, column: int, factor: float) -> None:
        """Set the relative width of a grid column.

        Panels in a grid share the width equally by default, which is wrong the
        moment one of them is a colour bar: it takes as much room as a plot and
        renders as an unreadable sliver of gradient.

        Parameters
        ----------
        column : int
            Column index.
        factor : float
            Relative width. Larger is wider; the factors are compared with each
            other, not with any absolute size.
        """
        self._grid.set_column_stretch(column, factor)
        self._layout.setColumnStretch(int(column), int(factor))

    def set_row_stretch(self, row: int, factor: float) -> None:
        """Set the relative height of a grid row.

        Parameters
        ----------
        row : int
            Row index.
        factor : float
            Relative height.
        """
        self._grid.set_row_stretch(row, factor)
        self._layout.setRowStretch(int(row), int(factor))

    def add_colorbar(
        self, image: H.Image, *, colormap=None, row=None, col=None, rowspan=1, colspan=1
    ) -> H.ColorBar:
        """Add a colour bar with interactive level handles, bound to ``image``.

        Replaces pyqtgraph's ``HistogramLUTItem``: the bar shows the image's
        intensity histogram, its handles set the mapped level range, and its
        gradient sets the colormap of both bar and image.

        Parameters
        ----------
        image : handles.Image
            The image handle the bar drives (from :meth:`Plot.image`).
        colormap : colormap-like, optional
            Initial colormap (name or :class:`~chisurf.chiplot.style.Colormap`).
        row, col : int, optional
            Target cell (implicit next cell if omitted).
        rowspan, colspan : int
            Cell span.

        Returns
        -------
        handles.ColorBar
        """
        self._grid.add_colorbar(
            image,
            colormap=S.to_colormap(colormap),
            row=row,
            col=col,
            rowspan=rowspan,
            colspan=colspan,
        )
        return self._place_last()

    def next_row(self) -> None:
        """Advance the implicit insertion cursor to the next row."""
        self._grid.next_row()

    def clear(self) -> None:
        """Remove every panel, and reset the insertion cursor to the first cell.

        Panels obtained from :meth:`add_plot` before this call are gone; a
        rebuild must ask for new ones.
        """
        self._grid.clear()
        for widget in self._placed:
            self._layout.removeWidget(widget)
            widget.setParent(None)
        self._placed.clear()

    @property
    def native(self):
        """The backend grid object (escape hatch; avoid in new code)."""
        return self._grid.native


class ImageView(QtWidgets.QWidget):
    """Image viewer: image + intensity/LUT histogram + (3-D) frame slider.

    Replaces ``pg.ImageView``. Drops into a Qt layout like any widget. Overlays
    and ROIs attach to its internal view.

    Parameters
    ----------
    parent : QWidget, optional
        Qt parent.
    **backend_opts
        Passed to the backend image-view factory.

    Signals
    -------
    clicked(float, float)
        Emitted with the ``(x, y)`` image coordinates of a click.
    """

    clicked = QtCore.Signal(float, float)
    #: Emitted with a :class:`chisurf.core.roi.PickedSpot` for each pick, whether
    #: or not the fit converged — a refusal carries its reason and is worth
    #: showing, where a silently dropped click is not.
    picked = QtCore.Signal(object)
    #: Emitted with the new index whenever the shown frame of a stack changes,
    #: whether by the slider, :meth:`set_frame` or playback.
    frame_changed = QtCore.Signal(int)
    #: Emitted with ``True`` when playback starts and ``False`` when it stops,
    #: including when a non-looping stack reaches its last frame by itself.
    playing_changed = QtCore.Signal(bool)

    def __init__(self, parent=None, **backend_opts):
        super().__init__(parent)
        self._iv = get_backend().create_image_view(**backend_opts)
        self._picking = False
        self._pick_fit = "gaussian"
        self._pick_window = 9
        self._pick_image = None
        self._last_image = None
        self._extent = None
        self._brush = None
        self._play_timer = None
        self._play_loop = True
        self._fps = 10
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(_hosted(self._iv.control()), 1)
        layout.addLayout(row, 1)
        self._row = row
        self._ramp = None
        # The frame stepper: shown only while a stack is on screen.
        self._frame_bar = QtWidgets.QWidget(self)
        bar = QtWidgets.QHBoxLayout(self._frame_bar)
        bar.setContentsMargins(4, 0, 4, 0)
        self._slider = QtWidgets.QSlider(QtCore.Qt.Horizontal, self._frame_bar)
        self._slider.setToolTip("Frame of the stack")
        self._frame_label = QtWidgets.QLabel("", self._frame_bar)
        bar.addWidget(self._slider, 1)
        bar.addWidget(self._frame_label)
        layout.addWidget(self._frame_bar)
        self._frame_bar.setVisible(False)
        self._slider.valueChanged.connect(self._on_slider)
        self._iv.on_click(lambda x, y: self.clicked.emit(x, y))
        self._iv.on_frame_changed(self._frame_moved)

    def set_image(self, data, *, auto_levels=True, axes=None) -> None:
        """Show a 2-D image or a 3-D ``(t, y, x)`` stack.

        Parameters
        ----------
        data : array-like
            2-D image or 3-D stack.
        auto_levels : bool
            Auto-scale the intensity range to the data.
        axes : dict, optional
            Dimension map for stacks, e.g. ``{"t": 0, "y": 1, "x": 2}``.
        """
        data = np.asarray(data)
        # Kept so picking has something to fit against without the caller
        # having to hand the same array over twice.
        self._last_image = data
        self._iv.set_image(data, auto_levels=auto_levels, axes=axes)
        count = int(self._iv.frame_count)
        self._slider.blockSignals(True)
        self._slider.setRange(0, max(count - 1, 0))
        self._slider.setValue(0)
        self._slider.blockSignals(False)
        self._frame_bar.setVisible(count > 1)
        self._frame_label.setText(f"1/{count}" if count > 1 else "")
        if count <= 1:
            self.stop()
        bar = self._iv.colorbar()
        if bar is not None and (bar.host is None or bar.host.widget is not self._ramp):
            self._ramp = _hosted(bar)
            self._row.addWidget(self._ramp)

    # -- frames and playback ----------------------------------------------
    @property
    def frame_count(self) -> int:
        """Number of frames of the shown stack (``1`` for a single image)."""
        return int(self._iv.frame_count)

    @property
    def frame(self) -> int:
        """Index of the frame being shown."""
        return int(self._iv.frame)

    def set_frame(self, index: int) -> None:
        """Show frame *index* of the stack (wrapping); a no-op for one image."""
        self._iv.set_frame(index)

    def _frame_moved(self, index: int) -> None:
        """The backend changed frame: follow it with the slider and announce it."""
        self._slider.blockSignals(True)
        self._slider.setValue(index)
        self._slider.blockSignals(False)
        count = self.frame_count
        self._frame_label.setText(f"{index + 1}/{count}" if count > 1 else "")
        self.frame_changed.emit(index)

    def _on_slider(self, value: int) -> None:
        self._iv.set_frame(value)

    @property
    def playing(self) -> bool:
        """Whether the stack is being played."""
        return self._play_timer is not None and self._play_timer.isActive()

    def play(self, fps: int | None = None, *, loop: bool | None = None) -> None:
        """Step through the stack at *fps* frames per second.

        Parameters
        ----------
        fps : int, optional
            Frames per second; the last value is kept when omitted.
        loop : bool, optional
            Wrap round at the end (default) or stop on the last frame.
        """
        if self.frame_count <= 1:
            return
        if fps is not None:
            self._fps = max(int(fps), 1)
        if loop is not None:
            self._play_loop = bool(loop)
        if self._play_timer is None:
            self._play_timer = QtCore.QTimer(self)
            self._play_timer.timeout.connect(self._advance)
        self._play_timer.start(int(1000 / self._fps))
        self.playing_changed.emit(True)

    def set_fps(self, fps: int) -> None:
        """Change the playback speed, taking effect at once while playing."""
        self._fps = max(int(fps), 1)
        if self.playing:
            self._play_timer.start(int(1000 / self._fps))

    def set_loop(self, loop: bool) -> None:
        """Wrap round at the end of the stack (``True``) or stop on the last frame."""
        self._play_loop = bool(loop)

    def pause(self) -> None:
        """Stop playing, staying on the current frame."""
        was = self.playing
        if self._play_timer is not None:
            self._play_timer.stop()
        if was:
            self.playing_changed.emit(False)

    def stop(self) -> None:
        """Stop playing and return to the first frame."""
        self.pause()
        if self.frame_count > 1:
            self.set_frame(0)

    def _advance(self) -> None:
        """One playback step: next frame, wrapping or stopping at the end."""
        nxt = self.frame + 1
        if nxt >= self.frame_count:
            if not self._play_loop:
                self.pause()
                return
            nxt = 0
        self.set_frame(nxt)

    # -- placing the picture ----------------------------------------------
    def set_extent(self, extent) -> None:
        """Put the picture on real axes ``(x0, x1, y0, y1)``.

        ``None`` returns to pixel indices. The view re-ranges to the new span
        when it changes, and otherwise keeps the user's zoom.
        """
        self._extent = None if extent is None else tuple(float(v) for v in extent)
        self._iv.set_extent(self._extent)

    def set_labels(self, *, bottom: str | None = None, left: str | None = None) -> None:
        """Title the axes and show them (a bare picture has none)."""
        self._iv.set_axes_visible(True)
        self._iv.set_labels(bottom=bottom, left=left)

    def set_axes_visible(self, visible: bool) -> None:
        """Show or hide tick numbers and axis titles."""
        self._iv.set_axes_visible(bool(visible))

    def invert_y(self, invert: bool = True) -> None:
        """Row 0 at the top (``True``, a picture) or the bottom (a plot)."""
        self._iv.invert_y(invert)

    def set_aspect_locked(self, lock: bool = True) -> None:
        """Square pixels (``True``) or fill the panel."""
        self._iv.set_aspect_locked(lock)

    def auto_range(self) -> None:
        """Fit the view to the picture."""
        self._iv.auto_range()

    def view_range(self):
        """The visible ``((x0, x1), (y0, y1))`` in axis units."""
        return self._iv.view_range()

    def pixel_at(self, x: float, y: float) -> tuple[int, int] | None:
        """Convert axis coordinates to ``(row, column)`` of the shown picture.

        Returns ``None`` outside the picture. With an extent the axes carry the
        quantity, so a click or a stroke is mapped back to the pixel under it.
        """
        image = self._last_image
        if image is None:
            return None
        ny, nx = image.shape[-2:]
        if self._extent is not None:
            x0, x1, y0, y1 = self._extent
            col = (x - x0) / (x1 - x0) * nx
            row = (y - y0) / (y1 - y0) * ny
        else:
            col, row = x, y
        row, col = int(np.floor(row)), int(np.floor(col))
        if 0 <= row < ny and 0 <= col < nx:
            return row, col
        return None

    # -- symbols and labels over the picture ------------------------------
    def marks(
        self, x, y, *, symbol="o", size=7.0, pen=None, brush=None, width=1.0, z=None
    ) -> H.Scatter:
        """Draw a set of symbols over the picture, in axis coordinates.

        Parameters
        ----------
        x, y : array-like
            Positions (``x`` a column, ``y`` a row for an image without extent).
        symbol : str
            ``"o"``, ``"s"``, ``"t"``, ``"d"``, ``"+"`` or ``"x"``.
        size : float
            Symbol size in pixels.
        pen, brush : color-like, optional
            Outline and fill; ``None`` leaves the symbol hollow / flat.
        width : float
            Outline width in pixels.
        z : float, optional
            Stacking order among the marks.

        Returns
        -------
        handles.Scatter
        """
        style = {
            "symbol": symbol,
            "size": size,
            "pen": None if pen is None else S.to_pen(pen),
            "brush": None if brush is None else S.to_brush(brush),
            "width": width,
        }
        marks = self._iv.add_marks(np.asarray(x, dtype=float), np.asarray(y, dtype=float), **style)
        if z is not None:
            marks.z = float(z)
        return marks

    def label(self, text: str, x: float, y: float, *, color="w", anchor=(0.0, 0.0)) -> H.Text:
        """Write *text* at axis position ``(x, y)`` over the picture."""
        return self._iv.add_text(str(text), (x, y), color=S.to_color(color), anchor=anchor)

    # -- painting ----------------------------------------------------------
    def enable_brush(self, kernel=None, *, on_stroke=None, color=(255, 255, 255)) -> None:
        """Make the picture paintable with a brush, on a layer of its own.

        The left drag stamps *kernel* onto a mask the size of the picture and
        shows it as a translucent layer; a drag that starts on a shape still
        moves the shape. Values accumulate (a stroke over painted pixels adds)
        and are floored at zero, so a negative kernel erases. The mask is read
        with :meth:`brush_mask`, replaced with :meth:`set_brush_mask`.

        Parameters
        ----------
        kernel : array-like or callable, optional
            2-D weights stamped at each pixel (centred on it), or a callable
            returning them, read at the start of every stroke so a tool can
            change brush size between strokes. Default a single pixel.
        on_stroke : callable, optional
            ``on_stroke(mask, phase)`` after every stamp, ``phase`` one of
            ``"start"``, ``"move"`` or ``"end"``; ``mask`` is a copy.
        color : color-like
            Colour of the painted layer.
        """
        tint = S.to_color(color)
        lut = np.zeros((256, 4), dtype=np.uint8)
        lut[:, :3] = (tint.r, tint.g, tint.b)
        lut[:, 3] = np.linspace(0, 170, 256).astype(np.uint8)
        self._brush = {
            "kernel": kernel,
            "on_stroke": on_stroke,
            "lut": lut,
            "layer": None,
            "mask": None,
            "last": None,
            "active": None,
        }
        self._iv.set_paint_handler(self._paint)
        if self._last_image is not None:
            self.set_brush_mask(None)

    def disable_brush(self) -> None:
        """Remove the brush and its layer; the drag pans again."""
        if self._brush is None:
            return
        if self._brush["layer"] is not None:
            self._brush["layer"].remove()
        self._iv.set_paint_handler(None)
        self._brush = None

    def brush_mask(self) -> np.ndarray | None:
        """A copy of the painted mask, or ``None`` before an image is shown."""
        if self._brush is None or self._brush["mask"] is None:
            return None
        return self._brush["mask"].copy()

    def set_brush_mask(self, mask) -> None:
        """Replace the painted mask (``None`` clears it) and redraw the layer.

        A mask whose shape is not the picture's is dropped for an empty one:
        painting on a stale mask would stamp onto pixels that no longer exist.
        """
        brush = self._brush
        if brush is None or self._last_image is None:
            return
        shape = self._last_image.shape[-2:]
        if mask is None or np.shape(mask) != shape:
            mask = np.zeros(shape, dtype=float)
        brush["mask"] = np.array(mask, dtype=float)
        if brush["layer"] is None or brush["layer"].get_image().shape != shape:
            if brush["layer"] is not None:
                brush["layer"].remove()
            brush["layer"] = self._iv.add_overlay(brush["mask"], colormap=brush["lut"])
            brush["layer"].set_levels(0.0, 1.0)
        else:
            brush["layer"].set_image(brush["mask"])

    def _stamp(self, row: int, col: int) -> None:
        """Add the kernel to the mask, centred on ``(row, col)``, clipped to it."""
        brush = self._brush
        kernel = brush["active"]
        mask = brush["mask"]
        kh, kw = kernel.shape
        top, left = row - kh // 2, col - kw // 2
        r0, c0 = max(top, 0), max(left, 0)
        r1, c1 = min(top + kh, mask.shape[0]), min(left + kw, mask.shape[1])
        if r1 <= r0 or c1 <= c0:
            return
        window = mask[r0:r1, c0:c1] + kernel[r0 - top : r1 - top, c0 - left : c1 - left]
        mask[r0:r1, c0:c1] = np.maximum(window, 0.0)

    def _paint(self, phase: str, x: float, y: float) -> None:
        """The backend's drag, in axis coordinates: stamp along the stroke."""
        brush = self._brush
        if brush is None:
            return
        if brush["mask"] is None or brush["mask"].shape != self._last_image.shape[-2:]:
            self.set_brush_mask(None)
        if phase == "start":
            source = brush["kernel"]
            kernel = source() if callable(source) else source
            kernel = np.ones((1, 1)) if kernel is None else np.atleast_2d(np.asarray(kernel, float))
            brush["active"] = kernel
            brush["last"] = None
        if phase != "end":
            pixel = self.pixel_at(x, y)
            if pixel is not None and brush["active"] is not None:
                last = brush["last"]
                if last is None or last == pixel:
                    steps = [pixel]
                else:
                    # A fast drag skips pixels: walk the straight line between
                    # the last stamp and this one so the stroke has no gaps.
                    n = max(abs(pixel[0] - last[0]), abs(pixel[1] - last[1]))
                    steps = [
                        (
                            int(round(last[0] + (pixel[0] - last[0]) * k / n)),
                            int(round(last[1] + (pixel[1] - last[1]) * k / n)),
                        )
                        for k in range(1, n + 1)
                    ]
                for row, col in steps:
                    self._stamp(row, col)
                brush["last"] = pixel
                brush["layer"].set_image(brush["mask"])
        if brush["on_stroke"] is not None:
            brush["on_stroke"](brush["mask"].copy(), phase)

    def on_hover(self, callback) -> None:
        """Call ``callback(x, y)`` as the pointer moves over the picture."""
        self._iv.on_hover(callback)

    def set_colormap(self, name, source="matplotlib") -> None:
        """Apply a named colormap.

        Parameters
        ----------
        name : str
            Colormap identifier (e.g. ``"viridis"``, ``"CET-L4"``).
        source : str
            Namespace hint for the backend.
        """
        self._iv.set_colormap(name, source)

    def clear(self) -> None:
        """Clear the image and overlays."""
        self.stop()
        self._iv.clear()
        self._last_image = None
        self._ramp = None
        self._frame_bar.setVisible(False)
        if self._brush is not None:
            self._brush["layer"] = None
            self._brush["mask"] = None

    def set_histogram_width(self, width) -> None:
        """Constrain (int) or free (``None``) the LUT histogram panel width."""
        self._iv.set_histogram_width(width)

    def set_interactive(self, *, mouse=True, menu=True) -> None:
        """Toggle view pan/zoom (``mouse``) and the right-click menu."""
        self._iv.set_interactive(mouse=mouse, menu=menu)

    def set_auto_range_button(self, shown: bool = True) -> None:
        """Show (default) or never show the "A" auto-range button.

        See :meth:`Plot.set_auto_range_button`.
        """
        self._iv.set_auto_range_button(shown)

    def add_overlay(self, data, *, colormap=None) -> H.Image:
        """Overlay a second image on the view.

        Parameters
        ----------
        data : array-like
            Overlay image (typically RGBA with transparency).
        colormap : str or style.Colormap, optional
            Colormap for grayscale overlays.

        Returns
        -------
        handles.Image
        """
        cmap = colormap
        if isinstance(cmap, str):
            cmap = S.colormap(cmap)
        return self._iv.add_overlay(np.asarray(data), colormap=cmap)

    def add_roi(
        self,
        *,
        kind="rect",
        pos=(0.0, 0.0),
        size=(10.0, 10.0),
        pen="y",
        movable=True,
        rotatable=False,
        points=None,
        angle=0.0,
        resizable=False,
    ) -> H.Roi:
        """Add a region-of-interest shape over the image.

        Parameters
        ----------
        kind : str
            ``"rect"``, ``"circle"``, ``"ellipse"`` or ``"polygon"``. The last
            two exist because the ROI subsystem has an ellipse and a polygon
            region and, until they could be drawn, no GUI could produce one.
        pos : tuple of float
            Lower-left corner in image coordinates.
        size : tuple of float
            ``(w, h)`` in image coordinates.
        pen : pen-like
            Outline style.
        movable : bool
            Whether the user can drag/resize it.
        rotatable : bool
            Whether a rectangle ROI can be rotated (ignored for the others).
        points : sequence of (float, float), optional
            Vertices for ``kind="polygon"``; a polygon is defined by these, not
            by a corner and a size. Without them the polygon starts as the box
            described by *pos* and *size*.
        angle : float, optional
            Rotation of an ellipse, in **radians**, about its own centre —
            the unit :class:`chisurf.core.roi.EllipseROI` carries.
        resizable : bool, optional
            Give an upright rectangle or ellipse a grip on two opposite corners
            that resizes it.

        Returns
        -------
        handles.Roi
        """
        return self._iv.add_roi(
            kind=kind,
            pos=tuple(pos),
            size=tuple(size),
            pen=S.to_pen(pen),
            movable=movable,
            rotatable=rotatable,
            points=points,
            angle=np.degrees(float(angle)),
            resizable=resizable,
        )

    def add_region(self, region, *, pen="y", movable=False, name: str = "") -> H.Roi:
        """Draw a :class:`chisurf.core.roi.ROI` over the image.

        The shape-agnostic form of :meth:`add_roi`. Every caller that had a
        region and wanted it on screen was converting it to ``kind``/``pos``/
        ``size`` by hand, differently, and getting the ellipse's radius-versus-
        diameter convention wrong in at least two places. A region knows what
        shape it is; this asks it.

        Parameters
        ----------
        region : chisurf.core.roi.ROI
            Rectangle, ellipse/circle or polygon. A mask-backed region has no
            analytic outline and raises — draw it as an overlay instead.
        pen : pen-like
            Outline style.
        movable : bool
            Whether the user can drag/resize it. Default is **not**: a region
            drawn from a measurement is a result, and dragging one would claim
            to edit something the analysis owns.
        name : str, optional
            Unused by the backend; accepted so a caller can keep its own
            bookkeeping in one call.

        Returns
        -------
        handles.Roi

        Raises
        ------
        TypeError
            For a region with no analytic outline, naming the alternative.
        """
        from chisurf.core.roi import EllipseROI, PolygonROI, RectangleROI

        if isinstance(region, RectangleROI):
            x0, y0, x1, y1 = region.bounds()
            return self.add_roi(
                kind="rect", pos=(x0, y0), size=(x1 - x0, y1 - y0), pen=pen, movable=movable
            )
        if isinstance(region, EllipseROI):
            # pos/size are the bounding box, so the radii double. Getting this
            # wrong draws an ellipse half the size of the region it describes,
            # which looks plausible on every screenshot.
            return self.add_roi(
                kind="ellipse",
                pos=(region.cx - region.rx, region.cy - region.ry),
                size=(2.0 * region.rx, 2.0 * region.ry),
                pen=pen,
                movable=movable,
                angle=region.angle,
            )
        if isinstance(region, PolygonROI):
            return self.add_roi(
                kind="polygon", points=[tuple(v) for v in region.vertices], pen=pen, movable=movable
            )
        raise TypeError(
            f"{type(region).__name__} has no analytic outline to draw; "
            "show it with add_overlay(region.to_mask(shape)) instead"
        )

    def enable_picking(self, image_source=None, *, fit: str = "gaussian", window: int = 9) -> None:
        """Turn clicks into picked regions.

        The third way a region gets made — beside a batch detector and a drawn
        shape — offered here because it is a *gesture*, and a gesture belongs to
        the thing being clicked. Before this, every tool that wanted it reached
        past the plotting seam for the click and re-implemented the fit.

        The click is a **seed, not the answer**: it lands a pixel or two off
        centre, and a region built on it inherits that as a biased centroid.
        With ``fit="gaussian"`` the click selects a window, the brightest pixel
        in it seeds a 2-D Gaussian, and the fit decides where the spot is and
        how wide it is (:func:`chisurf.core.roi.fit_gaussian_spot`). A fit that
        does not converge emits a :class:`~chisurf.core.roi.PickedSpot` with
        ``success`` false and a reason, rather than a region placed where
        nothing was found.

        Parameters
        ----------
        image_source : callable, optional
            Returns the 2-D array to fit against. Defaults to whatever was last
            passed to :meth:`set_image`, which is right whenever the canvas is
            showing the data rather than a rendering of it.
        fit : str, optional
            ``"gaussian"`` to refine the click, or ``"none"`` to take it as-is
            (for a canvas whose pixels are not a picture of anything fittable).
        window : int, optional
            Side of the square the fit sees.

        Notes
        -----
        Connect to :attr:`picked` to receive each pick.
        """
        self._pick_fit = str(fit)
        self._pick_window = int(window)
        self._pick_image = image_source
        if not self._picking:
            self._picking = True
            self.clicked.connect(self._on_pick_click)

    def _on_pick_click(self, x: float, y: float) -> None:
        """Turn one click into a pick and emit it."""
        from chisurf.core.roi import PickedSpot, fit_gaussian_spot

        image = self._pick_image() if callable(self._pick_image) else self._last_image
        if image is None:
            return
        if self._pick_fit == "none":
            self.picked.emit(PickedSpot(y=float(y), x=float(x), success=True))
            return
        self.picked.emit(fit_gaussian_spot(np.asarray(image), y, x, window=self._pick_window))

    @property
    def native(self):
        """The backend image-view object (escape hatch; avoid in new code)."""
        return self._iv.native


class PanelPlot(Plot):
    """A :class:`Plot` bound to an existing grid-panel canvas.

    Constructed by :meth:`Grid.add_plot`; not instantiated directly. It shares
    :class:`Plot`'s full drawing/axis API but is not a standalone top-level
    widget (its canvas already lives inside a :class:`Grid`).
    """

    def __init__(self, canvas):
        # Bypass Plot.__init__ (which would create a fresh top-level canvas);
        # a panel is a QObject only for signal support and wraps an existing canvas.
        QtWidgets.QWidget.__init__(self)
        self._canvas = canvas
        self._host_widget = canvas.host.widget
        self._series = []
        self._extra_menu_actions = []
        # A panel is not a standalone widget, so chiplot's contextMenuEvent never
        # fires here — keep the backend's own menu for grid panels.
        self._context_menu_enabled = False
        self._native_menu = self._canvas.provides_native_menu()
        if self._native_menu:
            self._install_native_export_actions()
        self._canvas.on_click(lambda x, y, btn: self.clicked.emit(x, y) if btn == "left" else None)
