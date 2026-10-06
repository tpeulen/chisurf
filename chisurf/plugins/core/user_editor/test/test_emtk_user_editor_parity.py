"""The native user editor against the Qt tool: rows, fields, edits, drawing, no Qt.

Hermetic: the settings folder and the MMFDB database live in a temporary
directory (``seeded_db.use_folder``), never in ``~/.chisurf``. The tests that need
a server talk to the real in-process MMFDB services over that temporary database,
logged in as the desktop administrator; the others use a small stateful stand-in
for the client. ``carry_local_state`` (session tokens) is replaced by a recorder.
"""

from __future__ import annotations

import csv
import json
import threading
import time
from pathlib import Path

import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.core.user_editor.test import seeded_db

HERE = Path(__file__).parent
GUI = HERE.parent / "gui"
SPEC_FILE = GUI / "users_emtk.view.json"
TABLE = "user_records"

FIELDS = (
    "user_id",
    "display_name",
    "email",
    "role",
    "affiliation",
    "department",
    "phone",
    "website",
    "address",
    "details",
)


# ── fixtures ────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    """A temporary settings folder and database; no real server, no token writes."""
    from chisurf.plugins.core.user_editor.gui import model as model_module
    from chisurf.plugins.core.user_editor.gui import view_model

    seeded_db.use_folder(tmp_path / "mmfdb", monkeypatch)
    monkeypatch.setattr(view_model, "active_user_id", lambda: "admin")
    monkeypatch.setattr(model_module, "active_user_id", lambda: "admin")

    def offline():
        raise RuntimeError("timeout: no response within 5000ms")

    # a model built without a client must not look for a server on this machine
    monkeypatch.setattr(view_model, "make_mmfdb_client", offline)
    renames = []
    monkeypatch.setattr(
        model_module.UserEditorModel,
        "carry_local_state",
        staticmethod(lambda old, new: renames.append((old, new))),
    )
    return renames


@pytest.fixture
def renames(hermetic):
    return hermetic


@pytest.fixture
def temp_db():
    """The real MMFDB services over a temporary database seeded through the RPC API."""
    client = seeded_db.admin_client()
    seeded_db.seed(client)
    return client


class FakeServer:
    """A stateful stand-in for the MMFDB client: lists, saves, renames, deletes."""

    def __init__(self, users=None, fail_list="", fail_delete="", fail_save=""):
        self.users = {u["user_id"]: dict(u) for u in (users or [])}
        self.fail_list, self.fail_delete, self.fail_save = fail_list, fail_delete, fail_save
        self.saved: list[dict] = []
        self.deleted: list[tuple] = []
        self.listed = 0
        #: When set, ``list_users`` waits for it: a call that is visibly "in flight".
        self.gate = None

    def list_users(self):
        self.listed += 1
        if self.gate is not None:
            self.gate.wait(10)
        if self.fail_list:
            raise RuntimeError(self.fail_list)
        return [dict(u) for u in self.users.values()]

    def save_user(self, payload):
        if self.fail_save:
            raise RuntimeError(self.fail_save)
        self.saved.append(dict(payload))
        old = payload.get("old_user_id")
        if old:
            self.users.pop(old, None)
        record = {k: v for k, v in payload.items() if k not in ("requester_id", "old_user_id")}
        self.users[payload["user_id"]] = record

    def delete_user(self, user_id, force=False, requester_id=""):
        self.deleted.append((user_id, force, requester_id))
        if self.fail_delete and not force:
            raise RuntimeError(self.fail_delete)
        self.users.pop(user_id, None)


def record(user_id, name=None, **over):
    base = {
        "user_id": user_id,
        "user_uuid": f"uuid-{user_id}",
        "display_name": name or user_id.title(),
        "email": f"{user_id}@example.org",
        "role": "Postdoc",
        "is_admin": 0,
        "allow_passwordless_login": 0,
    }
    base.update(over)
    return base


def known_users():
    return [
        record("admin", "Admin", is_admin=1, role="Principal Investigator"),
        record("bob", "Bob Baker", affiliation="Biophysics", department="FCS"),
        record("carol", "Carol Chen", role="PhD Student", allow_passwordless_login=1),
        record("dave", "Dave Dunn", role="Facility Manager", email=""),
        record("guest", "Guest User", role="Guest"),
    ]


def make_model(client):
    from chisurf.plugins.core.user_editor.gui.model import UserEditorModel

    return UserEditorModel(client_factory=lambda *a, **k: client)


def make_app(client=None, autoload=False):
    from chisurf.plugins.core.user_editor.gui.app import UserEditorApp

    return UserEditorApp(make_model(client or FakeServer()), autoload=autoload)


def draw(app, size=(1200, 800), frames=3):
    painter = None
    for _ in range(frames):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


