"""New-style GUI entrypoint for the Join-Trajectories tool.

:class:`JoinTrajectoriesWidget` is a thin :class:`~qtpy.QtWidgets.QWidget`
wrapping a single :class:`~chisurf.gui.autoform.AutoForm` bound to the Qt-free
:class:`~.view_model.JoinTrajectoriesViewModel` and laid out from
``join_trajectories.view.json``: the two trajectory pickers + save button, the
join-mode radio pair, the per-trajectory reverse toggles, the read chunk size
and a live log. Replaces the former ``join_traj.ui`` / hand-built grid layout.
Mirrors the Align-Trajectory tool.
"""

from __future__ import annotations

import logging

from qtpy import QtWidgets

from chisurf.gui.autoform import AutoForm

from . import sections  # noqa: F401  (side effect: register the custom section)
from .view_model import JoinTrajectoriesViewModel

try:
    from chisurf.gui.misc_helpers import persist_plugin_state
except ImportError:  # pragma: no cover - persistence optional
    persist_plugin_state = lambda n: lambda c: c  # noqa: E731

logger = logging.getLogger(__name__)


@persist_plugin_state("traj_join")
class JoinTrajectoriesWidget(QtWidgets.QWidget):
    """Join or stack two trajectories and save the result to a new H5 trajectory."""

    @property
    def trajectory_filename_1(self) -> str:
        """Path of the first loaded trajectory (delegates to the view-model)."""
        return self.model.trajectory_filename_1

    @trajectory_filename_1.setter
    def trajectory_filename_1(self, value: str) -> None:
        """Set the first trajectory path through the view-model (fires observers)."""
        self.model.set_trajectory_1(value)

    @property
    def trajectory_filename_2(self) -> str:
        """Path of the second loaded trajectory (delegates to the view-model)."""
        return self.model.trajectory_filename_2

    @trajectory_filename_2.setter
    def trajectory_filename_2(self, value: str) -> None:
        """Set the second trajectory path through the view-model (fires observers)."""
        self.model.set_trajectory_2(value)

    @property
    def chunk_size(self) -> int:
        """Read chunk size in frames (delegates to the view-model)."""
        return int(self.model.chunk_size)

    @property
    def reverse_traj_1(self) -> bool:
        """Whether trajectory 1 is reversed in time (delegates to the view-model)."""
        return bool(self.model.reverse_traj_1)

    @property
    def reverse_traj_2(self) -> bool:
        """Whether trajectory 2 is reversed in time (delegates to the view-model)."""
        return bool(self.model.reverse_traj_2)

    @property
    def join_mode(self) -> str:
        """Join mode (``"time"`` or ``"atoms"``; delegates to the view-model)."""
        return self.model.join_mode

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent)
        self.setWindowTitle("Join trajectories")
        self.setMinimumWidth(420)

        self.model = JoinTrajectoriesViewModel()

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
            logger.warning("JoinTrajectories: field sync failed", exc_info=True)


__all__ = ["JoinTrajectoriesWidget"]
