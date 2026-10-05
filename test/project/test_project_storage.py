"""Tests for optional project storage policy and transport boundaries."""

from __future__ import annotations

import builtins
import json

import pytest

from chisurf.core.project.archive import ProjectArchive
from chisurf.core.project.project import Project
from chisurf.core.project.pto import read_entries, read_project
from chisurf.core.project.storage import (
    ProjectStorageError,
    load_database,
    load_file,
    save_database,
    save_file,
    select_backend,
)


def _project() -> Project:
    """Use actual captured scientific state for every storage integration."""
    from chisurf.core.data import DataCurve
    from chisurf.core.fitting.fit import Fit
    from chisurf.core.models.description import tcspc_lifetime
    from chisurf.core.project import capture_session

    curve = DataCurve(x=[0.0, 1.0, 2.0], y=[8.0, 4.0, 2.0], unique_identifier="d1")
    fit = Fit(data=curve, model_class=tcspc_lifetime)
    project = capture_session([curve], [fit], name="roundtrip")
    project.metadata["embedded"] = {"resource": "bytes"}
    return project


def test_bootstrap_embedded_selects_file_without_importing_mmfdb(monkeypatch, tmp_path):
    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "mmfdb" or name.startswith("mmfdb."):
            raise AssertionError("file policy must not import MMFDB")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    assert select_backend({"client": {"mode": "embedded"}}) == "file"
    project = _project()
    target = save_file(project, tmp_path / "portable")
    assert load_file(target).to_dict() == project.to_dict()


