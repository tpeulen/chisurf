"""Real owner reset regressions at the existing Qt presentation boundary."""

import copy
from types import SimpleNamespace

import numpy as np
import pytest
from qtpy import QtWidgets

import chisurf as cs
import chisurf.gui as cs_gui
from chisurf.core.api._proxies import install_proxies
from chisurf.core.data import DataCurve
from chisurf.core.fitting.fit import Fit
from chisurf.core.plugin.client import InProcessClient
from chisurf.core.project.lifecycle import ProjectDocument, SaveDecision
from chisurf.gui.main import Main
from chisurf.gui.main_helper import ProjectMixin, SetupMixin
from chisurf.history.core import OperationHistory
from chisurf.macros import core_fit
from chisurf.server.dispatcher import ServiceDispatcher
from chisurf.server.services.projects import register_project_snapshot_services
from chisurf.server.session import SessionState
from test.project.test_server_project_snapshot import SnapshotLinearModel


class ResetHost(QtWidgets.QWidget, ProjectMixin, SetupMixin):
    """Real Qt resources with the production lifecycle and close methods."""

    onCloseAllFits = Main.onCloseAllFits
    _close_all_fit_subwindows = Main._close_all_fit_subwindows

    def __init__(self):
        """Create the MDI area and the three production analysis layouts."""
        super().__init__()
        self.setWindowTitle("Reset transaction scientific controls")
        layout = QtWidgets.QVBoxLayout(self)
        self.mdiarea = QtWidgets.QMdiArea(self)
        layout.addWidget(self.mdiarea)
        self.modelLayout = QtWidgets.QVBoxLayout()
        self.analysisHeaderLayout = QtWidgets.QVBoxLayout()
        self.plotOptionsLayout = QtWidgets.QVBoxLayout()
        for controls in (self.modelLayout, self.analysisHeaderLayout, self.plotOptionsLayout):
            layout.addLayout(controls)
        self.editor = QtWidgets.QLabel("Existing model: slope = 4, intercept = 2")
        self.modelLayout.addWidget(self.editor)
        self.comboBox_experimentSelect = QtWidgets.QComboBox()
        self.comboBox_experimentSelect.addItems(["TCSPC", "FCS"])
        self.comboBox_setupSelect = QtWidgets.QComboBox()
        self.comboBox_setupSelect.addItem("CSV/PQ/IBH")
        layout.addWidget(self.comboBox_experimentSelect)
        layout.addWidget(self.comboBox_setupSelect)
        self.current_experiment = SimpleNamespace(name="TCSPC")
        self.current_setup = SimpleNamespace(name="CSV/PQ/IBH")
        self._current_experiment_idx = self._current_setup_idx = 0
        self._fit_idx = 0
        self.dataset_selector = QtWidgets.QTreeWidget()
        self.fit_selector = QtWidgets.QTreeWidget()
        self.errors = []

    def add_recent_project(self, path):
        """Keep this reset test independent of recent-menu persistence."""


def _container_identities(value, path=()):
    """Retain each canonical nested container at its exact address for rollback."""
    if isinstance(value, dict):
        yield path, value
        for key, child in value.items():
            yield from _container_identities(child, (*path, key))
    elif isinstance(value, list):
        yield path, value
        for index, child in enumerate(value):
            yield from _container_identities(child, (*path, index))


