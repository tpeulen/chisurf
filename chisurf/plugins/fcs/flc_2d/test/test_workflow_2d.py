"""The reference's 2D-MEM minimization and its IRF-rise scan and averaging drivers.

The deterministic pieces (basis, prior, start values, rise-point sequences) are pinned
against the MATLAB in ``test_exp_curve.py``; the objective is the ``Reproduct`` pinned in
``test_reproduct.py``. What is tested here is that the minimizer optimizes exactly that
objective, runs the reference's schedule, and that the scan finds the IRF placement of
a simulated measurement whose placement is known.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.fcs.flc_2d.fit import minimize_q as MQ
from chisurf.plugins.fcs.flc_2d.fit.reproduct import reproduce_global_2d
from chisurf.plugins.fcs.flc_2d.fit.workflow_2d import average_2d_mem, search_irf_rise_2d


def _problem(seed=0, n=14, n_comp=6, n_lags=2):
    rng = np.random.default_rng(seed)
    axis = np.cumsum(rng.uniform(0.01, 0.2, n))
    E = rng.random((n, n_comp))
    A = rng.random((n_comp, 2))
    A[1, 0] = 0.0
    G = np.stack([np.array([[1.0, 0.2], [0.2, 0.8]])] * n_lags)
    data = np.stack([E @ A @ G[t] @ A.T @ E.T + rng.random((n, n)) for t in range(n_lags)])
    return axis, E, A, G, data


@pytest.mark.parametrize(("fix_A", "fix_G", "fix_y0"), [(2, 3, 2), (0, 0, 0), (3, 2, 1), (1, 3, 2)])
def test_the_objective_is_the_reproduction_and_its_gradient_is_exact(fix_A, fix_G, fix_y0):
    axis, E, A, G, data = _problem()
    mi = MQ.mi_model(A + 0.1, np.linspace(0.5, 3, 6), 3.0, 0.5, 0)
    obj = MQ._Objective(
        data,
        data,
        axis,
        E,
        A,
        G,
        np.array([0.3, 0.4]),
        np.full(2, fix_A),
        np.full((2, 2, 2), fix_G),
        np.full(2, fix_y0),
    )
    x = obj.start() * 1.1 + 0.05
    q, grad, (chi2, S) = obj(x, mi, 0.7)
    A_x, G_x, y_x = obj.unpack(x)
    rep = reproduce_global_2d(A_x, G_x, E, axis, y0=y_x, data=data, mi=mi, regulator=0.7)
    assert q == pytest.approx(rep.estimator_q, rel=1e-12)
    assert chi2 == pytest.approx(rep.chi2, rel=1e-12)
    h = 1e-6
    numeric = np.array(
        [
            (obj(x + h * e, mi, 0.7)[0] - obj(x - h * e, mi, 0.7)[0]) / (2 * h)
            for e in np.eye(x.size)
        ]
    )
    np.testing.assert_allclose(grad, numeric, rtol=2e-4, atol=1e-6)


def test_the_schedule_ramps_the_regulator_and_honours_the_break():
    axis, E, A, G, data = _problem(n_lags=1)
    tau = np.linspace(0.5, 3, 6)
    kw = dict(fit_start=1, t_min_ns=0.5, t_max_ns=3.0, initial_y0=0.2)
    r = MQ.minimize_q(
        data, axis, E, tau, A + 0.1, n_regulator_trials=6, regulator=0.5, regulator_factor=2.0, **kw
    )
    np.testing.assert_allclose(r.q_table[:, 0], 0.5 * 2.0 ** np.arange(6))
    # the entropy weight falls along the ramp, so the misfit may only shrink
    assert r.q_table[-1, 2] <= r.q_table[0, 2] * (1 + 1e-9)
    stopped = MQ.minimize_q(
        data, axis, E, tau, A + 0.1, n_regulator_trials=6, break_factor=-50, **kw
    )
    assert stopped.q_table.shape[0] == 1


def _simulated_matrices():
    from chisurf.plugins.fcs.flc_2d.bootstrap import separate_data_2d_fdc
    from chisurf.plugins.fcs.flc_2d.simulate import simulate_photon_stream

    from .conftest import matlab_sampled_irf, reference_irf

    irf, x = reference_irf()
    molecules = []
    for j in range(2):
        s = simulate_photon_stream(
            np.array([[0, 30.0], [10, 0]]),
            (1.0, 3.0),
            (1e4, 1e4),
            total_time_s=30,
            irf=matlab_sampled_irf(irf),
            irf_time_ns=x,
            seed=70 + j,
        )
        molecules.append((s.macro_times, s.micro_times))
    # the reference's 2D search: one lag of 100 us, window 10 us, gate 0.5-12.2 ns
    sep = separate_data_2d_fdc(
        molecules, [100], 10, tMin=125, tMax=3050, lint_bin_factor=4, logt_imax=100, n_chunks=4
    )
    kw = dict(
        irf=irf,
        xdata_ns=x,
        estimates=[0, 1, 1, 0.3, 1, 3, 0.3],
        t_min_ns=0.5,
        t_max_ns=12.2,
        t_step_ns=0.004,
        lint_bin_factor=4,
        logt_imax=100,
        tau_ns=np.arange(0.2, 5.01, 0.2),
        n_short_trials=60,
        n_lag_trials=5,
        n_global_trials=60,
    )
    return sep.total(), kw


@pytest.mark.slow
def test_the_rise_scan_finds_the_simulated_irf_placement():
    """The data were simulated with the IRF where rise point 300 puts it.

    Measured 2026-09-17 on this stream (600k photons): chi2 0.213 at 270, 0.101 at
    288-294, 0.105 at 300, 0.304 at 330; best 294. Lifetimes 0.8 / 2.9 ns near the
    minimum. The gate starts one channel before the data's first bin, which is why
    the minimum sits a few channels below 300.
    """
    mats, kw = _simulated_matrices()
    res = search_irf_rise_2d(mats, rise_points_irf=list(range(270, 331, 6)), **kw)
    assert 285 <= res.best <= 303, res.best
    chi2 = res.q[:, 1]
    assert chi2[0] > 1.5 * chi2.min() and chi2[-1] > 1.5 * chi2.min()

    avg = average_2d_mem(mats, center=res.best, n_points=3, keep_runs=True, **kw)
    np.testing.assert_array_equal(avg.rise_points_irf, res.best - 1 + np.arange(3))
    np.testing.assert_allclose(
        avg.correlations, np.mean([r.correlations for r in avg.runs], axis=0)
    )
    np.testing.assert_allclose(avg.model_log, np.mean([r.model_log for r in avg.runs], axis=0))
    # the averaging driver fixes the amplitudes at the scaled start distribution
    for run in avg.runs:
        np.testing.assert_allclose(run.amplitudes, run.short.amplitudes)


def test_the_cli_runs_the_scan_and_the_average(tmp_path, monkeypatch):
    """``flc-2d rise-search-2d`` / ``average-2d`` on one small simulated molecule."""
    from click.testing import CliRunner

    from chisurf.plugins.fcs.flc_2d import api
    from chisurf.plugins.fcs.flc_2d.cli.main import cli
    from chisurf.plugins.fcs.flc_2d.simulate import simulate_photon_stream

    from .conftest import reference_irf

    irf, x = reference_irf()
    s = simulate_photon_stream(
        np.array([[0, 30.0], [10, 0]]),
        (1.0, 3.0),
        (1e4, 1e4),
        total_time_s=2,
        irf=np.clip(irf, 0, None),
        irf_time_ns=x,
        seed=5,
    )
    f = tmp_path / "m0.ptu"
    f.write_bytes(b"")
    monkeypatch.setattr(
        api,
        "load_tttr",
        lambda path, routing_channels=None: api.TttrData(
            s.macro_times, s.micro_times, np.zeros(1), 1e-6, 0.004, 3127
        ),
    )
    irf_file = tmp_path / "irf.npz"
    np.savez(irf_file, irf=irf, irf_time_ns=x)
    common = [
        str(f),
        "--irf",
        str(irf_file),
        "--dt",
        "100",
        "--ddt",
        "10",
        "--tmax-ns",
        "10",
        "--log-bins",
        "40",
        "--short-trials",
        "2",
        "--lag-trials",
        "1",
        "--global-trials",
        "2",
    ]
    out = tmp_path / "scan.npz"
    r = CliRunner().invoke(
        cli, ["rise-search-2d", *common, "--center", "300", "--points", "2", "-o", str(out)]
    )
    assert r.exit_code == 0, r.output
    with np.load(out) as z:
        assert z["q_chi2_s"].shape == (2, 3) and int(z["best"]) in (299, 300)
    out = tmp_path / "avg.npz"
    r = CliRunner().invoke(
        cli, ["average-2d", *common, "--center", "300", "--points", "2", "-o", str(out)]
    )
    assert r.exit_code == 0, r.output
    with np.load(out) as z:
        assert z["model_log"].shape == (1, 40, 40)