def pump(app, seconds=30.0):
    """Draw frames until the app's background job has finished."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        draw(app, frames=1)
        if not app.job.busy:
            return
        time.sleep(0.01)
    raise AssertionError("the job did not finish")


def loaded_app(client=None):
    """An app that has fetched its accounts, the way the first frame does."""
    app = make_app(client or FakeServer(known_users()), autoload=True)
    pump(app)
    return app


def table(app):
    return app.form.tables[TABLE].control


def click_row(app, key):
    """Select the row with record ``key`` the way the table does when clicked."""
    binding = app.form.tables[TABLE]
    control = binding.control
    index = next(i for i in range(control.row_count()) if control.key_of(i) == key)
    control.selected_key = key
    binding._on_select(index)


def shown(app):
    records, _ = app.displayed()
    return [r["username"] for r in records]


# ── 1. rows and fields equal the Qt tool's ──────────────────────────────


def test_rows_fields_and_status_match_the_qt_widget(qapp, qtbot, temp_db):
    """The same seeded accounts give the Qt table's cells, the form's fields and status."""
    from qtpy import QtWidgets

    from chisurf.gui.widgets.chitable import ChiTableWidget
    from chisurf.plugins.core.user_editor.gui.model import TABLE_COLUMNS
    from chisurf.plugins.core.user_editor.gui.tool import UserEditorWidget
    from chisurf.plugins.core.user_editor.gui.view_model import UserEditorViewModel

    qt_widget = UserEditorWidget(view_model=UserEditorViewModel(client_factory=lambda: temp_db))
    qtbot.addWidget(qt_widget)
    qt_widget.show()
    qapp.processEvents()
    qt_table = qt_widget.auto_form.findChildren(ChiTableWidget)[0]
    qt_model = qt_table._view.model()
    titles = [str(qt_model.headerData(c, 1)) for c in range(qt_model.columnCount())]
    qt_cells = [
        [str(qt_model.index(r, c).data() or "") for c in range(qt_model.columnCount())]
        for r in range(qt_model.rowCount())
    ]

    app = loaded_app(temp_db)
    rows, columns = app.displayed()
    assert [title for _k, title in columns] == [t for _k, t in TABLE_COLUMNS]
    emtk_cells = [[str(r[key]) for key, _t in columns] for r in rows]
    shared = [t for _k, t in TABLE_COLUMNS]
    assert titles[: len(shared)] == shared
    assert emtk_cells == [row[: len(shared)] for row in qt_cells]
    assert len(emtk_cells) == 11 and "alice" in [r[1] for r in emtk_cells]
    assert (
        app.model.status_text()
        == qt_widget.model.status_text()
        == ("11 user(s). Signed in as 'admin'.")
    )

    # select the same account in both and compare every field
    qt_table._view.selectRow(2)
    qapp.processEvents()
    qt_key = qt_widget.model._selected_id
    click_row(app, qt_key)
    draw(app)
    edits = [e.text() for e in qt_widget.auto_form.findChildren(QtWidgets.QLineEdit)][:10]
    assert edits == [str(getattr(app.model, name)) for name in FIELDS]
    boxes = qt_widget.auto_form.findChildren(QtWidgets.QCheckBox)
    assert [b.isChecked() for b in boxes] == [app.model.is_admin, app.model.allow_autologin]
    assert app.model.details_text() == qt_widget.model.details_text() == "### Bob Baker\n"

    # an administrator and a passwordless account carry their flags in both
    for key in ("alice", "carol"):
        click_row(app, key)
        qt_widget.model.select_row({"username": key})
        assert app.model.is_admin == qt_widget.model.is_admin
        assert app.model.allow_autologin == qt_widget.model.allow_autologin
    assert app.model.is_admin is False and app.model.allow_autologin is True


def test_password_rule_matches_the_qt_dialog(qapp, qtbot):
    from chisurf.plugins.core.user_editor.gui.model import (
        password_strength,
        strength_label,
    )
    from chisurf.plugins.core.user_editor.gui.tool import PasswordChangeDialog

    dialog = PasswordChangeDialog(user_id="bob", is_admin=False)
    qtbot.addWidget(dialog)
    for text in ("", "a", "abcdefgh", "Abcdefgh", "Abcdefg1", "Abcdef1!", "ABC123!!", "aA1!"):
        dialog.on_password_changed(text)
        score, missing = password_strength(text)
        assert score == dialog.score, text
        assert strength_label(text).replace("Strength: ", "") == (
            dialog.strength_label.text().replace("Strength: ", "")
        ), text
        if text and score < 5:
            assert dialog.feedback_label.text() == "Requirements: " + ", ".join(missing)


# ── 2. the table: rows, empty state, errors ─────────────────────────────


def test_table_rows_are_the_accounts_and_keep_their_identity():
    app = loaded_app()
    model = app.model
    assert shown(app) == ["admin", "bob", "carol", "dave", "guest"]
    first = model.user_records()
    assert model.user_records() is first
    row = next(r for r in first if r["username"] == "carol")
    assert row["user"] == "Carol Chen" and row["role"] == "PhD Student"
    assert row["autologin"] == "yes" and row["admin"] == "" and row["active"] == ""
    assert next(r for r in first if r["username"] == "admin")["active"] == "★"
    assert next(r for r in first if r["username"] == "admin")["admin"] == "yes"
    assert model.status_text() == "5 user(s). Signed in as 'admin'."


def test_a_refused_listing_shows_the_reason_and_no_rows():
    client = FakeServer(known_users(), fail_list="Authentication required")
    app = make_app(client, autoload=True)
    pump(app)
    painter = draw(app)
    assert app.model.users == [] and shown(app) == []
    assert "Listing users requires an administrator account" in app.model.status_text()
    assert any("administrator" in s for s in painter.strings)
    assert not any("Bob" in s or "bob" in s for s in painter.strings)


def test_an_unreachable_server_says_so_and_invents_nothing():
    from chisurf.plugins.core.user_editor.gui.app import UserEditorApp
    from chisurf.plugins.core.user_editor.gui.model import UserEditorModel

    app = UserEditorApp(UserEditorModel(), autoload=True)  # the offline factory of the fixture
    pump(app)
    painter = draw(app)
    assert shown(app) == []
    assert "Could not reach the MMFDB server: timeout" in app.model.status_text()
    assert any("Could not reach the MMFDB server" in s for s in painter.strings)
    assert "No user selected" in painter.strings
    assert not app.model.enabled("do_save") and not app.model.enabled("ask_delete")


def test_permission_denied_from_the_real_server_matches_the_qt_message(qapp, qtbot, temp_db):
    """A plain account may not list users: both windows say the same."""
    from chisurf.plugins.core.user_editor.gui.tool import UserEditorWidget
    from chisurf.plugins.core.user_editor.gui.view_model import UserEditorViewModel

    plain = seeded_db.admin_client(seeded_db.PLAIN_USER)
    qt_widget = UserEditorWidget(view_model=UserEditorViewModel(client_factory=lambda: plain))
    qtbot.addWidget(qt_widget)
    qt_widget.model.ensure_loaded()
    app = loaded_app(plain)
    assert app.model.users == [] and shown(app) == []
    assert app.model.status_text() == qt_widget.model.status_text()
    # the server answered "Permission denied": that is a permission, not an unreachable server
    assert app.model.status_text().startswith("Listing users requires an administrator account")
    assert "Could not reach" not in app.model.status_text()


def test_first_frame_loads_in_the_background():
    client = FakeServer(known_users())
    client.gate = threading.Event()
    app = make_app(client, autoload=True)
    assert app.model.users == []
    painter = draw(app, frames=2)
    assert app.job.busy and not app.model.enabled("do_reload")
    assert any(s.startswith("Working...") for s in painter.strings)
    assert shown(app) == [], "rows appeared before the server answered"
    client.gate.set()
    pump(app)
    assert len(app.model.users) == 5 and client.listed == 1
    draw(app)
    assert client.listed == 1, "the list was fetched again on a later frame"


def test_reload_picks_up_a_change_made_elsewhere():
    client = FakeServer(known_users())
    app = loaded_app(client)
    client.users["zed"] = record("zed", "Zed Zimmer")
    app.model.do_reload()
    assert app.job.busy
    pump(app)
    assert "zed" in shown(app)
    assert app.model.status_text() == "6 user(s). Signed in as 'admin'."


# ── 3. search, sort, selection ──────────────────────────────────────────


def test_filter_box_narrows_the_rows_in_any_column():
    app = loaded_app()
    assert len(shown(app)) == 5
    table(app).filter.set_text("car")
    draw(app)
    assert shown(app) == ["carol"]
    table(app).filter.set_text("PhD")  # the role column
    draw(app)
    assert shown(app) == ["carol"]
    table(app).filter.set_text("yes")  # admin and autologin cells
    draw(app)
    assert shown(app) == ["admin", "carol"]
    table(app).filter.set_text("nobody")
    draw(app)
    assert shown(app) == [] and "0 of 5 rows" in table(app).status_text()
    table(app).filter.set_text("")
    draw(app)
    assert len(shown(app)) == 5 and table(app).status_text() == "5 rows × 6 columns"


def test_header_sort_orders_the_rows_and_reverses():
    app = loaded_app()
    table(app).sort_by("role", False)
    draw(app)
    roles = [r["role"] for r in app.displayed()[0]]
    assert roles == sorted(roles, key=str.lower) or roles == sorted(roles)
    table(app).sort_by("role", True)
    draw(app)
    assert [r["role"] for r in app.displayed()[0]] == list(reversed(roles))
    table(app).sort_by("user", False)
    draw(app)
    assert shown(app) == ["admin", "bob", "carol", "dave", "guest"]


def test_selecting_a_row_fills_the_form_with_that_account():
    app = loaded_app()
    model = app.model
    assert model.selected is None and model.user_id == ""
    click_row(app, "bob")
    painter = draw(app)
    assert model.selected_key == "bob"
    assert [getattr(model, f) for f in FIELDS[:3]] == ["bob", "Bob Baker", "bob@example.org"]
    assert (model.affiliation, model.department, model.role) == ("Biophysics", "FCS", "Postdoc")
    assert "Bob Baker" in painter.strings and "bob@example.org" in painter.strings
    assert not model.dirty and not model.enabled("do_save")
    click_row(app, "carol")
    draw(app)
    assert model.allow_autologin is True and model.is_admin is False and model.role == "PhD Student"
    assert model.status_text() == "5 user(s). Signed in as 'admin'."


def test_a_role_stored_by_another_tool_is_listed_and_kept():
    """The Qt combo is editable; here the stored role is a choice, never shown as Generic."""
    app = loaded_app()
    click_row(app, "dave")
    draw(app)
    assert app.model.role == "Facility Manager"
    assert app.model.role_options()[-1] == "Facility Manager"
    assert app.model.role_options()[:-1] == list(
        __import__("chisurf.plugins.core.user_editor.api.records", fromlist=["x"]).ROLE_OPTIONS
    )
    click_row(app, "bob")
    assert "Facility Manager" not in app.model.role_options()


def test_the_table_follows_a_selection_made_in_code():
    app = loaded_app()
    app.model.select_key("carol")
    draw(app)
    assert table(app).selected_key == "carol"
    app.model.new_user()
    draw(app)
    assert table(app).selected_key is None


# ── 4. editing, dirty, Save, Revert ─────────────────────────────────────


def test_editing_marks_the_account_dirty_and_enables_save():
    app = loaded_app()
    model = app.model
    click_row(app, "bob")
    assert not model.dirty and not model.enabled("do_save") and not model.enabled("ask_revert")
    model.display_name = "Robert Baker"
    assert model.dirty and model.enabled("do_save") and model.enabled("ask_revert")
    assert model.status_text().endswith("unsaved changes")
    assert model.users[1].display_name == "Bob Baker", "the table changed before saving"
    painter = draw(app)
    assert "Robert Baker" in painter.strings
    assert "Bob Baker" in [r["user"] for r in model.user_records()]


def test_a_committed_field_marks_dirty_and_stays_local():
    """What a field does when Enter or a click away commits it: ``setattr`` on the model."""
    from emtk.view_form import _commit

    app = loaded_app()
    click_row(app, "bob")
    draw(app)
    section = next(
        s for s in _walk(app.panels["account"]["sections"]) if s.get("attr") == "display_name"
    )
    _commit(app.model, section, "Robert", app.form)
    assert app.model.display_name == "Robert" and app.model.dirty
    assert app.model.users[1].display_name == "Bob Baker"


def test_save_writes_the_temporary_database(temp_db):
    app = loaded_app(temp_db)
    click_row(app, "bob")
    app.model.display_name = "Robert Baker"
    app.model.phone = "+49 1"
    app.model.do_save()
    assert app.job.busy and not app.model.enabled("do_save")
    pump(app)
    assert "Saved 'Robert Baker'" in app.model.status_text()
    assert not app.model.dirty and app.model.selected_key == "bob"
    # a fresh client reads the change back from the temporary database
    fresh = {u["user_id"]: u for u in seeded_db.admin_client().list_users()}
    assert fresh["bob"]["display_name"] == "Robert Baker" and fresh["bob"]["phone"] == "+49 1"
    assert (
        fresh["bob"]["email"] == "bob@example.org"
        and fresh["carol"]["display_name"] == "Carol Chen"
    )
    assert [r["user"] for r in app.model.user_records() if r["username"] == "bob"] == [
        "Robert Baker"
    ]


def test_a_staged_password_alone_is_saved_and_works_for_sign_in(temp_db):
    """Set bob's password on the real server, with no other edit, and sign in with it."""
    app = loaded_app(temp_db)
    click_row(app, "bob")
    assert not app.model.enabled("do_save")
    app.model.ask_password()
    app.model.password_new = app.model.password_confirm = "Abcdef1!"
    app.model.password_set()
    assert app.model.enabled("do_save") and not app.model.dirty
    app.model.do_save()
    pump(app)
    assert "Saved 'Bob Baker'" in app.model.status_text() and not app.model.password_staged
    from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient

    fresh = MMFDBClient(inprocess=True)
    assert fresh.login("bob", "Abcdef1!", quiet=True)["ok"]
    with pytest.raises(Exception):
        MMFDBClient(inprocess=True).login("bob", "wrong-password", quiet=True)


