"""The native switch-user port: model equals the Qt login dialog, actions, drawing, no Qt.

Hermetic: settings, MMFDB database and credential store are temporary or stubbed (see the
``world`` fixture); one test proves the real ``~/.chisurf`` settings file is not touched.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path

import pytest
import yaml
from emtk.testing import RecordingPainter

PLUGIN = Path(__file__).resolve().parents[1]
SPEC_FILE = PLUGIN / "switch_user_emtk.view.json"
GUIDE_FILE = PLUGIN / "guide.json"
SIZES = [(1200, 800), (800, 600)]

BASE = {
    "client": {"mode": "embedded", "username": "alice", "host": "127.0.0.1",
               "cmd_port": 8765, "pub_port": 8766},
    "server_history": ["127.0.0.1", "lab-server.example.org", "10.0.0.7"],
    "last_server": "lab-server.example.org", "last_port": 9100,
    "save_login": True, "autologin": False,
}


class FakeClient:
    """Stands in for the MMFDB client: records the call, answers as told."""

    def __init__(self, answer=None, error=None):
        self.answer = {"ok": True, "token": "fake-token"} if answer is None else answer
        self.error = error
        self.calls = []

    def login(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.answer


class World:
    """Temporary settings + stubbed credential store, and what happened to them."""

    def __init__(self, folder, cs, creds):
        self.folder, self.cs, self.creds = folder, cs, creds
        self.token_calls = []
        self.store_ok = True

    @property
    def yaml(self):
        path = self.folder / "settings_chisurf.yaml"
        return yaml.safe_load(path.read_text())["mmfdb"] if path.exists() else None

    def configure(self, mmfdb):
        self.cs.cs_settings["mmfdb"] = copy.deepcopy(mmfdb)


def real_settings_path() -> Path:
    return Path.home() / ".chisurf" / "settings_chisurf.yaml"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "absent"


@pytest.fixture
def world(tmp_path, monkeypatch):
    from mmfdb.security import credentials as creds

    import chisurf.core.settings as cs

    for key, sub in (("CHISURF_SETTINGS_DIR", ""), ("MMFDB_SETTINGS_DIR", ""),
                     ("MMFDB_DATABASE_PATH", "mmfdb.db")):
        monkeypatch.setenv(key, str(tmp_path / sub) if sub else str(tmp_path))
    saved = copy.deepcopy(cs.cs_settings.get("mmfdb", None))
    had = "mmfdb" in cs.cs_settings
    w = World(tmp_path, cs, creds)
    w.configure(BASE)

    def store(host, port, user, token):
        w.token_calls.append(("store", host, port, user, token))
        return w.store_ok

    def delete(host, port, user):
        w.token_calls.append(("delete", host, port, user))
        return True

    monkeypatch.setattr(creds, "store_session_token", store)
    monkeypatch.setattr(creds, "delete_session_token", delete)
    monkeypatch.setattr(creds, "_RUNTIME_SESSION_TOKENS", {})
    yield w
    if had:
        cs.cs_settings["mmfdb"] = saved
    else:
        cs.cs_settings.pop("mmfdb", None)


@pytest.fixture
def model(world):
    from chisurf.plugins.core.switch_user.model import SwitchUserModel

    client = FakeClient()
    m = SwitchUserModel(client_factory=lambda mode, server, port: client)
    m.fake = client
    return m


@pytest.fixture
def app(world):
    from chisurf.plugins.core.switch_user.app import SwitchUserApp

    return SwitchUserApp(client=FakeClient())


def frames(app, size=(1200, 800), n=3):
    painter = None
    for _ in range(n):
        painter = RecordingPainter()
        app.draw(painter, 0.0, 0.0, float(size[0]), float(size[1]))
    return painter


def click(app, label, size=(1200, 800), nth=0):
    painter = frames(app, size, 2)
    hits = [t for t in painter.texts if t[5] == label]
    if len(hits) <= nth:
        return False
    x, y, w, h = hits[nth][:4]
    x, y = x + w / 2.0, y + h / 2.0
    app.pointer_move(x, y)
    frames(app, size, 1)
    app.pointer_press(x, y, 1)
    frames(app, size, 1)
    app.pointer_release(x, y, 1)
    frames(app, size, 2)
    return True


def qt_login(world, cfg, user, password, server, port, save, auto, client, qapp, monkeypatch):
    """Run the legacy dialog's login on *cfg*; returns (accepted, dialogs, mmfdb settings, yaml)."""
    from test.gui import migration_parity  # noqa: F401  (keeps ``test`` resolvable)

    from chisurf import gui as g

    world.configure(cfg)
    shown = []
    for name in ("warning", "error", "information"):
        monkeypatch.setattr(g.dialogs, name,
                            lambda parent, title, text, _n=name: shown.append((_n, title, text)))
    dlg = g.LoginDialog()
    dlg.server_combo.setCurrentText(server)
    dlg.port_spin.setValue(port)
    dlg.user_combo.setCurrentText(user)
    dlg.password_edit.setText(password)
    dlg.save_login_check.setChecked(save)
    dlg.auto_login_check.setChecked(auto)
    dlg.client = client
    accepted = []
    dlg.accepted.connect(lambda: accepted.append(1))
    dlg.handle_login()
    result = copy.deepcopy(world.cs.cs_settings["mmfdb"])
    dlg.close()
    return bool(accepted), shown, result, world.yaml


