"""① Compute LUT panel — an AutoForm host over :class:`LutComputeViewModel`.

The panel is now declarative: the layout lives in ``lut_compute.view.json`` and
the interactive raw/after TAC plots (draggable linear region + offset/threshold
lines) are the custom sections in :mod:`.sections`. This class only builds the
:class:`~chisurf.gui.autoform.AutoForm` over the Qt-free view-model and re-syncs
the parameter fields when a plot item is dragged.

``current_table`` (the computed LUT) stays accessible for the ①→② bridge in
:mod:`.tool` and for tests.
"""

from __future__ import annotations

import logging

from qtpy import QtWidgets

from chisurf.gui.autoform import AutoForm

from . import sections  # noqa: F401 — importing registers the custom sections
from .view_model import LutComputeViewModel

logger = logging.getLogger(__name__)


class TACLinearizationPanel(QtWidgets.QWidget):
    """Interactive Felekyan-style TAC LUT computation, rendered by AutoForm."""

    def __init__(self) -> None:
        """Build the AutoForm over a fresh compute view-model."""
        super().__init__()
        self.setWindowTitle("TAC Linearization")
        self.model = LutComputeViewModel()

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        self.auto_form = AutoForm(self.model)
        layout.addWidget(self.auto_form)

        # A dragged plot item updates the model + emits "fields"; re-sync the
        # value editors. The custom plot/label sections refresh themselves.
        self.model.add_observer(self._on_model_event)

    def _on_model_event(self, event: str) -> None:
        try:
            self.auto_form.sync_fields()
        except Exception:  # pragma: no cover - cosmetic sync
            logger.debug("LUT compute: field sync failed", exc_info=True)

    # ── LUT result access (used by the ①→② bridge and tests) ────────────
    @property
    def current_table(self):
        """The computed LUT table (or ``None``)."""
        return self.model.current_table

    @current_table.setter
    def current_table(self, value):
        self.model.current_table = value
