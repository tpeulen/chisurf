"""Acceptance tests for the Qt-free acquisition native app."""

from __future__ import annotations

import threading
import time

import numpy as np
import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.microscopy.imaging_emtk.testing import Driver


class FakeBHDevice:
    """Deterministic hardware-shaped FIFO source used only by native tests."""

    device_type = "BH_SPC"

    def __init__(self, words):
        """Keep encoded B&H fixture words and record operator calls."""
        self.words = np.asarray(words, dtype=np.uint32)
        self.offset = 0
        self.calls: list[str] = []
        self.initialized = False
        self.output_path = None

    def initialize(self, *_args, **_kwargs):
        """Model a successful explicit card initialization."""
        self.calls.append("initialize")
        self.initialized = True
        return True

    def start_measurement(self):
        """Model a successful physical measurement start."""
        self.calls.append("start_measurement")
        return self.initialized

    def read_fifo(self, maximum):
        """Return bounded fixture chunks until the FIFO is empty."""
        self.calls.append("read_fifo")
        start = self.offset
        self.offset = min(len(self.words), start + int(maximum))
        return self.words[start : self.offset]

    def stop_measurement(self):
        """Record an explicit stop request."""
        self.calls.append("stop_measurement")
        return True

    def close(self):
        """Record the host-close lifecycle call."""
        self.calls.append("close")


class DelayedStartBHDevice(FakeBHDevice):
    """Hardware-shaped device that exposes the Start/Stop handoff race deterministically."""

    def __init__(self, words):
        super().__init__(words)
        self.start_entered = threading.Event()
        self.allow_start = threading.Event()

    def start_measurement(self):
        """Pause between UI Start and device-start completion until the test releases it."""
        self.calls.append("start_measurement")
        self.start_entered.set()
        self.allow_start.wait(timeout=2.0)
        return self.initialized


class SlowFakeBHDevice(FakeBHDevice):
    """FIFO source that leaves a deterministic window for a real Stop click."""

    def __init__(self, words):
        super().__init__(words)
        self.read_started = threading.Event()

    def read_fifo(self, maximum):
        """Expose an in-flight read before returning its finite fixture chunk."""
        self.read_started.set()
        time.sleep(0.02)
        return super().read_fifo(maximum)


def test_real_native_input_initializes_and_streams_injected_bh_device():
    """A native hardware click drives a fake FIFO through the actual pipeline."""
    from chisurf.plugins.core.acq.gui.app import AcquisitionApp, AcquisitionNativeModel
    from chisurf.plugins.core.acq.tcspc_devices.simulation.core.algorithms import (
        generate_spc132_uint32,
    )

    words = generate_spc132_uint32(
        {
            "N_ph_max": 64,
            "N_channels": 2,
            "M": [10.0],
            "D": [3.0],
            "q": [300.0, 225.0],
            "dt": 0.01,
            "psf_type": "analytic_gaussian3d",
            "analytic_excitation": True,
            "rmt1seed": 43,
            "rmt2seed": 44,
            "N_tac_channels": 4096,
            "tac_dt": 0.004069,
            "decay_lifetimes": [[[1.0, 3.2]]],
        }
    )
    fake = FakeBHDevice(words)
    model = AcquisitionNativeModel(device_factory=lambda device_type: fake)
    app = AcquisitionApp(model)
    try:
        ui = Driver(app, (1200, 800))
        ui.draw(3)
        ui.click("device_type")
        ui.click_text("Becker-Hickl")
        assert fake.calls == []
        ui.click("initialize_device")
        assert fake.calls == ["initialize"]
        ui.type_into("channel_0", "8")
        ui.type_into("channel_1", "0")
        ui.type_into("channel_2", "9")
        ui.type_into("channel_3", "1")
        ui.click("start")
        wait_for_run(app)
        assert "start_measurement" in fake.calls and "read_fifo" in fake.calls
        assert app.model.snapshot is not None
        assert app.model.snapshot["total_photons"] > 0
        assert sum(app.model.snapshot["channel_totals"]) == app.model.snapshot["total_photons"]
        ui.click("stop")
    finally:
        app.close()
    assert "stop_measurement" in fake.calls
    assert "close" in fake.calls


