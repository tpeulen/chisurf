"""Regressions for the concrete project presentation/storage review findings."""

from types import SimpleNamespace

import pytest

from chisurf.core.project import capture_session, storage
from chisurf.core.project.lifecycle import ProjectDocument
from chisurf.plugins.core.project_browser.gui.model import ProjectBrowserModel


def test_ordinary_save_resolves_backend_before_reusing_file_path(monkeypatch, tmp_path):
    """A portable destination cannot override a newly configured real deployment."""
    from chisurf.gui.main_helper import ProjectMixin

    calls = []
    document = ProjectDocument(path=tmp_path / "previous.cs.pto", name="live")
    context = SimpleNamespace(
        _get_project_document=lambda: document,
        _project_display_name=ProjectMixin._project_display_name,
        add_recent_project=lambda path: None,
    )

    def select():
        calls.append("select")
        raise storage.ProjectStorageError("configured authentication failure")

    monkeypatch.setattr(storage, "select_backend", select)
    monkeypatch.setattr(storage, "save_file", lambda *args: calls.append("file"))
    monkeypatch.setattr(
        "chisurf.macros.core_fit.get_project_payload",
        lambda name: capture_session([], [], name=name),
    )
    monkeypatch.setattr("chisurf.gui.main_helper.dialogs.warning", lambda *args: None)

    assert ProjectMixin._save_project_snapshot(context) is False
    assert calls == ["select"]
    assert document.path == tmp_path / "previous.cs.pto"


def test_browser_configured_auth_failure_uses_exact_storage_transport(monkeypatch):
    """Browser discovery must use the adapter that cannot bootstrap a local token."""
    calls = []
    monkeypatch.setattr(storage, "select_backend", lambda: "mmfdb")

    def denied(settings):
        calls.append(settings)
        raise storage.ProjectStorageError("no authenticated runtime token")

    monkeypatch.setattr(storage, "_real_client", denied)
    # Detect the competing bare browser client before it can auto-auth locally.
    monkeypatch.setattr(
        "chisurf.plugins.core.project_browser.gui.client.ProjectBrowserClient",
        lambda **kwargs: None,
    )
    with pytest.raises(storage.ProjectStorageError, match="authenticated runtime token"):
        ProjectBrowserModel(context=SimpleNamespace()).client
    assert len(calls) == 1


@pytest.mark.parametrize("field, actual", [("version_id", "v1"), ("project_id", "other")])
def test_database_save_rejects_wrong_readback_identity(field, actual):
    """Identical science does not make a different project/version acceptable."""
    project = capture_session([], [], name="live")
    result = {"ok": True, "project_id": "p1", "version_id": "v2", "version_number": 2}
    readback = {**result, "project_payload": project.to_dict(), field: actual}
    client = SimpleNamespace(
        save_project=lambda **kwargs: result,
        restore_project=lambda version: readback,
    )
    with pytest.raises(storage.ProjectStorageError, match="readback mismatch"):
        storage.save_database(
            project,
            project_id="p1",
            client=client,
            mmfdb_settings={"client": {"mode": "remote"}},
        )


@pytest.mark.parametrize("field, actual", [("version_id", "v1"), ("project_id", "other")])
def test_browser_rejects_wrong_requested_identity_before_loading(field, actual):
    """The selected identity is checked at fetch and before publication."""
    project = capture_session([], [], name="incoming")
    result = {
        "ok": True,
        "project_id": "p1",
        "version_id": "v2",
        "project_payload": project.to_dict(),
        field: actual,
    }
    loaded = []
    document = ProjectDocument(project_id="old", version_id="old-v", backend="mmfdb")
    model = ProjectBrowserModel(
        context=SimpleNamespace(_project_document=document),
        client=SimpleNamespace(restore_project=lambda **kwargs: result),
        payload_loader=loaded.append,
        window_restorer=lambda payload: None,
    )
    model.projects = [{"project_id": "p1", "versions": [{"version_id": "v2", "project_id": "p1"}]}]
    model.selected_id = "v2"
    with pytest.raises(ValueError, match="identity"):
        model.fetch_restore({"version_id": "v2", "project_id": "p1"})
    with pytest.raises(ValueError, match="identity"):
        model.apply_restore(result, "v2")
    assert loaded == []
    assert document.project_id == "old"
    assert document.version_id == "old-v"


