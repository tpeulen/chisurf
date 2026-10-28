"""The MT200 profiles through phacq's snAPI backend (PicoQuant units on Windows), and loading a
settings file in the Record tool: it connects the hardware it names, and the device's thresholds and
shifts stay behind *Advanced*.

snAPI itself is Windows-only, so a fake records the calls phacq makes on it.
"""

from __future__ import annotations

import sys
import types

import pytest

phacq = pytest.importorskip("phacq")
snapi = pytest.importorskip("phacq.snapi")

from chisurf.plugins.core.acq.live import devices, settings_file  # noqa: E402


class _Calls:
    def __init__(self, calls):
        self.calls = calls

    def __getattr__(self, name):
        def call(*args):
            self.calls.append((name, args))
            return True
        return call

    def getCountRates(self):
        return [20_000_000, 1000, 0, 2000, 0]       # sync, then four inputs


class FakeSnapi:
    """A HydraHarp 400 with four inputs, as snAPI shows it after initDevice."""

    def __init__(self):
        self.calls = []
        self.device = _Calls(self.calls)
        self.raw = _Calls(self.calls)
        self.deviceConfig = {"ID": "1032692", "NumChans": 0, "Model": ""}
        self.deviceIDs = ["1032692"]

    def getDeviceIDs(self):
        return True

    def getDevice(self, *dev):
        return True

    def initDevice(self, mode, ref):
        self.deviceConfig = {"ID": "1032692", "NumChans": 4, "Model": "HydraHarp 400",
                             "PartNo": "930021"}
        return True

    def getDeviceConfig(self):
        pass

    def closeDevice(self, allDevices=True):
        pass


@pytest.fixture
def fake(monkeypatch):
    main = types.ModuleType("snAPI.Main")
    main.MeasMode = types.SimpleNamespace(T2=2, T3=3)
    main.RefSource = types.SimpleNamespace(Internal=0, External_10MHZ=1)
    pkg = types.ModuleType("snAPI")
    pkg.Main = main
    monkeypatch.setitem(sys.modules, "snAPI", pkg)
    monkeypatch.setitem(sys.modules, "snAPI.Main", main)
    api = FakeSnapi()
    return api, snapi.SnapiDriver(lambda: api)


def _profile(stem):
    path = next(p for p, _n in settings_file.shipped_profiles() if p.stem == stem)
    return settings_file.load(path)


def test_a_profile_sends_its_thresholds_and_shifts_through_snapi(fake):
    api, driver = fake
    dev = driver.open("")
    dev.phacq_driver = "picoquant"
    notes = settings_file.apply(_profile("mt200_pie"), device=dev)
    assert notes == []
    calls = api.calls
    assert ("setSyncDiv", (4,)) in calls
    assert ("setSyncChannelOffset", (5000,)) in calls             # sync shift
    assert ("setSyncCFD", (350, 10)) in calls                     # sync threshold
    assert ("setInputChannelOffset", (0, 130)) in calls           # input shifts, on their inputs
    assert ("setInputChannelOffset", (2, -40)) in calls
    assert ("setInputCFD", (0, 250, 10)) in calls                 # input thresholds
    assert ("setInputCFD", (2, 250, 10)) in calls
    assert ("setBinning", (5,)) in calls
    s = dev.settings()
    assert s["input_offset_ps[2]"] == -40 and s["sync_offset_ps"] == 5000
    assert dev.information().number_of_channels == 4 and dev.information().base_resolution_ps == 32


def test_loading_settings_connects_the_device_and_keeps_the_form_behind_advanced(
        fake, monkeypatch, tmp_path):
    from chisurf.plugins.core.acq.gui.record_app import RecordModel
    from chisurf.plugins.core.acq.live import laser as laser_mod

    api, driver = fake
    entry = devices.DeviceEntry("picoquant", "1032692", "PicoQuant", "HydraHarp 400")
    monkeypatch.setattr(devices, "find_device", lambda key="", drivers=None: entry)
    monkeypatch.setattr(devices, "attached_devices", lambda drivers=None: [entry])

    def open_device(e, mode=None):
        dev = driver.open(e.serial)
        dev.initialize(phacq.MeasurementMode.T3, phacq.ReferenceClock.Internal)
        dev.phacq_driver = "picoquant"
        return dev

    monkeypatch.setattr(devices, "open_device", open_device)
    monkeypatch.setattr(laser_mod, "sepia_available", lambda: (False, "no Sepia II on this PC"))

    model = RecordModel(output_dir=tmp_path / "rec", realtime=False)
    model.source_kind = "device"
    assert model.device_form_hidden                     # Advanced is off by default
    model.advanced = True
    assert not model.device_form_hidden
    model.advanced = False

    key = next(k for k, label in model.settings_options()
               if k.startswith("profile:") and "PIE" in label)
    model.settings_address = key
    assert model.load_settings()
    assert model.device is not None                     # connected by loading the file
    assert ("setInputChannelOffset", (2, -40)) in api.calls
    # the file is for the Sepia II: no simulated laser stands in for it
    assert not model.laser_connected
    assert "no Sepia II on this PC" in model.settings_detail