# ------------------------------------------------ equal to the Qt dialog
def test_initial_fields_equal_the_qt_dialog(world, model, qapp):
    from chisurf import gui as g

    dlg = g.LoginDialog()
    items = lambda c: [c.itemText(i) for i in range(c.count())]  # noqa: E731
    assert model.server_history == items(dlg.server_combo)
    assert model.server == dlg.server_combo.currentText() == "lab-server.example.org"
    assert model.port == dlg.port_spin.value() == 9100
    assert (dlg.port_spin.minimum(), dlg.port_spin.maximum()) == model.bounds("port")
    assert model.known_users == items(dlg.user_combo) == ["alice", "user", "admin"]
    assert model.user == dlg.user_combo.currentText()
    assert model.save_login == dlg.save_login_check.isChecked() is True
    assert model.autologin == dlg.auto_login_check.isChecked() is False
    assert dlg.password_edit.echoMode() != dlg.password_edit.Normal and model.password == ""
    assert model.server_label == "Server"
    dlg.close()


def test_remote_mode_equals_the_qt_dialog(world, qapp):
    from qtpy import QtWidgets

    from chisurf import gui as g
    from chisurf.plugins.core.switch_user.model import SwitchUserModel

    world.configure({"client": {"mode": "remote", "base_url": "http://127.0.0.1:8080",
                                "username": "alice"}})
    dlg = g.LoginDialog()
    m = SwitchUserModel()
    labels = [w.text() for w in dlg.findChildren(QtWidgets.QLabel)]
    assert "MMFDB URL:" in labels and m.server_label == "MMFDB URL"
    assert m.remote and not dlg.port_spin.isVisible()
    assert [dlg.server_combo.itemText(i) for i in range(dlg.server_combo.count())] == m.server_history
    assert m.server == dlg.server_combo.currentText() == "http://127.0.0.1:8080"
    assert m.known_users == [dlg.user_combo.itemText(i) for i in range(dlg.user_combo.count())] == ["alice"]
    dlg.close()


@pytest.mark.parametrize("save,auto", [(True, False), (False, False), (True, True), (False, True)])
@pytest.mark.parametrize("server,port", [("10.0.0.7", 9200), ("new-host", 7000)])
def test_successful_login_persists_exactly_what_the_qt_dialog_did(
    world, model, qapp, save, auto, server, port, monkeypatch
):
    q_ok, q_shown, q_cfg, q_yaml = qt_login(
        world, BASE, "  admin ", "admin", server, port, save, auto, FakeClient(), qapp, monkeypatch)
    q_tokens = list(world.token_calls)
    world.token_calls.clear()
    world.creds._RUNTIME_SESSION_TOKENS.clear()
    for p in world.folder.glob("settings_chisurf.yaml"):
        p.unlink()
    world.configure(BASE)
    from chisurf.plugins.core.switch_user.model import SwitchUserModel

    client = FakeClient()
    m = SwitchUserModel(client_factory=lambda mode, s, p: client)
    m.user, m.password, m.server, m.port = "  admin ", "admin", server, port
    m.save_login, m.autologin = save, auto
    m.login()
    assert m.accepted == q_ok is True
    assert world.cs.cs_settings["mmfdb"] == q_cfg
    assert world.yaml == q_yaml
    assert world.token_calls == q_tokens
    assert client.calls == [{"user_id": "admin", "password": "admin"}]
    assert m.notices == [] and m.closed and q_shown == []
    assert sorted(world.creds._RUNTIME_SESSION_TOKENS) == [f"{server}:{port}:admin"]


