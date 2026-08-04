"""New-style GUI entrypoint for the Burst IRF & Background tool.

:class:`BurstIrfBackgroundTool` is a thin :class:`~qtpy.QtWidgets.QWidget` wrapping
a single :class:`~chisurf.gui.autoform.AutoForm` bound to the Qt-free
:class:`~..view_model.IrfBackgroundViewModel` and laid out from
``irf_bg.view.json``: a persistent dock area with the channel-definition page, the
file list + parameters, the IRF plot and the results table. Mirrors the Count
Rate tool.
"""

from __future__ import annotations

import logging

from qtpy import QtWidgets

from chisurf.gui.autoform import AutoForm

from . import sections  # noqa: F401  (side effect: register the custom sections)
from .view_model import IrfBackgroundViewModel

logger = logging.getLogger(__name__)


class BurstIrfBackgroundTool(QtWidgets.QWidget):
    """Per-detector IRF + background from the non-burst photons (AutoForm tool)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Burst IRF & Background")
        self.setMinimumSize(760, 560)

        self.model = IrfBackgroundViewModel()

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        # The shared ``?`` + **Guide** pair, in a hairline strip above the form.
        # A plain ``QWidget`` with no toolbar of its own goes through the
        # free-function form of the seam.
        from chisurf.gui.widgets.tools.help_guide import attach_help_and_guide

        self.help_toolbar = QtWidgets.QToolBar("Help", self)
        self.help_toolbar.setMovable(False)
        self.help_toolbar.setFloatable(False)
        self.help_toolbar.setStyleSheet(
            "QToolBar { border: none; padding: 0px; spacing: 2px; }"
        )
        attach_help_and_guide(
            self,
            self.help_toolbar,
            title="Burst IRF & background — help",
            model=self.model,
        )
        layout.addWidget(self.help_toolbar)

        self.auto_form = AutoForm(self.model)
        layout.addWidget(self.auto_form)

        self.model.add_observer(self._on_model_event)

    def _on_model_event(self, event: str) -> None:
        try:
            self.auto_form.refresh_plots()
        except Exception:
            logger.warning("IRF/background: plot refresh failed", exc_info=True)


__all__ = ["BurstIrfBackgroundTool"]
