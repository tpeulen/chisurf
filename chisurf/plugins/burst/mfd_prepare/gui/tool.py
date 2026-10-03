"""Qt host of the MFD preparation plugin (see /plugins/burst.md).

A dockable window that hosts the EMTK app in :mod:`.app` in a ``ControlHost``; the app owns the folder chooser, the
preparation run and the report (state and numbers in :mod:`.model`), and calls the API through the RPC client when one
is connected, otherwise in process.
"""

from __future__ import annotations

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

        from emtk.qt_host import ControlHost

        from .app import MfdPrepareApp
        from .model import MfdPrepareModel

        self.model = MfdPrepareModel(client=self._client)
        self.app = MfdPrepareApp(self.model)
        self.host = ControlHost(self.app, background=(30, 32, 38))
        self.setCentralWidget(self.host)

    @property
    def _folder(self) -> str:
        return self.model.folder

    @property
    def _report_text(self) -> str:
        return self.model.report
