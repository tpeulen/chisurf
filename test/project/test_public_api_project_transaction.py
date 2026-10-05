"""Public project entrypoints must retain the actual scientific owner on rejection."""

from types import SimpleNamespace

import numpy as np
import pytest

import chisurf as cs
from chisurf.core.api import ChiSurfAPI
from chisurf.core.api._proxies import install_proxies
from chisurf.core.plugin.client import InProcessClient
from chisurf.core.project import capture_session
from chisurf.core.project.lifecycle import ProjectDocument
from chisurf.core.project.storage import save_file
from chisurf.macros import core_fit
from chisurf.server.dispatcher import ServiceDispatcher
from chisurf.server.services.projects import register_project_snapshot_services
from test.project.test_server_project_snapshot import _state_with_real_fit


class PublicClient(InProcessClient):
    """Use actual registered handlers behind the facade's convenience calls."""

    def project__load(self, **params):
        """Load through public RPC."""
        return self.call("project.load", params)

    def session__restore(self, **params):
        """Reset through public RPC."""
        return self.call("session.restore", params)

    def dataset__list(self):
        """Read the actual owner for installed proxies."""
        return self.call("dataset.list")["datasets"]

    def fit__list(self):
        """Read the actual owner for installed proxies."""
        return self.call("fit.list")["fits"]


@pytest.fixture
def public_owner(monkeypatch, tmp_path):
    """Create real fitted science and an independent unrelated global dataset list."""
    state = _state_with_real_fit()
    document = ProjectDocument(name="original", path=tmp_path / "original.cs.pto")
    document._saved_fingerprint = "original baseline"
    calls = []
    gui = SimpleNamespace(
        _guard_project_transition=lambda: calls.append("guard") or False,
        _get_project_document=lambda: document,
        current_fit=state.fits[0],
        _fit_idx=0,
        _current_project_path=document.path,
        _current_project_name=document.name,
    )
    monkeypatch.setattr(cs, "cs", gui)
    monkeypatch.setattr(cs, "imported_datasets", [])
    monkeypatch.setattr(cs, "fits", [])
    monkeypatch.setattr(cs, "__client__", None, raising=False)
    dispatcher = ServiceDispatcher(state)
    dispatcher._build_default_registry()
    register_project_snapshot_services(dispatcher, state)
    client = PublicClient(dispatcher)
    incoming = capture_session([], [], name="incoming")
    path = tmp_path / "incoming.cs.pto"
    save_file(incoming, path)
    return SimpleNamespace(
        state=state,
        gui=gui,
        document=document,
        calls=calls,
        client=client,
        dispatcher=dispatcher,
        incoming=incoming,
        path=path,
    )


def invoke(s, route, operation):
    """Call the actual facade or dispatcher public boundary."""
    if route == "rpc":
        method, params = {
            "payload": ("project.restore_payload", {"project": s.incoming.to_dict()}),
            "load": ("project.load", {"project_path": str(s.path)}),
            "reset": ("session.restore", {}),
            "clear": ("session.clear", {}),
        }[operation]
        return s.dispatcher.dispatch(method, params)
    if route == "proxy":
        install_proxies(s.client)
    api = ChiSurfAPI(
        state=s.state,
        mode="server" if route == "proxy" else route,
        client=s.client if route in ("server", "hybrid", "proxy") else None,
    )
    if operation == "payload":
        return api.restore_project_payload(s.incoming)
    if operation == "load":
        return api.load_project(str(s.path))
    return api.session_restore()


@pytest.mark.parametrize("route", ["local", "hybrid", "server", "proxy", "rpc"])
@pytest.mark.parametrize("operation", ["payload", "load", "reset"])
def test_public_cancellation_precedes_science_mutation(public_owner, route, operation):
    """A false GUI decision preserves exact scientific objects and identity."""
    s = public_owner
    curve, fit = s.state.datasets[0], s.state.fits[0]
    before = dict(s.document.__dict__)
    values = fit.grouped_fits[0].model.y.copy()
    result = invoke(s, route, operation)
    assert result == {"ok": False, "cancelled": True}
    assert s.calls == ["guard"]
    assert s.state.datasets == [curve]
    assert s.state.fits == [fit]
    np.testing.assert_array_equal(fit.grouped_fits[0].model.y, values)
    assert s.document.__dict__ == before
    assert s.gui.current_fit is fit
    assert getattr(s.state, "_project_transition", None) is None


