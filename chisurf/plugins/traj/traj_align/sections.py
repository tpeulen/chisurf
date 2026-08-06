"""Custom AutoForm section for the Align-Trajectory tool.

The trajectory and topology pickers (``…`` browse + drag-drop) and the
``💾 Save aligned…`` action button are a bespoke Qt widget registered here; the
atom selection, stride and log are plain built-in sections in
``align_trajectory.view.json``. The widget owns only Qt concerns and drives the
Qt-free :class:`~.view_model.AlignTrajectoryViewModel`. Imported (and thus
registered) by ``widget``. Mirrors the Save-Topology ``traj_save_topology_io``
pattern.
"""

from __future__ import annotations

import logging
import pathlib

from qtpy import QtCore, QtGui, QtWidgets

from chisurf.gui.autoform.sections.registry import register_section
from chisurf.gui.glyphs import Glyphs
from chisurf.gui import dialogs

logger = logging.getLogger(__name__)


@register_section("traj_align_io")
def traj_align_io(model, target=None, **options):
    """AutoForm factory for the trajectory picker + save-aligned button."""
    return _IoSection(model)


class _IoSection(QtWidgets.QWidget):
    """Trajectory row (browse + drag-drop) and the save-aligned action button."""

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self._model = model

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)

        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        row.addWidget(QtWidgets.QLabel("Trajectory"))
        self._edit = QtWidgets.QLineEdit()
        self._edit.setReadOnly(True)
        self._edit.setPlaceholderText("Drop a DCD or XTC trajectory here or browse…")
        self._edit.setText(self._model.trajectory_filename)
        row.addWidget(self._edit, 1)
        browse = QtWidgets.QToolButton()
        browse.setText("…")
        browse.setToolTip("Open a DCD or XTC trajectory.")
        browse.clicked.connect(self._browse_trajectory)
        row.addWidget(browse)
        layout.addLayout(row)

        # DCD and XTC hold coordinates and nothing else, so the atom names have
        # to come from a structure file. Without this row the tool could be
        # driven from a script but not from the window.
        top_row = QtWidgets.QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(2)
        top_row.addWidget(QtWidgets.QLabel("Topology"))
        self._top_edit = QtWidgets.QLineEdit()
        self._top_edit.setReadOnly(True)
        self._top_edit.setPlaceholderText("PDB naming the atoms — required for DCD/XTC")
        self._top_edit.setText(self._model.topology_filename)
        top_row.addWidget(self._top_edit, 1)
        top_browse = QtWidgets.QToolButton()
        top_browse.setText("…")
        top_browse.setToolTip(
            "Open the PDB that names the atoms. DCD and XTC store coordinates "
            "only, so this is required for them."
        )
        top_browse.clicked.connect(self._browse_topology)
        top_row.addWidget(top_browse)
        layout.addLayout(top_row)

        self._save_btn = QtWidgets.QToolButton()
        self._save_btn.setText(f"{Glyphs.SAVE} Save aligned…")
        self._save_btn.setToolTip(
            "Superpose every frame onto the first frame and write a new DCD."
        )
        self._save_btn.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self._save_btn.clicked.connect(self._save_aligned)
        layout.addWidget(self._save_btn)

        self._enable_file_drop(self._edit, self._load_trajectory)
        self._enable_file_drop(self._top_edit, self._load_topology)
        self._model.add_observer(self._on_model_event)

    # ── model wiring ────────────────────────────────────────────────────
    def _on_model_event(self, event: str) -> None:
        if event != "loaded":
            return
        if self._edit.text() != self._model.trajectory_filename:
            self._edit.setText(self._model.trajectory_filename)
        if self._top_edit.text() != self._model.topology_filename:
            self._top_edit.setText(self._model.topology_filename)

    def _refresh_host_form(self) -> None:
        """Walk up to the hosting AutoForm and refresh its widgets (log panel)."""
        widget = self.parentWidget()
        while widget is not None:
            if hasattr(widget, "sync_fields") and hasattr(widget, "refresh_plots"):
                try:
                    widget.sync_fields()
                    widget.refresh_plots()
                except Exception:  # pragma: no cover - defensive
                    pass
                return
            widget = widget.parentWidget()

    # ── actions ─────────────────────────────────────────────────────────
    def _browse_trajectory(self) -> None:
        import chisurf.gui.widgets

        filename = chisurf.gui.widgets.get_filename(
            "Open trajectory", "Trajectories (*.dcd *.xtc)"
        )
        if filename:
            self._load_trajectory(filename)

    def _browse_topology(self) -> None:
        import chisurf.gui.widgets

        filename = chisurf.gui.widgets.get_filename(
            "Open topology", "Structures (*.pdb *.cif *.ent)"
        )
        if filename:
            self._load_topology(filename)

    def _load_topology(self, path: str) -> None:
        if not path or not pathlib.Path(path).is_file():
            return
        self._model.set_topology(path)
        self._refresh_host_form()

    def _load_trajectory(self, path: str) -> None:
        if not path or not pathlib.Path(path).is_file():
            return
        self._model.set_trajectory(path)
        self._refresh_host_form()

    def _save_aligned(self) -> None:
        if not self._model.trajectory_filename:
            dialogs.information(self, "No trajectory", "Open a trajectory first.")
            return
        target, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save aligned trajectory", "", "DCD trajectory (*.dcd)"
        )
        if not target:
            self._model.append_log("Save cancelled")
            self._refresh_host_form()
            return
        try:
            self._model.save_aligned(target)
        except Exception as exc:  # noqa: BLE001
            dialogs.error(self, "Align failed", str(exc))
        self._refresh_host_form()

    # ── drag-drop ───────────────────────────────────────────────────────
    @staticmethod
    def _enable_file_drop(line_edit: QtWidgets.QLineEdit, on_file) -> None:
        """Enable dropping a single existing file onto *line_edit* → ``on_file(path)``."""
        line_edit.setAcceptDrops(True)

        def dragEnterEvent(event: QtGui.QDragEnterEvent):
            urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
            if len(urls) == 1 and pathlib.Path(urls[0].toLocalFile()).is_file():
                event.acceptProposedAction()
                return
            event.ignore()

        def dropEvent(event: QtGui.QDropEvent):
            urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
            if len(urls) == 1:
                path = urls[0].toLocalFile()
                if pathlib.Path(path).is_file():
                    event.acceptProposedAction()
                    on_file(path)
                    return
            event.ignore()

        line_edit.dragEnterEvent = dragEnterEvent
        line_edit.dropEvent = dropEvent


__all__ = ["traj_align_io"]
