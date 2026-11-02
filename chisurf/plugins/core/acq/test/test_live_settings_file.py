"""Acquisition settings files: the JSON document, applying it, and reading it back out of measurements."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chisurf.plugins.core.acq.live import settings_file as S
from chisurf.plugins.core.acq.live.laser import SimLaser

ROOT = Path(__file__).resolve().parents[5]
SP5_PTU = ROOT / "test" / "data" / "clsm" / "Leica_SP5.ptu"
SP5_PTO = ROOT / "test" / "data" / "clsm" / "Leica_SP5.pto"
SP8_PTU = ROOT / "test" / "data" / "clsm" / "Leica_SP8.ptu"


def _doc() -> dict:
    return S.new_settings(
        name="PIE smFRET",
        device={
            "backend": "phacq",
            "mode": "T3",
            "sync": {"divider": 1, "level_mv": -60, "edge": "falling", "offset_ps": 1200},
            "inputs": [
                {"channel": 0, "level_mv": -70, "edge": "falling", "offset_ps": 0, "enabled": True},
                {
                    "channel": 1,
                    "level_mv": -80,
                    "edge": "rising",
                    "offset_ps": 350,
                    "enabled": False,
                },
            ],
            "binning": 2,
            "offset_ns": 0,
        },
        laser={
            "heads": [{"slot": 200, "output": 0, "enabled": True, "intensity_pct": 40.0}],
            "oscillator": {
                "divider": 4,
                "burst_lengths": [1, 1, 0, 0, 0, 0, 0, 0],
                "output_enabled": [True, True] + [False] * 6,
            },
        },
        experiment={
            "preset": "pie",
            "setup": {"detectors": {"G|G": {"chs": [0]}, "R|G": {"chs": [1]}}},
            "burst": {"min_photons": 30, "window_photons": 10, "window_time_ms": 1.0},
        },
        run={"duration_s": 600, "name": "sample", "project_data": "link"},
        future_section={"kept": True},
    )


def test_round_trip_keeps_everything_including_unknown_keys(tmp_path) -> None:
    doc = _doc()
    path = S.save(doc, tmp_path / "pie.json")
    assert json.loads(path.read_text())["schema"] == S.SCHEMA
    back = S.load(path)
    assert back == doc
    assert back["future_section"] == {"kept": True}


def test_validation_lists_every_problem_with_its_path(tmp_path) -> None:
    doc = _doc()
    doc["device"]["mode"] = "T5"
    doc["device"]["sync"]["divider"] = 3
    doc["device"]["inputs"][1]["channel"] = 0
    doc["device"]["inputs"][0]["level_mv"] = "low"
    doc["laser"]["heads"][0]["intensity_pct"] = 120
    doc["laser"]["oscillator"]["burst_lengths"] = [1, 1]
    doc["experiment"]["preset"] = "fcs"
    doc["run"]["project_data"] = "copy"
    problems = S.validate(doc)
    for where in (
        "device.mode",
        "device.sync.divider",
        "device.inputs[1].channel",
        "device.inputs[0].level_mv",
        "laser.heads[0].intensity_pct",
        "laser.oscillator.burst_lengths",
        "experiment.preset",
        "run.project_data",
    ):
        assert any(p.startswith(where) for p in problems), (where, problems)
    (tmp_path / "bad.json").write_text(json.dumps(doc))
    with pytest.raises(S.SettingsError) as err:
        S.load(tmp_path / "bad.json")
    assert len(err.value.problems) == len(problems)
    assert S.validate({"schema": "chisurf.acquisition/2"})[0].startswith("schema: version")
    assert S.validate({"device": {}})[0].startswith("schema: missing")
    with pytest.raises(S.SettingsError, match="not valid JSON"):
        S.loads("{broken")


def _fake_unit(channels: int = 3):
    """phacq's simulated TCSPC unit (sync on channel 0) with its described settings."""
    phacq = pytest.importorskip("phacq")
    cfg = phacq.FakeConfig()
    cfg.number_of_channels = channels
    cfg.rates_cps = phacq.VectorDouble([20e6] + [1e3] * (channels - 1))
    drv = phacq.FakeDriver()
    drv.add_device(cfg)
    dev = drv.open("")
    dev.initialize(phacq.MeasurementMode.T3, phacq.ReferenceClock.Internal)
    dev.phacq_driver = "fake"
    dev._keep_driver = drv
    return dev


def _unit_doc() -> dict:
    doc = _doc()
    doc["device"] = {
        "backend": "phacq",
        "mode": "T3",
        "sync": {"divider": 2},
        "inputs": [
            {"channel": 1, "level_mv": -80, "edge": "rising", "offset_ps": 350, "enabled": False}
        ],
        "binning": 2,
        "settings": {"input_level_mv[2]": -120},
    }
    return doc


def test_apply_and_capture_on_a_phacq_unit_and_laser() -> None:
    dev = _fake_unit()
    sim = SimLaser()
    sim.open()
    notes = S.apply(_unit_doc(), device=dev, laser=sim)
    assert notes == []
    s = dev.settings()
    assert s["sync_divider"] == 2 and s["binning"] == 2 and s["input_level_mv[2]"] == -120
    assert s["input_edge[1]"] == 1 and s["input_offset_ps[1]"] == 350
    assert s["input_enable[1]"] is False
    assert sim.state().emission_blocked, "applying settings never switches the laser on"
    got = S.capture(device=dev, laser=sim, base=_unit_doc())
    assert S.validate(got) == []
    assert got["device"]["backend"] == "phacq" and got["device"]["driver"] == "fake"
    assert got["device"]["settings"] == s, "every setting of the unit is captured"
    assert S.device_settings(got["device"])["input_level_mv[1]"] == -80
    assert got["laser"]["oscillator"]["divider"] == 4
    assert got["experiment"] == _doc()["experiment"], "sections the hardware does not hold are kept"


