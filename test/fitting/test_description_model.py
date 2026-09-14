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


def test_the_view_reproduces_the_classic_lifetime_model_with_its_irf_preparation():
    """Lamp background, IRF window, shift, scatter, background: one curve, two owners.

    The classic LifetimeModel prepares the IRF in Python -- subtract the lamp
    background, clip, zero outside [irf_start, irf_stop), shift, normalise --
    and BFF now does the same in the graph, so the view needs no Python curve.
    """
    from chisurf.core.models.tcspc.lifetime import LifetimeModel

    x = _axis()
    irf = _irf() + 6.0                      # a lamp background under the IRF
    y = np.random.default_rng(4).poisson(2000.0 * np.exp(-np.maximum(x - 1.0, 0) / 2.0) + 10).astype(float)
    ey = np.sqrt(np.maximum(y, 1.0))

    classic_fit = fitting.Fit(model_class=LifetimeModel,
                              data=chisurf.core.data.DataCurve(x=x, y=y, ey=ey))
    classic_fit.xmin, classic_fit.xmax = 0, N
    classic = classic_fit.model
    classic.convolve._irf = chisurf.core.curve.Curve(x=x, y=irf.copy())
    classic.convolve.dt = DT
    classic.convolve.rep_rate = 1000.0 / PERIOD
    classic.convolve._lb.value = 6.5
    classic.convolve._irf_start.value = 0.4
    classic.convolve._irf_stop.value = 3.6
    classic.convolve._ts.value = 0.7
    classic.convolve._n0.fixed = False
    classic.convolve._n0.value = 9000.0
    classic.generic._sc.value = 0.02
    classic.generic._bg.value = 3.0
    classic.lifetimes._lifetimes[0].value = 3.2
    classic.lifetimes.append(amplitude=0.45, lifetime=0.6)
    classic.find_parameters()
    classic.update()
    reference = np.array(classic.y)

    fit, model = _view(y)
    fit.data = chisurf.core.data.DataCurve(x=x, y=y, ey=ey)
    model.set_dataset("response", chisurf.core.curve.Curve(x=x, y=irf.copy()))
    model.set_scalar("response_start", 0.4)
    model.set_scalar("response_stop", 3.6)
    problem = model.problem
    model.structure = "lifetime.components.2"
    amplitudes = [a.value for a in classic.lifetimes._amplitudes]
    values = {
        "lifetime.amplitude.0": amplitudes[0], "lifetime.tau.0": 3.2,
        "lifetime.amplitude.1": amplitudes[1], "lifetime.tau.1": 0.6,
        "instrument.response_background": 6.5, "instrument.timeshift": 0.7,
        "instrument.n0": 9000.0, "instrument.scatter": 0.02, "instrument.background": 3.0,
    }
    for name, value in values.items():
        port = problem.get_parameter(name)
        held = port.fixed
        port.fixed = False
        port.value = value
        port.fixed = held
    model.update()
    np.testing.assert_allclose(model.y, reference, rtol=1e-9, atol=1e-9)


def test_the_view_reproduces_the_classic_background_pattern():
    """A measured background decay, split from the fluorescence by measurement time."""
    from chisurf.core.models.tcspc.lifetime import LifetimeModel

    x = _axis()
    irf = _irf()
    pattern = 30.0 + 20.0 * np.exp(-0.5 * ((x - 2.5) / 0.6) ** 2)
    y = np.random.default_rng(8).poisson(2000.0 * np.exp(-np.maximum(x - 1.0, 0) / 2.0) + 40).astype(float)
    ey = np.sqrt(np.maximum(y, 1.0))

    classic_fit = fitting.Fit(model_class=LifetimeModel,
                              data=chisurf.core.data.DataCurve(x=x, y=y, ey=ey))
    classic_fit.xmin, classic_fit.xmax = 0, N
    classic = classic_fit.model
    classic.convolve._irf = chisurf.core.curve.Curve(x=x, y=irf.copy())
    classic.convolve.dt = DT
    classic.convolve.rep_rate = 1000.0 / PERIOD
    classic.convolve._ts.value = 0.8
    classic.convolve._n0.fixed = False
    classic.convolve._n0.value = 1.0
    classic.generic.background_curve = chisurf.core.curve.Curve(x=x, y=pattern.copy())
    classic.generic._tmeas_bg.value = 5.0
    classic.generic._tmeas_exp.value = 3.0
    classic.lifetimes._lifetimes[0].value = 2.1
    classic.find_parameters()
    classic.update()
    reference = np.array(classic.y)

    fit, model = _view(y)
    fit.data = chisurf.core.data.DataCurve(x=x, y=y, ey=ey)
    model.set_dataset("background_pattern", chisurf.core.curve.Curve(x=x, y=pattern.copy()))
    model.set_scalar("t_background", 5.0)
    model.set_scalar("t_decay", 3.0)
    problem = model.problem
    model.structure = "lifetime.components.1"
    for name, value in {"lifetime.tau.0": 2.1, "instrument.timeshift": 0.8, "instrument.n0": 1.0,
                        "instrument.background": 0.0}.items():
        port = problem.get_parameter(name)
        held = port.fixed
        port.fixed = False
        port.value = value
        port.fixed = held
    model.update()
    np.testing.assert_allclose(model.y, reference, rtol=1e-9, atol=1e-9)


