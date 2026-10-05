"""Regression probes for authoritative project replacement boundaries."""

from threading import RLock
from types import SimpleNamespace

import numpy as np
import pytest

import chisurf as cs
from chisurf.core.actions import project_actions
from chisurf.core.api._proxies import install_proxies
from chisurf.core.data import DataCurve
from chisurf.core.plugin.client import InProcessClient
from chisurf.core.project import capture_session
from chisurf.core.project.lifecycle import ProjectDocument
from chisurf.macros import core_fit
from chisurf.server.dispatcher import ServiceDispatcher
from chisurf.server.services.projects import register_project_snapshot_services
from chisurf.server.session import SessionState


class ProjectClient(InProcessClient):
    """Expose the same convenience methods used by real installed proxies."""

    def dataset__list(self):
        """Read the authoritative datasets through the real dispatcher."""
        return self.call("dataset.list")["datasets"]

    def fit__list(self):
        """Read the authoritative fits through the real dispatcher."""
        return self.call("fit.list")["fits"]


class RuntimeHistory:
    """History containing mutable data and an uncopyable runtime resource."""

    def __init__(self):
        self.events = [{"action_type": "old"}]
        self.runtime = {"lock": RLock(), "cache": ["old"]}

    def list_events(self):
        """Return the persistable event list."""
        return list(self.events)

    def load_events(self, events, replace=True):
        """Replace events and invalidate a resource-bearing runtime cache."""
        self.events[:] = events
        self.runtime["cache"].clear()


@pytest.fixture
def live(monkeypatch):
    """Install a real local curve, history, selection and document."""
    curve = DataCurve(x=np.arange(4.0), y=np.arange(4.0) + 1, ex=np.ones(4), ey=np.ones(4))
    history = RuntimeHistory()
    document = ProjectDocument(project_id="old", version_id="v-old", backend="mmfdb")
    document._saved_fingerprint = "old-baseline"
    gui = SimpleNamespace(
        fit_idx=0,
        current_fit=None,
        _guard_project_transition=lambda: True,
        _get_project_document=lambda: document,
        _current_project_path=None,
        _current_project_id="old",
        _current_project_version_id="v-old",
        _current_project_name="old",
    )
    monkeypatch.setattr(cs, "imported_datasets", [curve])
    monkeypatch.setattr(cs, "fits", [])
    monkeypatch.setattr(cs, "history", history, raising=False)
    monkeypatch.setattr(cs, "current_fit", None, raising=False)
    monkeypatch.setattr(cs, "current_fit_idx", -1, raising=False)
    monkeypatch.setattr(cs, "cs", gui)
    monkeypatch.setattr(cs, "__client__", None, raising=False)
    for name in (
        "project_metadata",
        "project_path",
        "project_name",
        "current_fit_uid",
        "native_session",
        "_project_transition",
    ):
        monkeypatch.setattr(cs, name, getattr(cs, name, None), raising=False)
    return curve, history, document, gui


def test_data_only_gui_capture_has_no_stale_fit_selection(live):
    """A data-only GUI must reload the snapshot it actually saves."""
    project = core_fit.get_project_payload()
    assert project.ui_state.get("current_fit_index") in (None, -1)
    result = core_fit.load_project_payload(project)
    assert result["ok"] is True
    assert len(cs.imported_datasets) == 1
    assert cs.current_fit is None
    assert cs.current_fit_idx == -1


def test_ordinary_gui_capture_includes_history(live):
    """Ordinary Save uses get_project_payload without archive-only additions."""
    project = core_fit.get_project_payload()
    assert project.extra.get("history_events") == live[1].events


def test_direct_load_action_guard_cancels_without_mutation(live, monkeypatch, tmp_path):
    """Direct project.load must honor the same replacement gate as the GUI."""
    curve, history, document, gui = live
    gui._guard_project_transition = lambda: False
    project = capture_session([], [], name="incoming")
    monkeypatch.setattr("chisurf.core.project.storage.load_file", lambda path: project)
    result = project_actions.load_project._action_spec.handler(str(tmp_path / "new.cs.pto"))
    assert result == {"ok": False, "cancelled": True}
    assert cs.imported_datasets == [curve]
    assert history.events == [{"action_type": "old"}]
    assert document.project_id == "old"