def test_stop_before_hardware_start_completes_never_starts_an_uncancelled_run():
    """A Stop click in the startup handoff waits for one final device stop, not two."""
    from chisurf.plugins.core.acq.gui.app import AcquisitionApp, AcquisitionNativeModel

    fake = DelayedStartBHDevice(np.array([], dtype=np.uint32))
    app = AcquisitionApp(AcquisitionNativeModel(device_factory=lambda _kind: fake))
    try:
        ui = Driver(app, (1200, 800))
        ui.draw(3)
        ui.click("device_type")
        ui.click_text("Becker-Hickl")
        ui.click("initialize_device")
        ui.click("start")
        assert fake.start_entered.wait(timeout=2.0)
        ui.click("stop")
        assert fake.calls.count("stop_measurement") == 0
        fake.allow_start.set()
        wait_for_run(app)
        assert fake.calls.count("start_measurement") == 1
        assert fake.calls.count("stop_measurement") == 1
        assert app.model.cancel_requested is True
    finally:
        fake.allow_start.set()
        app.close()


def test_real_native_stop_click_sends_exactly_one_stop_to_hardware():
    """An in-flight native Stop click sends one physical stop and no duplicate finalizer stop."""
    from chisurf.plugins.core.acq.gui.app import AcquisitionApp, AcquisitionNativeModel
    from chisurf.plugins.core.acq.tcspc_devices.simulation.core.algorithms import (
        generate_spc132_uint32,
    )

    words = generate_spc132_uint32(
        {
            "N_ph_max": 64,
            "N_channels": 2,
            "M": [10.0],
            "D": [3.0],
            "q": [300.0, 225.0],
            "dt": 0.01,
            "psf_type": "analytic_gaussian3d",
            "analytic_excitation": True,
            "rmt1seed": 45,
            "rmt2seed": 46,
            "N_tac_channels": 4096,
            "tac_dt": 0.004069,
            "decay_lifetimes": [[[1.0, 3.2]]],
        }
    )
    fake = SlowFakeBHDevice(words)
    app = AcquisitionApp(AcquisitionNativeModel(device_factory=lambda _kind: fake))
    try:
        ui = Driver(app, (1200, 800))
        ui.draw(3)
        ui.click("device_type")
        ui.click_text("Becker-Hickl")
        ui.click("initialize_device")
        ui.type_into("photon_limit", "1000000")
        ui.click("start")
        assert fake.read_started.wait(timeout=2.0)
        assert app.model.running is True
        ui.click("stop")
        wait_for_run(app)
        assert fake.calls.count("stop_measurement") == 1
        assert app.model.cancel_requested is True
    finally:
        app.close()


def test_reset_after_hardware_session_forgets_prior_contact():
    """A real Reset click closes the selected device and returns to a safe idle simulator."""
    from chisurf.plugins.core.acq.gui.app import AcquisitionApp, AcquisitionNativeModel

    fake = FakeBHDevice(np.array([], dtype=np.uint32))
    app = AcquisitionApp(AcquisitionNativeModel(device_factory=lambda _kind: fake))
    try:
        ui = Driver(app, (1200, 800))
        ui.draw(3)
        ui.click("device_type")
        ui.click_text("Becker-Hickl")
        ui.click("initialize_device")
        assert app.model.hardware_contacted is True
        assert app.model.source == "BH_SPC"
        ui.click("reset")
        assert app.model.device_type == "SIMULATION"
        assert app.model.source == "simulation"
        assert app.model.hardware_contacted is False
        assert app.model.device is None
        assert app.model.initialized is False
    finally:
        app.close()
    assert "close" in fake.calls


