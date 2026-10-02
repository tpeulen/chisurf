"""Burst-wise FCS correlator as a ChiSurf tool: the native emtk app (``gui/app.py``) hosted in a Qt window.

There is one implementation of the window, the emtk app. This class only gives it a window of the application's dock tools, keeps
the ``embedded`` flag the burst workflow shell passes, and exposes the app's controller and settings model to the code that hosts
it (the shell, the FCS toolbox).
"""

from __future__ import annotations

from emtk.qt_host import ControlHost

from chisurf.gui.glyphs import Glyphs
from chisurf.gui.widgets.tools.chisurf_dock_tool import ChisurfDockTool

from .app import create_app
from .view_model import _BurstFcsModel  # noqa: F401  (kept importable from here: the settings model of the window)

WINDOW_BG = (30, 32, 38)


class _InputList:
    """The file-list contract the burst workflow shell hands burst folders over (``checked_paths`` / ``add_paths``)."""

    def __init__(self, controller):
        self._controller = controller

    def checked_paths(self):
        return list(self._controller.checked_files())

    def paths(self):
        return list(self._controller.files)

    def add_paths(self, paths):
        self._controller.add_files([str(p) for p in paths])


class BurstFcsTool(ChisurfDockTool):
    """Modern burst-wise FCS correlator: the emtk app in a dock tool."""

    def __init__(self, parent=None, *, embedded: bool = False):
        """Build the correlator.

        Parameters
        ----------
        parent : QWidget, optional
            Host widget.
        embedded : bool, optional
            Hosted inside another tool (the burst workflow shell), which owns the window and its size.
        """
        super().__init__(parent)
        self._embedded = embedded
        self.setWindowTitle(f"{Glyphs.SCIENCE} Burst-wise FCS Correlator")
        if not embedded:
            self.resize(1100, 700)
        self.app = create_app()
        self.controller = self.app.controller
        self.file_list = _InputList(self.controller)
        self.host = ControlHost(self.app, background=WINDOW_BG)
        self.setCentralWidget(self.host)

    @property
    def _model(self):
        """The settings model of the window."""
        return self.controller._model

    @property
    def _curves(self):
        return self.controller._curves

    def closeEvent(self, event):
        self.app.close()
        super().closeEvent(event)