def test_real_proxy_load_action_commits_server_session(live, monkeypatch, tmp_path):
    """RPC dictionaries are normalized without slicing installed proxies."""
    curve, history, document, gui = live
    state = SessionState(datasets=[curve])
    state.history = history
    dispatcher = ServiceDispatcher(state)
    dispatcher._build_default_registry()
    register_project_snapshot_services(dispatcher, state)
    client = ProjectClient(dispatcher)
    install_proxies(client)
    datasets_proxy, fits_proxy = cs.imported_datasets, cs.fits
    project = capture_session([], [], name="incoming")
    monkeypatch.setattr("chisurf.core.project.storage.load_file", lambda path: project)
    monkeypatch.setattr(core_fit, "restore_gui_from_fits", lambda *args: None)
    result = project_actions.load_project._action_spec.handler(str(tmp_path / "new.cs.pto"))
    assert result["ok"] is True
    assert state.datasets == []
    assert state.fits == []
    assert cs.imported_datasets is datasets_proxy
    assert cs.fits is fits_proxy
    assert document.name == "incoming"


@pytest.mark.parametrize("remote", [False, True])
def test_presentation_failure_restores_owner_history_selection_and_document(
    live, monkeypatch, tmp_path, remote
):
    """A failing synchronous view cannot accept or lose old scientific objects."""
    from chisurf.core.fitting.fit import Fit
    from test.project.test_server_project_snapshot import SnapshotLinearModel

    curve, history, document, gui = live
    fit = Fit(data=curve, model_class=SnapshotLinearModel)
    fit.model.update()
    cs.fits.append(fit)
    cs.current_fit = fit
    cs.current_fit_idx = 0
    gui.current_fit = fit
    gui._fit_idx = 0
    lock = history.runtime["lock"]
    old_runtime, old_cache = history.runtime, history.runtime["cache"]
    import IMP.bff as bff

    old_native = bff.get_session()
    cs.native_session = old_native
    state = None
    if remote:
        state = SessionState(datasets=[curve], fits=[fit], current_fit_uid=fit.unique_identifier)
        state.history = history
        state.native_session = old_native
        state.current_fit = fit
        state.current_fit_idx = 0
        state.project_metadata = {"old": ["metadata"]}
        state.project_path = "/old.cs.pto"
        dispatcher = ServiceDispatcher(state)
        dispatcher._build_default_registry()
        register_project_snapshot_services(dispatcher, state)
        install_proxies(ProjectClient(dispatcher))
    project = capture_session([], [], name="incoming")
    project.extra["history_events"] = [{"action_type": "incoming"}]
    monkeypatch.setattr("chisurf.core.project.storage.load_file", lambda path: project)

    def reject_presentation(*args):
        """Mutate GUI selection as a real failed window reconstruction would."""
        gui.current_fit = None
        gui._fit_idx = -1
        raise RuntimeError("window reconstruction failed")

    monkeypatch.setattr(core_fit, "restore_gui_from_fits", reject_presentation)
    monkeypatch.setattr("chisurf.core.runtime.presentation.defer", lambda *args: None)
    with pytest.raises(RuntimeError, match="window reconstruction failed"):
        project_actions.load_project._action_spec.handler(str(tmp_path / "candidate.cs.pto"))
    owner = state if remote else cs
    assert getattr(owner, "datasets" if remote else "imported_datasets")[0] is curve
    assert owner.fits[0] is fit
    assert owner.current_fit is fit
    assert owner.current_fit_idx == 0
    assert owner.native_session is old_native
    if remote:
        assert owner.current_fit_uid == fit.unique_identifier
        assert owner.project_metadata == {"old": ["metadata"]}
        assert owner.project_path == "/old.cs.pto"
    assert history.events == [{"action_type": "old"}]
    assert history.runtime is old_runtime
    assert history.runtime["cache"] is old_cache
    assert old_cache == ["old"]
    assert history.runtime["lock"] is lock
    assert document.project_id == "old"
    assert document._saved_fingerprint == "old-baseline"
    assert gui._current_project_id == "old"
    assert gui.current_fit is fit
    assert gui._fit_idx == 0


def test_real_inprocess_client_without_convenience_shims_rolls_back(live):
    """The common helper needs only PluginClient.call, even with installed proxies."""
    from chisurf.core.project.transition import replace_project

    curve, history, document, gui = live
    state = SessionState(datasets=[curve])
    state.history = history
    dispatcher = ServiceDispatcher(state)
    dispatcher._build_default_registry()
    register_project_snapshot_services(dispatcher, state)
    client = InProcessClient(dispatcher)
    install_proxies(client)
    original_proxy = cs.imported_datasets
    incoming = capture_session([], [], name="incoming")
    identity = document.stage_file_save(incoming, "/incoming.cs.pto")

    def fail(*args):
        """Reject presentation while owner rollback state is still retained."""
        assert state.datasets == []
        assert state._project_transition is not None
        raise RuntimeError("reject view")

    with pytest.raises(RuntimeError, match="reject view"):
        replace_project(incoming, gui=gui, target_identity=identity, present=fail)
    assert state.datasets[0] is curve
    assert state._project_transition is None
    assert cs.imported_datasets is original_proxy
    assert document.project_id == "old"