def test_real_native_input_reports_missing_hardware_driver_without_fallback():
    """A failed explicit hardware initialization stays truthful and selected."""
    from chisurf.plugins.core.acq.gui.app import AcquisitionApp, AcquisitionNativeModel

    def missing_driver(_device_type):
        raise RuntimeError("vendor library unavailable")

    app = AcquisitionApp(AcquisitionNativeModel(device_factory=missing_driver))
    try:
        ui = Driver(app, (1200, 800))
        ui.draw(3)
        ui.click("device_type")
        ui.click_text("PicoQuant")
        ui.click("initialize_device")
        assert app.model.device_type == "PICOQUANT"
        assert app.model.source == "PICOQUANT"
        assert app.model.initialized is False
        assert app.model.hardware_contacted is False
        assert "hardware was not contacted" in app.model.status
        ui.click("start")
        assert "initialize the selected device first" in app.model.status
    finally:
        app.close()


def wait_for_run(app, timeout: float = 30.0) -> None:
    """Draw frames until the finite simulator has published its pipeline result."""
    end = time.monotonic() + timeout
    while app.model.running and time.monotonic() < end:
        app.draw(RecordingPainter(), 0, 0, 1200, 800)
        time.sleep(0.01)
    assert not app.model.running, "finite simulator did not finish"
    app.model.poll()


@pytest.fixture
def app():
    """Create a native app with temporary, in-memory simulator state."""
    from chisurf.plugins.core.acq.gui.app import AcquisitionApp

    application = AcquisitionApp()
    yield application
    application.close()


@pytest.fixture
def ui(app):
    """Drive the app only with native input events and rendered rectangles."""
    driver = Driver(app, (1200, 800))
    driver.draw(3)
    return driver


def test_make_app_builds_a_safe_simulator_by_default():
    """The native factory starts in simulation mode and never contacts hardware."""
    from chisurf.plugins.core.acq.gui.app import make_app

    app = make_app()
    try:
        assert app.model.source == "simulation"
        assert app.model.hardware_contacted is False
    finally:
        app.close()


def test_finite_simulation_uses_the_existing_pipeline_and_is_deterministic(app):
    """Actual simulator records produce repeatable, non-invented pipeline state."""
    assert app.model.start()
    wait_for_run(app)
    first = app.model.snapshot
    assert first is not None
    assert 256 <= first["total_photons"] <= 257
    assert sum(first["channel_totals"]) == first["total_photons"]
    assert first["phasor"] is not None
    assert first["burst_count"] is not None
    assert np.asarray(first["decay_data"][0]).sum() > 0
    assert first["mcs_trace"] is not None
    first_decay = np.asarray(first["decay_data"][0]).copy()
    app.model.clear()
    assert app.model.snapshot is None
    assert app.model.start()
    wait_for_run(app)
    assert app.model.snapshot is not None
    np.testing.assert_array_equal(app.model.snapshot["decay_data"][0], first_decay)
    assert app.model.hardware_contacted is False


def test_cancel_clear_reset_and_persistence_are_safe_state_transitions(app):
    """Cancellation and resets never turn the simulator into a device operation."""
    assert app.model.cancel() is False
    assert "No simulator run" in app.model.status
    app.model.photon_limit = 77
    app.model.brightness_khz = 777.0
    app.model.seed = 77
    settings = app.export_settings()
    app.model.reset()
    assert app.model.photon_limit == 256 and app.model.snapshot is None
    app.restore_settings(settings)
    assert app.model.photon_limit == 77
    assert app.model.brightness_khz == 777.0
    assert app.model.seed == 77
    assert app.model.hardware_contacted is False


def test_factory_import_is_qt_free():
    """The native app imports and renders with Qt modules forbidden."""
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("acq", "chisurf.plugins.core.acq.gui.app:make_app")
    assert result["ok"], result["output"]


