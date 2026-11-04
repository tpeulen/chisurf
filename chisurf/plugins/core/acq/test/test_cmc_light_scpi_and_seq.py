"""Tests for the integrated cmc_light SCPI engine, sequence compiler, and optical sensor.
"""
import pytest
from chisurf.plugins.core.acq.live.cmc_light import (
    Calibration,
    Instrument,
    LaserSource,
    Reading,
    ScpiError,
    Sensor,
    alex_steps,
    format_csv,
    format_steps,
    make_instrument,
    parse_steps,
)
from chisurf.plugins.core.acq.live.cmc_light import preview_edit as pe
from chisurf.plugins.core.acq.live.cmc_light import seqcore


def test_integrated_cmc_scpi_command_set():
    """SCPI protocol commands work on the in-tree instrument model."""
    inst = make_instrument()
    assert inst.handle("*IDN?").startswith("CMC,LIGHT-3-SIM,SIM,")
    assert inst.handle("SYST:ERR?") == '0,"No error"'

    # OBIS power and emission commands
    inst.handle("SOURce2:POWer 0.42")
    assert inst.handle("SOUR2:POW?") == "0.4200"
    assert inst.handle("SOURce2:POWer:LEVel:IMMediate:AMPLitude?") == "0.4200"

    # Channel out of range produces standard SCPI error -222
    inst.handle("SOURce4:AM:STAT ON")
    assert inst.handle("SYST:ERR?").startswith("-222,")


def test_integrated_cmc_alex_sequence_compilation():
    """Sequence compiler generates microsecond edge tables and respects periods."""
    steps = alex_steps(3, 20, 5)
    assert steps == [(20, 1), (5, 0), (20, 2), (5, 0), (20, 4), (5, 0)]
    total_us = sum(s[0] for s in steps)
    assert total_us == 75

    # Compile into microsecond edge program using GPIOs [5, 4, 0]
    prog = seqcore.compile_program(
        steps,
        gpios=[5, 4, 0],
        enabled=[True, True, True],
        powers=[1.0, 1.0, 1.0],
        pwm_period_us=100,
        min_pulse_us=1,
        active_high=True,
        sync_gpio=14,
        sync_us=1,
    )
    assert prog["period"] == 75
    assert len(prog["times"]) > 0


def test_integrated_cmc_steps_text_parser_and_formatter():
    """Text format for sequence editing and round-tripping."""
    text = "20us 1; 5us; 20us 2; 5us; 20us 3; 5us"
    steps = parse_steps(text, ["1", "2", "3"])
    assert steps == [(20, 1), (5, 0), (20, 2), (5, 0), (20, 4), (5, 0)]

    formatted = format_steps(steps, ["1", "2", "3"])
    assert "20 1" in formatted
    assert "5 -" in formatted

    # CSV format
    csv_str = format_csv(steps, ["Blue", "Green", "Red"])
    assert "duration_us" in csv_str
    assert "Blue" in csv_str


def test_integrated_cmc_preview_windows_and_dragging():
    """Preview windows and interactive dragging of boundary edges."""
    steps = [(1000, 1), (500, 0), (1000, 2), (500, 4)]
    wins = pe.laser_windows(steps, 3)
    assert wins == [[(0, 1000)], [(1500, 2500)], [(2500, 3000)]]
    assert pe.steps_from_windows(wins, 3000) == steps

    # Drag boundary trades between neighbours
    assert pe.drag_boundary([1000, 500, 1000], 1, 300, lo=20) == [1300, 200, 1000]


def test_integrated_cmc_sensor_calibration_model():
    """Camera sensor power calibration model."""
    cal = Calibration()
    assert cal.sensor == ""
    assert isinstance(cal.response, dict)
    assert isinstance(cal.absolute, dict)
    assert isinstance(cal.crosstalk, dict)
