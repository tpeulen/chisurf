"""The ALEX Creator's period auto-detection and excitation-range definition, operated with real pointer input.

These are the two capabilities the Creator has lost before (the excitation-range table and its automatic detection),
so every assertion here is against an answer planted in the data and computed independently of the plugin's code:

* a written µs-ALEX stream with a 5000-tick alternation (deliberately not the default 8000 in the Period field), donor
  laser on in [0, 2400) and acceptor laser in [2500, 4900), donor detector 0 and acceptor detector 1;
* the ALEX Suite's own demo measurement (8000 ticks, gates [0, 3900) and [4000, 7900));
* a non-alternating stream, which must be refused rather than given a period.

The converted file's micro-time is checked against ``(macro - shift) mod period`` in numpy, not against the core.
"""

from __future__ import annotations

import time

import numpy as np
import pytest
import tttrlib

from chisurf.plugins.emtk_test_input import CTRL, Driver
from chisurf.plugins.tttr.ptu_alex_creator import core
from chisurf.plugins.tttr.ptu_alex_creator.gui.app import AlexApp

PERIOD = 5000
DONOR_GATE = (0, 2400)
ACCEPTOR_GATE = (2500, 4900)
SIZE = (1100, 720)


def write_stream(path, macro, routing):
    """Write photons as a real SPC-130 container whose micro-time is still empty (an unconverted µs-ALEX file)."""
    stream = tttrlib.TTTR()
    stream.append_events(
        np.asarray(macro, dtype=np.uint64),
        np.zeros(len(macro), dtype=np.uint16),
        np.asarray(routing, dtype=np.int8),
        np.zeros(len(macro), dtype=np.int8),
    )
    header = stream.header
    header.set_macro_time_resolution(12.5e-9)
    header.set_micro_time_resolution(12.5e-9 / 4096)
    assert stream.write(str(path), "SPC-130", header)
    return path


def planted_alex(path, seed=7):
    """A µs-ALEX stream with the module's planted period, gates and detector brightness per laser."""
    rng = np.random.default_rng(seed)
    n = 300_000
    cycle = rng.integers(0, 30_000, n)
    phase = rng.uniform(0, PERIOD, n)
    donor_on = (phase >= DONOR_GATE[0]) & (phase < DONOR_GATE[1])
    acceptor_on = (phase >= ACCEPTOR_GATE[0]) & (phase < ACCEPTOR_GATE[1])
    keep = donor_on | acceptor_on
    phase, cycle, donor_on = phase[keep], cycle[keep], donor_on[keep]
    routing = np.where(
        donor_on, rng.choice(2, phase.size, p=[0.7, 0.3]), rng.choice(2, phase.size, p=[0.05, 0.95])
    )
    macro = (cycle * PERIOD + phase.astype(np.int64)).astype(np.uint64)
    order = np.argsort(macro, kind="stable")
    return write_stream(path, macro[order], routing[order])


def settle(ui, timeout=60.0):
    """Draw frames until every worker (load, measurement, preview) has published."""
    end = time.monotonic() + timeout
    while ui.app.running and time.monotonic() < end:
        time.sleep(0.01)
        ui.draw(1)
    assert not ui.app.running
    ui.draw(3)
    while ui.app.running and time.monotonic() < end:  # the refold the new Period starts
        time.sleep(0.01)
        ui.draw(1)
    return ui.draw(3)


@pytest.fixture
def ui(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "db.sqlite"))
    app = AlexApp(tmp_path / "state.json")
    driver = Driver(app, size=SIZE)
    driver.draw(2)
    yield driver
    app.close()


def load(ui, path):
    assert ui.drop(path)  # one file dropped on the window loads it, as a user would
    settle(ui)
    assert ui.app.model.has_data, ui.app.message


def inside(region, gate, cover=0.75):
    """The region lies in the planted gate and covers most of it (the detector trims a guard off each edge)."""
    lo, hi = region["ranges"][0] if len(region["ranges"]) == 1 else (None, None)
    assert lo is not None, f"a planted gate must not wrap: {region}"
    return gate[0] <= lo < hi <= gate[1] and (hi - lo) >= cover * (gate[1] - gate[0])


def test_the_range_and_detection_controls_are_all_drawn(ui, tmp_path):
    """Tripwire against losing them again: every range / detection control is drawn once a file is loaded."""
    load(ui, planted_alex(tmp_path / "alex.spc"))
    for name in (
        "alex_period",
        "period_shift",
        "detect_period",
        "detector_groups",
        "redetect_regions",
        "region_rows",
    ):
        x, y, w, h = ui.rect(name)
        assert w > 0 and h > 0 and 0 <= x < SIZE[0] and 0 <= y < SIZE[1], name
    assert ui.app.form.tables["region_rows"].control.column_editable("start")
    assert ui.app.form.tables["region_rows"].control.column_editable("stop")


def test_detect_period_is_grey_until_a_file_is_loaded(ui):
    assert not ui.app.enabled("detect_period")
    ui.click_name("detect_period")
    assert ui.app.model.alex_period == 8000 and not ui.app.running


