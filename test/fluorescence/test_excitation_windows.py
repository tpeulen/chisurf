"""Excitation windows: PIE pulses and µs-ALEX alternation found in the data, windows checked.

Known answers: synthetic micro-time histograms (IRF-convolved decays, background, Poisson noise)
at several resolutions, channel counts and sync offsets -- including a pulse straddling the end of
the range -- plus tttrlib-simulated PIE / donor-only measurements and a synthetic µs-ALEX ``.sm``
stream with planted laser windows. The Record tool's MT200 case (32 ps data, windows of a 50 ps /
4096-channel setup) must come back flagged.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fluorescence.excitation import (
    ExcitationWindows,
    check_setup,
    check_windows,
    detect_pie_windows,
    detect_windows,
    rescale_windows,
)


def pie_histograms(
    n=3125, res=32e-12, pulses=((2e-9, "d"), (52e-9, "a")), tau=4e-9, irf=0.12e-9,
    counts=200_000, bg=0.02, donor_only=False, afterpulse=0.0, seed=0,
):
    """``{"green", "red"}`` micro-time histograms of a two-colour PIE measurement.

    Donor pulses (``"d"``) light both detectors (donor emission + FRET), acceptor pulses (``"a"``)
    only the acceptor detector -- unless *donor_only*, when there is nothing to excite.
    """
    rng = np.random.default_rng(seed)
    t = np.arange(n) * res
    period = n * res

    def decay(t0):
        dt = (t - t0) % period
        y = np.exp(-dt / tau)
        k = np.arange(-40, 41)
        g = np.exp(-0.5 * (k * res / irf) ** 2)
        g /= g.sum()
        y = np.convolve(np.concatenate([y[-40:], y, y[:40]]), g, "same")[40:-40]
        return y / y.sum()

    green, red = np.zeros(n), np.zeros(n)
    for t0, role in pulses:
        if role == "d":
            green += 0.6 * decay(t0)
            red += 0.4 * decay(t0)
        elif not donor_only:
            red += 0.5 * decay(t0)
    total = green.sum() + red.sum()
    out = {}
    for name, y in (("green", green), ("red", red)):
        lam = y / total * counts * (1 - bg) + bg * counts / (2 * n)
        lam = lam + afterpulse * lam.sum() / n
        out[name] = rng.poisson(lam).astype(float)
    return out


def _holds(window, channel, n):
    lo, hi = window
    return lo <= channel % n < hi


@pytest.mark.parametrize(
    "n,res,pulses",
    [
        (3125, 32e-12, ((2e-9, "d"), (52e-9, "a"))),  # MT200: 32 ps, 100 ns
        (4096, 12.2e-12, ((5e-9, "d"), (30e-9, "a"))),  # 50 ns over 4096 channels
        (1024, 48.8e-12, ((10e-9, "d"), (35e-9, "a"))),  # binned to 1024 channels
        (6250, 8e-12, ((40e-9, "a"), (15e-9, "d"))),  # acceptor pulse first in the range
        (3125, 32e-12, ((49e-9, "a"), (99.5e-9, "d"))),  # donor pulse straddles the range end
    ],
    ids=["32ps", "12ps", "1024ch", "acceptor-first", "wraps"],
)
def test_pie_pulses_get_prompt_and_delayed_windows(n, res, pulses):
    h = pie_histograms(n=n, res=res, pulses=pulses)
    r = detect_pie_windows(h, res)
    assert r.kind == "pie", r.message
    assert set(r.windows) == {"prompt", "delayed"}
    assert r.donor_detectors == ["green"] and r.acceptor_detectors == ["red"]
    expect = {"d": "prompt", "a": "delayed"}
    for t0, role in pulses:
        rise = int(round(t0 / res)) % n
        win = r.windows[expect[role]]
        if not _holds(win, rise + 3, n):  # a wrapped window keeps the part with the peak
            assert _holds(win, rise + int(0.5e-9 / res), n), (role, win, rise)
        p = next(p for p in r.pulses if p.window == expect[role])
        assert abs(((p.rise - rise + n // 2) % n) - n // 2) <= max(3, int(0.3e-9 / res))
        assert p.role == ("donor" if role == "d" else "acceptor")
    # the detected windows hold every pulse: checking them finds nothing
    assert check_windows(r.windows, r, histogram=h["green"] + h["red"]).status == "ok"


def test_windows_tile_the_period():
    r = detect_pie_windows(pie_histograms(), 32e-12)
    (a, b), (c, d) = r.windows["prompt"], r.windows["delayed"]
    assert b == c and a < b < d <= 3125


def test_donor_only_is_single_not_an_error():
    h = pie_histograms(donor_only=True)
    r = detect_pie_windows(h, 32e-12)
    assert r.kind == "single" and not r.windows
    assert "donor-only" in r.message
    c = check_windows({"prompt": [0, 1500], "delayed": [1500, 3125]}, r)
    assert c.status == "info" and not c.mismatch and not c.proposal
    assert c.issues[0].code == "single_pulse"


def test_noise_only_is_unclear():
    rng = np.random.default_rng(3)
    r = detect_pie_windows({"green": rng.poisson(30, 3125), "red": rng.poisson(30, 3125)}, 32e-12)
    assert r.kind == "unclear"


def test_too_few_photons_is_unclear():
    r = detect_pie_windows(pie_histograms(counts=300), 32e-12)
    assert r.kind == "unclear" and "Too few photons" in r.message


def test_low_counts_still_find_both_pulses():
    r = detect_pie_windows(pie_histograms(counts=5_000, seed=7), 32e-12)
    assert r.kind == "pie"


def test_afterpulsing_and_background_add_no_pulse():
    r = detect_pie_windows(pie_histograms(bg=0.2, afterpulse=0.02), 32e-12)
    assert r.kind == "pie" and len(r.pulses) == 2


def test_dark_count_detector_adds_no_pulse():
    h = pie_histograms()
    h["dark"] = np.random.default_rng(1).poisson(2.0, 3125).astype(float)
    r = detect_pie_windows(h, 32e-12)
    assert r.kind == "pie" and len(r.pulses) == 2


def test_sync_divider_gives_a_window_per_pulse():
    pulses = ((2e-9, "d"), (27e-9, "a"), (52e-9, "d"), (77e-9, "a"))
    r = detect_pie_windows(pie_histograms(pulses=pulses), 32e-12)
    assert r.kind == "pie" and len(r.windows) == 4
    assert [p.role for p in r.pulses] == ["donor", "acceptor", "donor", "acceptor"]


def test_screenshot_case_windows_for_4096_channels_are_flagged():
    """1024 channels of data, the red pulse at ~520; windows defined for a 4096-channel range."""
    res = 100e-9 / 1024
    h = pie_histograms(n=1024, res=res, pulses=((3e-9, "d"), (51e-9, "a")))
    r = detect_pie_windows(h, res)
    assert r.kind == "pie"
    c = check_windows({"prompt": [0, 2000], "delayed": [2000, 4000]}, r,
                      histogram=h["green"] + h["red"])
    assert c.mismatch and c.status == "error"
    codes = {i.code for i in c.issues}
    assert {"outside_range", "window_mixes_pulses"} <= codes
    assert c.proposal == r.windows


def test_setup_of_another_resolution_is_converted_not_misapplied():
    """MT200: 32 ps data; the setup's windows are in 50 ps channels (SPC-130, 4096 ch)."""
    h = pie_histograms()
    r = detect_pie_windows(h, 32e-12)
    setup = {
        "windows": {"prompt": [0, 2048], "delayed": [2048, 4095]},
        "tttr_reading": {"micro_time_resolution": 50.0},
    }
    c = check_setup(setup, detection=r, histogram=h["green"] + h["red"])
    assert c.mismatch
    assert c.issues[0].code == "resolution_mismatch"
    assert c.windows["prompt"] == [0, 3200]
    # the same windows, right for the data but given in 50 ps channels: only converted
    good = rescale_windows(r.windows, 32e-12, 50e-12)
    c = check_windows(good, r, windows_resolution_s=50e-12)
    assert [i.code for i in c.issues] == ["resolution_mismatch"]
    for k in r.windows:
        assert abs(c.proposal[k][0] - r.windows[k][0]) <= 1


