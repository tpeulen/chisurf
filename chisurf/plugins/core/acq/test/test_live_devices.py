"""The device path through libphacq: a simulated TCSPC unit's events, decoded and recorded as a real
one's are, and its settings described, edited and applied as one flat dict.

Nothing here opens real hardware: the units are phacq's ``fake`` device (a 20 MHz sync, two
inputs) and the Sepia II simulator.
"""

from __future__ import annotations

import time

import numpy as np
import pytest
import tttrlib

from chisurf.plugins.core.acq.live import devices
from chisurf.plugins.core.acq.live.session import RecordSession

phacq = pytest.importorskip("phacq")


def _fake(duration_s=2.0, seed=7):
    """A fake unit: sync 20 MHz on channel 0, two detector inputs at 40 kHz each, 16 ps bins."""
    cfg = phacq.FakeConfig()
    cfg.number_of_channels = 3
    cfg.sync_channel = 0
    cfg.rates_cps = phacq.VectorDouble([20e6, 40e3, 40e3])
    cfg.base_resolution_ps = 16.0
    cfg.micro_time_range = 4096
    cfg.duration_s = duration_s
    cfg.seed = seed
    cfg.serial_number = "FAKE-REC"
    drv = phacq.FakeDriver()
    drv.add_device(cfg)
    dev = drv.open("FAKE-REC")
    dev.initialize(phacq.MeasurementMode.T3, phacq.ReferenceClock.Internal)
    dev.phacq_driver = "fake"
    dev._keep_driver = drv  # the device must not outlive the driver object
    return dev


def test_the_source_takes_its_clocks_from_the_device():
    source = devices.DeviceSource(_fake())
    assert source.info.macro_clock_s == pytest.approx(1 / 20e6)  # T3: one sync period
    assert source.info.micro_res_s == pytest.approx(16e-12)
    assert source.info.n_micro == round(50e-9 / 16e-12)


def test_a_device_without_sync_is_refused():
    cfg = phacq.FakeConfig()
    cfg.number_of_channels = 2
    cfg.rates_cps = phacq.VectorDouble([0.0, 1e3])
    drv = phacq.FakeDriver()
    drv.add_device(cfg)
    dev = drv.open("")
    dev.initialize(phacq.MeasurementMode.T3, phacq.ReferenceClock.Internal)
    with pytest.raises(devices.SourceUnavailable):
        devices.DeviceSource(dev)


@pytest.fixture(scope="module")
def device_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("dev")
    source = devices.DeviceSource(_fake(duration_s=1.0))
    session = RecordSession(source, duration_s=1.0, ptu_path=out / "fake.ptu", name="fake")
    session.start()
    result = session.wait(60)
    assert result is not None and not session.error, session.error
    return session, result


def test_the_device_ends_the_run_and_the_ptu_holds_its_events(device_run):
    session, result = device_run
    tttr = tttrlib.TTTR(str(result.ptu))
    # every event the unit delivered is recorded (two inputs, 40 kHz each, 1 s); the analysis
    # counts the photons of the experiment's detector channels among them
    assert len(tttr) == pytest.approx(80e3, rel=0.05)
    assert 1000 < result.photons <= len(tttr)
    assert tttr.header.macro_time_resolution == pytest.approx(50e-9)
    assert tttr.header.micro_time_resolution == pytest.approx(16e-12)
    assert set(np.unique(tttr.routing_channels)) <= {1, 2}
    assert session.source.status()["dropped"] == 0


def test_stop_from_another_thread_ends_the_run(tmp_path):
    source = devices.DeviceSource(_fake(duration_s=3.0))
    session = RecordSession(source, ptu_path=tmp_path / "stop.ptu")
    session.start()
    time.sleep(0.5)
    session.stop()  # as the UI does
    result = session.wait(30)
    # the fake hands its events out as fast as they are read, so it may be done before the stop
    assert result is not None and result.stop_reason in ("stopped", "source finished")
    assert len(tttrlib.TTTR(str(result.ptu))) >= result.photons


def test_every_setting_is_described_and_round_trips():
    dev = _fake()
    form = devices.settings_form(dev)
    props = dev.schema()["params_schema"]["properties"]
    assert {p["parameter"] for p in props.values()} == set(dev.parameter_names())
    assert props["input_edge[1]"]["enum_labels"] == ["falling", "rising"]
    values = form.params()
    assert set(values) == set(props)
    values["input_level_mv[1]"] = -120
    values["sync_divider"] = 4
    assert devices.apply_settings(dev, values) == []
    assert dev.settings()["input_level_mv[1]"] == -120 and dev.settings()["sync_divider"] == 4