def _classic_and_view(configure_classic, configure_view, n_lifetimes=2):
    """Build the classic LifetimeModel and the view over the same decay and IRF."""
    from chisurf.core.models.tcspc.lifetime import LifetimeModel

    x = _axis()
    irf = _irf()
    y = np.random.default_rng(11).poisson(2000.0 * np.exp(-np.maximum(x - 1.0, 0) / 2.0) + 20).astype(float)
    ey = np.sqrt(np.maximum(y, 1.0))
    classic_fit = fitting.Fit(model_class=LifetimeModel,
                              data=chisurf.core.data.DataCurve(x=x, y=y, ey=ey))
    classic_fit.xmin, classic_fit.xmax = 0, N
    classic = classic_fit.model
    classic.convolve._irf = chisurf.core.curve.Curve(x=x, y=irf.copy())
    classic.convolve.dt = DT
    classic.convolve.rep_rate = 1000.0 / PERIOD
    classic.convolve._n0.fixed = False
    classic.convolve._n0.value = 5000.0
    classic.generic._sc.value = 0.01
    classic.generic._bg.value = 2.0
    classic.lifetimes._lifetimes[0].value = 3.2
    if n_lifetimes == 2:
        classic.lifetimes.append(amplitude=0.45, lifetime=0.6)
    configure_classic(classic)
    classic.find_parameters()
    classic.update()

    fit, model = _view(y)
    fit.data = chisurf.core.data.DataCurve(x=x, y=y, ey=ey)
    configure_view(model)
    problem = model.problem
    model.structure = f"lifetime.components.{n_lifetimes}"
    amplitudes = [a.value for a in classic.lifetimes._amplitudes]
    values = {"lifetime.amplitude.0": amplitudes[0], "lifetime.tau.0": 3.2,
              "instrument.n0": 5000.0, "instrument.scatter": 0.01, "instrument.background": 2.0}
    if n_lifetimes == 2:
        values.update({"lifetime.amplitude.1": amplitudes[1], "lifetime.tau.1": 0.6})
    for name, value in values.items():
        port = problem.get_parameter(name)
        held = port.fixed
        port.fixed = False
        port.value = value
        port.fixed = held
    model.update()
    return np.array(classic.y), np.array(model.y)


@pytest.mark.parametrize("mode, convolve", [("exp", True), ("per", False), ("exp", False)])
def test_the_view_reproduces_the_classic_convolution_modes(mode, convolve):
    def classic(model):
        model.convolve.mode = mode
        model.convolve.do_convolution = convolve

    def view(model):
        model.set_scalar("periodic_excitation", 1.0 if mode == "per" else 0.0)
        model.set_scalar("convolve", 1.0 if convolve else 0.0)

    reference, got = _classic_and_view(classic, view)
    np.testing.assert_allclose(got, reference, rtol=1e-9, atol=1e-9)


def test_the_view_reproduces_the_classic_generated_irf():
    """No IRF loaded: both model it as a generalized-normal peak at the decay's rise."""
    def classic(model):
        model.convolve.unload_irf()           # nothing measured
        model.convolve._iw.value = 0.09
        model.convolve._ik.value = -0.25

    def view(model):
        model.unset_dataset("response")
        model.set_scalar("generated_response", 1.0)
        problem = model.problem
        for name, value in {"instrument.irf_width": 0.09, "instrument.irf_shape": -0.25}.items():
            port = problem.get_parameter(name)
            held = port.fixed
            port.fixed = False
            port.value = value
            port.fixed = held

    reference, got = _classic_and_view(classic, view)
    np.testing.assert_allclose(got, reference, rtol=1e-9, atol=1e-9)