def test_real_native_input_configures_runs_reads_tabs_and_clears(ui):
    """Pointer and keyboard input operates every simulation result surface."""
    ui.type_into("photon_limit", "128")
    ui.type_into("brightness_khz", "420")
    ui.type_into("seed", "42")
    ui.click("start")
    wait_for_run(ui.app)
    assert ui.app.model.snapshot is not None
    assert 128 <= ui.app.model.snapshot["total_photons"] <= 129
    assert any("Simulation acquisition complete" in text for text in ui.strings())
    assert any(text.startswith("Photons: ") for text in ui.strings())
    ui.click_text("Correlation")
    assert any("Lag (ms)" in text for text in ui.strings())
    ui.click_text("Count rate")
    assert any("Count rate (cps)" in text for text in ui.strings())
    ui.click_text("Decay")
    assert any("Time (ns)" in text for text in ui.strings())
    ui.click("clear")
    assert ui.app.model.snapshot is None
    assert any("No result yet" in text for text in ui.strings())
    ui.click("reset")
    assert ui.app.model.photon_limit == 256


def test_real_native_input_exercises_cancel_help_and_guide(ui):
    """Pointer clicks visit Stop, Help, and Guide without a hardware action."""
    ui.type_into("photon_limit", "4096")
    ui.click("start")
    ui.draw(1)
    ui.click("stop")
    assert ui.app.model.cancel_requested is True
    wait_for_run(ui.app)
    assert "cancelled" in ui.app.model.status.lower()
    ui.click("help")
    assert any("Acquisition" in text for text in ui.strings())
    ui.click_text("×", last=True)
    ui.click("guide")
    assert any("Select source" in text for text in ui.strings())
    ui.click_text("Next ►", last=True)
    ui.click_text("Close Tour", last=True)
    assert ui.app.model.hardware_contacted is False


def test_real_native_input_exercises_settings_output_advanced_and_visibility(tmp_path):
    """Every generic native control is driven through pointer/keyboard input."""
    from chisurf.plugins.core.acq.gui.app import AcquisitionApp, AcquisitionNativeModel

    settings_path = tmp_path / "acquisition.json"

    def path_for(action):
        return settings_path if action in {"save", "load"} else None

    app = AcquisitionApp(AcquisitionNativeModel(settings_path_provider=path_for))
    try:
        ui = Driver(app, (1200, 800))
        ui.draw(3)
        ui.type_into("time_limit_s", "12")
        ui.type_into("photon_limit", "128")
        for name, value in zip(("channel_0", "channel_1", "channel_2", "channel_3"), (8, 0, 9, 1)):
            ui.type_into(name, str(value))
        ui.type_into("output_folder", str(tmp_path / "output"))
        ui.click("output_browse")
        assert app.dialog is not None
        ui.click_text("Cancel", last=True)
        ui.click("save_settings")
        assert settings_path.exists()
        ui.click("reset")
        ui.click("load_settings")
        assert app.model.channels == (8, 0, 9, 1)
        settings_path.write_text("{not JSON", encoding="utf-8")
        ui.click("load_settings")
        assert "Settings load rejected" in app.model.status
        ui.click("open_advanced_settings")
        ui.type_into("advanced_json", "{")
        ui.click("apply_advanced_settings")
        assert "Simulation settings rejected" in app.model.status
        ui.click("cancel_advanced_settings")
        ui.click("open_advanced_settings")
        ui.click("apply_advanced_settings")
        assert "validated" in app.model.status
        ui.click("show_macrotime")
        ui.click("show_mcs")
        ui.click("start")
        wait_for_run(app)
        for tab in ("Decay", "Correlation", "Count rate", "MCS", "Macrotime"):
            ui.click_text(tab)
        ui.click("clear")
    finally:
        app.close()


def test_every_native_control_has_a_tooltip():
    """Inventory the app after a real render and reject unhelpful controls."""
    from chisurf.plugins.core.acq.gui.app import AcquisitionApp
    from test.gui.emtk_port_parity import emtk_inventory

    application = AcquisitionApp()
    try:
        assert application.model.start()
        wait_for_run(application)
        inventory = emtk_inventory(application)
    finally:
        application.close()
    assert inventory["controls_without_tooltip"] == []