def test_file_backend_selection_does_not_import_database_or_its_gui(monkeypatch):
    import importlib

    calls = []
    original = importlib.import_module

    def tracked(name, *args, **kwargs):
        calls.append(name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", tracked)
    assert select_backend({"client": {"mode": "embedded"}}) == "file"
    assert calls == []


def test_remote_and_configured_file_deployment_select_mmfdb(tmp_path):
    assert (
        select_backend(
            {
                "client": {
                    "mode": "remote",
                    "base_url": "http://localhost",
                    "allow_insecure_http": True,
                }
            }
        )
        == "mmfdb"
    )
    config = tmp_path / "mmfdb.yaml"
    config.write_text(
        "version: 1\nclient:\n  mode: remote\n  base_url: http://localhost\n  allow_insecure_http: true\n",
        encoding="utf-8",
    )
    assert select_backend({"config_file": str(config)}) == "mmfdb"
    assert (
        select_backend({"client": {"mode": "embedded", "database_url": "postgresql://db"}})
        == "file"
    )


def test_file_roundtrip_and_canonical_extension(tmp_path):
    project = _project()
    target = save_file(project, tmp_path / "saved")
    assert target.name == "saved.cs.pto"
    assert load_file(target).to_dict() == project.to_dict()


def test_file_failure_preserves_existing_file(monkeypatch, tmp_path):
    target = save_file(_project(), tmp_path / "saved")
    old = target.read_bytes()

    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("chisurf.core.project.storage.write_project", fail)
    with pytest.raises(ProjectStorageError, match="disk full"):
        save_file(_project(), target)
    assert target.read_bytes() == old


def test_invalid_project_never_reaches_writer_or_replaces_existing_file(monkeypatch, tmp_path):
    target = save_file(_project(), tmp_path / "saved")
    old = target.read_bytes()

    def forbidden(*args, **kwargs):
        raise AssertionError("invalid payload reached the PTO writer")

    monkeypatch.setattr("chisurf.core.project.storage.write_project", forbidden)
    with pytest.raises(ProjectStorageError, match="Unsupported project format version"):
        save_file(Project(name="invalid", project_format_version=4), target)

    assert target.read_bytes() == old
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_malformed_session_graph_never_reaches_writer(monkeypatch, tmp_path):
    target = save_file(_project(), tmp_path / "saved")
    old = target.read_bytes()
    malformed = Project(
        name="invalid-session",
        metadata={"session_codec": "detached-v2"},
        fits=[{"uid": "fit-without-members"}],
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("malformed session reached the PTO writer")

    monkeypatch.setattr("chisurf.core.project.storage.write_project", forbidden)
    with pytest.raises(ProjectStorageError, match="has no members"):
        save_file(malformed, target)

    assert target.read_bytes() == old
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_database_rejects_invalid_science_before_any_rpc():
    calls = []

    class Client:
        def save_project(self, **params):
            calls.append("save")
            raise AssertionError("invalid snapshot reached the database")

    project = Project(
        name="invalid",
        metadata={"session_codec": "detached-v2"},
        fits=[{"uid": "missing-members"}],
    )
    with pytest.raises(ProjectStorageError):
        save_database(
            project,
            client=Client(),
            mmfdb_settings={
                "client": {
                    "mode": "remote",
                    "base_url": "http://127.0.0.1:9876",
                    "allow_insecure_http": True,
                }
            },
        )
    assert calls == []


def test_project_and_archive_writers_share_one_canonical_pto_layout(tmp_path):
    tttrlib = pytest.importorskip("tttrlib")
    project = _project()
    direct = save_file(project, tmp_path / "direct")
    archive = ProjectArchive()
    archive.write_text("project.json", json.dumps(project.to_dict()))
    archive.write_bytes("history.jsonl", b"event\n")
    assembled = archive.save(tmp_path / "assembled.cs.pto")

    def kinds(path):
        reader = tttrlib.PtoFile()
        assert reader.open(str(path)), reader.error()
        try:
            return [(obj.kind, obj.name) for obj in reader.objects()]
        finally:
            reader.close()

    direct_kinds = kinds(direct)
    assembled_kinds = kinds(assembled)
    assert direct_kinds.count(("chisurf.project", "project")) == 1
    assert assembled_kinds.count(("chisurf.project", "project")) == 1
    assert ("chisurf.project-entry", "project.json") not in assembled_kinds
    assert read_project(direct)[0] == json.loads(read_entries(assembled)["project.json"])


def test_archive_writer_readback_failure_keeps_previous_file(monkeypatch, tmp_path):
    target = save_file(_project(), tmp_path / "saved")
    old = target.read_bytes()
    original = __import__("chisurf.core.project.pto", fromlist=["read_entries"]).read_entries

    def fail(path):
        if str(path).endswith(".tmp"):
            raise RuntimeError("candidate readback failed")
        return original(path)

    monkeypatch.setattr("chisurf.core.project.pto.read_entries", fail)
    archive = ProjectArchive()
    archive.write_text("project.json", json.dumps(_project().to_dict()))
    with pytest.raises(RuntimeError, match="candidate readback failed"):
        archive.save(target)
    assert target.read_bytes() == old


@pytest.mark.parametrize(
    ("section", "value"),
    [
        ("datasets", []),
        ("experiments", []),
        ("fits", {}),
        ("ui", []),
        ("extra", []),
        ("dependency_edges", {}),
        ("parameters", []),
    ],
)
def test_project_from_dict_rejects_malformed_falsy_sections(section, value):
    data = Project(name="valid").to_dict()
    data[section] = value
    with pytest.raises(ValueError, match=section):
        Project.from_dict(data)


class _FakeClient:
    def __init__(self, payload, returned=None):
        self.payload = payload
        self.returned = returned
        self.saved = None

    def save_project(self, **kwargs):
        self.saved = kwargs
        return {
            "ok": True,
            "project_id": "p1",
            "version_id": "v1",
            "version_number": 1,
            "project_name": kwargs["project_name"],
        }

    def restore_project(self, version_id):
        assert version_id == "v1"
        return {
            "ok": True,
            "version_id": version_id,
            "version_number": 1,
            "project_id": "p1",
            "project_payload": self.returned or self.payload,
        }


def test_database_save_verifies_exact_payload_and_returns_metadata():
    project = _project()
    result = save_database(
        project,
        mmfdb_settings={"client": {"mode": "remote"}},
        client=_FakeClient(project.to_dict()),
    )
    assert result == {
        "ok": True,
        "project_id": "p1",
        "version_id": "v1",
        "version_number": 1,
        "project_name": "roundtrip",
        "visibility": "private",
    }
    from chisurf.core.project.lifecycle import ProjectDocument

    document = ProjectDocument()
    document.record_database_save(project, result)
    assert document.version_id == "v1"


def test_database_save_rejects_readback_mismatch():
    project = _project()
    client = _FakeClient(project.to_dict(), {"project_format_version": 5, "meta": {}})
    with pytest.raises(ProjectStorageError, match="readback mismatch"):
        save_database(project, mmfdb_settings={"client": {"mode": "remote"}}, client=client)


def test_database_load_requires_exact_version_and_does_not_use_latest():
    project = _project()
    loaded, metadata = load_database(
        "v1",
        mmfdb_settings={"client": {"mode": "remote"}},
        client=_FakeClient(project.to_dict()),
    )
    assert loaded.to_dict() == project.to_dict()
    assert metadata["version_id"] == "v1"


def test_database_roundtrip_uses_real_project_browser_backend_in_isolated_db(monkeypatch, tmp_path):
    from mmfdb.repository import MFDatabase
    from mmfdb.security.auth import create_session

    from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient
    from chisurf.plugins.core.project_browser.gui.client import ProjectBrowserClient

    db_path = tmp_path / "isolated-mmfdb.db"
    db = MFDatabase(db_path)
    db.ensure_user("storage-user")
    token = create_session(db.conn, "storage-user")["token"]
    db.conn.commit()
    monkeypatch.setattr(
        "chisurf.plugins.core.project_browser.backend.services.resolve_database_path",
        lambda: db_path,
    )
    monkeypatch.delenv("MMFDB_DATABASE_URL", raising=False)
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(db_path))
    from mmfdb.config import reset_runtime_config

    reset_runtime_config()
    base = MMFDBClient(inprocess=True)
    base.token = token
    client = ProjectBrowserClient(mmfdb_client=base)
    settings = {
        "client": {
            "mode": "remote",
            "base_url": "http://127.0.0.1:8080",
            "allow_insecure_http": True,
        }
    }
    project = _project()
    first = save_database(project, mmfdb_settings=settings, client=client)
    second = save_database(
        project,
        project_id=first["project_id"],
        parent_version_id=first["version_id"],
        mmfdb_settings=settings,
        client=client,
    )
    loaded, metadata = load_database(second["version_id"], mmfdb_settings=settings, client=client)
    assert loaded.to_dict() == project.to_dict()
    assert metadata["project_id"] == first["project_id"]
    assert metadata["version_id"] == second["version_id"]
    db.close()


def test_configured_remote_without_exact_runtime_token_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "mmfdb.security.credentials._RUNTIME_SESSION_TOKENS",
        {"127.0.0.1:8080:other-user": "not-for-this-user"},
    )
    settings = {
        "client": {
            "mode": "remote",
            "base_url": "http://127.0.0.1:8080/project",
            "allow_insecure_http": True,
            "username": "storage-user",
        }
    }
    with pytest.raises(ProjectStorageError, match="authenticated runtime token"):
        save_database(_project(), mmfdb_settings=settings, client=None)
