"""Headless tests of the project browser window, driven on the native emtk app.

Ported from the retired Qt ``ProjectBrowserTool`` (same cases, same fake client and
deployment): the tree a fake service fills, one click per toolbar button, the in-process
services, delete with confirmation, import with collision remap and restore.
"""

from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from .test_emtk_project_browser_parity import _app, _project, _settle


def _sample_payload(tmp_path):
    data_path = tmp_path / "sample_curve.csv"
    data_path.write_text("time,intensity\n0,10\n1,12\n2,11\n", encoding="utf-8")
    return {
        "project_format_version": 5,
        "meta": {"name": "Sample Project", "description": "headless GUI test"},
        "datasets": {
            "ds_sample": {
                "uid": "ds_sample",
                "name": "Sample Curve",
                "filename": str(data_path),
                "experiment_name": "TCSPC",
                "x": [0.0, 1.0, 2.0],
                "y": [10.0, 12.0, 11.0],
                "data_reader": {
                    "module": "chisurf.test",
                    "class": "SampleReader",
                    "state": {"source": "pytest-gui"},
                },
            },
        },
        "fits": [],
        "experiments": {},
        "ui": {},
        "extra": {},
    }


class FakeProjectBrowserClient:
    def __init__(self):
        self.calls: list[dict[str, object]] = []

    def list_projects(self, show_public: bool = True, search: str | None = None):
        self.calls.append({"show_public": show_public, "search": search})
        return [
            {
                "project_id": "proj_sample",
                "project_name": "Sample Project",
                "owner_user_id": "admin_user",
                "visibility": "private",
                "version_count": 2,
                "latest_version_number": 2,
                "latest_version_id": "ver_2",
                "created_at": "2026-07-05T10:00:00",
                "updated_at": "2026-07-05T11:00:00",
                "versions": [
                    {
                        "version_id": "ver_2",
                        "project_id": "proj_sample",
                        "project_name": "Sample Project",
                        "version_number": 2,
                        "owner_user_id": "admin_user",
                        "status": "succeeded",
                        "dataset_count": 1,
                        "fit_count": 0,
                        "created_at": "2026-07-05T11:00:00",
                        "notes": "sample data",
                    },
                    {
                        "version_id": "ver_1",
                        "project_id": "proj_sample",
                        "project_name": "Sample Project",
                        "version_number": 1,
                        "owner_user_id": "admin_user",
                        "status": "succeeded",
                        "dataset_count": 1,
                        "fit_count": 0,
                        "created_at": "2026-07-05T10:00:00",
                        "notes": "first sample",
                    },
                ],
            },
        ]


def test_project_browser_renders_sample_project_tree_headless():
    fake_client = FakeProjectBrowserClient()
    app = _app(client=fake_client)
    try:
        _settle(app)
        model = app.model
        assert len(model.projects) == 1
        rows = app.panel.tree_rows()
        assert rows[0]["project_name"].startswith("Sample Project")
        project = model.projects[0]
        assert project["version_count"] == 2 and len(project["versions"]) == 2
        assert project["versions"][0]["version_id"] == "ver_2"
        assert project["versions"][0]["dataset_count"] == 1

        model.selected_id = project["project_id"]
        selected = model.selected_version(latest=True)
        assert selected is not None
        assert selected["version_id"] == "ver_2"

        model.search = "sample"
        app.refresh()
        _settle(app)
        assert fake_client.calls[-1]["search"] == "sample"
    finally:
        app.close()