def test_reverting_a_staged_password_forgets_it():
    app = loaded_app()
    click_row(app, "bob")
    app.model.stage_password("abcdefgh")
    app.model.ask_revert()
    assert app.model.confirm == "revert"
    app.model.confirm_yes()
    assert not app.model.password_staged and not app.model.enabled("do_save")


def test_rename_carries_the_session_token(temp_db, renames):
    app = loaded_app(temp_db)
    click_row(app, "erin")
    app.model.user_id = "erin2"
    app.model.do_save()
    pump(app)
    assert renames == [("erin", "erin2")]
    ids = {u["user_id"] for u in seeded_db.admin_client().list_users()}
    assert "erin2" in ids and "erin" not in ids


def test_the_flags_are_saved(temp_db):
    """Administrator and passwordless sign-in, written and read back from the database."""

    def stored(user_id):
        return {u["user_id"]: u for u in seeded_db.admin_client().list_users()}[user_id]

    app = loaded_app(temp_db)
    click_row(app, "bob")
    app.model.is_admin = True
    app.model.do_save()
    pump(app)
    assert stored("bob")["is_admin"] and not stored("bob")["allow_passwordless_login"]
    row = next(r for r in app.model.user_records() if r["username"] == "bob")
    assert row["admin"] == "yes" and row["autologin"] == ""
    click_row(app, "erin")
    app.model.allow_autologin = True
    app.model.do_save()
    pump(app)
    assert stored("erin")["allow_passwordless_login"] and not stored("erin")["is_admin"]
    row = next(r for r in app.model.user_records() if r["username"] == "erin")
    assert row["autologin"] == "yes"
    click_row(app, "erin")
    app.model.allow_autologin = False
    app.model.is_admin = False
    app.model.do_save()
    pump(app)
    assert not stored("erin")["allow_passwordless_login"]