def test_document_publication_failure_rolls_back_runtime_and_resource_history(live):
    """A partially mutating identity publisher must not leave new science active."""
    from chisurf.core.project.transition import replace_project

    curve, history, document, gui = live
    incoming = capture_session([], [], name="incoming")
    staged = document.stage_file_save(incoming, "/incoming.cs.pto")

    def fail_adopt(candidate):
        """Simulate a mutating publisher failing after it has changed identity."""
        document.name = candidate.name
        document.project_id = None
        raise RuntimeError("document publication failed")

    document.adopt = fail_adopt
    with pytest.raises(RuntimeError, match="document publication failed"):
        replace_project(incoming, gui=gui, document=document, target_identity=staged)
    assert cs.imported_datasets[0] is curve
    assert history.events == [{"action_type": "old"}]
    assert document.project_id == "old"
    assert document.name == "untitled"
    assert document._saved_fingerprint == "old-baseline"


def test_headless_owner_load_publishes_name_path_and_history(live, tmp_path):
    """A server load with no GUI still commits canonical metadata and history."""
    from chisurf.core.project.storage import save_file
    from chisurf.server.services.projects import get_project_info, load_project

    curve, history, _, _ = live
    state = SessionState(datasets=[curve])
    state.history = history
    project = capture_session([curve], [], name="published")
    project.extra["history_events"] = [{"action_type": "incoming"}]
    path = save_file(project, tmp_path / "published.cs.pto")
    result = load_project(state, str(path))
    assert result["ok"] is True
    assert result["fit_uids"] == []
    assert state.project_name == "published"
    assert state.project_path == str(path)
    assert history.events == [{"action_type": "incoming"}]
    assert get_project_info(state)["project_path"] == str(path)


def test_api_capture_includes_owning_history(live):
    """An explicit API owner must use the same complete capture as server saves."""
    from chisurf.core.api import ChiSurfAPI

    state = SessionState(datasets=[live[0]])
    state.history = live[1]
    api = ChiSurfAPI(state=state, mode="local")
    assert api.capture_project("api-history").extra["history_events"] == live[1].events


def test_macro_presentation_failure_keeps_old_windows(live, monkeypatch):
    """The real macro must propagate construction failure and retain old views."""
    from chisurf.core.fitting.fit import Fit
    from test.project.test_server_project_snapshot import SnapshotLinearModel

    curve, _, _, gui = live
    fit = Fit(data=curve, model_class=SnapshotLinearModel)
    cs.fits.append(fit)
    from qtpy import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    area = QtWidgets.QMdiArea()
    old = area.addSubWindow(QtWidgets.QWidget())
    old.fit = fit
    old.get_project_plot_state = lambda: {"version": 1, "current_plot_index": 0, "plots": []}
    old.set_project_plot_state = lambda state: True
    old.closed = False
    old.show()
    area.show()
    app.processEvents()
    calls = []
    gui._close_all_fit_subwindows = lambda: (setattr(old, "closed", True), calls.append("close"))
    gui.mdiarea = area

    def fail_window(candidate, *, restored=False):
        assert candidate is fit and restored is True
        raise RuntimeError("window failed")

    gui._open_fit_subwindow = fail_window
    with pytest.raises(RuntimeError, match="window failed"):
        core_fit.restore_gui_from_fits([fit.unique_identifier], {"current_fit_index": 0})
    assert old.closed is False
    assert calls == []
    assert old in area.subWindowList()
    area.hide()


def test_actual_inprocess_installed_proxies_can_read_scientific_objects(live):
    """Installed real proxies consume the PluginClient.call contract directly."""
    from chisurf.core.fitting.fit import Fit
    from test.project.test_server_project_snapshot import SnapshotLinearModel

    curve = live[0]
    fit = Fit(data=curve, model_class=SnapshotLinearModel)
    state = SessionState(datasets=[curve], fits=[fit])
    dispatcher = ServiceDispatcher(state)
    dispatcher._build_default_registry()
    register_project_snapshot_services(dispatcher, state)
    install_proxies(InProcessClient(dispatcher))
    assert cs.imported_datasets[0].uid == curve.unique_identifier
    assert cs.fits[0].uid == fit.unique_identifier