@pytest.mark.parametrize("route", ["local", "hybrid", "server", "proxy", "rpc"])
@pytest.mark.parametrize("operation", ["payload", "load", "reset"])
def test_public_presentation_failure_rolls_back_owner(public_owner, monkeypatch, route, operation):
    """Synchronous GUI failure cannot commit science or document identity."""
    s = public_owner
    curve, fit = s.state.datasets[0], s.state.fits[0]
    before = dict(s.document.__dict__)
    s.gui._guard_project_transition = lambda: s.calls.append("guard") or True

    def fail(*args, **kwargs):
        """Fail only presentation after actual owner staging."""
        assert s.state.datasets == []
        assert s.state.fits == []
        raise RuntimeError("injected presentation failure")

    monkeypatch.setattr(core_fit, "restore_gui_from_fits", fail)
    result = invoke(s, route, operation)
    assert result["ok"] is False
    assert "presentation failure" in result["error"]
    assert s.calls == ["guard"]
    assert s.state.datasets == [curve]
    assert s.state.fits == [fit]
    assert s.document.__dict__ == before
    assert s.gui.current_fit is fit
    assert getattr(s.state, "_project_transition", None) is None


def test_rpc_clear_cannot_bypass_gui_decision(public_owner):
    """The sibling public reset alias must preserve cancellation unchanged."""
    s = public_owner
    curve = s.state.datasets[0]
    assert invoke(s, "rpc", "clear") == {"ok": False, "cancelled": True}
    assert s.calls == ["guard"]
    assert s.state.datasets == [curve]


def test_public_payload_cannot_use_confirmed_rpc_parameter(public_owner):
    """Private owner staging is not a public caller's authorization flag."""
    s = public_owner
    result = s.dispatcher.dispatch(
        "project.restore_payload",
        {
            "project": s.incoming.to_dict(),
            "confirmed": True,
        },
    )
    assert result == {"ok": False, "cancelled": True}
    assert s.calls == ["guard"]
    assert len(s.state.fits) == 1


@pytest.mark.parametrize("save_result", [None, False, {"ok": True}])
def test_public_save_decision_requires_explicit_success(public_owner, save_result):
    """An ambiguous save acknowledgement cannot authorize loss of real science."""
    from chisurf.core.project.lifecycle import SaveDecision, confirm_transition

    s = public_owner
    s.gui._guard_project_transition = lambda: confirm_transition(
        has_content=True,
        prompt=lambda: SaveDecision.SAVE,
        save=lambda: save_result,
    )
    assert invoke(s, "local", "reset") == {"ok": False, "cancelled": True}
    assert len(s.state.fits) == len(s.state.datasets) == 1


def test_macro_public_payload_must_synchronously_present(public_owner, monkeypatch):
    """A public macro payload restore also retains the owner through presentation."""
    s = public_owner
    # Exercise the actual member fit independently of the concurrently owned
    # FitGroup ownership traversal, which has its own unchanged probes above.
    s.state.fits[:] = [s.state.fits[0].grouped_fits[0]]
    monkeypatch.setattr(cs, "fits", s.state.fits)
    monkeypatch.setattr(cs, "imported_datasets", s.state.datasets)
    s.gui._guard_project_transition = lambda: s.calls.append("guard") or True

    def fail(*args, **kwargs):
        """Inject failure at the GUI boundary after real scientific staging."""
        assert cs.fits == []
        raise RuntimeError("macro presentation failure")

    monkeypatch.setattr(core_fit, "restore_gui_from_fits", fail)
    fit = s.state.fits[0]
    with pytest.raises(RuntimeError, match="macro presentation failure"):
        core_fit.load_project_payload(s.incoming, _skip_gui_creation=True)
    assert s.state.fits == [fit]
    assert s.calls == ["guard"]


