"""Custom AutoForm section for the Save-Topology tool.

The trajectory picker (``…`` browse + drag-drop, H5 filter) and the
``💾 Save topology`` action button are a bespoke Qt widget registered here; the
log is a plain built-in ``info`` section in ``save_topology.view.json``. The
widget owns only Qt concerns and drives the Qt-free
:class:`~.view_model.SaveTopologyViewModel`. Imported (and thus registered) by
``widget``. Mirrors the TTTR-Splitter ``splitter_io`` pattern.
"""

from __future__ import annotations

import logging
import pathlib

from qtpy import QtCore, QtGui, QtWidgets

from chisurf.gui import dialogs
from chisurf.gui.autoform.sections.registry import register_section
from chisurf.gui.glyphs import Glyphs

logger = logging.getLogger(__name__)


@register_section("traj_save_topology_io")
def traj_save_topology_io(model, target=None, **options):
    """AutoForm factory for the trajectory picker + save-topology button."""
    return _IoSection(model)


class _IoSection(QtWidgets.QWidget):
    """Trajectory row (browse + drag-drop) and the save-topology action button."""

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
        self._edit.setPlaceholderText("Drop a DCD trajectory here or browse…")
        self._edit.setText(self._model.trajectory_filename)
        row.addWidget(self._edit, 1)
        browse = QtWidgets.QToolButton()
        browse.setText("…")
        browse.setToolTip("Open an H5 trajectory file.")
        browse.clicked.connect(self._browse_trajectory)
        row.addWidget(browse)
        layout.addLayout(row)

        # DCD holds coordinates and nothing else, so the atom names have
        # to come from a structure file. Without this row the tool could be
        # driven from a script but not from the window.
        _top_row = QtWidgets.QHBoxLayout()
        _top_row.setContentsMargins(0, 0, 0, 0)
        _top_row.setSpacing(2)
        _top_row.addWidget(QtWidgets.QLabel("Topology"))
        self._top_edit = QtWidgets.QLineEdit()
        self._top_edit.setReadOnly(True)
        self._top_edit.setPlaceholderText("PDB naming the atoms — required for DCD")
        self._top_edit.setText(self._model.topology_filename)
        _top_row.addWidget(self._top_edit, 1)
        _top_browse = QtWidgets.QToolButton()
        _top_browse.setText("…")
        _top_browse.setToolTip(
            "Open the PDB that names the atoms. DCD stores coordinates "
            "only, so this is required for them."
        )
        _top_browse.clicked.connect(self._browse_topology)
        _top_row.addWidget(_top_browse)
        layout.addLayout(_top_row)

        self._save_btn = QtWidgets.QToolButton()
        self._save_btn.setText(f"{Glyphs.SAVE} Save topology…")
        self._save_btn.setToolTip("Write the first frame of the trajectory as a PDB file.")
        self._save_btn.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self._save_btn.clicked.connect(self._save_topology)
        layout.addWidget(self._save_btn)

        self._enable_file_drop(self._edit, self._load_trajectory)
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

        filename = chisurf.gui.widgets.get_filename("Open trajectory", "Trajectories (*.dcd)")
        if filename:
            self._load_trajectory(filename)

    def _load_trajectory(self, path: str) -> None:
        if not path or not pathlib.Path(path).is_file():
            return
        self._model.set_trajectory(path)
        self._refresh_host_form()

    def _save_topology(self) -> None:
        if not self._model.trajectory_filename:
            dialogs.information(self, "No trajectory", "Open a trajectory first.")
            return
        target, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save PDB-file", "", "PDB-files (*.pdb)"
        )
        if not target:
            self._model.append_log("Save cancelled")
            self._refresh_host_form()
            return
        try:
            self._model.save_topology(target)
        except Exception as exc:  # noqa: BLE001
            dialogs.error(self, "Save failed", str(exc))
        self._refresh_host_form()

    # ── drag-drop ───────────────────────────────────────────────────────

    def _browse_topology(self) -> None:
        import chisurf.gui.widgets

        filename = chisurf.gui.widgets.get_filename(
            "Open topology", "Structures (*.pdb *.cif *.ent)"
        )
        if filename:
            self._load_topology(filename)

    def _load_topology(self, path: str) -> None:
        import pathlib as _pathlib

        if not path or not _pathlib.Path(path).is_file():
            return
        self._model.set_topology(path)
        self._refresh_host_form()

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


__all__ = ["traj_save_topology_io"]
