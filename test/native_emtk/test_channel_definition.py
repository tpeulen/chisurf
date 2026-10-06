"""Complete native detector-setup workflows reuse the scientific APIs."""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from chisurf.core.fio.lut_context import clear_active_setup_lut, get_active_setup_lut
from chisurf.core.setup_channel_definition import ChannelDefinition


def definition(file_path=None, db=None):
    return ChannelDefinition(
        {
            "detectors": {
                "green": {
                    "chs": [0, 1],
                    "micro_time_ranges": [[0, 32]],
                    "g_factor": 1.0,
                    "l1": 0.0,
                    "l2": 0.0,
                    "mle_settings": {"keep": True},
                }
            },
            "windows": {"prompt": [0, 32]},
            "tttr_reading": {
                "file_type": "auto",
                "macro_time_resolution": 25.0,
                "micro_time_resolution": 50.0,
                "micro_time_binning": 2,
            },
        },
        file_path=file_path,
        db=db,
    )


def test_setup_crud_public_and_calibration_snapshot(tmp_path):
    file = tmp_path / "setups.json"
    model = definition(file_path=file)
    try:
        model.save_setup("Instrument", public=True)
        assert json.loads(file.read_text())["setups"]["Instrument"]["_is_public"]
        other = definition(file_path=file)
        assert other.refresh_setups() == ["Instrument"]
        other.select_setup("Instrument")
        assert other.get_settings()["tttr_reading"]["effective_micro_time_resolution"] == 100
        assert other.get_settings()["channels"]["prompt_green"][0]["window_range"] == [0, 32]
        other.rename_setup("Renamed")
        assert list(json.loads(file.read_text())["setups"]) == ["Renamed"]
        assert other.data["detectors"]["green"]["mle_settings"] == {"keep": True}
        other.rename_detector("green", "donor")
        other.rename_window("prompt", "excitation")
        assert other.data["detectors"]["donor"]["mle_settings"] == {"keep": True}
        assert "excitation_donor" in other.get_settings()["channels"]
        other.delete_setup()
        assert json.loads(file.read_text())["setups"] == {}

        class Database:
            def list_setup_calibration_dates(self, key):
                return ["2026-09-01"]

            def get_setup_calibration(self, key, calibrated_at=None):
                assert calibrated_at == "2026-09-01"
                return [{"channel_name": "green", "g_factor": 1.7, "l1": 0.1, "l2": 0.2}]

        model = definition(db=Database())
        model.current_name = "Instrument"
        assert model.calibration_dates() == ["2026-09-01"]
        assert model.apply_calibration("2026-09-01") == 1
        assert model.data["detectors"]["green"]["g_factor"] == 1.7
    finally:
        clear_active_setup_lut()


def test_numerical_g_lut_and_timing_override(tmp_path):
    model = definition()
    try:
        model.preview = {0: np.full(32, 20.0), 1: np.full(32, 10.0)}
        assert model.calculate_g("green", bounds=[0, 31])["g_factor"] == 2
        table = model.compute_lut(0, 0, 31)
        assert np.isfinite(table["NTAC_fract"]).all()
        model.data["channel_shifts"]["0"] = 2
        model.data["apply_lut"] = True
        model.changed()
        luts, shifts, apply = get_active_setup_lut()
        assert apply and 0 in luts and shifts[0] == 2
        lut = tmp_path / "table.npy"
        np.save(lut, np.asarray(table["NTAC_fract"]))
        model.assign_lut(1, lut)
        assert len(model.data["channel_luts"]["1"]) == 32
        exported = tmp_path / "tac_lut.json"
        model.export_lut(1, exported)
        assert len(json.loads(exported.read_text())["NTAC_fract"]) == 32
        path = Path("chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/m000.spc")
        model.data["apply_lut"] = False
        model.data["tttr_reading"].update(
            macro_time_resolution=4.0, micro_time_resolution=100.0, override_timing=True
        )
        tttr = model.open_tttr(path)
        assert np.isclose(tttr.header.macro_time_resolution, 4e-9, rtol=1e-10, atol=0)
        assert np.isclose(tttr.header.micro_time_resolution, 100e-12, rtol=1e-10, atol=0)
        model.read_tttr(path)
        assert model.preview and model.preview_path == str(path)
    finally:
        clear_active_setup_lut()


