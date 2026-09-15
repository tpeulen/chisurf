"""The acceptor-density FRET model, checked by recovering what it was given.

A donor quenched by acceptors at a density in 1, 2 or 3 dimensions
(``tcspc_fret_acceptor_density``). The round trip is the point: a stretched exponential and a
two-exponential decay are close over a limited window, so only fitting
simulated data with a known answer shows that the density is recovered -- and
that the dimensionality, which the model searches, is found.
"""
from __future__ import annotations

import numpy as np
import pytest

import chisurf.core.curve
import chisurf.core.data
import chisurf.core.fitting.fit as fitting
from chisurf.core.models.description import for_family

N = 512
DT = 0.05
PERIOD = 25.0
TAU_D0 = 4.0


def _axis():
    return np.arange(N) * DT


def _irf():
    return 1000.0 * np.exp(-0.5 * ((_axis() - 1.0) / 0.08) ** 2)


def _set(problem, canonical, value):
    port = problem.get_parameter(canonical)
    held = port.fixed
    port.fixed = False
    port.value = float(value)
    port.fixed = held


def _view(y, dimension):
    x = _axis()
    fit = fitting.Fit(model_class=for_family("tcspc_fret_acceptor_density"),
                      data=chisurf.core.data.DataCurve(x=x, y=y, ey=np.sqrt(np.maximum(y, 1.0))))
    fit.xmin, fit.xmax = 0, N
    model = fit.model
    model.set_dataset("response", chisurf.core.curve.Curve(x=x, y=_irf()))
    model.set_scalar("period", PERIOD)
    model.set_scalar("periodic_excitation", 0.0)
    assert model.problem is not None, model.missing
    model.structure = f"tcspc_fret_acceptor_density.dimensions.{dimension}"
    problem = model.problem
    for canonical, value in (("donor.amplitude.0", 1.0), ("donor.tau.0", TAU_D0), ("fret.tau0", TAU_D0),
                             ("instrument.n0", 50000.0), ("instrument.background", 1.0)):
        _set(problem, canonical, value)
    return fit, model


def _simulated(dimension, density):
    _, model = _view(np.full(N, 10.0), dimension)
    _set(model.problem, "acceptor.c_over_c0", density)
    model.update()
    return np.asarray(model.y, dtype=float)


def _parameters(model):
    return {p.canonical_id: p for p in model.parameters_all if not getattr(p, "is_output", False)}


@pytest.mark.parametrize("dimension, truth", [(3, 0.9), (2, 1.3), (1, 1.7)])
def test_the_density_is_recovered_from_a_simulated_decay(dimension, truth):
    y = _simulated(dimension, truth)
    fit, model = _view(y, dimension)
    parameters = _parameters(model)
    parameters["donor.tau.0"].fixed = True
    _set(model.problem, "acceptor.c_over_c0", 0.3)            # away from the truth
    model.find_parameters()
    fit.run()
    assert parameters["acceptor.c_over_c0"].value == pytest.approx(truth, rel=1e-3)


def test_zero_density_is_the_unquenched_donor():
    quenched = _simulated(2, 1.5)
    unquenched = _simulated(2, 0.0)
    assert np.all(quenched <= unquenched + 1e-9)
    assert quenched.sum() < unquenched.sum()


def test_the_search_finds_the_dimensionality_of_the_data():
    """The three laws are distinguishable -- that is the whole claim."""
    from chisurf.core.fitting.mcts.dispatcher import prepare_model_search
    from chisurf.core.fitting.mcts.execution import NativeSearchSettings, run_native_search

    y = _simulated(3, 1.0)
    fit, model = _view(y, 1)
    _parameters(model)["donor.tau.0"].fixed = True
    prepared = prepare_model_search(fit)
    assert prepared.supported, prepared.reasons
    result = run_native_search(prepared.problem, NativeSearchSettings(simulations=20, seed=3))
    assert result.get_best_state().get_structure_key() == "tcspc_fret_acceptor_density.dimensions.3"


def test_the_geometry_survives_a_save_and_reload():
    """A saved 1-D fit must not reopen as a 2-D fit carrying the 1-D density."""
    y = _simulated(1, 2.2)
    _, saved = _view(y, 1)
    _set(saved.problem, "acceptor.c_over_c0", 2.2)
    saved.update()
    _, restored = _view(y, 2)
    restored.set_state(saved.get_state())
    assert restored.structure == "tcspc_fret_acceptor_density.dimensions.1"
    np.testing.assert_allclose(np.asarray(restored.y), np.asarray(saved.y), rtol=1e-12)


@pytest.mark.parametrize("dimension", [1, 2, 3])
def test_the_view_reports_the_efficiency_and_the_absolute_density(dimension):
    from chisurf.core.fluorescence.fret.acceptor_density import characteristic_density, transfer_efficiency

    _, model = _view(np.full(N, 10.0), dimension)
    _set(model.problem, "acceptor.c_over_c0", 2.5)
    _set(model.problem, "fret.forster_radius", 52.0)
    model.update()
    outputs = {p.name: p.value for p in model.parameters_all if getattr(p, "is_output", False)}
    assert outputs["E"] == pytest.approx(transfer_efficiency(2.5, dimension), rel=1e-12)
    assert outputs["density [Å^-d]"] == pytest.approx(2.5 * characteristic_density(52.0, dimension), rel=1e-12)
