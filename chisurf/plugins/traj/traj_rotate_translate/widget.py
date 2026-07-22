"""New-style GUI entrypoint for the Rotate/Translate-Trajectory tool.

:class:`RotateTranslateTrajectoryWidget` is a thin :class:`~qtpy.QtWidgets.QWidget`
wrapping a single :class:`~chisurf.gui.autoform.AutoForm` bound to the Qt-free
:class:`~.view_model.RotateTranslateViewModel` and laid out from
``rotate_translate.view.json``: a trajectory picker, a 3x3 rotation-matrix grid, a
3-field translation row, a save button, the read stride, and a live log. Replaces
the former ``rotate_translate_traj.ui`` / hand-built grid layout. Mirrors the
Align-Trajectory tool.
"""

from __future__ import annotations

import logging

import numpy as np
from qtpy import QtWidgets

from chisurf.gui.autoform import AutoForm

from . import sections  # noqa: F401  (side effect: register the custom section)
from .view_model import RotateTranslateViewModel

try:
    from chisurf.gui.misc_helpers import persist_plugin_state
except ImportError:  # pragma: no cover - persistence optional
    persist_plugin_state = lambda n: lambda c: c  # noqa: E731

logger = logging.getLogger(__name__)


@persist_plugin_state("traj_rotate_translate")
class RotateTranslateTrajectoryWidget(QtWidgets.QWidget):
    """Apply a rigid-body rotation and translation to a trajectory and save it."""

    @property
    def stride(self) -> int:
        """Frame read-stride (delegates to the view-model)."""
        return int(self.model.stride)

    @stride.setter
    def stride(self, value: int) -> None:
        """Set the frame read-stride through the view-model."""
        self.model.stride = int(value)

    @property
    def rotation_matrix(self) -> np.ndarray:
        """The 3x3 rotation matrix (delegates to the view-model)."""
        return self.model.rotation_matrix

    @rotation_matrix.setter
    def rotation_matrix(self, value) -> None:
        """Set the rotation matrix through the view-model (re-syncs the editors)."""
        self.model.set_rotation_matrix(value)

    @property
    def translation_vector(self) -> np.ndarray:
        """The raw 3-vector translation as entered (delegates to the view-model).

        Unlike the historic widget, this returns the raw entered values; the
        ``/10.0`` Angstrom convention is applied only where the vector is consumed
        in :meth:`~.view_model.RotateTranslateViewModel.save_rotated_translated`.
        """
        return self.model.translation_vector

    @translation_vector.setter
    def translation_vector(self, value) -> None:
        """Set the raw translation vector through the view-model (re-syncs the editors)."""
        self.model.set_translation_vector(value)

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
        self.setWindowTitle("Rotate and translate trajectories")
        self.setMinimumWidth(420)

        self.model = RotateTranslateViewModel()

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
            logger.warning("RotateTranslate: field sync failed", exc_info=True)


__all__ = ["RotateTranslateTrajectoryWidget"]
