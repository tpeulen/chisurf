"""User editor: validation, the save payload, and the panel.

The plugin had no tests at all, which is how a NameError in the force-delete
path, a Role box that silently rewrote unknown roles, and a blocking RPC in the
constructor all survived.
"""

from __future__ import annotations

import json

import pytest

from chisurf.plugins.core.user_editor.api.records import (
    PROTECTED_USER_IDS,
    UserRow,
    to_payload,
    validate_user,
)
from chisurf.plugins.core.user_editor.gui.view_model import UserEditorViewModel


class _FakeClient:
    """An MMFDB client stand-in that records what it was asked to do."""

    def __init__(self, users=None, fail=None):
        self.users = users if users is not None else []
        self.fail = fail
        self.saved = []
        self.deleted = []

    def list_users(self):
        if self.fail:
            raise RuntimeError(self.fail)
        return list(self.users)

    def save_user(self, payload):
        self.saved.append(payload)

    def delete_user(self, user_id, force=False, requester_id=""):
        self.deleted.append((user_id, force))


def _record(**over):
    base = {
        "user_id": "bob", "user_uuid": "u-1", "display_name": "Bob",
        "email": "bob@example.org", "role": "Postdoc", "is_admin": 0,
        "allow_passwordless_login": 0,
    }
    base.update(over)
    return base


def _model(client):
    return UserEditorViewModel(client_factory=lambda *a, **k: client)


# ── validation ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "row, expect",
    [
        (UserRow(user_id="", display_name="B"), "username is required"),
        (UserRow(user_id="a b", display_name="B"), "must not contain spaces"),
        (UserRow(user_id="a", display_name=""), "display name is required"),
        (UserRow(user_id="a", display_name="B", email="nope"), "not a valid e-mail"),
        (UserRow(user_id="a", display_name="B", website="example.org"), "http://"),
    ],
)
def test_validation_catches_what_the_backend_would_refuse(row, expect):
    problems = " ".join(validate_user(row)).lower()
    assert expect.lower() in problems


def test_a_valid_account_has_no_problems():
    row = UserRow(user_id="bob", display_name="Bob", email="b@x.io",
                  website="https://x.io")
    assert validate_user(row) == []


def test_a_duplicate_username_is_caught_before_the_round_trip():
    row = UserRow(user_id="bob", display_name="Bob")
    existing = [UserRow(user_id="bob", display_name="Other")]
    assert validate_user(row, existing=existing, creating=True)
    # renaming an existing account to its own name is not a duplicate
    assert validate_user(row, existing=existing, creating=False) == []


def test_an_unknown_role_survives_a_round_trip():
    """The old combo displayed anything unknown as "Other" and saved that back."""
    row = UserRow.from_record(_record(role="Facility Manager"))
    assert row.role == "Facility Manager"
    assert to_payload(row)["role"] == "Facility Manager"


def test_payload_renames_only_when_the_username_changed():
    row = UserRow(user_id="new", display_name="X")
    assert to_payload(row, old_user_id="old")["old_user_id"] == "old"
    assert "old_user_id" not in to_payload(row, old_user_id="new")


def test_a_password_is_only_sent_when_one_was_staged():
    row = UserRow(user_id="a", display_name="A")
    assert "password" not in to_payload(row)
    assert to_payload(row, password="s3cret")["password"] == "s3cret"


def test_missing_columns_do_not_raise():
    """Older rows lack columns the form reads; indexing them used to KeyError."""
    row = UserRow.from_record({"user_id": "x"})
    assert row.display_name == "" and row.role == "Generic"


# ── the view model ──────────────────────────────────────────────────────


def test_nothing_is_fetched_until_the_panel_is_shown():
    """A blocking RPC in the constructor froze the whole Settings dialog."""
    client = _FakeClient([_record()])
    model = _model(client)
    assert model.users == []
    model.ensure_loaded()
    assert [u.user_id for u in model.users] == ["bob"]


def test_a_refused_listing_is_state_not_an_exception():
    model = _model(_FakeClient(fail="Authentication required"))
    model.ensure_loaded()
    assert model.users == []
    assert "administrator" in model.status_text().lower()


def test_an_unreachable_server_says_so():
    model = _model(_FakeClient(fail="timeout: no response"))
    model.ensure_loaded()
    assert "could not reach" in model.status_text().lower()


