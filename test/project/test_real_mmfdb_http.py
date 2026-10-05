"""Acceptance tests for the standalone MMFDB project RPC surface."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import urllib.request
from wsgiref.simple_server import WSGIRequestHandler, make_server

import pytest
from mmfdb.repository import MFDatabase


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, *_args):
        return


def _rpc(url: str, method: str, params: dict, token: str | None = None) -> dict:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(f"{url}/rpc", body, headers, method="POST")
    with urllib.request.urlopen(request, timeout=10) as response:
        result = json.loads(response.read())
    assert "error" not in result, result
    return result["result"]


@pytest.fixture
def standalone_server(tmp_path, monkeypatch):
    from mmfdb.admin.backend.password_services import hash_password
    from mmfdb.repository import MFDatabase

    database = tmp_path / "mmfdb.sqlite"
    objects = tmp_path / "objects"
    monkeypatch.delenv("MMFDB_DATABASE_URL", raising=False)
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(database))
    monkeypatch.setenv("MMFDB_OBJECT_STORE_ROOT", str(objects))
    from mmfdb.config import reset_runtime_config

    reset_runtime_config()
    with MFDatabase(database) as db:
        db.add_user(
            "real-http-user", "Real HTTP User", password_hash=hash_password("test-http-password")
        )
        db.conn.commit()

    from mmfdb.webadmin import create_app

    app = create_app()
    server = make_server("127.0.0.1", 0, app, handler_class=_QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}"
        from mmfdb.admin.backend import auth_services

        with auth_services._get_db() as auth_db:
            paths = [row[2] for row in auth_db.conn.execute("PRAGMA database_list")]
            assert str(database) in paths
            assert (
                auth_db.conn.execute(
                    "SELECT count(*) FROM flr_sample_users WHERE user_id = ?",
                    ("real-http-user",),
                ).fetchone()[0]
                == 1
            )
        session = _rpc(
            url,
            "mmfdb.security.auth.login",
            {
                "user_id": "real-http-user",
                "password": "test-http-password",
                "provider": "local",
            },
        )
        assert session["ok"] and session["authenticated"], session
        yield url, session["token"], database
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_native_mmfdb_http_registers_and_persists_project_versions(standalone_server, tmp_path):
    url, token, database = standalone_server
    from chisurf.core.data import DataCurve
    from chisurf.core.fitting.fit import Fit
    from chisurf.core.models.description import tcspc_lifetime as LifetimeModel
    from chisurf.core.project import capture_session
    from chisurf.core.project.storage import load_database, save_database
    from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient
    from chisurf.plugins.core.project_browser.gui.client import ProjectBrowserClient

    base_client = MMFDBClient(
        mode="remote",
        base_url=url,
        allow_insecure_http=True,
        inprocess=False,
    )
    base_client.token = token
    browser_client = ProjectBrowserClient(mmfdb_client=base_client)
    storage_settings = {"client": {"mode": "remote", "base_url": url, "allow_insecure_http": True}}
    curve = DataCurve(x=[0.0, 1.0], y=[2.0, 3.0], name="curve")
    fit = Fit(data=curve, model_class=LifetimeModel)
    scientific = capture_session([curve], [fit], name="Storage HTTP Project")
    stored = save_database(scientific, mmfdb_settings=storage_settings, client=browser_client)
    restored_project, restored_meta = load_database(
        stored["version_id"],
        mmfdb_settings=storage_settings,
        client=browser_client,
    )
    assert restored_meta["version_id"] == stored["version_id"]
    assert restored_project.to_dict() == scientific.to_dict()

    first_payload = capture_session([curve], [fit], name="HTTP Project").to_dict()
    first = _rpc(
        url,
        "project_browser.save",
        {
            "project_name": "HTTP Project",
            "project_payload": first_payload,
        },
        token,
    )
    assert first["ok"] is True
    assert first["project_payload"] == first_payload
    assert first["version_number"] == 1
    with MFDatabase(database) as db:
        original = dict(
            db.conn.execute(
                "SELECT * FROM mmfdb_operation WHERE operation_id = ? AND operation_type = 'project'",
                (first["version_id"],),
            ).fetchone()
        )

    curve.y = [5.0, 8.0]
    second_payload = capture_session([curve], [fit], name="HTTP Project").to_dict()
    second = _rpc(
        url,
        "project_browser.save",
        {
            "project_name": "HTTP Project",
            "project_payload": second_payload,
            "project_id": first["project_id"],
            "parent_version_id": first["version_id"],
        },
        token,
    )
    assert second["ok"]
    assert second["version_number"] == 2
    assert second["parent_version_id"] == first["version_id"]

    # Omitted and older explicit parents must still allocate across the project.
    third = _rpc(
        url,
        "project_browser.save",
        {
            "project_payload": second_payload,
            "project_id": first["project_id"],
        },
        token,
    )
    fourth = _rpc(
        url,
        "project_browser.save",
        {
            "project_payload": first_payload,
            "project_id": first["project_id"],
            "parent_version_id": first["version_id"],
        },
        token,
    )
    assert third["ok"] and fourth["ok"]
    assert (third["version_number"], fourth["version_number"]) == (3, 4)
    assert third["parent_version_id"] == second["version_id"]
    assert fourth["parent_version_id"] == first["version_id"]
    for version, payload in (
        (first, first_payload),
        (second, second_payload),
        (third, second_payload),
        (fourth, first_payload),
    ):
        restored = _rpc(
            url, "project_browser.restore", {"version_id": version["version_id"]}, token
        )
        assert restored["ok"] and restored["project_payload"] == payload
        assert restored["version_id"] == version["version_id"]

    with MFDatabase(database) as db:
        from mmfdb.security.auth import create_session

        db.add_user("unauthorized-user", "Unauthorized User")
        unauthorized = create_session(db.conn, "unauthorized-user", client_name="pytest")
        db.conn.commit()
    for parent in (None, second["version_id"]):
        with pytest.raises(AssertionError):
            _rpc(
                url,
                "project_browser.save",
                {
                    "project_payload": second_payload,
                    "project_id": first["project_id"],
                    **({"parent_version_id": parent} if parent else {}),
                },
                unauthorized["token"],
            )
    with pytest.raises(AssertionError):
        _rpc(url, "project_browser.save", {"project_payload": second_payload}, "invalid-token")

    with MFDatabase(database) as db:
        rows = db.conn.execute(
            "SELECT operation_id, metadata_json FROM mmfdb_operation "
            "WHERE operation_type = 'project' AND json_extract(metadata_json, '$.project_id') = ?",
            (first["project_id"],),
        ).fetchall()
        assert (
            dict(
                db.conn.execute(
                    "SELECT * FROM mmfdb_operation WHERE operation_id = ?", (first["version_id"],)
                ).fetchone()
            )
            == original
        )
    assert len(rows) == 4
    assert sorted(json.loads(row[1])["version_number"] for row in rows) == [1, 2, 3, 4]


def test_native_mmfdb_project_service_does_not_import_chisurf(tmp_path):
    source = """
import sys
from mmfdb.webadmin import create_app
create_app()
assert 'chisurf' not in sys.modules
"""
    env = dict(os.environ)
    env["MMFDB_DATABASE_PATH"] = str(tmp_path / "fresh.sqlite")
    env["MMFDB_OBJECT_STORE_ROOT"] = str(tmp_path / "objects")
    result = subprocess.run([sys.executable, "-c", source], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