def test_a_refused_value_names_the_setting_and_changes_nothing():
    dev = _fake()
    notes = devices.apply_settings(dev, {"input_level_mv[0]": -10, "sync_divider": 3})
    assert notes and "sync_divider" in notes[0]
    assert dev.settings()["input_level_mv[0]"] == -50  # validated as a whole first
    assert devices.apply_settings(dev, {"no_such": 1}) == ["no_such: not a setting of " +
                                                           devices.device_label(dev)]


def test_the_laser_simulator_opens_through_the_same_layer():
    dev = devices.open_device("sepia:sim:")
    s = dev.settings()
    assert "soft_lock" in s and "pulse_mode[0]" in s
    assert dev.schema()["params_schema"]["properties"]["pulse_mode[0]"]["type"] == "boolean"
    dev.close()


def test_the_record_panel_sends_an_edit_and_reverts_a_refused_one(tmp_path):
    from chisurf.plugins.core.acq.gui.record_app import RecordModel

    model = RecordModel(output_dir=tmp_path / "rec", realtime=False)
    model.device = dev = _fake()
    model._device_form_from_device()  # what Connect does after opening
    group = model.device_form._params_group
    setattr(group, "input_level_mv[1]", -150)
    assert dev.settings()["input_level_mv[1]"] == -150
    assert model.device_values["input_level_mv[1]"] == -150  # what a settings file saves
    setattr(group, "input_level_mv[2]", -5000)  # outside -1200..1200: refused as a whole
    assert dev.settings()["input_level_mv[2]"] == -50
    assert "input_level_mv[2]" in model.device_text
    assert getattr(model.device_form._params_group, "input_level_mv[2]") == -50  # panel reverts
    model.device = None


def test_a_recording_carries_the_device_settings_as_ptu_hardware_tags(tmp_path):
    """The PTU header holds the device's identity and settings under PicoQuant's tag names, so
    a reader (SymPhoTime, ChiSurf's settings recovery) gets the instrument state back."""
    from chisurf.plugins.core.acq.live import settings_file

    dev = _fake(duration_s=0.2)
    dev.apply({"input_level_mv[1]": -120, "input_edge[1]": 1, "input_enable[2]": False})
    source = devices.DeviceSource(dev)
    session = RecordSession(source, duration_s=0.2, ptu_path=tmp_path / "tags.ptu", name="tags")
    session.start()
    assert session.wait(30) is not None
    tags = settings_file.read_ptu_tags(tmp_path / "tags.ptu")
    info = dev.information()
    assert tags["HW_Type"] == info.model                    # the device, not the maker
    assert tags["HW_InpChannels"] == info.number_of_channels  # inputs, without the sync
    assert tags["HWInpChan_TrgLevel(1)"] == -120 and tags["HWInpChan_TrgEdge(1)"] == 1
    assert tags["HWInpChan_Enabled(2)"] is False
    doc, _missing = settings_file.from_ptu_tags({k: v for k, v in tags.items()
                                                 if k != settings_file.CHISURF_SETTINGS_TAG})
    inputs = {c["channel"]: c for c in doc["device"]["inputs"]}
    assert inputs[1]["level_mv"] == -120 and inputs[1]["edge"] == "rising"


def test_a_bh_run_also_writes_spc_and_set(tmp_path):
    """A B&H card's run keeps B&H's own files beside the PTU: the .spc holds the same events
    (tttrlib reads it), the .set the card's settings."""
    dev = _fake(duration_s=0.2)
    dev.phacq_driver = "bh"  # a B&H card, as far as the recording is concerned
    source = devices.DeviceSource(dev)
    session = RecordSession(source, duration_s=0.2, ptu_path=tmp_path / "bh.ptu", name="bh")
    session.start()
    assert session.wait(30) is not None
    ptu = tttrlib.TTTR(str(tmp_path / "bh.ptu"))
    spc = tttrlib.TTTR(str(tmp_path / "bh.spc"), "SPC-130")
    assert (tmp_path / "bh.set").read_bytes()[32:34] == b"UU"  # header_valid 0x5555
    assert len(spc) == len(ptu) > 1000
    assert np.array_equal(np.asarray(spc.macro_times), np.asarray(ptu.macro_times))
    assert np.array_equal(np.asarray(spc.routing_channels), np.asarray(ptu.routing_channels))
