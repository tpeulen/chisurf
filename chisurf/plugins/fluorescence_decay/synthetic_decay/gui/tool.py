"""Synthetic decay generator — AutoForm GUI tool."""

from __future__ import annotations

from qtpy import QtWidgets

from .view_model import SyntheticDecayViewModel


class SyntheticDecayTool(QtWidgets.QWidget):
    """A thin QWidget hosting the AutoForm for the synthetic decay generator."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Synthetic Decay Generator")
        self.resize(720, 640)

        from chisurf.gui.autoform import AutoForm

        self.model = SyntheticDecayViewModel()
        self.form = AutoForm(self.model, parent=self)
        self.model._form = self.form

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self.form)


if __name__ == "plugin":  # pragma: no cover
    _tool = SyntheticDecayTool()
    _tool.show()