@pytest.mark.parametrize("operation", ["payload", "reset"])
@pytest.mark.parametrize(
    "decision",
    [
        "cancel",
        "failed-save",
        "failed-publish",
        "unrelated-owner",
        "late-selector",
        "late-ack",
    ],
)
def test_native_main_public_transition_keeps_original_window(
    request,
    tmp_path,
    monkeypatch,
    operation,
    decision,
):
    """Exercise one real Main/native canvas per process, retaining actual windows."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    if os.environ.get("CHISURF_PUBLIC_NATIVE_CHILD") != "1":
        env = os.environ.copy()
        env["CHISURF_PUBLIC_NATIVE_CHILD"] = "1"
        env["CHISURF_SETTINGS_DIR"] = str(tmp_path / "settings")
        env["MMFDB_SETTINGS_DIR"] = str(tmp_path / "mmfdb")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                request.node.nodeid,
                "-q",
                "--tb=short",
                f"--basetemp={tmp_path / 'native'}",
                f"--junitxml={tmp_path / 'native.xml'}",
                "-p",
                "no:cacheprovider",
            ],
            cwd=Path(__file__).resolve().parents[2],
            env=env,
            capture_output=True,
            text=True,
            timeout=90,
        )
        (tmp_path / "native.log").write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stdout + result.stderr
        assert (tmp_path / "native.xml").is_file()
        return

    from qtpy import QtCore, QtWidgets

    import chisurf.gui as cs_gui
    from chisurf.core.project.lifecycle import SaveDecision
    from chisurf.gui.main import Main
    from test.gui.test_tcspc_project_visual_roundtrip import _simulated_fit

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    settings_path = tmp_path / "main.ini"

    class IsolatedSettings(QtCore.QSettings):
        """Keep native Main preferences in the test's scratch directory."""

        def __init__(self, *args, **kwargs):
            """Create the actual settings backend with an isolated file."""
            super().__init__(str(settings_path), QtCore.QSettings.IniFormat)

    monkeypatch.setattr(QtCore, "QSettings", IsolatedSettings)
    monkeypatch.setattr(cs, "fits", [])
    monkeypatch.setattr(cs, "imported_datasets", [])
    monkeypatch.setattr(cs_gui, "fit_windows", [])
    if getattr(cs, "console", None) is None:
        cs.console = cs_gui.widgets.ipython.QIPythonWidget()
        cs.console.history_widget = None
    main = Main()
    monkeypatch.setattr(cs, "cs", main)
    main.resize(1500, 950)
    main.init_setups()
    main.define_actions()
    main.arrange_widgets()
    main.show()
    fit = _simulated_fit()
    cs.fits.append(fit)
    cs.imported_datasets.extend(member.data for member in fit.grouped_fits)
    main._open_fit_subwindow(fit)
    main.dataset_selector.update()
    main.fit_selector.update()
    # Main seeds one built-in Global-fit curve; the two actual member curves
    # must also be visible, rather than hidden inside a filtered DataCurveGroup.
    assert main.dataset_selector.topLevelItemCount() == 3
    curve_index = next(
        i
        for i, curve in enumerate(main.dataset_selector.datasets)
        if curve is fit.grouped_fits[0].data
    )
    main.dataset_selector.setCurrentItem(main.dataset_selector.topLevelItem(curve_index))
    main.onCurrentDatasetChanged()
    assert main.current_dataset is fit.grouped_fits[0].data
    app.processEvents()
    window = main.mdiarea.subWindowList()[0]
    document = main._get_project_document()
    document.name = "original native scientific session"
    document.path = tmp_path / "original.cs.pto"
    main._current_project_path = document.path
    api = ChiSurfAPI(mode="local")
    api._state.current_fit_uid = fit.unique_identifier
    if decision == "unrelated-owner":
        api = ChiSurfAPI(mode="local", state=_state_with_real_fit())
    science_state = api._state
    if decision == "late-ack":
        dispatcher = ServiceDispatcher(science_state)
        dispatcher._build_default_registry()
        register_project_snapshot_services(dispatcher, science_state)
        client = PublicClient(dispatcher)
        actual_call = client.call

        def reject_ack(method, params=None):
            """Reject acknowledgement while executing actual begin and rollback RPCs."""
            if method == "project.transition.finish" and params["commit"] is True:
                return {"ok": False, "error": "late owner acknowledgement failure"}
            return actual_call(method, params)

        monkeypatch.setattr(client, "call", reject_ack)
        api = ChiSurfAPI(mode="server", client=client, state=science_state)
        api.install_proxies()
    owner_fits = list(science_state.fits)
    main.current_fit = fit
    main._fit_idx = 0
    calls = []
    choice = (
        SaveDecision.SAVE
        if decision == "failed-save"
        else (SaveDecision.CANCEL if decision == "cancel" else SaveDecision.DISCARD)
    )
    main._save_decision = lambda: calls.append("decision") or choice
    if decision == "failed-save":
        main._save_project_snapshot = lambda: calls.append("save") or False
    if decision == "failed-publish":

        def fail(staged):
            """Fail a document publication after the real window was staged."""
            assert window not in main.mdiarea.subWindowList()
            assert window.fit is fit
            raise RuntimeError("native document publication failure")

        monkeypatch.setattr(document, "adopt", fail)
    if decision == "late-selector":
        original_update = main.dataset_selector.update

        def reject_selector(*args, **kwargs):
            """Refresh actual rows, alter layout, then inject a late publication failure."""
            original_update(*args, **kwargs)
            main.onCurrentDatasetChanged()
            main.resize(900, 600)
            raise RuntimeError("late selector publication failure")

        monkeypatch.setattr(main.dataset_selector, "update", reject_selector)
    before = dict(document.__dict__)
    datasets = list(science_state.datasets)
    original_dataset = main.current_dataset
    original_size = main.size()
    old_rows = {
        name: [
            tuple(selector.topLevelItem(i).text(column) for column in range(selector.columnCount()))
            for i in range(selector.topLevelItemCount())
        ]
        for name in ("dataset_selector", "fit_selector")
        if (selector := getattr(main, name)) is not None
    }
    arrays = [member.model.y.copy() for member in fit.grouped_fits]
    assert main.grab().save(str(tmp_path / "before.png"))
    incoming = capture_session([], [], name="incoming")
    if decision == "late-ack" and operation == "payload":
        main.resize(900, 600)
        incoming.ui_state["geometry"] = bytes(main.saveGeometry()).hex()
        main.resize(original_size)
    result = (
        api.restore_project_payload(incoming) if (operation == "payload") else api.session_restore()
    )
    app.processEvents()
    assert main.grab().save(str(tmp_path / "after.png"))
    if decision in ("failed-publish", "unrelated-owner", "late-selector", "late-ack"):
        assert result["ok"] is False
        expected_error = {
            "failed-publish": "native document publication failure",
            "unrelated-owner": "not attached",
            "late-selector": "late selector publication failure",
            "late-ack": "late owner acknowledgement failure",
        }[decision]
        assert expected_error in result["error"]
    else:
        assert result == {"ok": False, "cancelled": True}
    assert calls == (
        []
        if decision == "unrelated-owner"
        else ["decision", "save"]
        if decision == "failed-save"
        else ["decision"]
    )
    assert science_state.fits == owner_fits
    assert science_state.datasets == datasets
    assert main.mdiarea.subWindowList() == [window]
    assert window.fit is fit
    assert document.__dict__ == before
    assert main.current_fit is fit
    assert main._fit_idx == 0
    assert main.current_dataset is original_dataset
    assert main.size() == original_size
    for name, rows in old_rows.items():
        selector = getattr(main, name)
        assert [
            tuple(selector.topLevelItem(i).text(column) for column in range(selector.columnCount()))
            for i in range(selector.topLevelItemCount())
        ] == rows
    for member, array in zip(fit.grouped_fits, arrays):
        np.testing.assert_array_equal(member.model.y, array)
    app.processEvents()
    assert main.grab().save(str(tmp_path / "after.png"))
    main.hide()


