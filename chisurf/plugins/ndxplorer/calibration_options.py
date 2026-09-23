"""What the FRET calibration is allowed to determine, before it runs.

The toolbar button used to take every default and apply every factor, which is
the right thing exactly once — the first time, on a measurement that carries its
own donor-only and acceptor-only populations. After that it is usually wrong in
one specific way: γ from a measurement's own populations is only as good as
those populations, and somebody who determined γ properly on a reference sample
wants α and δ fitted *around* it rather than replaced by a worse estimate.

So the factors are a choice, and so is the route γ comes from. The calibration
is still run in full whatever is chosen — the report says what every factor came
out as — but only the selected ones are written into the window.

The options and their form belong to ndX
(:mod:`ndxplorer.analysis.fret_calibration`), because its emtk app asks the
same question; this module only shows them in the Qt window, through AutoForm.
"""

from __future__ import annotations

from ndxplorer.analysis.fret_calibration import FACTOR_ATTRS, OPTIONS_SPEC
from ndxplorer.analysis.fret_calibration import CalibrationOptions as _Options

__all__ = ["CalibrationOptions", "FACTOR_ATTRS", "ask_calibration_options"]


class CalibrationOptions(_Options):
    """ndX's calibration options, with the view spec AutoForm resolves."""

    def view_spec(self):
        """Resolve the AutoForm view spec from ndX's options form."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(OPTIONS_SPEC)


def ask_calibration_options(parent, donor_lifetime: float = 4.0):
    """Show the options and return them, or ``None`` if the user cancelled."""
    from qtpy import QtWidgets

    from chisurf.gui.autoform import AutoForm

    options = CalibrationOptions(donor_lifetime=donor_lifetime)
    dialog = QtWidgets.QDialog(parent)
    dialog.setWindowTitle("FRET calibration")
    layout = QtWidgets.QVBoxLayout(dialog)
    layout.addWidget(AutoForm(options, dialog))
    buttons = QtWidgets.QDialogButtonBox(
        QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel, dialog
    )
    buttons.button(QtWidgets.QDialogButtonBox.Ok).setText("🎯 Calibrate")
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    if dialog.exec_() != QtWidgets.QDialog.Accepted:
        return None
    return options