def test_rejected_login_changes_nothing_like_the_qt_dialog(world, model, qapp, monkeypatch):
    for answer, expected in (({"ok": False, "error": "Incorrect credentials"}, "Incorrect credentials"),
                             ({"authenticated": False, "error": {"message": "Account locked"}}, "Account locked"),
                             ({"ok": False}, "Incorrect credentials")):
        world.configure(BASE)
        before = copy.deepcopy(world.cs.cs_settings["mmfdb"])
        q_ok, q_shown, q_cfg, q_yaml = qt_login(world, BASE, "admin", "x", "10.0.0.7", 9200,
                                                True, False, FakeClient(answer), qapp, monkeypatch)
        assert not q_ok and q_shown == [("warning", "Login Failed", expected)]
        assert q_cfg == before and q_yaml is None
        world.configure(BASE)
        model.fake.answer = answer
        model.user, model.password = "admin", "x"
        model.login()
        assert model.notices == [("warning", "Login Failed", expected)]
        assert not model.accepted and not model.closed
        assert world.cs.cs_settings["mmfdb"] == before and world.yaml is None
        assert world.token_calls == []
        model.notices.clear()


def test_exception_is_the_error_message_of_the_qt_dialog(world, model, qapp, monkeypatch):
    q_ok, q_shown, *_ = qt_login(world, BASE, "admin", "x", "h", 1, True, False,
                                 FakeClient(error=RuntimeError("Connection refused")), qapp, monkeypatch)
    model.fake.error = RuntimeError("Connection refused")
    model.login()
    assert q_shown == [("error", "Error", "Login failed: Connection refused")]
    assert model.notices == [q_shown[0]] and not model.accepted


def test_empty_user_falls_back_to_the_picked_account_like_qt(world, model, qapp, monkeypatch):
    client = FakeClient({"ok": False})
    qt_login(world, BASE, "", "x", "h", 1, True, False, client, qapp, monkeypatch)
    model.user, model.password = "", "x"
    model.login()
    assert client.calls[-1] == {"user_id": "alice", "password": "x"}
    assert model.fake.calls[-1] == {"user_id": "alice", "password": "x"}


def test_token_refused_and_settings_not_saved_warnings_equal_qt(world, model, qapp, monkeypatch):
    from chisurf.core.settings import settings_utils

    world.store_ok = False
    q_ok, q_shown, q_cfg, q_yaml = qt_login(world, BASE, "admin", "admin", "10.0.0.7", 9200,
                                            True, True, FakeClient(), qapp, monkeypatch)
    world.token_calls.clear()
    world.configure(BASE)
    model.user, model.password, model.autologin = "admin", "admin", True
    model.server, model.port = "10.0.0.7", 9200
    model.login()
    assert [n[1:] for n in model.notices] == [s[1:] for s in q_shown]
    assert model.notices[0][1] == "Autologin Not Saved"
    assert world.cs.cs_settings["mmfdb"]["autologin"] is False and q_cfg["autologin"] is False
    assert world.yaml["autologin"] is False == q_yaml["autologin"]
    assert model.accepted and not model.closed          # the box must be read first
    model.dismiss_notice()
    assert model.closed
    # settings file cannot be written
    world.store_ok = True
    monkeypatch.setattr(settings_utils, "set_mmfdb_login_settings", lambda d: False)
    world.configure(BASE)
    model.notices.clear()
    model.accepted = model.closed = False
    model.autologin = False
    model.login()
    assert model.notices == [("warning", "Settings Not Saved",
                              "Login succeeded, but ChiSurf could not store the MMFDB login settings.")]
    assert model.accepted


# ----------------------------------------------------------- the actions
def test_server_history_is_five_long_and_moves_to_the_front(world, model):
    world.configure({**BASE, "server_history": ["a", "b", "c", "d", "e"]})
    model.load_settings()
    model.server = "f"
    model.login()
    assert world.cs.cs_settings["mmfdb"]["server_history"] == ["f", "a", "b", "c", "d"]
    model.accepted = model.closed = False
    model.server = "c"
    model.login()
    assert world.cs.cs_settings["mmfdb"]["server_history"] == ["c", "f", "a", "b", "d"]


def test_nothing_is_remembered_when_both_options_are_off(world, model):
    model.save_login = model.autologin = False
    model.user = "bob"
    model.login()
    cfg = world.cs.cs_settings["mmfdb"]
    assert cfg["client"]["username"] == "alice" and "default_user_id" not in cfg
    assert cfg["save_login"] is False and cfg["autologin"] is False
    assert world.token_calls[0][0] == "delete"


