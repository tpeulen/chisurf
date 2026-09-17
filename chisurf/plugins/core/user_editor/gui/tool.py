"""User editor: the accounts registered in the MMFDB.

The panel is built from ``users.view.json`` by AutoForm over
:class:`~.view_model.UserEditorViewModel`; the client seam, the record shapes and
the validation live in the Qt-free ``api`` package.

This replaced an 861-line widget that fetched users from its own constructor
(freezing the Settings dialog for the client timeout whenever no server was up),
reported a refused call through a modal, and re-implemented the backend's
password-strength rule and e-mail check line for line.

:class:`PasswordChangeDialog` stays here and stays a dialog -- a password entry
genuinely needs one, and ``chisurf/gui/__init__.py`` imports this class for the
login flow.
"""

from __future__ import annotations

from typing import Any

from qtpy import QtCore, QtWidgets
from qtpy.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from chisurf import logging
from chisurf.gui import dialogs
from chisurf.gui.autoform import AutoForm
from chisurf.gui.glyphs import Glyphs
from chisurf.gui.widgets.tools.chisurf_dock_tool import ChisurfDockTool
from chisurf.plugins.core.user_editor.api.records import PROTECTED_USER_IDS
from chisurf.plugins.core.user_editor.gui.view_model import UserEditorViewModel

#: Legacy AST-discovery name.
name = "Setup:User Editor"


class PasswordChangeDialog(QDialog):
    """
    A dialog for setting/changing a password with strength indicator.
    Calculates and shows password strength using color coding (red, yellow, green).
    """

    def __init__(self, user_id: str, is_admin: bool, parent=None):
        super().__init__(parent)
        self.user_id = user_id
        self.is_admin = is_admin
        self.setWindowTitle(f"Change Password for {user_id}")
        self.resize(360, 240)

        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        form_layout = QFormLayout()
        self.edit_password = QLineEdit()
        self.edit_password.setEchoMode(QLineEdit.Password)
        self.edit_password.textChanged.connect(self.on_password_changed)
        form_layout.addRow("New Password:", self.edit_password)

        self.edit_confirm = QLineEdit()
        self.edit_confirm.setEchoMode(QLineEdit.Password)
        form_layout.addRow("Confirm Password:", self.edit_confirm)

        layout.addLayout(form_layout)

        # Strength indicator
        self.strength_label = QLabel("Strength: Weak")
        self.strength_label.setStyleSheet("color: #ff4d4d; font-weight: bold;")
        layout.addWidget(self.strength_label)

        self.strength_bar = QProgressBar()
        self.strength_bar.setRange(0, 100)
        self.strength_bar.setValue(0)
        self.strength_bar.setTextVisible(False)
        self.strength_bar.setMaximumHeight(8)
        self.strength_bar.setStyleSheet("QProgressBar::chunk { background-color: #ff4d4d; }")
        layout.addWidget(self.strength_bar)

        # Feedback label
        self.feedback_label = QLabel()
        self.feedback_label.setWordWrap(True)
        self.feedback_label.setStyleSheet("color: #555555; font-size: 11px;")
        layout.addWidget(self.feedback_label)

        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_save = QPushButton("Save")
        self.btn_save.setToolTip("Write the edited details back to the MMFDB.")
        self.btn_save.clicked.connect(self.on_save_clicked)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

        self.on_password_changed("")

    def on_password_changed(self, text):
        score = 0
        feedback = []

        if len(text) >= 8:
            score += 1
        else:
            feedback.append("At least 8 characters")

        if any(c.islower() for c in text):
            score += 1
        else:
            feedback.append("At least one lowercase letter")

        if any(c.isupper() for c in text):
            score += 1
        else:
            feedback.append("At least one uppercase letter")

        if any(c.isdigit() for c in text):
            score += 1
        else:
            feedback.append("At least one number")

        special_chars = "!@#$%^&*()_+-=[]{}|;':\",./<>?"
        if any(c in special_chars for c in text):
            score += 1
        else:
            feedback.append("At least one special character")

        self.score = score
        self.strength_bar.setValue(score * 20)

        if not text:
            self.strength_bar.setValue(0)
            self.strength_bar.setStyleSheet("QProgressBar::chunk { background-color: #cccccc; }")
            self.strength_label.setText("Enter a password")
            self.strength_label.setStyleSheet("color: #777777;")
            self.feedback_label.clear()
        elif score <= 2:
            self.strength_bar.setStyleSheet("QProgressBar::chunk { background-color: #ff4d4d; }")
            self.strength_label.setText("Strength: Weak")
            self.strength_label.setStyleSheet("color: #ff4d4d; font-weight: bold;")
            self.feedback_label.setText("Requirements: " + ", ".join(feedback))
        elif score <= 4:
            self.strength_bar.setStyleSheet("QProgressBar::chunk { background-color: #ffc107; }")
            self.strength_label.setText("Strength: Medium")
            self.strength_label.setStyleSheet("color: #ffc107; font-weight: bold;")
            self.feedback_label.setText("Requirements: " + ", ".join(feedback))
        else:
            self.strength_bar.setStyleSheet("QProgressBar::chunk { background-color: #28a745; }")
            self.strength_label.setText("Strength: Strong")
            self.strength_label.setStyleSheet("color: #28a745; font-weight: bold;")
            self.feedback_label.clear()

    def on_save_clicked(self):
        password = self.edit_password.text()
        confirm = self.edit_confirm.text()

        if password != confirm:
            dialogs.warning(self, "Validation Error", "Passwords do not match.")
            return

        if self.is_admin and self.score < 4:
            dialogs.warning(
                self,
                "Validation Error",
                "Administrator password is too weak. It must be at least Medium strength (score >= 4).",
            )
            return

        self.password = password
        self.accept()


