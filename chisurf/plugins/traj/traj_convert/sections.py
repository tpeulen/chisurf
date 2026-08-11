"""Custom AutoForm sections for the MD-Converter (trajectory converter) tool.

Two bespoke Qt widgets are registered here; everything else (the folder / split
toggles, the frame-range spin boxes, the output base name, the extension combo
and the log) is a plain built-in section in ``convert_structures.view.json``.

* ``traj_convert_io`` — the three file rows: the topology PDB, the input
  trajectory (a single file, or a folder of PDBs when the model's ``use_folder``
  is set — the browse button switches accordingly) and the output directory.
* ``traj_convert_run`` — the ``▶ Convert`` action button; after the Qt-free
  :meth:`~.view_model.MDConverterViewModel.convert` returns it refreshes the
  host form's log and pops a ``Conversion done!`` message box.

The widgets own only Qt concerns and drive the Qt-free
:class:`~.view_model.MDConverterViewModel`. Imported (and thus registered) by
``widget``. Mirrors the Save-Topology / Align-Trajectory ``*_io`` pattern.
"""

from __future__ import annotations

import logging
import pathlib

from qtpy import QtCore, QtGui, QtWidgets

from chisurf.gui.autoform.sections.registry import register_section
from chisurf.gui import dialogs

logger = logging.getLogger(__name__)


@register_section("traj_convert_io")
def traj_convert_io(model, target=None, **options):
    """AutoForm factory for the topology / trajectory / target-folder rows."""
    return _IoSection(model)


@register_section("traj_convert_run")
def traj_convert_run(model, target=None, **options):
    """AutoForm factory for the ``▶ Convert`` action button."""
    return _RunSection(model)


class _IoSection(QtWidgets.QWidget):
    """The three input/output path rows (topology, trajectory, target folder)."""

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self._model = model

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)

        self._topology_edit = self._add_row(
            layout,
            "Topology",
            "Topology (PDB) — required for trajectory formats without topology.",
            self._browse_topology,
            model.topology_path,
        )
        self._trajectory_edit = self._add_row(
            layout,
            "Trajectory",
            "Input trajectory file, or a folder of PDBs when 'Input is a folder of PDBs' is on.",
            self._browse_trajectory,
            model.trajectory,
        )
        self._target_edit = self._add_row(
            layout,
            "Target folder",
            "Output directory the converted file(s) are written to.",
            self._browse_target,
            model.target_directory,
        )

        self._enable_file_drop(self._trajectory_edit, self._model.set_trajectory)
        self._model.add_observer(self._on_model_event)

    # ── construction helper ─────────────────────────────────────────────
    def _add_row(self, layout, label, tooltip, on_browse, initial):
        """Add a ``label + read-only edit + … browse`` row and return its edit."""
        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        row.addWidget(QtWidgets.QLabel(label))
        edit = QtWidgets.QLineEdit()
        edit.setReadOnly(True)
        edit.setToolTip(tooltip)
        edit.setText(str(initial))
        row.addWidget(edit, 1)
        browse = QtWidgets.QToolButton()
        browse.setText("…")
        browse.setToolTip(tooltip)
        browse.clicked.connect(on_browse)
        row.addWidget(browse)
        layout.addLayout(row)
        return edit

    # ── model wiring ────────────────────────────────────────────────────
    def _on_model_event(self, event: str) -> None:
        if self._topology_edit.text() != self._model.topology_path:
            self._topology_edit.setText(self._model.topology_path)
        if self._trajectory_edit.text() != self._model.trajectory:
            self._trajectory_edit.setText(self._model.trajectory)
        if self._target_edit.text() != self._model.target_directory:
            self._target_edit.setText(self._model.target_directory)

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
    def _browse_topology(self) -> None:
        import chisurf.gui.widgets

        filename = chisurf.gui.widgets.get_filename("Open PDB-File", "PDB-File (*.pdb)")
        if filename:
            self._model.set_topology(filename)
            self._refresh_host_form()

    def _browse_trajectory(self) -> None:
        import chisurf.gui.widgets

        if self._model.use_folder:
            path = str(QtWidgets.QFileDialog.getExistingDirectory(self, "Open PDB-Files", "."))
        else:
            path = chisurf.gui.widgets.get_filename(
                "Open trajectory", "Trajectory (*.dcd)"
            )
        if path:
            self._model.set_trajectory(path)
            self._refresh_host_form()

    def _browse_target(self) -> None:
        path = str(QtWidgets.QFileDialog.getExistingDirectory(self, "Choose Target-Folder", "."))
        if path:
            self._model.set_target_directory(path)
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


class _RunSection(QtWidgets.QWidget):
    """The ``▶ Convert`` action button driving the Qt-free view-model."""

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self._model = model
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)
        self._btn = QtWidgets.QToolButton()
        self._btn.setText("▶ Convert")
        self._btn.setToolTip("Convert the trajectory with the current settings.")
        self._btn.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self._btn.clicked.connect(self._convert)
        layout.addWidget(self._btn)
        layout.addStretch(1)

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

    def _convert(self) -> None:
        if not self._model.trajectory:
            dialogs.information(self, "No trajectory", "Choose a trajectory first.")
            return
        try:
            self._model.convert()
        except Exception as exc:  # noqa: BLE001
            self._refresh_host_form()
            dialogs.error(self, "Conversion failed", str(exc))
            return
        self._refresh_host_form()
        dialogs.information(self, "MC-Converter", "Conversion done!")


__all__ = ["traj_convert_io", "traj_convert_run"]