def test_a_setting_the_device_lacks_is_a_note_not_a_failure() -> None:
    dev = _fake_unit(channels=2)
    notes = S.apply(_unit_doc(), device=dev)
    assert any("input_level_mv[2]" in n for n in notes)
    assert dev.settings()["sync_divider"] == 2, "the settings it has are applied"


def test_a_readable_device_section_translates_to_phacq_names() -> None:
    flat = S.device_settings(_doc()["device"])
    assert flat["sync_level_mv"] == -60 and flat["sync_offset_ps"] == 1200
    assert flat["input_edge[1]"] == 1 and flat["input_enable[1]"] is False
    assert flat["binning"] == 2 and flat["offset_ns"] == 0


@pytest.mark.skipif(not SP5_PTU.exists(), reason="CLSM test data not present")
def test_settings_from_a_symphotime_ptu_with_its_sepia_program() -> None:
    doc, missing = S.from_ptu(SP5_PTU)
    assert S.validate(doc) == []
    dev = doc["device"]
    assert dev["model"] == "TimeHarp260P" and dev["mode"] == "T3"
    assert dev["sync"] == {
        "divider": 8,
        "level_mv": -180,
        "zero_cross_mv": -10,
        "discriminator": "cfd",
        "offset_ps": 10000,
    }
    assert [c["channel"] for c in dev["inputs"]] == [0, 1]
    assert dev["binning"] == 0 and dev["resolution_ps"] == pytest.approx(25.0, abs=1e-3)
    assert dev["measured_sync_rate_hz"] == 20_000_000
    laser = doc["laser"]
    assert laser["oscillator"]["base_hz"] == 80e6 and laser["oscillator"]["divider"] == 4
    assert laser["oscillator"]["burst_lengths"][:2] == [1, 0]
    assert (
        laser["heads"][0]["name"].startswith("481.0nm")
        and laser["heads"][0]["intensity_pct"] == 7.0
    )
    assert laser["heads"][0]["wavelength_nm"] == 481.0
    assert doc["run"]["duration_s"] == pytest.approx(36000.0)
    for field in ("device.sync.dead_time_ps", "experiment.setup", "laser.oscillator.delays_ns"):
        assert field in missing


@pytest.mark.skipif(not SP8_PTU.exists(), reason="CLSM test data not present")
def test_settings_from_a_picoharp_ptu_without_a_laser_program() -> None:
    doc, missing = S.from_ptu(SP8_PTU)
    assert doc["device"]["model"] == "PicoHarp" and doc["device"]["binning"] == 2
    assert doc["device"]["inputs"][0]["level_mv"] == 400
    assert "laser" in missing and "laser" not in doc


@pytest.mark.skipif(not SP5_PTO.exists(), reason="CLSM test data not present")
def test_settings_from_a_pto_member_equal_the_ptu() -> None:
    from chisurf.core.fio import pto

    member = pto.Measurement.open(SP5_PTO).photon_member_names()[0]
    doc, missing = S.from_address(f"{SP5_PTO}/{member}")
    ref, ref_missing = S.from_ptu(SP5_PTU)
    assert doc["device"] == ref["device"]
    assert doc["laser"] == ref["laser"]
    assert missing == ref_missing


def test_a_stored_settings_document_wins_over_the_hardware_tags() -> None:
    tags = {"HW_Type": "MultiHarp", "HWSync_Divider": 2, S.CHISURF_SETTINGS_TAG: json.dumps(_doc())}
    doc, missing = S.from_ptu_tags(tags)
    assert doc == _doc() and missing == []


def test_a_settings_file_enters_the_workspace_as_a_setup(tmp_path) -> None:
    from chisurf.core.fio import classify

    path = S.save(_doc(), tmp_path / "acq.json")
    assert classify.classify(path) == "setup"
    (tmp_path / "other.json").write_text(json.dumps({"title": "not a setup"}))
    assert classify.classify(tmp_path / "other.json") != "setup"


@pytest.mark.skipif(not SP5_PTU.exists(), reason="CLSM test data not present")
def test_header_json_booleans_are_reported_never_guessed() -> None:
    import tttrlib

    doc, missing = S.from_header_json(tttrlib.TTTR(str(SP5_PTU)).header.json)
    ref, _ = S.from_ptu(SP5_PTU)
    # Every value it does return agrees with the PTU header read directly ...
    assert doc["device"]["sync"] == ref["device"]["sync"]
    assert doc["laser"]["oscillator"]["divider"] == ref["laser"]["oscillator"]["divider"]
    assert all("enabled" not in c for c in doc["device"]["inputs"])
    # ... and the booleans it could not trust are named.
    assert any(m.startswith("HWInpChan_Enabled") for m in missing)
    assert (
        ref["laser"]["heads"][0]["enabled"] is True
        and ref["device"]["inputs"][0]["enabled"] is True
    )
