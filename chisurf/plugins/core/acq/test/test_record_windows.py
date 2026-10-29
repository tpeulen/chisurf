"""Record checks the excitation windows against the live decays, and the user decides.

The MT200 case: HydraHarp at 32 ps, 3125 channels per 100 ns, a setup made for an SPC-130 (50 ps,
prompt 0–2048, delayed 2048–4095). Converted, those windows are 0–3200 / 3200–6398 -- beyond the
data; unconverted they cut the 3125 channels in the wrong place. Either way the decays show two
pulses the windows do not hold, and Record says so without stopping the run or changing anything.
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from chisurf.plugins.core.acq.live.window_check import LiveWindowCheck, convert_setup_windows

RES, N = 32e-12, 3125
SPC130 = {
    "detectors": {"green": {"chs": [0]}, "red": {"chs": [1]}},
    "windows": {"prompt": [0, 2048], "delayed": [2048, 4095]},
    "tttr_reading": {"micro_time_resolution": 50.0},
}


def _decays(pulses=((2e-9, "d"), (52e-9, "a")), photons=200_000, n_bins=1024, seed=0):
    """A live snapshot's decays: ``n_bins`` bins over the 3125-channel range."""
    rng = np.random.default_rng(seed)
    t = (np.arange(n_bins) + 0.5) * (N * RES / n_bins)
    period = N * RES
    green, red = np.zeros(n_bins), np.zeros(n_bins)
    for t0, role in pulses:
        y = np.exp(-((t - t0) % period) / 3e-9)
        y /= y.sum()
        if role == "d":
            green, red = green + 0.6 * y, red + 0.4 * y
        else:
            red = red + 0.5 * y
    s = green.sum() + red.sum()
    bg = 0.01 * photons / n_bins
    return {
        "decays": {
            "green": rng.poisson(green / s * photons + bg).astype(float),
            "red": rng.poisson(red / s * photons + bg).astype(float),
            "prompt green": np.zeros(n_bins),
        }
    }


def test_setup_windows_of_another_resolution_are_converted():
    setup, note = convert_setup_windows(SPC130, RES)
    assert setup["windows"] == {"prompt": [0, 3200], "delayed": [3200, 6398]}
    assert setup["tttr_reading"]["micro_time_resolution"] == pytest.approx(32.0)
    assert "50 ps" in note and "32 ps" in note
    again, note = convert_setup_windows(setup, RES)
    assert again == setup and not note
    plain = {"windows": {"prompt": [0, 10]}}
    assert convert_setup_windows(plain, RES) == (plain, "")


def test_live_check_warns_once_per_picture_and_keep_holds():
    live = LiveWindowCheck()
    windows = SPC130["windows"]
    assert not live.update(_decays(photons=2_000), windows, RES, N)  # too few photons
    assert live.update(_decays(), windows, RES, N)
    assert live.asking and live.check.mismatch
    prompt, delayed = live.check.proposal["prompt"], live.check.proposal["delayed"]
    assert prompt[0] <= 2e-9 / RES < prompt[1] and delayed[0] <= 52e-9 / RES < delayed[1]
    live.keep()
    assert not live.asking
    assert not live.update(_decays(photons=300_000, seed=1), windows, RES, N)  # not doubled
    assert live.update(_decays(photons=500_000, seed=2), windows, RES, N)
    assert not live.asking  # the same picture: kept
    moved = _decays(pulses=((10e-9, "d"), (60e-9, "a")), photons=2_000_000, seed=3)
    assert live.update(moved, windows, RES, N)
    assert live.asking  # another picture asks again


def test_matching_windows_and_a_donor_only_run_do_not_ask():
    live = LiveWindowCheck()
    live.update(_decays(), {"prompt": [40, 1600], "delayed": [1600, 3125]}, RES, N)
    assert live.check.status == "ok" and not live.asking
    live = LiveWindowCheck()
    live.update(_decays(pulses=((2e-9, "d"),)), SPC130["windows"], RES, N)
    assert live.check.detection.kind == "single" and not live.asking


@pytest.fixture
def model(tmp_path):
    from chisurf.plugins.core.acq.gui.record_app import RecordModel
    from chisurf.plugins.core.acq.gui.record_settings import SETTINGS_SETUP

    m = RecordModel(output_dir=tmp_path / "rec", realtime=False)
    m.load_example()
    m.duration_s = 4.0
    # a setup whose windows were made for another instrument, in raw channels
    m.settings_setup = {"detectors": SPC130["detectors"],
                        "windows": {"prompt": [2048, 3000], "delayed": [3000, 4000]}}
    m.settings_name = "SPC-130 setup"
    m.setup_address = SETTINGS_SETUP
    m.preset = "pie"
    return m


def _run(m, timeout=120.0):
    end = time.monotonic() + timeout
    while m.running:
        assert time.monotonic() < end
        m.poll(force=True)
        time.sleep(0.02)
    m.poll(force=True)


