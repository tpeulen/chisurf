"""Burst Browser — an AutoForm tool over :class:`BurstBrowserViewModel`.

Thin :class:`~qtpy.QtWidgets.QWidget` wrapping a single
:class:`~chisurf.gui.autoform.AutoForm` bound to the Qt-free
:class:`~.view_model.BurstBrowserViewModel` and laid out from
``gui/burst_browser.view.json``: a Controls panel (open action, detector/column
combos, a foldable Gating box) plus the per-burst table and the histogram as
draggable chisurf docks. The former hand-built widget (table model, gating spin
boxes, histogram) now lives in ``gui/sections.py``.
"""

from __future__ import annotations

import logging

from qtpy import QtWidgets

from .view_model import BurstBrowserViewModel

# Plugin brand icon (unified emoji set) + hierarchical menu name.
icon = "📇"
name = "Spectroscopy:Single-Molecule:Burst Browser"

logger = logging.getLogger(__name__)


class BurstBrowserWidget(QtWidgets.QWidget):
    """Inspect burstwise ``.bur`` tables + ``…4`` companions (AutoForm tool)."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Burst Browser")
        self.setMinimumSize(820, 560)

        self.model = BurstBrowserViewModel()

        # Import AutoForm + register the custom sections lazily (only when the
        # widget is actually built) so importing this package — e.g. for the
        # Qt-free view-model — never pulls in the heavy GUI/settings chain.
        from chisurf.gui.autoform import AutoForm

        from .gui import sections  # noqa: F401  (side effect: register sections)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        self.auto_form = AutoForm(self.model)
        layout.addWidget(self.auto_form)

    # -- public API kept for the workflow shell (_apply_context_to_browser) ---
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
