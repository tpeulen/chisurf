"""Actual burst workflow children share one acquisition definition."""

from copy import deepcopy

import pytest

SETUP = {
    "detectors": {
        "green": {"chs": [0, 1], "micro_time_ranges": [], "g_factor": 1.0},
        "red": {"chs": [8, 9], "micro_time_ranges": [], "g_factor": 1.0},
    },
    "windows": {},
    "tttr_reading": {"file_type": "SPC-130", "micro_time_binning": 1},
    "setup_name": "shared",
    "future_metadata": {"source": "authority"},
}
ROLES = (
    "selection",
    "mle",
    "segment_mle",
    "background",
    "irf_bg",
    "h2mm",
    "accurate_fret",
    "burst_fcs",
)


@pytest.fixture(autouse=True)
def private_settings(tmp_path, monkeypatch):
    for key, suffix in [
        ("CHISURF_SETTINGS_DIR", "settings"),
        ("MMFDB_SETTINGS_DIR", "mmfdb"),
        ("MMFDB_DATABASE_PATH", "mmfdb.sqlite"),
    ]:
        monkeypatch.setenv(key, str(tmp_path / suffix))


def editor_of(child):
    if hasattr(child, "editor"):
        return child.editor
    if hasattr(child, "setup"):
        return child.setup
    return child.controller.channel_definition


def test_actual_burst_children_share_the_setup_and_keep_context():
    from chisurf.plugins.burst.burst_analysis.gui.native import create_app

    hub = create_app()
    try:
        step = hub.ensure_child("setup")
        step.autoload = False
        step.page.load_definition(deepcopy(SETUP))
        assert step.model is hub.setup_model
        for role in ROLES:
            child = hub.select(role)
            assert child is not None, hub.errors
            assert editor_of(child).hosted, role
            assert editor_of(child).model is hub.setup_model, role
        assert hub.context.channel_settings["future_metadata"] == SETUP["future_metadata"]
        assert hub.context.setup_name == "shared"
        hub.setup_model.data["detectors"]["green"]["chs"] = [2, 3]
        hub.setup_model.changed()
        fcs = hub.children["burst_fcs"].controller
        assert fcs._pair_presets[0]["chs_a"] == [2, 3]
        assert hub.children["mle"].model.session.detectors["green"]["chs"] == [2, 3]
    finally:
        hub.close()


def test_child_restore_cannot_replace_hub_authority_in_place():
    from chisurf.plugins.burst.burst_analysis.gui.native import create_app

    hub = create_app()
    try:
        step = hub.ensure_child("setup")
        step.autoload = False
        step.page.load_definition(deepcopy(SETUP))
        child = hub.select("accurate_fret")
        state = hub.export_settings()
        state["children"]["accurate_fret"]["channel_definition"]["detectors"]["green"]["chs"] = [12]
        hub.restore_settings(state)
        assert editor_of(child).model is hub.setup_model
        assert hub.setup_model.data["detectors"]["green"]["chs"] == [0, 1]
        assert hub.context.channel_settings["detectors"]["green"]["chs"] == [0, 1]
    finally:
        hub.close()


def test_fcs_same_name_definition_change_adopts_pairs_once(monkeypatch):
    from chisurf.plugins.burst.burst_fcs_correlator.gui.app import create_app

    app = create_app()
    calls = []
    original = app.controller.adopt_setup
    monkeypatch.setattr(
        app.controller, "adopt_setup", lambda *args: (calls.append(args), original(*args))[1]
    )
    try:
        app.setup.load_definition(deepcopy(SETUP))
        assert len(calls) == 1
        app.setup.model.data["detectors"]["green"]["chs"] = [2, 3]
        app.setup.model.changed()
        assert len(calls) == 2
        assert app.controller._pair_presets[0]["chs_a"] == [2, 3]
    finally:
        app.close()


def test_irf_deferred_setup_drains_with_channel_dock_closed():
    import json

    from chisurf.plugins.burst.burst_analysis.gui.native import create_app

    hub = create_app()
    try:
        step = hub.ensure_child("setup")
        step.autoload = False
        step.page.load_definition(deepcopy(SETUP))
        child = hub.select("irf_bg")
        controller = child.controller
        controller.running = True
        controller.model.micro_time_binning = 32
        hub.setup_model.data["tttr_reading"]["micro_time_binning"] = 8
        hub.setup_model.changed()
        child.irf_gui._sync_binning()
        assert hub.setup_model.data["tttr_reading"]["micro_time_binning"] == 8
        assert controller.model.micro_time_binning == 32
        controller.running = False
        # Dialog polling is independent of whether the Channels dock is visible.
        controller.channel_definition.draw_dialogs((0, 0, 1200, 800))
        assert controller.model.micro_time_binning == 8
    finally:
        hub.close()


def test_context_patterns_sources_and_fusion_survive_restore(tmp_path):
    import numpy as np

    from chisurf.plugins.burst.burst_analysis.gui.native import create_app

    hub = create_app()
    again = create_app()
    try:
        step = hub.ensure_child("setup")
        step.autoload = False
        step.page.load_definition(deepcopy(SETUP))
        hub.context.raw_files = [tmp_path / "measurement.spc"]
        hub.context.burst_folder = tmp_path / "analysis"
        hub.context.bur_files = [tmp_path / "analysis" / "bur4" / "measurement.bur"]
        hub.context.mmfdb_artifacts = {"operation": "op"}
        hub.context.raw_mmfdb_artifacts = {"measurement": "raw"}
        hub.context.irf_background_patterns = {"green": {"irf": np.arange(8.0), "bg": np.ones(8)}}
        hub._fusion_source = tmp_path / "original"
        hub._fused_folder = tmp_path / "analysis"
        state = hub.export_settings()
        again.restore_settings(state)
        assert again.context.raw_files == hub.context.raw_files
        assert again.context.burst_folder == hub.context.burst_folder
        assert again.context.bur_files == hub.context.bur_files
        assert again.context.mmfdb_artifacts == hub.context.mmfdb_artifacts
        assert again.context.raw_mmfdb_artifacts == hub.context.raw_mmfdb_artifacts
        np.testing.assert_array_equal(
            again.context.irf_background_patterns["green"]["irf"], np.arange(8.0)
        )
        assert again._fusion_source == hub._fusion_source
        assert again._fused_folder == hub._fused_folder
    finally:
        hub.close()
        again.close()
