"""The ebFRET main-window workflow, headless: what each menu entry and control does.

Every test drives :class:`Session` with the values the MATLAB dialogs would
return, on the simulated demo dataset, and checks the observable the reference
defines -- the crop a bleaching threshold sets, the series an outlier count
excludes, the files an export writes.
"""

from __future__ import annotations

import gzip
import json

import numpy as np
import pytest

from chisurf.plugins.burst.burst_ebfret import demo
from chisurf.plugins.burst.burst_ebfret import io as ebio
from chisurf.plugins.burst.burst_ebfret.core.session import RAW, SESSION, Session


@pytest.fixture(scope="module")
def demo_file(tmp_path_factory):
    return demo.write_demo(tmp_path_factory.mktemp("demo") / "demo.dat", seed=7)


@pytest.fixture
def session(demo_file):
    s = Session(seed=3)
    s.load_data([str(demo_file)], RAW)
    return s


def test_loading_sets_the_controls_ebfret_sets(session):
    c = session.controls
    assert len(session.series) == demo.DEMO["n_series"]
    assert (c.series_min, c.series_max, c.series_value) == (1, 40, 1)
    assert c.ensemble_value == c.min_states == 2
    assert sorted(session.analysis) == list(range(2, 7))
    assert all(a.prior is not None for a in session.analysis.values())
    assert session.series[0].group == "group 1"
    assert session.series[0].label == "1", "the first row of a series is its label"


def test_keeping_loaded_series_makes_a_new_group(session, demo_file):
    session.load_data([str(demo_file)], RAW, append=True)
    assert len(session.series) == 80
    assert session.groups() == ["group 1", "group 2"]


def test_crop_is_clamped_and_resets_that_series_only(session):
    a = session.analysis[2]
    a.lowerbound[:] = 1.0
    session.set_series(value=3)
    session.set_crop(crop_min=0, crop_max=10_000)
    s = session.series[2]
    assert s.crop_min == 1 and s.crop_max == s.length
    session.set_crop(crop_max=50)
    assert s.crop_max == 50
    assert a.lowerbound[2] == 0.0 and a.lowerbound[1] == 1.0


def test_exclude_clears_the_posterior(session):
    session.set_series(value=2)
    session.set_exclude(True)
    assert session.series[1].exclude
    assert session.analysis[3].posterior[1] is None
    assert session.get_signal([1])[0].size == 0


def test_min_and_max_states_move_the_select_states_limits(session):
    session.set_max_states(8)
    session.set_min_states(3)
    c = session.controls
    assert (c.ensemble_min, c.ensemble_max) == (3, 8)
    assert c.ensemble_value >= 3
    assert 8 in session.analysis


def test_manual_bleaching_threshold_crops_where_the_signal_drops(session):
    s = session.series[0]
    s.acceptor[:] = 300.0
    s.acceptor[100:] = -50.0
    message = session.remove_bleaching(1, {"acc": 20.0})
    assert "Excluded" in message
    # the 7-frame smoothing puts the crossing a few frames past the drop, as in MATLAB
    assert 100 <= s.crop_max <= 105


def test_auto_bleaching_uses_photobleach_detection(session):
    message = session.remove_bleaching(2, None)
    assert message.startswith("Total length:")
    assert all(1 <= s.crop_max <= s.length for s in session.series)


def test_clip_outliers_excludes_series_with_too_many_outliers(session):
    session.series[4].signal[:20] = 5.0
    message = session.clip_outliers((-0.2, 1.2), 10)
    assert session.series[4].exclude
    assert "Excluded 1 out of 40" in message
    assert (session.controls.clip_min, session.controls.clip_max) == (-0.2, 1.2)


def test_set_priors_spreads_the_centers(session):
    session.init_priors({"mu_min": 0.1, "mu_max": 0.7, "sigma": 0.05, "tau": 50.0},
                        {"mu": 0.1, "sigma": 10.0, "tau": 10.0}, 1)
    np.testing.assert_allclose(session.analysis[4].prior.mu, [0.1, 0.3, 0.5, 0.7])
    np.testing.assert_allclose(session.analysis[4].prior.W, 400.0 / 10.0)


def test_a_current_run_recovers_the_simulated_states(session):
    # restarts=2, the window's default: with one uninformative restart only, this
    # dataset settles in a local optimum ([0.20, 0.38, 0.50, 0.72]) -- which is
    # what the random restarts are for.
    session.set_controls(run_all=False, restarts=2)
    session.set_ensemble(value=4)
    events = list(session.run_ebayes(should_stop=lambda: False))
    assert any(e["kind"] == "iteration" for e in events)
    assert not session.controls.run_analysis
    mu = np.sort(session.analysis[4].prior.mu)
    np.testing.assert_allclose(mu, demo.DEMO["efret"], atol=0.03)
    assert session.log and session.log[0].startswith("K04")
    assert all(v is not None for v in session.analysis[4].viterbi)


def test_stop_ends_the_run(session):
    session.set_controls(run_all=True)
    calls = {"n": 0}

    def stop():
        calls["n"] += 1
        return calls["n"] > 1

    list(session.run_ebayes(should_stop=stop))
    assert not session.controls.run_analysis
    assert all(lb == 0.0 for lb in session.analysis[6].lowerbound), "never reached K=6"


def test_exports_and_session_round_trip(session, tmp_path):
    session.set_controls(run_all=False, restarts=0)
    session.set_ensemble(value=2)
    list(session.run_ebayes(should_stop=lambda: False))

    summary = tmp_path / "summary.csv"
    session.export_summary(str(summary))
    text = summary.read_text()
    assert "Lower_Bound" in text and "Transition_Matrix" in text

    traces = tmp_path / "traces.dat"
    session.export_traces(str(traces), dict.fromkeys(
        ("donor", "acceptor", "fret", "viterbi_state", "viterbi_mean"), True), 2)
    table = np.loadtxt(traces)
    assert table.shape[1] == 6
    assert set(np.unique(table[:, 4])) <= {1.0, 2.0}

    smd = tmp_path / "export.json.gz"
    session.export_smd(str(smd), 2)
    with gzip.open(smd, "rt") as handle:
        assert len(json.load(handle)["data"]) == 40

    saved = tmp_path / "session.mat"
    session.save_data(str(saved))
    other = Session()
    other.load_data([str(saved)], SESSION)
    assert len(other.series) == 40
    np.testing.assert_allclose(other.analysis[2].prior.mu, session.analysis[2].prior.mu)
    assert not other.controls.run_analysis


def test_a_group_export_reestimates_the_prior(session, demo_file):
    session.load_data([str(demo_file)], RAW, append=True)
    session.set_controls(run_all=False, restarts=0)
    session.set_ensemble(value=2)
    list(session.run_ebayes(should_stop=lambda: False))
    series, analysis = session.select_analysis(2, "group 2")
    assert len(series) == 40 and len(analysis.posterior) == 40
    assert analysis.prior is not None


def test_the_demo_file_is_what_load_raw_reads():
    donors, acceptors, states = demo.simulate(seed=1, n_series=3)
    assert len(donors) == 3 and all(len(d) == len(s) for d, s in zip(donors, states))
    path = demo.write_demo(seed=1)
    loaded = ebio.load_raw(str(path), has_labels=True)
    assert len(loaded[0]) == demo.DEMO["n_series"]
