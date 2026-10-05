"""Publish real authenticated PTO exports without risking the previous science."""

from __future__ import annotations

import base64
import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from chisurf.core.project import pto
from chisurf.plugins.core.project_browser.gui.model import ProjectBrowserModel
from chisurf.plugins.core.project_browser.test.test_project_browser_services import (
    _payload_with_fit,
    assert_scientific_roundtrip,
)
from chisurf.plugins.core.project_browser.test.test_project_browser_services import (
    authenticated_browser as authenticated_browser,
)
from chisurf.plugins.core.project_browser.test.test_project_browser_services import (
    project_db as project_db,
)
from chisurf.plugins.core.project_browser.test.test_project_browser_services import (
    sample_project_payload as sample_project_payload,
)
from chisurf.plugins.core.project_browser.test.test_project_browser_services import (
    standalone_server as standalone_server,
)


@pytest.fixture
def export_case(authenticated_browser, sample_project_payload, tmp_path, monkeypatch):
    """Save measured reader/model science through the actual HTTP deployment."""
    client = authenticated_browser["client"]
    payload = _payload_with_fit(sample_project_payload)
    saved = client.save_project("Atomic measured export", project_payload=payload)
    assert saved["ok"] is True
    destination = tmp_path / "existing.cs.pto"
    old = copy.deepcopy(payload)
    old["meta"]["name"] = "Previous measured document"
    pto.write_project(destination, old)
    previous = destination.read_bytes()
    received = []
    call = client._call

    def record(method, *args, **kwargs):
        result = call(method, *args, **kwargs)
        if method == "project_browser.export_csp":
            received.append(result)
        return result

    monkeypatch.setattr(client, "_call", record)
    model = ProjectBrowserModel(client=client, context=SimpleNamespace())
    model.last_directory = "previous-directory"
    return client, model, saved, destination, previous, received, payload


def _export(case, caller):
    """Drive each public browser export against the real transport."""
    client, model, saved, destination, *_ = case
    if caller == "model":
        return model.export(saved, destination)
    return client.export_csp(saved["version_id"], target_path=str(destination))


class _FailingWrite:
    """Inject failure into the actual destination or sibling file write."""

    def __init__(self, stream, fault, calls):
        self.stream, self.fault, self.calls = stream, fault, calls

    def __enter__(self):
        self.stream.__enter__()
        return self

    def __exit__(self, *args):
        return self.stream.__exit__(*args)

    def __getattr__(self, name):
        return getattr(self.stream, name)

    def write(self, data):
        """Write real bytes before disk-full, short-write or corruption failure."""
        self.calls.append(self.fault)
        if self.fault == "corruption":
            return self.stream.write(b"invalid!" + data[8:])
        self.stream.write(data[:16])
        if self.fault == "disk-full":
            raise OSError("disk full after 16 bytes")
        return 16


@pytest.mark.parametrize("caller", ["model", "client"])
@pytest.mark.parametrize("fault", ["disk-full", "short-write", "corruption", "fsync", "validator"])
def test_failed_actual_export_preserves_previous_native_document(
    export_case, caller, fault, monkeypatch
):
    """Review repro: partial output must never truncate the existing valid PTO."""
    _, model, _, destination, previous, received, _ = export_case
    before = set(destination.parent.iterdir())
    calls = []
    original_open = Path.open

    def failing_open(path, mode="r", *args, **kwargs):
        stream = original_open(path, mode, *args, **kwargs)
        if (
            mode == "wb"
            and path.parent == destination.parent
            and (path == destination or path.name.startswith(f".{destination.name}."))
        ):
            return _FailingWrite(stream, fault, calls)
        return stream

    def fail_fsync(fd):
        calls.append("fsync")
        raise OSError("injected stage fsync failure")

    def reject(payload):
        calls.append("validator")
        raise pto.ProjectPtoError("injected scientific rejection")

    if fault in {"disk-full", "short-write", "corruption"}:
        monkeypatch.setattr(Path, "open", failing_open)
    elif fault == "fsync":
        monkeypatch.setattr(pto.os, "fsync", fail_fsync)
    else:
        monkeypatch.setattr(pto, "_validate_project_payload", reject)
    failure = None
    try:
        _export(export_case, caller)
    except (OSError, pto.ProjectPtoError) as exc:
        failure = exc
    assert destination.read_bytes() == previous, "export damaged the previous native PTO"
    assert calls == [fault], "the actual publication failure path was not exercised"
    assert failure is not None, "publication accepted an incomplete/unvalidated stage"
    assert len(received) == 1, "proof must include actual authenticated HTTP export"
    assert set(destination.parent.iterdir()) == before, "orphan staging file"
    assert model.last_directory == "previous-directory"


