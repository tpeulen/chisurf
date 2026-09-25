"""Burst Background Estimation — an immediate-mode EMTK tool over :class:`BackgroundViewModel`.

Hosts :class:`~.gui.app.BurstBackgroundApp` via :class:`emtk.qt_host.ControlHost` inside
a Qt widget, providing:
- Dockable and draggable windows (Parameters, Inter-photon Time Distribution, Rate Bars, Results).
- Interactive draggable tail-fit window (:func:`implot.drag_rect`) and region dropping.
- Per-detector background rates and export to burst containers.
"""

from __future__ import annotations

import logging
from typing import Any

from emtk.qt_host import ControlHost
from qtpy import QtWidgets

from .gui import sections
from .gui.app import WINDOW_BG, BurstBackgroundApp
from .view_model import BackgroundViewModel

# Plugin brand icon (unified emoji set) + hierarchical menu name.
icon = "🌑"
name = "Spectroscopy:Single-Molecule:Burst Background Estimation"

# The packaged console script.
cli_entrypoint = "burst-background=chisurf.plugins.burst.burst_background.cli:cli"

logger = logging.getLogger(__name__)


class BurstBackgroundEstimator(QtWidgets.QWidget):
    """Per-detector background from burst analysis (EMTK tool)."""

    def __init__(
        self, show_channel_definition: bool = True, parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Burst Background Estimation")
        self.setMinimumSize(820, 600)

        self.model = BackgroundViewModel(show_channel_definition=show_channel_definition)

        # Always build the detector page so the shell can push channels into it.
        sections.build_detector_page(self.model)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.app = BurstBackgroundApp(model=self.model, on_estimate=self._estimate)
        self.gui = self.app.bg_gui

        self.host = ControlHost(self.app, background=WINDOW_BG[:3])
        layout.addWidget(self.host, 1)

        # Proxy action button for workflow shell discovery
        self.toolAction_run = QtWidgets.QToolButton(self)
        self.toolAction_run.setObjectName("toolAction_run")
        self.toolAction_run.setVisible(False)
        self.toolAction_run.clicked.connect(self._estimate)

        # Hidden QListWidget for compatibility with tests inspecting file lists
        self._list_widget = QtWidgets.QListWidget(self)
        self._list_widget.setVisible(False)

        self.model.add_observer(self._on_model_event)

    def _estimate(self) -> None:
        try:
            self.model.estimate()
        except Exception:
            pass

    def _on_model_event(self, event: str) -> None:
        """Sync internal lists on model changes."""
        if event in ("files", "computed"):
            self._list_widget.clear()
            for f in self.model.files:
                self._list_widget.addItem(f)

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

    # -- API kept for the workflow shell (_apply_context_to_background) --------
    @property
    def detector_wizard_page(self):
        """The detector channel-definition page (always present)."""
        return self.model.detector_wizard_page

    @property
    def tttr_files(self):
        """The loaded TTTR file paths."""
        return self.model.files

    def _add_tttr_files(self, paths) -> None:
        """Add TTTR files (used by the shell to push the selected raw files)."""
        self.model.add_files(list(paths))
        self._list_widget.clear()
        for f in self.model.files:
            self._list_widget.addItem(f)


__all__ = ["BurstBackgroundEstimator", "BackgroundViewModel", "name"]


if __name__ == "__main__":  # pragma: no cover - manual GUI entry
    import sys

    app = QtWidgets.QApplication(sys.argv)
    window = BurstBackgroundEstimator()
    window.show()
    sys.exit(app.exec())
elif __name__ == "plugin":  # pragma: no cover - used by the plugin host
    window = BurstBackgroundEstimator()
    window.show()