@pytest.mark.parametrize("route", ["local", "hybrid", "server", "proxy", "rpc"])
def test_headless_public_roundtrip_preserves_actual_scientific_owner(
    public_owner, monkeypatch, route
):
    """Actual headless owners round-trip models, parameters, ranges and curve arrays."""
    s = public_owner
    monkeypatch.setattr(cs, "cs", None)
    original = s.state.fits[0]
    member = original.grouped_fits[0]
    member.fit_range = (1, 3)
    member.model.slope.bounds = (0.1, 8.0)
    member.model.slope.bounds_on = True
    member.model.slope.fixed = True
    member.model.update()
    expected = member.model.y.copy()
    expected_data = member.data.y.copy()
    expected_uid = original.unique_identifier
    api = ChiSurfAPI(state=s.state, mode="local")
    s.incoming = api.capture_project("actual owner")
    member.model.slope.value = 6.0
    member.model.update()
    assert not np.array_equal(member.model.y, expected)
    result = invoke(s, route, "payload")
    assert result["ok"] is True, result
    restored = s.state.fits[0]
    assert restored is not original
    assert restored.unique_identifier == expected_uid
    restored_member = restored.grouped_fits[0]
    assert restored_member.model.slope.value == 3.0
    assert restored_member.model.slope.fixed is True
    assert tuple(restored_member.model.slope.bounds) == (0.1, 8.0)
    assert restored_member.model.slope.bounds_on is True
    assert tuple(restored_member.fit_range) == (1, 3)
    np.testing.assert_array_equal(restored_member.data.y, expected_data)
    restored_member.model.update()
    np.testing.assert_allclose(restored_member.model.y, expected, rtol=1e-12, atol=1e-12)
    assert s.state.current_fit_uid == expected_uid
    assert getattr(s.state, "_project_transition", None) is None
    if route not in ("proxy",):
        assert cs.fits == []
        assert cs.imported_datasets == []