def test_an_irf_is_missing_until_one_is_loaded_or_modelled():
    x = _axis()
    data = chisurf.core.data.DataCurve(x=x, y=np.ones(N), ey=np.ones(N))
    fit = fitting.Fit(model_class=for_family("tcspc_lifetime"), data=data)
    model = fit.model
    model.set_scalar("period", PERIOD)
    assert model.problem is None and "response" in model.missing
    model.set_scalar("generated_response", 1.0)
    assert model.problem is not None, model.missing


@pytest.mark.parametrize("polarization, code", [("vv", 1.0), ("vh", 2.0), ("vv/vh", 3.0)])
def test_the_polarized_view_reproduces_the_classic_anisotropy(polarization, code):
    """VV, VH and VV/VH decays with two rotations, g and the l1/l2 mixing."""
    from chisurf.core.models.tcspc.lifetime import LifetimeModel

    x = _axis()
    irf = _irf()
    y = np.random.default_rng(12).poisson(2000.0 * np.exp(-np.maximum(x - 1.0, 0) / 2.0) + 20).astype(float)
    ey = np.sqrt(np.maximum(y, 1.0))
    classic_fit = fitting.Fit(model_class=LifetimeModel,
                              data=chisurf.core.data.DataCurve(x=x, y=y, ey=ey))
    classic_fit.xmin, classic_fit.xmax = 0, N
    classic = classic_fit.model
    classic.convolve._irf = chisurf.core.curve.Curve(x=x, y=irf.copy())
    classic.convolve.dt = DT
    classic.convolve.rep_rate = 1000.0 / PERIOD
    classic.convolve._n0.fixed = False
    classic.convolve._n0.value = 5000.0
    classic.lifetimes._lifetimes[0].value = 3.2
    classic.lifetimes.append(amplitude=0.45, lifetime=0.6)
    anisotropy = classic.anisotropy
    anisotropy.polarization_type = polarization
    while len(anisotropy) < 2:
        anisotropy.add_rotation(b=0.2, rho=1.0)
    anisotropy._bs[0].value, anisotropy._rhos[0].value = 0.3, 0.8
    anisotropy._bs[1].value, anisotropy._rhos[1].value = 0.1, 4.0
    anisotropy._r0.value, anisotropy._g.value = 0.36, 1.2
    anisotropy._l1.value, anisotropy._l2.value = 0.03, 0.04
    classic.find_parameters()
    classic.update()
    reference = np.array(classic.y)
    amplitudes = [a.value for a in classic.lifetimes._amplitudes]
    rotations = [b.value for b in anisotropy._bs]

    data = chisurf.core.data.DataCurve(x=x, y=y, ey=ey)
    fit = fitting.Fit(model_class=for_family("tcspc_polarized"), data=data)
    fit.xmin, fit.xmax = 0, N
    model = fit.model
    model.set_dataset("response", chisurf.core.curve.Curve(x=x, y=irf.copy()))
    model.set_scalar("period", PERIOD)
    model.set_scalar("polarization", code)
    problem = model.problem
    assert problem is not None, model.missing
    model.structure = "lifetime.components.2.rotations.2"
    values = {"lifetime.amplitude.0": amplitudes[0], "lifetime.tau.0": 3.2,
              "lifetime.amplitude.1": amplitudes[1], "lifetime.tau.1": 0.6,
              "rotation.amplitude.0": rotations[0], "rotation.time.0": 0.8,
              "rotation.amplitude.1": rotations[1], "rotation.time.1": 4.0,
              "anisotropy.r0": 0.36, "anisotropy.g": 1.2, "anisotropy.l1": 0.03, "anisotropy.l2": 0.04,
              "instrument.n0": 5000.0, "instrument.scatter": 0.0, "instrument.background": 0.0}
    for name, value in values.items():
        port = problem.get_parameter(name)
        held = port.fixed
        port.fixed = False
        port.value = value
        port.fixed = held
    model.update()
    np.testing.assert_allclose(model.y, reference, rtol=1e-9, atol=1e-9)
