"""Analytic FRET lines: internal physics and parity with the model-based generator."""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fluorescence.fret.lines import (
    donor_lifetime_spectrum,
    dynamic_fret_line,
    lifetime_averages,
    no_linker_line,
    static_fret_line,
)

TAU_D0 = 4.0
R0 = 52.0
SIGMA = 6.0


def test_no_linker_line_is_the_diagonal():
    """Without a distance distribution the line degenerates to E = 1 - tau/tau_D0."""
    line = no_linker_line(TAU_D0, n_points=64)
    np.testing.assert_allclose(line.tau_x, line.tau_f, rtol=1e-12)
    np.testing.assert_allclose(line.efficiency, 1.0 - line.tau_f / TAU_D0, atol=1e-12)


def test_multi_exponential_donor_curves_the_line():
    """A multi-exponential donor bends the line even without a linker distribution."""
    line = no_linker_line([(0.6, 4.0), (0.4, 1.5)], n_points=64)
    tau_d0 = 0.6 * 4.0 + 0.4 * 1.5
    assert line.tau_d0 == pytest.approx(tau_d0)
    # tau_f >= tau_x always (Cauchy-Schwarz), with equality only for a single lifetime
    assert np.all(line.tau_f >= line.tau_x - 1e-12)
    assert np.max(line.tau_f - line.tau_x) > 1e-3


def test_linker_width_raises_efficiency_at_a_given_lifetime():
    """Averaging over a distance distribution moves the line above the diagonal.

    The species-averaged lifetime (which sets E) drops faster than the
    fluorescence-averaged one (the measured axis), so a broadened population has
    a higher efficiency than a sharp one of the same apparent lifetime.
    """
    sharp = no_linker_line(TAU_D0, n_points=256)
    broad = static_fret_line(TAU_D0, r0=R0, sigma=10.0, n_points=256)
    tau = np.linspace(0.5, 3.0, 20)
    assert np.all(broad.efficiency_at(tau) > sharp.efficiency_at(tau))


def test_static_line_interpolators_are_inverse():
    """``efficiency_at`` and ``lifetime_at`` invert each other on the line."""
    line = static_fret_line(TAU_D0, r0=R0, sigma=SIGMA, n_points=400)
    e = np.linspace(0.1, 0.9, 17)
    np.testing.assert_allclose(line.efficiency_at(line.lifetime_at(e)), e, atol=2e-3)


def test_dynamic_line_lies_above_the_static_line():
    """Fast exchange between two states shifts a population off the static line.

    That offset is the standard sub-burst-dynamics diagnostic: mixing two states
    keeps the species-averaged lifetime linear in the fraction while the measured
    fluorescence-averaged lifetime is pulled towards the long-lifetime state.
    """
    static = static_fret_line(TAU_D0, r0=R0, sigma=SIGMA, n_points=400)
    dynamic = dynamic_fret_line(
        TAU_D0, r0=R0, sigma=SIGMA, distance_1=35.0, distance_2=75.0, n_points=200
    )
    inner = (dynamic.parameter > 0.1) & (dynamic.parameter < 0.9)
    deviation = static.deviation(dynamic.efficiency[inner], dynamic.tau_f[inner])
    assert np.all(deviation > 0.0)
    # the endpoints of the dynamic line are static states and must sit on the line
    assert abs(static.deviation(dynamic.efficiency[0], dynamic.tau_f[0])) < 5e-3


def test_lifetime_averages_match_the_definition():
    """The two averages are the first and the ratio of the second to first moment."""
    x, tau = donor_lifetime_spectrum([(0.3, 1.0), (0.7, 3.0)])
    tau_x, tau_f = lifetime_averages(x, tau)
    assert tau_x == pytest.approx(0.3 * 1.0 + 0.7 * 3.0)
    assert tau_f == pytest.approx((0.3 * 1.0 + 0.7 * 9.0) / (0.3 * 1.0 + 0.7 * 3.0))


def test_deviation_sign_follows_gamma_error():
    """A too large gamma pushes a static population below its own line.

    ``E = F_DA/(F_DA + gamma·F_DD)`` falls with ``gamma``, so over-estimating the
    detection factor produces exactly the negative off-line offset the
    lifetime-assisted calibration corrects for.
    """
    line = static_fret_line(TAU_D0, r0=R0, sigma=SIGMA)
    tau = 2.0
    e_true = float(line.efficiency_at(tau))
    ratio = e_true / (1.0 - e_true)  # F_DA/F_DD at the true gamma = 1
    e_high_gamma = ratio / (ratio + 2.0)
    assert line.deviation(e_high_gamma, tau) < 0.0


def test_overlay_contract():
    """The line exports the shared overlay dictionary used by the plot clients."""
    overlay = static_fret_line(TAU_D0).as_overlay()
    assert overlay["kind"] == "curve"
    assert overlay["axes"] == {
        "x": "tau_f", "y": "e_fret", "label": "E vs fluorescence-averaged lifetime"
    }
    assert len(overlay["x"]) == len(overlay["y"])


def test_parity_with_the_model_based_generator():
    """The analytic line reproduces the full ChiSurf model machinery.

    The model-driven generator builds a Gaussian FRET model, computes its decay
    moments and sweeps the mean distance. Because both describe the same curve in
    the E-tau plane, the efficiencies must agree *at matched lifetime* (the
    mapping from the mean distance onto the line differs slightly, as the model
    discretizes P(R) on its own logarithmic distance axis).
    """
    algorithms = pytest.importorskip("chisurf.plugins.fret_line.core.algorithms")
    components = [{
        "model_name": "FRET: FD (Gaussian)",
        "n_components": 1,
        "params": {"distance.mean.0": 50.0, "distance.sigma.0": SIGMA, "distance.amplitude.0": 1.0,
                   "fret.x_donly": 0.0, "fret.forster_radius": R0, "donor.tau.0": TAU_D0,
                   "donor.amplitude.0": 1.0, "fret.tau0": TAU_D0},
    }]
    res = algorithms.compute_fret_line(
        components, {"kind": "param", "component": 0, "name": "distance.mean.0"},
        20.0, 120.0, 40, tau_d0=TAU_D0,
    )
    assert res["ok"], res.get("error")
    tau_f = np.asarray(res["result"]["tau_f"])
    e_model = np.asarray(res["result"]["e_fret"])
    e_analytic = static_fret_line(
        TAU_D0, r0=R0, sigma=SIGMA, distance_range=(10.0, 200.0), n_points=400
    ).efficiency_at(tau_f)
    inside = (tau_f > 0.2) & (tau_f < 0.95 * TAU_D0)
    assert np.max(np.abs(e_model - e_analytic)[inside]) < 5e-3
