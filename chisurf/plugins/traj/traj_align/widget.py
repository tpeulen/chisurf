"""New-style GUI entrypoint for the Align-Trajectory tool.

:class:`AlignTrajectoryWidget` is a thin :class:`~qtpy.QtWidgets.QWidget`
wrapping a single :class:`~chisurf.gui.autoform.AutoForm` bound to the Qt-free
:class:`~.view_model.AlignTrajectoryViewModel` and laid out from
``align_trajectory.view.json``: a trajectory picker + save button, the
atom-selection and stride controls, and a live log. Replaces the former
``align_trajectory.ui`` / hand-built grid layout. Mirrors the Save-Topology tool.
"""

from __future__ import annotations

import logging

import numpy as np
from qtpy import QtWidgets

from chisurf.gui.autoform import AutoForm

from . import sections  # noqa: F401  (side effect: register the custom section)
from .view_model import AlignTrajectoryViewModel

try:
    from chisurf.gui.misc_helpers import persist_plugin_state
except ImportError:  # pragma: no cover - persistence optional
    persist_plugin_state = lambda n: lambda c: c  # noqa: E731

logger = logging.getLogger(__name__)


@persist_plugin_state("traj_align")
class AlignTrajectoryWidget(QtWidgets.QWidget):
    """Superpose a trajectory onto its first frame and save it aligned."""

    @property
    def stride(self) -> int:
        """Frame read-stride (delegates to the view-model)."""
        return int(self.model.stride)

    @property
    def atom_list(self) -> np.ndarray:
        """Parsed atom-id array from the atom selection (delegates to the view-model)."""
        return self.model.atom_indices()

    @property
    def trajectory_filename(self) -> str:
        """Path of the currently loaded trajectory (delegates to the view-model)."""
        return self.model.trajectory_filename

    @trajectory_filename.setter
    def trajectory_filename(self, value: str) -> None:
        """Set the trajectory path through the view-model (fires observers)."""
        self.model.set_trajectory(value)

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent)
        self.setWindowTitle("Align trajectory")
        self.setMinimumWidth(420)

        self.model = AlignTrajectoryViewModel()

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
            logger.warning("AlignTrajectory: field sync failed", exc_info=True)


__all__ = ["AlignTrajectoryWidget"]
