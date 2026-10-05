"""Ordinary project capture retains real client-owned views with owned science."""

from types import SimpleNamespace

import numpy as np
import pytest

import chisurf as cs
from chisurf.core.api import ChiSurfAPI
from chisurf.core.api._proxies import ProxyDatasetList, ProxyFitList
from chisurf.core.data import DataCurve
from chisurf.core.fitting.fit import Fit
from chisurf.core.models.parse.parse import ParseModel
from chisurf.core.plugin.client import InProcessClient
from chisurf.core.project import storage
from chisurf.core.project.project import ResourceContext
from chisurf.core.project.session import capture_session
from chisurf.core.project.ui_state import ProjectUIStateError, get_ui_state
from chisurf.history.core import OperationHistory
from chisurf.macros.core_fit import get_project_payload, save_project
from chisurf.server.dispatcher import ServiceDispatcher
from chisurf.server.session import SessionState


@pytest.fixture(params=["local", "inprocess-proxies"])
def real_view_owner(request, qtbot, monkeypatch):
    """Use production controller/plot widgets; proxy science is a real service."""
    from qtpy import QtWidgets

    from chisurf.gui.widgets.fitting import fitting_client
    from chisurf.gui.widgets.fitting.fit_controller import FittingControllerWidget
    from chisurf.gui.widgets.fitting.fit_subwindow import FitSubWindow

    curve = DataCurve(
        x=np.arange(12.0),
        y=3 * np.arange(12.0) + 2,
        name="synthetic linear view-capture control",
    )
    curve.ex = np.ones(12)
    curve.ey = np.ones(12)
    fit = Fit(data=curve, model_class=ParseModel)
    fit.fit_range = (1, 10)
    fit.model.func = "a*x+b"
    fit.model.parameters_all_dict["a"].value = 3.0
    fit.model.parameters_all_dict["b"].value = 2.0
    fit.model.update()
    history = OperationHistory()
    resources = ResourceContext(entries={"fixture/retained.txt": b"synthetic portable note"})
    monkeypatch.setattr(cs, "__client__", None, raising=False)
    monkeypatch.setattr(cs, "api", None, raising=False)
    monkeypatch.setattr(cs, "cs", None, raising=False)
    monkeypatch.setattr(cs, "history", history, raising=False)
    monkeypatch.setattr(cs, "project_resources", resources, raising=False)
    monkeypatch.setattr(cs, "imported_datasets", [curve])
    monkeypatch.setattr(cs, "fits", [fit])
    monkeypatch.setattr(cs, "current_fit_idx", 0, raising=False)
    monkeypatch.setattr(cs, "_project_gui", None, raising=False)
    monkeypatch.setattr(cs, "_project_authorizations", {}, raising=False)
    monkeypatch.setattr(fitting_client, "_FITTING_CLIENT", None)
    main = QtWidgets.QMainWindow()
    main.mdiarea = QtWidgets.QMdiArea(main)
    main.setCentralWidget(main.mdiarea)
    main.fit_idx = 0
    main._current_project_path = "unchanged-before-capture"
    qtbot.addWidget(main)
    controller = FittingControllerWidget(fit=fit)
    controls_host = QtWidgets.QWidget()
    qtbot.addWidget(controls_host)
    controls = QtWidgets.QVBoxLayout(controls_host)
    window = FitSubWindow(fit=fit, control_layout=controls, fit_widget=controller)
    main.mdiarea.addSubWindow(window)
    main.resize(900, 650)
    main.show()
    window.show()
    window.ensure_plot_created(0)
    window.refresh_current_plot()
    QtWidgets.QApplication.processEvents()
    expected_ui = get_ui_state(main)
    assert expected_ui["fit_windows"][fit.unique_identifier]
    monkeypatch.setattr(cs, "cs", main)
    monkeypatch.setattr(cs, "_project_gui", main)
    client = None
    if request.param == "inprocess-proxies":
        state = SessionState(datasets=[curve], fits=[fit])
        state.current_fit_uid = fit.unique_identifier
        setattr(state, "history", history)
        setattr(state, "project_resources", resources)
        dispatcher = ServiceDispatcher(state)
        dispatcher._build_default_registry()
        from chisurf.server.services.projects import register_project_snapshot_services

        register_project_snapshot_services(dispatcher, state)

        class RecordingClient(InProcessClient):
            def __init__(self, service):
                super().__init__(service)
                self.calls = []

            def call(self, method, params=None, timeout=None):
                self.calls.append(method)
                return super().call(method, params, timeout)

        client = RecordingClient(dispatcher)
        monkeypatch.setattr(cs, "__client__", client)
        monkeypatch.setattr(cs, "imported_datasets", ProxyDatasetList(client))
        monkeypatch.setattr(cs, "fits", ProxyFitList(client))
    reference = capture_session([curve], [fit], resources=resources)
    yield SimpleNamespace(
        main=main,
        window=window,
        curve=curve,
        fit=fit,
        client=client,
        expected_ui=expected_ui,
        reference=reference,
        resources=resources,
    )
    window.close()
    main.close()
    QtWidgets.QApplication.processEvents()


