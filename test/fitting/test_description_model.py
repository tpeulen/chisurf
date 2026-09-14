"""ChiSurf's view on a model BFF owns.

Every property here is about the absence of a copy: the parameters are the
model's ports, the curve is the model's output, the fit and the search write
the model in place, and changing the data rebuilds nothing the view holds.
"""

from __future__ import annotations

import numpy as np
import pytest

bff = pytest.importorskip("IMP.bff")

import chisurf.core.curve
import chisurf.core.data
import chisurf.core.fitting.fit as fitting
from chisurf.core.fitting.mcts.dispatcher import prepare_model_search
from chisurf.core.models.description import DescriptionModel, for_family

N = 128
DT = 0.048
PERIOD = 12.5
TRUTH = {
    "lifetime.tau.0": 3.2,
    "lifetime.amplitude.1": 0.45,
    "lifetime.tau.1": 0.6,
    "instrument.background": 2.0,
    "instrument.n0": 60000.0,
}


def _axis():
    return np.arange(N) * DT


def _irf():
    return 1000.0 * np.exp(-0.5 * ((_axis() - 1.0) / 0.08) ** 2)


def _view(y=None):
    x = _axis()
    y = np.full(N, 10.0) if y is None else y
    data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.sqrt(np.maximum(y, 1.0)))
    fit = fitting.Fit(model_class=for_family("tcspc_lifetime"), data=data)
    fit.xmin, fit.xmax = 0, N
    model = fit.model
    model.set_dataset("response", chisurf.core.curve.Curve(x=x, y=_irf()))
    model.set_scalar("period", PERIOD)
    return fit, model


def _simulated():
    """A decay the model itself generates at TRUTH, so recovery means something."""
    _, model = _view()
    problem = model.problem
    model.structure = "lifetime.components.2"
    for canonical, value in TRUTH.items():
        port = problem.get_parameter(canonical)
        port.fixed = False
        port.value = value
    active = problem.get_active_structure()
    return np.array(problem.get_structure_output(
        active, problem.get_structure_curve_node(active, "decay")))


def test_the_family_is_data_and_the_class_is_generic():
    cls = for_family("tcspc_lifetime")
    assert issubclass(cls, DescriptionModel)
    assert for_family("tcspc_lifetime") is cls
    assert cls.family == "tcspc_lifetime"


def test_an_incomplete_model_says_what_it_is_missing():
    x = _axis()
    data = chisurf.core.data.DataCurve(x=x, y=np.ones(N), ey=np.ones(N))
    fit = fitting.Fit(model_class=for_family("tcspc_lifetime"), data=data)
    assert fit.model.problem is None
    assert fit.model.missing == ["response"]


def test_parameters_are_the_models_own_ports():
    _, model = _view()
    problem = model.problem
    assert problem is not None, model.missing
    for parameter in model.parameters_all:
        assert parameter._port.uid == problem.get_parameter(parameter.canonical_id).uid


def test_the_curve_is_the_models_output():
    fit, model = _view()
    model.update()
    problem = model.problem
    active = problem.get_active_structure()
    expected = problem.get_structure_output(active, problem.get_structure_curve_node(active, "decay"))
    assert np.asarray(model.y) == pytest.approx(np.asarray(expected))


def test_picking_a_topology_shows_its_rows_and_frees_them():
    _, model = _view()
    model.structure = "lifetime.components.2"
    lifetimes = model.lifetimes.visible_parameters()
    assert [p.canonical_id for p in lifetimes] == [
        "lifetime.amplitude.0", "lifetime.tau.0", "lifetime.amplitude.1", "lifetime.tau.1"]
    free = {p.canonical_id for p in model.parameters}
    assert {"lifetime.tau.0", "lifetime.tau.1", "lifetime.amplitude.1"} <= free