def test_swapped_and_cutting_windows():
    h = pie_histograms()
    r = detect_pie_windows(h, 32e-12)
    swapped = {"prompt": r.windows["delayed"], "delayed": r.windows["prompt"]}
    c = check_windows(swapped, r)
    assert "windows_swapped" in {i.code for i in c.issues}
    d = r.pulses[0]
    cut = {"prompt": [d.rise + 5, 1500], "delayed": [1500, 3125]}
    c = check_windows(cut, r)
    assert "window_cuts_pulse" in {i.code for i in c.issues}


def test_no_windows_on_a_pie_measurement_is_a_warning():
    r = detect_pie_windows(pie_histograms(), 32e-12)
    c = check_windows({}, r)
    assert c.status == "warning" and c.proposal == r.windows


def test_result_round_trips_and_converts():
    r = detect_pie_windows(pie_histograms(), 32e-12)
    again = ExcitationWindows.from_dict(r.to_dict())
    assert again.windows == r.windows and again.pulses[0].role == r.pulses[0].role
    ns = r.windows_ns()["delayed"]
    assert ns[0] == pytest.approx(r.windows["delayed"][0] * 0.032)
    assert r.windows_at(16e-12)["delayed"][0] == 2 * r.windows["delayed"][0]
    assert r.setup_patch()["tttr_reading"]["micro_time_resolution"] == pytest.approx(32.0)


