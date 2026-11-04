"""The standalone power-calibration panel: measured entries only, explicit hardware-state
gates, a conversion that refuses everything the measurements do not back, and the quality
of a calibration shown as a table (metric, measured value, user limit, status, guidance).

The panel is a view over :mod:`chisurf.plugins.core.acq.live.power_calibration` and the
calibration library's inventory; these tests pin the behaviour the owner asked for:

* nothing is assumed installed -- a laser is selectable only after a verified record,
* the simulator is never presented as live and its readback is never captured,
* the panel never energizes a laser -- it only reads state,
* every capture carries the verified emission/config evidence the backend demands,
* the conversion is disabled wherever the backend refuses (unverified states, expired,
  out of the measured band) and the refusal is shown instead of a number,
* the quality table preserves raw values and unavailable/unverified statuses, judges
  only by USER-configured limits, and ships none of its own thresholds.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from chisurf.plugins.core.acq.gui.calibration_panel import (
    CalibrationPanel,
    CalibrationPanelModel,
    make_app,
)
from chisurf.plugins.core.acq.live.calibration.lasers import NotInstalled
from chisurf.plugins.core.acq.live.laser import HeadState, LaserState, SimLaser
from chisurf.plugins.core.acq.live.power_calibration import (
    CALIBRATION_SCHEMA,
    CalibrationSet,
    LaserConditions,
)

SIZE = (940, 1000)


@pytest.fixture
def env(tmp_path, monkeypatch):
    from chisurf.plugins.microscopy.imaging_emtk.testing import hermetic_env

    hermetic_env(tmp_path, monkeypatch)
    return tmp_path


@pytest.fixture
def model(env) -> CalibrationPanelModel:
    return CalibrationPanelModel(cal_path=env / "power" / "cal.json")


@pytest.fixture
def app(model):
    panel = CalibrationPanel(model)
    yield panel
    panel.close()


def verified_640(model: CalibrationPanelModel) -> None:
    model.inventory.verify_installed(640, evidence="hardware configuration: SLM 1 head 640")
    model.verify_nm = 640
    model.verify_installed()


# -- a stand-in for an open Sepia II that records every call the panel makes --------------------
class RecordingBackend:
    """Read-only stand-in: reads are listed, any driving call lands in ``mutations``."""

    kind = "sepia"

    def __init__(self, state: LaserState) -> None:
        self._state = state
        self.reads: list[str] = []
        self.mutations: list[str] = []

    @property
    def is_open(self) -> bool:
        self.reads.append("is_open")
        return True

    def state(self) -> LaserState:
        self.reads.append("state")
        return self._state

    def close(self) -> None:
        self.mutations.append("close")

    def __getattr__(self, name: str):
        if name.startswith("set_") or name in ("apply", "laser_off", "open"):
            def record(*args, **kwargs):
                self.mutations.append(name)

            return record
        raise AttributeError(name)


def sepia_state(emission_blocked: bool = False) -> LaserState:
    return LaserState(
        model="PDL 828", serial="PQ-0123", library="libphacq",
        heads=[
            HeadState(slot=0, name="SLM 0", serial="H-488", wavelength_nm=488.0,
                      intensity_pct=0.0),
            HeadState(slot=1, name="SLM 1", serial="H-640", wavelength_nm=640.0,
                      intensity_pct=30.0),
        ],
        oscillator=None, emission_blocked=emission_blocked,
    )


def fill_conditions(model: CalibrationPanelModel, **over) -> None:
    model.head_name = over.get("head_name", "LDH-640")
    model.rep_rate_mhz = over.get("rep_rate_mhz", 20.0)
    model.mode = over.get("mode", "pulsed")
    model.pattern = over.get("pattern", "PIE 1:5")
    model.optical_path = over.get("optical_path", "main dichroic, 560 LP")


CONFIG_JSON = json.dumps({"heads": [
    {"name": "LDH-488", "wavelength_nm": 488.0, "serial": "H-488"},
    {"name": "LDH-640", "wavelength_nm": 640.0, "serial": "H-640"},
]})
EMISSION_ON_640 = json.dumps([
    {"laser": "LDH-488", "on": False, "verified": True},
    {"laser": "LDH-640", "on": True, "verified": True},
])
EMISSION_ALL_OFF = json.dumps([
    {"laser": "LDH-488", "on": False, "verified": True},
    {"laser": "LDH-640", "on": False, "verified": True},
])


def capture_via_manual_transcription(model: CalibrationPanelModel) -> None:
    """The whole measured session, typed the way an operator transcribes the instrument."""
    verified_640(model)
    model.laser_nm = 640
    model.laser_selected()
    fill_conditions(model)
    model.config_json = CONFIG_JSON
    assert model.capture_configuration()
    model.emission_json = EMISSION_ALL_OFF
    assert model.capture_emission()  # the dark offset's all-off state
    model.diode_source = "manual entry"
    model.diode_raw = 12.0
    assert model.capture_dark()
    model.emission_json = EMISSION_ON_640
    assert model.capture_emission()
    model.meter = "Thorlabs PM100D S121C"
    model.meter_calibrated = "2026-04-10"
    for drive, raw, uw in ((5.0, 120.0, 0.9), (10.0, 240.0, 1.9), (20.0, 520.0, 4.2)):
        model.diode_raw = raw
        model.new_uw = uw
        model.new_drive_pct = drive
        assert model.capture_point(), model.error


# -------------------------------------------------------------------------------------------
# Construction and layout
# -------------------------------------------------------------------------------------------
def test_the_panel_draws_every_section_and_keeps_content_reachable(app):
    from chisurf.plugins.microscopy.imaging_emtk.testing import Driver

    ui = Driver(app, SIZE)
    ui.draw(3)
    strings = ui.strings()
    for expected in ("Power calibration", "Laser head", "Hardware readback",
                     "Quality", "Reference points", "Conversion"):
        assert any(expected in s for s in strings), (expected, strings[:30])
    for control in ("cal_path", "laser_nm", "capture_dark", "capture_point",
                    "adopt_save", "probe_raw"):
        assert control in app.form.rects, (control, sorted(app.form.rects)[:40])
    # the body scrolls: content taller than the window lays out inside the child region
    deepest = max((r[1] + r[3]) for r in app.form.rects.values())
    assert deepest > SIZE[1], "the panel content should extend below the fold (and scroll)"


def test_make_app_and_window_size(app):
    assert isinstance(make_app(), CalibrationPanel)
    assert isinstance(CalibrationPanel.window_size, tuple) and len(CalibrationPanel.window_size) == 2


# -------------------------------------------------------------------------------------------
# Nothing is assumed installed
# -------------------------------------------------------------------------------------------
def test_no_laser_is_selectable_before_it_is_verified(model):
    assert model.laser_options() == []
    with pytest.raises(NotInstalled):
        model.laser_nm = 640
        model.laser_selected()
    model.verify_nm = 640
    assert not model.verify_installed()  # the verification demands the readback as evidence
    assert "evidence" in model.error.lower()
    assert model.laser_options() == []
    model.verify_evidence = "hardware configuration readback: 640 nm head in SLM 1"
    model.verify_installed()
    assert model.laser_options() == [[640, "640 nm"]]
    with pytest.raises(NotInstalled):
        model.inventory.select(488)  # the other heads stay unverified
    assert model.inventory.select(640) == 640


# -------------------------------------------------------------------------------------------
# The simulator is never live; the panel never drives the laser
# -------------------------------------------------------------------------------------------
def test_the_simulator_is_labelled_and_never_captured(model):
    model.laser_kind = "simulated"
    assert model.attach_laser()
    assert isinstance(model.laser, SimLaser)
    text = model.laser_status_text()
    assert "simulated" in text.lower() and "not live" in text.lower()
    assert not model.capture_configuration()
    assert "simulator" in model.error.lower()
    assert not model.capture_emission()
    assert "simulator" in model.error.lower()
    # the captures stay refused even with the sim driven into a tempting state
    model.config_json = CONFIG_JSON
    assert not model.capture_configuration()


def test_the_panel_only_reads_the_laser_never_drives_it(model, env):
    backend = RecordingBackend(sepia_state())
    model.inventory.verify_installed(640, evidence="hardware configuration: SLM 1 head 640")
    model.laser_nm = 640
    model.laser_selected()
    fill_conditions(model, head_name="")  # empty: the readback's own name is adopted
    model.attach_backend(backend)
    assert model.capture_configuration()
    assert model.capture_emission()
    model.meter = "Thorlabs PM100D S121C"
    model.meter_calibrated = "2026-04-10"
    for drive, raw, uw in ((5.0, 120.0, 0.9), (10.0, 240.0, 1.9)):
        model.diode_raw = raw
        model.new_uw = uw
        model.new_drive_pct = drive
        assert model.capture_point(), model.error
    # the OPERATOR blocks the emission for the dark reading (the panel has no such
    # control): the next readback shows every head off, and the dark capture passes
    backend._state.emission_blocked = True
    assert model.capture_emission()
    model.diode_raw = 12.0
    assert model.capture_dark(), model.error
    model.probe_raw = 240.0
    model.probe()
    assert model.adopt_and_save() == []
    assert backend.mutations == [], backend.mutations
    assert "state" in backend.reads


# -------------------------------------------------------------------------------------------
# A full measured session, saved, reloaded and converted
# -------------------------------------------------------------------------------------------
def test_a_measured_calibration_round_trips_and_converts_inside_its_band(model, env):
    capture_via_manual_transcription(model)
    model.draft.conditions = model.conditions()
    model.draft.calibrated = date.today().isoformat()  # what adopting records
    assert model.draft.validate() == [], model.draft.validate()
    assert model.adopt_and_save() == []
    path = Path(model.cal_path)
    assert path.exists()
    doc = json.loads(path.read_text())
    assert doc["schema"] == CALIBRATION_SCHEMA
    book = CalibrationSet.load(path)
    cal = book.calibrations[0]
    assert cal.key.laser == "LDH-640" and cal.key.wavelength_nm == 640.0
    assert len(cal.points) == 3 and cal.dark.raw == 12.0
    assert cal.calibrated == date.today().isoformat()
    today = date.today()
    assert cal.expires_on() == date(today.year + (today.month + 3 - 1) // 12,
                                    (today.month + 2) % 12 + 1, today.day)  # +3 calendar months
    # the conversion works where it was measured, under the verified state it was measured in
    conditions = LaserConditions("LDH-640", 640.0, repetition_rate_hz=20e6, mode="pulsed",
                                 pattern="PIE 1:5", optical_path="main dichroic, 560 LP")
    from chisurf.plugins.core.acq.live.power_calibration import ConfigIdentity, EmissionState

    emission = EmissionState.from_dict(json.loads(EMISSION_ON_640))
    config = ConfigIdentity.from_dict(json.loads(CONFIG_JSON))
    good = cal.convert(240.0, conditions=conditions, emission=emission, config=config)
    assert good.valid and good.uw == pytest.approx(1.9, rel=1e-6)
    beyond = cal.convert(5000.0, conditions=conditions, emission=emission, config=config)
    assert not beyond.valid and beyond.status == "extrapolated"


def test_the_reloaded_book_powers_the_probe_and_shows_refusals(model, env):
    capture_via_manual_transcription(model)
    assert model.adopt_and_save() == []
    fresh = CalibrationPanelModel(cal_path=model.cal_path)
    fresh.load_all()
    assert len(fresh.book.calibrations) == 1
    fresh.inventory.verify_installed(640, evidence="hardware configuration: SLM 1 head 640")
    fresh.laser_nm = 640
    fresh.laser_selected()
    fill_conditions(fresh)
    fresh.config_json = CONFIG_JSON
    assert fresh.capture_configuration()
    fresh.emission_json = EMISSION_ON_640
    assert fresh.capture_emission()
    fresh.probe_raw = 240.0
    result = fresh.probe()
    assert result.valid and result.uw == pytest.approx(1.9, rel=1e-6)
    fresh.probe_raw = 99999.0
    result = fresh.probe()
    assert not result.valid and "beyond" in (result.reason or "")


def test_unverified_emission_blocks_captures_and_the_conversion(model):
    verified_640(model)
    model.laser_nm = 640
    model.laser_selected()
    fill_conditions(model)
    model.config_json = CONFIG_JSON
    assert model.capture_configuration()
    # an emission state whose 488 head is not verified blocks everything downstream
    model.emission_json = json.dumps([
        {"laser": "LDH-488", "on": False, "verified": False},
        {"laser": "LDH-640", "on": True, "verified": True},
    ])
    assert model.capture_emission()  # recorded as reported; its USE is what is refused
    assert not model.capture_point()
    assert "unverified" in model.error.lower()
    model.diode_raw = 12.0
    assert not model.capture_dark()
    assert "off" in model.error.lower() or "verified" in model.error.lower()
    result = model.probe()
    assert not result.valid and result.uw is None
    assert model.probe_text()
    assert "unverified" in model.probe_text().lower()


def test_conditions_and_configuration_gates(model):
    verified_640(model)
    model.laser_nm = 640
    model.laser_selected()
    model.config_json = CONFIG_JSON
    model.emission_json = EMISSION_ON_640
    # the config the states are checked against was never captured: refused
    assert not model.capture_emission()
    assert model.capture_configuration()
    # a config without the selected head is refused at capture
    model.config_json = json.dumps({"heads": [
        {"name": "LDH-488", "wavelength_nm": 488.0, "serial": "H-488"}]})
    assert not model.capture_configuration()
    assert "640" in model.error
    model.config_json = CONFIG_JSON
    assert model.capture_configuration()
    # a malformed emission text is refused, never defaulted
    model.emission_json = "{'laser': broken"
    assert not model.capture_emission()
    assert not model.capture_point()
    result = model.probe()
    assert not result.valid and result.uw is None


def test_bad_point_entries_are_refused_at_capture(model):
    capture_via_manual_transcription(model)
    n = len(model.draft.points)
    model.new_uw = -1.0
    model.diode_raw = 700.0
    assert not model.capture_point()
    assert "positive" in model.error.lower()
    # a raw at or below the dark reading has no light above dark to attribute
    model.new_uw = 1.0
    model.diode_raw = 12.0
    assert not model.capture_point()
    assert "dark" in model.error.lower()
    assert len(model.draft.points) == n


def test_an_expired_calibration_is_refused_and_shown(model, env):
    capture_via_manual_transcription(model)
    assert model.adopt_and_save() == []
    # four months later: the shipped 3-calendar-month policy expires it
    doc = json.loads(Path(model.cal_path).read_text())
    doc["calibrations"][0]["calibrated"] = (date.today() - timedelta(days=125)).isoformat()
    Path(model.cal_path).write_text(json.dumps(doc))
    fresh = CalibrationPanelModel(cal_path=model.cal_path)
    fresh.load_all()
    fresh.inventory.verify_installed(640, evidence="hardware configuration: SLM 1 head 640")
    fresh.laser_nm = 640
    fresh.laser_selected()
    fill_conditions(fresh)
    fresh.config_json = CONFIG_JSON
    assert fresh.capture_configuration()
    fresh.emission_json = EMISSION_ON_640
    assert fresh.capture_emission()
    fresh.probe_raw = 240.0
    result = fresh.probe()
    assert not result.valid and result.uw is None
    assert result.status == "expired"
    assert "expired" in fresh.probe_text().lower()
    rows = {r["metric"]: r for r in fresh.quality_rows()}
    expiry = rows["Calibration expiry"]
    assert expiry["status"] == "expired"
    assert "fresh" in expiry["guidance"].lower()


# -------------------------------------------------------------------------------------------
# The quality table: measured values, user limits, statuses, guidance
# -------------------------------------------------------------------------------------------
def test_the_quality_table_ships_no_thresholds_and_preserves_unavailable(model):
    rows = model.quality_rows()
    assert rows, "the quality table exists before anything is measured"
    for row in rows:
        assert set(row) >= {"metric", "measured", "limit", "status", "guidance"}
        assert str(row["guidance"]).strip(), row
    by_name = {r["metric"]: r for r in rows}
    # an unmeasured value says unavailable, never 0 -- and with no user limit set
    # no pass/fail is invented either (the limit column stays empty)
    assert by_name["Residual RMS"]["status"] == "unavailable"
    assert by_name["Residual RMS"]["limit"] == ""
    # an unmeasured value says unavailable, never 0
    for name in ("Residual RMS", "Residual max", "Linearity slope"):
        assert by_name[name]["status"] == "unavailable"
        assert by_name[name]["measured"] == ""
    assert by_name["Dark offset"]["status"] in ("missing", "unavailable")
    assert by_name["Operating state"]["status"] in ("unverified", "unavailable")


def test_the_quality_table_judges_only_by_user_limits(model):
    capture_via_manual_transcription(model)
    rows = {r["metric"]: r for r in model.quality_rows()}
    assert rows["Residual RMS"]["status"] == "not configured"  # still no thresholds of our own
    assert rows["Measured anchors"]["measured"] == 4  # the dark zero + three references
    assert rows["Measured anchors"]["status"] == "not configured"
    # the user sets the limits; the table judges by them and says so
    model.set_limit("residual_rms_uw", maximum=1e-9)  # impossibly tight -> outside
    model.set_limit("anchors", minimum=4)
    rows = {r["metric"]: r for r in model.quality_rows()}
    assert rows["Residual RMS"]["status"] == "outside bounds"
    assert rows["Residual RMS"]["limit"] != ""
    assert rows["Measured anchors"]["status"] == "within bounds"
    model.set_limit("residual_rms_uw", maximum=1e6)  # comfortably loose -> within
    rows = {r["metric"]: r for r in model.quality_rows()}
    assert rows["Residual RMS"]["status"] == "within bounds"
    # raw values survive next to the verdicts
    assert isinstance(rows["Residual RMS"]["measured"], float)
    assert rows["Residual RMS"]["measured"] >= 0.0


def test_the_limits_are_editable_and_persisted(model, env):
    capture_via_manual_transcription(model)
    model.set_limit("residual_rms_uw", maximum=0.05)
    model.set_limit("anchors", minimum=4)
    assert model.adopt_and_save() == []
    panel_doc = json.loads(Path(str(model.cal_path) + ".panel.json").read_text())
    assert panel_doc["format"] == "chisurf.power-panel/1"
    fresh = CalibrationPanelModel(cal_path=model.cal_path)
    fresh.load_all()
    assert fresh.limits["residual_rms_uw"].maximum == pytest.approx(0.05)
    assert fresh.limits["anchors"].minimum == 4
    rows = {r["metric"]: r for r in fresh.quality_rows()}
    assert rows["Measured anchors"]["status"] == "within bounds"


def test_the_quality_table_draws(app, model):
    from chisurf.plugins.microscopy.imaging_emtk.testing import Driver

    capture_via_manual_transcription(model)
    panel = CalibrationPanel(model)
    try:
        ui = Driver(panel, SIZE)
        ui.draw(3)
        texts = [t[5] for t in ui.draw(1).texts]
        for expected in ("Residual RMS", "Measured anchors", "Calibration expiry",
                         "Operating state"):
            assert any(expected in t for t in texts), (expected, texts[:50])
        assert "metric" in " ".join(texts).lower()
    finally:
        panel.close()


# -------------------------------------------------------------------------------------------
# The curve and the table of points
# -------------------------------------------------------------------------------------------
def test_points_table_and_curve_show_the_measured_data(app, model):
    from chisurf.plugins.microscopy.imaging_emtk.testing import Driver

    capture_via_manual_transcription(model)
    panel = CalibrationPanel(model)
    try:
        ui = Driver(panel, SIZE)
        ui.draw(3)
        texts = [t[5] for t in ui.draw(1).texts]
        joined = " ".join(texts)
        for expected in ("diode raw", "µW", "measured"):
            assert expected in joined, (expected, texts[:60])
        table = model.points_table()
        assert [r["raw"] for r in table.rows()] == [120.0, 240.0, 520.0]
        assert [r["uw"] for r in table.rows()] == [0.9, 1.9, 4.2]
        assert [r["drive_pct"] for r in table.rows()] == [5.0, 10.0, 20.0]
    finally:
        panel.close()


def test_a_point_can_be_removed_before_adoption(model):
    capture_via_manual_transcription(model)
    model.draft.calibrated = date.today().isoformat()  # what adopting records
    n = len(model.draft.points)
    model.remove_point(1)
    assert len(model.draft.points) == n - 1
    assert model.draft.validate() == [], model.draft.validate()


# -------------------------------------------------------------------------------------------
# Hardware readback capture through an attached backend
# -------------------------------------------------------------------------------------------
def test_backend_capture_builds_config_and_emission_from_the_readback(model):
    backend = RecordingBackend(sepia_state())
    model.inventory.verify_installed(640, evidence="hardware configuration: SLM 1 head 640")
    model.laser_nm = 640
    model.laser_selected()
    model.attach_backend(backend)
    assert model.capture_configuration()
    assert model.config_identity is not None
    assert model.config_identity.includes("SLM 1", 640.0)
    assert "SLM 1" in model.config_evidence or "PDL 828" in model.config_evidence
    assert model.capture_emission()
    ok, why = model.emission_state.confirmed_single("SLM 1")
    assert ok, why
    assert model.emission_evidence  # the readback is recorded as the evidence
    states = {e.laser: (e.on, e.verified) for e in model.emission_state.lasers}
    assert states["SLM 0"] == (False, True)  # intensity 0: reads off
    assert states["SLM 1"] == (True, True)


def test_dark_capture_demands_every_laser_verified_off(model):
    backend = RecordingBackend(sepia_state(emission_blocked=True))
    model.inventory.verify_installed(640, evidence="hardware configuration: SLM 1 head 640")
    model.laser_nm = 640
    model.laser_selected()
    model.attach_backend(backend)
    model.capture_configuration()
    model.capture_emission()
    model.diode_source = "manual entry"
    model.diode_raw = 11.5
    assert model.capture_dark()
    assert model.draft.dark.raw == 11.5
    ok, why = model.draft.dark.emission.all_off_confirmed()
    assert ok, why
    # with a head still driven, the dark capture is refused
    backend._state.emission_blocked = False
    model.emission_state = None
    model.emission_evidence = ""
    model.capture_emission()
    model.diode_raw = 11.5
    assert not model.capture_dark()
    assert "off" in model.error.lower() or "emitting" in model.error.lower()


def test_capture_gates_are_disabled_until_their_evidence_exists(model):
    verified_640(model)
    model.laser_nm = 640
    model.laser_selected()
    assert not model.enabled("capture_emission")
    assert not model.enabled("capture_dark")
    assert not model.enabled("capture_point")
    assert not model.enabled("adopt_save")
    model.config_json = CONFIG_JSON
    assert model.capture_configuration()
    model.emission_json = EMISSION_ALL_OFF
    assert model.capture_emission()
    assert model.enabled("capture_dark")
    assert not model.enabled("capture_point")  # needs the meter next
    model.meter = "Thorlabs PM100D S121C"
    model.meter_calibrated = "2026-04-10"
    model.diode_raw = 120.0
    model.new_uw = 0.9
    assert model.enabled("capture_point")


def test_attach_refuses_without_hardware_and_reports_why(model, monkeypatch):
    from chisurf.plugins.core.acq.live import laser as laser_mod

    monkeypatch.setattr(laser_mod, "sepia_available", lambda: (False, "not available: no Sepia II connected"))
    model.laser_kind = "sepia"
    assert not model.attach_laser()
    assert "no Sepia II" in model.error
    assert model.laser is None


# -------------------------------------------------------------------------------------------
# Persistence of the book, the inventory and the panel state
# -------------------------------------------------------------------------------------------
def test_save_and_load_round_trip_every_file(model, env):
    capture_via_manual_transcription(model)
    model.inventory.verify_installed(488, evidence="hardware configuration: SLM 0 head 488")
    model.set_limit("residual_max_uw", maximum=0.2)
    assert model.adopt_and_save() == []
    fresh = CalibrationPanelModel(cal_path=model.cal_path)
    fresh.load_all()
    assert len(fresh.book.calibrations) == 1
    assert fresh.inventory.is_verified(640) and fresh.inventory.is_verified(488)
    assert fresh.limits["residual_max_uw"].maximum == pytest.approx(0.2)


def test_adopt_refuses_an_incomplete_calibration(model):
    verified_640(model)
    model.laser_nm = 640
    model.laser_selected()
    fill_conditions(model)
    assert model.adopt_and_save() != []  # the blockers come back instead of a file
    assert not Path(model.cal_path).exists()
    assert model.error
