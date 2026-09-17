"""A/B of the numerical core against ebFRET's own MATLAB code.

Two references, neither needed at test time:

* ``data/octave/*.json`` -- ebFRET's ``+analysis``/``+plot`` functions run
  under Octave on six traces of the vendored simulated dataset
  (``octave/make_fixtures.m``). Direct computations agree to rounding; results
  of an iterative solver (the Newton steps of the h-step, 1e-6 relative stop)
  to ~1e-11, so those are held to ``ITERATIVE``.
* ``data/ebfret_session_k4.json`` -- the four-state analysis ebFRET's MATLAB
  GUI saved in its shipped session (``octave/extract_session_fixture.py``),
  which used the compiled single-precision forward-backward. Restarting VBEM
  from those posteriors must reproduce the saved lower bounds (one further
  VBEM iteration apart, and single vs double precision) and the Viterbi paths.
"""

from __future__ import annotations

import json
import pathlib

import numpy as np
import pytest

from chisurf.plugins.burst.burst_ebfret.core import dist, ebayes, hmm, plots
from chisurf.plugins.burst.burst_ebfret.core.model import (
    Analysis,
    Controls,
    Expect,
    HmmParams,
    Series,
    Viterbi,
)

DATA = pathlib.Path(__file__).parent / "data"
EXACT = 1e-12
ITERATIVE = 1e-9
FIELDS = ("mu", "beta", "W", "nu", "A", "pi")


