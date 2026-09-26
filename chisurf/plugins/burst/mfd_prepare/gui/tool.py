"""GUI tool for the MFD preparation plugin (see /plugins/burst.md).

A dockable tool that lets the user pick a burst folder, prepare it for MFD
analysis, and inspect the result (verified channels, count agreement, source
resolution, diagnostics). Calls the API via the RPC client — no direct core
imports in the GUI. The UI is the EMTK app in :mod:`.app`; this window is its
Qt host.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from qtpy import QtWidgets

from chisurf.gui.widgets.tools.chisurf_dock_tool import ChisurfDockTool

from .client import MfdPrepareClient

logger = logging.getLogger(__name__)


class MfdPrepareTool(ChisurfDockTool):
    """Dockable tool for preparing burst folders for MFD analysis."""

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        mmfdb_client: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent=parent, **kwargs)
        self.setWindowTitle("MFD Prepare")
        self._client = MfdPrepareClient(rpc_client=mmfdb_client)
        self._folder: str = ""
        self._report_text: str = ""

        from emtk.qt_host import ControlHost

        from .app import WINDOW_BG, MfdPrepareApp

        self.app = MfdPrepareApp(
            self,
            on_browse=self._browse_folder,
            on_prepare=self._prepare,
        )
        self.host = ControlHost(self.app, background=WINDOW_BG[:3])
        self.setCentralWidget(self.host)

    def _browse_folder(self) -> None:
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select burst folder")
        if folder:
            self._folder = folder
            self.host.update()

    def _prepare(self) -> None:
        if not self._folder:
            self._report_text = "Select a folder first."
            self.host.update()
            return
        self._report_text = "Preparing…"
        self.host.update()
        QtWidgets.QApplication.processEvents()
        try:
            if self._client._rpc is not None:
                result = self._client.prepare(self._folder)
            else:
                from ..api import prepare_folder
                from ..api.models import PrepareRequest

                result = prepare_folder(PrepareRequest(folder=self._folder)).to_dict()
            if result.get("error"):
                self._report_text = f"Error: {result['error']}"
            elif result.get("ok"):
                payload = result.get("result", result)
                self._report_text = payload.get(
                    "report", json.dumps(payload, indent=2, default=str)
                )
            else:
                self._report_text = result.get("report", json.dumps(result, indent=2, default=str))
        except Exception as exc:
            self._report_text = f"Error: {exc}"
        self.host.update()
