"""The kappa^2 calculator, checked against values it cannot get wrong.

This plugin turns residual anisotropies into an orientation-factor
distribution, and that distribution is what turns a FRET distance into a
distance *range*. Two properties pin it down without needing a reference
implementation: the mean orientation factor is 2/3, and a reported statistic
must not depend on how many histogram bins the caller asked for.

Both were violated. The moments were taken from the histogram paired with the
*upper* bin edges, so every mean sat half a bin too high and moved when
``n_bins`` changed; the isotropic model, whose mean is exactly 2/3, reported
0.71.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.calculator.kappa2_dist.core.algorithms import compute_kappa2_dist

#: Residual anisotropies of a real donor (measured from the VV/VH pair in
#: test/data) with plausible acceptor values.
ANISOTROPIES = {"r_0": 0.38, "r_Dinf": 0.0453, "r_Ainf": 0.10, "r_ADinf": 0.005}


@pytest.fixture(autouse=True)
def _seeded():
    """The cone model samples orientations; keep it reproducible."""
    np.random.seed(20260726)


def test_the_isotropic_model_averages_two_thirds():
    """Its exact value, and the reason 2/3 is quoted everywhere."""
    result = compute_kappa2_dist(model_type="isotropic", r_0=0.38)
    assert result["k2_mean"] == pytest.approx(2.0 / 3.0, abs=0.01)


@pytest.mark.parametrize("model_type", ["isotropic", "cone"])
def test_the_reported_mean_does_not_depend_on_the_bin_count(model_type):
    """``n_bins`` chooses a plot's resolution, not the answer."""
    means = [
        compute_kappa2_dist(model_type=model_type, n_bins=n, **ANISOTROPIES)["k2_mean"]
        for n in (61, 131, 501)
    ]
    assert max(means) - min(means) < 0.03, f"{model_type}: means drift with n_bins: {means}"


def test_the_cone_model_also_averages_two_thirds():
    """Restraining the dyes shapes the distribution; it does not move its mean."""
    result = compute_kappa2_dist(model_type="cone", **ANISOTROPIES)
    assert result["k2_mean"] == pytest.approx(2.0 / 3.0, abs=0.05)
    assert result["k2_sd"] > 0.05, "a cone model should carry real spread"


def test_an_apparent_distance_is_unbiased_when_the_assumption_holds():
    """Assuming the kappa^2 the model produces must leave the distance alone."""
    result = compute_kappa2_dist(model_type="cone", kappa2_true=2.0 / 3.0, **ANISOTROPIES)
    assert result["Rapp_mean"] == pytest.approx(1.0, abs=0.02)
    assert 0.0 < result["RappSD"] < 0.5


def test_the_order_parameters_follow_from_the_anisotropies():
    """S^2 = sqrt(r_inf / r_0), donor negative by the usual convention."""
    result = compute_kappa2_dist(model_type="cone", **ANISOTROPIES)
    assert result["SD2"] == pytest.approx(-np.sqrt(0.0453 / 0.38), rel=1e-6)
    assert result["SA2"] == pytest.approx(np.sqrt(0.10 / 0.38), rel=1e-6)
    assert 0.0 <= result["delta_deg"] <= 180.0


def test_the_histogram_still_has_the_resolution_that_was_asked_for():
    """Fixing the statistics must not change what gets plotted."""
    result = compute_kappa2_dist(model_type="cone", n_bins=61, **ANISOTROPIES)
    assert len(result["k2_scale"]) == len(result["k2_hist"]) + 1


def test_the_advertised_rpc_method_runs():
    """The manifest promises ``kappa2_dist.compute``; it has to answer."""
    from chisurf.plugins.calculator.kappa2_dist.backend.services import register_services

    handlers: dict = {}
    register_services(type("D", (), {"register": lambda self, n, h: handlers.__setitem__(n, h)})())

    assert "kappa2_dist.compute" in handlers
    reply = handlers["kappa2_dist.compute"]({"model_type": "cone", **ANISOTROPIES})
    assert reply["ok"], reply
    assert reply["result"]["k2_mean"] == pytest.approx(2.0 / 3.0, abs=0.05)


def test_an_unknown_model_is_refused_rather_than_guessed():
    with pytest.raises(ValueError, match="model_type"):
        compute_kappa2_dist(model_type="wobble", **ANISOTROPIES)
