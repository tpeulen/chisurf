"""New-style GUI entrypoint for the MD-Converter (trajectory converter) tool.

:class:`MDConverter` is a thin :class:`~qtpy.QtWidgets.QWidget` wrapping a single
:class:`~chisurf.gui.autoform.AutoForm` bound to the Qt-free
:class:`~.view_model.MDConverterViewModel` and laid out from
``convert_structures.view.json``: the input file rows + folder/frame controls,
the output base name / extension / split controls, the ``▶ Convert`` action and a
live log. Replaces the former ``convert_structures.ui`` / hand-built grid layout.
Mirrors the Save-Topology / Align-Trajectory tools.
"""

from __future__ import annotations

import logging

from qtpy import QtWidgets

from chisurf.gui.autoform import AutoForm

from . import sections  # noqa: F401  (side effect: register the custom sections)
from .view_model import MDConverterViewModel

try:
    from chisurf.gui.misc_helpers import persist_plugin_state
except ImportError:  # pragma: no cover - persistence optional
    persist_plugin_state = lambda n: lambda c: c  # noqa: E731

logger = logging.getLogger(__name__)


@persist_plugin_state("traj_convert")
class MDConverter(QtWidgets.QWidget):
    """Convert a molecular-dynamics trajectory between supported formats."""

    name = "MC-Converter"

    def __init__(self, parent=None, *args, **kwargs):
        super().__init__(parent)
        self.setWindowTitle("Trajectory-converter")
        self.setMinimumWidth(420)

        self.model = MDConverterViewModel()

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
            logger.warning("MDConverter: field sync failed", exc_info=True)

    # ── delegating properties (public API preserved from the legacy widget) ──
    @property
    def topology_file(self):
        """Topology path if it is an existing file, else ``None`` (delegates)."""
        return self.model.topology_file

    @topology_file.setter
    def topology_file(self, value) -> None:
        """Set the topology path through the view-model (fires observers)."""
        self.model.set_topology(value)

    @property
    def trajectory(self) -> str:
        """Input trajectory path/folder (delegates to the view-model)."""
        return self.model.trajectory

    @trajectory.setter
    def trajectory(self, value) -> None:
        """Set the input trajectory through the view-model (fires observers)."""
        self.model.set_trajectory(value)

    @property
    def target_directory(self) -> str:
        """Output directory (delegates to the view-model)."""
        return self.model.target_directory

    @target_directory.setter
    def target_directory(self, value) -> None:
        """Set the output directory through the view-model (fires observers)."""
        self.model.set_target_directory(value)

    @property
    def use_folder(self) -> bool:
        """Whether the input is a folder of PDBs (delegates to the view-model)."""
        return bool(self.model.use_folder)

    @property
    def first_frame(self) -> int:
        """First frame of the processed range (delegates to the view-model)."""
        return int(self.model.first_frame)

    @property
    def last_frame(self) -> int:
        """Last frame of the processed range (delegates to the view-model)."""
        return int(self.model.last_frame)

    @property
    def stride(self) -> int:
        """Frame read-stride (delegates to the view-model)."""
        return int(self.model.stride)

    @property
    def filename(self) -> str:
        """Output base name (delegates to the view-model)."""
        return str(self.model.filename)

    @property
    def ending(self) -> str:
        """Output file extension (delegates to the view-model)."""
        return str(self.model.ending)

    @property
    def split(self) -> bool:
        """Whether each frame is written to its own file (delegates)."""
        return bool(self.model.split)


__all__ = ["MDConverter"]
