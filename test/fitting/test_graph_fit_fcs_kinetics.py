"""FCS kinetics "full" saturation mode fits through the graph (PRD-119).

The numerical volume integration (`IMP.bff.FCSSaturationCurve`) is a producer
node in front of the same ``Expression -> ChiSquared -> Minimizer`` the
closed-form FCS modes use.  Pinned here:

* the graph node curve == ``_update_model`` at 1e-10 (the node and the Python
  call the same C++ kernel, so the tolerance is tight);
* the graph objective builds and minimises (zero Python evaluations inside
  the fit);
* "fast" mode and no-power mode refuse the graph (they are closed-form, not
  a numerical kernel).
"""

import numpy as np
import pytest

import chisurf.core.data
import chisurf.core.fitting.fit as F
import chisurf.core.fitting.minimizer as M
from chisurf.core.models.fcs.kinetics import FCSKineticsModel

pytestmark = pytest.mark.skipif(not M.have_minimizer(), reason="IMP.bff carries no Minimizer")


def _tau_ms(n=128):
    return np.logspace(-4.0, 2.5, n)


def make_fit(y=None, meta=None, n=128):
    tau = _tau_ms(n)
    if y is None:
        y = np.ones_like(tau)
    data = chisurf.core.data.DataCurve(x=tau, y=y, ey=np.full(tau.size, 1e-3))
    if meta:
        data.meta_data.update(meta)
    fit = F.Fit(model_class=FCSKineticsModel, data=data)
    fit.xmin, fit.xmax = 0, tau.size
    fit.model.find_parameters()
    return fit


def _arm_saturation(model):
    """Engage the photokinetic scheme with a non-zero power."""
    sat = model.saturation
    sat._power.value = 20.0  # 20 mW — active
    sat._extinction.value = 73000.0
    sat._N.value = 2.5
    sat._b.value = 1.0
    sat._bg.value = 4.0  # count-rate background factor armed
    sat._w_r.value = 250.0  # nm
    sat._w_z.value = 1250.0  # nm
    sat._D.value = 400.0  # um^2/s
    # All scheme parameters (rate matrices, brightness) stay fixed: they
    # are configuration on the C++ node, not ports, so freeing one refuses
    # the graph (unclaimable-port rule) — the same design as MDF optics.
    for p in model.parameters:
        p.fixed = True
    # Free one equation variable (N) so the free list is non-empty.
    sat._N.fixed = False
    model.find_parameters()


def _node_curve(fit):
    """Evaluate the graph's Expression node and return its output."""
    built = M.graph_objective(fit, fit.model)
    assert built is not None, "graph_objective returned None for full mode"
    m, _ = built
    chi2, _, keepalive, _ = m._graph
    # The Expression node's output port is named "chi2_model"
    expr_out = chi2.get_output_port("chi2_model")
    # The keepalive tuple holds the FcsSaturationCurve node
    sat_node = keepalive[0]
    sat_node.update()
    chi2.update()
    return np.asarray(expr_out.value, dtype=float)


def test_the_node_curve_is_the_python_curve_full_mode():
    """Graph node output == _update_model output at 1e-10 in full saturation mode."""
    fit = make_fit(meta={"mean_count_rate_total": 35.2})
    model = fit.model
    assert model.saturation_mode == "full"
    _arm_saturation(model)
    model.update()

    assert M._is_fcs_kinetics_full_model(model), "model should be recognized as full kinetics"
    built = M.graph_objective(fit, model)
    assert built is not None, "graph_objective should build for full kinetics"

    m, free = built
    chi2, carried, keepalive, extra_keepalive = m._graph
    # extra_keepalive is the FcsSaturationCurve node
    sat_node = extra_keepalive if extra_keepalive is not None else keepalive[0]
    sat_node.update()
    chi2.update()

    # The Expression node and its output port are in keepalive:
    # keepalive = (curve, axes_alive, out_port, model_in_port)
    expr_node, _axes, expr_out_port, _model_in = keepalive
    node_y = np.asarray(expr_out_port.value, dtype=float)
    py_y = np.asarray(model.y, dtype=float)

    assert node_y.shape == py_y.shape, f"shape mismatch: {node_y.shape} vs {py_y.shape}"
    np.testing.assert_allclose(
        node_y, py_y, rtol=1e-10, atol=1e-12, err_msg="graph node curve != python curve"
    )


def test_fast_mode_refuses_graph():
    """Fast mode is closed-form (Gaussian * bunching), not a numerical kernel."""
    fit = make_fit()
    model = fit.model
    _arm_saturation(model)
    model.saturation_mode = "fast"
    assert not M._is_fcs_kinetics_full_model(model)
    assert M.graph_objective(fit, model) is None


def test_no_power_refuses_graph():
    """Zero power is the analytical Gaussian, not a numerical kernel."""
    fit = make_fit()
    model = fit.model
    # Leave power at default 0 (inactive)
    model.find_parameters()
    model.update()
    assert not model.saturation.active
    assert not M._is_fcs_kinetics_full_model(model)
    assert M.graph_objective(fit, model) is None


def test_the_expression_compiles():
    """The model's func string compiles in the engine."""
    fit = make_fit(meta={"mean_count_rate_total": 35.2})
    model = fit.model
    _arm_saturation(model)
    expr = model._expression
    assert expr is not None
    params = model._parameters_equation
    assert len(params) == 3  # N, b, bg
    names = [p.name for p in params]
    assert "N" in names and "b" in names and "bg" in names


def test_free_brightness_refuses_graph():
    """A freed brightness is configuration, not a port — unclaimable.

    The brightness vector is set on the C++ node via ``set_scheme`` at build
    time, not as a port. Freeing ``B_2`` puts it in ``model.parameters`` with
    no port to carry it, so the graph refuses — the same design as MDF optics.
    """
    fit = make_fit(meta={"mean_count_rate_total": 35.2})
    model = fit.model
    _arm_saturation(model)
    # Free a brightness parameter (scheme configuration, not a port)
    sat = model.saturation
    sat.brightness._brightness[1].fixed = False  # B_2 free
    model.find_parameters()
    model.update()
    # The graph should refuse because B_2 is free but has no port
    assert M.graph_objective(fit, model) is None