@pytest.fixture(params=[False, True], ids=["local", "server-proxies"])
def reset_session(request, monkeypatch, qtbot, tmp_path):
    """Install real science and real server services, retaining resource identity."""
    curve = DataCurve(
        x=np.arange(64.0),
        y=2.0 + 4.0 * np.arange(64.0),
        ex=np.ones(64),
        ey=np.ones(64),
        name="old-science",
    )
    fit = Fit(data=curve, model_class=SnapshotLinearModel)
    fit.fit_range = (5, 41)
    fit.model.slope.value = 4.0
    fit.model.update()
    history = OperationHistory()
    history.record(
        "dataset.add",
        "Load old science",
        {"filename": "old-science"},
        target_uid=curve.unique_identifier,
        persist=False,
    )
    from chisurf.core.project.session import capture_session

    history.set_checkpoint_capture(lambda: capture_session([curve], [fit]).to_dict())
    assert history.create_checkpoint(0) is True
    history.validate_state(history.export_state())
    import IMP.bff as bff

    old_native = bff.get_session()
    for name, value in (
        ("imported_datasets", [curve]),
        ("fits", [fit]),
        ("history", history),
        ("current_fit", fit),
        ("current_fit_idx", 0),
        ("current_fit_uid", fit.unique_identifier),
        ("native_session", old_native),
        ("project_metadata", {"old": ["metadata"]}),
        ("project_path", str(tmp_path / "old.cs.pto")),
        ("project_name", "old"),
        ("current_experiment", "TCSPC"),
        ("current_setup", "CSV/PQ/IBH"),
        ("_project_transition", None),
        ("__client__", None),
        ("_project_gui", None),
        ("_project_authorizations", {}),
    ):
        monkeypatch.setattr(cs, name, value, raising=False)
    owner = cs
    if request.param:
        owner = SessionState(datasets=[curve], fits=[fit], current_fit_uid=fit.unique_identifier)
        for name in (
            "history",
            "current_fit",
            "current_fit_idx",
            "native_session",
            "project_metadata",
            "project_path",
            "project_name",
            "current_experiment",
            "current_setup",
        ):
            setattr(owner, name, getattr(cs, name))
        dispatcher = ServiceDispatcher(owner)
        dispatcher._build_default_registry()
        register_project_snapshot_services(dispatcher, owner)
        install_proxies(InProcessClient(dispatcher))
    host = ResetHost()
    qtbot.addWidget(host)
    document = ProjectDocument(name="old", path=tmp_path / "old.cs.pto")
    document._saved_fingerprint = "old-baseline"
    host._project_document = document
    host._current_project_path = document.path
    host._current_project_id = host._current_project_version_id = None
    host._current_project_name = "old"
    host.current_fit = fit
    host._current_dataset = curve
    host._current_fit = fit
    window = host.mdiarea.addSubWindow(QtWidgets.QLabel("Live scientific window"))
    window.fit = fit
    window.get_project_plot_state = lambda: {"version": 1, "current_plot_index": 0, "plots": []}
    window.set_project_plot_state = lambda state: True
    plugin = host.mdiarea.addSubWindow(QtWidgets.QLabel("Live plugin window"))
    host.resize(800, 600)
    host.show()
    window.show()
    plugin.show()
    monkeypatch.setattr(cs, "cs", host)
    monkeypatch.setattr(owner, "_project_gui", host, raising=False)
    monkeypatch.setattr(cs_gui, "fit_windows", [window])
    monkeypatch.setattr(
        "chisurf.gui.main_helper.dialogs.error", lambda *args: host.errors.append(args[-1])
    )
    monkeypatch.setattr("chisurf.gui.main_helper.dialogs.warning", lambda *args: None)
    monkeypatch.setattr("chisurf.core.project.storage.select_backend", lambda: "file")
    monkeypatch.setattr(
        "chisurf.gui.main_helper.dialogs.choice",
        lambda *args, **kwargs: SimpleNamespace(key="discard"),
    )
    qtbot.wait(1)
    assert host.grab().save(str(tmp_path / "reset-before.png"))
    snapshot = dict(
        document=document.__dict__.copy(),
        events=history.list_events(),
        event_container=history._events,
        lock=history._lock,
        checkpoints=history._checkpoints,
        checkpoint_identities=list(_container_identities(history._checkpoints)),
        checkpoint_state=copy.deepcopy(history._checkpoints),
        native=old_native,
        datasets=owner.datasets if request.param else owner.imported_datasets,
        fits=owner.fits,
        proxy_datasets=cs.imported_datasets,
        proxy_fits=cs.fits,
        windows=host.mdiarea.subWindowList(),
        registry=list(cs_gui.fit_windows),
    )
    snapshot["owner_path"] = owner.project_path
    snapshot["gui_identity"] = tuple(
        getattr(host, name)
        for name in (
            "_current_project_path",
            "_current_project_id",
            "_current_project_version_id",
            "_current_project_name",
        )
    )
    yield SimpleNamespace(
        host=host,
        owner=owner,
        curve=curve,
        fit=fit,
        history=history,
        document=document,
        window=window,
        plugin=plugin,
        snapshot=snapshot,
        remote=request.param,
    )
    host._guard_project_transition = lambda: True
    host.hide()