class UserEditorWidget(ChisurfDockTool):
    """Browse and edit the MMFDB user accounts."""

    tool_settings_name = "UserEditorWidget"
    modelEvent = QtCore.Signal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None, view_model=None, **kwargs: Any):
        super().__init__(parent)
        self.setWindowTitle("User Editor")
        self.model = view_model or UserEditorViewModel()

        toolbar = QtWidgets.QToolBar()
        toolbar.setObjectName("user_editor_toolbar")
        toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
        self._add_actions(toolbar)
        self.add_toolbar_guide(toolbar, resource="guide.json")
        self.add_toolbar_help(toolbar, resource="help.md", title="Users — help")
        self.addToolBar(toolbar)

        self.auto_form = AutoForm(self.model)
        self.setCentralWidget(self.auto_form)

        self.modelEvent.connect(self._on_model_event)
        self.model.add_observer(self.modelEvent.emit)
        self.restore_window_geometry()

    def _add_actions(self, toolbar: QtWidgets.QToolBar) -> None:
        """Build the toolbar; every action carries a tooltip."""

        def add(label: str, tooltip: str, slot) -> None:
            action = toolbar.addAction(label)
            action.setToolTip(tooltip)
            action.triggered.connect(slot)

        add(f"{Glyphs.SAVE} Save", "Write the edited account back to the database.", self._save)
        add(f"{Glyphs.RESET} Revert", "Discard the edits to this account.", self._revert)
        toolbar.addSeparator()
        add(f"{Glyphs.REFRESH} Reload", "Fetch the user list again.", self._reload)
        toolbar.addSeparator()
        add(f"{Glyphs.ADD} New", "Create a new account.", self._new)
        add(
            f"{Glyphs.DELETE} Delete",
            "Delete the selected account. Built-in accounts and the active "
            "account cannot be deleted.",
            self._delete,
        )
        add(
            f"{Glyphs.KEY} Password…",
            "Set or change this account's password. It is applied when you Save.",
            self._password,
        )

    # -- lifecycle -------------------------------------------------------

    def showEvent(self, event) -> None:  # noqa: N802 - Qt signature
        """Fetch the accounts the first time the panel is shown."""
        super().showEvent(event)
        self.model.ensure_loaded()

    def _on_model_event(self, _event: str) -> None:
        self.auto_form.refresh_plots()
        self.auto_form.sync_fields()

    # -- actions ---------------------------------------------------------

    def _reload(self) -> None:
        self.model.reload()

    def _new(self) -> None:
        self.model.new_user()

    def _revert(self) -> None:
        if not self.model.dirty:
            return
        if dialogs.confirm(
            self,
            "Discard changes",
            "Discard the edits to this account?",
        ):
            self.model.revert()

    def _save(self) -> None:
        problem = self.model.save()
        if problem.startswith("renamed:"):
            old = problem.split(":", 1)[1]
            self._carry_local_state(old, self.model.edited.user_id)
            return
        if problem:
            dialogs.warning(self, "Cannot save", problem)

    def _delete(self) -> None:
        row = self.model.selected
        if row is None:
            dialogs.information(self, "No user selected", "Select an account first.")
            return
        if row.user_id in PROTECTED_USER_IDS:
            dialogs.warning(
                self,
                "Cannot delete",
                f"{row.user_id!r} is a built-in account and cannot be deleted.",
            )
            return
        if row.is_active:
            dialogs.warning(
                self,
                "Cannot delete",
                "This is the account ChiSurf is using. Switch to another account first.",
            )
            return
        if not dialogs.confirm(
            self,
            "Delete user",
            f"Permanently delete {row.display_name or row.user_id!r}?",
        ):
            return

        problem = self.model.delete(row.user_id)
        if not problem:
            return
        # The backend refuses to delete an account that owns committed data.
        # An administrator may override; anyone else just gets the reason.
        if self._is_admin() and dialogs.confirm(
            self,
            "Force delete",
            f"Could not delete the account:\n{problem}\n\nForce the deletion? "
            "The account goes, its committed data stays.",
        ):
            forced = self.model.delete(row.user_id, force=True)
            if forced:
                dialogs.error(self, "Force delete failed", forced)
        else:
            dialogs.warning(self, "Cannot delete", problem)

    def _password(self) -> None:
        row = self.model.selected
        user_id = self.model.edited.user_id or (row.user_id if row else "")
        if not user_id:
            dialogs.information(self, "No user selected", "Select or create an account first.")
            return
        dialog = PasswordChangeDialog(
            user_id=user_id, is_admin=self.model.edited.is_admin, parent=self
        )
        if dialog.exec() == QDialog.Accepted:
            self.model.stage_password(getattr(dialog, "password", ""))

    # -- helpers ---------------------------------------------------------

    def _is_admin(self) -> bool:
        """Whether the signed-in account is an administrator."""
        from chisurf.plugins.core.user_editor.api.client import active_user_id

        me = active_user_id()
        return any(u.user_id == me and u.is_admin for u in self.model.users)

    @staticmethod
    def _carry_local_state(old_user_id: str, new_user_id: str) -> None:
        """Move the stored session tokens after a rename."""
        try:
            from mmfdb.security.credentials import (
                rename_runtime_session_token,
                rename_session_token,
            )

            from chisurf.core.settings.settings_utils import set_mmfdb_login_settings
            from chisurf.plugins.core.user_editor.api.client import server_address

            host, port = server_address()
            rename_runtime_session_token(host, port, old_user_id, new_user_id)
            rename_session_token(host, port, old_user_id, new_user_id)
            set_mmfdb_login_settings({"default_user_id": new_user_id})
        except Exception:
            logging.exception("User Editor: could not carry local state after a rename")

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt signature
        """Warn before dropping unsaved edits."""
        if self.model.dirty and not dialogs.confirm(
            self,
            "Unsaved changes",
            "This account has unsaved changes.\n\nClose anyway?",
        ):
            event.ignore()
            return
        self.save_window_geometry()
        super().closeEvent(event)


#: Backwards-compatible alias.
UserEditorTool = UserEditorWidget
