"""The demo seam gives the tour accounts to select without an MMFDB server."""

from __future__ import annotations

import pytest

from chisurf.plugins.core.user_editor import demo
from chisurf.plugins.core.user_editor.api import client as client_seam
from chisurf.plugins.core.user_editor.gui.view_model import UserEditorViewModel


@pytest.fixture(autouse=True)
def _restore_client():
    yield
    client_seam.use_demo_client(None)


def test_make_demo_lists_demo_accounts_through_the_view_model():
    demo.make_demo()
    model = UserEditorViewModel()
    model.reload()
    assert [u.user_id for u in model.users] == ["alice", "bob", "carol"]


def test_demo_client_saves_renames_and_deletes():
    client = demo.DemoUserClient()
    client.save_user({"user_id": "bobby", "old_user_id": "bob", "display_name": "Bobby"})
    ids = [u["user_id"] for u in client.list_users()]
    assert "bobby" in ids and "bob" not in ids
    client.delete_user("bobby")
    assert [u["user_id"] for u in client.list_users()] == ["alice", "carol"]
