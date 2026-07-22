"""New-style GUI entrypoint for the Remove-Clashed-Frames tool.

:class:`RemoveClashedFrames` is a thin :class:`~qtpy.QtWidgets.QWidget` wrapping
a single :class:`~chisurf.gui.autoform.AutoForm` bound to the Qt-free
:class:`~.view_model.RemoveClashesViewModel` and laid out from
``remove_clashes.view.json``: a trajectory picker + save button, the
atom-selection, stride and minimum-distance controls, and a live log. Replaces
the former ``remove_clashes.ui`` / hand-built grid layout. Mirrors the
Align-Trajectory tool.
"""

from __future__ import annotations

import logging

from qtpy import QtWidgets

from chisurf.gui.autoform import AutoForm

from . import sections  # noqa: F401  (side effect: register the custom section)
from .view_model import RemoveClashesViewModel

try:
    from chisurf.gui.misc_helpers import persist_plugin_state
except ImportError:  # pragma: no cover - persistence optional
    persist_plugin_state = lambda n: lambda c: c  # noqa: E731

logger = logging.getLogger(__name__)


@persist_plugin_state("traj_remove_clashes")
class RemoveClashedFrames(QtWidgets.QWidget):
    """Drop frames containing steric clashes from a trajectory and save the rest."""

    @property
    def stride(self) -> int:
        """Frame read-stride (delegates to the view-model)."""
        return int(self.model.stride)

    @property
    def atom_list(self) -> str:
        """Raw mdtraj atom-selection expression (delegates to the view-model)."""
        return str(self.model.atom_selection)

    @property
    def min_distance(self) -> float:
        """Consumed clash threshold, i.e. the raw spin value divided by ten.

        Mirrors the former widget's ``min_distance`` getter (delegates to the
        view-model's :meth:`~.view_model.RemoveClashesViewModel.min_distance_nm`).
        """
        return self.model.min_distance_nm()

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
        self.setWindowTitle("Remove clashed frames")
        self.setMinimumWidth(420)

        self.model = RemoveClashesViewModel()

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
            logger.warning("RemoveClashedFrames: field sync failed", exc_info=True)


__all__ = ["RemoveClashedFrames"]
