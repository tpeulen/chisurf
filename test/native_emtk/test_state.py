from types import SimpleNamespace

from emtk.app import ImApp
from emtk.docking import DockManager, Region

from chisurf.emtk.state import attach_native_state, bind_layout, load_settings, save_settings


def test_native_layout_and_window_size_restore_without_qt(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    docks = DockManager(Region("main"))
    docks.add_window("controls", "Controls", dock="main")
    bind_layout("example", docks)
    docks.hide("controls")
    docks.flush()
    second = DockManager(Region("main"))
    second.add_window("controls", "Controls", dock="main")
    bind_layout("example", second)
    assert not second.window("controls").visible

    app = attach_native_state("window_example", ImApp(lambda: None))
    app.window_resized(900, 650)
    app.close()
    app.close()
    reopened = attach_native_state("window_example", ImApp(lambda: None))
    assert reopened.window_size == (900, 650)
    reopened.close()


def test_native_declared_preferences_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    assert save_settings("example", {"bin_width": 0.032, "mode": "vm"})
    assert load_settings("example") == {"bin_width": 0.032, "mode": "vm"}


def test_native_state_calls_explicit_model_preference_hooks(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    save_settings("preferences", {"zoom": 1.5})
    app = ImApp(lambda: None)
    restored = []
    closed = []
    app.restore_settings = lambda values: restored.append(values)
    app.export_settings = lambda: {"zoom": 2.0}
    app.close = lambda: closed.append(True)
    attach_native_state("preferences", app)
    assert restored == [{"zoom": 1.5}]
    app.close()
    app.close()
    assert closed == [True]
    assert load_settings("preferences") == {"zoom": 2.0}


def test_a_tool_opened_in_the_shell_gets_its_settings_back_but_not_its_files(tmp_path, monkeypatch):
    """Closed and opened again inside ChiSurf: the settings return, the data files do not."""
    from chisurf.emtk.state import strip_data_files

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    saved = {
        "setup_name": "RVZ-MH150",
        "output_format": ".pto",
        "style": {"current_file": "/u/.chisurf/styles/dark.css"},
        "data_root": "/data/records",
        "workflow": {"raw_files": ["/data/m1.ptu", "/data/m2.ptu"], "burst_folder": "/data/m1.pto"},
        "batch": [{"name": "a", "path": "/data/a.dat"}, {"name": "b"}],
        "input": "photons:/data/m1.ptu",
        "link": "mmfdb://store/x",
    }
    assert strip_data_files(saved) == {
        "setup_name": "RVZ-MH150",
        "output_format": ".pto",
        "style": {"current_file": "/u/.chisurf/styles/dark.css"},
        "data_root": "/data/records",
        "workflow": {"raw_files": []},
        "batch": [{"name": "b"}],
    }
    save_settings("tool", saved)
    restored = []
    app = SimpleNamespace(restore_settings=restored.append, export_settings=lambda: saved)
    attach_native_state("tool", app, restore_files=False)
    assert restored == [strip_data_files(saved)]


def test_a_run_inside_a_container_is_data_and_does_not_come_back():
    """A burst run is addressed *inside* its container (``m000.pto/<run>``): that is a data
    reference as much as the container is, so a reopened tool does not get it back."""
    from chisurf.emtk.state import is_data_reference, strip_data_files

    run = "/tmp/chisurf-analysis/1-x/uid/DNA13bp_3.pto/cusum_sprt_All 0.1500#5"
    assert is_data_reference(run)
    assert is_data_reference(run + "/bi4_bur/DNA13bp_3.bur")
    assert not is_data_reference("pto")  # an output-format choice
    assert not is_data_reference("/settings/setups/RVZMT150")
    saved = {"workflow": {"burst_folder": run, "bur_files": [run], "setup_name": "RVZMT150"}}
    assert strip_data_files(saved) == {"workflow": {"bur_files": [], "setup_name": "RVZMT150"}}


def test_a_new_burst_analysis_starts_without_the_last_runs_results():
    """Opened without its measurements, the hub keeps its settings but no bursts, fused run or
    IRF of the last opening: no step shows a check it did not earn in this session."""
    from chisurf.plugins.burst.burst_analysis.gui.native import BurstAnalysisHubApp

    hub = BurstAnalysisHubApp()
    hub.restore_settings(
        {
            "workflow": {
                "raw_files": [],
                "bur_files": ["/elsewhere/burstwise_All 0.1500#30/m000.bur"],
                "burst_folder": "/elsewhere/burstwise_All 0.1500#30",
                "irf_background_patterns": {"G|G": {"irf": [1.0]}},
                "setup_name": "RVZMT150",
            },
            "fused_folder": "/elsewhere/fused",
        }
    )
    assert hub.context.burst_folder is None and hub.context.bur_files == []
    assert hub.context.irf_background_patterns == {} and hub._fused_folder is None
    assert not hub.step_done("selection") and hub.selected == "setup"
