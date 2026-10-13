"""Behaviour contracts of the native MMFDB Admin's eLabFTW panel (ported from the Qt ``ELabFTWView`` tests).

The app runs over a seeded temporary MMFDB; the eLabFTW calls of its client are replaced by
a recording fake (no network), and the panel is typed into and pressed through the emtk
Driver.
"""

from __future__ import annotations

import json

import pytest

from .native_support import (  # noqa: F401
    admin_folder,
    app,
    client,
    driver,
    open_panel,
    seeded_template,
)


class FakeElab:
    """Record every eLabFTW call the panel makes."""

    def __init__(self):
        self.connected = []
        self.disconnected = []
        self.imported = []
        self.exported = []

    def connect_elabftw(self, base_url, api_key, **kwargs):
        self.connected.append((base_url, api_key, kwargs))
        return {
            "connection_id": "opaque-handle",
            "endpoint": "https://lab.example/api/v2",
            "info": {"version": "5.2.0"},
        }

    def disconnect_elabftw(self, connection_id):
        self.disconnected.append(connection_id)

    def list_elabftw_experiments(self, connection_id, **kwargs):
        assert connection_id == "opaque-handle"
        return [
            {
                "id": 7,
                "title": "Lifetime series",
                "date": "2026-07-13",
                "status": "Complete",
                "modified_at": "2026-07-13 12:00:00",
                "tags": ["tcspc", "fret"],
            }
        ]

    def import_elabftw_experiments(self, connection_id, remote_ids, **kwargs):
        self.imported.append((connection_id, remote_ids, kwargs))
        return {"imported": [{"remote_id": i} for i in remote_ids], "updated": [], "skipped": []}

    def list_experiments(self):
        return [{"experiment_id": "local-1", "status": "complete"}]

    def export_elabftw_experiment(self, connection_id, experiment_id, **kwargs):
        self.exported.append((connection_id, experiment_id, kwargs))
        return {"remote_id": kwargs.get("remote_id") or 91, "mode": kwargs["mode"]}


@pytest.fixture
def fake(app, monkeypatch):  # noqa: F811
    fake = FakeElab()
    for name in (
        "connect_elabftw",
        "disconnect_elabftw",
        "list_elabftw_experiments",
        "import_elabftw_experiments",
        "list_experiments",
        "export_elabftw_experiment",
    ):
        monkeypatch.setattr(app.model.client, name, getattr(fake, name))
    return fake


def _connect(driver, key: str = "secret-key"):  # noqa: F811
    panel = open_panel(driver, "elabftw", "eLabFTW")
    driver.type_into_name("endpoint", "https://lab.example")
    driver.type_into_name("api_key", key)
    driver.click_name("connect_remote")
    driver.draw(2)
    return panel


def test_key_is_masked_never_persisted_and_cleared_after_connect(driver, app, fake):  # noqa: F811
    from chisurf.plugins.core.mmfdb_admin.gui.app import load_specs

    _shell, panels, _actions = load_specs()
    spec = json.dumps(panels["elabftw"])
    assert '"attr": "api_key"' in spec and '"kind": "password"' in spec
    panel = open_panel(driver, "elabftw", "eLabFTW")
    driver.type_into_name("endpoint", "https://lab.example")
    driver.type_into_name("api_key", "secret-key")
    assert panel.api_key == "secret-key" and not driver.drawn("secret-key")  # masked
    driver.click_name("connect_remote")
    driver.draw(2)
    assert panel.api_key == ""
    assert panel.connection_id == "opaque-handle"
    assert fake.connected[0][1] == "secret-key"
    assert "secret-key" not in panel.message
    assert [r["title"] for r in panel.remote] == ["Lifetime series"]
    assert driver.drawn("Lifetime series")
    assert "secret-key" not in json.dumps(app.export_settings(), default=str)


def test_busy_state_disables_remote_mutations(driver, app, fake):  # noqa: F811
    panel = _connect(driver)
    panel.busy = True
    for name in ("connect_remote", "refresh_remote", "import_checked", "export_selected"):
        assert not panel.enabled(name), name
    panel.busy = False
    assert panel.enabled("refresh_remote") and panel.enabled("import_checked")
    assert not panel.enabled("connect_remote")  # already connected


def test_selected_import_and_explicit_export_modes(driver, app, fake):  # noqa: F811
    panel = _connect(driver)
    panel.edited(panel.remote[0], "checked", True)
    panel.conflict = "update"
    driver.type_into_name("sample_id", "sample-1")
    driver.click_name("import_checked")
    assert fake.imported == [
        ("opaque-handle", [7], {"conflict": "update", "sample_id": "sample-1"})
    ]
    assert panel.message.startswith("Import complete: 1 created")
    panel.local_experiment = "local-1"
    panel.export_mode = "create"
    driver.click_name("export_selected")
    panel.export_mode = "update"
    panel.remote_id = 91
    driver.click_name("export_selected")
    assert fake.exported == [
        ("opaque-handle", "local-1", {"mode": "create", "remote_id": None}),
        ("opaque-handle", "local-1", {"mode": "update", "remote_id": 91}),
    ]


def test_disconnect_discards_handle_and_remote_rows(driver, app, fake):  # noqa: F811
    panel = _connect(driver)
    driver.click_name("disconnect_remote")
    assert fake.disconnected == ["opaque-handle"]
    assert panel.connection_id is None
    assert panel.remote == []


def test_error_path_is_non_modal_and_does_not_echo_key(driver, app, fake, monkeypatch):  # noqa: F811
    def refuse(base_url, api_key, **kwargs):
        raise RuntimeError("authentication rejected")

    monkeypatch.setattr(app.model.client, "connect_elabftw", refuse)
    panel = _connect(driver, "super-secret")
    assert panel.connection_id is None
    assert "authentication rejected" in panel.message
    assert "super-secret" not in panel.message
    assert panel.api_key == ""
    assert app.model.dialog is None  # non-modal: the reason is in the panel's status line