def test_browser_presentation_reads_canonical_ui(monkeypatch):
    """Presentation receives the exact canonical UI state."""
    from chisurf.plugins.core.project_browser.gui.model import restore_fit_windows

    calls = []
    monkeypatch.setattr(
        "chisurf.macros.core_fit.restore_gui_from_fits",
        lambda uids, ui: calls.append((uids, ui)),
    )
    restore_fit_windows({"fits": [{"uid": "f1"}], "ui": {"current_fit_index": 0}})
    assert calls == [(["f1"], {"current_fit_index": 0})]


def test_browser_restorer_returns_prepared_presentation_even_without_fits(monkeypatch):
    """The owner must receive the reversible token for accepting/rolling back windows."""
    from chisurf.plugins.core.project_browser.gui.model import restore_fit_windows

    prepared = object()
    calls = []
    monkeypatch.setattr(
        "chisurf.macros.core_fit.restore_gui_from_fits",
        lambda uids, ui: calls.append((uids, ui)) or prepared,
    )
    assert restore_fit_windows({"fits": [], "ui": {"current_fit_index": None}}) is prepared
    assert calls == [([], {"current_fit_index": None})]


@pytest.fixture
def active_session(monkeypatch):
    """Install real science/history with identity and a selected fit."""
    import chisurf as cs
    from chisurf.core.data import DataCurve
    from chisurf.core.fitting.fit import FitGroup
    from chisurf.core.models.description import tcspc_lifetime
    from chisurf.history.core import OperationHistory

    curve = DataCurve(x=[0.0, 1.0, 2.0], y=[5.0, 3.0, 1.0], name="old curve")
    fit = FitGroup(data=[curve], model_class=tcspc_lifetime)
    history = OperationHistory()
    history.load_events([{"action_type": "old", "payload": {"value": 7}}])
    document = ProjectDocument(project_id="old", version_id="old-v", backend="mmfdb", name="old")
    context = SimpleNamespace(
        _project_document=document,
        _get_project_document=lambda: document,
        _guard_project_transition=lambda: True,
        _current_project_id="old",
        _current_project_version_id="old-v",
        _current_project_path=None,
        _current_project_name="old",
        fit_idx=0,
    )
    for name, value in (
        ("imported_datasets", [curve]),
        ("fits", [fit]),
        ("current_fit", fit),
        ("current_fit_idx", 0),
        ("history", history),
        ("cs", context),
        ("__client__", None),
    ):
        monkeypatch.setattr(cs, name, value, raising=False)
    return curve, fit, history, context


def _throwing_restorer(payload):
    """Reject window construction after the incoming science was installed."""
    raise RuntimeError("window reconstruction failed")


def test_browser_window_failure_restores_local_history_and_selection(active_session):
    """Presentation failure restores science, history, selection and document."""
    import chisurf as cs

    curve, fit, history, context = active_session
    old_events = history.list_events()
    project = capture_session([], [], name="incoming")
    project.extra["history_events"] = [{"action_type": "incoming"}]
    model = ProjectBrowserModel(context=context, window_restorer=_throwing_restorer)
    result = {
        "ok": True,
        "project_id": "p1",
        "version_id": "v1",
        "project_payload": project.to_dict(),
    }
    with pytest.raises(RuntimeError, match="window reconstruction failed"):
        model.apply_restore(result, "v1")
    assert cs.imported_datasets == [curve]
    assert cs.fits == [fit]
    assert history.list_events() == old_events
    assert cs.current_fit is fit
    assert cs.current_fit_idx == 0
    assert context.fit_idx == 0
    assert context._project_document.project_id == context._current_project_id == "old"
    assert context._project_document.version_id == context._current_project_version_id == "old-v"


