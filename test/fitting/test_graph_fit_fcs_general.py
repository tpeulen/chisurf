"""The composable FCS model fits through the graph (PRD-105, family verdicts).

`GeneralFCSModel`'s curve genuinely *is* an equation — `equation_html` has
always written it — so the graph route regenerates that equation in the
engine's spelling. The structural inputs (diffusion mode, species count,
bunching/anticorrelation term count, the dataset's count-rate constant) all
change the string, and the graph cache key carries the string, so no stale
graph can serve a reconfigured model. The `"mdf"` mode is a numerical
kernel, not a formula: it refuses, and the director path remains its
definition.

Pinned here:

* node curve == `update_model` at 1e-12 for every closed-form mode, with
  bunching + anticorrelation terms armed and with the count-rate background
  factor active;
* the fit recovers a synthetic curve's parameters with zero Python
  evaluations inside the minimisation;
* the refusals: `"mdf"` mode, and a free `bg` on a dataset with no
  count-rate metadata (the parameter would be unclaimable).
"""
import numpy as np
import pytest

import chisurf.core.data
import chisurf.core.fitting.fit as F
import chisurf.core.fitting.minimizer as M
from chisurf.core.models.fcs.general import GeneralFCSModel

pytestmark = pytest.mark.skipif(
    not M.have_minimizer(), reason="IMP.bff carries no Minimizer")


def _tau_ms(n=256):
    return np.logspace(-4.0, 2.5, n)


def make_fit(y=None, meta=None, n=256):
    tau = _tau_ms(n)
    if y is None:
        y = np.ones_like(tau)
    data = chisurf.core.data.DataCurve(
        x=tau, y=y, ey=np.full(tau.size, 1e-3))
    if meta:
        data.meta_data.update(meta)
    fit = F.Fit(model_class=GeneralFCSModel, data=data)
    fit.xmin, fit.xmax = 0, tau.size
    fit.model.find_parameters()
    return fit


def _arm_everything(model):
    """Drive every optional factor off its neutral default."""
    model.bunching.add_bunching(ba=0.2, bt=0.005)
    model.bunching.add_bunching(ba=0.1, bt=0.08)
    model.anticorr.add_anticorr(aca=0.4, act=3.0)


def _node_curve(fit):
    built = M.graph_objective(fit, fit.model)
    assert built is not None
    m, _ = built
    _, _, keepalive = m._graph
    node = keepalive[0]
    node.update()
    return np.asarray(node.get_output_port("chi2_model").value, dtype=float)


@pytest.mark.parametrize("mode", ["gauss", "two_focus", "species"])
def test_the_node_curve_is_the_python_curve(mode):
    fit = make_fit(meta={"mean_count_rate_total": 35.2})
    model = fit.model
    model.diffusion_mode = mode
    _arm_everything(model)
    group = {"two_focus": model.two_focus,
             "species": model.species}.get(mode, model.gauss)
    group._diam.value = 400.0     # two-focus factor armed in every mode
    group._bg.value = 4.0         # count-rate background factor armed
    if mode == "species":
        model.species._x_1.value = 0.7
        model.species._D_1.value = 500.0
        model.species._x_2.value = 0.3
        model.species._D_2.value = 30.0
    model.find_parameters()
    model.update()
    np.testing.assert_allclose(
        _node_curve(fit), np.asarray(model.y, dtype=float),
        rtol=1e-12, atol=1e-14)


def test_neutral_defaults_are_exactly_neutral():
    """No terms, diam = 0, bg = 0, no count-rate meta: the plain 3D-Gauss."""
    fit = make_fit()
    fit.model.update()
    np.testing.assert_allclose(
        _node_curve(fit), np.asarray(fit.model.y, dtype=float),
        rtol=1e-12, atol=1e-14)


def test_the_fit_recovers_the_truth_with_zero_python_evaluations():
    truth = dict(N=2.5, D=150.0, ba=0.25, bt=0.02)
    fit = make_fit()
    model = fit.model
    model.bunching.add_bunching(ba=truth["ba"], bt=truth["bt"])
    model.gauss._N.value = truth["N"]
    model.gauss._D.value = truth["D"]
    model.find_parameters()
    model.update()
    rng = np.random.default_rng(3)
    fit.data.y = np.asarray(model.y) + rng.normal(0.0, 1e-3, model.y.size)

    model.gauss._N.value = 1.5
    model.gauss._D.value = 400.0
    model.bunching._ba[0].value = 0.1
    model.bunching._bt[0].value = 0.01
    # The beam geometry is a calibration, and with it free the problem is
    # genuinely degenerate (only D/w^2 is constrained): fixed, as measured.
    model.gauss._w_r.fixed = True
    model.gauss._w_z.fixed = True
    model.find_parameters()

    calls = {"n": 0}
    original = type(model)._update_model

    def counting(self, **kwargs):
        calls["n"] += 1
        return original(self, **kwargs)

    type(model)._update_model = counting
    try:
        assert M.graph_objective(fit, model) is not None
        fit.run()
        during = calls["n"]
    finally:
        type(model)._update_model = original

    assert model.gauss.N == pytest.approx(truth["N"], rel=2e-2)
    assert model.gauss.D == pytest.approx(truth["D"], rel=2e-2)
    assert float(model.bunching._bt[0].value) == pytest.approx(
        truth["bt"], rel=5e-2)
    assert during <= 2      # the post-run display refresh only


def test_mdf_mode_refuses_the_graph_and_still_fits():
    """The MDF shape is a numerical kernel (bff FcsMdf), not a formula."""
    fit = make_fit()
    fit.model.diffusion_mode = "mdf"
    fit.model.find_parameters()
    assert fit.model.func is None
    assert M.graph_objective(fit, fit.model) is None
    # The director path remains the definition; on this deliberately
    # meaningless fixture it must complete, not converge.
    fit.run()


def test_a_free_bg_without_count_rate_metadata_refuses():
    """Without the count-rate constant the equation has no ``bg`` variable,
    so a *free* ``bg`` would be unclaimable — the builder must refuse
    rather than silently freeze it."""
    fit = make_fit()
    fit.model.gauss._bg.fixed = False
    fit.model.find_parameters()
    assert M.graph_objective(fit, fit.model) is None


def test_reconfiguration_regenerates_the_equation():
    fit = make_fit()
    model = fit.model
    plain = model.func
    model.bunching.add_bunching()
    assert model.func != plain
    key_a = M._graph_cache_key(fit, model)
    model.diffusion_mode = "species"
    assert M._graph_cache_key(fit, model) != key_a
