"""The first native tests of the user editor, kept: the app now takes the emtk model.

The earlier version built the app over the shared ``UserEditorViewModel`` and asserted the
old ``Users`` / ``Details`` headings; the app is over ``UserEditorModel`` now (the same view
model plus the table source, confirmations and password prompt) and its windows are
``Accounts`` and ``Account``. Both tests keep their meaning: load, edit and save through the
client; draw with the account in the table.
"""

from __future__ import annotations

from emtk.testing import RecordingPainter

from ..api.records import UserRow
from ..gui.app import UserEditorApp
from ..gui.model import UserEditorModel


class FakeClient:
    def list_users(self):
        return [
            {
                "user_id": "alice",
                "user_uuid": "u1",
                "display_name": "Alice",
                "email": "alice@example.org",
                "role": "Postdoc",
            }
        ]

    def save_user(self, payload):
        self.saved = payload

    def delete_user(self, *args, **kwargs):
        return None


def test_native_user_editor_load_edit_and_validation():
    client = FakeClient()
    app = UserEditorApp(UserEditorModel(client_factory=lambda: client), autoload=False)
    app.model.reload()
    app.model.select_row(0)
    app.model.display_name = "Alice Example"
    assert app.model.problems() == []
    assert app.model.save() == ""
    assert client.saved["display_name"] == "Alice Example"


def test_native_user_editor_render_has_tooltips():
    app = UserEditorApp(UserEditorModel(client_factory=FakeClient), autoload=False)
    app.model.users = [UserRow(user_id="alice", display_name="Alice")]
    painter = RecordingPainter()
    app.draw(painter, 0, 0, 980, 700)
    assert "Accounts" in painter.strings and "Account" in painter.strings
    assert "Alice" in painter.strings
