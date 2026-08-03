"""Custom AutoForm section for the Rotate/Translate-Trajectory tool.

A single bespoke Qt widget registered here bundles all of the tool's editors: the
trajectory picker (``…`` browse + drag-drop, H5 filter), the 3x3 rotation-matrix
grid, the 3-field translation row, and the ``💾 Save rotated/translated…`` action
button. The stride and the log are plain built-in sections in
``rotate_translate.view.json``. The widget owns only Qt concerns and drives the
Qt-free :class:`~.view_model.RotateTranslateViewModel`. Imported (and thus
registered) by ``widget``. Mirrors the Align-Trajectory ``traj_align_io`` pattern.
"""

from __future__ import annotations

import logging
import pathlib

import numpy as np
from qtpy import QtCore, QtGui, QtWidgets

from chisurf.gui.autoform.sections.registry import register_section
from chisurf.gui.glyphs import Glyphs
from chisurf.gui import dialogs

logger = logging.getLogger(__name__)


@register_section("traj_rotate_translate_io")
def traj_rotate_translate_io(model, target=None, **options):
    """AutoForm factory for the trajectory picker + matrix/vector editors + save button."""
    return _IoSection(model)


def _make_edit() -> QtWidgets.QLineEdit:
    """Build a compact, numeric-validated line edit for a matrix/vector element."""
    edit = QtWidgets.QLineEdit()
    edit.setValidator(QtGui.QDoubleValidator())
    edit.setMinimumWidth(48)
    return edit


class _IoSection(QtWidgets.QWidget):
    """Trajectory row, rotation-matrix grid, translation row and the save button."""

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self._model = model

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)

        # ── trajectory row ──────────────────────────────────────────────
        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        row.addWidget(QtWidgets.QLabel("Trajectory"))
        self._edit = QtWidgets.QLineEdit()
        self._edit.setReadOnly(True)
        self._edit.setPlaceholderText("Drop an H5 trajectory here or browse…")
        self._edit.setText(self._model.trajectory_filename)
        row.addWidget(self._edit, 1)
        browse = QtWidgets.QToolButton()
        browse.setText("…")
        browse.setToolTip("Open an H5 trajectory file.")
        browse.clicked.connect(self._browse_trajectory)
        row.addWidget(browse)
        layout.addLayout(row)

        # ── rotation matrix (3x3) ───────────────────────────────────────
        rot_box = QtWidgets.QGroupBox("Rotation matrix")
        rot_box.setToolTip(
            "The 3x3 rotation matrix. The coordinates of every frame are multiplied "
            "by this matrix; the user must ensure it is a valid rotation matrix."
        )
        rot_grid = QtWidgets.QGridLayout(rot_box)
        rot_grid.setContentsMargins(2, 2, 2, 2)
        rot_grid.setSpacing(2)
        self._rot_edits: list[list[QtWidgets.QLineEdit]] = []
        for i in range(3):
            row_edits: list[QtWidgets.QLineEdit] = []
            for j in range(3):
                edit = _make_edit()
                edit.editingFinished.connect(self._write_rotation_matrix)
                rot_grid.addWidget(edit, i, j)
                row_edits.append(edit)
            self._rot_edits.append(row_edits)
        layout.addWidget(rot_box)

        # ── translation vector (3) ──────────────────────────────────────
        trans_box = QtWidgets.QGroupBox("Translation [Ang.]")
        trans_row = QtWidgets.QHBoxLayout(trans_box)
        trans_row.setContentsMargins(2, 2, 2, 2)
        trans_row.setSpacing(2)
        self._trans_edits: list[QtWidgets.QLineEdit] = []
        for _ in range(3):
            edit = _make_edit()
            edit.editingFinished.connect(self._write_translation_vector)
            trans_row.addWidget(edit)
            self._trans_edits.append(edit)
        layout.addWidget(trans_box)

        # ── save button ─────────────────────────────────────────────────
        self._save_btn = QtWidgets.QToolButton()
        self._save_btn.setText(f"{Glyphs.SAVE} Save rotated/translated…")
        self._save_btn.setToolTip("Rotate + translate every frame and write a new H5 trajectory.")
        self._save_btn.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self._save_btn.clicked.connect(self._save)
        layout.addWidget(self._save_btn)

        self._read_matrices_from_model()
        self._enable_file_drop(self._edit, self._load_trajectory)
        self._model.add_observer(self._on_model_event)

    # ── model <-> widget sync ───────────────────────────────────────────
    def _read_matrices_from_model(self) -> None:
        """Populate the matrix/vector line edits from the model state."""
        rot = np.asarray(self._model.rotation_matrix, dtype=float)
        for i in range(3):
            for j in range(3):
                self._rot_edits[i][j].setText(str(float(rot[i, j])))
        trans = np.asarray(self._model.translation_vector, dtype=float)
        for k in range(3):
            self._trans_edits[k].setText(str(float(trans[k])))

    def _write_rotation_matrix(self) -> None:
        """Read the 3x3 grid into the model's ``rotation_matrix``."""
        values = [
            [self._as_float(self._rot_edits[i][j].text()) for j in range(3)] for i in range(3)
        ]
        self._model.rotation_matrix = np.array(values, dtype=np.float32)

    def _write_translation_vector(self) -> None:
        """Read the translation row into the model's ``translation_vector``."""
        values = [self._as_float(edit.text()) for edit in self._trans_edits]
        self._model.translation_vector = np.array(values, dtype=np.float32)

    @staticmethod
    def _as_float(text: str) -> float:
        """Parse *text* as a float, treating an empty/invalid entry as ``0.0``."""
        try:
            return float(text)
        except (TypeError, ValueError):
            return 0.0

    def _on_model_event(self, event: str) -> None:
        if event == "loaded" and self._edit.text() != self._model.trajectory_filename:
            self._edit.setText(self._model.trajectory_filename)
        elif event == "fields":
            self._read_matrices_from_model()

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

        filename = chisurf.gui.widgets.get_filename("Open H5-Model file", "H5-files (*.h5)")
        if filename:
            self._load_trajectory(filename)

    def _load_trajectory(self, path: str) -> None:
        if not path or not pathlib.Path(path).is_file():
            return
        self._model.set_trajectory(path)
        self._refresh_host_form()

    def _save(self) -> None:
        if not self._model.trajectory_filename:
            dialogs.information(self, "No trajectory", "Open a trajectory first.")
            return
        self._write_rotation_matrix()
        self._write_translation_vector()
        target, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save H5-Model file", "", "H5-files (*.h5)"
        )
        if not target:
            self._model.append_log("Save cancelled")
            self._refresh_host_form()
            return
        try:
            self._model.save_rotated_translated(target)
        except Exception as exc:  # noqa: BLE001
            dialogs.error(self, "Save failed", str(exc))
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


__all__ = ["traj_rotate_translate_io"]