def test_the_server_refuses_passwordless_sign_in_for_an_administrator(temp_db):
    """The form says so ("Administrators may not use it"); the table shows what the server kept."""
    app = loaded_app(temp_db)
    click_row(app, "carol")  # seeded with passwordless sign-in
    assert app.model.allow_autologin is True
    app.model.is_admin = True
    app.model.do_save()
    pump(app)
    row = next(r for r in app.model.user_records() if r["username"] == "carol")
    assert row["admin"] == "yes" and row["autologin"] == ""
    assert app.model.allow_autologin is False, "the form still shows what the server dropped"


def test_save_refuses_a_problem_without_calling_the_server():
    client = FakeServer(known_users())
    app = loaded_app(client)
    click_row(app, "bob")
    app.model.email = "not-an-email"
    app.model.do_save()
    assert not app.job.busy and client.saved == []
    assert (
        "Cannot save:" in app.model.status_text()
        and "not a valid e-mail" in app.model.status_text()
    )
    assert "Cannot save yet" in app.model.details_text()
    app.model.email = "bob@example.org"
    app.model.website = "example.org"
    app.model.do_save()
    assert client.saved == [] and "http://" in app.model.status_text()


def test_a_server_failure_on_save_is_shown_not_raised():
    client = FakeServer(known_users(), fail_save="Permission denied")
    app = loaded_app(client)
    click_row(app, "bob")
    app.model.display_name = "Robert"
    app.model.do_save()
    pump(app)
    assert "Cannot save: Permission denied" in app.model.status_text()
    assert app.model.dirty, "the edits were lost on a failed save"


