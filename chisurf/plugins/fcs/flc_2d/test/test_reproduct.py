"""Reproducing decays and 2D-FDC/2D-FLC maps from fitted parameters.

Two anchors. The fixture ``test/data/flc_2d/matlab_reproduct.npz`` holds inputs and
the outputs of the original ``TK_FitF_Reproduct1DFDC``/``_02``,
``TK_FitF_Reproduct2DFDCand2DFLC_03`` and ``TK_GFitF_Reproduct2DFDCand2DFLC_03``,
run in Octave on 2026-09-17 (every fix flag, a zero amplitude for the floor, a
non-uniform axis for the bin widths): the port agreed to 2e-16 relative. And the
simulated reference stream: a 2D-FDC built from photons must be reproduced by the
ground-truth two-state parameters, and a fit reproduced on its own basis must give back
exactly the model it fitted.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.plugins.fcs.flc_2d import api
from chisurf.plugins.fcs.flc_2d.fit import reproduct as R

_FIXTURE = (
    pathlib.Path(__file__).resolve().parents[5]
    / "test"
    / "data"
    / "flc_2d"
    / "matlab_reproduct.npz"
)
RTOL = 1e-12


@pytest.fixture(scope="module")
def matlab():
    assert _FIXTURE.is_file(), f"committed fixture is missing: {_FIXTURE}"
    with np.load(_FIXTURE) as z:
        i = {k[3:]: z[k] for k in z.files if k.startswith("in_")}
        o = {k[4:]: z[k] for k in z.files if k.startswith("out_")}
    return i, o


def _lags_first(a):
    return np.moveaxis(np.asarray(a), -1, 0)


def test_1d_reproduction_matches_the_matlab(matlab):
    i, o = matlab
    nc = i["E"].shape[1]
    mi = i["mi"][:, 0]
    # TK_FitF_Reproduct1DFDC: abs() amplitudes, no y0, bin-width-weighted chi2
    A, _ = R.unpack_estimates_1d(i["est1"], nc, fix=2)
    r = R.reproduce_1d(
        A,
        i["E"],
        i["axis"],
        data=i["d1"],
        data_cor=i["c1"],
        mi=mi,
        regulator=float(i["reg"]),
        area_weighted=True,
    )
    np.testing.assert_allclose(r.model, o["m1a"], rtol=RTOL)
    np.testing.assert_allclose(r.amplitudes[:, 0], o["A1a"], rtol=RTOL)
    np.testing.assert_allclose(
        [r.chi2, r.entropy, r.estimator_q], [o["K1a"], o["S1a"], o["Q1a"]], rtol=RTOL
    )
    # _02: free amplitudes and y0 scaled by bin width
    A, y0 = R.unpack_estimates_1d(i["est1p"], nc, fix=0, fix_y0=0)
    r = R.reproduce_1d(
        A,
        i["E"],
        i["axis"],
        y0=y0,
        data=i["d1"],
        data_cor=i["c1"],
        mi=mi,
        regulator=float(i["reg"]),
    )
    np.testing.assert_allclose(r.model, o["m1b"], rtol=RTOL)
    np.testing.assert_allclose(
        [r.y0, r.chi2, r.entropy, r.estimator_q],
        [o["y1b"], o["K1b"], o["S1b"], o["Q1b"]],
        rtol=RTOL,
    )
    # _02: everything fixed at the initial values
    A, y0 = R.unpack_estimates_1d(
        i["est1"], nc, fix=1, initial_amplitudes=i["initA"][:, 0], fix_y0=1, initial_y0=0.4
    )
    r = R.reproduce_1d(
        A,
        i["E"],
        i["axis"],
        y0=y0,
        data=i["d1"],
        data_cor=i["c1"],
        mi=mi,
        regulator=float(i["reg"]),
    )
    np.testing.assert_allclose(r.model, o["m1c"], rtol=RTOL)
    np.testing.assert_allclose([r.chi2, r.estimator_q], [o["K1c"], o["Q1c"]], rtol=RTOL)


@pytest.mark.parametrize("tag", ["2a", "2b"])
def test_2d_reproduction_matches_the_matlab(matlab, tag):
    i, o = matlab
    nc = i["E"].shape[1]
    kw = dict(
        fix_amplitudes=i["fixA" + tag], fix_correlation=i["fixG" + tag], fix_y0=i["fixy" + tag]
    )
    if tag == "2b":
        kw["initial_y0"] = float(i["inity2b"])
    A, G, y0 = R.unpack_estimates_2d(
        i["est" + tag], nc, 2, initial_amplitudes=i["initA"], initial_correlation=i["initG"], **kw
    )
    r = R.reproduce_2d(
        A,
        G,
        i["E"],
        i["axis"],
        y0=y0,
        data=i["data"],
        data_cor=i["cor"],
        mi=i["mi"],
        regulator=float(i["reg"]),
    )
    np.testing.assert_allclose(r.flc_map, o["f" + tag], rtol=RTOL)
    np.testing.assert_allclose(r.model, o["m" + tag], rtol=RTOL)
    np.testing.assert_allclose(r.amplitudes, o["A" + tag], rtol=RTOL)
    np.testing.assert_allclose(r.correlation, o["G" + tag], rtol=RTOL)
    np.testing.assert_allclose(
        [r.y0, r.chi2, r.entropy, r.estimator_q],
        [o["y" + tag], o["K" + tag], o["S" + tag], o["Q" + tag]],
        rtol=RTOL,
    )


def test_global_reproduction_matches_the_matlab(matlab):
    i, o = matlab
    nc = i["E"].shape[1]
    A, Gs, y0s = R.unpack_estimates_global_2d(
        i["estg"],
        nc,
        2,
        3,
        initial_amplitudes=i["initA"],
        initial_correlations=_lags_first(i["initGs"]),
        initial_y0=i["inityg"],
        fix_amplitudes=i["fixAg"],
        fix_correlations=_lags_first(i["fixGg"]),
        fix_y0=i["fixyg"],
    )
    r = R.reproduce_global_2d(
        A,
        Gs,
        i["E"],
        i["axis"],
        y0=y0s,
        data=_lags_first(i["dstack"]),
        data_cor=_lags_first(i["cstack"]),
        mi=i["mi"],
        regulator=float(i["reg"]),
    )
    np.testing.assert_allclose(r.flc_map, _lags_first(o["fg"]), rtol=RTOL)
    np.testing.assert_allclose(r.model, _lags_first(o["mg"]), rtol=RTOL)
    np.testing.assert_allclose(r.correlation, _lags_first(o["Gg"]), rtol=RTOL)
    np.testing.assert_allclose(r.y0, o["yg"], rtol=RTOL)
    np.testing.assert_allclose(
        [r.chi2, r.entropy, r.estimator_q], [o["Kg"], o["Sg"], o["Qg"]], rtol=RTOL
    )


def test_a_fit_reproduced_on_its_own_basis_gives_back_its_model():
    """The fits and the reproduction share one forward model."""
    time_ns = np.linspace(0, 16, 60)
    tau = api.lifetime_grid(0.3, 8.0, 16)
    E = api.build_exp_basis(time_ns, tau)
    decay = 1e4 * (0.4 * np.exp(-time_ns / 1.0) + 0.6 * np.exp(-time_ns / 3.0)) + 20.0
    fit1 = api.ilt_1d(decay, E, tau, reg=1e-3)
    np.testing.assert_allclose(R.reproduce_result(fit1, E).model, fit1.model, rtol=1e-12)
    P = np.zeros((tau.size, tau.size))
    P[4, 4], P[10, 10], P[4, 10] = 1.0, 0.6, 0.2
    P[10, 4] = 0.2
    M = E @ P @ E.T * 1e3 + 5.0
    fit2 = api.ilt_2d(M, E, tau)
    np.testing.assert_allclose(api.reproduce_fit(fit2, time_ns).model, fit2.model, rtol=1e-12)
    fitg = api.global_lifetime_mem([M, M * 0.9], time_ns, n_components=16)
    rep = api.reproduce_fit(fitg, time_ns, data=np.stack([M, M * 0.9]))
    assert rep.model.shape == (2, 60, 60) and np.isfinite(rep.chi2)


@pytest.mark.slow
def test_ground_truth_parameters_reproduce_the_simulated_2d_fdc(reference_photons):
    """Two-state truth -> the photon-built 2D-FDC, to within counting noise.

    At a lag far beyond the 25 ms relaxation the pair matrix is the outer product of
    the decay with itself, so ``A`` = the two species' amplitudes (population x
    brightness on the lifetime grid) and ``G`` = 1 reproduce it up to one
    scale. The reproduction must explain the matrix far better than a single-lifetime
    model on the same basis does.
    """
    rp = reference_photons
    lin_bins = 60
    out = api.two_d_fdc(
        rp["macro_ticks"],
        rp["micro_ticks"],
        dT=500_000,
        ddT=4_000,
        tMin=1,
        tMax=rp["n_microtime_bins"],
        max_bins=lin_bins,
    )
    M = out["mat_lin"].astype(float)
    time_ns = (out["mat_lin_t"] + 1) * rp["micro_resolution_ns"]
    tau = np.array([1.0, 3.0])
    # equal brightness: photons per species follow the populations, and a peak-normalized
    # basis column carries a decay of area tau, so the amplitude is population / tau
    amplitudes = (np.array([0.25, 0.75]) / tau)[:, None]
    kw = dict(tau_grid=tau, irf=rp["irf"], irf_time_ns=rp["irf_time_ns"])
    truth = api.reproduce_2d_fdc(amplitudes, np.eye(1), time_ns, **kw)
    single = api.reproduce_2d_fdc(
        np.array([[0.0], [1.0]]), np.eye(1), time_ns, floor_zeros=False, **kw
    )

    def rel_misfit(model):
        scale = float(np.sum(model * M) / np.sum(model * model))
        return float(np.linalg.norm(M - scale * model) / np.linalg.norm(M))

    assert rel_misfit(truth.model) < 0.25
    assert rel_misfit(truth.model) < 0.5 * rel_misfit(single.model)


def test_the_cli_reproduces_maps_from_a_parameter_file(tmp_path):
    import json

    from click.testing import CliRunner

    from chisurf.plugins.fcs.flc_2d.cli.main import cli

    params = {
        "time_axis_ns": [0.0, 0.5, 1.0, 2.0, 4.0],
        "tau_grid": [1.0, 3.0],
        "amplitudes": [[0.25, 0.0], [0.0, 0.25]],
        "correlation": [[1.0, -0.1], [-0.1, 1.0]],
        "y0": 0.01,
    }
    f = tmp_path / "params.json"
    f.write_text(json.dumps(params))
    result = CliRunner().invoke(cli, ["reproduce", str(f)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    expected = api.reproduce_2d_fdc(
        np.asarray(params["amplitudes"]),
        np.asarray(params["correlation"]),
        np.asarray(params["time_axis_ns"]),
        tau_grid=np.asarray(params["tau_grid"]),
        y0=0.01,
    )
    np.testing.assert_allclose(payload["model"], expected.model)
    np.testing.assert_allclose(payload["flc_map"], expected.flc_map)
