"""The Qt shell's dialog for the slow-storage staging settings.

The model and its spec are Qt-free (:mod:`chisurf.core.fio.staging_settings`);
this only hosts them in an AutoForm.
"""

from __future__ import annotations

from chisurf.core.fio.staging_settings import DataLoadingSettingsModel
from chisurf.gui import QtWidgets
from chisurf.gui.autoform import AutoForm


class DataLoadingSettingsWidget(QtWidgets.QWidget):
    """Renders :class:`DataLoadingSettingsModel` via :class:`AutoForm`."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = DataLoadingSettingsModel()
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        self.form = AutoForm(self.model, parent=self)
        layout.addWidget(self.form)