def test_revert_asks_first_and_restores_the_server_version():
    app = loaded_app()
    model = app.model
    click_row(app, "bob")
    model.ask_revert()
    assert model.confirm == "" and model.status_text().startswith("Nothing to revert.")
    model.display_name = "Robert"
    model.is_admin = True
    model.ask_revert()
    assert model.confirm == "revert" and "Discard the edits" in model.confirm_text
    model.confirm_no()
    assert model.dirty and model.display_name == "Robert" and model.confirm == ""
    model.ask_revert()
    model.confirm_yes()
    assert not model.dirty and model.display_name == "Bob Baker" and model.is_admin is False


def test_confirmation_dialog_opens_on_screen_and_cancel_leaves_state():
    app = loaded_app()
    click_row(app, "bob")
    app.model.display_name = "Robert"
    app.model.ask_revert()
    painter = draw(app)
    assert app.confirm_window.open
    assert "Discard changes" in painter.strings and "Cancel" in painter.strings
    assert "Discard the edits to this account?" in painter.strings
    app.model.confirm_no()
    draw(app)
    assert not app.confirm_window.open and app.model.display_name == "Robert"


# ── 5. New ──────────────────────────────────────────────────────────────


def test_new_starts_a_blank_account_and_refuses_an_empty_username():
    client = FakeServer(known_users())
    app = loaded_app(client)
    click_row(app, "bob")
    app.model.new_user()
    model = app.model
    draw(app)
    assert model.user_id == "" and model.display_name == "" and model.role == "Generic"
    assert model.dirty and model.edited.user_uuid and model.selected is None
    assert "New account" in model.details_text()
    model.do_save()
    assert client.saved == []
    assert "A username is required." in model.status_text()
    assert "A display name is required." in model.status_text()


def test_new_refuses_a_duplicate_username_and_one_with_spaces():
    client = FakeServer(known_users())
    app = loaded_app(client)
    model = app.model
    model.new_user()
    model.user_id, model.display_name = "bob", "Another Bob"
    model.do_save()
    assert client.saved == [] and "A user called 'bob' already exists." in model.status_text()
    model.user_id = "a b"
    model.do_save()
    assert client.saved == [] and "must not contain spaces" in model.status_text()


def test_new_creates_the_account_in_the_temporary_database(temp_db):
    app = loaded_app(temp_db)
    model = app.model
    model.new_user()
    model.user_id, model.display_name = "frank", "Frank Fischer"
    model.email, model.role, model.is_admin = "frank@example.org", "Technician", False
    model.do_save()
    pump(app)
    assert "Saved 'Frank Fischer'" in model.status_text()
    assert model.selected_key == "frank" and "frank" in shown(app) and not model.dirty
    stored = {u["user_id"]: u for u in seeded_db.admin_client().list_users()}["frank"]
    assert stored["display_name"] == "Frank Fischer" and stored["role"] == "Technician"
    # an existing name is refused before the server (the same rule as the Qt tool)
    model.new_user()
    model.user_id, model.display_name = "frank", "Second Frank"
    model.do_save()
    assert "already exists" in model.status_text()


# ── 6. Delete ───────────────────────────────────────────────────────────


