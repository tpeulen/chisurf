"""Fresh actual Main probes for restoration and retired-view lifetimes."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "scenario",
    [
        "refresh-failure",
        "dispose",
        "macro-refresh-failure",
        "macro-dispose",
        "resources",
        "rpc-thread",
    ],
)
def test_actual_main_owner_publication(request, tmp_path, monkeypatch, scenario):
    """A native Main must protect the document through publication and cleanup."""
    if os.environ.get("CHISURF_OWNER_PUBLICATION_CHILD") != "1":
        env = os.environ.copy()
        env["CHISURF_OWNER_PUBLICATION_CHILD"] = "1"
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
            timeout=120,
        )
        (tmp_path / "native.log").write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stdout + result.stderr
        assert (tmp_path / "native.xml").is_file()
        return

    from qtpy import QtCore, QtWidgets, sip

    import chisurf as cs
    import chisurf.gui as cs_gui
    from chisurf.core.api import ChiSurfAPI
    from chisurf.core.project.lifecycle import SaveDecision
    from chisurf.core.project.project import ResourceContext
    from chisurf.gui.main import Main
    from chisurf.gui.plots.lineplot.lineplot import LinePlot
    from chisurf.gui.widgets.fitting import FitSubWindow
    from test.gui.test_tcspc_project_visual_roundtrip import _simulated_fit

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    class IsolatedSettings(QtCore.QSettings):
        """Use only this test's real native INI preferences."""

        def __init__(self, *args, **kwargs):
            """Construct the isolated settings store."""
            super().__init__(str(tmp_path / "main.ini"), QtCore.QSettings.IniFormat)

    monkeypatch.setattr(QtCore, "QSettings", IsolatedSettings)
    monkeypatch.setattr(cs, "fits", [])
    monkeypatch.setattr(cs, "imported_datasets", [])
    monkeypatch.setattr(cs, "__client__", None, raising=False)
    monkeypatch.setattr(cs, "project_resources", ResourceContext(), raising=False)
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
    document = main._get_project_document()
    if scenario == "resources":
        resources = ResourceContext({"attachments/owned.pdb": b"owned attachment"})
        cs.project_resources = resources
        cs.imported_datasets[:] = []
        assert main._project_has_content() is True
        calls = []
        monkeypatch.setattr(
            main, "_save_decision", lambda: calls.append("decision") or SaveDecision.CANCEL
        )
        assert main._guard_project_transition() is False
        monkeypatch.setattr(
            main, "_save_decision", lambda: calls.append("decision") or SaveDecision.SAVE
        )
        monkeypatch.setattr(main, "_save_project_snapshot", lambda: calls.append("save") or False)
        before = dict(document.__dict__)
        assert main._guard_project_transition() is False
        assert calls == ["decision", "decision", "save"]
        assert document.__dict__ == before
        assert cs.project_resources is resources
        assert main.grab().save(str(tmp_path / "resource-only.png"))
        main.hide()
        return

    if scenario == "rpc-thread":
        import threading

        from chisurf.core.data import DataCurve
        from chisurf.core.project import capture_session
        from chisurf.server.dispatcher import ServiceDispatcher
        from chisurf.server.services.projects import register_project_snapshot_services

        curve = DataCurve(x=[0.0], y=[7.0])
        cs.imported_datasets[:] = [curve]
        api = ChiSurfAPI(mode="local")
        assert getattr(api._state, "_project_gui", None) is None
        original_thread = main.thread
        thread_queries = []

        def observe_thread():
            """Record actual QObject queries from the isolated RPC worker."""
            thread_queries.append(threading.current_thread())
            return original_thread()

        monkeypatch.setattr(main, "thread", observe_thread)
        dispatcher = ServiceDispatcher(api._state)
        register_project_snapshot_services(dispatcher, api._state)
        results = []
        worker = threading.Thread(
            target=lambda: results.append(
                dispatcher.dispatch(
                    "project.transition.begin",
                    {"project": capture_session([], []).to_dict()},
                )
            )
        )
        worker.start()
        worker.join(30)
        assert not worker.is_alive()
        assert results[0]["ok"] is False
        assert "GUI thread" in results[0]["error"]
        assert thread_queries == []
        assert api._state.datasets == [curve]
        assert api._state.fits == []
        assert main.grab().save(str(tmp_path / "rpc-thread.png"))
        main.hide()
        return
    fit = _simulated_fit()
    from chisurf.core.experiments.tcspc.reader import TCSPCReader

    experiment = cs.experiment["TCSPC"]
    reader = TCSPCReader(record_provenance=False)
    experiment.add_reader(reader)
    for member in fit.grouped_fits:
        member.data.experiment = experiment
        member.data.data_reader = reader
    cs.fits.append(fit)
    cs.imported_datasets.extend(member.data for member in fit.grouped_fits)
    main._open_fit_subwindow(fit)
    main.dataset_selector.update()
    main.fit_selector.update()
    app.processEvents()
    window = main.mdiarea.subWindowList()[0]
    original_plot_state = window.get_project_plot_state()
    plot = next(p for p in window._created_plots if isinstance(p, LinePlot))
    controller = plot.plot_controller
    old_controls = [
        layout.itemAt(i).widget()
        for layout in (main.modelLayout, main.analysisHeaderLayout, main.plotOptionsLayout)
        for i in range(layout.count())
        if layout.itemAt(i).widget() is not None
    ]
    timer = QtCore.QTimer(plot)
    timer.start(10000)
    api = ChiSurfAPI(mode="local")
    api._state.current_fit_uid = fit.unique_identifier
    incoming = api.capture_project("actual native roundtrip")
    if scenario.startswith("macro-"):
        from chisurf.macros.core_fit import get_project_payload

        incoming = get_project_payload("actual native roundtrip")
    import chisurf.core.project.transition as transition_module

    dump_json = transition_module.json.dumps
    fingerprints = []

    def observe_fingerprint(value, *args, **kwargs):
        """Retain exact source-observation payloads for failure diagnosis."""
        result = dump_json(value, *args, **kwargs)
        if isinstance(value, dict) and "objects" in value and "links" in value:
            fingerprints.append(result)
            (tmp_path / f"owner-content-{len(fingerprints)}.json").write_text(result)
        return result

    monkeypatch.setattr(transition_module.json, "dumps", observe_fingerprint)
    before = dict(document.__dict__)
    monkeypatch.setattr(main, "_save_decision", lambda: SaveDecision.DISCARD)
    assert main.grab().save(str(tmp_path / "before.png"))
    if scenario.endswith("refresh-failure"):

        def fail_refresh(self):
            """Reject the actual restored window after it has been installed."""
            raise RuntimeError("actual restored refresh failure")

        monkeypatch.setattr(FitSubWindow, "refresh_current_plot", fail_refresh)
        if scenario.startswith("macro-"):
            from chisurf.macros.core_fit import load_project_payload

            with pytest.raises(RuntimeError, match="actual restored refresh failure"):
                load_project_payload(incoming)
        else:
            result = api.restore_project_payload(incoming)
            assert result["ok"] is False, result
            assert "actual restored refresh failure" in result["error"]
        assert api._state.fits == [fit]
        assert main.mdiarea.subWindowList() == [window]
        assert main.current_fit is fit
        assert document.__dict__ == before
        assert window.get_project_plot_state() == original_plot_state
        assert not sip.isdeleted(controller)
        assert timer.isActive()
    else:
        if scenario.startswith("macro-"):
            from chisurf.macros.core_fit import load_project_payload

            result = load_project_payload(incoming)
        else:
            result = api.restore_project_payload(incoming)
        assert result["ok"] is True, result
        assert main.mdiarea.subWindowList()[0] is not window
        app.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        app.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        assert sip.isdeleted(window)
        assert sip.isdeleted(plot)
        assert sip.isdeleted(timer)
        assert sip.isdeleted(controller)
        assert all(sip.isdeleted(widget) for widget in old_controls)
        assert len(api._state.fits) == 1
    app.processEvents()
    assert main.grab().save(str(tmp_path / "after.png"))
    main.hide()