def _decode(value):
    """Turn the driver's ``{"shape", "data"}`` arrays back into numpy (column-major)."""
    if isinstance(value, dict):
        if set(value) == {"shape", "data"}:
            data = [float(v) for v in value["data"]]
            return np.array(data, dtype=float).reshape(value["shape"], order="F")
        return {k: _decode(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_decode(v) for v in value]
    return value


def _load(name: str):
    """Load one Octave fixture."""
    return _decode(json.loads((DATA / "octave" / f"{name}.json").read_text()))


def _params(record) -> HmmParams:
    """Build HmmParams from a MATLAB struct record."""
    return HmmParams(
        **{
            k: (
                np.atleast_2d(np.asarray(record[k], dtype=float))
                if k == "A"
                else np.ravel(record[k])
            )
            for k in FIELDS
        }
    )


def _expect(record) -> Expect:
    """Build Expect from a MATLAB struct record."""
    return Expect(
        **{
            k: (np.asarray(record[k], dtype=float) if k == "zz" else np.ravel(record[k]))
            for k in ("z", "z1", "zz", "x", "xx")
        }
    )


def _close(actual, expected, rtol, atol=1e-300):
    """Assert elementwise closeness with MATLAB column vectors flattened."""
    actual = np.asarray(actual, dtype=float)
    expected = np.asarray(expected, dtype=float)
    if actual.shape != expected.shape and actual.size == expected.size:
        expected = expected.reshape(actual.shape)
    np.testing.assert_allclose(actual, expected, rtol=rtol, atol=atol)


def _assert_params(actual: HmmParams, record, rtol):
    """Compare every hyperparameter."""
    for name in FIELDS:
        _close(getattr(actual, name), record[name], rtol)


@pytest.fixture(scope="module")
def core():
    return _load("core")


@pytest.fixture(scope="module")
def eb():
    return _load("ebayes")


@pytest.fixture(scope="module")
def traces(core):
    return [np.ravel(x) for x in core["x"]]


# --------------------------------------------------------------------------- #
# single trace
# --------------------------------------------------------------------------- #
def test_x_lim_and_guess_prior(core, traces):
    x_min, x_max = hmm.x_lim(traces)
    _close([x_min, x_max], [core["x_lim_min"], core["x_lim_max"]], EXACT)
    _assert_params(hmm.guess_prior(traces, 2), core["u2"], 1e-12)
    _assert_params(hmm.guess_prior(traces, 3), core["u3"], 1e-12)


def test_init_prior_with_unequal_dwell_times(core):
    theta = {"mu": [0.1, 0.5, 0.9], "lambda": [100, 200, 400], "tau": [10, 50, 200]}
    counts = {"mu": [0.1, 0.2, 0.3], "lambda": [5, 10, 20], "tau": [3, 4, 5]}
    _assert_params(hmm.init_prior(theta, counts), core["init_prior"], 1e-12)


def test_vbem_steps(core, traces):
    u = _params(core["u3"])
    x = traces[0]
    w0 = hmm.init_posterior(x, u)
    _assert_params(w0, core["w0"], 1e-12)
    e_pi, e_a, e_px = hmm.e_step(w0, x)
    _close(e_pi, core["E_ln_pi"], 1e-12)
    _close(e_a, core["E_ln_A"], 1e-12)
    _close(e_px, core["E_ln_px_z"], 1e-12)
    g, xi, ln_z = hmm.forwback(np.exp(e_px), np.exp(e_a), np.exp(e_pi))
    _close(g, core["gamma"], 1e-12)
    _close(xi, core["xi"], 1e-12)
    _close(ln_z, core["ln_Z"], 1e-12)
    _close(hmm.kl_div(w0, u), core["kl_w0_u"], 1e-12)
    w, ev = hmm.m_step(u, x, g, xi)
    _assert_params(w, core["m_step_w"], 1e-12)
    _close(ev["xmean"], core["m_step_ev"]["xmean"], 1e-12)
    _close(ev["xvar"], core["m_step_ev"]["xvar"], 1e-12)


def test_vbayes_and_viterbi(core, traces):
    u = _params(core["u3"])
    x = traces[0]
    w, L, E = hmm.vbayes(x, hmm.init_posterior(x, u), u)
    assert L.size == np.size(core["vbayes_L"])
    _close(L, core["vbayes_L"], 1e-12)
    _assert_params(w, core["vbayes_w"], 1e-12)
    _close(E["xmean"], core["vbayes_xmean"], 1e-12)
    state, mean = hmm.viterbi_vb(w, x)
    np.testing.assert_array_equal(state, np.ravel(core["viterbi_state"]).astype(int))
    _close(mean, core["viterbi_mean"], 1e-12)
    assert hmm.valid_prior(w) == bool(core["valid"])
    _close(dist.dirichlet_tau(w.A), core["dirichlet_tau"], 1e-12)
    _close(dist.normwish_kl_div(w, u), core["normwish_kl"], 1e-12)
    _close(dist.dirichlet_kl_div(w.A, u.A), core["dirichlet_kl_A"], 1e-12)
    _close(dist.dirichlet_kl_div(w.pi, u.pi), core["dirichlet_kl_pi"], 1e-12)


# --------------------------------------------------------------------------- #
# empirical Bayes
# --------------------------------------------------------------------------- #
def test_hyperparameter_steps(eb):
    posteriors = [_params(p) for p in eb["posterior"]]
    stacked = hmm._stack(posteriors)
    m, beta, a, b = dist.normgamma_h_step(
        stacked["mu"], stacked["beta"], stacked["a"], stacked["b"], 1
    )
    _close(m, eb["ng_m"], ITERATIVE)
    _close(beta, eb["ng_beta"], ITERATIVE)
    _close(a, eb["ng_a"], ITERATIVE)
    _close(b, eb["ng_b"], ITERATIVE)
    _close(dist.dirichlet_h_step(stacked["A"]), eb["dir_A"], ITERATIVE)
    _close(dist.dirichlet_h_step(stacked["pi"]), eb["dir_pi"], ITERATIVE)
    _assert_params(hmm.h_step(posteriors), eb["h_step_no_expect"], ITERATIVE)


def test_three_empirical_bayes_iterations(eb, traces):
    """run_ebayes.m with Restarts 1: lower bound per iteration and the final prior."""
    analysis = Analysis(states=3, prior=_params(eb["prior0"]))
    run = ebayes.run_ebayes(
        analysis,
        traces,
        restarts=int(eb["restarts"].item()),
        precision=float(eb["precision"].item()),
        max_iter=int(eb["max_iter"].item()),
    )
    events = []
    while True:
        try:
            events.append(next(run))
        except StopIteration as stop:
            history = stop.value
            break
    assert [e["it"] for e in events if e["kind"] == "iteration"] == [1, 2, 3]
    _close(history, eb["L"], 1e-12)
    _assert_params(analysis.prior, eb["prior"], ITERATIVE)
    _close(analysis.lowerbound, eb["lowerbound_3"], ITERATIVE)
    np.testing.assert_array_equal(analysis.restart, np.ravel(eb["restart_3"]).astype(int))
    for n, record in enumerate(eb["posterior"]):
        _assert_params(analysis.posterior[n], record, ITERATIVE)
        np.testing.assert_array_equal(
            analysis.viterbi[n].state, np.ravel(eb["viterbi"][n]["state"]).astype(int)
        )
        for name in ("z", "z1", "zz", "x", "xx"):
            _close(getattr(analysis.expect[n], name), eb["expect"][n][name], ITERATIVE)


# --------------------------------------------------------------------------- #
# summary
# --------------------------------------------------------------------------- #
def _compare_report(actual, expected, path=""):
    """Walk both reports: same keys in the same order, same values."""
    if isinstance(expected, dict):
        assert list(actual) == list(expected), path
        for key in expected:
            _compare_report(actual[key], expected[key], f"{path}.{key}")
    elif isinstance(expected, str) or (
        isinstance(expected, list) and expected and isinstance(expected[0], str)
    ):
        assert actual == expected, path
    else:
        _close(actual, expected, ITERATIVE)


def test_h_step_remap_and_report(eb, traces):
    rep = _load("report")
    prior = _params(eb["prior"])
    expect = [_expect(e) for e in eb["expect"]]
    u, _, _ = hmm.h_step_remap(prior, expect)
    _assert_params(u, rep["remap_u"], ITERATIVE)
    u, w, e = hmm.h_step_remap(prior, expect, [1, 1, 2])
    _assert_params(u, rep["merge_u"], ITERATIVE)
    for n in range(len(expect)):
        _assert_params(w[n], rep["merge_w"][n], ITERATIVE)
        for name in ("z", "z1", "zz", "x", "xx"):
            _close(getattr(e[n], name), rep["merge_e"][n][name], ITERATIVE)
    reports = hmm.report(
        traces,
        prior,
        expect,
        lowerbound=np.ravel(eb["lowerbound_3"]),
        splits=[list(range(6)), [0, 2, 4]],
        labels=["all", "odd"],
    )
    assert len(reports) == 2
    for actual, expected in zip(reports, rep["report"]):
        _compare_report(actual, expected)


def test_photobleach_index():
    pb = _load("photobleach")
    for name in ("donor", "acceptor", "step"):
        index, d = hmm.photobleach_index(pb[name])
        assert index == int(np.ravel(pb[f"{name}_index"])[0])
        # MATLAB builds the running sums by matrix products, this port by cumsum
        _close(d, pb[f"{name}_d"], 1e-9)


# --------------------------------------------------------------------------- #
# plots
# --------------------------------------------------------------------------- #
def _compare_lines(actual, expected, rtol):
    assert len(actual) == len(expected)
    for a, e in zip(actual, expected):
        for key in ("xdata", "ydata"):
            if np.size(e[key]):
                _close(a[key], e[key], rtol)
            else:
                assert np.size(a[key]) == 0
        if isinstance(e.get("linestyle"), str):
            assert a["linestyle"] == e["linestyle"]
        if isinstance(e.get("marker"), str):
            assert a["marker"] == e["marker"]
        if isinstance(e.get("displayname"), str):
            assert a["displayname"] == e["displayname"]


def test_plot_data(eb, traces):
    pl = _load("plots")
    x = np.concatenate(traces)
    state = np.concatenate([np.ravel(v["state"]).astype(int) for v in eb["viterbi"]])
    bins = plots.get_bins(x, 200, min(0.5 / 6, 1e-2))
    _close(bins, pl["bins"], 1e-12)
    counts, _ = plots.whist(x, bins, state=state, num_states=3)
    _close(counts, pl["whist_counts"], 0)
    colours = plots.line_colors(3)
    obs = plots.state_obs(x, xdata=bins, state=state, num_states=3, color=colours)
    _compare_lines(obs, pl["obs"], 1e-12)
    x_lim, y_lim = plots.get_lim(obs, 1e-2, [0.05, 0.05, 0.05, 0.15])
    _close(x_lim, pl["obs_xlim"], 1e-12)
    _close(y_lim, pl["obs_ylim"], 1e-12)

    u = _params(eb["prior"])
    u_a, u_b = 0.5 * u.nu, 0.5 / u.W
    prior = {
        "mean": plots.state_mean(u.mu, u.beta, u_a, u_b, color=colours, linestyle="--"),
        "noise": plots.state_stdev(u_a, u_b, color=colours, linestyle="--"),
        "dwell": plots.state_dwell(u.A, color=colours, linestyle="--"),
    }
    posteriors = [_params(p) for p in eb["posterior"]]
    stacked = hmm._stack(posteriors)
    e_tau = -1.0 / np.log(np.diag(hmm.normalize(stacked["A"].mean(axis=2), axis=1)[0]))
    posterior = {
        "mean": plots.mean_lines(
            plots.state_mean(
                stacked["mu"], stacked["beta"], stacked["a"], stacked["b"], color=colours
            )
        ),
        "noise": plots.mean_lines(plots.state_stdev(stacked["a"], stacked["b"], color=colours)),
        "dwell": plots.mean_lines(
            plots.state_dwell(
                stacked["A"],
                color=colours,
                xdata=[np.exp(np.linspace(np.log(0.01 * t), np.log(100 * t), 101)) for t in e_tau],
            )
        ),
    }
    # the density evaluations go through gammaln of large shapes: 1e-11
    for name in ("mean", "noise", "dwell"):
        _compare_lines(prior[name], pl[f"prior_{name}"], ITERATIVE * 10)
        _compare_lines(posterior[name], pl[f"post_{name}"], ITERATIVE * 10)

    # refresh_ensemble_plots assembles the same curves with the same limits
    series = [
        Series(
            file="f",
            label=str(n),
            group="group 1",
            time=np.arange(1, t.size + 1),
            signal=t,
            donor=t,
            acceptor=t,
            crop_min=1,
            crop_max=t.size,
        )
        for n, t in enumerate(traces)
    ]
    analysis = Analysis(
        states=3,
        prior=u,
        posterior=posteriors,
        expect=[_expect(e) for e in eb["expect"]],
        viterbi=[None] * len(traces),
    )
    for n, v in enumerate(eb["viterbi"]):
        analysis.viterbi[n] = Viterbi(
            state=np.ravel(v["state"]).astype(int), mean=np.ravel(v["mean"])
        )
    view = plots.refresh_ensemble_plots(series, analysis, Controls(), traces)
    _close(view["obs"]["xlim"], pl["obs_xlim"], 1e-12)
    _close(view["signal_ylim"], pl["obs_xlim"], 1e-12)
    _close(pl["scale"], np.stack([e.z for e in analysis.expect], axis=1).mean(axis=1), 1e-12)
    for name in ("mean", "noise", "dwell"):
        _close(view[name]["xlim"], pl[f"{name}_xlim"], ITERATIVE)
        _close(view[name]["ylim"], pl[f"{name}_ylim"], ITERATIVE)
    assert view["dwell"]["xscale"] == "log"


def test_time_series_lines(eb, traces):
    pl = _load("plots")
    w = _params(eb["posterior"][0])
    state, _ = hmm.viterbi_vb(w, traces[0][10:100])
    np.testing.assert_array_equal(state, np.ravel(pl["ts_state"]).astype(int))
    colours = [(0.4, 0.4, 0.4), (0.66, 0.33, 0.33), *plots.line_colors(3)]
    lines = plots.time_series(
        traces[0],
        np.arange(1, traces[0].size + 1),
        crop_min=11,
        crop_max=100,
        state=state,
        num_states=3,
        colors=colours,
        markersize=4,
    )
    _compare_lines(lines, pl["time_series"], 1e-12)


def test_num_to_str():
    pl = _load("plots")
    assert plots.num_to_str([0, 0.2, 0.25, 1, 10]) == pl["num_to_str_a"]
    assert plots.num_to_str([0, 0.001, 1000, 12345]) == pl["num_to_str_b"]


# --------------------------------------------------------------------------- #
# a real MATLAB run
# --------------------------------------------------------------------------- #
def test_matlab_session_lower_bounds_and_viterbi():
    session = json.loads((DATA / "ebfret_session_k4.json").read_text())
    prior = HmmParams(**{k: np.asarray(session["prior"][k], dtype=float) for k in FIELDS})
    for record in session["series"]:
        x = np.asarray(record["signal"], dtype=float)
        w = HmmParams(**{k: np.asarray(record["posterior"][k], dtype=float) for k in FIELDS})
        _, L, _ = hmm.vbayes(x, w, prior)
        # one VBEM iteration past convergence (threshold 1e-5) and MEX single
        # precision separate the two: measured <= 2e-8 relative
        assert L[0] == pytest.approx(record["lowerbound"], rel=1e-7)
        state, mean = hmm.viterbi_vb(w, x)
        np.testing.assert_array_equal(state, np.asarray(record["viterbi_state"], dtype=int))
        _close(mean, record["viterbi_mean"], 1e-12)