def test_edits_do_not_touch_the_table_until_saved():
    client = _FakeClient([_record()])
    model = _model(client)
    model.ensure_loaded()
    model.select_row({"username": "bob"})

    model.display_name = "Robert"
    assert model.dirty
    assert model.users[0].display_name == "Bob", "the table changed before saving"

    model.revert()
    assert not model.dirty
    assert model.display_name == "Bob"


def test_save_sends_the_edited_account():
    client = _FakeClient([_record()])
    model = _model(client)
    model.ensure_loaded()
    model.select_row({"username": "bob"})
    model.display_name = "Robert"
    assert model.save() == ""

    assert len(client.saved) == 1
    assert client.saved[0]["display_name"] == "Robert"


def test_save_refuses_an_invalid_account_without_calling_the_server():
    client = _FakeClient([_record()])
    model = _model(client)
    model.ensure_loaded()
    model.select_row({"username": "bob"})
    model.email = "not-an-email"

    problem = model.save()
    assert "e-mail" in problem
    assert client.saved == [], "an invalid account still reached the server"


def test_a_rename_is_reported_so_the_token_can_follow():
    client = _FakeClient([_record()])
    model = _model(client)
    model.ensure_loaded()
    model.select_row({"username": "bob"})
    model.user_id = "robert"
    assert model.save() == "renamed:bob"


def test_a_staged_password_is_flagged_and_then_cleared():
    client = _FakeClient([_record()])
    model = _model(client)
    model.ensure_loaded()
    model.select_row({"username": "bob"})

    model.stage_password("hunter2")
    assert model.password_staged
    assert "password" in model.status_text().lower()

    model.save()
    assert not model.password_staged
    assert client.saved[0]["password"] == "hunter2"


def test_new_user_starts_a_blank_account_with_a_uuid():
    model = _model(_FakeClient([_record()]))
    model.ensure_loaded()
    model.new_user()
    assert model.user_id == "" and model.edited.user_uuid
    assert model.dirty


def test_delete_passes_force_through():
    client = _FakeClient([_record()])
    model = _model(client)
    model.ensure_loaded()
    assert model.delete("bob") == ""
    assert client.deleted == [("bob", False)]
    model.delete("bob", force=True)
    assert client.deleted[-1] == ("bob", True)


def test_builtin_accounts_are_marked_protected():
    for user_id in PROTECTED_USER_IDS:
        assert UserRow(user_id=user_id).protected
    assert not UserRow(user_id="bob").protected


# ── the panel ───────────────────────────────────────────────────────────


def test_the_view_spec_matches_the_schema():
    from chisurf.core.dataspec.schema import validate_view_spec
    from chisurf.plugins.core.user_editor.gui.view_model import _VIEW_JSON

    assert validate_view_spec(json.loads(_VIEW_JSON.read_text())) == []


def test_every_bound_attribute_exists_on_the_model():
    from chisurf.plugins.core.user_editor.gui.view_model import _VIEW_JSON

    model = _model(_FakeClient())
    spec = json.loads(_VIEW_JSON.read_text())
    missing = []

    def walk(section):
        for key in ("attr", "source", "options_source", "selected_call"):
            target = section.get(key)
            if target and not hasattr(model, target):
                missing.append(f"{section.get('type')}.{key} -> {target}")
        for nested in ("source", "selected_call"):
            target = (section.get("options") or {}).get(nested)
            if target and not hasattr(model, target):
                missing.append(f"custom.{nested} -> {target}")
        for child in section.get("sections", []):
            walk(child)

    for section in spec["sections"]:
        walk(section)
    assert not missing, "view spec binds to missing attributes:\n  " + "\n  ".join(missing)


def test_user_editor_widget_creation(qapp, qtbot):
    """The panel builds without reaching the network."""
    from chisurf.plugins.core.user_editor.gui.tool import UserEditorWidget

    widget = UserEditorWidget(view_model=_model(_FakeClient([_record()])))
    qtbot.addWidget(widget)
    assert "User" in widget.windowTitle()
    assert widget.model.users == [], "the constructor fetched users"


def test_the_password_dialog_is_still_importable_from_here(qapp):
    """chisurf/gui/__init__.py imports it from this module for the login flow."""
    from chisurf.plugins.core.user_editor.gui.tool import PasswordChangeDialog

    assert PasswordChangeDialog is not None