def _assert_retained(session):
    """Require original owner containers, science and Qt objects on failure."""
    s = session
    datasets = s.owner.datasets if s.remote else s.owner.imported_datasets
    assert datasets is s.snapshot["datasets"]
    assert datasets == [s.curve]
    assert s.owner.fits is s.snapshot["fits"]
    assert s.owner.fits == [s.fit]
    assert s.owner.current_fit is s.fit
    assert s.owner.current_fit_idx == 0
    assert s.owner.current_fit_uid == s.fit.unique_identifier
    assert s.owner.native_session is s.snapshot["native"]
    assert s.owner.project_metadata == {"old": ["metadata"]}
    assert s.owner.project_path == s.snapshot["owner_path"]
    assert s.owner.project_name == "old"
    assert s.owner.history is s.history
    assert s.history.list_events() == s.snapshot["events"]
    assert s.history._events is s.snapshot["event_container"]
    assert s.history._lock is s.snapshot["lock"]
    assert s.history._checkpoints is s.snapshot["checkpoints"]
    assert s.history._checkpoints == s.snapshot["checkpoint_state"]
    for path, original in s.snapshot["checkpoint_identities"]:
        retained = s.history._checkpoints
        for key in path:
            retained = retained[key]
        assert retained is original, f"Checkpoint container replaced at {path!r}"
    saved_fit = s.history._checkpoints[0]["snapshot"]["fits"][0]
    assert saved_fit["uid"] == s.fit.unique_identifier
    assert saved_fit["members"][0]["uid"] == s.fit.unique_identifier
    assert saved_fit["members"][0]["fit_range"] == [5, 41]
    assert s.document.__dict__ == s.snapshot["document"]
    assert (
        tuple(
            getattr(s.host, name)
            for name in (
                "_current_project_path",
                "_current_project_id",
                "_current_project_version_id",
                "_current_project_name",
            )
        )
        == s.snapshot["gui_identity"]
    )
    assert s.host.current_fit is s.fit
    assert s.host._fit_idx == 0
    assert s.host._current_dataset is s.curve
    assert s.host._current_fit is s.fit
    assert s.host.mdiarea.subWindowList() == s.snapshot["windows"]
    assert s.window.isVisible() and s.plugin.isVisible() and s.host.editor.isVisible()
    assert cs_gui.fit_windows == s.snapshot["registry"]
    assert cs.imported_datasets is s.snapshot["proxy_datasets"]
    assert cs.fits is s.snapshot["proxy_fits"]
    assert tuple(s.fit.fit_range) == (5, 41)
    np.testing.assert_array_equal(s.fit.model.y, 2.0 + 4.0 * s.curve.x)
    from pathlib import Path

    assert s.host.grab().save(str(Path(s.snapshot["owner_path"]).parent / "reset-retained.png"))


@pytest.mark.parametrize("decision", [SaveDecision.CANCEL, SaveDecision.SAVE])
def test_reset_cancel_and_cancelled_save_keep_live_session(reset_session, monkeypatch, decision):
    """Cancel and a cancelled real file chooser authorize no teardown."""
    monkeypatch.setattr(reset_session.host, "_save_decision", lambda: decision)
    if decision == SaveDecision.SAVE:
        reset_session.document.path = None
        reset_session.snapshot["document"] = reset_session.document.__dict__.copy()
        monkeypatch.setattr(QtWidgets.QFileDialog, "getSaveFileName", lambda *a: ("", ""))
    assert reset_session.host.reinitialize(False, False) is False
    _assert_retained(reset_session)


def test_reset_failed_save_keeps_live_session(reset_session, monkeypatch):
    """A real Save boundary failure leaves science, history and windows alive."""
    monkeypatch.setattr(reset_session.host, "_save_decision", lambda: SaveDecision.SAVE)

    def fail_write(*args):
        """Inject the file-system failure at the real save boundary."""
        raise OSError("unwritable destination")

    monkeypatch.setattr("chisurf.core.project.storage.save_file", fail_write)
    assert reset_session.host.reinitialize(False, False) is False
    _assert_retained(reset_session)


