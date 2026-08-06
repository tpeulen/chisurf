"""The correlation (FCS) path through the agent tools.

The decay tools have a lot of TCSPC-specific machinery; these tests pin that
the general tools still work for a model with no instrument response and no
component groups, and that the summaries stay meaningful for a reader that
returns a group rather than a curve.
"""

from __future__ import annotations

import pytest

from chisurf.core.agent import ToolError
from chisurf.core.agent.tools import data as data_tools
from chisurf.core.agent.tools import decay as decay_tools
from chisurf.core.agent.tools import fitting as fitting_tools

CURVE = "fcs/kristine/Kristine_with_error.cor"
MODEL = "FCS (general: diffusion + bunching/anticorr)"


@pytest.fixture()
def correlation_fit(context):
    """Load the sample correlation curve and create a fit for it."""
    data_tools.load_data(context, paths=[CURVE])
    fitting_tools.create_fit(context, model_name=MODEL, datasets=[0])
    return context


def test_a_correlation_file_is_recognised_and_loaded(context):
    result = data_tools.load_data(context, paths=[CURVE])
    assert result["n_loaded"] == 1
    assert result["datasets"][0]["experiment"] == "FCS"


def test_a_grouped_dataset_keeps_a_meaningful_name(context):
    """The reader wraps the curve in a group whose own name is its class."""
    result = data_tools.load_data(context, paths=[CURVE])
    name = result["datasets"][0]["name"]
    assert name == "Kristine_with_error"
    assert name != "ExperimentDataCurveGroup"


def test_the_fit_reports_the_dataset_by_that_name(correlation_fit):
    assert fitting_tools.list_fits(correlation_fit)["fits"][0]["dataset"] == ("Kristine_with_error")


def test_the_correlation_fit_runs_and_improves(correlation_fit):
    result = fitting_tools.run_fit(correlation_fit, fit=0)["results"][0]
    assert result["ok"]
    assert result["chi2r"] < result["chi2r_before"]


def test_the_model_has_no_components_to_add(correlation_fit):
    """set_components is decay machinery; it must fail clearly here."""
    groups = decay_tools.component_groups(correlation_fit.fits[0].model)
    assert groups == {}
    with pytest.raises(ToolError, match="no components"):
        decay_tools.set_components(correlation_fit, n=2, fit=0)


def test_set_irf_refuses_a_model_that_does_not_convolve(correlation_fit):
    with pytest.raises(ToolError, match="does not convolve"):
        decay_tools.set_irf(correlation_fit, irf=0, fit=0)


def test_only_the_active_diffusion_mode_is_fitted(correlation_fit):
    """Three diffusion presets exist; the model computes with exactly one.

    While all three were exposed, the optimiser varied parameters the model
    never reads and ``parameters_all_dict`` could return an inactive ``N``
    still sitting at its default, as though it were the fitted value.
    """
    model = correlation_fit.fits[0].model
    names = [parameter.name for parameter in model.parameters]

    assert len(names) == len(set(names)), f"a parameter is exposed more than once: {names}"
    assert "w_r" in names, "the active (gauss) preset should be present"
    assert "w0" not in names, "the inactive MDF preset should not be"


def test_the_shape_parameters_arrive_free_and_can_be_fixed(correlation_fit):
    """Fixing the calibrated volume is the judgement the skill teaches."""
    before = {p["name"]: p for p in fitting_tools.get_fit(correlation_fit, fit=0)["parameters"]}
    assert before["w_r"]["fixed"] is False, "the volume shape is free in a fresh fit"

    fitting_tools.set_parameter(correlation_fit, parameter="w_r", fit=0, fixed=True)
    after = {p["name"]: p for p in fitting_tools.get_fit(correlation_fit, fit=0)["parameters"]}
    assert after["w_r"]["fixed"] is True


def test_fitting_moves_the_parameters_off_their_defaults(correlation_fit):
    """The reported values must be fitted ones, not untouched defaults."""
    model = correlation_fit.fits[0].model
    before = {name: model.parameters_all_dict[name].value for name in ("N", "D")}
    fitting_tools.run_fit(correlation_fit, fit=0)
    after = {name: model.parameters_all_dict[name].value for name in ("N", "D")}

    assert after["N"] != before["N"], "N was reported unchanged from its default"
    assert after["D"] != before["D"], "D was reported unchanged from its default"


def test_the_report_does_not_claim_an_irf(correlation_fit):
    report = decay_tools.fit_report(correlation_fit, fit=0)
    assert "irf_attached" not in report
    assert "warning" not in report
    assert {"N", "D"} <= {p["name"] for p in report["parameters"]}


def test_a_poor_correlation_fit_gets_generic_advice(correlation_fit):
    """With no IRF and no components, the advice must not suggest either."""
    fitting_tools.run_fit(correlation_fit, fit=0)
    verdict = decay_tools.assess_fit(correlation_fit.fits[0])
    if verdict["quality"] == "poor":
        assert "set_irf" not in verdict["next_step"]
        assert "set_components" not in verdict["next_step"]


def test_a_correlation_fit_can_be_plotted(correlation_fit, tmp_path):
    fitting_tools.run_fit(correlation_fit, fit=0)
    target = tmp_path / "fcs.png"
    assert decay_tools.plot_fit(correlation_fit, path=str(target), fit=0)["ok"]
    assert target.stat().st_size > 5000
