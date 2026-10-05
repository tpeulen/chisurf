"""Authoritative server-mode project snapshot and restore contracts."""

from __future__ import annotations

import numpy as np

import chisurf as cs
from chisurf.core.api import ChiSurfAPI
from chisurf.core.api._proxies import ProxyDatasetList, ProxyFitList
from chisurf.core.data import DataCurve
from chisurf.core.fitting.fit import Fit, FitGroup
from chisurf.core.fitting.parameter import FittingParameter
from chisurf.core.models.model import ModelCurve
from chisurf.core.plugin.client import InProcessClient
from chisurf.core.project import Project, capture_session
from chisurf.macros.core_fit import get_project_payload, load_project_payload
from chisurf.server.dispatcher import ServiceDispatcher
from chisurf.server.services.projects import register_project_snapshot_services
from chisurf.server.session import SessionState


class SnapshotLinearModel(ModelCurve):
    name = "SnapshotLinearModel"

    def __init__(self, fit: Fit, **kwargs):
        super().__init__(fit, **kwargs)
        self.offset = FittingParameter(name="offset", value=2.0)
        self.slope = FittingParameter(name="slope", value=3.0)
        self.find_parameters()

    def _update_model(self, **kwargs):
        self.x = np.asarray(self.fit.data.x, dtype=float)
        self.y = float(self.offset.value) + float(self.slope.value) * self.x


class _ProjectInProcessClient(InProcessClient):
    def dataset__list(self):
        return self.call("dataset.list")["datasets"]

    def fit__list(self):
        return self.call("fit.list")["fits"]


def _state_with_real_fit() -> SessionState:
    curve = DataCurve(x=np.arange(4.0), y=np.array([2.0, 5.0, 8.0, 11.0]), name="server")
    fit = FitGroup(data=[curve], model_class=SnapshotLinearModel)
    fit.grouped_fits[0].model.update()
    return SessionState(datasets=[curve], fits=[fit], current_fit_uid=fit.unique_identifier)


def test_proxy_capture_and_restore_use_authoritative_server_session(monkeypatch):
    monkeypatch.setattr(cs, "imported_datasets", cs.imported_datasets)
    monkeypatch.setattr(cs, "fits", cs.fits)
    monkeypatch.setattr(cs, "__client__", getattr(cs, "__client__", None), raising=False)
    state = _state_with_real_fit()
    dispatcher = ServiceDispatcher(state)
    dispatcher._build_default_registry()
    register_project_snapshot_services(dispatcher, state)
    client = _ProjectInProcessClient(dispatcher)
    api = ChiSurfAPI(client=client, mode="server")
    api.install_proxies()

    datasets_proxy = cs.imported_datasets
    fits_proxy = cs.fits
    assert isinstance(datasets_proxy, ProxyDatasetList)
    assert isinstance(fits_proxy, ProxyFitList)

    project = get_project_payload("server-snapshot")
    assert isinstance(project, Project)
    saved_y = np.asarray(next(iter(project.datasets.values()))["arrays"]["y"]["values"])
    saved_parameters = project.fits[0]["members"][0]["model"]["parameters"]
    saved_slope = next(p["value"] for p in saved_parameters if p["name"] == "slope")

    state.datasets[0].y = np.full(4, -1.0)
    state.fits[0].grouped_fits[0].model.slope.value = 99.0
    load_project_payload(project)

    assert cs.imported_datasets is datasets_proxy
    assert cs.fits is fits_proxy
    np.testing.assert_allclose(state.datasets[0].y, saved_y)
    assert state.fits[0].grouped_fits[0].model.slope.value == saved_slope
    assert type(state.fits[0].grouped_fits[0].model) is SnapshotLinearModel
    assert state.current_fit_uid == state.fits[0].unique_identifier


def test_server_restore_rolls_back_every_field_when_commit_listener_fails():
    class FailingList(list):
        def __init__(self, values):
            super().__init__(values)
            self.fail_once = True

        def __setitem__(self, key, value):
            super().__setitem__(key, value)
            if isinstance(key, slice) and self.fail_once:
                self.fail_once = False
                raise RuntimeError("listener rejected datasets")

    state = _state_with_real_fit()
    old_dataset = state.datasets[0]
    old_fit = state.fits[0]
    state.datasets = FailingList(state.datasets)
    state.experiments = {"old": object()}
    state.current_experiment = "old"
    state.current_setup = "setup"
    state.project_metadata = {"source": "old"}
    state.project_path = "/old.cs.pto"
    project = capture_session([], [], name="empty")

    from chisurf.server.services.projects import restore_project_payload

    result = restore_project_payload(state, project.to_dict())

    assert result["ok"] is False
    assert state.datasets == [old_dataset]
    assert state.fits == [old_fit]
    assert list(state.experiments) == ["old"]
    assert state.current_fit_uid == old_fit.unique_identifier
    assert state.current_experiment == "old"
    assert state.current_setup == "setup"
    assert state.project_metadata == {"source": "old"}
    assert state.project_path == "/old.cs.pto"