class FakeBHSetupAdapter:
    """Deterministic direct-BH contract double for native setup coverage."""

    def __init__(self):
        self.values = {}
        self.calls = []

    def detect_cards(self, simulation=False):
        self.calls.append(("detect_cards", simulation))
        return [
            {"module_number": 0, "status": "Initialized", "active": True},
            {"module_number": 1, "status": "Unavailable", "active": False},
        ]

    def get_parameter(self, module, parameter):
        from chisurf.plugins.core.acq.gui.setup_models import BH_PARAMETER_IDS

        name = next(name for name, value in BH_PARAMETER_IDS.items() if value == parameter)
        self.calls.append(("get_parameter", module, name))
        defaults = {
            "TAC_GAIN": 1,
            "STOP_ON_TIME": 1,
            "STOP_ON_OVFL": 1,
            "MACRO_TIME_CLK": 1,
            "MODE": 1,
            "ROUTING_MODE": 1,
            "ADC_RESOLUTION": 6,
        }
        return self.values.get((module, name), defaults.get(name, 1.0))

    def set_parameter(self, module, parameter, value):
        from chisurf.plugins.core.acq.gui.setup_models import BH_PARAMETER_IDS

        name = next(name for name, identifier in BH_PARAMETER_IDS.items() if identifier == parameter)
        self.calls.append(("set_parameter", module, name, value))
        self.values[module, name] = value

    def set_active_cards(self, cards):
        self.calls.append(("set_active_cards", list(cards)))


def test_native_bh_setup_model_uses_the_retained_direct_device_contract(tmp_path):
    """BH read/apply/save/load is based on the legacy get/set parameter API."""
    from chisurf.plugins.core.acq.gui.setup_models import BHSetupModel

    fake = FakeBHSetupAdapter()
    setup = BHSetupModel(fake)
    setup.detect_cards()
    setup.read_parameters()
    assert ("detect_cards", False) in fake.calls
    assert len([call for call in fake.calls if call[0] == "get_parameter"]) == 24
    setup.values["CFD_LIMIT_LOW"] = -40.0
    setup.active_cards = [0]
    assert setup.apply() is True
    assert ("set_active_cards", [0]) in fake.calls
    assert ("set_parameter", 0, "CFD_LIMIT_LOW", -40.0) in fake.calls
    path = tmp_path / "bh.json"
    assert setup.save_json(path)
    setup.values["CFD_LIMIT_LOW"] = 0.0
    assert setup.load_json(path)
    assert setup.values["CFD_LIMIT_LOW"] == -40.0


def test_device_setup_real_native_click_path_opens_and_cancels_for_all_devices():
    """The visible Device Setup action opens only native cards for each source."""
    from chisurf.plugins.core.acq.gui.app import AcquisitionApp, AcquisitionNativeModel

    fake = FakeBHSetupAdapter()
    app = AcquisitionApp(AcquisitionNativeModel(device_factory=lambda _kind: fake))
    try:
        ui = Driver(app, (1200, 800))
        ui.draw(3)
        for label, kind in (("Simulation", "SIMULATION"), ("Becker-Hickl", "BH_SPC"), ("PicoQuant", "PICOQUANT")):
            ui.click("device_type")
            ui.click_text(label, last=True)
            ui.click("open_device_setup")
            assert app.setup_open is True
            assert app.setup_kind == kind
            if kind == "SIMULATION":
                ui.type_into("simulation_setup_json", "{")
                ui.click("setup_apply")
                assert "rejected" in app.setup_model.status
            elif kind == "PICOQUANT":
                ui.click("pico_status")
                ui.click("pico_max_photons", fx=0.01)
                ui.click("setup_apply")
                assert app.model.photon_limit == 100_000
            ui.click("setup_cancel")
            assert app.setup_open is False
    finally:
        app.close()


