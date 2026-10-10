"""Password entry dialog of the Qt shell (the main window's login flow).

A password entry genuinely needs a modal dialog, so the shell keeps one: a strength bar
(red, yellow, green) beside the confirmation field. The User Editor plugin is a native emtk
app with its own in-window password section; this dialog serves only the shell's
"set a password for this account" prompt after sign-in.
"""

from __future__ import annotations

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

from chisurf.gui import dialogs


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
