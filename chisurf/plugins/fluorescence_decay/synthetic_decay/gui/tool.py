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
        # A hairline strip for the ``?`` and **Guide** pair: this is a plain
        # QWidget with no toolbar, so the buttons would otherwise land inside
        # the form.
        from chisurf.gui.widgets.tools.help_guide import (
            attach_help_and_guide,
            promote_to_toolbar,
        )

        toolbar = QtWidgets.QToolBar(self)
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setStyleSheet("QToolBar { border: none; padding: 0px; spacing: 2px; }")
        # Generate and Save act on the whole tool, so they belong on the strip.
        # Add / Remove / Load stay put: they act on the lifetime-spectrum table
        # and mean nothing away from it.
        promote_to_toolbar(self.form, toolbar, ("generate", "save"))
        attach_help_and_guide(
            self, toolbar, title="Synthetic decay generator — help", model=self.model
        )
        layout.addWidget(toolbar)
        layout.addWidget(self.form)


if __name__ == "plugin":  # pragma: no cover
    _tool = SyntheticDecayTool()
    _tool.show()
