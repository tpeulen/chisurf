"""The reference's binned exponential basis, its priors and its driver start values.

``test/data/flc_2d/matlab_exp_curve.npz`` was recorded 2026-09-17 by running, in Octave,
the original ``TK_CreateExpCurve`` (four gates: two plain, one whose last linear bin is
mirror-padded by a single channel with the IRF shifted past the window end, one at
``lint_bin_factor = 1``), ``TK_mi_ModelFunction`` (types 0-3, two states), the
rise-point loops of ``TK_MyMain_Search_RiseIRF_2DMEM`` and ``TK_MyMain_Run_Ave2DMEM``
(lines copied verbatim), and lines 1-176 of ``TK_MyMain_Fit_2DMEM_04`` unchanged -- its
lifetime grid, start distribution, scaling, ``y0`` and settings -- on the reference IRF.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.plugins.fcs.flc_2d import api
from chisurf.plugins.fcs.flc_2d.fit.exp_curve import (
    create_exp_curve,
    matlab_lin_axis_ns,
    matlab_log_axis_ns,
)
from chisurf.plugins.fcs.flc_2d.fit.ilt import build_exp_basis
from chisurf.plugins.fcs.flc_2d.fit.minimize_q import (
    gaussian_initial_distribution,
    mi_model,
    scale_initial_distribution,
)
from chisurf.plugins.fcs.flc_2d.fit.workflow_2d import rise_points

_DATA = pathlib.Path(__file__).resolve().parents[5] / "test" / "data" / "flc_2d"


@pytest.fixture(scope="module")
def ref():
    f = _DATA / "matlab_exp_curve.npz"
    assert f.is_file(), f"committed fixture is missing: {f}"
    with np.load(f) as z:
        return {k: z[k] for k in z.files}


def _curves(ref, c):
    t_min, t_max, f, L, rfl, rirf, rmin, rmax = ref[f"p{c}"]
    return create_exp_curve(
        ref["Tau"], ref["xdata"], ref["IRF"], t_min_ns=t_min, t_max_ns=t_max, t_step_ns=0.004,
        lint_bin_factor=int(f), log_axis_ns=ref[f"logt{c}"], rise_point_fl=int(rfl),
        rise_point_irf=int(rirf), irf_range=(int(rmin), int(rmax)),
    ), (t_min, t_max, int(f), int(L))


@pytest.mark.parametrize("case", [1, 2, 3, 4])
def test_the_binned_basis_matches_the_matlab(ref, case):
    curves, (t_min, t_max, f, L) = _curves(ref, case)
    np.testing.assert_allclose(matlab_log_axis_ns(t_min, t_max, 0.004, f, L), ref[f"logt{case}"],
                               rtol=1e-14)
    np.testing.assert_allclose(matlab_lin_axis_ns(t_min, t_max, 0.004, f), ref[f"lint{case}"],
                               atol=1e-15)
    np.testing.assert_allclose(curves.binned_lin, ref[f"Elin{case}"], rtol=1e-12, atol=1e-14)
    np.testing.assert_allclose(curves.binned_log, ref[f"Elog{case}"], rtol=1e-12, atol=1e-14)
    if case == 3:
        np.testing.assert_allclose(curves.full, ref["E3"], rtol=1e-11, atol=1e-14)


def test_a_one_channel_bin_is_summed_across_lifetimes_as_matlab_does(ref):
    """At factor 1 every linear bin is ``sum`` of one row: a scalar in every column."""
    curves, _ = _curves(ref, 4)
    lin = curves.binned_lin
    assert np.allclose(lin, lin[:, :1])  # all columns equal
    np.testing.assert_allclose(lin[:, 0], curves.full[: lin.shape[0]].sum(axis=1), rtol=1e-12)


@pytest.mark.parametrize("mi_type", [0, 1, 2, 3])
def test_the_entropy_prior_matches_the_matlab(ref, mi_type):
    np.testing.assert_allclose(mi_model(ref["A"], ref["TauM"], 3.3, 0.5, mi_type),
                               ref[f"mi{mi_type}"], rtol=1e-13)


def test_the_rise_point_sequences_match_the_matlab(ref):
    np.testing.assert_array_equal(rise_points(310, 20), ref["search_rise"])
    np.testing.assert_array_equal(rise_points(300, 5), ref["average_rise"])


def test_the_driver_start_values_match_the_matlab(ref):
    """``TK_MyMain_Fit_2DMEM_04`` lines 1-176: grid, basis, start A, y0 and settings."""
    irf = np.load(_DATA / "reference_irf.npz")
    tau = np.arange(0.05, 5.05 + 1e-9, 0.05)
    np.testing.assert_allclose(tau, ref["prep_Tau"], atol=1e-15)
    curves = api.exp_curves(ref["prep_Tau"], irf["irf_time_ns"], irf["irf"], t_min_ns=0.5,
                            t_max_ns=3.3, t_step_ns=0.004, lint_bin_factor=4, logt_imax=20,
                            rise_point_irf=297)
    np.testing.assert_allclose(curves.binned_log, ref["prep_ExpCurve_Binned_log"], rtol=1e-12)
    np.testing.assert_allclose(curves.binned_lin, ref["prep_ExpCurve_Binned_lin"], rtol=1e-12)
    A0 = scale_initial_distribution(
        gaussian_initial_distribution(ref["prep_Tau"], [0, 1, 1, 0.3, 1, 3, 0.3]),
        curves.binned_log, float(ref["prep_data_max"]))
    np.testing.assert_allclose(A0, ref["prep_Tau_Initial_distribution"], rtol=1e-12, atol=1e-300)
    width = curves.lin_axis_ns[1] - curves.lin_axis_ns[0]
    assert 5000.0 / width == pytest.approx(float(ref["prep_Var_y0"]), rel=1e-14)
    settings = {k: float(ref[f"prep_{k}"]) for k in (
        "RangePoint_IRF_min", "RisePoint_FL", "y0", "FitStartI", "RegulatorConst",
        "RegulatorFactor", "TrialNumFor_RegulatorConst", "Linear0orLog1", "UseCor1orNot0",
        "mi_TypeSelect")}
    assert settings == {"RangePoint_IRF_min": 50, "RisePoint_FL": 300, "y0": 5000,
                        "FitStartI": 30, "RegulatorConst": 0.1, "RegulatorFactor": 1.4,
                        "TrialNumFor_RegulatorConst": 100, "Linear0orLog1": 1,
                        "UseCor1orNot0": 0, "mi_TypeSelect": 0}
    assert float(ref["prep_RangePoint_IRF_max"]) == irf["irf"].size - 90


def test_a_sampled_basis_is_close_on_the_linear_axis_and_wrong_on_the_log_axis():
    """Why log matrices need the binned basis, measured.

    Same IRF convolution, column sampled at the bin centre against summed over the
    bin, residual norm after the best scale: linear <= 1%, log median > 30%.
    """
    z = np.load(_DATA / "reference_irf.npz")
    tau = np.arange(0.05, 5.05 + 1e-9, 0.05)
    c = api.exp_curves(tau, z["irf_time_ns"], z["irf"], t_min_ns=0.5, t_max_ns=12.2,
                       t_step_ns=0.004, lint_bin_factor=4, logt_imax=100, rise_point_irf=300)

    def misfit(ref_cols, other):
        a, b = ref_cols, other
        s = np.sum(a * b, axis=0) / np.sum(b * b, axis=0)
        return np.linalg.norm(a - s * b, axis=0) / np.linalg.norm(a, axis=0)

    n = c.full.shape[0]
    lin_idx = np.minimum((c.lin_axis_ns / 0.004 + 2).astype(int), n - 1)
    edges = np.append(c.log_axis_ns[1:], 12.2 - 0.5)
    log_idx = np.minimum((0.5 * (c.log_axis_ns + edges) / 0.004).astype(int), n - 1)
    # the last linear bin is mirror-padded from a one-channel slice, which MATLAB's sum()
    # turns into a sum over all lifetimes -- at the reference's own default gate
    # (0.5-12.2 ns, factor 4) that bin is not a decay sample at all
    assert c.binned_lin[-1, 0] > 100 * c.binned_lin[-2, 0]
    m = min(lin_idx.size, c.binned_lin.shape[0]) - 1
    assert misfit(c.binned_lin[:m], c.full[lin_idx[:m]]).max() < 0.01
    assert np.median(misfit(c.binned_log, c.full[log_idx])) > 0.3


def test_a_log_axis_is_refused_without_a_binned_basis():
    time_ns = np.geomspace(0.01, 12.0, 30)
    M = np.ones((30, 30))
    with pytest.raises(ValueError, match="non-uniform"):
        api.two_d_spectrum(M, time_ns)
    E = build_exp_basis(np.linspace(0, 12, 30), np.array([1.0, 3.0]))
    res = api.two_d_spectrum(E @ np.eye(2) @ E.T, time_ns, basis=E, tau_grid=[1.0, 3.0])
    assert res.spectrum.shape == (2, 2)