def test_bound_gui_cannot_become_implicit_headless_consent(public_owner, monkeypatch):
    """Losing a process-global pointer must not silently authorize a bound owner."""
    s = public_owner
    api = ChiSurfAPI(mode="local", state=s.state)
    assert api.session_restore() == {"ok": False, "cancelled": True}
    monkeypatch.setattr(cs, "cs", None)
    result = api.session_restore()
    assert s.calls == ["guard", "guard"]
    assert result == {"ok": False, "cancelled": True}
    assert len(s.state.fits) == len(s.state.datasets) == 1


def test_remote_gui_ownership_blocks_direct_headless_public_rpc(public_owner, monkeypatch):
    """A GUI facade's remote owner cannot infer GUI consent from public RPC."""
    s = public_owner
    api = ChiSurfAPI(mode="server", client=s.client, state=s.state)
    assert api.session_restore() == {"ok": False, "cancelled": True}
    monkeypatch.setattr(cs, "cs", None)
    # A separate process would have no Main pointer, while the actual SessionState
    # and real dispatcher remain the owner. Remove only its local presentation
    # callback when present, to model that process boundary explicitly.
    monkeypatch.delattr(s.state, "_project_gui", raising=False)
    for method, params in (
        ("project.restore_payload", {"project": s.incoming.to_dict()}),
        ("project.load", {"project_path": str(s.path)}),
        ("session.restore", {}),
        ("session.clear", {}),
    ):
        result = s.dispatcher.dispatch(method, params)
        assert result["ok"] is False
        assert "GUI" in result["error"]
        assert len(s.state.datasets) == len(s.state.fits) == 1


