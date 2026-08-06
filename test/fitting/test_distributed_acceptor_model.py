"""The distributed-acceptor model, checked by recovering what it was given.

A model that builds a decay is not yet a model that *fits*. These tests take the
whole path: construct the model through a ``Fit``, generate a decay from a known
acceptor density, hand it back as data, release the density and see whether the
optimizer returns the number it started from.

The round-trip is the point. A stretched exponential and a two-exponential decay
are close enough over a limited time window that a model can look right while
recovering the wrong density, and only fitting simulated data with a known
answer catches that.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.data import DataCurve
from chisurf.core.fluorescence.fret.dimensionality import quench_decay


def _fit_with_model(x, y):
    """Build a Fit around the distributed-acceptor model on the given data."""
    import chisurf.core.fitting.fit as fit_mod

    from chisurf.core.models.tcspc.distributed_acceptor import (
        DistributedAcceptorModel,
    )

    return fit_mod.Fit(model_class=DistributedAcceptorModel, data=DataCurve(x=x, y=y))


@pytest.fixture
def time_axis():
    """Strictly positive: t**(d/6) is fine at zero but 1/x elsewhere is not."""
    return np.linspace(0.02, 40.0, 1024)


def test_the_model_computes_a_finite_decay(time_axis):
    """The minimum bar: it produces something to compare against data."""
    fit = _fit_with_model(time_axis, np.exp(-time_axis / 4.0))
    model = fit.model
    model.update_model()
    y = np.asarray(model.y, dtype=float)
    assert y.shape == time_axis.shape
    assert np.all(np.isfinite(y))
    assert y.max() > 0


def test_zero_density_is_the_unquenched_donor(time_axis):
    """With no acceptors the model must be the donor decay and nothing else."""
    fit = _fit_with_model(time_axis, np.exp(-time_axis / 4.0))
    model = fit.model
    model.c_over_c0 = 0.0
    unquenched = model.unconvolved_decay(time_axis)

    model.c_over_c0 = 1.5
    quenched = model.unconvolved_decay(time_axis)

    assert np.all(quenched <= unquenched + 1e-12)
    assert quenched[-1] < unquenched[-1]


@pytest.mark.parametrize("dimension", [1, 2, 3])
def test_the_reported_efficiency_follows_the_density(time_axis, dimension):
    """E is derived from C/C0, so it must move with it and stay bounded."""
    fit = _fit_with_model(time_axis, np.exp(-time_axis / 4.0))
    model = fit.model
    model.dimension = dimension
    model.c_over_c0 = 0.0
    assert model.fret_efficiency == pytest.approx(0.0, abs=1e-6)
    model.c_over_c0 = 1.0
    low = model.fret_efficiency
    model.c_over_c0 = 4.0
    high = model.fret_efficiency
    assert 0.0 < low < high < 1.0


@pytest.mark.parametrize("dimension", [1, 2, 3])
def test_the_absolute_density_matches_the_forster_volume(dimension):
    """acceptor_density is C/C0 times C0, so it must scale with R0 correctly."""
    from chisurf.core.fluorescence.fret.dimensionality import characteristic_density

    fit = _fit_with_model(np.linspace(0.02, 40.0, 128), np.exp(-np.linspace(0.02, 40.0, 128)))
    model = fit.model
    model.dimension = dimension
    model.forster_radius = 52.0
    model.c_over_c0 = 2.5
    expected = 2.5 * characteristic_density(52.0, dimension)
    assert model.acceptor_density == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize("dimension, truth", [(3, 0.9), (2, 1.3), (1, 1.7)])
def test_the_density_is_recovered_from_a_simulated_decay(time_axis, dimension, truth):
    """The round trip: simulate at a known C/C0, fit, get it back.

    The decay is built with the same analytic law the model uses, so this is a
    test of the *fit* -- that the parameter is reachable, released, and not
    degenerate with the donor lifetime -- rather than of the physics, which
    ``test_fret_dimensionality.py`` pins separately.
    """
    tau_d0 = 4.0
    donor = np.exp(-time_axis / tau_d0)
    y = quench_decay(donor, time_axis, tau_d0, truth, dimension)

    fit = _fit_with_model(time_axis, y)
    model = fit.model
    model.dimension = dimension
    model.tau_d0 = tau_d0
    model.convolve.do_convolution = False      # compare the ideal decay
    model.lifetimes._lifetimes[0].value = tau_d0   # donor lifetime, held
    model.lifetimes._lifetimes[0].fixed = True
    model.generic.background = 0.0
    model.generic.scatter = 0.0

    model.c_over_c0 = 0.3                      # deliberately away from the truth
    model._c_over_c0.fixed = False
    fit.fit_range = (0, len(time_axis) - 1)
    fit.run()

    assert model.c_over_c0 == pytest.approx(truth, rel=0.05), (
        f"d={dimension}: started at 0.3, expected {truth}, got {model.c_over_c0}"
    )


def test_a_three_dimensional_decay_is_not_fitted_by_the_one_dimensional_law(time_axis):
    """The dimensionalities are distinguishable -- that is the whole claim.

    If a 1-D fit reproduced 3-D data equally well, the decay shape would carry
    no information about geometry and the model would be reporting a density
    against an arbitrary choice.
    """
    tau_d0 = 4.0
    donor = np.exp(-time_axis / tau_d0)
    truth = quench_decay(donor, time_axis, tau_d0, 1.0, 3)

    def best_residual(dimension):
        fit = _fit_with_model(time_axis, truth)
        model = fit.model
        model.dimension = dimension
        model.tau_d0 = tau_d0
        model.convolve.do_convolution = False
        model.lifetimes._lifetimes[0].value = tau_d0
        model.lifetimes._lifetimes[0].fixed = True
        model.generic.background = 0.0
        model.generic.scatter = 0.0
        model.c_over_c0 = 1.0
        model._c_over_c0.fixed = False
        fit.fit_range = (0, len(time_axis) - 1)
        fit.run()
        model.update_model()
        y = np.asarray(model.y, dtype=float)
        y = y / max(y.max(), 1e-30) * truth.max()
        return float(np.sum((y - truth) ** 2))

    right = best_residual(3)
    wrong = best_residual(1)
    assert wrong > 10 * right, (
        f"the 1-D law fitted 3-D data too well: {wrong:.3e} vs {right:.3e}"
    )