def test_a_file_for_another_unit_connects_nothing_and_says_which(fake, monkeypatch, tmp_path):
    from chisurf.plugins.core.acq.gui.record_app import RecordModel
    from chisurf.plugins.core.acq.live import laser as laser_mod

    other = devices.DeviceEntry("picoquant", "9999999", "PicoQuant", "HydraHarp 400")
    monkeypatch.setattr(devices, "attached_devices", lambda drivers=None: [other])
    opened = []
    monkeypatch.setattr(devices, "open_device", lambda e, mode=None: opened.append(e))
    monkeypatch.setattr(laser_mod, "sepia_available", lambda: (False, "none"))
    model = RecordModel(output_dir=tmp_path / "rec", realtime=False)
    model.source_kind = "device"
    model.settings_address = next(k for k, label in model.settings_options()
                                  if k.startswith("profile:") and "PIE" in label)
    assert model.load_settings()
    assert opened == [] and model.device is None
    assert "HydraHarp 400 1032692 is not attached" in model.settings_detail


def test_the_device_a_section_is_for(monkeypatch):
    units = [devices.DeviceEntry("picoquant", "111", "PicoQuant", "MultiHarp 150"),
             devices.DeviceEntry("picoquant", "1032692", "PicoQuant", "HydraHarp 400"),
             devices.DeviceEntry("bh", "SPC-1", "Becker & Hickl", "SPC-150")]
    monkeypatch.setattr(devices, "attached_devices", lambda drivers=None: units)
    assert devices.device_for({"driver": "picoquant", "serial": "1032692"}).serial == "1032692"
    assert devices.device_for({"driver": "picoquant", "model": "HydraHarp 400"}).serial == "1032692"
    assert devices.device_for({"driver": "bh"}).serial == "SPC-1"
    assert devices.device_for({"driver": "picoquant", "serial": "nope"}) is None


def test_choosing_a_profile_loads_it_with_progress(fake, monkeypatch, tmp_path):
    """Picking a settings file in the list loads it at once, in a worker thread, and says what
    it is connecting to."""
    from chisurf.plugins.core.acq.gui.record_app import RecordModel
    from chisurf.plugins.core.acq.live import laser as laser_mod

    api, driver = fake
    entry = devices.DeviceEntry("picoquant", "1032692", "PicoQuant", "HydraHarp 400")
    monkeypatch.setattr(devices, "attached_devices", lambda drivers=None: [entry])

    def open_device(e, mode=None):
        dev = driver.open(e.serial)
        dev.initialize(phacq.MeasurementMode.T3, phacq.ReferenceClock.Internal)
        dev.phacq_driver = "picoquant"
        return dev

    monkeypatch.setattr(devices, "open_device", open_device)
    monkeypatch.setattr(laser_mod, "sepia_available", lambda: (False, "none"))
    model = RecordModel(output_dir=tmp_path / "rec", realtime=False)
    model.source_kind = "device"
    steps = []
    real = model._progress
    model._progress = lambda f, t: (steps.append(t), real(f, t))
    model.settings_address = next(k for k, label in model.settings_options()
                                  if k.startswith("profile:") and "PIE" in label)
    assert model.settings_chosen()
    model.wait_connected(30)
    assert not model.connecting and model.connect_text == ""
    assert model.device is not None
    assert any("Connecting to" in s and "1032692" in s for s in steps)
    assert any("Applying" in s for s in steps)
    # a measurement row is not loaded by picking it
    model.settings_address = "photons:somewhere.ptu"
    assert not model.settings_chosen()


def test_the_last_settings_are_loaded_again_on_start(fake, monkeypatch, tmp_path):
    from chisurf.plugins.core.acq.gui.record_app import RecordApp, RecordModel
    from chisurf.plugins.core.acq.live import laser as laser_mod

    api, driver = fake
    entry = devices.DeviceEntry("picoquant", "1032692", "PicoQuant", "HydraHarp 400")
    monkeypatch.setattr(devices, "attached_devices", lambda drivers=None: [entry])
    monkeypatch.setattr(devices, "open_device", lambda e, mode=None: (
        lambda d: (d.initialize(phacq.MeasurementMode.T3, phacq.ReferenceClock.Internal),
                   setattr(d, "phacq_driver", "picoquant"), d)[-1])(driver.open(e.serial)))
    monkeypatch.setattr(laser_mod, "sepia_available", lambda: (False, "none"))

    first = RecordApp(RecordModel(output_dir=tmp_path / "rec", realtime=False))
    first.model.source_kind = "device"
    first.model.settings_address = next(k for k, label in first.model.settings_options()
                                        if k.startswith("profile:") and "PIE" in label)
    saved = first.export_settings()
    assert saved["settings_address"].startswith("profile:") and saved["advanced"] is False

    again = RecordApp(RecordModel(output_dir=tmp_path / "rec2", realtime=False))
    again.restore_settings(saved)
    again.model.wait_connected(30)
    assert again.model.device is not None
    from pathlib import Path

    assert again.model.settings_name == Path(saved["settings_address"].split(":", 1)[1]).name

    # a simulation session restores the choice but connects nothing
    sim = RecordApp(RecordModel(output_dir=tmp_path / "rec3", realtime=False))
    sim.restore_settings({**saved, "source_kind": "simulator"})
    assert not sim.model.connecting and sim.model.device is None