def test_project_browser_toolbar_buttons_fire_their_handler_once(monkeypatch):
    """One click on a toolbar button must run its handler exactly once (RF-617)."""
    from chisurf.plugins.core.project_browser.gui.panel import ProjectPanel
    from chisurf.plugins.core.project_browser.test.driving import BIG, BrowserDriver

    calls: dict[str, int] = {}
    handlers = ("open", "save", "export", "import_project", "delete", "refresh")
    for name in handlers:
        monkeypatch.setattr(
            ProjectPanel,
            name,
            lambda self, *_args, _name=name: calls.__setitem__(_name, calls.get(_name, 0) + 1),
        )
    monkeypatch.setattr(ProjectPanel, "enabled", lambda self, name: True)

    app = _app(client=FakeProjectBrowserClient())
    try:
        drv = BrowserDriver(app, BIG)
        drv.settle()
        for name in handlers:
            calls.clear()
            drv.click(name)
            drv.draw(2)
            assert calls.get(name, 0) == 1, f"{name} fired {calls.get(name, 0)} times"
    finally:
        app.close()


@pytest.fixture
def deployment(authenticated_browser, sample_project_payload):
    """The window on the authenticated MMFDB deployment the Save path uses."""
    client = authenticated_browser["client"]

    def save(name, visibility="public", notes=""):
        payload = copy.deepcopy(sample_project_payload)
        payload["meta"]["name"] = name
        saved = client.save_project(
            project_name=name, project_payload=payload, visibility=visibility, notes=notes
        )
        assert saved["ok"] is True, saved
        return saved, payload

    return SimpleNamespace(
        client=client,
        save=save,
        tmp_path=authenticated_browser["tmp_path"],
        db={"client": client, "payload": sample_project_payload},
    )


def test_project_browser_gui_uses_inprocess_chisurf_services_with_sample_data(deployment):
    saved, _ = deployment.save("Sample Project", notes="headless GUI test")

    app = _app(deployment.db)
    try:
        _settle(app)
        assert len(app.model.projects) == 1
        project = app.model.projects[0]
        assert project["project_id"] == saved["project_id"]
        assert len(project["versions"]) == 1
        version = project["versions"][0]
        assert version["version_id"] == saved["version_id"]
        assert version["dataset_count"] == 1
    finally:
        app.close()


def test_project_browser_gui_deletes_selected_version_with_confirmation(deployment):
    saved, _ = deployment.save("Delete Project", notes="headless delete GUI test")

    app = _app(deployment.db)
    try:
        _settle(app)
        app.model.selected_id = saved["version_id"]
        assert app.model.selected_version()["version_id"] == saved["version_id"]

        app.begin_delete()
        assert app.modal == "delete"  # asks first
        app.confirm_delete()
        _settle(app)

        assert [p for p in app.model.projects if p.get("version_count")] == []
    finally:
        app.close()


def test_project_browser_gui_imports_archive_with_collision_remap(deployment):
    saved, _ = deployment.save("Import Project", notes="headless import GUI test")
    archive_path = deployment.tmp_path / "import-project.cs.pto"
    exported = deployment.client.export_csp(
        version_id=saved["version_id"], target_path=str(archive_path)
    )
    assert exported["ok"] is True

    app = _app(deployment.db)
    try:
        _settle(app)
        app.import_preview(archive_path)
        _settle(app)
        assert app.modal == "import"
        app.confirm_import()
        _settle(app)

        assert len(app.model.projects) == 1
        project = _project(app, "Import Project")
        assert project["project_id"] == saved["project_id"]
        assert len(project["versions"]) == 2
    finally:
        app.close()


def test_project_browser_gui_restores_selected_version_into_chisurf_context(deployment):
    saved, payload = deployment.save(
        "Restore Project", visibility="private", notes="headless restore GUI test"
    )

    app = _app(deployment.db)
    try:
        _settle(app)
        app.model.selected_id = saved["version_id"]
        app.open_selected()
        _settle(app)

        assert len(app.restored) == 1
        restored = app.restored[0]
        assert restored["meta"]["name"] == "Restore Project"
        assert set(restored["datasets"]) == set(payload["datasets"])
        assert len(app.reopened) == 1
        context = app.model.context
        assert context._current_project_id == saved["project_id"]
        assert context._current_project_version_id == saved["version_id"]
        assert context._current_project_name == "Restore Project"
        assert context._current_project_visibility == "private"
    finally:
        app.close()