@pytest.mark.parametrize("resource_only", [False, True], ids=["fitted-science", "attachment-only"])
def test_actual_remote_owner_requires_gui_for_all_public_replacement(
    public_owner,
    tmp_path,
    measured_resource,
    resource_only,
):
    """Exercise separate-process ChiSurfServer over its real ZMQ transport."""
    import os
    import subprocess
    import sys
    import time
    from pathlib import Path

    from chisurf.core.api._client import ChisurfClient, RemoteError
    from test.server.helpers import find_free_port

    s = public_owner
    command_port, publication_port = find_free_port(), find_free_port()
    ready = tmp_path / "server.ready"
    script = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[4])
from test.project.test_server_project_snapshot import _state_with_real_fit
from chisurf.server.app import ChiSurfServer
server = ChiSurfServer(cmd_port=int(sys.argv[1]), pub_port=int(sys.argv[2]),
                      state=_state_with_real_fit())
Path(sys.argv[3]).write_text('ready')
server.serve_forever()
"""
    env = os.environ.copy()
    env["CHISURF_SETTINGS_DIR"] = str(tmp_path / "remote-settings")
    env["MMFDB_SETTINGS_DIR"] = str(tmp_path / "remote-mmfdb")
    client = None
    with (tmp_path / "remote.log").open("w") as output:
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                script,
                str(command_port),
                str(publication_port),
                str(ready),
                str(Path(__file__).resolve().parents[2]),
            ],
            cwd=Path(__file__).resolve().parents[2],
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 30
            while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
            assert ready.exists(), (tmp_path / "remote.log").read_text()
            client = ChisurfClient(cmd_port=command_port, pub_port=publication_port)
            client.connect()
            if resource_only:
                s.incoming.resources = measured_resource
                assert (
                    client.call(
                        "project.restore_payload",
                        {
                            "project": s.incoming.to_dict(),
                            "resources": measured_resource.to_transport_dict(),
                        },
                    )["ok"]
                    is True
                )
                captured = ChiSurfAPI(mode="server", client=client).capture_project()
                assert captured.resources.entries == measured_resource.entries
                assert captured.resources.sources == measured_resource.sources
            envelope = client.call("project.capture")
            before = envelope["project"]
            api = ChiSurfAPI(mode="server", client=client)
            assert api.session_restore() == {"ok": False, "cancelled": True}
            for method, params in (
                ("project.restore_payload", {"project": s.incoming.to_dict()}),
                ("project.load", {"project_path": str(s.path)}),
                ("session.restore", {}),
                ("session.clear", {}),
            ):
                with pytest.raises(RemoteError, match="owning GUI"):
                    client.call(method, params)
                after_envelope = client.call("project.capture")
                after = after_envelope["project"]
                # Capture timestamps are bookkeeping, while all science and
                # presentation identifiers must remain exactly the same.
                assert after["datasets"] == before["datasets"]
                assert after["fits"] == before["fits"]
                assert after["ui"] == before["ui"]
                assert after_envelope["resources"] == envelope["resources"]
        finally:
            try:
                if client is not None:
                    client.close()
            finally:
                process.terminate()
                process.wait(timeout=10)


def test_remote_directory_load_stages_resolved_archive_identity(public_owner, monkeypatch):
    """The server resolves directory aliases before GUI document staging."""
    s = public_owner
    expected = s.path.parent / "project.cs.pto"
    save_file(s.incoming, expected)
    s.gui._guard_project_transition = lambda: True
    staged_paths = []
    original_stage = s.document.stage_file_save

    def stage(project, path):
        """Observe actual document validation rather than replace its result."""
        staged_paths.append(path)
        return original_stage(project, path)

    monkeypatch.setattr(s.document, "stage_file_save", stage)
    api = ChiSurfAPI(mode="server", client=s.client, state=s.state)
    api.load_project(str(s.path.parent))
    assert staged_paths == [str(expected)]


def test_api_capture_retains_empty_owner_resource_context(monkeypatch):
    """Named attachment bytes belong to the owner even with no fitted datasets."""
    from chisurf.core.project.project import ResourceContext
    from chisurf.server.session import SessionState

    monkeypatch.setattr(cs, "cs", None)
    state = SessionState()
    state.project_resources = ResourceContext(
        {"attachments/label.pdb": b"owned original resource"},
        {"original-label.pdb": b"owned original resource"},
    )
    project = ChiSurfAPI(mode="local", state=state).capture_project()
    assert project.resources.entries == state.project_resources.entries
    assert project.resources.sources == state.project_resources.sources


def test_local_payload_keeps_canonical_project_owned_resources(monkeypatch):
    """Local payload replacement must not strip the Project's non-DTO context."""
    from chisurf.core.project.project import ResourceContext
    from chisurf.server.session import SessionState

    monkeypatch.setattr(cs, "cs", None)
    project = capture_session([], [], name="resource-only")
    project.resources = ResourceContext({"attachments/model.pdb": b"exact attachment"})
    state = SessionState()
    result = ChiSurfAPI(mode="local", state=state).restore_project_payload(project)
    assert result["ok"] is True, result
    assert state.project_resources.entries == project.resources.entries