def test_real_native_bh_setup_clicks_every_retained_group_and_apply_path():
    """Pointer input drives all BH setup tabs and the direct adapter effects."""
    from chisurf.plugins.core.acq.gui.app import AcquisitionApp, AcquisitionNativeModel

    fake = FakeBHSetupAdapter()
    app = AcquisitionApp(AcquisitionNativeModel(device_factory=lambda _kind: fake))
    try:
        ui = Driver(app, (1200, 800))
        ui.draw(3)
        ui.click("device_type")
        ui.click_text("Becker-Hickl")
        app.model.device = fake
        ui.click("open_device_setup")
        ui.click("bh_detect")
        ui.click("bh_simulation")
        for tab, field in (
            ("CFD", "bh_CFD_LIMIT_LOW"),
            ("Sync", "bh_SYNC_FREQ_DIV"),
            ("TAC", "bh_TAC_RANGE"),
            ("Timing", "bh_COLLECT_TIME"),
            ("Mode", "bh_MODE"),
        ):
            ui.click_text(tab, last=True)
            ui.rect(field)
        ui.click("bh_read")
        ui.click("setup_apply")
        assert any(call[0] == "set_active_cards" for call in fake.calls)
        assert len([call for call in fake.calls if call[0] == "set_parameter"]) == 24
        ui.click("setup_cancel")
    finally:
        app.close()


def test_picoquant_and_simulation_setup_models_preserve_retained_apply_semantics():
    """PicoQuant stays truthful while simulation validates its real backend dictionary."""
    from chisurf.plugins.core.acq.gui.app import AcquisitionNativeModel
    from chisurf.plugins.core.acq.gui.setup_models import PicoQuantSetupModel, SimulationSetupModel

    acquisition = AcquisitionNativeModel()
    pico = PicoQuantSetupModel(None, 5000)
    pico.detect_status()
    assert "no physical device status" in pico.status.lower()
    assert pico.apply(acquisition)
    assert acquisition.photon_limit == 5000
    simulation = SimulationSetupModel(acquisition.simulation_params())
    assert simulation.apply() is not None
    simulation.text = "{"
    assert simulation.apply() is None
    assert "rejected" in simulation.status


class FakeBrickMicAdapter:
    """Deterministic stand-in for the BrickMic wrapper's configuration surface."""

    def __init__(self) -> None:
        self.device = self
        self.channels, self.start_ctr, self.end_ctr = 2, 0, 1
        self.acquisition_rate, self.buffer_size = 1_000_000, 2_000_000
        self.N_ph_per_file = 100_000


def test_native_brickmic_setup_card_reads_applies_and_keeps_channels_consistent():
    """BrickMic gets its own native card; apply writes all six retained settings."""
    from chisurf.plugins.core.acq.gui.setup_models import BrickMicSetupModel

    fake = FakeBrickMicAdapter()
    setup = BrickMicSetupModel(fake)
    assert setup.values["channels"] == 2
    setup.values["start_ctr"], setup.values["end_ctr"] = 3, 7
    setup.values["acquisition_rate"] = 2_500_000
    assert setup.apply() is True
    assert fake.channels == 5  # end - start + 1, as the Qt dialog enforced
    assert fake.start_ctr == 3 and fake.end_ctr == 7
    assert fake.acquisition_rate == 2_500_000
    assert "Applied BrickMic settings" in setup.status


def test_real_native_brickmic_setup_click_path_opens_a_brickmic_card():
    """Selecting BrickMic and opening Device Setup shows the BrickMic card, not the simulator's."""
    from chisurf.plugins.core.acq.gui.app import AcquisitionApp, AcquisitionNativeModel
    from chisurf.plugins.core.acq.gui.setup_models import BrickMicSetupModel

    fake = FakeBrickMicAdapter()
    app = AcquisitionApp(AcquisitionNativeModel(device_factory=lambda _kind: fake))
    try:
        ui = Driver(app, (1200, 800))
        ui.draw(3)
        ui.click("device_type")
        ui.click_text("BrickMic")
        app.model.device = fake
        ui.click("open_device_setup")
        assert app.setup_open is True
        assert app.setup_kind == "BRICKMIC"
        assert isinstance(app.setup_model, BrickMicSetupModel)
        ui.type_into("brickmic_start_ctr", "2")
        ui.click("setup_apply")
        assert fake.start_ctr == 2
        ui.click("setup_cancel")
        assert app.setup_open is False
    finally:
        app.close()