def test_pickers_fill_the_fields_and_follow_typing(model):
    model.recent_server = "10.0.0.7"
    model.use_recent_server()
    assert model.server == "10.0.0.7"
    model.known_user = "admin"
    model.use_known_user()
    assert model.user == model.picked_user == "admin"
    model.user = "carol"
    model.edited_user()
    assert model.known_user == ""
    model.user = "user"
    model.edited_user()
    assert model.known_user == "user"
    assert model.recent_servers() == model.server_history


def test_cancel_closes_without_changing_anything(world, model):
    before = copy.deepcopy(world.cs.cs_settings["mmfdb"])
    model.password = "secret"
    model.cancel()
    assert model.closed and not model.accepted and model.password == ""
    assert world.cs.cs_settings["mmfdb"] == before and world.yaml is None
    assert model.fake.calls == [] and world.token_calls == []


def test_buttons_are_disabled_while_busy_or_blocked(model):
    assert model.enabled("login") and model.enabled("cancel")
    model.busy = True
    assert not model.enabled("login")
    model.busy = False
    model.notices.append(("warning", "t", "x"))
    assert not model.enabled("login")


def test_an_invalid_settings_block_does_not_stop_the_window(world):
    from chisurf.plugins.core.switch_user.model import SwitchUserModel

    world.configure({"client": {"mode": "carrier-pigeon"}})
    m = SwitchUserModel()
    assert "invalid" in m.message and m.mode == "embedded" and m.user == "admin"


def test_login_error_text_rule():
    from chisurf.plugins.core.switch_user.model import format_login_error as f

    assert f(None) == f("") == "Incorrect credentials"
    assert f({"reason": "no"}) == "no" and f({"x": 1}) == '{"x": 1}' and f(7) == "7"


def test_settings_round_trip_and_no_password(world, model):
    model.user, model.password, model.server, model.port = "admin", "admin", "10.0.0.7", 9200
    model.autologin = True
    model.login()
    from chisurf.plugins.core.switch_user.model import SwitchUserModel

    again = SwitchUserModel()
    assert (again.server, again.port, again.user, again.autologin) == ("10.0.0.7", 9200, "admin", True)
    assert again.server_history[0] == "10.0.0.7" and again.password == ""
    assert "password" not in json.dumps(world.yaml).lower().replace("passwordless", "")
    from chisurf.plugins.core.switch_user.app import SwitchUserApp

    a = SwitchUserApp(client=FakeClient())
    assert a.export_settings() == {} and a.restore_settings({"server": "x", "user": "y"}) is None


def test_the_real_settings_were_not_touched(world, model):
    real = real_settings_path()
    before = digest(real)
    model.user, model.password, model.autologin = "admin", "admin", True
    model.login()
    from chisurf.core.settings.path_utils import get_path

    assert Path(get_path("settings")).resolve() == world.folder.resolve()
    assert world.yaml is not None and (world.folder / "settings_chisurf.yaml").exists()
    assert digest(real) == before
    assert not str(world.folder).startswith(str(Path.home() / ".chisurf"))


def test_real_in_process_mmfdb_login_on_a_temp_database(world):
    """The default factory path with a real (temporary) MMFDB: admin/admin signs in, a wrong password does not."""
    from chisurf.plugins.core.switch_user.model import SwitchUserModel
    from chisurf.plugins.core.user_editor.test import seeded_db

    client = seeded_db.admin_client()
    m = SwitchUserModel(client_factory=lambda mode, s, p: client)
    m.user, m.password = "admin", "admin"
    m.login()
    assert m.accepted and world.yaml["client"]["username"] == "admin"
    m2 = SwitchUserModel(client_factory=lambda mode, s, p: client)
    m2.user, m2.password = "admin", "definitely-wrong"
    m2.login()
    assert not m2.accepted and m2.notices and m2.notices[0][0] in ("warning", "error")
    assert (world.folder / "mmfdb.db").exists()


# ------------------------------------------------------------- the app
def test_job_login_through_the_app(world):
    from chisurf.plugins.core.switch_user.app import SwitchUserApp

    client = FakeClient()
    app = SwitchUserApp(client=client)
    app.model.user, app.model.password = "admin", "admin"
    assert click(app, "Login")
    for _ in range(200):
        frames(app, n=1)
        if app.model.accepted:
            break
    assert app.model.accepted and app.model.closed and app.close_requested
    assert client.calls == [{"user_id": "admin", "password": "admin"}]