def test_browser_window_failure_restores_actual_server_owner(active_session, monkeypatch):
    """Rollback reaches SessionState without slicing real read-only proxies."""
    import chisurf as cs
    from chisurf.core.api._proxies import ProxyDatasetList, ProxyFitList, install_proxies
    from chisurf.core.plugin.client import InProcessClient
    from chisurf.server.dispatcher import ServiceDispatcher
    from chisurf.server.services.projects import register_project_snapshot_services
    from chisurf.server.session import SessionState

    curve, fit, history, context = active_session
    state = SessionState(datasets=[curve], fits=[fit], current_fit_uid=fit.unique_identifier)
    state.history = history
    state.project_metadata = {"origin": "old"}
    state.project_path = "/old.cs.pto"
    dispatcher = ServiceDispatcher(state)
    dispatcher._build_default_registry()
    register_project_snapshot_services(dispatcher, state)

    class Client(InProcessClient):
        def dataset__list(self):
            return self.call("dataset.list")["datasets"]

        def fit__list(self):
            return self.call("fit.list")["fits"]

    client = Client(dispatcher)
    install_proxies(client)
    old_proxies = cs.imported_datasets, cs.fits
    assert isinstance(old_proxies[0], ProxyDatasetList)
    assert isinstance(old_proxies[1], ProxyFitList)
    project = capture_session([], [], name="incoming")
    project.extra["history_events"] = [{"action_type": "incoming"}]
    model = ProjectBrowserModel(context=context, window_restorer=_throwing_restorer)
    result = {
        "ok": True,
        "project_id": "p1",
        "version_id": "v1",
        "project_payload": project.to_dict(),
    }
    with pytest.raises(RuntimeError, match="window reconstruction failed"):
        model.apply_restore(result, "v1")
    assert (cs.imported_datasets, cs.fits) == old_proxies
    assert state.datasets == [curve]
    assert state.fits == [fit]
    assert state.current_fit_uid == fit.unique_identifier
    assert state.history.list_events() == [{"action_type": "old", "payload": {"value": 7}}]
    assert state.project_metadata == {"origin": "old"}
    assert state.project_path == "/old.cs.pto"
    assert context._project_document.project_id == context._current_project_id == "old"


def test_open_file_window_failure_rolls_back_before_recents(active_session, monkeypatch, tmp_path):
    """The actual file-opening path waits for synchronous presentation."""
    import chisurf as cs
    from chisurf.gui import project_helpers

    curve, fit, history, context = active_session
    path = storage.save_file(capture_session([], [], name="incoming"), tmp_path / "incoming")
    recents = []
    warnings = []
    monkeypatch.setattr(
        "chisurf.macros.core_fit.restore_gui_from_fits", lambda *args: _throwing_restorer(None)
    )
    monkeypatch.setattr(project_helpers, "add_recent_project", lambda *args: recents.append(args))
    monkeypatch.setattr(project_helpers.dialogs, "warning", lambda *args: warnings.append(args))
    assert project_helpers.open_recent_project(context, str(path)) is False
    assert warnings
    assert recents == []
    assert cs.imported_datasets == [curve]
    assert cs.fits == [fit]
    assert cs.current_fit is fit
    assert cs.current_fit_idx == 0
    assert history.list_events() == [{"action_type": "old", "payload": {"value": 7}}]
    assert context._project_document.project_id == context._current_project_id == "old"


def test_explicit_save_as_forces_portable_live_science(active_session, monkeypatch, tmp_path):
    """Save As publishes current science without consulting configured MMFDB."""
    import numpy as np

    from chisurf.core.project import restore_session
    from chisurf.gui.main_helper import ProjectMixin

    curve, fit, history, context = active_session
    context._project_display_name = ProjectMixin._project_display_name
    recents = []
    context.add_recent_project = recents.append
    monkeypatch.setattr(
        storage, "select_backend", lambda: pytest.fail("explicit Save As must force PTO")
    )
    target = tmp_path / "live.cs.pto"
    assert ProjectMixin._save_project_snapshot(context, save_as=target) is True
    loaded = storage.load_file(target)
    restored = restore_session(loaded)
    np.testing.assert_array_equal(restored.datasets[0].y, curve.y)
    assert restored.fits[0].unique_identifier == fit.unique_identifier
    assert restored.fits[0].grouped_fits[0].data is restored.datasets[0]
    assert recents == [target]
    assert context._project_document.path == context._current_project_path == target
    assert context._current_project_id is None