def test_detect_period_measures_the_planted_period_and_the_ranges_follow(ui, tmp_path):
    path = planted_alex(tmp_path / "alex.spc")
    load(ui, path)
    assert ui.app.model.alex_period == 8000  # the default, wrong for this file
    ui.click_name("detect_period")
    settle(ui)
    assert ui.app.model.alex_period == PERIOD, ui.app.message
    assert not ui.app.message_is_error and str(PERIOD) in ui.app.message
    assert len(ui.app.histogram) == PERIOD
    # The ranges were re-detected at the measured period: one per planted laser gate.
    regions = ui.app.region_rows()
    assert len(regions) == 2, regions
    assert sorted(inside(r, DONOR_GATE) or inside(r, ACCEPTOR_GATE) for r in regions) == [
        True,
        True,
    ]
    assert any(inside(r, DONOR_GATE) for r in regions) and any(
        inside(r, ACCEPTOR_GATE) for r in regions
    )
    # The written file carries the measured fold: micro-time = (macro - shift) mod period, computed here.
    target = tmp_path / "converted.ptu"
    assert ui.app.save(target)
    settle(ui)
    written = tttrlib.TTTR(str(target))
    raw = tttrlib.TTTR(str(path))
    np.testing.assert_array_equal(written.macro_times, raw.macro_times)
    np.testing.assert_array_equal(
        written.micro_times, (raw.macro_times.astype(np.int64) - 0) % PERIOD
    )
    np.testing.assert_array_equal(written.routing_channels, raw.routing_channels)


def test_the_demo_measurement_ranges_match_its_planted_gates(ui, tmp_path):
    """The ALEX Suite's demo (a different simulator, period 8000) gives back its two laser gates."""
    from chisurf.plugins.burst.alex_suite import demo

    load(ui, demo.make_demo(tmp_path / "demo"))
    ui.click_name("detect_period")
    settle(ui)
    assert ui.app.model.alex_period == demo.PERIOD
    regions = ui.app.region_rows()
    assert len(regions) == 2
    assert any(inside(r, demo.DONOR_GATE) for r in regions)
    assert any(inside(r, demo.ACCEPTOR_GATE) for r in regions)


def test_a_stream_that_does_not_alternate_is_refused_and_period_kept(ui, tmp_path):
    rng = np.random.default_rng(3)
    macro = np.sort(rng.integers(0, 10**9, 200_000)).astype(np.uint64)
    load(ui, write_stream(tmp_path / "noise.spc", macro, rng.integers(0, 2, macro.size)))
    ui.type_into_name("alex_period", "6000")
    settle(ui)
    ui.click_name("detect_period")
    settle(ui)
    assert ui.app.model.alex_period == 6000
    assert ui.app.message_is_error and "alternation" in ui.app.message


def test_ranges_are_defined_by_hand_in_the_table_and_redetect_restores_them(ui, tmp_path):
    load(ui, planted_alex(tmp_path / "alex.spc"))
    ui.click_name("detect_period")
    settle(ui)
    measured = [(r["start"], r["stop"]) for r in ui.app.region_rows()]
    donor = next(r for r in ui.app.region_rows() if inside(r, DONOR_GATE))
    # Double-click the donor range's End cell, type the planted gate edge, Enter.
    ui.click_text(f"{donor['stop']:.1f}", clicks=2)
    ui.app.key(0x41, "a", CTRL)
    ui.draw(1)
    ui.type("2400")
    ui.enter()
    assert donor["stop"] == 2400.0 and donor["edited"]
    assert donor["ranges"] == [[donor["start"], 2400.0]]
    ui.draw(2)
    assert "Edited" in [t[5] for t in ui.draw(1).texts], "the table says the range was set by hand"
    # A range across phase zero: Start above End is one region drawn as two bands.
    ui.click_text(f"{donor['start']:.1f}", clicks=2)
    ui.app.key(0x41, "a", CTRL)
    ui.draw(1)
    ui.type("4950")
    ui.enter()
    assert donor["wraps"] and donor["ranges"] == [[4950.0, float(PERIOD)], [0.0, 2400.0]]
    texts = [t[5] for t in ui.draw(2).texts]
    assert texts.count(donor["label"]) == 2, "one table cell and one legend entry, not one per band"
    # Re-detect gives back the measured ranges.
    ui.click_name("redetect_regions")
    settle(ui)
    assert [(r["start"], r["stop"]) for r in ui.app.region_rows()] == measured
    assert not any(r.get("edited") for r in ui.app.region_rows())


@pytest.mark.xfail(
    strict=True,
    reason="emtk defect: a one-line input field keeps the keyboard (nav focus) after a click elsewhere "
    "(emtk/im_widgets.py input field clears only its click focus; text_editor clears both), so keys typed "
    "into a table cell opened afterwards also land in the field",
)
def test_a_range_typed_after_typing_the_file_path_reaches_the_cell(ui, tmp_path):
    ui.type_into_name("input_file", str(planted_alex(tmp_path / "alex.spc")))
    settle(ui)
    ui.click_name("detect_period")
    settle(ui)
    donor = next(r for r in ui.app.region_rows() if inside(r, DONOR_GATE))
    ui.click_text(f"{donor['stop']:.1f}", clicks=2)
    ui.app.key(0x41, "a", CTRL)
    ui.draw(1)
    ui.type("2400")
    ui.enter()
    assert donor["stop"] == 2400.0
    assert ui.app.model.input_file.endswith("alex.spc")