def test_reset_failed_presentation_restores_live_session(reset_session, monkeypatch):
    """A failed synchronous presentation rejects the owner replacement."""

    def reject_window(*args):
        """Reject while the old native resources are still retained."""
        raise RuntimeError("window presentation failed")

    monkeypatch.setattr(core_fit, "restore_gui_from_fits", reject_window)
    assert reset_session.host.reinitialize(False, False) is False
    assert "window presentation failed" in reset_session.host.errors[-1]
    _assert_retained(reset_session)


def test_reset_failed_document_publication_restores_live_session(reset_session, monkeypatch):
    """A partially mutating publication must roll back views and the owner."""

    def reject_identity(staged):
        """Fail after modifying one live field to test exact restoration."""
        reset_session.document.name = staged.name
        raise RuntimeError("document publication failed")

    monkeypatch.setattr(reset_session.document, "adopt", reject_identity)
    reset_session.snapshot["document"] = reset_session.document.__dict__.copy()
    assert reset_session.host.reinitialize(False, False) is False
    assert "document publication failed" in reset_session.host.errors[-1]
    _assert_retained(reset_session)


def test_reset_failed_window_publication_restores_live_session(reset_session, monkeypatch):
    """Failure during prepared-window commit also restores the original views."""

    def reject_refresh():
        """Fail on the real selector publication after staging the old windows."""
        raise RuntimeError("selector publication failed")

    monkeypatch.setattr(reset_session.host.dataset_selector, "update", reject_refresh)
    assert reset_session.host.reinitialize(False, False) is False
    assert "selector publication failed" in reset_session.host.errors[-1]
    _assert_retained(reset_session)


@pytest.mark.parametrize("save", [False, True], ids=["dont-save", "save"])
def test_reset_success_installs_empty_science_and_keeps_setup(reset_session, monkeypatch, save):
    """Successful reset empties the real owner while retaining application readers."""
    s = reset_session
    monkeypatch.setattr(
        s.host, "_save_decision", lambda: SaveDecision.SAVE if save else SaveDecision.DISCARD
    )
    assert s.host.reinitialize(False, False) is True
    assert (s.owner.datasets if s.remote else s.owner.imported_datasets) == []
    assert s.owner.fits == []
    assert s.owner.current_fit is None and s.owner.current_fit_idx == -1
    assert s.owner.current_fit_uid is None
    assert s.owner.history is s.history
    assert s.owner.history._lock is s.snapshot["lock"]
    empty_history = s.owner.history.export_state()
    s.owner.history.validate_state(empty_history)
    assert empty_history == {
        "history_version": s.owner.history.HISTORY_VERSION,
        "events": [],
        "cursor": -1,
        "baseline": None,
        "states": [],
        "checkpoints": [],
    }
    assert s.history.list_events() == []
    assert s.document.name == "untitled"
    assert s.document.path is s.document.project_id is s.document.version_id is None
    assert s.document._saved_fingerprint is None
    assert s.host._current_project_path is s.host._current_project_name is None
    assert s.host.current_fit is None and s.host._fit_idx == -1
    assert s.host._current_dataset is s.host._current_fit is None
    assert s.host.mdiarea.subWindowList() == []
    assert cs_gui.fit_windows == []
    assert not s.window.isVisible() and not s.plugin.isVisible() and not s.host.editor.isVisible()
    assert s.host.current_experiment.name == "TCSPC"
    assert s.host.current_setup.name == "CSV/PQ/IBH"
    assert s.owner.current_experiment == "TCSPC" and s.owner.current_setup == "CSV/PQ/IBH"
    assert cs.imported_datasets is s.snapshot["proxy_datasets"]
    assert cs.fits is s.snapshot["proxy_fits"]
    from pathlib import Path

    assert s.host.grab().save(str(Path(s.snapshot["owner_path"]).parent / "reset-empty.png"))
    if save:
        from chisurf.core.project import restore_session
        from chisurf.core.project.storage import load_file

        saved = restore_session(load_file(s.snapshot["document"]["path"]))
        assert len(saved.datasets) == len(saved.fits) == 1
        np.testing.assert_array_equal(saved.datasets[0].y, s.curve.y)
        assert tuple(saved.fits[0].fit_range) == (5, 41)