def test_delete_asks_first_and_deletes_only_the_selected_account(temp_db):
    app = loaded_app(temp_db)
    model = app.model
    before = set(shown(app))
    assert not model.enabled("ask_delete")
    model.ask_delete()
    assert model.confirm == "" and "No user selected" in model.status_text()
    click_row(app, "bob")
    model.ask_delete()
    assert model.confirm == "delete" and "Permanently delete 'Bob Baker'?" == model.confirm_text
    model.confirm_no()
    pump(app)
    assert set(shown(app)) == before and "bob" in {
        u["user_id"] for u in seeded_db.admin_client().list_users()
    }
    model.ask_delete()
    model.confirm_yes()
    assert app.job.busy
    pump(app)
    assert set(shown(app)) == before - {"bob"}
    assert model.status_text().startswith("Deleted 'bob'.")
    ids = {u["user_id"] for u in seeded_db.admin_client().list_users()}
    assert ids == before - {"bob"}
    assert model.selected is None and model.user_id == ""


def test_delete_dialog_names_the_account_on_screen():
    app = loaded_app()
    click_row(app, "carol")
    app.model.ask_delete()
    painter = draw(app)
    assert "Delete user" in painter.strings
    assert "Permanently delete 'Carol Chen'?" in painter.strings


def test_builtin_and_active_accounts_are_not_deleted():
    client = FakeServer(known_users())
    app = loaded_app(client)
    model = app.model
    click_row(app, "guest")
    model.ask_delete()
    assert model.confirm == "" and "'guest' is a built-in account" in model.status_text()
    click_row(app, "admin")
    model.ask_delete()
    assert model.confirm == "" and "account ChiSurf is using" in model.status_text()
    assert client.deleted == []


def test_a_refused_delete_offers_force_to_an_administrator():
    client = FakeServer(known_users(), fail_delete="Account owns committed data")
    app = loaded_app(client)
    model = app.model
    click_row(app, "bob")
    model.ask_delete()
    model.confirm_yes()
    pump(app)
    assert model.confirm == "force_delete"
    assert (
        "Account owns committed data" in model.confirm_text
        and "Force the deletion?" in model.confirm_text
    )
    painter = draw(app)
    assert "Force delete" in painter.strings
    model.confirm_no()
    assert "bob" in client.users and client.deleted == [("bob", False, "admin")]
    model.ask_delete()
    model.confirm_yes()
    pump(app)
    model.confirm_yes()
    pump(app)
    assert client.deleted[-1] == ("bob", True, "admin") and "bob" not in client.users
    assert "bob" not in shown(app)


def test_a_refused_delete_only_explains_itself_to_a_plain_user():
    users = known_users()
    users[0]["is_admin"] = 0  # the signed-in account is not an administrator
    client = FakeServer(users, fail_delete="Account owns committed data")
    app = loaded_app(client)
    click_row(app, "bob")
    app.model.ask_delete()
    app.model.confirm_yes()
    pump(app)
    assert app.model.confirm == ""
    assert "Cannot delete: Account owns committed data" in app.model.status_text()
    assert "bob" in client.users


# ── 7. password ─────────────────────────────────────────────────────────


def test_password_prompt_needs_an_account():
    app = loaded_app()
    app.model.ask_password()
    assert not app.model.password_open and "No user selected" in app.model.status_text()
    assert not app.model.enabled("ask_password")
    click_row(app, "bob")
    assert app.model.enabled("ask_password")
    app.model.ask_password()
    assert app.model.password_open and app.model.password_title == "Change Password for bob"


def test_password_mismatch_empty_and_weak_admin_password_are_refused():
    client = FakeServer(known_users())
    app = loaded_app(client)
    model = app.model
    click_row(app, "bob")
    model.ask_password()
    model.password_set()
    assert model.password_error == "Enter a password." and model.password_open
    model.password_new, model.password_confirm = "Abcdef1!", "Abcdef1"
    model.password_set()
    assert model.password_error == "Passwords do not match." and model.password_open
    assert not model.password_staged
    assert model.password_feedback() == "Passwords do not match."
    model.password_new, model.password_confirm = "abc", "abc"  # weak is fine for a plain user
    model.password_set()
    assert model.password_staged and not model.password_open
    model.revert()
    # an administrator needs at least Medium
    click_row(app, "bob")
    model.is_admin = True
    model.ask_password()
    model.password_new = model.password_confirm = "abc"
    model.password_set()
    assert (
        "Administrator password is too weak" in model.password_error and not model.password_staged
    )
    model.password_new = model.password_confirm = "Abcdef1!"
    model.password_set()
    assert model.password_staged


def test_a_staged_password_is_sent_with_save_and_forgotten_after():
    client = FakeServer(known_users())
    app = loaded_app(client)
    click_row(app, "bob")
    app.model.ask_password()
    app.model.password_new = app.model.password_confirm = "S3cret!pw"
    app.model.password_set()
    assert app.model.password_new == "" and app.model.password_confirm == ""
    assert "a new password is staged" in app.model.status_text()
    # a password can be set on its own: Save and Revert are usable without any field edit
    assert (
        app.model.dirty is False
        and app.model.enabled("do_save")
        and app.model.enabled("ask_revert")
    )
    app.model.do_save()
    pump(app)
    assert client.saved[-1]["password"] == "S3cret!pw"
    assert client.saved[-1]["display_name"] == "Bob Baker"
    assert (
        "staged" not in app.model.status_text() and "Saved 'Bob Baker'" in app.model.status_text()
    )
    assert not app.model.password_staged and not app.model.enabled("do_save")


