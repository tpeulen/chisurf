"""GUI tool for the MFD preparation plugin (see /plugins/burst.md).

A dockable tool that lets the user pick a burst folder, prepare it for MFD
analysis, and inspect the result (verified channels, count agreement, source
resolution, diagnostics). Calls the API via the RPC client — no direct core
imports in the GUI.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
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
        self._setup_ui()

    def _setup_ui(self) -> None:
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        folder_row = QtWidgets.QHBoxLayout()
        self.folder_label = QtWidgets.QLabel("No folder selected")
        browse_btn = QtWidgets.QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_folder)
        prepare_btn = QtWidgets.QPushButton("Prepare")
        prepare_btn.clicked.connect(self._prepare)
        folder_row.addWidget(self.folder_label, stretch=1)
        folder_row.addWidget(browse_btn)
        folder_row.addWidget(prepare_btn)
        layout.addLayout(folder_row)

        self.result_text = QtWidgets.QPlainTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setPlaceholderText(
            "Select a burst folder and click Prepare to see the MFD preparation report."
        )
        layout.addWidget(self.result_text, stretch=1)

    def _browse_folder(self) -> None:
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select burst folder")
        if folder:
            self._folder = folder
            self.folder_label.setText(str(Path(folder).name))

    def _prepare(self) -> None:
        if not self._folder:
            self.result_text.setPlainText("Select a folder first.")
            return
        self.result_text.setPlainText("Preparing…")
        QtWidgets.QApplication.processEvents()
        try:
            if self._client._rpc is not None:
                result = self._client.prepare(self._folder)
            else:
                from ..api import prepare_folder
                from ..api.models import PrepareRequest

                result = prepare_folder(PrepareRequest(folder=self._folder)).to_dict()
            if result.get("error"):
                self.result_text.setPlainText(f"Error: {result['error']}")
            elif result.get("ok"):
                payload = result.get("result", result)
                self.result_text.setPlainText(
                    payload.get("report", json.dumps(payload, indent=2, default=str))
                )
            else:
                self.result_text.setPlainText(
                    result.get("report", json.dumps(result, indent=2, default=str))
                )
        except Exception as exc:
            self.result_text.setPlainText(f"Error: {exc}")
