"""The µs-ALEX alternation detection, against a stream with a planted period.

The detection replaces seven numbers a user used to type, so the thing worth
pinning is that it gets them right on data where they are known — and that it
*refuses* rather than inventing a period when the data is not alternating.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.plugins.tttr.ptu_alex_creator.core import (
    auto_alex_windows,
    detect_alex_period,
)

PERIOD = 8000
GREEN = (300, 3700)
RED = (4300, 7700)


def alternating_stream(n=400_000, period=PERIOD, seed=3):
    """Photons whose detector depends on which laser window they fall in."""
    rng = np.random.default_rng(seed)
    t = np.sort(rng.integers(0, period * 6000, n))
    phase = t % period
    green_on = (phase >= GREEN[0]) & (phase < GREEN[1])
    red_on = (phase >= RED[0]) & (phase < RED[1])
    keep = green_on | red_on
    t, green_on = t[keep], green_on[keep]
    # Under donor excitation most photons land on the donor detector; under
    # acceptor excitation almost none do. That contrast is the signal.
    p_donor = np.where(green_on, 0.7, 0.05)
    routing = np.where(rng.random(t.size) < p_donor, 0, 1)
    return t, routing


def test_period_is_recovered_exactly():
    """The scan finishes on the integer period, not on an FFT bin edge.

    Exactness matters: one macro-time unit out, over 10^5 cycles, walks the
    folded phase clean across a laser window.
    """
    t, routing = alternating_stream()
    result = detect_alex_period(t, routing, donor_channels=[0], acceptor_channels=[1])
    assert result["period"] == PERIOD
    assert result["confidence"] > 50


def test_windows_land_inside_the_true_laser_gates():
    """The detected gates sit inside the real ones, trimmed by the guard band."""
    t, routing = alternating_stream()
    period = detect_alex_period(t, routing, donor_channels=[0], acceptor_channels=[1])["period"]
    windows = auto_alex_windows(
        t % period, routing, donor_channels=[0], acceptor_channels=[1], alex_period=period
    )
    for name, (lo_true, hi_true) in (("green", GREEN), ("red", RED)):
        lo, hi = windows[name]
        assert lo_true <= lo < hi <= hi_true, name
        # The guard trims the laser rise/fall; it must not eat the window.
        assert (hi - lo) > 0.7 * (hi_true - lo_true), name


def test_swapped_channels_swap_the_windows_not_the_period():
    """Calling the acceptor 'donor' relabels the gates; the period is unchanged.

    This is the old channel-flip checkbox: the period is a property of the
    lasers, the *labelling* is what the detector assignment decides.
    """
    t, routing = alternating_stream()
    straight = detect_alex_period(t, routing, donor_channels=[0], acceptor_channels=[1])
    swapped = detect_alex_period(t, routing, donor_channels=[1], acceptor_channels=[0])
    assert straight["period"] == swapped["period"]

    period = straight["period"]
    a = auto_alex_windows(
        t % period, routing, donor_channels=[0], acceptor_channels=[1], alex_period=period
    )
    b = auto_alex_windows(
        t % period, routing, donor_channels=[1], acceptor_channels=[0], alex_period=period
    )
    assert np.allclose(a["green"], b["red"])
    assert np.allclose(a["red"], b["green"])


def test_continuous_wave_data_is_refused_rather_than_converted():
    """Non-alternating data does not get converted on a noise-peak "period".

    A period always comes back — a power spectrum has a maximum whatever is in
    it — so the *contrast* is what decides, and the conversion is where that
    decision has to be enforced: this step rewrites every measurement, and doing
    that on continuous-wave data would fold a meaningless micro-time into all of
    them and leave nothing to say so afterwards.

    ``auto_alex_windows`` cannot be relied on to raise here: Poisson noise in a
    folded histogram produces two "plateaus" often enough.
    """
    from chisurf.plugins.burst.alex_suite.api.convert import detect_and_convert

    rng = np.random.default_rng(1)
    t = np.sort(rng.integers(0, 10_000_000, 200_000))
    routing = rng.integers(0, 2, t.size)
    result = detect_alex_period(t, routing, donor_channels=[0], acceptor_channels=[1])
    assert result["confidence"] < 50

    class _Fake:
        macro_times = t
        routing_channels = routing

    import chisurf.plugins.tttr.ptu_alex_creator.core as core

    original = core.load
    core.load = lambda *a, **k: _Fake()
    try:
        with pytest.raises(ValueError, match="no clear laser alternation"):
            detect_and_convert(["cw.ptu"], donor_channels=[0], acceptor_channels=[1])
    finally:
        core.load = original


def test_too_few_photons_is_an_error_that_names_the_cause():
    """An empty channel selection is a channel mistake, not an empty result."""
    t, routing = alternating_stream(n=5000)
    with pytest.raises(ValueError, match="channel assignment"):
        detect_alex_period(t, routing, donor_channels=[7], acceptor_channels=[8])


def test_setup_built_from_the_gates_uses_the_names_every_reader_knows():
    """The setup writes Seidel names, so the shipped equations resolve.

    ``prompt``/``delayed`` windows and ``green``/``red``/``yellow`` detectors is
    the vocabulary ndX's MFD equations and the shared column conventions are
    written against. With the windows named after the colours instead, the burst
    table's stream columns matched nothing and the E-S step came up empty with
    the burst files loaded.
    """
    pytest.importorskip("qtpy")
    from chisurf.plugins.burst.alex_suite.gui.alternation import build_setup

    setup = build_setup({"green": (300.0, 3700.0), "red": (4300.0, 7700.0)}, [0], [1], PERIOD)
    assert setup["windows"] == {"prompt": [300, 3700], "delayed": [4300, 7700]}
    assert list(setup["detectors"]) == ["green", "red", "yellow"]
    assert setup["detectors"]["green"]["chs"] == [0]
    # red and yellow are the SAME physical detector, entered once per window.
    assert setup["detectors"]["red"]["chs"] == [1]
    assert setup["detectors"]["yellow"]["chs"] == [1]
    assert setup["detectors"]["red"]["micro_time_ranges"] == [[300, 3700]]
    assert setup["detectors"]["yellow"]["micro_time_ranges"] == [[4300, 7700]]


def test_the_streams_of_that_setup_map_onto_the_alex_channels():
    """A burst table written from the setup resolves to DD / DA / AA.

    The writer intersects the window with each detector's *own* micro-time
    range, so the cross product also writes an all-zero ``S delayed red``.
    Picking that as I_AA is not a missing column -- it is every burst at S = 1.
    """
    from chisurf.core.fluorescence.burst.table import guess_columns

    columns = ["Number of Photons (green)", "Number of Photons (red)", "Number of Photons (yellow)"]
    for window, (lo, hi) in (("prompt", (300, 3700)), ("delayed", (4300, 7700))):
        for detector in ("green", "red", "yellow"):
            columns.append(f"S {window} {detector} (photons) | {lo}-{hi}")
    mapping = guess_columns(columns)
    assert mapping["i_dd"] == "S prompt green (photons) | 300-3700"
    assert mapping["i_da"] == "S prompt red (photons) | 300-3700"
    assert mapping["i_aa"] == "S delayed yellow (photons) | 4300-7700"


def test_a_two_detector_pie_table_still_resolves():
    """Without a second acceptor entry the acceptor window uses the only one."""
    from chisurf.core.fluorescence.burst.table import guess_columns

    columns = ["Number of Photons (green)", "Number of Photons (red)"]
    for window, (lo, hi) in (("prompt", (300, 3700)), ("delayed", (4300, 7700))):
        for detector in ("green", "red"):
            columns.append(f"S {window} {detector} (photons) | {lo}-{hi}")
    mapping = guess_columns(columns)
    assert mapping["i_dd"] == "S prompt green (photons) | 300-3700"
    assert mapping["i_da"] == "S prompt red (photons) | 300-3700"
    assert mapping["i_aa"] == "S delayed red (photons) | 4300-7700"


def test_photon_counts_win_over_the_rates_beside_them():
    """E and S are ratios of counts; the rates have per-stream denominators."""
    from chisurf.core.fluorescence.burst.table import guess_columns

    columns = ["Number of Photons (green)", "Number of Photons (red)"]
    for window, (lo, hi) in (("prompt", (300, 3700)), ("delayed", (4300, 7700))):
        for detector in ("green", "red"):
            columns.append(f"S {window} {detector} (kHz) | {lo}-{hi}")
            columns.append(f"S {window} {detector} (photons) | {lo}-{hi}")
    assert "photons" in guess_columns(columns)["i_dd"]

    # An older table with only the rates still resolves -- on the rates.
    rates_only = [c for c in columns if "photons" not in c]
    assert "kHz" in guess_columns(rates_only)["i_dd"]


# ── against a real measurement ──────────────────────────────────────────

#: A real 300 s µs-ALEX measurement (Cy3B / ATTO647N dsDNA calibration sample),
#: and what the ALEX-Suite program was configured with for it: a 100 µs
#: alternation at 12.5 ns macro-time units = 8000 units, green 240-3760, red
#: 4160-7680, channel_flip on (the donor is routing channel 1).
REAL_FILE = pathlib.Path(
    "~/dev/tttr-data/sm/cal1/001_60g_25r_cal1_cy3b_8_18_33bp_atto647n.sm"
).expanduser()
REAL_PERIOD = 8000
REAL_GREEN = (240, 3760)
REAL_RED = (4160, 7680)

real_data = pytest.mark.skipif(not REAL_FILE.is_file(), reason=f"{REAL_FILE} not available")


@pytest.fixture(scope="module")
def folded_real():
    """Return the real measurement, folded on its true period."""
    tttrlib = pytest.importorskip("tttrlib")
    from chisurf.plugins.tttr.ptu_alex_creator.core import apply_alex

    return apply_alex(tttrlib.TTTR(str(REAL_FILE), "SM"), REAL_PERIOD, 0)


@real_data
def test_the_period_of_a_real_measurement_is_found_exactly():
    """8000 macro-time units — what the old program was configured with."""
    tttrlib = pytest.importorskip("tttrlib")

    tttr = tttrlib.TTTR(str(REAL_FILE), "SM")
    result = detect_alex_period(
        tttr.macro_times, tttr.routing_channels, donor_channels=[1], acceptor_channels=[0]
    )
    assert result["period"] == REAL_PERIOD
    assert result["confidence"] > 1000


@real_data
def test_the_channel_assignment_of_a_real_measurement_is_worked_out(folded_real):
    """The donor is channel 1 here — the old 'channel flip', decided by physics.

    Nothing about the sample settles it except that the donor detector goes dark
    under acceptor excitation, and here it drops to a few per cent of its
    donor-excitation rate.
    """
    from chisurf.plugins.tttr.ptu_alex_creator.core import detect_alex_channels

    assignment = detect_alex_channels(
        folded_real.micro_times, folded_real.routing_channels, alex_period=REAL_PERIOD
    )
    assert assignment["donor"] == [1]
    assert assignment["acceptor"] == [0]
    assert assignment["contrast"] < 0.2


@real_data
def test_the_windows_of_a_real_measurement_match_the_old_configuration(folded_real):
    """The detected gates sit inside the edges the old program was given.

    This is the case that broke the previous implementation: real µs-ALEX has
    **no laser-off gap** — both lasers keep the sample emitting, so the folded
    intensity is flat to within a factor of two and an occupancy threshold finds
    one window covering the whole period. The detector *ratio* alternates 0.69
    against 0.07 across the same period, which is what the split now uses.
    """
    windows = auto_alex_windows(
        folded_real.micro_times,
        folded_real.routing_channels,
        donor_channels=[1],
        acceptor_channels=[0],
        alex_period=REAL_PERIOD,
    )
    for name, (lo_true, hi_true) in (("green", REAL_GREEN), ("red", REAL_RED)):
        lo, hi = windows[name]
        assert lo_true <= lo < hi <= hi_true + 100, (name, lo, hi)
        assert (hi - lo) > 0.7 * (hi_true - lo_true), name


@real_data
def test_a_flat_folded_intensity_is_what_makes_this_hard(folded_real):
    """The measurement this is checked against really has no laser-off gap.

    Without this the window test above would pass for the wrong reason — on data
    that happens to be gated, where the old occupancy method also worked.
    """
    counts, _ = np.histogram(
        np.asarray(folded_real.micro_times), bins=np.linspace(0, REAL_PERIOD, 41)
    )
    interior = counts[2:]  # the first bins hold the laser turn-on transient
    assert interior.min() > 0.4 * interior.max(), (
        "this file has laser-off gaps after all; pick one that does not"
    )