def test_a_refusal_opens_the_message_and_ok_closes_it(world):
    from chisurf.plugins.core.switch_user.app import SwitchUserApp

    app = SwitchUserApp(client=FakeClient({"ok": False, "error": "Incorrect credentials"}))
    app.model.password = "x"
    assert click(app, "Login")
    for _ in range(200):
        painter = frames(app, n=1)
        if app.model.notices:
            break
    painter = frames(app)
    assert "Login Failed" in painter.strings and "Incorrect credentials" in painter.strings
    assert not app.close_requested
    assert click(app, "OK")
    assert app.model.notices == [] and not app.close_requested


def test_cancel_button_requests_close(app):
    assert click(app, "Cancel")
    assert app.close_requested and app.model.closed


def test_declining_changes_nothing_in_the_settings(world, app):
    before = copy.deepcopy(world.cs.cs_settings["mmfdb"])
    click(app, "Cancel")
    assert world.cs.cs_settings["mmfdb"] == before and world.yaml is None


@pytest.mark.parametrize("size", SIZES)
def test_app_draws_empty_and_populated(size, world):
    from chisurf.plugins.core.switch_user.app import SwitchUserApp

    app = SwitchUserApp(client=FakeClient())
    painter = frames(app, size)
    for text in ("Login", "Cancel", "Server", "Port", "User", "Password", "Save selected user",
                 "Log in automatically when allowed", "Sign in to the MMFDB workspace",
                 "Recent servers", "Select user", "Help", "Guide"):
        assert text in painter.strings, text
    assert "lab-server.example.org" in painter.strings and "9100" in painter.strings
    app.model.password = "hunter2-secret"
    app.model.notices.append(("warning", "Login Failed", "Incorrect credentials"))
    painter = frames(app, size)
    assert "Login Failed" in painter.strings
    assert not any("hunter2" in s for s in painter.strings)


def test_remote_app_shows_the_url_label_and_no_port(world):
    from chisurf.plugins.core.switch_user.app import SwitchUserApp

    world.configure({"client": {"mode": "remote", "base_url": "http://127.0.0.1:8080", "username": "alice"}})
    painter = frames(SwitchUserApp(client=FakeClient()))
    assert "MMFDB URL" in painter.strings and "Port" not in painter.strings
    assert "Server" not in painter.strings


# ---------------------------------------- spec, tooltips, guide, no Qt
def test_every_spec_key_exists_on_the_model(model):
    spec = json.loads(SPEC_FILE.read_text())

    def walk(sections):
        for s in sections:
            if s.get("attr"):
                assert hasattr(model, s["attr"]), s["attr"]
            if s.get("source"):
                assert hasattr(model, s["source"]), s["source"]
            if s.get("options_source"):
                assert callable(getattr(model, s["options_source"])), s["options_source"]
            if s.get("call"):
                assert callable(getattr(model, s["call"])), s["call"]
            for b in s.get("buttons", []):
                assert callable(getattr(model, b["action"])), b["action"]
            walk(s.get("sections", []))

    walk(spec["sections"])


def test_every_control_has_a_tooltip(world):
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    inv = emtk_inventory(build_emtk_app("switch_user"))
    assert inv["controls_without_tooltip"] == []
    assert len(inv["interactive"]) >= 8
    spec = json.loads(SPEC_FILE.read_text())

    def walk(sections):
        for s in sections:
            if s.get("type") in ("value", "choice", "toggle", "table", "data_table", "custom",
                                 "button_row", "info", "panel"):
                assert s.get("description"), s.get("attr") or s.get("title") or s
            for b in s.get("buttons", []):
                assert b.get("description"), b
            walk(s.get("sections", []))

    walk(spec["sections"])


def test_guide_targets_are_real_controls_and_awaits_are_noticed(world):
    from chisurf.plugins.core.switch_user.app import SwitchUserApp

    app = SwitchUserApp(client=FakeClient())
    frames(app)
    guide = json.loads(GUIDE_FILE.read_text())
    targets = {s["target"]["name"] for s in guide["steps"]}
    assert targets <= set(app.item_rects) | set(app.form.rects), targets - set(app.form.rects)
    assert [s for s in guide["steps"] if s.get("await")]
    assert app.tour.steps == guide["steps"]
    assert (PLUGIN / "help.md").read_text().startswith("# Switch User")


def test_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("switch_user")
    assert result["ok"], result["output"]


def test_manifest_points_at_the_factory():
    manifest = json.loads((PLUGIN / "manifest.json").read_text())
    assert manifest["entrypoints"]["emtk"] == "chisurf.plugins.core.switch_user.app:make_app"
    from chisurf.plugins.core.switch_user.app import make_app

    assert make_app().model.mode in ("embedded", "remote")