def test_ordinary_save_file_chooser_cancellation_keeps_active_identity(active_session, monkeypatch):
    """Cancelling a destination chooser cannot authorize replacement."""
    import chisurf as cs
    from chisurf.gui.main_helper import ProjectMixin

    curve, fit, history, context = active_session
    context._project_display_name = ProjectMixin._project_display_name
    context.add_recent_project = lambda path: pytest.fail(
        "cancelled save cannot record a recent path"
    )
    monkeypatch.setattr(storage, "select_backend", lambda: "file")
    monkeypatch.setattr(
        "chisurf.gui.main_helper.QtWidgets.QFileDialog.getSaveFileName", lambda *args: ("", "")
    )
    assert ProjectMixin._save_project_snapshot(context) is False
    assert cs.imported_datasets == [curve]
    assert cs.fits == [fit]
    assert cs.current_fit is fit
    assert context._project_document.project_id == context._current_project_id == "old"


def test_ordinary_save_existing_path_still_uses_database_dialog(
    active_session, monkeypatch, tmp_path
):
    """A configured real backend controls Save even for a portable document."""
    from qtpy import QtWidgets

    from chisurf.gui.main_helper import ProjectMixin

    curve, fit, history, context = active_session
    calls = []
    context._project_document.path = tmp_path / "previous.cs.pto"
    context._project_display_name = ProjectMixin._project_display_name
    context.add_recent_project = lambda path: pytest.fail(
        "cancelled database save must not write a file"
    )
    monkeypatch.setattr(storage, "select_backend", lambda: calls.append("mmfdb") or "mmfdb")
    monkeypatch.setattr(
        storage, "save_file", lambda *args: pytest.fail("ordinary Save bypassed real backend")
    )

    class Dialog:
        def __init__(self, **kwargs):
            calls.append("dialog")

        def exec(self):
            return QtWidgets.QDialog.Rejected

    monkeypatch.setattr("chisurf.plugins.core.project_browser.gui.tool.SaveProjectDialog", Dialog)
    assert ProjectMixin._save_project_snapshot(context) is False
    assert calls == ["mmfdb", "dialog"]
    assert context._project_document.project_id == "old"
    assert context._project_document.path == tmp_path / "previous.cs.pto"


def test_browser_cancel_keeps_active_session(active_session):
    """Direct browser replacement uses the shared owner's cancellation guard."""
    import chisurf as cs

    curve, fit, history, context = active_session
    context._guard_project_transition = lambda: False
    model = ProjectBrowserModel(
        context=context, window_restorer=lambda payload: pytest.fail("cancelled presentation")
    )
    result = {
        "ok": True,
        "project_id": "p1",
        "version_id": "v1",
        "project_payload": capture_session([], [], name="incoming").to_dict(),
    }
    assert model.apply_restore(result, "v1") is False
    assert cs.imported_datasets == [curve]
    assert cs.fits == [fit]
    assert cs.current_fit is fit
    assert context._project_document.project_id == context._current_project_id == "old"


def test_browser_failed_identity_publication_rolls_back_owner(active_session):
    """A failure after successful presentation must still reject the replacement."""
    import chisurf as cs

    curve, fit, history, context = active_session
    document = context._project_document
    adopt = document.adopt
    calls = []

    def fail_once(candidate):
        calls.append(candidate.project_id)
        adopt(candidate)
        if len(calls) == 1:
            raise RuntimeError("identity publication failed")

    document.adopt = fail_once
    model = ProjectBrowserModel(context=context, window_restorer=lambda payload: None)
    result = {
        "ok": True,
        "project_id": "p1",
        "version_id": "v1",
        "project_payload": capture_session([], [], name="incoming").to_dict(),
    }
    with pytest.raises(RuntimeError, match="identity publication failed"):
        model.apply_restore(result, "v1")
    assert cs.imported_datasets == [curve]
    assert cs.fits == [fit]
    assert cs.current_fit is fit
    assert cs.current_fit_idx == 0
    assert context._project_document.project_id == context._current_project_id == "old"