def test_a_staged_password_travels_with_a_save_of_edited_fields_too():
    """The password is applied with the next Save, whether or not fields were edited."""
    client = FakeServer(known_users())
    app = loaded_app(client)
    click_row(app, "bob")
    app.model.stage_password("abcdefgh")
    assert app.model.password_staged
    app.model.email = "robert@example.org"
    app.model.do_save()
    pump(app)
    assert client.saved[-1]["password"] == "abcdefgh"


def test_password_prompt_masks_what_is_typed_and_cancel_forgets_it():
    app = loaded_app()
    click_row(app, "bob")
    app.model.ask_password()
    app.model.password_new = "Abcdef1!"
    app.model.password_confirm = "Abc"
    painter = draw(app)
    assert app.password_window.open
    assert "Change Password for bob" in painter.strings
    assert "********" in painter.strings and "***" in painter.strings
    assert not any("Abcdef1" in s or s == "Abc" for s in painter.strings)
    assert "Strength: Strong" in painter.strings
    app.model.password_cancel()
    draw(app)
    assert not app.password_window.open
    assert app.model.password_new == "" and app.model.password_confirm == ""


def test_the_password_entries_are_drawn_with_the_password_flag():
    from emtk import im

    seen = []
    original = im.input_text

    def spy(label, value="", hint="", flags=0, *a, **k):
        seen.append((label, flags))
        return original(label, value, hint, flags, *a, **k)

    app = loaded_app()
    click_row(app, "bob")
    app.model.ask_password()
    import unittest.mock as mock

    with mock.patch.object(im, "input_text", spy):
        draw(app, frames=2)
    flags = {label: f for label, f in seen if label in ("##password_new", "##password_confirm")}
    assert set(flags) == {"##password_new", "##password_confirm"}
    assert all(f & im.InputTextFlags.PASSWORD for f in flags.values())


# ── 8. copy and export ──────────────────────────────────────────────────


def test_export_csv_follows_the_filter_and_the_columns(tmp_path):
    app = loaded_app()
    table(app).filter.set_text("a")
    table(app).set_column_hidden("autologin", True)
    draw(app)
    names = shown(app)
    app.model.request_export()
    draw(app)
    assert app.dialog is not None and app.dialog.title == "Export users as CSV"
    target = tmp_path / "out.csv"
    assert app.model.export_csv(str(target))
    rows = list(csv.reader(target.open(encoding="utf-8")))
    assert rows[0] == ["User", "Username", "Role", "Admin", "Active"]
    assert [r[1] for r in rows[1:]] == names
    assert f"Exported {len(names)} rows" in app.model.status_text()
    assert app.model.export_csv(str(tmp_path / "missing" / "x.csv")) is False
    assert "Could not write" in app.model.status_text()


def test_copy_puts_the_shown_rows_with_headers_on_the_clipboard(monkeypatch):
    from emtk import im

    copied = []
    monkeypatch.setattr(im, "set_clipboard_text", copied.append)
    app = loaded_app()
    table(app).filter.set_text("carol")
    draw(app)
    app.model.request_copy()
    draw(app)
    lines = copied[0].splitlines()
    assert lines[0].split("\t") == ["User", "Username", "Role", "Admin", "Autologin", "Active"]
    assert len(lines) == 2 and lines[1].startswith("Carol Chen\tcarol\tPhD Student")
    assert "Copied 1 rows" in app.model.status_text()


# ── 9. drawing ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_app_draws_populated_and_empty_at_both_sizes(size):
    app = loaded_app()
    click_row(app, "bob")
    painter = draw(app, size)
    strings = painter.strings
    for expected in (
        "Accounts",
        "Account",
        "Save",
        "Revert",
        "Reload",
        "New",
        "Delete",
        "Password...",
        "Copy",
        "Export CSV",
        "Help",
        "Guide",
        "Username",
        "Display name",
        "E-mail",
        "Role",
        "Affiliation",
        "Department",
        "Phone",
        "Website",
        "Address",
        "Notes",
        "Administrator",
        "Allow sign-in without a password",
    ):
        assert expected in strings, expected
    assert "bob" in strings and "carol" in strings  # (display names are elided when narrow)
    assert any("5 user(s)" in s for s in strings)
    empty = draw(make_app(FakeServer()), size)
    assert "Accounts" in empty.strings and "No user selected" in empty.strings
    assert "Bob Baker" not in empty.strings and "Username" in empty.strings


def test_every_dialog_draws_inside_a_small_window():
    app = loaded_app()
    click_row(app, "bob")
    app.model.ask_password()
    draw(app, (800, 600))
    app.model.password_cancel()
    app.model.display_name = "x"
    app.model.ask_revert()
    draw(app, (800, 600))
    assert app.confirm_window.open and app.confirm_window.box[0] + app.confirm_window.box[2] <= 800


# ── 10. spec, tooltips, guide, help ─────────────────────────────────────


def _walk(sections):
    for section in sections:
        yield section
        yield from _walk(section.get("sections", []))


