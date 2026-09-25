"""Burst Browser — an immediate-mode EMTK tool over :class:`BurstBrowserViewModel`.

Hosts :class:`~.gui.app.BurstBrowserApp` via :class:`emtk.qt_host.ControlHost` inside
a Qt widget, providing:
- Left pane: Data source (Open folder/file), detector & column selection, and Gating controls.
- Center pane: Paginated per-burst table with row selection.
- Right pane: Live histogram of the selected column with emtk.implot.
"""

from __future__ import annotations

import logging
import pathlib
from typing import Any

from emtk.qt_host import ControlHost
from qtpy import QtWidgets

from .gui.app import WINDOW_BG, BurstBrowserApp
from .view_model import BurstBrowserViewModel

# Plugin brand icon (unified emoji set) + hierarchical menu name.
icon = "📇"
name = "Spectroscopy:Single-Molecule:Burst Browser"

logger = logging.getLogger(__name__)


class BurstBrowserWidget(QtWidgets.QWidget):
    """Inspect burstwise ``.bur`` tables + ``…4`` companions (EMTK tool)."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Burst Browser")
        self.setMinimumSize(820, 560)

        self.model = BurstBrowserViewModel()

        self.app = BurstBrowserApp(
            model=self.model,
            on_open_folder=self._open_folder_dialog,
            on_open_file=self._open_file_dialog,
        )
        self.gui = self.app.browser_gui

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.host = ControlHost(self.app, background=WINDOW_BG[:3])
        layout.addWidget(self.host)

    # ── Guided Tour Hook ────────────────────────────────────────────────
    def tour_target(
        self, target: Any
    ) -> tuple[QtWidgets.QWidget, tuple[float, float, float, float]] | None:
        """Resolve a guided-tour target dict to an EMTK item screen rect."""
        if not isinstance(target, dict):
            return None
        name = target.get("name")
        rect = self.gui.item_rects.get(name) if name else None
        if rect is not None:
            return self.host, rect
        return None

    def _open_folder_dialog(self) -> None:
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Select folder with .bur files")
        if d:
            self.load_folder(pathlib.Path(d))

    def _open_file_dialog(self) -> None:
        f, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select burst file", filter="Burst Files (*.bur *.pto);;All Files (*)"
        )
        if f:
            p = pathlib.Path(f)
            if p.suffix == ".bur":
                self.load_bur(p)
            else:
                self.load_folder(p)

    # ── public API kept for the workflow shell (_apply_context_to_browser) ──
    @property
    def table(self):
        """The loaded burst table (or ``None``) — the shell checks this."""
        return self.model.table

    def load_folder(self, folder) -> None:
        """Load every ``.bur`` (+ companions) under *folder*."""
        self.model.load_folder(folder)

    def load_bur(self, path) -> None:
        """Load a single ``.bur`` file (+ companions)."""
        self.model.load_bur(path)


__all__ = ["BurstBrowserWidget", "BurstBrowserViewModel", "name"]


# Default plugin entry style used by ChiSurf.
if __name__ == "plugin":  # pragma: no cover - used by the plugin host
    widget = BurstBrowserWidget()
    widget.show()