def test_capture_preserves_exact_real_window_state_and_science(real_view_owner):
    owner = real_view_owner
    project = get_project_payload("complete-view")
    assert project.ui_state["fit_windows"] == owner.expected_ui["fit_windows"]
    assert project.ui_state["active_tabs"] == owner.expected_ui["active_tabs"]
    assert project.ui_state["current_fit_index"] == 0
    assert project.datasets == owner.reference.datasets
    assert project.fits == owner.reference.fits
    assert dict(project.resources.entries) == dict(owner.resources.entries)
    if owner.client is not None:
        assert "project.capture" in owner.client.calls
        assert project.ui_state["current_fit_uid"] == owner.fit.unique_identifier
    project.ui_state["fit_windows"].clear()
    assert get_ui_state(owner.main)["fit_windows"] == owner.expected_ui["fit_windows"]


def test_api_capture_uses_same_owned_view_contract(real_view_owner):
    owner = real_view_owner
    state = SessionState(datasets=[owner.curve], fits=[owner.fit])
    state._project_gui = owner.main
    state.history = cs.history
    state.project_resources = owner.resources
    api = ChiSurfAPI(client=owner.client, mode="server" if owner.client else "local", state=state)
    project = api.capture_project("api-view")
    assert project.ui_state["fit_windows"] == owner.expected_ui["fit_windows"]
    assert project.ui_state["active_tabs"] == owner.expected_ui["active_tabs"]
    assert project.ui_state["current_fit_index"] == 0
    assert project.datasets == owner.reference.datasets
    assert project.fits == owner.reference.fits
    assert dict(project.resources.entries) == dict(owner.resources.entries)
    assert project.extra["history_state"] == cs.history.export_state()


def test_normal_macro_save_reads_back_complete_real_views(real_view_owner, tmp_path):
    owner = real_view_owner
    path = save_project(str(tmp_path / "view-owned.cs.pto"))
    restored = storage.load_file(path)
    assert restored.ui_state["fit_windows"] == owner.expected_ui["fit_windows"]
    assert restored.datasets == owner.reference.datasets
    assert restored.fits == owner.reference.fits
    assert dict(restored.resources.entries) == dict(owner.resources.entries)


def test_failed_real_view_capture_cannot_replace_old_file(
    real_view_owner,
    monkeypatch,
    tmp_path,
):
    owner = real_view_owner
    path = storage.save_file(owner.reference, tmp_path / "existing.cs.pto")
    previous = path.read_bytes()

    def fail_capture():
        raise RuntimeError("reached UI capture fault")

    monkeypatch.setattr(owner.window, "get_project_plot_state", fail_capture)
    with pytest.raises(ProjectUIStateError, match="reached UI capture fault"):
        save_project(str(path))
    assert path.read_bytes() == previous
    assert owner.main._current_project_path == "unchanged-before-capture"
    if owner.client is not None:
        assert "project.capture" not in owner.client.calls
    assert owner.fit.data is owner.curve
    assert owner.fit.fit_range == (1, 10)
