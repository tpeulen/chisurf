"""chiplot's Qt host layer: :func:`host`, :class:`PanelHost` and :class:`ImagePanelHost`.

Everything that draws is in the toolkit-free core (:mod:`chisurf.chiplot`): a
:class:`~chisurf.chiplot.Panel`, a :class:`~chisurf.chiplot.PanelGrid` and an
:class:`~chisurf.chiplot.ImagePanel` are emtk controls there. This module only
*hosts* one in a legacy Qt form -- an ``emtk.qt_host.ControlHost`` attached
through the core's duck-typed host hook -- and adds what is Qt's: the
right-click menu with its file dialogs (exports painted by Qt, as the widget
shows them), the playback timer and the slider tooltip. It goes with the last Qt
form (``okf/subsystems/chiplot.md``); new code draws the panel on an emtk surface.
"""

from __future__ import annotations

from qtpy import QtCore, QtWidgets

from chisurf.chiplot.canvas import Panel, PanelGrid, PlotAPI, _Hook
from chisurf.chiplot.image_panel import ImagePanel

__all__ = [
    "ImagePanel",
    "ImagePanelHost",
    "Panel",
    "PanelGrid",
    "PanelHost",
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
    :class:`PanelHost` (with the panel's right-click menu), an
    :class:`~chisurf.chiplot.ImagePanel` an :class:`ImagePanelHost`; a
    :class:`~chisurf.chiplot.PanelGrid` or any other control a plain ``ControlHost``.

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
    if isinstance(panel, PanelGrid):
        return _hosted(panel.control(), parent)
    return _hosted(panel, parent)


def _export_qt(canvas, widget, path, width) -> bool:
    """Paint *canvas* into a ``QImage`` at *widget*'s size: what a Qt-hosted panel exports."""
    from emtk.qt_painter import QtPainter
    from qtpy import QtGui

    w, h = widget.width(), widget.height()
    scale = float(width) / max(w, 1) if width else 1.0
    image = QtGui.QImage(max(int(w * scale), 1), max(int(h * scale), 1), QtGui.QImage.Format_ARGB32)
    image.fill(QtGui.QColor(*canvas._background))
    painter = QtGui.QPainter(image)
    try:
        painter.scale(scale, scale)
        canvas.draw(QtPainter(painter), 0.0, 0.0, float(w), float(h))
    finally:
        painter.end()
    return bool(image.save(str(path)))
