"""The Qt main window's project dialogs: *Save Project* and the import collision warning.

They belong to the Qt window's File menu (``chisurf/gui/main_helper.py``) and go with it.
The emtk shell draws its own (``chisurf/emtk/shell_session.py``,
``views/save_project.view.json``), and the Project Browser plugin is the emtk app
``chisurf.plugins.core.project_browser.gui.app``.
"""

from __future__ import annotations

from typing import Any

from qtpy import QtWidgets


class SaveProjectDialog(QtWidgets.QDialog):
    """Single dialog for project name, visibility, and notes."""

    def __init__(
        self,
        current_name: str = "",
        parent: QtWidgets.QWidget | None = None,
        allow_name_edit: bool = True,
        title: str = "Save Project",
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(400)
        layout = QtWidgets.QVBoxLayout(self)

        form = QtWidgets.QFormLayout()
        self._name_edit = QtWidgets.QLineEdit(current_name)
        self._name_edit.setPlaceholderText("Enter project name")
        self._name_edit.setEnabled(allow_name_edit)
        form.addRow("Project name:", self._name_edit)

        self._vis_combo = QtWidgets.QComboBox()
        self._vis_combo.addItems(["Private", "Public"])
        self._vis_combo.setToolTip(
            "Private: only the owner can see this project.\n"
            "Public: any authenticated user can see this project."
        )
        form.addRow("Visibility:", self._vis_combo)

        self._notes_edit = QtWidgets.QPlainTextEdit()
        self._notes_edit.setPlaceholderText("Optional notes...")
        self._notes_edit.setMaximumHeight(120)
        form.addRow("Notes:", self._notes_edit)

        layout.addLayout(form)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def project_name(self) -> str:
        """Return the project name entered in the dialog."""
        return self._name_edit.text().strip()

    @property
    def visibility(self) -> str:
        """Return the selected visibility as a lowercase string."""
        return self._vis_combo.currentText().lower()

    @property
    def notes(self) -> str:
        """Return optional notes entered in the dialog."""
        return self._notes_edit.toPlainText().strip()


class CollisionDialog(QtWidgets.QDialog):
    """Dialog to show ID collisions before import."""

    def __init__(
        self,
        collisions: dict[str, list[str]],
        origin: dict[str, Any],
        parent: QtWidgets.QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Import — Collision Warning")
        self.setModal(True)
        self.setMinimumSize(500, 300)
        layout = QtWidgets.QVBoxLayout(self)

        label = QtWidgets.QLabel(
            f"The following IDs from the archive already exist in the database.\n"
            f"Original project: {origin.get('project_id', '?')} "
            f"v{origin.get('version_number', '?')}.\n"
            "On confirmation, conflicting IDs will be remapped."
        )
        label.setWordWrap(True)
        layout.addWidget(label)

        text = QtWidgets.QTextEdit()
        text.setReadOnly(True)
        lines = []
        for category, ids in collisions.items():
            if ids:
                lines.append(f"<b>{category}</b> ({len(ids)}):")
                for cid in ids[:20]:
                    lines.append(f"  - {cid}")
                if len(ids) > 20:
                    lines.append(f"  ... and {len(ids) - 20} more")
                lines.append("")
        text.setHtml("<br>".join(lines) or "<i>No collisions found</i>")
        layout.addWidget(text)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.button(QtWidgets.QDialogButtonBox.Ok).setText("Remap & Import")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
