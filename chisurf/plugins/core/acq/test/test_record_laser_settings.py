"""The Record tool's Laser and Settings panels with the simulated laser and the simulated MultiHarp.

Never the real hardware: the laser is ``live.laser.SimLaser``, the TCSPC unit ``PieSimDevice``.
The rules checked are the safety ones (outputs off after Connect and after any edit, Emission on
only after Apply, Laser off always there, the laser closed when a run ends) and the round trips: a
saved settings file loads back into the form, the device and the laser; a recording carries its
settings document in its header, and a measurement gives its settings and windows back.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from chisurf.plugins.core.acq.gui import record_settings
from chisurf.plugins.core.acq.gui.record_app import RecordApp, RecordModel
from chisurf.plugins.core.acq.live import devices, settings_file
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver

SIZE = (1400, 1000)
SHOTS = Path(__file__).resolve().parents[5] / "test" / "native_emtk" / "screenshots"


@pytest.fixture
def model(tmp_path):
    m = RecordModel(output_dir=tmp_path / "rec", realtime=False)
    m.laser_kind = "simulated"
    yield m
    m.close()


def _pie_program(m):
    for record in m.laser_heads():
        m.laser_head_edited(record, "enabled", True)
        m.laser_head_edited(record, "intensity_pct", 40.0)
    for record in m.laser_outputs()[:2]:
        m.laser_output_edited(record, "burst", 1)


def _run(m, seconds=2.0):
    m.duration_s = seconds
    assert m.start(), m.status_detail
    end = time.monotonic() + 120
    while m.running:
        assert time.monotonic() < end, "the run did not end"
        time.sleep(0.02)
    m.poll(force=True)


def test_connect_leaves_the_outputs_off_and_emission_needs_apply(model):
    assert model.enabled("laser_off")  # always there, connected or not
    assert model.connect_laser()
    assert model.laser.kind == "simulated" and model.laser.state().emission_blocked
    assert model.laser_light() == "amber"
    assert not model.enabled("laser_emission_on")  # nothing applied yet
    _pie_program(model)
    assert not model.enabled("laser_emission_on")
    assert model.apply_laser_program()
    assert model.enabled("laser_emission_on") and model.laser.state().emission_blocked
    assert model.laser_emission_on()
    assert not model.laser.state().emission_blocked and model.laser_light() == "red"
    # an edit after Apply switches the outputs off and asks for Apply again
    model.laser_head_edited(model.laser_heads()[0], "intensity_pct", 55.0)
    assert model.laser.state().emission_blocked and not model.enabled("laser_emission_on")
    assert model.apply_laser_program() and model.laser_emission_on()
    model.laser_off()
    assert model.laser.state().emission_blocked
    st = model.laser.state()
    assert [h.intensity_pct for h in st.heads] == [55.0, 40.0]
    assert st.oscillator.output_enabled[:2] == [True, True]


def test_the_rate_is_the_lasers(model):
    model.connect_laser()
    _pie_program(model)
    model.laser_divider = 2
    model.laser_program_edited()
    model.apply_laser_program()
    text, detail = model.laser_rate()
    rate = model.laser.capture()["repetition_rate_hz"]
    assert text == f"Rate {rate / 1e6:.2f} MHz" and "one sequence" in detail


def test_windows_from_the_laser_replace_the_setups(model):
    assert not model.enabled("windows_from_laser")
    model.connect_laser()
    _pie_program(model)
    model.apply_laser_program()
    assert model.windows_from_laser()
    n_micro, _res = model._clock()
    exp = model.make_experiment(n_micro)
    # the simulated laser pulses in step with the simulated measurement: two halves of the period
    assert exp.setup["windows"] == {"prompt": [0, n_micro // 2], "delayed": [n_micro // 2, n_micro]}
    assert "windows from the laser" in exp.name


def test_a_run_end_and_the_window_close_close_the_laser(model):
    model.connect_laser()
    laser = model.laser
    _run(model)
    assert model.laser is None and not laser.is_open and laser.events[-1] == "close"
    model.connect_laser()
    laser = model.laser
    model.close()
    assert not laser.is_open


def test_saved_settings_load_back_into_the_form_the_device_and_the_laser(model, tmp_path):
    model.connect_laser()
    _pie_program(model)
    model.apply_laser_program()
    model.min_photons, model.window_time_ms, model.duration_s = 45, 0.5, 30.0
    model.sync_offset_ps = 1200
    model.real_gamma = 0.7
    model.realism_edited()
    saved = model.save_settings_to(tmp_path / "pie")
    assert saved.name == "pie.json" and model.settings_text.endswith("pie.json")
    doc = settings_file.load(saved)
    assert doc["laser"]["backend"] == "simulated" and doc["experiment"]["preset"] == "pie"

    if devices.PieSimDevice is None:  # the simulated device runs behind pqusb (CMC)
        pytest.skip("pqusb (CMC) is not installed")
    other = RecordModel(output_dir=tmp_path / "rec2", realtime=False)
    other.laser_kind = "simulated"
    other.connect_laser()
    dev = devices.PieSimDevice(seed=1)
    import pqusb

    dev.initialize(pqusb.MODE_T3)
    other.device = dev
    rows = [SimpleNamespace(address=str(saved), name=saved.name, data_kind="setup")]
    record_settings.workspace_datasets = lambda kind: rows if kind == "setup" else []
    try:
        other.settings_address = f"setup:{saved}"
        assert other.enabled("load_settings") and not other.enabled("use_measurement_settings")
        assert other.load_settings(), other.settings_detail
    finally:
        from chisurf.plugins.core.acq.live.project import workspace_datasets

        record_settings.workspace_datasets = workspace_datasets
    assert (other.min_photons, other.window_time_ms, other.duration_s) == (45, 0.5, 30.0)
    assert other.sync_offset_ps == 1200 and dev.settings.sync.offset_ps == 1200  # on the device
    assert other.realism().gamma == pytest.approx(0.7)
    assert other.setup_address == record_settings.SETTINGS_SETUP
    st = other.laser.state()  # on the laser, emission off
    assert st.emission_blocked and [h.intensity_pct for h in st.heads] == [40.0, 40.0]
    assert other.laser_applied and other.enabled("laser_emission_on")
    # the device section comes from the device itself when one is connected
    assert "resolution_ps" in other.current_settings()["device"]
    other.device = None
    other.close()


def test_a_recording_carries_its_settings_and_gives_them_back(model, tmp_path):
    model.connect_laser()
    _pie_program(model)
    model.apply_laser_program()
    model.run_name = "with_settings"
    model.min_photons = 35
    _run(model)
    tags = settings_file.read_ptu_tags(model.saved_path)
    stored = json.loads(tags[settings_file.CHISURF_SETTINGS_TAG])
    assert stored["experiment"]["burst"]["min_photons"] == 35
    assert stored["laser"]["oscillator"]["output_enabled"][:2] == [True, True]

    fresh = RecordModel(output_dir=tmp_path / "rec3", realtime=False)
    rows = [SimpleNamespace(address=str(model.saved_path), name="with_settings", header_json="")]
    record_settings.workspace_datasets = lambda kind: rows if kind == "photons" else []
    try:
        fresh.settings_address = f"photons:{model.saved_path}"
        assert fresh.enabled("use_measurement_settings")
        assert fresh.use_measurement_settings(), fresh.settings_detail
    finally:
        from chisurf.plugins.core.acq.live.project import workspace_datasets

        record_settings.workspace_datasets = workspace_datasets
    assert fresh.min_photons == 35 and fresh.settings_text == "Settings: with_settings"
    assert fresh.proposed_windows and fresh.enabled("use_proposed_windows")
    assert fresh.use_proposed_windows()
    assert set(fresh.make_experiment(fresh._clock()[0]).setup["windows"]) == {"prompt", "delayed"}
    fresh.close()


def test_a_measurement_without_settings_lists_what_it_did_not_record(model, tmp_path):
    """A plain PTU (no ChiSurf tag): the settings come from its tags, the gaps are listed."""
    model.run_name = "plain"
    model._run_settings = lambda: None  # a recording made without a settings document
    _run(model)
    doc, missing = settings_file.from_address(str(model.saved_path))
    fresh = RecordModel(output_dir=tmp_path / "rec4", realtime=False)
    assert fresh.adopt_settings(doc, "plain", missing)
    assert fresh.settings_detail.startswith("Not recorded") or "Notes" in fresh.settings_detail
    fresh.close()


def test_the_laser_section_renders(tmp_path):
    model = RecordModel(output_dir=tmp_path / "rec", realtime=False)
    model.laser_kind = "simulated"
    app = RecordApp(model)
    try:
        app.focus_dock("laser")  # the Laser window is a tab beside Acquisition by default
        ui = Driver(app, SIZE)
        ui.draw(3)
        ui.click("connect_laser")
        ui.draw(2)
        assert model.laser_connected
        _pie_program(model)
        ui.click("apply_laser_program")
        ui.draw(2)
        assert model.laser_applied
        ui.click("windows_from_laser")
        ui.draw(3)
        from emtk import testing

        painter = testing.PixelPainter(*SIZE)
        app.draw(painter, 0, 0, *SIZE)
        SHOTS.mkdir(parents=True, exist_ok=True)
        (SHOTS / "record_laser.png").write_bytes(
            testing.png_encode(painter.width, painter.height, painter.px)
        )
        assert model.window_override
    finally:
        app.close()


def test_the_photon_level_recorder_writes_the_settings_tag_too(tmp_path):
    """Without pqusb the session writes the PTU through tttrlib: the same tag, the same document."""
    from chisurf.plugins.core.acq.live.session import RecordSession
    from chisurf.plugins.core.acq.live.sources import SimulatedPieSource

    doc = settings_file.new_settings(
        name="x", experiment={"preset": "pie", "burst": {"min_photons": 33}}
    )
    src = SimulatedPieSource(duration_s=None, realtime=False, seed=1)
    session = RecordSession(
        src, duration_s=1.0, ptu_path=tmp_path / "a.ptu", name="a", settings=doc
    )
    session.start()
    session.wait(60)
    assert settings_file.from_address(str(tmp_path / "a.ptu")) == (doc, [])
