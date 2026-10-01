"""Capture the legacy Qt login dialog (switch_user) against a TEMPORARY MMFDB and settings.

Usage: ``python capture_qt_populated.py <out_dir>`` from the repository root with
QT_QPA_PLATFORM=offscreen and PYTHONPATH holding the repository and emtk. The real
``LoginDialog`` is modal (``exec``), which is why ``emtk_port_parity before`` never returns;
here it is constructed and shown non-modally. Settings, database and the credential store
are temporary / stubbed: nothing reaches ``~/.chisurf`` or the OS keyring.
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

from test.gui import migration_parity as mp  # noqa: E402  (first: later imports shadow `test`)
from test.gui.emtk_port_parity import normalize  # noqa: E402

out = Path(sys.argv[1])
tmp = Path(tempfile.mkdtemp(prefix="su_qt_"))
for key, value in (("CHISURF_SETTINGS_DIR", tmp), ("MMFDB_SETTINGS_DIR", tmp),
                   ("MMFDB_DATABASE_PATH", tmp / "mmfdb.db")):
    os.environ[key] = str(value)

# A recognisable "current user" and a server history, written before the settings load.
import yaml  # noqa: E402

(tmp / "settings_chisurf.yaml").write_text(yaml.safe_dump({"mmfdb": {
    "client": {"mode": "embedded", "username": "alice", "host": "127.0.0.1",
               "cmd_port": 8765, "pub_port": 8766},
    "server_history": ["127.0.0.1", "lab-server.example.org", "10.0.0.7"],
    "last_server": "lab-server.example.org", "last_port": 9100,
    "save_login": True, "autologin": False}}))

from chisurf.plugins.core.user_editor.test import seeded_db as db  # noqa: E402

client = db.admin_client()
db.seed(client)

stored = []
from mmfdb.security import credentials as cred  # noqa: E402

cred.store_session_token = lambda *a: stored.append(("store",) + a[:3]) or True
cred.delete_session_token = lambda *a: stored.append(("delete",) + a[:3]) or True

from qtpy import QtWidgets  # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf import gui as g  # noqa: E402

warnings = []
for name in ("warning", "error", "information"):
    setattr(g.dialogs, name, lambda parent, title, text, _n=name: warnings.append((_n, title, text)))

dlg = g.LoginDialog()
dlg.show()


def pump(n=20, wait=0.0):
    end = time.monotonic() + wait
    for _ in range(n):
        app.processEvents()
    while time.monotonic() < end:
        app.processEvents()


def grab(name):
    pump(20, 0.1)
    dlg.grab().save(str(out / name))
    print("wrote", name)


pump()
grab("before.png")
grab("before_populated.png")
inventory = mp.control_inventory(dlg)
inventory["entrypoint"] = "chisurf.gui:LoginDialog (non-modal, temp settings)"
inventory["size"] = [dlg.width(), dlg.height()]
inventory["controls"] = sorted({normalize(c) for c in inventory["controls"]} - {""})
(out / "before.json").write_text(json.dumps(inventory, indent=2, ensure_ascii=False))

facts = {
    "title": dlg.windowTitle(), "modal": dlg.isModal(), "size": [dlg.width(), dlg.height()],
    "server_items": [dlg.server_combo.itemText(i) for i in range(dlg.server_combo.count())],
    "server_current": dlg.server_combo.currentText(), "server_editable": dlg.server_combo.isEditable(),
    "port": dlg.port_spin.value(), "port_range": [dlg.port_spin.minimum(), dlg.port_spin.maximum()],
    "user_items": [dlg.user_combo.itemText(i) for i in range(dlg.user_combo.count())],
    "user_current": dlg.user_combo.currentText(), "user_editable": dlg.user_combo.isEditable(),
    "password_echo_mode": int(dlg.password_edit.echoMode()),
    "save_login": dlg.save_login_check.isChecked(), "autologin": dlg.auto_login_check.isChecked(),
    "save_text": dlg.save_login_check.text(), "auto_text": dlg.auto_login_check.text(),
    "buttons": [dlg.btn_login.text(), dlg.btn_cancel.text()],
}

# Errors: no server is listening (the real client is a ZMQ one on localhost).
dlg.client = type("Down", (), {"login": lambda self, **k: (_ for _ in ()).throw(
    RuntimeError("Connection refused"))})()
dlg.password_edit.setText("x")
dlg.handle_login()
facts["unreachable"] = list(warnings[-1])
warnings.clear()
dlg.client = type("Bad", (), {"login": lambda self, **k: {"ok": False, "error": "Incorrect credentials"}})()
dlg.handle_login()
facts["rejected_not_ok"] = list(warnings[-1]) if warnings else None
warnings.clear()
dlg.client = type("Bad2", (), {"login": lambda self, **k: {"authenticated": False, "error": {"message": "Account locked"}}})()
dlg.handle_login()
facts["rejected_dict_error"] = list(warnings[-1]) if warnings else None
warnings.clear()
dlg.user_combo.setCurrentText("")
calls = []
dlg.client = type("Rec", (), {"login": lambda self, **k: calls.append(k) or {"ok": False}})()
dlg.handle_login()
facts["empty_user_call"] = calls[-1]
facts["empty_user_warning"] = list(warnings[-1]) if warnings else None
warnings.clear()
grab("before_populated_error.png")

# Success: sign in as the desktop administrator through the real in-process MMFDB.
dlg.user_combo.setCurrentText("  admin ")
dlg.password_edit.setText("admin")
dlg.server_combo.setCurrentText("10.0.0.7")
dlg.port_spin.setValue(9200)
dlg.save_login_check.setChecked(True)
dlg.auto_login_check.setChecked(True)
grab("before_populated_edited.png")
dlg.client = client
client.login = (lambda orig: lambda **k: (calls.append(k), orig(**k))[1])(client.login)
done = []
dlg.accepted.connect(lambda: done.append(True))
dlg.handle_login()
facts["success_accepted"] = bool(done)
facts["success_call"] = {k: v for k, v in calls[-1].items()}
facts["success_warnings"] = [list(w) for w in warnings]
facts["token_store_calls"] = stored[:]
saved = yaml.safe_load((tmp / "settings_chisurf.yaml").read_text())["mmfdb"]
facts["yaml_after_login"] = saved
from mmfdb.security.credentials import session_token_registry  # noqa: E402
facts["runtime_token_keys"] = sorted(session_token_registry())

# Warnings after a successful login: the credential store refuses, then the settings file cannot be written.
import chisurf.core.settings as cs_settings  # noqa: E402
import chisurf.core.settings.settings_utils as su  # noqa: E402

cred.store_session_token = lambda *a: False
warnings.clear()
dlg.auto_login_check.setChecked(True)
done.clear()
dlg.handle_login()
facts["token_refused"] = {"warnings": [list(w) for w in warnings], "accepted": bool(done),
                          "autologin_after": cs_settings.cs_settings["mmfdb"]["autologin"]}
orig_set = su.set_mmfdb_login_settings
su.set_mmfdb_login_settings = lambda d: False
warnings.clear()
done.clear()
dlg.auto_login_check.setChecked(False)
dlg.handle_login()
facts["settings_not_saved"] = {"warnings": [list(w) for w in warnings], "accepted": bool(done)}
su.set_mmfdb_login_settings = orig_set

# Remote mode: the server row is a URL and the port is hidden.
cs_settings.cs_settings["mmfdb"]["client"] = {"mode": "remote", "base_url": "http://127.0.0.1:8080",
                                              "username": "alice"}
cs_settings.cs_settings["mmfdb"]["server_history"] = []
cs_settings.cs_settings["mmfdb"].pop("last_server", None)
dlg2 = g.LoginDialog()
dlg2.show()
pump(20, 0.2)
dlg2.grab().save(str(out / "before_populated_remote.png"))
facts["remote"] = {"server_label_rows": [w.text() for w in dlg2.findChildren(QtWidgets.QLabel)],
                   "port_visible": dlg2.port_spin.isVisible(),
                   "server_items": [dlg2.server_combo.itemText(i) for i in range(dlg2.server_combo.count())],
                   "user_items": [dlg2.user_combo.itemText(i) for i in range(dlg2.user_combo.count())]}

(out / "before_facts.json").write_text(json.dumps(facts, indent=2, ensure_ascii=False, default=str))
print(json.dumps(facts, indent=2, default=str))
print("temp folder:", tmp)