def test_one_histogram_without_detectors():
    h = pie_histograms()
    r = detect_pie_windows(h["green"] + h["red"], 32e-12)
    assert r.kind == "pie" and not r.donor_detectors
    assert any("not known" in n for n in r.notes)


# -- whole measurements ------------------------------------------------------------------------------


tttrlib = pytest.importorskip("tttrlib")


@pytest.fixture(scope="module")
def alex_sm(tmp_path_factory):
    from chisurf.core.fluorescence.simulation.alex_sm import simulate_alex_sm

    path = tmp_path_factory.mktemp("alex") / "alex.sm"
    simulate_alex_sm(path, [{"E": 0.3, "S": 0.5, "n": 400}, {"E": 0.8, "S": 0.5, "n": 400}])
    return path


def test_alex_period_and_windows_from_the_macro_time(alex_sm):
    from chisurf.core.fluorescence.simulation.alex_sm import (
        ALEX_PERIOD,
        GREEN_WINDOW,
        RED_WINDOW,
    )

    r = detect_windows(alex_sm)
    assert r.kind == "alex" and r.domain == "macro", r.message
    assert r.n_channels == ALEX_PERIOD
    g, red = r.windows["prompt"], r.windows["delayed"]
    assert GREEN_WINDOW[0] - 200 <= g[0] and g[1] <= GREEN_WINDOW[1] + 200
    assert RED_WINDOW[0] - 200 <= red[0] and red[1] <= RED_WINDOW[1] + 200
    assert r.donor_detectors == ["ch 0"]
    halves = {"prompt": [0, ALEX_PERIOD // 2], "delayed": [ALEX_PERIOD // 2, ALEX_PERIOD]}
    assert not check_windows(halves, r).mismatch
    shifted = {"prompt": [2000, 6000], "delayed": [6000, 8000]}
    assert check_windows(shifted, r).mismatch


sim = pytest.importorskip("chisurf.plugins.burst.fret_check.sim")
if not hasattr(tttrlib, "SimEngine"):
    pytest.skip("tttrlib without the simulator", allow_module_level=True)


@pytest.mark.parametrize("name", ["PIE 2c", "PIE, acceptor pulse first", "PIE MFD (0/8, 1/9)"])
def test_simulated_pie_measurements(name):
    sc = next(s for s in sim.SCENARIOS if s.name == name)
    data = sim.simulate(sc)
    r = detect_windows(data)
    assert r.kind == "pie", r.message
    per_ns = 4096 / sc.laser_period_ns
    for window, pulse in (("prompt", sc.donor_pulse_ns), ("delayed", sc.acceptor_pulse_ns)):
        lo, hi = r.windows[window]
        assert lo <= (pulse + 0.5) * per_ns < hi, (window, r.windows)
    assert r.donor_detectors == [f"ch {c}" for c in sorted(sc.donor)]


def test_simulated_donor_only_measurement_is_single():
    sc = next(s for s in sim.SCENARIOS if s.name.startswith("1c"))
    r = detect_windows(sim.simulate(sc), kind="pie")
    assert r.kind == "single"


# -- detector gates --------------------------------------------------------------------------------


def test_detector_gates_are_converted_and_checked():
    from chisurf.core.fluorescence.excitation import apply_check, rescale_gates

    h = pie_histograms()
    r = detect_pie_windows(h, 32e-12)
    good = rescale_windows(r.windows, 32e-12, 50e-12)
    setup = {
        "windows": good,
        "detectors": {"green": {"chs": [0], "micro_time_ranges": [[0, 4095]]},
                      "red": {"chs": [1], "micro_time_ranges": [[1100, 2000]]}},  # holds neither pulse
        "tttr_reading": {"micro_time_resolution": 50.0},
    }
    c = check_setup(setup, detection=r, histograms=h)
    codes = [i.code for i in c.issues]
    assert "gate_misses_pulse" in codes and c.mismatch
    assert c.gates["red"] == [[1719, 3125]] and c.gates["green"] == [[0, 6398]]
    assert c.proposal_gates["red"] == [[0, 3125]]
    assert c.proposal_gates["green"] == [[0, 3125]]  # a gate that works is kept, clipped to the data
    fixed = apply_check(setup, c)
    assert fixed["detectors"]["red"]["micro_time_ranges"] == [[0, 3125]]
    assert fixed["tttr_reading"]["micro_time_resolution"] == pytest.approx(32.0)
    assert check_setup(fixed, detection=r, histograms=h).status == "ok"
    assert rescale_gates({"a": [[0, 2048]]}, 50e-12, 32e-12) == {"a": [[0, 3200]]}


def test_a_gate_beyond_the_range_is_an_error_even_for_donor_only():
    h = pie_histograms(donor_only=True)
    r = detect_pie_windows(h, 32e-12)
    c = check_windows({}, r, gates={"green": [[4000, 5000]]}, histograms=h)
    assert c.status == "error" and c.issues[0].code == "gate_outside_range"
    assert not c.proposal  # one pulse: nothing to offer for the windows


def test_gates_only_and_the_pie_split_of_the_acceptor_say_nothing():
    """A gate-only consumer (no windows) with gates that hold the pulses, and PIE's standard
    split of one acceptor detector into red (prompt) and yellow (delayed) by gates."""
    h = pie_histograms()
    r = detect_pie_windows(h, 32e-12)
    c = check_windows({}, r, gates={"green": [[0, 3125]], "red": [[0, 3125]]}, histograms=h)
    assert c.status == "ok", c.issues
    split = {"green": [[0, 1612]], "red": [[0, 1612]], "yellow": [[1613, 3124]]}
    chans = {"green": [0], "red": [1], "yellow": [1]}
    hists = {"green": h["green"], "red": h["red"], "yellow": h["red"]}
    r2 = detect_pie_windows(hists, 32e-12)
    c = check_windows(r2.windows, r2, gates=split, histograms=hists, gate_channels=chans)
    assert c.status == "ok", [i.message for i in c.issues]


def test_a_gate_that_keeps_one_excitation_on_purpose_says_nothing():
    """BVA / FRET-2CDE gate the acceptor to the prompt pulse: fine, no sibling needed."""
    h = pie_histograms()
    r = detect_pie_windows(h, 32e-12)
    c = check_windows(r.windows, r, gates={"red": [[50, 1613]]}, histograms=h)
    assert not any(i.code.startswith("gate") for i in c.issues), c.issues


def test_a_gate_missing_the_only_pulse_is_worded():
    from chisurf.core.fluorescence.excitation import windows_message

    h = pie_histograms(donor_only=True)
    r = detect_pie_windows(h, 32e-12)
    c = check_windows({}, r, gates={"green": [[1700, 3000]]}, histograms=h)
    assert c.mismatch and "Detector gates do not match" in windows_message(c)
