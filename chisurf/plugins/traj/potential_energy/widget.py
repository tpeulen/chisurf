"""New-style GUI entrypoint for the Potential-Energy calculator.

:class:`PotentialEnergyWidget` is a thin :class:`~qtpy.QtWidgets.QWidget`
wrapping a single :class:`~chisurf.gui.autoform.AutoForm` bound to the Qt-free
:class:`~.view_model.PotentialEnergyViewModel` and laid out from
``calculate_potential.view.json``: the trajectory picker + potential editor +
Add button, the read stride, a table of the configured potentials, the Process
button and a live log. Replaces the former ``calculate_potential.ui`` /
hand-built grid layout. Mirrors the Align-Trajectory tool.
"""

from __future__ import annotations

import logging

from qtpy import QtWidgets

from chisurf.gui.autoform import AutoForm

from . import sections  # noqa: F401  (side effect: register the custom sections)
from .view_model import PotentialEnergyViewModel

try:
    from chisurf.gui.misc_helpers import persist_plugin_state
except ImportError:  # pragma: no cover - persistence optional
    persist_plugin_state = lambda n: lambda c: c  # noqa: E731

logger = logging.getLogger(__name__)


@persist_plugin_state("potential_energy")
class PotentialEnergyWidget(QtWidgets.QWidget):
    """Calculate potential-energy components across the frames of a trajectory."""

    name = "Potential-Energy calculator"

    def __init__(self, parent=None, verbose: bool = False, structure=None, **kwargs):
        super().__init__(parent)
        self.setWindowTitle("Potential energy calculator")
        self.setMinimumWidth(420)

        self.model = PotentialEnergyViewModel()
        if structure is not None:
            self.model.structure = structure

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
            logger.warning("PotentialEnergy: field sync failed", exc_info=True)

    # ── public properties (delegate to the view-model) ──────────────────
    @property
    def stride(self) -> int:
        """Frame read-stride (delegates to the view-model)."""
        return int(self.model.stride)

    @property
    def potential_number(self) -> int:
        """Index of the currently selected potential type (delegates to the view-model)."""
        return int(self.model.selected_potential_index)

    @property
    def potential_name(self) -> str:
        """Name of the currently selected potential type (delegates to the view-model)."""
        names = self.model.potential_names()
        index = int(self.model.selected_potential_index)
        return names[index] if 0 <= index < len(names) else ""

    @property
    def energy(self) -> float:
        """Total (scaled) energy of the configured potentials (delegates to the view-model)."""
        return self.model.energy()

    @property
    def trajectory_file(self) -> str:
        """Path of the currently loaded trajectory (delegates to the view-model)."""
        return self.model.trajectory_file

    @trajectory_file.setter
    def trajectory_file(self, value: str) -> None:
        """Set the trajectory path through the view-model (fires observers)."""
        self.model.set_trajectory(value)


__all__ = ["PotentialEnergyWidget"]
