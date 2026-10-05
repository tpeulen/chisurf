"""Qt-level regression tests for the project transition guard."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from chisurf.core.project.lifecycle import SaveDecision, confirm_transition

qtpy = pytest.importorskip("qtpy")
from qtpy import QtGui, QtWidgets  # noqa: E402

from chisurf.gui.main import Main  # noqa: E402


@pytest.fixture
def app():
    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    return application


class _CloseProbe(QtWidgets.QWidget):
    """Small real QWidget carrying only the shutdown hooks Main.closeEvent uses."""

    def __init__(self, decision: bool):
        super().__init__()
        self.decision = decision
        self.saved_window_state = False
        self.closed_fits = False

    def _guard_project_transition(self):
        return self.decision

    def _save_window_state(self):
        self.saved_window_state = True

    def _save_setup_defaults(self):
        pass

    def onCloseAllFits(self):
        self.closed_fits = True


@pytest.mark.parametrize("decision, accepted", [(False, False), (True, True)])
def test_real_qcloseevent_honours_project_guard(app, monkeypatch, decision, accepted):
    """Cancel/error stops before teardown; an accepted decision reaches teardown."""
    probe = _CloseProbe(decision)
    monkeypatch.setattr(
        "chisurf.gui.main.cs.core.settings.gui",
        {"confirm_close_program": False},
    )

    event = QtGui.QCloseEvent()
    Main.closeEvent(probe, event)

    assert event.isAccepted() is accepted
    assert probe.saved_window_state is accepted
    assert probe.closed_fits is accepted


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


def test_close_project_action_failure_keeps_document(monkeypatch):
    """A failed close action must not reset identity or report success."""
    import chisurf as cs
    from chisurf.core.project.lifecycle import ProjectDocument
    from chisurf.gui.main_helper import ProjectMixin

    document = ProjectDocument(project_id="p1", version_id="v1", name="live")
    dummy = SimpleNamespace(
        _guard_project_transition=lambda: True,
        _get_project_document=lambda: document,
        _current_project_id="p1",
        _current_project_version_id="v1",
        _current_project_name="live",
        _current_project_path=None,
    )
    monkeypatch.setattr(
        cs.core.actions, "dispatch", lambda **kwargs: (_ for _ in ()).throw(OSError("close failed"))
    )
    monkeypatch.setattr("chisurf.gui.main_helper.dialogs.warning", lambda *args: None)
    assert ProjectMixin.onCloseProject(dummy) is False
    assert document.project_id == "p1"
    assert dummy._current_project_id == "p1"


def test_open_file_identity_failure_happens_before_science_commit(monkeypatch, tmp_path):
    import chisurf as cs
    from chisurf.core.project import Project
    from chisurf.core.project.lifecycle import ProjectDocument
    from chisurf.gui import project_helpers

    old_dataset = object()
    monkeypatch.setattr(cs, "imported_datasets", [old_dataset])
    monkeypatch.setattr(cs, "fits", [])
    project = Project(name="candidate")
    document = ProjectDocument(project_id="p1", version_id="v1", backend="mmfdb")
    document.stage_file_save = lambda *args: (_ for _ in ()).throw(ValueError("identity failed"))
    window = SimpleNamespace(
        _guard_project_transition=lambda: True,
        _get_project_document=lambda: document,
    )
    path = tmp_path / "candidate.cs.pto"
    path.touch()
    committed = []
    monkeypatch.setattr("chisurf.core.project.storage.load_file", lambda value: project)
    monkeypatch.setattr(
        "chisurf.macros.core_fit.load_project_payload",
        lambda *args, **kwargs: committed.append(True),
    )
    monkeypatch.setattr(project_helpers.dialogs, "warning", lambda *args: None)

    assert project_helpers.open_recent_project(window, str(path)) is False
    assert committed == []
    assert cs.imported_datasets == [old_dataset]
    assert document.project_id == "p1"


def test_reinitialize_failed_presentation_restores_science_and_document(monkeypatch, app):
    import numpy as np

    import chisurf as cs
    from chisurf.core.data import DataCurve
    from chisurf.core.fitting.fit import Fit
    from chisurf.core.models.parse.parse import ParseModel
    from chisurf.core.project.lifecycle import ProjectDocument
    from chisurf.gui.main_helper import SetupMixin

    old_dataset = DataCurve(
        x=np.arange(12.0),
        y=3 * np.arange(12.0) + 2,
        ex=np.ones(12),
        ey=np.ones(12),
        name="synthetic linear rollback control",
    )
    old_fit = Fit(data=old_dataset, model_class=ParseModel)
    old_fit.model.func = "a*x+b"
    old_fit.model.parameters_all_dict["a"].value = 3
    old_fit.model.parameters_all_dict["b"].value = 2
    old_fit.fit_range = (1, 10)
    old_fit.model.update()
    prediction = old_fit.model.y.copy()
    datasets = [old_dataset]
    fits = [old_fit]
    monkeypatch.setattr(cs, "imported_datasets", datasets)
    monkeypatch.setattr(cs, "fits", fits)
    document = ProjectDocument(project_id="p1", version_id="v1", backend="mmfdb")
    document_state = document.__dict__.copy()
    guard_calls = []
    presentation_calls = []
    errors = []
    dummy = SimpleNamespace(
        _guard_project_transition=lambda: guard_calls.append("confirm") or True,
        _project_has_content=lambda: True,
        _get_project_document=lambda: document,
    )
    monkeypatch.setattr(cs, "__client__", None, raising=False)
    monkeypatch.setattr(cs, "cs", dummy)
    monkeypatch.setattr(cs, "_project_gui", dummy, raising=False)
    monkeypatch.setattr(cs, "_project_authorizations", {}, raising=False)
    monkeypatch.setattr(cs, "_project_transition", None, raising=False)

    def partial_presentation(fit_uids, ui_state):
        presentation_calls.append("partial presentation")
        assert fit_uids == []
        assert cs.fits == [] and cs.imported_datasets == []
        raise RuntimeError("reset presentation failed")

    monkeypatch.setattr("chisurf.macros.core_fit.restore_gui_from_fits", partial_presentation)
    monkeypatch.setattr(
        "chisurf.gui.main_helper.dialogs.error", lambda *args: errors.append(args[-1])
    )

    assert SetupMixin.reinitialize(dummy, show_confirmation=False, show_success=False) is False
    assert presentation_calls == ["partial presentation"], errors
    assert errors == ["An error occurred during reinitialization:\nreset presentation failed"]
    assert guard_calls and set(guard_calls) == {"confirm"}
    assert cs.imported_datasets is datasets and datasets == [old_dataset]
    assert cs.fits is fits and fits == [old_fit]
    assert tuple(old_fit.fit_range) == (1, 10)
    np.testing.assert_array_equal(old_fit.model.y, prediction)
    assert document.__dict__ == document_state
    assert document.project_id == "p1"


def test_reinitialize_success_clears_document_and_legacy_identity(monkeypatch, app):
    import chisurf as cs
    from chisurf.core.project.lifecycle import ProjectDocument
    from chisurf.gui.main_helper import SetupMixin

    monkeypatch.setattr(cs, "imported_datasets", [])
    monkeypatch.setattr(cs, "fits", [])
    document = ProjectDocument(project_id="p1", version_id="v1", backend="mmfdb")
    dummy = SimpleNamespace(
        _guard_project_transition=lambda: True,
        _project_has_content=lambda: False,
        _get_project_document=lambda: document,
        _current_project_path=None,
        _current_project_id="p1",
        _current_project_version_id="v1",
        _current_project_name="remote",
    )

    monkeypatch.setattr(cs, "__client__", None, raising=False)
    monkeypatch.setattr(cs, "cs", dummy)
    monkeypatch.setattr(cs, "_project_gui", dummy, raising=False)
    monkeypatch.setattr(cs, "_project_authorizations", {}, raising=False)

    assert SetupMixin.reinitialize(dummy, show_confirmation=False, show_success=False) is True
    assert document.project_id is None
    assert dummy._current_project_id is None
    assert dummy._current_project_version_id is None
    assert dummy._current_project_name is None


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


def test_project_shortcuts_use_conventional_project_bindings(app):
    from chisurf.gui.main import configure_project_shortcuts

    host = QtWidgets.QWidget()
    host.actionSave_Project = QtWidgets.QAction(host)
    host.actionExport_Project = QtWidgets.QAction(host)
    host.actionSaveCurrentFit = QtWidgets.QAction(host)

    configure_project_shortcuts(host)

    assert host.actionSave_Project.shortcut().toString() == "Ctrl+S"
    assert host.actionExport_Project.shortcut().toString() == "Ctrl+Shift+S"
    assert host.actionSaveCurrentFit.shortcut().toString() == "Ctrl+Alt+S"


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