def test_a_fit_writes_the_model_in_place_and_recovers_the_truth():
    y = _simulated()
    fit, model = _view(y)
    model.structure = "lifetime.components.2"
    starts = {"lifetime.tau.0": 2.5, "lifetime.amplitude.1": 0.6, "lifetime.tau.1": 0.8}
    for parameter in model.parameters_all:
        if parameter.canonical_id in starts:
            parameter.value = starts[parameter.canonical_id]
    fit.run()
    values = {p.canonical_id: p.value for p in model.parameters_all}
    for canonical in ("lifetime.tau.0", "lifetime.tau.1", "lifetime.amplitude.1"):
        assert values[canonical] == pytest.approx(TRUTH[canonical], rel=1e-3), canonical
        assert values[canonical] == model.problem.get_parameter(canonical).value


def test_fixing_holds_for_every_topology_and_freeing_releases_the_instrument():
    _, model = _view()
    by_id = {p.canonical_id: p for p in model.parameters_all}
    by_id["instrument.n0"].fixed = True
    model.structure = "lifetime.components.3"
    assert by_id["instrument.n0"].fixed
    assert by_id["instrument.timeshift"].fixed
    by_id["instrument.timeshift"].fixed = False
    assert not by_id["instrument.timeshift"].fixed
    assert model.problem.get_parameter_released("instrument.timeshift")


def test_new_data_keeps_every_port_the_view_holds():
    fit, model = _view()
    ports = {p.canonical_id: p._port.uid for p in model.parameters_all}
    model.set_dataset("response", chisurf.core.curve.Curve(x=_axis(), y=np.roll(_irf(), 2)))
    fit.data = chisurf.core.data.DataCurve(x=_axis(), y=np.full(N, 50.0), ey=np.full(N, 7.0))
    assert model.problem is not None
    assert {p.canonical_id: p._port.uid for p in model.parameters_all} == ports
    for canonical, uid in ports.items():
        assert model.problem.get_parameter(canonical).uid == uid


def test_the_search_leaves_the_model_at_its_winner_without_a_copy():
    y = _simulated()
    fit, model = _view(y)
    prepared = prepare_model_search(fit)
    assert prepared.supported, prepared.reasons
    assert prepared.problem.get_parameter("lifetime.tau.0").uid == model.problem.get_parameter("lifetime.tau.0").uid
    config = bff.ModelSearchConfig()
    config.set_number_of_simulations(16)
    config.set_dirichlet_fraction(0.0)
    search = bff.ModelSearch(prepared.problem)
    search.set_config(config)
    best = search.run().get_best_state()
    prepared.binding.apply_state(prepared.problem, best)
    assert model.structure == best.get_structure_key() == "lifetime.components.2"
    taus = sorted(p.value for p in model.lifetimes.visible_parameters() if p.canonical_id.startswith("lifetime.tau"))
    assert taus == pytest.approx([0.6, 3.2], rel=1e-2)


def test_a_refused_search_puts_the_model_back():
    fit, model = _view(_simulated())
    before = {p.canonical_id: p.value for p in model.parameters_all}
    structure = model.structure
    prepared = prepare_model_search(fit)
    prepared.problem.get_initial_state()
    prepared.binding.restore(prepared.problem)
    assert {p.canonical_id: p.value for p in model.parameters_all} == before
    assert model.structure == structure


def test_state_round_trips_without_rebuilding_twice():
    fit, model = _view()
    model.structure = "lifetime.components.2"
    by_id = {p.canonical_id: p for p in model.parameters_all}
    by_id["lifetime.tau.1"].value = 1.7
    by_id["instrument.n0"].fixed = True
    state = model.get_state()

    other_fit, other = _view()
    other.set_state(state)
    assert other.structure == "lifetime.components.2"
    other_by_id = {p.canonical_id: p for p in other.parameters_all}
    assert other_by_id["lifetime.tau.1"].value == pytest.approx(1.7)
    assert other_by_id["instrument.n0"].fixed


def test_the_editor_is_derived_from_the_description():
    _, model = _view()
    model.problem
    spec = model.view_spec()
    targets = spec.section_targets()
    assert "lifetimes" in targets and "instrument" in targets
    labels = [getattr(s, "label", None) for s in spec.flat_sections()]
    assert "IRF" in labels and "Period [ns]" in labels
