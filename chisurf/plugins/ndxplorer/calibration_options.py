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
"""

from __future__ import annotations

import pathlib

_VIEW_JSON = pathlib.Path(__file__).parent / "calibration_options.view.json"

#: Factor name → the attribute holding whether it is applied.
FACTOR_ATTRS = {
    "alpha": "fit_alpha",
    "delta": "fit_delta",
    "gamma": "fit_gamma",
    "beta": "fit_beta",
    "r0": "fit_r0",
}


class CalibrationOptions:
    """The settings of one calibration run."""

    def __init__(self, donor_lifetime: float = 4.0) -> None:
        """Start from the window's own τ_D(0), and apply everything."""
        #: Leakage of donor emission into the acceptor channel.
        self.fit_alpha: bool = True
        #: Direct excitation of the acceptor by the donor laser.
        self.fit_delta: bool = True
        #: Detection efficiency × quantum yield ratio.
        self.fit_gamma: bool = True
        #: Excitation flux / cross-section ratio of the two lasers.
        self.fit_beta: bool = True
        #: Förster radius. Not a correction factor; the distances depend on it.
        self.fit_r0: bool = False
        #: Where the channel backgrounds come from. Not fitted — an input.
        self.background: str = "measurement"
        #: Which route γ comes from.
        self.gamma_source: str = "auto"
        #: Combine the data estimates with the light-path priors.
        self.use_priors: bool = True
        #: Bootstrap resamples for the factor uncertainties (0 skips them).
        self.n_bootstrap: int = 50
        #: Donor-only lifetime τ_D(0), ns — shapes the static FRET line.
        self.donor_lifetime: float = float(donor_lifetime)
        #: Linker width, Å.
        self.linker_sigma: float = 6.0
        #: Also add the accurate per-burst E / S / R_DA columns.
        self.inject_columns: bool = True

    def view_spec(self):
        """Resolve the AutoForm view spec from the authored view.json."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW_JSON)

    def factors(self) -> list[str]:
        """The factors the calibration may write, in the paper's order."""
        return [name for name, attr in FACTOR_ATTRS.items() if getattr(self, attr)]

    def as_kwargs(self) -> dict:
        """Keyword arguments for :func:`optimize_calibration_from_ndx`."""
        return {
            "factors": self.factors(),
            "background": str(self.background),
            "gamma_source": str(self.gamma_source),
            "use_priors": bool(self.use_priors),
            "n_bootstrap": int(self.n_bootstrap),
            "donor_lifetime": float(self.donor_lifetime),
            "linker_sigma": float(self.linker_sigma),
            "inject_columns": bool(self.inject_columns),
        }


def ask_calibration_options(parent, donor_lifetime: float = 4.0):
    """Show the options and return them, or ``None`` if the user cancelled."""
    from qtpy import QtWidgets

    from chisurf.gui.autoform import AutoForm

    options = CalibrationOptions(donor_lifetime=donor_lifetime)
    dialog = QtWidgets.QDialog(parent)
    dialog.setWindowTitle("Optimize FRET calibration")
    layout = QtWidgets.QVBoxLayout(dialog)
    layout.addWidget(AutoForm(options, dialog))
    buttons = QtWidgets.QDialogButtonBox(
        QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel, dialog)
    buttons.button(QtWidgets.QDialogButtonBox.Ok).setText("🎯 Calibrate")
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    if dialog.exec_() != QtWidgets.QDialog.Accepted:
        return None
    return options
