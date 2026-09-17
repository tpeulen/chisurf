"""Custom AutoForm section for the Join-Trajectories tool.

The two trajectory pickers (``…`` browse + drag-drop, H5 filter) and the
``💾 Save joined…`` action button are a bespoke Qt widget registered here; the
join mode, per-trajectory reverse flags, chunk size and log are plain built-in
sections in ``join_trajectories.view.json``. The widget owns only Qt concerns
and drives the Qt-free :class:`~.view_model.JoinTrajectoriesViewModel`. Imported
(and thus registered) by ``widget``. Mirrors the Align-Trajectory
``traj_align_io`` pattern.
"""

from __future__ import annotations

import logging
import pathlib

from qtpy import QtCore, QtGui, QtWidgets

from chisurf.gui import dialogs
from chisurf.gui.autoform.sections.registry import register_section
from chisurf.gui.glyphs import Glyphs

logger = logging.getLogger(__name__)


@register_section("traj_join_io")
def traj_join_io(model, target=None, **options):
    """AutoForm factory for the two trajectory pickers + save-joined button."""
    return _IoSection(model)


class _IoSection(QtWidgets.QWidget):
    """Two trajectory rows (browse + drag-drop) and the save-joined action button."""

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self._model = model

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)

        self._edit_1 = self._build_row(
            layout,
            "Trajectory 1",
            self._model.trajectory_filename_1,
            self._browse_trajectory_1,
            self._load_trajectory_1,
        )
        self._edit_2 = self._build_row(
            layout,
            "Trajectory 2",
            self._model.trajectory_filename_2,
            self._browse_trajectory_2,
            self._load_trajectory_2,
        )

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
        self._save_btn.setText(f"{Glyphs.SAVE} Save joined…")
        self._save_btn.setToolTip(
            "Join the two trajectories and write the result as a new H5 trajectory."
        )
        self._save_btn.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self._save_btn.clicked.connect(self._save_joined)
        layout.addWidget(self._save_btn)

        self._model.add_observer(self._on_model_event)

    def _build_row(self, layout, label, initial, on_browse, on_drop):
        """Build one ``label + read-only line edit + browse`` row and return the edit."""
        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        row.addWidget(QtWidgets.QLabel(label))
        edit = QtWidgets.QLineEdit()
        edit.setReadOnly(True)
        edit.setPlaceholderText("Drop a DCD trajectory here or browse…")
        edit.setText(initial)
        row.addWidget(edit, 1)
        browse = QtWidgets.QToolButton()
        browse.setText("…")
        browse.setToolTip("Open an H5 trajectory file.")
        browse.clicked.connect(on_browse)
        row.addWidget(browse)
        layout.addLayout(row)

        self._enable_file_drop(edit, on_drop)
        return edit

    # ── model wiring ────────────────────────────────────────────────────
    def _on_model_event(self, event: str) -> None:
        if event != "loaded":
            return
        if self._edit_1.text() != self._model.trajectory_filename_1:
            self._edit_1.setText(self._model.trajectory_filename_1)
        if self._edit_2.text() != self._model.trajectory_filename_2:
            self._edit_2.setText(self._model.trajectory_filename_2)

        if event == "loaded" and self._top_edit.text() != self._model.topology_filename:
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
    def _browse_trajectory_1(self) -> None:
        import chisurf.gui.widgets

        filename = chisurf.gui.widgets.get_filename("Open trajectory", "Trajectories (*.dcd)")
        if filename:
            self._load_trajectory_1(filename)

    def _browse_trajectory_2(self) -> None:
        import chisurf.gui.widgets

        filename = chisurf.gui.widgets.get_filename("Open trajectory", "Trajectories (*.dcd)")
        if filename:
            self._load_trajectory_2(filename)

    def _load_trajectory_1(self, path: str) -> None:
        if not path or not pathlib.Path(path).is_file():
            return
        self._model.set_trajectory_1(path)
        self._refresh_host_form()

    def _load_trajectory_2(self, path: str) -> None:
        if not path or not pathlib.Path(path).is_file():
            return
        self._model.set_trajectory_2(path)
        self._refresh_host_form()

    def _save_joined(self) -> None:
        if not self._model.trajectory_filename_1 or not self._model.trajectory_filename_2:
            dialogs.information(self, "Two trajectories", "Open two trajectories first.")
            return
        target, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save trajectory", "", "DCD trajectory (*.dcd)"
        )
        if not target:
            self._model.append_log("Join cancelled")
            self._refresh_host_form()
            return
        try:
            self._model.save_joined(target)
        except Exception as exc:  # noqa: BLE001
            dialogs.error(self, "Join failed", str(exc))
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


__all__ = ["traj_join_io"]
