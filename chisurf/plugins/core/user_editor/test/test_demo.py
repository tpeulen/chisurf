"""The demo gives the tour accounts to select without an MMFDB server, in one window only."""

from __future__ import annotations

from chisurf.plugins.core.user_editor import demo
from chisurf.plugins.core.user_editor.gui.model import UserEditorModel


def test_load_example_lists_the_demo_accounts_in_this_model_only(tmp_path, monkeypatch):
    monkeypatch.setattr("chisurf.plugins.demo_cache.cache_folder", lambda plugin: tmp_path / plugin)
    model = UserEditorModel(client_factory=lambda: (_ for _ in ()).throw(RuntimeError("no server")))
    other = UserEditorModel(client_factory=lambda: (_ for _ in ()).throw(RuntimeError("no server")))
    model.load_example()
    assert [u.user_id for u in model.users] == ["alice", "bob", "carol"]
    other.reload()
    assert other.users == []  # the demonstration client was never installed globally


def test_make_demo_writes_the_accounts_once(tmp_path):
    path = demo.make_demo(tmp_path)
    stamp = path.stat().st_mtime_ns
    assert demo.make_demo(tmp_path) == path and path.stat().st_mtime_ns == stamp
    demo.make_demo(tmp_path, overwrite=True)
    assert [a["user_id"] for a in __import__("json").loads(path.read_text())] == [
        "alice",
        "bob",
        "carol",
    ]


def test_demo_client_saves_renames_and_deletes():
    client = demo.DemoUserClient()
    client.save_user({"user_id": "bobby", "old_user_id": "bob", "display_name": "Bobby"})
    ids = [u["user_id"] for u in client.list_users()]
    assert "bobby" in ids and "bob" not in ids
    client.delete_user("bobby")
    assert [u["user_id"] for u in client.list_users()] == ["alice", "carol"]