@pytest.mark.parametrize("caller", ["model", "client"])
def test_successful_actual_export_overwrites_with_exact_complete_server_bytes(export_case, caller):
    """Keep typed science, real reader and MMFDB measurement attachments verbatim."""
    _, _, saved, destination, previous, received, payload = export_case
    before = set(destination.parent.iterdir())
    _export(export_case, caller)
    assert len(received) == 1
    result = received[0]
    assert result["version_id"] == saved["version_id"]
    assert result["project_id"] == saved["project_id"]
    actual = destination.read_bytes()
    assert actual != previous
    assert actual == base64.b64decode(result["archive_bytes"], validate=True)
    entries = pto.read_entries(destination)
    assert json.loads(entries["project.json"]) == payload
    assert_scientific_roundtrip(payload)
    dependencies = json.loads(entries["mmfdb_export.json"])["dependencies"]
    raw = next(a for a in dependencies["artifacts"] if a["artifact_kind"] == "raw_measurement")
    obj = next(o for o in dependencies["objects"] if o["object_uuid"] == raw["object_uuid"])
    assert base64.b64decode(obj["data_base64"], validate=True) == Path(obj["filename"]).read_bytes()
    assert set(destination.parent.iterdir()) == before


def test_ordinary_browser_client_never_forces_local_auth(authenticated_browser):
    """A configured loopback remote stays remote, and missing auth stays missing."""
    from mmfdb.repository import MFDatabase

    from chisurf.plugins.core.project_browser.gui.client import ProjectBrowserClient

    with MFDatabase(authenticated_browser["path"]) as db:
        before = db.conn.execute("SELECT count(*) FROM mmfdb_session").fetchone()[0]
    client = ProjectBrowserClient()
    assert client.mode == "remote"
    assert client.base_url == authenticated_browser["url"]
    assert client.token is None
    with pytest.raises(Exception, match="[Aa]uth|[Ss]ession|[Tt]oken"):
        client.list_projects()
    with MFDatabase(authenticated_browser["path"]) as db:
        assert db.conn.execute("SELECT count(*) FROM mmfdb_session").fetchone()[0] == before


def test_explicit_inprocess_injection_requires_actual_auth(project_db):
    """Authorized fault-test injection may use a dispatcher, never minted credentials."""
    from mmfdb.repository import MFDatabase

    from chisurf.plugins.core.project_browser.gui.client import ProjectBrowserClient

    with MFDatabase(project_db["path"]) as db:
        before = db.conn.execute("SELECT count(*) FROM mmfdb_session").fetchone()[0]
    client = ProjectBrowserClient(inprocess=True)
    assert client.token is None
    with pytest.raises(Exception, match="[Aa]uth|[Ss]ession|[Tt]oken"):
        client.list_projects()
    client.token = project_db["auth"]["token"]
    assert client.list_projects() == []
    with MFDatabase(project_db["path"]) as db:
        assert db.conn.execute("SELECT count(*) FROM mmfdb_session").fetchone()[0] == before


