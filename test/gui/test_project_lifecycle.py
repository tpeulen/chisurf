"""Qt-level regression tests for the project transition guard."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from chisurf.core.project.lifecycle import SaveDecision, confirm_transition


def test_save_decision_is_explicit_and_save_must_succeed():
    """The GUI delegates the three-way policy to the GUI-independent guard."""
    calls = []

    assert not confirm_transition(
        has_content=True,
        prompt=lambda: SaveDecision.SAVE,
        save=lambda: calls.append("save") or False,
    )
    assert calls == ["save"]
    assert confirm_transition(
        has_content=True,
        prompt=lambda: SaveDecision.DISCARD,
        save=lambda: pytest.fail("discard must not save"),
    )
    assert not confirm_transition(
        has_content=True,
        prompt=lambda: SaveDecision.CANCEL,
        save=lambda: pytest.fail("cancel must not save"),
    )


def test_project_browser_uses_configured_transport(monkeypatch):
    """Lazy browser clients must not force the embedded MMFDB service."""
    from chisurf.core.project import storage as storage_module

    calls = []
    client = object()
    monkeypatch.setattr(storage_module, "_settings", lambda value: {"client": {"mode": "remote"}})
    monkeypatch.setattr(
        storage_module, "_real_client", lambda settings: calls.append(settings) or client
    )
    monkeypatch.setattr(storage_module, "select_backend", lambda: "mmfdb")
    from chisurf.plugins.core.project_browser.gui.model import ProjectBrowserModel

    model = ProjectBrowserModel(context=SimpleNamespace())
    assert model.client is model.client
    assert model.client is client
    assert calls == [{"client": {"mode": "remote"}}]


def test_project_browser_never_bootstraps_database_in_file_mode(monkeypatch):
    from chisurf.core.project import storage as storage_module
    from chisurf.plugins.core.project_browser.gui import client as client_module
    from chisurf.plugins.core.project_browser.gui.model import ProjectBrowserModel

    monkeypatch.setattr(storage_module, "select_backend", lambda: "file")
    monkeypatch.setattr(
        client_module,
        "ProjectBrowserClient",
        lambda **kwargs: pytest.fail("file policy must not construct an embedded database"),
    )

    with pytest.raises(storage_module.ProjectStorageError, match="configured"):
        ProjectBrowserModel(context=SimpleNamespace()).client


def test_browser_restore_guard_runs_before_background_restore():
    """A cancelled replacement leaves the live browser job untouched."""
    from chisurf.plugins.core.project_browser.gui.app import ProjectBrowserApp
    from chisurf.plugins.core.project_browser.gui.model import ProjectBrowserModel

    context = SimpleNamespace(_guard_project_transition=lambda: False)
    model = ProjectBrowserModel(client=object(), context=context)
    model.projects = [
        {
            "project_id": "p1",
            "latest_version_id": "v1",
            "versions": [{"project_id": "p1", "version_id": "v1"}],
        }
    ]
    model.selected_id = "p1"
    app = ProjectBrowserApp(model, autoload=False)
    try:
        assert app.open_selected() is False
        assert app.jobs.future is None
        assert "cancelled" in model.status
    finally:
        app.close()


def test_browser_restore_updates_document_baseline():
    """A successful database restore makes the exact version the clean baseline."""
    from chisurf.core.project import Project
    from chisurf.core.project.lifecycle import ProjectDocument
    from chisurf.plugins.core.project_browser.gui.model import ProjectBrowserModel

    project = Project(name="remote", datasets={"d": {"name": "curve"}})
    context = SimpleNamespace(_project_document=ProjectDocument())
    model = ProjectBrowserModel(
        client=object(),
        context=context,
        payload_loader=lambda payload: None,
        window_restorer=lambda payload: None,
    )
    result = {
        "ok": True,
        "project_id": "p1",
        "version_id": "v1",
        "project_name": "remote",
        "project_payload": project.to_dict(),
    }
    model.update_current(result, version_id="v1")
    assert context._project_document.project_id == "p1"
    assert context._project_document.version_id == "v1"
    assert not context._project_document.is_modified(project)


def test_project_browser_requires_explicit_success():
    from chisurf.plugins.core.project_browser.gui.model import ProjectBrowserModel

    with pytest.raises(RuntimeError, match="failed"):
        ProjectBrowserModel.checked({"project_id": "p1", "version_id": "v1"})


def test_project_browser_stages_identity_before_payload_restore():
    from chisurf.core.project import Project
    from chisurf.core.project.lifecycle import ProjectDocument
    from chisurf.plugins.core.project_browser.gui.model import ProjectBrowserModel

    document = ProjectDocument(project_id="old", version_id="old-v", backend="mmfdb")
    document.stage_database_save = lambda *args: (_ for _ in ()).throw(
        ValueError("identity rejected")
    )
    restored = []
    model = ProjectBrowserModel(
        client=object(),
        context=SimpleNamespace(_project_document=document),
        payload_loader=lambda payload: restored.append(payload),
        window_restorer=lambda payload: None,
    )
    result = {
        "ok": True,
        "project_id": "p1",
        "version_id": "v1",
        "project_payload": Project(name="remote").to_dict(),
    }

    with pytest.raises(ValueError, match="identity rejected"):
        model.apply_restore(result, "v1")

    assert restored == []
    assert document.project_id == "old"


def test_restore_fit_windows_passes_saved_ui_state(monkeypatch):
    from chisurf.plugins.core.project_browser.gui import model as model_module

    calls = []
    monkeypatch.setattr(
        "chisurf.macros.core_fit.restore_gui_from_fits",
        lambda fit_uids, ui_state=None: calls.append((fit_uids, ui_state)),
    )
    payload = {
        "fits": [{"uid": "fit-1"}],
        "ui": {"current_fit_index": 0},
    }

    model_module.restore_fit_windows(payload)

    assert calls == [(["fit-1"], {"current_fit_index": 0})]


def test_project_browser_real_save_uses_verified_storage(monkeypatch):
    from chisurf.core.project import Project
    from chisurf.plugins.core.project_browser.gui.model import ProjectBrowserModel

    calls = []
    monkeypatch.setattr("chisurf.core.project.storage.select_backend", lambda: "mmfdb")
    monkeypatch.setattr(
        "chisurf.core.project.storage.save_database",
        lambda project, **kwargs: (
            calls.append((project, kwargs)) or {"ok": True, "project_id": "p1", "version_id": "v2"}
        ),
    )
    context = SimpleNamespace(_current_project_id="p1", _current_project_version_id="v1")
    model = ProjectBrowserModel(client=object(), context=context)

    result = model.save_remote("remote", "private", "note", Project(name="remote").to_dict())

    assert result["ok"] is True
    assert calls[0][1]["parent_version_id"] == "v1"


def test_project_browser_file_save_uses_common_save_ui(monkeypatch, tmp_path):
    from chisurf.core.project import Project
    from chisurf.plugins.core.project_browser.gui.model import ProjectBrowserModel

    target = tmp_path / "portable.cs.pto"
    saved = []
    context = SimpleNamespace(
        _save_project_snapshot=lambda: saved.append(True) or True,
        _get_project_document=lambda: SimpleNamespace(path=target),
    )
    monkeypatch.setattr("chisurf.core.project.storage.select_backend", lambda: "file")
    model = ProjectBrowserModel(client=object(), context=context)

    result = model.save_remote("portable", "private", "", Project(name="portable").to_dict())

    assert saved == [True]
    assert result["ok"] is True
    assert result["backend"] == "file"
    assert result["file_path"] == str(target)
