"""The simulator's laser behaviour: default powers, run-time emission, and the light gate.

Owner contract (2026-11-01): the default powers are 60 µW blue (488 nm) and 25 µW red
(640 nm); starting an acquisition turns the simulated emission on; with the laser off
no excitation-driven photon (FRET, donor-only, acceptor-only, aggregate) may pass —
only dark counts, and only while a detection path is open.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.core.acq.gui.record_app import RecordModel
from chisurf.plugins.core.acq.live.instrument_sim import (
    DEFAULT_LASER_TARGETS_UW,
    SimulationRig,
    laser_diode_drive_for_power,
    laser_diode_power_fraction,
    laser_diode_threshold,
)


def test_the_drive_inverse_returns_the_power_that_is_asked_for():
    for threshold in (35.0, 47.0):
        for target_uw in (10.0, 25.0, 60.0, 250.0, 1000.0):
            drive = laser_diode_drive_for_power(target_uw, 1000.0, threshold)
            delivered = laser_diode_power_fraction(drive, threshold) * 1000.0
            assert delivered == pytest.approx(target_uw, rel=0.01), (threshold, target_uw)


def test_connect_sets_the_default_powers_60uw_blue_25uw_red(tmp_path):
    m = RecordModel(output_dir=tmp_path, realtime=False)
    assert m.connect_instrument_simulator()
    try:
        state = m.laser.state()
        for head in state.heads:
            target = DEFAULT_LASER_TARGETS_UW[int(head.wavelength_nm or 0)]
            assert m.power_targets_uw[head.slot] == pytest.approx(target), head.name
            # the targets wait while idle: zero drive keeps the passive dark capture honest
            assert head.intensity_pct == 0.0, head.name
        assert state.emission_blocked  # light waits for the run
    finally:
        m.close()


def test_starting_a_run_switches_the_simulated_emission_on(tmp_path):
    m = RecordModel(output_dir=tmp_path, realtime=False)
    assert m.connect_instrument_simulator()
    try:
        assert m.laser.state().emission_blocked
        m.stop_after = True
        assert m.start()
        state = m.laser.state()
        assert not state.emission_blocked
        for head in state.heads:
            target = DEFAULT_LASER_TARGETS_UW[int(head.wavelength_nm or 0)]
            power = laser_diode_power_fraction(head.intensity_pct, laser_diode_threshold(head)) * 1000.0
            assert power == pytest.approx(target, rel=0.01), head.name
        m.stop()
        for _ in range(100):
            m.poll(force=True)
            if not m.busy:
                break
            time.sleep(0.1)
    finally:
        m.close()


def test_no_excitation_driven_photon_passes_with_the_laser_off():
    """The gate must scale EVERY labeled molecule photon, not only the FRET species.

    Donor-only, acceptor-only and aggregate states carry truth labels beyond the FRET
    populations; before the fix they bypassed the gate and bursted in the dark.
    """
    rig = SimulationRig()
    try:
        rig.laser.set_emission(False)  # fully off, whatever the drive
        source = rig.source(populations=None, seed=7, realtime=False, duration_s=2.0)
        source.start()
        labeled = total = 0
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline and total < 5000:
            batch = source.read(timeout=0.5)
            if batch is None:
                if source.finished:
                    break
                continue
            total += len(batch)
            if batch.truth is not None:
                labeled += int((batch.truth >= 0).sum())
        source.stop()
        assert labeled == 0, f"{labeled} excitation-driven photons passed with the laser off"
        assert total == 0, "with every shutter closed nothing may be delivered at all"
    finally:
        rig.close()


def test_the_default_powers_show_the_calibrated_sample(tmp_path):
    """At 60/25 µW the rig's relative gain is 1.0: the canonical burst view (SIMULATION ONLY)."""
    rig = SimulationRig()
    try:
        gains = rig._default_gains
        state = rig.laser.state()
        for head in state.heads:
            drive = laser_diode_drive_for_power(
                DEFAULT_LASER_TARGETS_UW[int(head.wavelength_nm or 0)], 1000.0,
                laser_diode_threshold(head))
            relative = laser_diode_power_fraction(drive, laser_diode_threshold(head)) / gains[head.output]
            assert relative == pytest.approx(1.0)
    finally:
        rig.close()