def test_every_spec_key_exists_on_the_model():
    app = make_app()
    model = app.model
    spec = json.loads(SPEC_FILE.read_text())
    for section in _walk(spec["sections"]):
        for key in ("attr", "call", "source", "options_source", "text_source"):
            if section.get(key):
                assert hasattr(model, section[key]), (section.get("type"), key, section[key])
        for button in section.get("buttons", []):
            assert callable(getattr(model, button["action"])), button["action"]
        options = section.get("options") or {}
        for key in ("source", "selected_call"):
            if options.get(key):
                assert hasattr(model, options[key]), options[key]
        if section.get("type") == "custom" and section.get("key") != "data_table":
            assert section["key"] in app.form.custom, section["key"]
        columns = [c["key"] for c in options.get("columns", [])]
        if columns:
            model.users = [
                __import__("chisurf.plugins.core.user_editor.api.records", fromlist=["x"]).UserRow(
                    user_id="x"
                )
            ]
            assert set(columns) <= set(model.user_records()[0]), columns


def test_every_control_has_a_tooltip():
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    inventory = emtk_inventory(build_emtk_app("user_editor"))
    assert inventory["controls_without_tooltip"] == []
    spec = json.loads(SPEC_FILE.read_text())
    for section in _walk(spec["sections"]):
        if section.get("type") in (
            "value",
            "choice",
            "toggle",
            "table",
            "data_table",
            "custom",
            "info",
            "button_row",
            "panel",
            "progress",
        ):
            assert section.get("description"), (
                section.get("attr") or section.get("title") or section
            )
        for column in (section.get("options") or {}).get("columns", []):
            assert column.get("tooltip"), column
        for button in section.get("buttons", []):
            assert button.get("description"), button


def test_the_populated_app_has_no_untooltipped_control_either():
    from test.gui.emtk_port_parity import emtk_inventory

    app = loaded_app()
    click_row(app, "bob")
    app.model.ask_password()
    inventory = emtk_inventory(app)
    # the shared dialog window's close button is emtk's and has no tooltip (reported)
    assert set(inventory["controls_without_tooltip"]) <= {"button: ×"}
    labels = {row["label"] for row in inventory["interactive"]}
    assert {
        "Save",
        "Revert",
        "Reload",
        "New",
        "Delete",
        "Password...",
        "Copy",
        "Export CSV",
        "Help",
        "Guide",
        "Administrator",
        "Allow sign-in without a password",
    } <= labels


def test_guide_steps_point_at_controls_the_app_draws():
    from chisurf.emtk.help_guide import EmTkGuidedTour

    app = loaded_app()
    click_row(app, "bob")
    draw(app)
    steps = json.loads((GUI / "guide.json").read_text())["steps"]
    assert len(steps) >= 6
    for step in steps:
        name = EmTkGuidedTour._target_key(step["target"])
        rect = app.item_rects.get(name) or app.form.rects.get(name)
        assert rect is not None, f"{step['title']}: nothing drawn for {name!r}"
    awaiting = [EmTkGuidedTour._target_key(s["target"]) for s in steps if s.get("await")]
    assert awaiting == ["row_selected", "display_name", "ask_password", "do_save"]


def test_the_tour_hears_the_row_pick_the_edit_and_the_buttons():
    app = loaded_app()
    draw(app)
    heard = []
    app.tour.notify_used = heard.append
    app.form.on_used = app.tour.notify_used
    click_row(app, "bob")
    draw(app)
    assert "row_selected" in heard
    section = next(
        s for s in _walk(app.panels["account"]["sections"]) if s.get("attr") == "display_name"
    )
    from emtk.view_form import _commit

    _commit(app.model, section, "Robert", app.form)
    assert "display_name" in heard
    app.form.used("ask_password")
    app.form.used("do_save")
    assert "ask_password" in heard and "do_save" in heard


def test_help_exists_and_its_links_are_live():
    import re

    help_text = (GUI / "help.md").read_text()
    assert "Export CSV" in help_text and "Delete" in help_text
    repo = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
    for target in re.findall(r"\]\((docs/[^)#]+)\)", help_text):
        assert (repo / target).is_file(), target
    app = loaded_app()
    app.help_window.show()
    assert draw(app).strings


# ── 11. persistence, the status fix, no Qt ──────────────────────────────


def test_settings_round_trip_restores_the_selection_once_loaded():
    app = loaded_app()
    click_row(app, "carol")
    saved = app.export_settings()
    assert saved == {"selected_key": "carol"}
    json.dumps(saved)
    other = make_app(FakeServer(known_users()), autoload=True)
    other.restore_settings(saved)
    pump(other)
    draw(other)
    assert other.model.selected_key == "carol" and other.model.display_name == "Carol Chen"
    assert table(other).selected_key == "carol"
    other.restore_settings({"selected_key": "ghost"})
    pump(other)
    draw(other)
    assert other.model.selected_key == "carol"  # a gone account is not selected


def test_a_stale_message_does_not_outlive_the_selection_it_was_about():
    """ "New account..." and "Changes discarded." used to stay on the status line."""
    app = loaded_app()
    model = app.model
    model.new_user()
    assert "New account" in model.status_text()
    click_row(app, "bob")
    assert model.status_text() == "5 user(s). Signed in as 'admin'."
    model.display_name = "x"
    model.ask_revert()
    model.confirm_yes()
    assert model.status_text() == "Changes discarded."
    click_row(app, "carol")
    assert model.status_text() == "5 user(s). Signed in as 'admin'."


def test_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("user_editor")
    assert result["ok"], result["output"]
