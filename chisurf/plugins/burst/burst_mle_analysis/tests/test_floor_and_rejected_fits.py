"""The fit's flat background is the burst decay's floor; fits that are no lifetime are excluded.

Owner, 2026-11-05: "seems like detector dark counts and bg are not accounted for" (the summed
decay's tail sat above the model: the background rate times the time in the bursts misses the
afterpulsing of the burst photons) and "the mean lifetimes are weird, outliers must be removed"
(G|G mean 882 ns over a median of 3.4 ns: fits at the lifetime's bound averaged in).
"""

import numpy as np
import pytest

from chisurf.plugins.burst.burst_mle_analysis import engine
from chisurf.plugins.burst.burst_mle_analysis._mp_worker import REJECT_REASONS, reject_reason
from chisurf.plugins.burst.burst_mle_analysis.gui import fit_view


def _decay(n=250, onset=40, floor=(21.0, 26.0), seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    shape = np.where(t >= onset, np.exp(-(t - onset) / 50.0), 0.0) * 5000
    irf = np.where(np.abs(t - onset - 3) < 3, 1.0, 0.0)
    vv = rng.poisson(shape + floor[0])
    vh = rng.poisson(0.5 * shape + floor[1])
    return np.hstack([vv, vh]).astype(float), np.hstack([irf, irf])


def test_the_floor_is_read_before_the_prompt():
    decay, irf = _decay()
    vv, vh, bins = engine.decay_floor(decay, irf, (0, 250))
    assert bins == 41 - engine.FLOOR_MARGIN_BINS  # the IRF rises at bin 41
    assert vv == pytest.approx(21.0, abs=2.5)
    assert vh == pytest.approx(26.0, abs=2.5)


def test_no_floor_when_the_prompt_opens_the_gate():
    decay, irf = _decay(onset=5)
    assert engine.decay_floor(decay, irf, (0, 250)) is None


def test_with_floor_keeps_the_scatter_and_replaces_the_flat_part():
    n = 100
    flat = np.full(2 * n, 2.0)
    scatter = np.zeros(2 * n)
    scatter[50] = 30.0
    out = engine.with_floor(flat + scatter, (20.0, 25.0), (10, 90), reference=(2.0, 2.0))
    assert out[50] == pytest.approx(20.0 + 30.0)
    assert out[20] == pytest.approx(20.0)
    assert out[n + 20] == pytest.approx(25.0)
    assert out[5] == 0.0 and out[n + 95] == 0.0  # outside the gate


def test_rho_is_free_by_default():
    settings = engine.MleSettings()
    names, _values, fixed = settings.parameter_state()
    assert dict(zip(names, fixed))["rho"] == 0
    assert dict(zip(names, fixed))["r0"] == 1
    assert settings.floor_from_bursts


@pytest.mark.parametrize(
    "x, converged, code",
    [
        ([3.4, 0.05, 0.38, 1.0], 1.0, 0),
        (None, None, 1),
        ([3.4, 0.05, 0.38, 1.0], 0.0, 2),
        ([np.nan, 0.05, 0.38, 1.0], 1.0, 3),
        ([-1.0, 0.05, 0.38, 1.0], 1.0, 4),
        ([0.01, 0.05, 0.38, 1.0], 1.0, 4),
        ([882.0, 0.05, 0.38, 1.0], 1.0, 5),
        ([3.4, 0.995, 0.38, 1.0], 1.0, 6),
    ],
)
def test_reject_reason(x, converged, code):
    cfg = {"model": "fit23", "dt": 0.08, "fit_window": (32, 230)}
    assert reject_reason(cfg, x, converged) == code
    assert code == 0 or code in REJECT_REASONS


def test_the_lifetime_table_excludes_rejected_fits():
    from chisurf.plugins.burst.burst_mle_analysis.gui.model import MleViewModel

    rows = [{"Tau (G|G)": 3.0, "Fit rejected (G|G)": 0}, {"Tau (G|G)": 4.0, "Fit rejected (G|G)": 0},
            {"Tau (G|G)": np.nan, "Fit rejected (G|G)": 5}, {"Tau (G|G)": np.nan, "Fit rejected (G|G)": 1}]
    assert fit_view.rejected_fits(rows) == {"G|G": {5: 1, 1: 1}}
    model = MleViewModel.__new__(MleViewModel)
    model.burst_results = rows
    (row,) = MleViewModel.lifetime_rows(model)
    assert row["n"] == "2" and row["excluded"] == "2"
    assert row["mean"] == "3.500"
    assert "longer than the fit window" in row["excluded_tip"]
