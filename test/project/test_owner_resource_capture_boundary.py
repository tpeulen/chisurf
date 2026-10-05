"""Actual macro resource capture and resource-only document protection."""

from pathlib import Path
from types import SimpleNamespace

import pytest

import chisurf as cs
from chisurf.core.api._proxies import install_proxies
from chisurf.core.project.lifecycle import ProjectDocument
from chisurf.core.project.project import ResourceContext
from chisurf.core.project.storage import load_file, save_file
from chisurf.macros.core_fit import get_project_payload
from chisurf.server.dispatcher import ServiceDispatcher
from chisurf.server.services.projects import register_project_snapshot_services
from chisurf.server.session import SessionState
from test.project.test_public_api_project_transaction import PublicClient
from test.project.test_spec_science_resources import (
    authenticated_browser as authenticated_browser,
)
from test.project.test_spec_science_resources import (
    measured_export as measured_export,
)
from test.project.test_spec_science_resources import (
    sample_project_payload as sample_project_payload,
)
from test.project.test_spec_science_resources import (
    standalone_server as standalone_server,
)


@pytest.mark.parametrize("remote", [False, True])
def test_actual_macro_resave_retains_owned_bytes_without_original_path(
    monkeypatch, tmp_path, remote
):
    """Main Save's macro captures retained entries and aliases in both runtimes."""
    source = tmp_path / "original.pdb"
    content = b"owned test attachment\n"
    source.write_bytes(content)
    resources = ResourceContext({"attachments/owned.pdb": content}, {str(source): content})
    source.unlink()
    history = SimpleNamespace(list_events=lambda: [{"action_type": "capture"}])
    monkeypatch.setattr(cs, "fits", [])
    monkeypatch.setattr(cs, "imported_datasets", [])
    monkeypatch.setattr(cs, "__client__", None, raising=False)
    monkeypatch.setattr(cs, "cs", SimpleNamespace(fit_idx=4))
    monkeypatch.setattr(cs, "history", history, raising=False)
    monkeypatch.setattr(cs, "project_resources", resources, raising=False)
    if remote:
        state = SessionState()
        state.history = history
        state.project_resources = resources
        dispatcher = ServiceDispatcher(state)
        dispatcher._build_default_registry()
        register_project_snapshot_services(dispatcher, state)
        install_proxies(PublicClient(dispatcher))
    project = get_project_payload()
    assert project.resources.entries == resources.entries
    assert project.resources.sources == resources.sources
    assert project.extra["history_events"] == history.list_events()
    assert project.ui_state.get("current_fit_index") in (None, -1)
    destination = save_file(project, tmp_path / "owned.cs.pto")
    restored = load_file(destination)
    assert restored.resources.entries["attachments/owned.pdb"] == content
    assert restored.resources.sources == resources.sources
    assert not source.exists()


def test_resource_bytes_and_aliases_are_document_edits(tmp_path):
    """Unchanged science cannot hide edits to retained attachment bytes or aliases."""
    from chisurf.core.project import capture_session

    project = capture_session([], [])
    project.resources = ResourceContext({"attachments/owned.pdb": b"original"})
    document = ProjectDocument()
    document.record_file_save(project, tmp_path / "saved.cs.pto")
    project.resources = ResourceContext({"attachments/owned.pdb": b"changed"})
    assert document.is_modified(project)
    document.record_file_save(project, tmp_path / "saved.cs.pto")
    project.resources = ResourceContext(
        {"attachments/owned.pdb": b"changed"}, {"alias": b"changed"}
    )
    assert document.is_modified(project)


def test_default_api_replacement_and_main_macro_share_resources(monkeypatch):
    """The API's default owner and Main Save cannot diverge on resources/history."""
    from chisurf.core.api import ChiSurfAPI
    from chisurf.core.project import capture_session

    monkeypatch.setattr(cs, "cs", None)
    monkeypatch.setattr(cs, "fits", [])
    monkeypatch.setattr(cs, "imported_datasets", [])
    monkeypatch.setattr(cs, "__client__", None, raising=False)
    old = ResourceContext({"attachments/old": b"old"})
    monkeypatch.setattr(cs, "project_resources", old, raising=False)
    api = ChiSurfAPI(mode="local")
    assert api.capture_project().resources.entries == old.entries
    incoming = capture_session([], [])
    incoming.resources = ResourceContext({"attachments/incoming": b"incoming"})
    assert api.restore_project_payload(incoming)["ok"] is True
    assert get_project_payload().resources.entries == incoming.resources.entries
    assert api.capture_project().resources.entries == incoming.resources.entries


def test_macro_attachment_only_authenticated_database_and_proxy_resave(
    monkeypatch,
    tmp_path,
    measured_export,
    standalone_server,
):
    """Actual transport and macro saves retain measured aliases after copies vanish."""
    from chisurf.core.project.storage import load_database, save_database
    from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient
    from chisurf.plugins.core.project_browser.gui.client import ProjectBrowserClient

    measured = load_file(measured_export)
    source = tmp_path / "copied-148l.pdb"
    content = Path("test/data/atomic_coordinates/pdb_files/148l.pdb").read_bytes()
    source.write_bytes(content)
    resources = ResourceContext(
        {"attachments/148l.pdb": content},
        {**measured.resources.sources, str(source): content},
    )
    source.unlink()
    for alias in resources.sources:
        assert not Path(alias).exists()
    monkeypatch.setattr(cs, "cs", None)
    monkeypatch.setattr(cs, "fits", [])
    monkeypatch.setattr(cs, "imported_datasets", [])
    monkeypatch.setattr(cs, "__client__", None, raising=False)
    monkeypatch.setattr(cs, "project_resources", resources, raising=False)
    project = get_project_payload("resource-only measured Main Save")
    url, token, _database = standalone_server
    base = MMFDBClient(mode="remote", base_url=url, allow_insecure_http=True, inprocess=False)
    base.token = token
    client = ProjectBrowserClient(mmfdb_client=base)
    settings = {"client": {"mode": "remote", "base_url": url, "allow_insecure_http": True}}
    saved = save_database(project, mmfdb_settings=settings, client=client)
    loaded, _meta = load_database(saved["version_id"], mmfdb_settings=settings, client=client)
    assert loaded.resources.entries["attachments/148l.pdb"] == content
    assert loaded.resources.sources == resources.sources
    state = SessionState()
    state.project_resources = loaded.resources
    dispatcher = ServiceDispatcher(state)
    dispatcher._build_default_registry()
    register_project_snapshot_services(dispatcher, state)
    install_proxies(PublicClient(dispatcher))
    recaptured = get_project_payload("proxy resource-only resave")
    destination = save_file(recaptured, tmp_path / "proxy-resave.cs.pto")
    final = load_file(destination)
    assert final.resources.entries["attachments/148l.pdb"] == content
    assert final.resources.sources == resources.sources
    second = save_database(
        recaptured,
        project_id=saved["project_id"],
        parent_version_id=saved["version_id"],
        mmfdb_settings=settings,
        client=client,
    )
    final_database, _meta = load_database(
        second["version_id"], mmfdb_settings=settings, client=client
    )
    assert final_database.resources.entries["attachments/148l.pdb"] == content
    assert final_database.resources.sources == resources.sources
