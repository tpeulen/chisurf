"""The shell's password dialog: strength rule and the administrator floor."""

from __future__ import annotations

import pytest

pytest.importorskip("qtpy")


def test_strength_rises_with_each_character_class(qapp, qtbot):
    from chisurf.gui.password_dialog import PasswordChangeDialog

    dialog = PasswordChangeDialog(user_id="bob", is_admin=False)
    qtbot.addWidget(dialog)
    scores = []
    for text in ("", "a", "abcdefgh", "Abcdefgh", "Abcdefg1", "Abcdef1!"):
        dialog.on_password_changed(text)
        scores.append(dialog.score)
    assert scores == [0, 1, 2, 3, 4, 5]
    dialog.on_password_changed("")
    assert dialog.strength_label.text() == "Enter a password"
    dialog.on_password_changed("Abcdef1!")
    assert dialog.strength_label.text() == "Strength: Strong"


def test_an_administrator_needs_at_least_medium_strength(qapp, qtbot, monkeypatch):
    from chisurf.gui import password_dialog
    from chisurf.gui.password_dialog import PasswordChangeDialog

    asked = []
    monkeypatch.setattr(password_dialog.dialogs, "warning", lambda *args, **kw: asked.append(args[2]))
    dialog = PasswordChangeDialog(user_id="root", is_admin=True)
    qtbot.addWidget(dialog)
    dialog.edit_password.setText("abc")
    dialog.edit_confirm.setText("abc")
    dialog.on_save_clicked()
    assert asked and "too weak" in asked[-1] and not hasattr(dialog, "password")
    dialog.edit_password.setText("Abcdef1!")
    dialog.edit_confirm.setText("Abcdef1!")
    dialog.on_save_clicked()
    assert dialog.password == "Abcdef1!"
