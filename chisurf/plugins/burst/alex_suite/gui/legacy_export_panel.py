"""The ALEX-Suite CSV export of the legacy Qt shell, hosted in Qt.

The state and the export are :class:`.export_model.LegacyExportModel` (Qt-free, shared with the native hub); the
canvas is :class:`.app.LegacyExportApp`. This widget only hosts the canvas and keeps the Qt shell's hand-off names.
"""

from __future__ import annotations

from qtpy import QtWidgets

from .export_model import LegacyExportModel


class LegacyExportPanel(QtWidgets.QWidget):
    """Pick a burst file and write the ALEX-Suite five-file export (Qt host of the model)."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Build the export panel."""
        super().__init__(parent)
        self._workflow = parent
        self.model = LegacyExportModel()
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        from emtk.qt_host import ControlHost

        from .app import WINDOW_BG, LegacyExportApp

        self.app = LegacyExportApp(self.model)
        self.host = ControlHost(self.app, background=WINDOW_BG[:3])
        layout.addWidget(self.host, 1)

    def set_burst_files(self, files) -> None:
        """Adopt the burst files the pipeline produced."""
        self.model.set_burst_files(files)
        gui = self.app.export_gui
        gui.selected_index = min(gui.selected_index, max(0, len(self.model.bur_files) - 1))
        self.host.update()

    def run_export(self, source: str, sample: str, buffer: str, parts: dict) -> None:
        """Write the export beside the chosen burst file."""
        self.model.run_export(source, sample, buffer, parts)
        self.host.update()


__all__ = ["LegacyExportPanel"]