@pytest.mark.parametrize("caller", ["model", "client"])
@pytest.mark.parametrize("credential", ["missing", "rejected", "expired"])
def test_actual_export_auth_failure_keeps_previous_file(export_case, caller, credential):
    """Missing, rejected and genuinely expired remote sessions cannot publish a file."""
    from mmfdb.repository import MFDatabase
    from mmfdb.security.auth import _hash_token

    client, model, _, destination, previous, received, _ = export_case
    before = set(destination.parent.iterdir())
    if credential == "expired":
        # The actual endpoint rejects the actual password-login session after expiry.
        from mmfdb.store.database_resolver import resolve_database_path

        with MFDatabase(resolve_database_path()) as db:
            changed = db.conn.execute(
                "UPDATE mmfdb_session SET expires_at = ? WHERE token_hash = ?",
                ("2000-01-01T00:00:00", _hash_token(client.token)),
            )
            assert changed.rowcount == 1
            db.conn.commit()
    else:
        client.token = None if credential == "missing" else "rejected-session"
    with pytest.raises(Exception, match="[Aa]uth|[Ss]ession|[Tt]oken"):
        _export(export_case, caller)
    assert received == []
    assert destination.read_bytes() == previous
    assert set(destination.parent.iterdir()) == before
    assert model.last_directory == "previous-directory"


def test_real_export_destination_chooser_cancel_preserves_file(export_case):
    """Cancel the native chooser by its real button before any export or publication."""
    from emtk.testing import PixelPainter, save_png

    from chisurf.plugins.core.project_browser.gui.app import ProjectBrowserApp
    from chisurf.plugins.core.project_browser.test.driving import BrowserDriver

    client, model, saved, destination, previous, received, _ = export_case
    model.projects = client.list_projects()
    model.selected_id = saved["version_id"]
    model.last_directory = str(destination.parent)
    app = ProjectBrowserApp(model, autoload=False)
    try:
        app.loaded = True
        app.choose_file("export")
        app.dialog.filename = destination.name
        driver = BrowserDriver(app)
        driver.draw(3)
        pixels = PixelPainter(1200, 800)
        app.draw(pixels, 0, 0, 1200, 800)
        save_png(str(destination.parent / "actual-export-chooser.png"), 1200, 800, pixels.px)
        driver.click_text("Cancel")
        assert app.dialog is None
        assert app.jobs.future is None
        assert received == []
        assert destination.read_bytes() == previous
        assert not list(destination.parent.glob(f".{destination.name}.*.tmp"))
    finally:
        app.close()


def test_raw_publication_with_all_mmfdb_imports_blocked(export_case):
    """Complete real remote PTO bytes remain publishable without optional MMFDB."""
    client, _, saved, destination, _, received, _ = export_case
    result = client.export_csp(saved["version_id"], target_path=str(destination))
    assert received == [result]
    script = r"""
import importlib.abc
import sys
from pathlib import Path

class NoMMFDB(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "mmfdb" or fullname.startswith("mmfdb."):
            raise ModuleNotFoundError("MMFDB deliberately unavailable", name=fullname)
        return None

sys.meta_path.insert(0, NoMMFDB())
from chisurf.core.project.pto import publish_project_bytes, read_entries
source = Path(sys.argv[1])
target = source.with_name("optional-copy.cs.pto")
data = source.read_bytes()
assert publish_project_bytes(target, data) == target
assert target.read_bytes() == data
assert read_entries(target) == read_entries(source)
assert "mmfdb_export.json" in read_entries(target)
assert not any(n == "mmfdb" or n.startswith("mmfdb.") for n in sys.modules)
assert not list(source.parent.glob(f".{target.name}.*.tmp"))
print("Complete authenticated native PTO published with all MMFDB imports blocked")
"""
    settings = destination.parent / "optional-settings"
    env = dict(os.environ, CHISURF_SETTINGS_DIR=str(settings), MMFDB_SETTINGS_DIR=str(settings))
    completed = subprocess.run(
        [sys.executable, "-c", script, str(destination)],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    (destination.parent / "mmfdb-blocked-publication.log").write_text(
        completed.stdout + completed.stderr
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
