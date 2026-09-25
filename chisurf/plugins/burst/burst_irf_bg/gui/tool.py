"""Immediate-mode EMTK tool for Burst IRF & Background.

Hosts :class:`~.app.BurstIrfBackgroundApp` via :class:`emtk.qt_host.ControlHost`,
providing dockable and draggable windows (Parameters, IRF Plot, Results Table)
and interactive baseline threshold adjustments.
"""

from __future__ import annotations

import logging
from typing import Any

from emtk.qt_host import ControlHost
from qtpy import QtCore, QtWidgets

from chisurf.gui import dialogs
from chisurf.gui.autoform import AutoForm

from . import sections  # noqa: F401  (side effect: register custom sections)
from .app import WINDOW_BG, BurstIrfBackgroundApp
from .view_model import IrfBackgroundViewModel

logger = logging.getLogger(__name__)


class BurstIrfBackgroundTool(QtWidgets.QWidget):
    """Per-detector IRF + background from non-burst photons (EMTK tool)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Burst IRF & Background")
        self.setMinimumSize(760, 560)

        self.model = IrfBackgroundViewModel()

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Retain AutoForm instance for test contracts and section registration
        self.auto_form = AutoForm(self.model)
        self.auto_form.setVisible(False)

        self.app = BurstIrfBackgroundApp(
            model=self.model,
            on_compute=self._compute,
            on_send_to_mle=self._send_to_mle,
        )
        self.gui = self.app.irf_gui

        self.host = ControlHost(self.app, background=WINDOW_BG[:3])
        layout.addWidget(self.host, 1)

        self.model.add_observer(self._on_model_event)

    def _compute(self) -> None:
        reason = self.model.can_compute()
        if reason is not None:
            self.gui.status_text = f"Cannot compute: {reason}"
            return
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            self.model.compute()
        except Exception as exc:
            dialogs.error(self, "Error", str(exc))
            self.gui.status_text = f"Error: {exc}"
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()

    def _send_to_mle(self) -> None:
        if not self.model.has_results():
            self.gui.status_text = "Compute the IRF and background first."
            return
        host = self.parent()
        while host is not None and not hasattr(host, "apply_irf_background_to_mle"):
            host = host.parent()
        if host is None:
            dialogs.information(
                self,
                "Send to MLE",
                "Open this tool inside the Burst Analysis workflow to feed the "
                "MLE lifetime fit. The IRF/background patterns are available via "
                "the tool's model for scripted use.",
            )
            return
        try:
            count = host.apply_irf_background_to_mle(self.model.mle_patterns())
            self.gui.status_text = f"Sent IRF + background to MLE for {count} detector(s)."
        except Exception as exc:
            dialogs.error(self, "Error", str(exc))

    def _on_model_event(self, event: str) -> None:
        try:
            self.auto_form.refresh_plots()
        except Exception:
            pass

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


__all__ = ["BurstIrfBackgroundTool"]
