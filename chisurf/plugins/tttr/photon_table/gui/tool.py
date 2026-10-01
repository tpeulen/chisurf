"""GUI entry point of the Photon Table plugin.

A dockable tool that opens a TTTR file and shows its photons in a paged,
channel-filterable table. The UI is the EMTK app in :mod:`.app`; this window
is its Qt host and owns the file dialog and the OS drop.
"""

from __future__ import annotations

import logging
from typing import Any

from qtpy import QtWidgets

from chisurf.core.support import i18n
from chisurf.gui.misc_helpers import persist_plugin_state
from chisurf.gui.widgets.tools import ChisurfDockTool

from ..core.model import PhotonTableModel

logger = logging.getLogger(__name__)


@persist_plugin_state("photon_table")
class PhotonTableTool(ChisurfDockTool):
    """Inspect the photons of a TTTR file in a table."""

    tool_settings_name = "PhotonTableTool"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.setWindowTitle(i18n.tr("Photon Table"))
        try:
            self.resize(1000, 640)
        except Exception:
            pass

        self._model = PhotonTableModel()
        self.first_index: int = 0
        self.rows_per_page: int = 200
        #: The routing channel shown (_CHANNEL_ANY = -1 for all).
        self.channel_filter: int = -1

        from emtk.qt_host import ControlHost

        from .app import WINDOW_BG, PhotonTableApp

        self.app = PhotonTableApp(self, on_browse=self._browse)
        self.host = ControlHost(self.app, background=WINDOW_BG[:3])
        self.setCentralWidget(self.host)

    # ── files ────────────────────────────────────────────────────────

    def _browse(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            i18n.tr("Open TTTR file"),
            "",
            "TTTR files (*.ptu *.phu *.ht2 *.ht3 *.pt3 *.t3r);;All files (*)",
        )
        if path:
            self.load_file(path)

    def load_file(self, path: str) -> None:
        """Open a TTTR file and show its photons, reset to the first page."""
        try:
            self._model.load_file(path)
        except Exception as exc:
            logger.warning("Photon Table: could not open %s — %s", path, exc)
            self.statusBar().showMessage(f"Could not open {path}: {exc}", 8000)
            return
        self.first_index = 0
        self.channel_filter = -1
        self.statusBar().showMessage(f"{self._model.n_photons:,} photons from {path}", 8000)
        self.host.update()

    def on_paths_dropped(self, paths) -> None:
        """A dropped TTTR file is opened."""
        if paths:
            self.load_file(str(paths[0]))
