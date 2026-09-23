"""Global View: the parameter network of every open fit, and the links in it.

The window is one emtk surface (:class:`.surface.GlobalViewSurface`) over one
Qt-free model (:class:`.model.GlobalViewModel`); this module only hosts it.
What Qt still does here is what a host does -- a top-level window that
remembers its geometry, the file dialogs, a warning box, the help modal and the
guided tour, and the fit events, which arrive off the GUI thread and are
coalesced before the model is told.

The window this replaces was a dock area of four hand-built Qt panels around
the emtk network: a toolbar of ``QToolButton``\\ s, a ``QFormLayout`` of view
settings, a scroll area of per-parameter editor widgets, and an AutoForm-hosted
Qt table. All four are now sections of ``globalview.view.json``.
"""

from __future__ import annotations

import pathlib
from typing import Any

from qtpy import QtCore, QtWidgets

from chisurf import logging
from chisurf.gui.widgets.tools.chisurf_dock_tool import ChisurfDockTool
from chisurf.plugins.core.globalview.gui.model import GRAPH_LAYOUTS, GlobalViewModel
from chisurf.plugins.core.globalview.gui.surface import GlobalViewSurface

try:
    from chisurf.gui.misc_helpers import persist_plugin_state
except ImportError:

    def persist_plugin_state(n):
        return lambda c: c


__all__ = ["GRAPH_LAYOUTS", "GraphWizard", "REFRESH_DEBOUNCE_MS"]

_GUI_DIR = pathlib.Path(__file__).parent

#: How long a burst of change events is allowed to settle before the model
#: re-reads the fits. A running fit emits a parameter event per iteration.
REFRESH_DEBOUNCE_MS = 300


