"""New-style GUI entrypoint for the Structure-to-Transfer (Trajectory→FRET) tool.

:class:`Structure2Transfer` is a thin :class:`~qtpy.QtWidgets.QWidget` wrapping a
single :class:`~chisurf.gui.autoform.AutoForm` bound to the Qt-free
:class:`~.view_model.FretTrajectoryViewModel` and laid out from
``structure2transfer.view.json``: the trajectory picker + read stride, the
donor/acceptor dipole atom-pair selectors (four
:class:`~chisurf.gui.widgets.pdb.PDBSelector` widgets), the dye parameters (R0,
tau0, dipole averaging, frame time-step) and the Process button with a live log.
Replaces the former ``structure2transfer.ui`` / hand-built grid layout. Mirrors
the Align-Trajectory tool.
"""

from __future__ import annotations

import logging

from qtpy import QtWidgets

from chisurf.gui.autoform import AutoForm

from . import sections  # noqa: F401  (side effect: register the custom sections)
from .view_model import FretTrajectoryViewModel

try:
    from chisurf.gui.misc_helpers import persist_plugin_state
except ImportError:  # pragma: no cover - persistence optional
    persist_plugin_state = lambda n: lambda c: c  # noqa: E731

logger = logging.getLogger(__name__)


@persist_plugin_state("fret_trajectory")
class Structure2Transfer(QtWidgets.QWidget):
    """Calculate FRET observables from a molecular-dynamics trajectory."""

    name = "Structure2Transfer"

    def __init__(self, parent=None, verbose: bool = False, **kwargs):
        super().__init__(parent)
        self.setWindowTitle("Structure2Transfer")
        self.setMinimumWidth(460)

        self.model = FretTrajectoryViewModel(verbose=verbose)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        self.auto_form = AutoForm(self.model)
        layout.addWidget(self.auto_form)

        self.model.add_observer(self._on_model_event)

    def _on_model_event(self, event: str) -> None:
        try:
            self.auto_form.sync_fields()
            self.auto_form.refresh_plots()
        except Exception:  # pragma: no cover - defensive
            logger.warning("Structure2Transfer: field sync failed", exc_info=True)

    # ── public API (delegates to the view-model) ────────────────────────
    @property
    def trajectory_file(self) -> str:
        """Path of the currently loaded trajectory (delegates to the view-model)."""
        return self.model.trajectory_file

    @trajectory_file.setter
    def trajectory_file(self, value: str) -> None:
        self.model.trajectory_file = value

    @property
    def donor(self) -> tuple:
        """Donor dipole atom-index pair (delegates to the view-model)."""
        return self.model.donor

    @property
    def acceptor(self) -> tuple:
        """Acceptor dipole atom-index pair (delegates to the view-model)."""
        return self.model.acceptor

    @property
    def t_step(self) -> float:
        """Trajectory frame time-step in ns (delegates to the view-model)."""
        return self.model.t_step

    @t_step.setter
    def t_step(self, value: float) -> None:
        self.model.t_step = value

    @property
    def stride(self) -> int:
        """Frame read-stride (delegates to the view-model)."""
        return self.model.stride

    @stride.setter
    def stride(self, value: int) -> None:
        self.model.stride = value

    @property
    def forster_radius(self) -> float:
        """Förster radius R0 (delegates to the view-model)."""
        return self.model.forster_radius

    @forster_radius.setter
    def forster_radius(self, value: float) -> None:
        self.model.forster_radius = value

    @property
    def tau0(self) -> float:
        """Donor fluorescence lifetime tau0 (delegates to the view-model)."""
        return self.model.tau0

    @tau0.setter
    def tau0(self, value: float) -> None:
        self.model.tau0 = value

    @property
    def dipoles(self) -> bool:
        """Dipole (kappa2) averaging flag (delegates to the view-model)."""
        return self.model.dipoles

    @dipoles.setter
    def dipoles(self, value: bool) -> None:
        self.model.dipoles = value


__all__ = ["Structure2Transfer"]