def test_a_run_with_wrong_windows_warns_and_update_takes_the_detected_ones(model):
    assert model.start()
    _run(model)
    assert model.window_check_asking, model.window_check_text
    assert model.window_check_level == "warning"
    assert model.enabled("update_windows_from_check") and model.enabled("keep_windows")
    before = dict(model.settings_setup["windows"])
    assert model.make_experiment(4000).setup["windows"] == before  # nothing changed silently
    assert model.update_windows_from_check()
    assert not model.window_check_asking
    exp = model.make_experiment(4000, 8e-12)
    assert exp.setup["windows"] == model.live_windows.check.proposal
    model.start()
    _run(model)
    assert not model.window_check_asking  # the next run's windows hold the pulses
    assert model.live_windows.check.status in ("ok", "info")


def test_keep_leaves_the_windows(model):
    model.start()
    _run(model)
    assert model.window_check_asking
    model.keep_windows()
    assert not model.window_check_asking and model.window_check_level == "info"
    assert model.window_override is None


# -- µs-ALEX: the alternation is in the macro time ------------------------------------------------


class _Info:
    macro_clock_s = 12.5e-9
    micro_res_s = 1e-9
    n_micro = 1


class _AlexSession:
    """What the check reads of a µs-ALEX run: the experiment, the clock, the first photons."""

    def __init__(self, experiment, macro=None, channels=None):
        self.experiment = experiment
        self.source = type("S", (), {"info": _Info()})()
        if macro is not None:
            self.alex_photons = lambda: (macro, channels)


@pytest.fixture(scope="module")
def alex_stream(tmp_path_factory):
    tttrlib = pytest.importorskip("tttrlib")
    from chisurf.core.fluorescence.simulation.alex_sm import simulate_alex_sm

    path = tmp_path_factory.mktemp("alex") / "alex.sm"
    simulate_alex_sm(path, [{"E": 0.3, "S": 0.5, "n": 400}, {"E": 0.8, "S": 0.5, "n": 400}])
    t = tttrlib.TTTR(str(path))
    return np.asarray(t.macro_times), np.asarray(t.routing_channels)


def test_an_alex_run_with_the_wrong_period_warns_and_update_takes_period_and_windows(
        tmp_path, alex_stream):
    from chisurf.plugins.core.acq.gui.record_app import RecordModel
    from chisurf.plugins.core.acq.live.setups import Experiment

    m = RecordModel(output_dir=tmp_path, realtime=False)
    setup = {"detectors": {"green": {"chs": [0]}, "red": {"chs": [1]}}}
    exp = Experiment(setup, "alex", alex_period_s=60e-6)  # the stream alternates every 100 µs
    m.session, m.snapshot = _AlexSession(exp, *alex_stream), {"bursts": 0}
    m.window_check_poll()
    assert m.window_check_asking, m.window_check_text
    assert any(i.code == "alex_period_mismatch" for i in m.live_windows.check.issues)
    assert m.update_windows_from_check()
    assert m.alex_period_us == pytest.approx(100.0, rel=1e-3)
    m.session = None
    m.preset = "alex"
    assert m.make_experiment(1).alex_windows_s["delayed"][0] > 50e-6


def test_an_alex_run_without_macro_times_says_so(tmp_path):
    from chisurf.plugins.core.acq.gui.record_app import RecordModel
    from chisurf.plugins.core.acq.live.setups import Experiment

    m = RecordModel(output_dir=tmp_path, realtime=False)
    exp = Experiment({"detectors": {"green": {"chs": [0]}, "red": {"chs": [1]}}}, "alex",
                     alex_period_s=100e-6)
    m.session, m.snapshot = _AlexSession(exp), {"bursts": 0}
    m.window_check_poll()
    assert m.window_check_level == "info"
    assert "not checked live" in m.window_check_text


def test_detector_gates_of_another_resolution_are_converted_with_the_windows():
    setup = {**SPC130, "detectors": {"green": {"chs": [0], "micro_time_ranges": [[0, 4095]]},
                                     "red": {"chs": [1]}}}
    out, note = convert_setup_windows(setup, RES)
    assert out["detectors"]["green"]["micro_time_ranges"] == [[0, 6398]]
    assert "detector gates" in note


def test_a_gate_that_holds_no_pulse_is_flagged_live():
    live = LiveWindowCheck()
    windows = {"prompt": [40, 1600], "delayed": [1600, 3125]}
    live.update(_decays(), windows, RES, N, gates={"red": [[1700, 3000]]})
    assert live.asking
    assert live.check.proposal_gates["red"] == [[0, N]]


def test_the_stand_in_reads_the_setup_micro_time_in_ps():
    """The setup editor writes ``tttr_reading.micro_time_resolution`` in ps (tttrlib's
    ``from_setup`` reads it so too since the unit fix; Record passes it explicitly either way)."""
    from chisurf.plugins.core.acq.live.analyzer import StreamingBurstAnalyzer

    setup = {**SPC130, "tttr_reading": {"macro_time_resolution": 12.5,
                                        "micro_time_resolution": 32.0}}
    a = StreamingBurstAnalyzer.from_setup(setup, "pie")
    assert a.micro_time_resolution() == pytest.approx(32e-12)
    assert a.macro_time_resolution() == pytest.approx(12.5e-9)