def test_optical_graph_extraction_matches_roundtrip(tmp_path):
    from chisurf.core.optical_configuration import _graph_to_config, build_easy_graph
    from chisurf.emtk.optical_configuration import OpticalConfigurationWidget

    config = {
        "lasers": "488:1.0",
        "detectors": [{"name": "green", "bandpass_probe_id": 10, "qe_probe_id": 20}],
        "dyes": {"1": {"qy": 0.8, "ec": 10000}},
        "kappa2": 0.6,
        "n": 1.4,
    }
    graph = build_easy_graph(config)
    assert graph["nodes"] and graph["edges"]
    restored = _graph_to_config(graph)
    assert restored["lasers"] == "488:1.0"
    assert restored["detectors"][0]["name"] == "green"
    widget = OpticalConfigurationWidget(config)
    path = tmp_path / "optical.json"
    widget.save(path)
    widget.load(path)
    assert widget.config["kappa2"] == 0.6


def test_the_native_channel_page_and_its_windows_render_without_qt(tmp_path):
    code = """
import sys,logging,numpy as np
class Errors(logging.Handler):
    def emit(self,record):
        if record.levelno>=40:raise AssertionError(record.getMessage())
logging.getLogger().addHandler(Errors())
class Painter:
    def text_width(self,text):return len(str(text))*7
    def line_height(self):return 14
    def __getattr__(self,name):return lambda *a,**kw:None
from emtk import frame,im
from chisurf.core.setup_channel_definition import ChannelDefinition
from chisurf.emtk.channel_definition import ChannelDefinitionWidget
m=ChannelDefinition({'detectors':{'green':{'chs':[0,1],'micro_time_ranges':[[0,32]]}},'windows':{'prompt':[0,32]},'tttr_reading':{'file_type':'auto','macro_time_resolution':25,'micro_time_resolution':50,'micro_time_binning':1}})
m.preview={0:np.full(32,20.),1:np.full(32,10.)}
w=ChannelDefinitionWidget(model=m)
for opened in (False,True):
    w.open_sections=dict.fromkeys(w.open_sections,opened)
    for window in (w.preview_window,w.lut_window,w.shift_window,w.optical_window,w.help_window):
        window.open=opened
    w._shift_draft={}
    with frame(Painter(),(0.,0.,1200.,900.)):
        im.begin('test',(0.,0.,1200.,900.))
        w.draw()
        im.end()
        w.draw_dialogs((0.,0.,1200.,900.))
w.close()
qt=[m for m in sys.modules if m.startswith(('qtpy','PyQt','PySide'))]
assert not qt,qt
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr


def test_named_setups_use_real_mmfdb_public_store(tmp_path):
    from mmfdb.repository import MFDatabase

    with MFDatabase(str(tmp_path / "setups.sqlite")) as db:
        from chisurf.core.fio.setup_store import resolve_active_user_id

        db.add_user(resolve_active_user_id(), "Test User")
        model = definition(db=db)
        model.save_setup("Shared instrument", public=True)
        loaded = definition(db=db)
        assert loaded.refresh_setups() == ["Shared instrument"]
        loaded.select_setup("Shared instrument")
        assert loaded.data["_is_public"] is True
        assert loaded.data["detectors"]["green"]["g_factor"] == 1
        loaded.rename_setup("Renamed instrument")
        assert loaded.refresh_setups() == ["Renamed instrument"]
        loaded.delete_setup()
        assert loaded.refresh_setups() == []
    clear_active_setup_lut()


def test_g_factor_archive_registers_real_reference_provenance(tmp_path, monkeypatch):
    from mmfdb.repository import MFDatabase

    from chisurf.core.fio.setup_store import resolve_active_user_id

    path = tmp_path / "calibrations.sqlite"
    objects = tmp_path / "objects"
    objects.mkdir()
    with MFDatabase(str(path)) as db:
        db.add_user(resolve_active_user_id(), "Test User")
    monkeypatch.setattr("mmfdb.store.database_resolver.resolve_database_path", lambda: path)
    monkeypatch.setattr("mmfdb.store.database_resolver.object_store_root", lambda: objects)
    model = definition()
    model.preview = {0: np.full(64, 20.0), 1: np.full(64, 10.0)}
    try:
        model.calculate_g("green")
        archived = model.archive_g("green")
        assert archived["ok"] and archived["calibration_id"]
        assert archived["reference_decay_id"]
        assert (
            model.data["detectors"]["green"]["g_factor_calibration_id"]
            == archived["calibration_id"]
        )
    finally:
        clear_active_setup_lut()


def test_optical_simulation_action_uses_original_backend(monkeypatch):
    from chisurf.emtk.optical_configuration import OpticalConfigurationWidget
    from chisurf.plugins.core.lightpath_simulator.core import workflow

    calls = []

    def simulate(graph, db_path=None):
        assert graph["nodes"] and graph["edges"]
        calls.append(graph)
        return {"crosstalk_matrices": {"detected": np.eye(2)}}

    monkeypatch.setattr(workflow, "simulate_lightpath", simulate)
    saved = []
    widget = OpticalConfigurationWidget(detector_names=["green", "red"], on_changed=saved.append)
    result = widget.simulate()
    assert calls and result["crosstalk_matrices"]["detected"] == [[1.0, 0.0], [0.0, 1.0]]
    assert saved[-1]["_cached_results"]["crosstalk_matrices"] == result["crosstalk_matrices"]


def test_failed_setup_persistence_preserves_working_state(tmp_path, monkeypatch):
    import pytest

    model = definition(file_path=tmp_path / "setups.json")
    model.save_setup("Original")
    monkeypatch.setattr("chisurf.core.fio.setup_store.save_setups", lambda *a, **kw: False)
    for action in (
        lambda: model.save_setup("Other"),
        lambda: model.rename_setup("Other"),
        model.delete_setup,
    ):
        with pytest.raises(OSError):
            action()
        assert model.current_name == "Original"
        assert list(model.setups) == ["Original"]
    clear_active_setup_lut()


def test_actual_photons_follow_channel_lut_and_shift_settings():
    from pathlib import Path

    path = Path("chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/m000.spc")
    model = definition()
    try:
        model.data["apply_lut"] = False
        original = model.open_tttr(path)
        channels = np.asarray(original.routing_channels)
        micro = np.asarray(original.micro_times, dtype=np.int64)
        n = int(original.header.number_of_micro_time_channels)
        model.data["apply_lut"] = True
        model.data["channel_shifts"] = {"0": 7}
        shifted = model.open_tttr(path)
        mask = (channels == 0) & (micro < n - 10)
        assert mask.sum() > 0
        np.testing.assert_array_equal(
            np.asarray(shifted.micro_times, dtype=np.int64)[mask], micro[mask] + 7
        )
        np.testing.assert_array_equal(
            np.asarray(shifted.micro_times)[channels != 0], micro[channels != 0]
        )
        model.data["channel_luts"] = {"0": np.linspace(0, n / 2, n).tolist()}
        transformed = model.open_tttr(path)
        corrected = np.asarray(transformed.micro_times, dtype=np.int64)
        assert np.all(corrected[mask] <= micro[mask] / 2 + 9)
        assert np.any(corrected[mask] != micro[mask])
        np.testing.assert_array_equal(np.asarray(transformed.routing_channels), channels)
        np.testing.assert_array_equal(
            np.asarray(transformed.macro_times), np.asarray(original.macro_times)
        )
        model.read_tttr(path)
        assert not np.array_equal(model.preview[0], model.raw_preview[0])
        assert model.preview[0].sum() == model.raw_preview[0].sum()
    finally:
        clear_active_setup_lut()


def test_calibration_revision_survives_setup_save_and_reopen(tmp_path):
    from mmfdb.repository import MFDatabase

    from chisurf.core.fio import setup_store

    with MFDatabase(str(tmp_path / "calibration_reopen.sqlite")) as db:
        user = setup_store.resolve_active_user_id()
        db.add_user(user, "Test User")
        model = definition(db=db)
        model.save_setup("Instrument")
        key = setup_store.setup_id_for_name("Instrument", user, "tttr_detector_setup")
        revision = "2026-09-01T12:00:00+00:00"
        db.add_setup_calibration(
            key,
            "green",
            g_factor=1.9,
            l1=-0.01,
            l2=0.02,
            calibrated_at=revision,
            created_by_user_id=user,
        )
        assert revision in model.calibration_dates()
        model.apply_calibration(revision)
        model.save_setup("Instrument")
        reopened = definition(db=db)
        reopened.refresh_setups()
        reopened.select_setup("Instrument")
        assert reopened.data["detectors"]["green"]["g_factor"] == 1.9
        assert reopened.data["detectors"]["green"]["l1"] == -0.01
        assert reopened.data["detectors"]["green"]["l2"] == 0.02
    clear_active_setup_lut()


def test_advanced_optical_handoff_keeps_custom_graph_and_unknown_metadata(tmp_path):
    from emtk import frame
    from emtk.testing import RecordingPainter

    from chisurf.emtk.optical_configuration import OpticalConfigurationWidget

    widget = OpticalConfigurationWidget(detector_names=["green", "red"])
    widget.open_advanced()
    try:
        controller = widget.advanced_app.controller
        custom = controller.add_node("combiner", (700.0, 800.0))
        custom.config["unknown_metadata"] = {"preserve": True}
        with frame(RecordingPainter(), (0.0, 0.0, 1200.0, 900.0)):
            widget.draw_dialogs((0.0, 0.0, 1200.0, 900.0))
        widget.apply_advanced()
        graph = widget.config["_graph"]
        assert any(
            node["id"] == custom.id and node["config"]["unknown_metadata"] == {"preserve": True}
            for node in graph["nodes"]
        )
        widget.config["kappa2"] = 0.8
        widget.changed()
        assert any(node["id"] == custom.id for node in widget.graph_override["nodes"])
        path = tmp_path / "advanced_optical.json"
        widget.save(path)
        reopened = OpticalConfigurationWidget()
        reopened.load(path)
        assert reopened.graph_override == widget.graph_override
        reopened.close()
    finally:
        widget.close()


def test_standalone_channel_editor_hover_help_and_populated_narrow_frame(tmp_path):
    from emtk.testing import RecordingPainter

    from chisurf.plugins.core.setup_channel_definition.gui.app import create_app

    app = create_app(model=definition(file_path=tmp_path / "setups.json"))
    try:
        app.io.wall_clock = False
        app.io.delta_time = 0.01
        painter = RecordingPainter()
        app.draw(painter, 0.0, 0.0, 800.0, 600.0)
        button = next(text for text in painter.texts if text[5] == "Save")
        app.hover(button[0] + button[2] / 2, button[1] + button[3] / 2)
        hovered = RecordingPainter()
        app.draw(hovered, 0.0, 0.0, 800.0, 600.0)
        app.io.delta_time = 0.6
        app.draw(hovered, 0.0, 0.0, 800.0, 600.0)
        assert "Ask for a name and store the working definition" in " ".join(hovered.strings)
        app.io.mouse_pos = (-1.0, -1.0)
        narrow = RecordingPainter()
        app.draw(narrow, 0.0, 0.0, 320.0, 640.0)
        assert "Detector Name" in narrow.strings
        assert "Channels" in narrow.strings
        preferences = app.export_settings()
        restored = create_app()
        try:
            restored.restore_settings(preferences)
            assert restored.get_settings()["detectors"]["green"]["mle_settings"] == {"keep": True}
        finally:
            restored.close()
    finally:
        app.close()
