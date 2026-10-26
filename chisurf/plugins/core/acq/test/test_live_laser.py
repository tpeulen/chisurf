"""Laser control: the safety rules, the simulated driver, and the PIE windows a program implies."""

from __future__ import annotations

import sys

import pytest

from chisurf.plugins.core.acq.live import laser as L


def _pie_program() -> dict:
    """Two heads interleaved: 485 nm in slot 1, 640 nm in slot 2, 80 MHz / 4 = 20 MHz pulses."""
    return {
        "heads": [
            {"slot": 200, "output": 0, "enabled": True, "intensity_pct": 40.0},
            {"slot": 300, "output": 1, "enabled": True, "intensity_pct": 25.0},
        ],
        "oscillator": {
            "base_hz": 80e6,
            "divider": 4,
            "burst_lengths": [1, 1, 0, 0, 0, 0, 0, 0],
            "output_enabled": [True, True] + [False] * 6,
            "sync_enabled": [True] + [False] * 7,
        },
    }


def test_outputs_are_off_after_open_and_apply_keeps_them_off() -> None:
    sim = L.SimLaser()
    st = sim.open()
    assert st.emission_blocked
    st = sim.apply(_pie_program())
    assert st.emission_blocked, "applying a program must not switch the light on"
    assert st.oscillator.divider == 4 and st.oscillator.burst_lengths[:2] == [1, 1]
    assert [h.intensity_pct for h in st.heads] == [40.0, 25.0]
    sim.set_emission(True)
    assert not sim.state().emission_blocked
    sim.close()
    assert sim.events[-2:] == ["emission off", "close"], "closing switches the light off first"


def test_an_error_switches_the_light_off() -> None:
    sim = L.SimLaser()
    sim.open()
    sim.apply(_pie_program())
    sim.set_emission(True)
    with pytest.raises(L.LaserError, match="outputs switched off"):
        sim.set_head(999, intensity_pct=10.0)
    assert sim.state().emission_blocked
    with pytest.raises(L.LaserError, match="outside 0..100"):
        sim.set_head(200, intensity_pct=140.0)


def test_laser_off_never_raises() -> None:
    sim = L.SimLaser()
    sim.laser_off()  # not open: still fine
    sim.open()
    sim._set_emission = lambda on: (_ for _ in ()).throw(RuntimeError("usb gone"))  # noqa: SLF001
    sim.laser_off()
    assert sim._state.emission_blocked  # noqa: SLF001


def test_capture_round_trips_through_apply() -> None:
    a = L.SimLaser()
    a.open()
    a.apply(_pie_program())
    prog = a.capture()
    assert prog["repetition_rate_hz"] == pytest.approx(20e6)
    b = L.SimLaser()
    b.open()
    b.apply(prog)
    assert b.capture()["oscillator"] == prog["oscillator"]
    assert [h["intensity_pct"] for h in b.capture()["heads"]] == [40.0, 25.0]


def test_pie_windows_from_the_laser_program() -> None:
    prog = _pie_program()
    prog["heads"][0]["wavelength_nm"], prog["heads"][1]["wavelength_nm"] = 485, 640
    # 20 MHz pulses, two slots -> 100 ns sequence; 25 ps channels -> 2000 per slot.
    patch = L.propose_pie_windows(prog, 25e-12)
    assert patch["windows"] == {"prompt": [0, 2000], "delayed": [2000, 4000]}
    assert patch["sync_period_s"] == pytest.approx(100e-9)
    assert [s["wavelength_nm"] for s in patch["excitation"]] == [485, 640]
    # A sync offset shifts both windows; clipping keeps them inside the micro-time range.
    shifted = L.propose_pie_windows(prog, 25e-12, sync_offset_s=10e-9, n_micro=3000)
    assert shifted["windows"] == {"prompt": [0, 1600], "delayed": [1600, 3000]}
    # Three excitations are named by wavelength.
    prog["heads"].append({"slot": 400, "output": 2, "wavelength_nm": 405})
    prog["oscillator"]["burst_lengths"][2] = 1
    prog["oscillator"]["output_enabled"][2] = True
    assert list(L.propose_pie_windows(prog, 25e-12)["windows"]) == ["ex485", "ex640", "ex405"]


def test_a_disabled_output_gives_no_window() -> None:
    prog = _pie_program()
    prog["oscillator"]["output_enabled"][1] = False
    assert list(L.propose_pie_windows(prog, 25e-12, names=["blue"])["windows"]) == ["blue"]


def test_sepia_backend_reports_why_it_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(L, "_candidate_libraries", lambda explicit=None: [])
    ok, why = L.sepia_available()
    assert not ok and why.startswith("not available")
    if sys.platform == "darwin":
        assert "Windows only" in why
    with pytest.raises(L.LaserError, match="not available"):
        L.SepiaBackend().open()
    assert isinstance(L.open_laser("auto"), L.SimLaser)


def test_frequency_parsing_of_the_decoded_mode() -> None:
    assert L._parse_frequency("internal 80.00 MHz") == pytest.approx(80e6)  # noqa: SLF001
    assert L._parse_frequency("ext. rising edge") is None  # noqa: SLF001