def test_close_action_with_native_server_proxies_is_owner_transaction(live):
    """Close must not clear/slice proxy collections or lose authoritative selection."""
    curve, history, document, gui = live
    state = SessionState(datasets=[curve])
    state.history = history
    dispatcher = ServiceDispatcher(state)
    dispatcher._build_default_registry()
    register_project_snapshot_services(dispatcher, state)
    install_proxies(InProcessClient(dispatcher))
    gui._project_document = document
    result = project_actions.close_project._action_spec.handler(gui)
    assert result["ok"] is True
    assert state.datasets == []
    assert state.fits == []
    assert state.current_fit_uid is None
    assert history.events == []
    assert document.project_id is None
    assert document._saved_fingerprint is None


def test_failing_presentation_rollback_still_restores_document_and_gui_identity(live):
    """A broken view disposer cannot interrupt authoritative context rollback."""
    from chisurf.core.project.transition import PreparedPresentation, replace_project

    curve, _, document, gui = live
    project = capture_session([], [], name="incoming")
    staged = document.stage_file_save(project, "/incoming.cs.pto")

    def fail_commit():
        """Fail after document publication."""
        gui.current_fit = "incorrect selection"
        raise RuntimeError("publish failed")

    def fail_rollback():
        """Simulate an independently broken window disposer."""
        raise RuntimeError("disposal failed")

    with pytest.raises(RuntimeError):
        replace_project(
            project,
            gui=gui,
            document=document,
            target_identity=staged,
            present=lambda *args: PreparedPresentation(fail_commit, fail_rollback),
        )
    assert cs.imported_datasets[0] is curve
    assert document.project_id == "old"
    assert document.path is None
    assert gui._current_project_id == "old"
    assert gui.current_fit is None


def test_macro_failure_restores_original_control_visibility(live):
    """Window construction may hide old editors before it fails internally."""
    from qtpy import QtWidgets

    from chisurf.core.fitting.fit import Fit
    from test.project.test_server_project_snapshot import SnapshotLinearModel

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    curve, _, _, gui = live
    fit = Fit(data=curve, model_class=SnapshotLinearModel)
    cs.fits.append(fit)
    host = QtWidgets.QWidget()
    gui.modelLayout = QtWidgets.QVBoxLayout(host)
    editor = QtWidgets.QLabel("Original scientific controls")
    gui.modelLayout.addWidget(editor)
    gui.mdiarea = QtWidgets.QMdiArea()
    host.show()
    app.processEvents()
    assert editor.isVisible()

    def fail_window(candidate, *, restored=False):
        """Represent Main hiding an old editor before construction fails."""
        assert restored is True
        editor.hide()
        raise RuntimeError("editor reconstruction failed")

    gui._open_fit_subwindow = fail_window
    with pytest.raises(RuntimeError, match="editor reconstruction failed"):
        core_fit.restore_gui_from_fits([fit.unique_identifier])
    assert editor.isVisible()
    host.hide()


def test_owner_retains_staged_native_scientific_session(live, monkeypatch):
    """The codec's detached graph lifetime belongs to the installed runtime owner."""
    from chisurf.core.fitting.fit import Fit
    from chisurf.core.project import transition
    from test.project.test_server_project_snapshot import SnapshotLinearModel

    curve = live[0]
    fit = Fit(data=curve, model_class=SnapshotLinearModel)
    project = capture_session([curve], [fit])
    restored = []
    real_restore = transition.restore_session

    def stage(candidate):
        """Observe the real codec result without replacing scientific reconstruction."""
        value = real_restore(candidate)
        restored.append(value)
        return value

    monkeypatch.setattr(transition, "restore_session", stage)
    state = SessionState()
    result = transition.replace_project(project, owner=state)
    assert result["ok"] is True
    assert state.native_session is restored[0].native_session
    assert state.native_session is not None
    state.fits[0].model.slope.value = 4.0
    state.fits[0].model.update()
    np.testing.assert_allclose(state.fits[0].model.y, 2.0 + 4.0 * curve.x)


def test_headless_macro_load_publishes_actual_file_path(live, monkeypatch, tmp_path):
    """Document context is optional, but owner file identity must still be canonical."""
    from chisurf.core.project.storage import save_file

    monkeypatch.setattr(cs, "cs", None)
    path = save_file(capture_session([live[0]], [], name="headless"), tmp_path / "owner.cs.pto")
    result = core_fit.load_project(str(path))
    assert result["ok"] is True
    assert cs.project_path == str(path)
    assert cs.project_name == "headless"