@persist_plugin_state("globalview")
class GraphWizard(ChisurfDockTool):
    """The Global View window: a host for the emtk surface.

    Parameters
    ----------
    fit_list : list, optional
        The fits to show; the session's, re-read on every refresh, by default.
    connect_owners, include_fixed : bool
        Initial values of the two view settings.

    Attributes
    ----------
    model : GlobalViewModel
    surface : GlobalViewSurface
    host : QWidget
        The emtk control host, the window's central widget.
    """

    #: Emitted with a field's ``attr`` or a button's ``action`` when the user
    #: uses it -- what a guided tour step waits on.
    tour_used = QtCore.Signal(str)

    def __init__(
        self,
        fit_list: list[Any] | None = None,
        parent=None,
        connect_owners: bool = False,
        include_fixed: bool = False,
        *args,
        **kwargs,
    ):
        super().__init__(parent)
        from emtk.docking import LayoutStore
        from emtk.qt_host import ControlHost

        self.setWindowTitle("Global View — parameter network")
        self.resize(1150, 760)

        fits = (lambda: list(fit_list)) if fit_list is not None else None
        self.model = GlobalViewModel(fits=fits)
        self.model.connect_owners = bool(connect_owners)
        self.model.include_fixed = bool(include_fixed)
        self.model.ask_open_path = self._ask_open_path
        self.model.ask_save_path = self._ask_save_path
        self.model.warn = self._warn
        self.model.open_help = self.show_help
        self.model.open_guide = self.show_guide
        self.model.rebuild(force=True)

        store = None
        try:
            from chisurf.core.settings import chisurf_settings_path

            store = LayoutStore("globalview", path=chisurf_settings_path / "globalview_layout.json")
        except Exception:  # noqa: BLE001 - no settings folder: the layout is not kept
            store = None
        self.surface = GlobalViewSurface(self.model, store=store, on_used=self.tour_used.emit)
        self.host = ControlHost(self.surface, background=(30, 32, 38))
        self.host.setObjectName("globalview_surface")
        self.setCentralWidget(self.host)

        self._refresh_timer = QtCore.QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(REFRESH_DEBOUNCE_MS)
        self._refresh_timer.timeout.connect(self._refresh_if_visible)
        self._stale_while_hidden = False
        self._subscription_tokens: list = []

        self.restore_window_geometry()
        self._connect_events()

    # -- what the model asks of its host -----------------------------------

    def _ask_open_path(self, title: str, file_filter: str) -> str:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, title, "", file_filter)
        return str(path or "")

    def _ask_save_path(self, title: str, file_filter: str) -> str:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, title, "", file_filter)
        return str(path or "")

    def _warn(self, title: str, message: str) -> None:
        from chisurf.gui import dialogs

        dialogs.warning(self, title, message)

    def show_help(self) -> None:
        """The help modal, the one the ``?`` of every tool opens."""
        from chisurf.gui.autoform.sections.help_section import HelpButton

        button = HelpButton(
            None, resource=str(_GUI_DIR / "help.md"), title="Global View — help", align="none"
        )
        button.setParent(self, QtCore.Qt.Widget)
        button.hide()
        button.show_help()

    def show_guide(self) -> None:
        """Walk through the window: each step lights one real control."""
        from chisurf.gui.widgets.tools.guided_tour import GuidedTour, load_tour

        tour = getattr(self, "_guided_tour", None)
        if tour is not None:
            tour.stop()
        tour = GuidedTour(self, load_tour(_GUI_DIR / "guide.json"), model=self.model)
        self._guided_tour = tour
        tour.start()

    def tour_target(self, target: dict) -> tuple | None:
        """Where a guide step's control is: ``(widget, rect in that widget)``.

        A step names a control the way the view spec does -- a field's
        ``attr``, a button's ``action`` -- or a dock by its title (``tab``).
        The dock holding it is brought to the front first, and the rectangle
        is last frame's, so the host is repainted before it is read.
        """
        name = str(
            target.get("attr")
            or target.get("action")
            or target.get("tab")
            or target.get("panel")
            or ""
        )
        if not name:
            return None
        self.surface.reveal(name)
        self.host.repaint()
        rect = self.surface.rect_of(name)
        if rect is None:
            return None
        x, y, w, h = rect
        return self.host, QtCore.QRect(int(x), int(y), int(w), int(h))

    # -- fit events ---------------------------------------------------------

    def _connect_events(self) -> None:
        """Re-read the fits when one of them, or a parameter, changes."""
        from chisurf.gui.widgets.fitting.fitting_client import get_fitting_client

        fc = get_fitting_client()
        if fc is None:
            return
        for topic in ("fit.", "parameter."):
            # Off the GUI thread, possibly: bounced through the event loop,
            # then coalesced by the timer.
            def callback(*_args, **_kwargs):
                return QtCore.QTimer.singleShot(0, self._refresh_timer.start)

            fc.subscribe(topic, callback)
            self._subscription_tokens.append((topic, callback))

    def _refresh_if_visible(self) -> None:
        if not self.isVisible():
            self._stale_while_hidden = True
            return
        self.model.fits_changed()
        self.host.update()

    def showEvent(self, event) -> None:  # noqa: N802 (Qt)
        """Catch up on changes that arrived while the window was hidden."""
        super().showEvent(event)
        if self._stale_while_hidden:
            self._stale_while_hidden = False
            self.model.fits_changed()
            self.host.update()

    def closeEvent(self, event):  # noqa: N802 (Qt)
        """Unsubscribe, and remember the geometry and the docks."""
        from chisurf.gui.widgets.fitting.fitting_client import get_fitting_client

        fc = get_fitting_client()
        if fc is not None:
            for topic, callback in self._subscription_tokens:
                try:
                    fc.unsubscribe(topic, callback)
                except Exception:  # noqa: BLE001
                    pass
        try:
            self.surface.docks.save()
        except Exception as exc:  # noqa: BLE001
            logging.log(0, f"globalview: could not save the dock layout ({exc})")
        self.save_window_geometry()
        super().closeEvent(event)


if __name__ == "plugin":
    graph_wiz = GraphWizard()
    graph_wiz.show()

if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication(sys.argv)
    app.aboutToQuit.connect(app.deleteLater)
    graph_wiz = GraphWizard()
    graph_wiz.show()
    sys.exit(app.exec_())
