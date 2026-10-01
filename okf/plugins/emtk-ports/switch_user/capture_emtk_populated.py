"""Capture the emtk switch-user app in realistic states on TEMPORARY settings and MMFDB.

Usage: ``python capture_emtk_populated.py <out_dir> [prefix]`` from the repository root with
QT_QPA_PLATFORM=offscreen and PYTHONPATH holding the repository and emtk. Credential-store
calls are stubbed; the client is the in-process MMFDB over a temp SQLite file.
"""
import os
import sys
import tempfile
from pathlib import Path

out = Path(sys.argv[1])
prefix = sys.argv[2] if len(sys.argv) > 2 else "after"
tmp = Path(tempfile.mkdtemp(prefix="su_emtk_"))
for key, value in (("CHISURF_SETTINGS_DIR", tmp), ("MMFDB_SETTINGS_DIR", tmp),
                   ("MMFDB_DATABASE_PATH", tmp / "mmfdb.db")):
    os.environ[key] = str(value)

import yaml  # noqa: E402

(tmp / "settings_chisurf.yaml").write_text(yaml.safe_dump({"mmfdb": {
    "client": {"mode": "embedded", "username": "alice", "host": "127.0.0.1",
               "cmd_port": 8765, "pub_port": 8766},
    "server_history": ["127.0.0.1", "lab-server.example.org", "10.0.0.7"],
    "last_server": "lab-server.example.org", "last_port": 9100,
    "save_login": True, "autologin": False}}))

from test.gui.emtk_port_parity import emtk_screenshot  # noqa: E402

from chisurf.plugins.core.user_editor.test import seeded_db as db  # noqa: E402

client = db.admin_client()
db.seed(client)

from mmfdb.security import credentials as cred  # noqa: E402

cred.store_session_token = lambda *a: True
cred.delete_session_token = lambda *a: True

from chisurf.plugins.core.switch_user.app import SwitchUserApp  # noqa: E402


def shot(app, name, sizes=((1200, 800), (800, 600))):
    for w, h in sizes:
        emtk_screenshot(app, out / f"{prefix}_{name}_{w}x{h}.png", (w, h))
        print("wrote", f"{prefix}_{name}_{w}x{h}.png")


app = SwitchUserApp(client=client)
m = app.model
shot(app, "populated")
m.user, m.password = "admin", "wrong"
m.notices.append(("warning", "Login Failed", "Incorrect credentials"))
shot(app, "populated_login_failed")
m.dismiss_notice()
m.user, m.password, m.server, m.port = "admin", "admin", "10.0.0.7", 9200
m.autologin = True
shot(app, "populated_edited")
m.run_login()
shot(app, "populated_signed_in", ((1200, 800),))
print("closed", m.closed, "temp", tmp)
