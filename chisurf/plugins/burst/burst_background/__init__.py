"""Burst Background Estimation — an AutoForm tool over :class:`BackgroundViewModel`.

Thin :class:`~qtpy.QtWidgets.QWidget` wrapping a single
:class:`~chisurf.gui.autoform.AutoForm` bound to the Qt-free
:class:`~.view_model.BackgroundViewModel` and laid out from
``gui/background.view.json``: the detector channel-definition page, the TTTR file
list + Estimate action, the inter-photon-time distribution (points + fitted
tail), the per-detector background-rate bars and the results table — each a
draggable chisurf dock. The former hand-built tabbed widget now lives in
``view_model.py`` (logic) + ``gui/sections.py`` (Qt).
"""

from __future__ import annotations

import logging

from qtpy import QtWidgets

from .view_model import BackgroundViewModel

# Plugin brand icon (unified emoji set) + hierarchical menu name.
icon = "🌑"
name = "Spectroscopy:Single-Molecule:Burst Background Estimation"

logger = logging.getLogger(__name__)


class BurstBackgroundEstimator(QtWidgets.QWidget):
    """Per-detector background from burst analysis (AutoForm tool)."""

    def __init__(
        self, show_channel_definition: bool = True, parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Burst Background Estimation")
        self.setMinimumSize(820, 600)

        self.model = BackgroundViewModel(show_channel_definition=show_channel_definition)

        # Import AutoForm + register/build sections lazily so importing this
        # package for the Qt-free model never pulls the GUI chain.
        from chisurf.gui.autoform import AutoForm

        from .gui import sections

        # Always create the detector page (so the shell can push channels into it
        # even when the channels dock is hidden in the embedded workflow).
        sections.build_detector_page(self.model)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        self.auto_form = AutoForm(self.model)
        layout.addWidget(self.auto_form)

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
