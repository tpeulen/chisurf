"""The ChiSurf tool window around the emtk ebFRET window.

A ``QMainWindow`` whose central widget is emtk's ``ControlHost`` drawing
:class:`~chisurf.plugins.burst.burst_ebfret.gui.app.App`, with ChiSurf's slim
toolbar on top: *Load demo* on the left, **Guide** and ``?`` on the right.

The guided tour spotlights Qt widgets, and the controls of an emtk window are
not widgets. So the tool keeps one invisible, pointer-transparent
:class:`TourAnchor` per named emtk control, moved over the control's last drawn
rectangle every frame and emitting ``clicked`` when the control is used. A tour
step names an anchor (``{"name": "ebfret_run"}``) exactly as it names any
other button, and waits on it the same way.
"""

from __future__ import annotations

from qtpy import QtCore, QtWidgets

from chisurf.gui.widgets.tools.help_guide import HelpGuideMixin

from ..api.client import EbfretClient
from .app import WINDOW_BG, App, EbfretGui

__all__ = ["EbfretTool", "TourAnchor", "ANCHORS"]

#: Controls a tour may point at: anchor object name -> the emtk control key.
ANCHORS = {
    "ebfret_menu_file": "menu.File",
    "ebfret_menu_analysis": "menu.Analysis",
    "ebfret_menu_view": "menu.View",
    "ebfret_plot_signal": "plot.signal",
    "ebfret_plot_raw": "plot.raw",
    "ebfret_series_slider": "series_value.slider",
    "ebfret_series_edit": "series_value.edit",
    "ebfret_crop_min": "crop_min",
    "ebfret_crop_max": "crop_max",
    "ebfret_exclude": "exclude",
    "ebfret_plot_obs": "plot.obs",
    "ebfret_plot_mean": "plot.mean",
    "ebfret_plot_noise": "plot.noise",
    "ebfret_plot_dwell": "plot.dwell",
    "ebfret_states_slider": "ensemble_value.slider",
    "ebfret_min_states": "min_states",
    "ebfret_max_states": "max_states",
    "ebfret_run_all": "run_scope",
    "ebfret_restarts": "restarts",
    "ebfret_precision": "run_precision",
    "ebfret_run": "run",
    "ebfret_stop": "stop",
    "ebfret_reset": "reset",
}


class TourAnchor(QtWidgets.QWidget):
    """An invisible stand-in for one emtk control, for the guided tour.

    Attributes
    ----------
    clicked : Signal
        Emitted when the control it stands for is used.
    """

    clicked = QtCore.Signal()

    def __init__(self, name: str, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)
        self.setObjectName(name)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        self.resize(1, 1)


class EbfretTool(HelpGuideMixin, QtWidgets.QMainWindow):
    """ebFRET, as a ChiSurf tool.

    Parameters
    ----------
    parent : QWidget, optional
        Parent widget.
    client : object, optional
        An RPC client for a ChiSurf server; in-process by default.
    """

    help_title = "ebFRET"

    def __init__(self, parent: QtWidgets.QWidget | None = None, client=None) -> None:
        super().__init__(parent)
        from emtk.qt_host import ControlHost

        self.setWindowTitle("ebFRET")
        self.client = EbfretClient(client)
        self.gui = EbfretGui(self.client)
        self.app = App(self.gui, on_exit=self.close)
        self.host = ControlHost(self.app, background=WINDOW_BG[:3])
        self.host.setMinimumSize(900, 600)
        self.setCentralWidget(self.host)

        toolbar = QtWidgets.QToolBar("ebFRET", self)
        toolbar.setObjectName("ebfret_toolbar")
        toolbar.setMovable(False)
        demo = toolbar.addAction("Load demo")
        demo.setToolTip("Simulate a four-state donor/acceptor dataset and load it")
        demo.triggered.connect(self._load_demo)
        self.addToolBar(toolbar)
        self.ensure_help_toolbar(toolbar=toolbar)

        self.anchors = {name: TourAnchor(name, self.host) for name in ANCHORS}
        self._keys = {key: name for name, key in ANCHORS.items()}
        self.gui.on_used = self._used

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(50)
        self.resize(1200, 800)

    def _load_demo(self) -> None:
        self.gui.load_demo()
        self.host.update()

    def _used(self, key: str) -> None:
        name = self._keys.get(key)
        if name is not None:
            self.anchors[name].clicked.emit()

    def _tick(self) -> None:
        """Repaint, and keep the tour anchors over their controls."""
        self.host.update()
        for name, key in ANCHORS.items():
            rect = self.gui.item_rects.get(key)
            if rect:
                x, y, w, h = rect
                self.anchors[name].setGeometry(int(x), int(y), max(int(w), 1), max(int(h), 1))

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt's spelling
        """Stop the timer and release the backend session."""
        self.timer.stop()
        try:
            self.client.close()
        finally:
            super().closeEvent(event)
