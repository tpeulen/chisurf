"""The MMFDB login dialog of the native admin (ported from the Qt ``ConnectionAuthDialog`` test).

One masked single-line password, the user and the server in a collapsed Advanced block,
and the values round-trip -- drawn from ``connection_auth.view.json`` by emtk.
"""

from __future__ import annotations

import json
from pathlib import Path

from chisurf.plugins.core.mmfdb_admin.gui.native import dialogs as dlg

from .native_support import (  # noqa: F401
    admin_folder,
    app,
    client,
    driver,
    seeded_template,
)

SPEC = Path(dlg.__file__).resolve().parents[1] / "connection_auth.view.json"


def _walk(sections):
    for s in sections:
        yield s
        yield from _walk(s.get("sections", ()))


def test_login_dialog_password_masked_and_advanced_collapsible(driver, app):  # noqa: F811
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    fields = list(_walk(spec["sections"]))
    assert [s["attr"] for s in fields if s.get("kind") == "password"] == ["password"]
    advanced = [s for s in fields if s.get("collapsible")]
    assert len(advanced) == 1 and advanced[0]["collapsed"] is True
    assert {s.get("attr") for s in advanced[0]["sections"]} == {
        "user",
        "host",
        "cmd_port",
        "pub_port",
    }

    driver.click_name("logout")
    app.model.client.token = None
    app.model.ask_login("admin")
    dialog = app.model.dialog
    assert isinstance(dialog, dlg.ConnectionDialog)
    driver.type_into_name("dialog.password", "pw-not-drawn", commit=False)
    assert not driver.drawn("pw-not-drawn")  # masked
    assert driver.drawn("Advanced — user & connection")

    probe = dlg.ConnectionDialog("admin", "127.0.0.1", 8765, 8766, on_ok=lambda v: None)
    probe.password = "pw"
    probe.host = "10.0.0.5"
    assert probe.values() == {
        "user": "admin",
        "password": "pw",
        "host": "10.0.0.5",
        "cmd_port": 8765,
        "pub_port": 8766,
    }