@pytest.fixture
def measured_resource(tmp_path):
    """Retain checked-in measured protein coordinates after the source disappears."""
    from pathlib import Path

    from chisurf.core.project.project import ResourceContext

    content = (
        Path(__file__).resolve().parents[1] / "data/atomic_coordinates/pdb_files/148l.pdb"
    ).read_bytes()
    source = tmp_path / "original-148l.pdb"
    source.write_bytes(content)
    context = ResourceContext({"attachments/148l.pdb": content}, {str(source): content})
    source.unlink()
    assert not source.exists()
    return context


@pytest.mark.parametrize("route", ["local", "hybrid", "server", "proxy", "rpc"])
def test_public_payload_and_capture_retain_attachment_only_resources(
    public_owner,
    monkeypatch,
    route,
    measured_resource,
):
    """The explicit RPC resource context survives without curves to infer it from."""
    s = public_owner
    monkeypatch.setattr(cs, "cs", None)
    s.incoming.resources = measured_resource
    if route == "rpc":
        result = s.dispatcher.dispatch(
            "project.restore_payload",
            {
                "project": s.incoming.to_dict(),
                "resources": s.incoming.resources.to_transport_dict(),
            },
        )
    else:
        result = invoke(s, route, "payload")
    assert result["ok"] is True, result
    assert s.state.fits == s.state.datasets == []
    assert s.state.project_resources.entries == s.incoming.resources.entries
    assert s.state.project_resources.sources == s.incoming.resources.sources
    if route in ("server", "proxy", "rpc"):
        captured = ChiSurfAPI(mode="server", client=s.client, state=s.state).capture_project()
    else:
        captured = ChiSurfAPI(mode=route, state=s.state).capture_project()
    assert captured.resources.entries == s.incoming.resources.entries
    assert captured.resources.sources == s.incoming.resources.sources


def test_private_remote_owner_staging_retains_resource_identity_on_rollback(public_owner):
    """Begin validates owned byte context and finish restores the exact old context."""
    from chisurf.core.project.project import ResourceContext

    s = public_owner
    original = ResourceContext({"attachments/original.pdb": b"original owner attachment"})
    incoming = ResourceContext({"attachments/incoming.pdb": b"incoming owner attachment"})
    s.state.project_resources = original
    result = s.client.call(
        "project.transition.begin",
        {
            "project": s.incoming.to_dict(),
            "resources": incoming.to_transport_dict(),
        },
    )
    assert result["ok"] is True, result
    assert s.state.project_resources.entries == incoming.entries
    assert s.client.call(
        "project.transition.finish",
        {
            "transaction_id": result["transaction_id"],
            "commit": False,
        },
    ) == {"ok": True}
    assert s.state.project_resources is original