def test_save_failed_identity_publication_keeps_previous_document(
    active_session, monkeypatch, tmp_path
):
    """A written file does not accept a partially published document identity."""
    import chisurf as cs
    from chisurf.gui.main_helper import ProjectMixin

    curve, fit, history, context = active_session
    context._project_display_name = ProjectMixin._project_display_name
    context.add_recent_project = lambda path: None
    document = context._project_document
    adopt = document.adopt
    attempts = []

    def fail_once(candidate):
        attempts.append(candidate.path)
        adopt(candidate)
        if len(attempts) == 1:
            raise RuntimeError("save identity publication failed")

    document.adopt = fail_once
    monkeypatch.setattr("chisurf.gui.main_helper.dialogs.warning", lambda *args: None)
    assert ProjectMixin._save_project_snapshot(context, save_as=tmp_path / "new.cs.pto") is False
    assert cs.imported_datasets == [curve]
    assert cs.fits == [fit]
    assert cs.current_fit is fit
    assert document.project_id == context._current_project_id == "old"
    assert document.version_id == context._current_project_version_id == "old-v"
    assert document.path is None


def test_real_database_browser_restore_failure_keeps_active_science(
    active_session, monkeypatch, tmp_path
):
    """Drive exact-version fetch through an authenticated actual MMFDB service."""
    from mmfdb.repository import MFDatabase
    from mmfdb.security.auth import create_session

    import chisurf as cs
    from chisurf.core.data import DataCurve
    from chisurf.history.core import OperationHistory
    from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient
    from chisurf.plugins.core.project_browser.gui.client import ProjectBrowserClient

    curve, fit, history, context = active_session
    database_path = tmp_path / "real-browser.db"
    with MFDatabase(database_path) as database:
        database.ensure_user("browser-review")
        token = create_session(database.conn, "browser-review")["token"]
        database.conn.commit()
    monkeypatch.setattr(
        "chisurf.plugins.core.project_browser.backend.services.resolve_database_path",
        lambda: database_path,
    )
    monkeypatch.delenv("MMFDB_DATABASE_URL", raising=False)
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(database_path))
    from mmfdb.config import reset_runtime_config

    reset_runtime_config()
    base = MMFDBClient(inprocess=True)
    base.token = token
    client = ProjectBrowserClient(mmfdb_client=base)
    incoming = DataCurve(x=[0.0, 1.0, 2.0], y=[15.0, 9.0, 3.0], name="incoming curve")
    project = capture_session([incoming], [], name="incoming")
    incoming_history = OperationHistory()
    incoming_history.record("dataset.add", "incoming curve", persist=False)
    project.extra["history_events"] = incoming_history.list_events()
    saved = storage.save_database(
        project,
        client=client,
        mmfdb_settings={"client": {"mode": "remote"}},
    )
    model = ProjectBrowserModel(client=client, context=context, window_restorer=_throwing_restorer)
    model.projects = [{"project_id": saved["project_id"], "versions": [saved]}]
    result = model.fetch_restore(saved)
    assert result["version_id"] == saved["version_id"]
    assert result["project_id"] == saved["project_id"]
    assert result["project_payload"] == project.to_dict()
    with pytest.raises(RuntimeError, match="window reconstruction failed"):
        model.apply_restore(result, saved["version_id"])
    assert cs.imported_datasets == [curve]
    assert cs.fits == [fit]
    assert cs.current_fit is fit
    assert history.list_events() == [{"action_type": "old", "payload": {"value": 7}}]
    assert context._project_document.project_id == context._current_project_id == "old"
