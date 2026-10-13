"""chiplot's Qt host layer: :func:`host` with :class:`PanelHost` and :class:`ImagePanelHost`,
and the ``QWidget`` wrappers :class:`Plot` and :class:`Grid`.

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
from chisurf.chiplot.image_panel import ImagePanel

__all__ = [
    "Grid",
    "ImagePanel",
    "ImagePanelHost",
    "Panel",
    "PanelHost",
    "PanelPlot",
    "Plot",
    "PlotAPI",
    "_Hook",
    "host",
]


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


def _ask_and_export_csv(panel) -> None:
    """File dialog, then :meth:`~chisurf.chiplot.canvas.PlotAPI.export_csv`."""
    path, _ = QtWidgets.QFileDialog.getSaveFileName(
        None, "Export data as CSV", "", "CSV files (*.csv)"
    )
    if path:
        panel.export_csv(path)


def _ask_and_export_image(panel, widget) -> None:
    """File dialog, then the picture *widget* shows, painted by Qt."""
    path, _ = QtWidgets.QFileDialog.getSaveFileName(
        None, "Export image", "", "Images (*.png *.svg *.jpg)"
    )
    if path and not _export_qt(panel._canvas, widget, path, None):
        raise OSError(f"chiplot: the plot could not be exported to {path}")


def _show_panel_menu(panel, widget, parent, event) -> None:
    """chiplot's right-click menu for *panel*: export data/image, auto-range, its own entries."""
    if not panel._context_menu_enabled or getattr(panel, "_native_menu", False):
        event.ignore()
        return
    menu = QtWidgets.QMenu(parent)
    menu.addAction("Export data as CSV…", lambda: _ask_and_export_csv(panel))
    menu.addAction("Export image…", lambda: _ask_and_export_image(panel, widget))
    menu.addSeparator()
    menu.addAction("Auto-range", lambda: panel.autoscale())
    if panel._extra_menu_actions:
        menu.addSeparator()
        for label, cb in panel._extra_menu_actions:
            menu.addAction(label, cb)
    menu.exec_(event.globalPos())


class PanelHost(QtWidgets.QWidget):
    """A Qt widget that only hosts a toolkit-free :class:`~chisurf.chiplot.Panel`.

    The panel is drawn by emtk (an ``emtk.qt_host.ControlHost`` inside); the
    host adds what a Qt form expects of a plot widget: a size, and chiplot's
    right-click menu (export data, export image, auto-range and the panel's
    own :meth:`~chisurf.chiplot.canvas.PlotAPI.add_menu_action` entries). The
    panel's ``clicked`` / ``mouse_moved`` hooks are its own; connect to those.
    Built by :func:`host`.
    """

    def __init__(self, panel, parent=None) -> None:
        super().__init__(parent)
        self.panel = panel
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._host_widget = _hosted(panel.control())
        layout.addWidget(self._host_widget)

    def export_image(self, path: str, *, width: int | None = None) -> None:
        """Save the panel as this widget shows it, painted by Qt."""
        if not _export_qt(self.panel._canvas, self._host_widget, path, width):
            raise OSError(f"chiplot: the plot could not be exported to {path}")

    def contextMenuEvent(self, event):  # noqa: N802 (Qt override)
        """Show chiplot's right-click menu for the hosted panel."""
        _show_panel_menu(self.panel, self._host_widget, self, event)


class ImagePanelHost(QtWidgets.QWidget):
    """A Qt widget that only hosts a toolkit-free :class:`~chisurf.chiplot.ImagePanel`.

    The whole viewer (picture, colour ramp, frame slider) is one emtk control
    drawn in an ``emtk.qt_host.ControlHost``; the host adds the clock playback
    needs (a timer calling :meth:`~chisurf.chiplot.ImagePanel.advance` every
    :attr:`~chisurf.chiplot.ImagePanel.interval_ms` while it plays) and the
    slider's tooltip. Built by :func:`host`.
    """

    def __init__(self, panel, parent=None) -> None:
        super().__init__(parent)
        self.panel = panel
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        canvas = panel._iv.control()
        adapter = _QtHost(panel, background=canvas._background)
        self._host_widget = adapter.widget
        self._host_widget.installEventFilter(self)
        layout.addWidget(self._host_widget)
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(panel.advance)
        adapter.playing_changed = self._playing_changed
        panel.attach_host(adapter)
        panel.set_refresh_target(adapter.update)

    def _playing_changed(self, playing: bool) -> None:
        if playing:
            self._timer.start(self.panel.interval_ms)
        else:
            self._timer.stop()

    def eventFilter(self, watched, event):  # noqa: N802 (Qt override)
        """Show the tooltip of the part under the pointer (the frame slider's)."""
        if watched is self._host_widget and event.type() == QtCore.QEvent.ToolTip:
            tip = self.panel.tooltip_at(float(event.pos().x()), float(event.pos().y()))
            if tip:
                QtWidgets.QToolTip.showText(event.globalPos(), tip, self._host_widget)
                return True
            # Not the slider: the host's own tooltip (a caller's setToolTip) applies.
            return False
        return super().eventFilter(watched, event)


def host(panel, parent=None) -> QtWidgets.QWidget:
    """Host a toolkit-free chiplot panel (or a bare control) in a Qt layout.

    For a legacy Qt form: the panel stays an emtk control drawn by emtk, and the
    widget returned only hosts it. A :class:`~chisurf.chiplot.Panel` gets a
    :class:`PanelHost` (with the panel's right-click menu); any other control
    (an image view's canvas, a colour ramp, a grid) a plain ``ControlHost``.

    Parameters
    ----------
    panel : Panel or control
        A :class:`~chisurf.chiplot.Panel`, or any control with ``draw``.
    parent : QWidget, optional
        Qt parent.

    Returns
    -------
    QWidget
    """
    if isinstance(panel, Panel):
        return PanelHost(panel, parent)
    if isinstance(panel, ImagePanel):
        return ImagePanelHost(panel, parent)
    return _hosted(panel, parent)


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
        _ask_and_export_csv(self)

    def _on_export_image(self):
        """File-dialog + write for the image export menu action."""
        _ask_and_export_image(self, self._host_widget)

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
        _show_panel_menu(self, self._host_widget, self, event)


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