def test_remote_gui_private_transaction_transports_canonical_resources(public_owner, monkeypatch):
    """The GUI facade carries resources through the same staged owner protocol."""
    from chisurf.core.project.project import ResourceContext

    s = public_owner
    s.incoming.resources = ResourceContext({"attachments/incoming.pdb": b"incoming resource"})
    s.gui._guard_project_transition = lambda: True

    # Fault injection observes the actual owner before rejecting presentation.
    def inspect_owner(*args, **kwargs):
        """Reject after requiring complete staged science and resource bytes."""
        assert s.state.project_resources.entries == s.incoming.resources.entries
        raise RuntimeError("resource presentation rejected")

    monkeypatch.setattr(core_fit, "restore_gui_from_fits", inspect_owner)
    original = ResourceContext({"attachments/original.pdb": b"original resource"})
    s.state.project_resources = original
    result = invoke(s, "server", "payload")
    assert result["ok"] is False
    assert "resource presentation rejected" in result["error"]
    assert s.state.project_resources is original


@pytest.mark.parametrize("method", ["project.restore_payload", "project.transition.begin"])
@pytest.mark.parametrize(
    "invalid",
    [
        {"entries": {"../outside": "aGVsbG8="}, "sources": {}},
        {"entries": {"attachments/file": "not base64"}, "sources": {}},
        {"entries": {}, "sources": {"source": 5}},
    ],
)
def test_rpc_invalid_resource_context_preserves_exact_owner(
    public_owner,
    monkeypatch,
    method,
    invalid,
    measured_resource,
):
    """Malformed or unsafe byte contexts fail before the actual owner is changed."""
    s = public_owner
    monkeypatch.setattr(cs, "cs", None)
    s.state.project_resources = measured_resource
    curve, fit = s.state.datasets[0], s.state.fits[0]
    result = s.dispatcher.dispatch(
        method,
        {
            "project": s.incoming.to_dict(),
            "resources": invalid,
        },
    )
    assert result["ok"] is False
    assert s.state.datasets == [curve]
    assert s.state.fits == [fit]
    assert s.state.project_resources is measured_resource
    assert getattr(s.state, "_project_transition", None) is None


def test_failed_public_session_restore_publishes_no_success_event(public_owner, monkeypatch):
    """A denied public restore cannot announce that the original science was replaced."""
    from chisurf.server.eventbus import InProcessEventBus
    from chisurf.server.services.session_svc import session_restore

    s = public_owner
    bus = InProcessEventBus()
    events = []
    bus.subscribe("session.restored", events.append)
    assert session_restore(s.state, event_bus=bus) == {"ok": False, "cancelled": True}
    assert events == []
    monkeypatch.setattr(cs, "cs", None)
    monkeypatch.delattr(s.state, "_project_gui")
    result = session_restore(
        s.state, project_path=str(s.path.parent / "missing.cs.pto"), event_bus=bus
    )
    assert result["ok"] is False
    assert events == []


def test_api_proxy_install_retains_actual_gui_owner(public_owner, monkeypatch):
    """Installing proxies cannot discard the API's live presentation context."""
    s = public_owner
    api = ChiSurfAPI(mode="server", client=s.client, state=s.state)
    api.install_proxies()
    monkeypatch.setattr(cs, "cs", None)
    result = api.session_restore()
    assert result == {"ok": False, "cancelled": True}
    assert s.calls == ["guard"]
    assert len(s.state.fits) == len(s.state.datasets) == 1


def test_hybrid_reset_targets_local_api_owner_not_connected_server(public_owner, monkeypatch):
    """A hybrid client connection cannot redirect reset to an unrelated live session."""
    s = public_owner
    monkeypatch.setattr(cs, "cs", None)
    remote = _state_with_real_fit()
    curve, fit = remote.datasets[0], remote.fits[0]
    remote_dispatcher = ServiceDispatcher(remote)
    remote_dispatcher._build_default_registry()
    register_project_snapshot_services(remote_dispatcher, remote)
    remote_client = PublicClient(remote_dispatcher)
    api = ChiSurfAPI(mode="hybrid", client=remote_client, state=s.state)
    result = api.session_restore()
    assert result["ok"] is True, result
    assert s.state.datasets == s.state.fits == []
    assert remote.datasets == [curve]
    assert remote.fits == [fit]
    assert remote.current_fit_uid == fit.unique_identifier
    assert cs.fits == cs.imported_datasets == []
