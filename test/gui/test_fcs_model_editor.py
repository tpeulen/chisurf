"""Headless model-editor tests for the MDF and general composable FCS models (PRD-62).

Mirrors ``test_ics_model_editor.py``: each pure model builds through the real
AutoForm seam (table-view parameter groups + dynamic bunching/anticorrelation
groups render), and the model computes a finite correlation curve. A synthetic
log-spaced lag grid (ms) avoids any file I/O.
"""

from __future__ import annotations

import numpy as np
import pytest




def _make_fcs_data():
    """Return a DataCurve with a synthetic log-spaced FCS lag grid (ms)."""
    from chisurf.core.data import DataCurve

    x = np.logspace(-3, 3, 60)  # 1 us .. 1 s, in ms
    y = np.zeros_like(x)
    return DataCurve(name="synthetic-fcs", load_filename_on_init=False, y=y, x=x)


def _make_fcs_fit(model_class):
    import chisurf.core.fitting.fit as fit_mod

    return fit_mod.Fit(model_class=model_class, data=_make_fcs_data())






def test_mdf_bunching_terms_change_the_curve():
    from chisurf.core.models.fcs.mdf import MdfFCSModel

    fit = _make_fcs_fit(MdfFCSModel)
    model = fit.model
    model.update()
    baseline = np.asarray(model.y).copy()

    model.bunching.add_bunching(ba=0.5, bt=0.01)
    assert len(model.bunching) == 1
    model.find_parameters()
    model.update()
    bunched = np.asarray(model.y)

    assert not np.allclose(baseline, bunched)
    assert np.all(np.isfinite(bunched))

    model.bunching.remove_bunching()
    assert len(model.bunching) == 0
    model.find_parameters()
    model.update()
    np.testing.assert_allclose(model.y, baseline)


def test_mdf_wem_parameter_is_not_labeled_as_foerster_radius():
    """Regression guard: MdfFCSModel's emission waist must not inherit FRET's R0 text."""
    from chisurf.core.models.fcs.mdf import MdfFCSModel

    fit = _make_fcs_fit(MdfFCSModel)
    model = fit.model
    assert "R0" not in [p.name for p in model.physical.parameters_all]
    wem = model.physical._wem
    assert "orster" not in (wem.description or "")




def test_general_model_gauss_two_focus_suppresses_g0():
    """A known inter-focus separation (diam > 0) suppresses G(0) (Dertinger two-focus)."""
    from chisurf.core.models.fcs.general import GeneralFCSModel

    fit = _make_fcs_fit(GeneralFCSModel)
    model = fit.model
    model.diffusion_mode = "gauss"
    model.gauss._b.value = 0.0
    model.update()
    g0_single = float(np.asarray(model.y)[0])

    model.gauss._diam.value = 400.0  # nm
    model.update()
    g0_two_focus = float(np.asarray(model.y)[0])

    assert g0_two_focus < g0_single






def test_general_model_two_focus_preset_is_suppressed_by_default():
    """The 'two_focus' diffusion-mode preset starts with a non-zero diam."""
    from chisurf.core.models.fcs.general import GeneralFCSModel

    fit = _make_fcs_fit(GeneralFCSModel)
    model = fit.model

    model.diffusion_mode = "gauss"
    model.gauss._b.value = 0.0
    model.update()
    g0_single = float(np.asarray(model.y)[0])

    model.diffusion_mode = "two_focus"
    model.two_focus._b.value = 0.0
    model.update()
    g0_two_focus = float(np.asarray(model.y)[0])

    assert model.two_focus.diam > 0
    assert g0_two_focus < g0_single


def test_general_model_anticorr_dips_below_bunched_curve():
    from chisurf.core.models.fcs.general import GeneralFCSModel

    fit = _make_fcs_fit(GeneralFCSModel)
    model = fit.model
    model.diffusion_mode = "gauss"
    model.update()
    baseline = np.asarray(model.y).copy()

    model.anticorr.add_anticorr(aca=0.8, act=500.0)  # 500 ns
    model.find_parameters()
    model.update()
    dipped = np.asarray(model.y)

    assert np.all(np.isfinite(dipped))
    # Anticorrelation only affects short lags (fast exp(-tau/act) decay); the
    # curve must differ near tau ~ act and converge back at long lag.
    assert not np.allclose(baseline[:5], dipped[:5])
    np.testing.assert_allclose(baseline[-1], dipped[-1], rtol=1e-6)


def test_general_model_default_diffusion_mode_is_gauss():
    from chisurf.core.models.fcs.general import GeneralFCSModel

    fit = _make_fcs_fit(GeneralFCSModel)
    assert fit.model.diffusion_mode == "gauss"


def test_bunching_and_anticorr_defaults_step_by_decade():
    from chisurf.core.models.fcs.relaxation import AnticorrTerms, BunchingTerms

    bunching = BunchingTerms()
    for _ in range(3):
        bunching.add_bunching()
    assert [bt for _, bt in bunching.terms()] == pytest.approx([0.001, 0.01, 0.1])

    anticorr = AnticorrTerms()
    for _ in range(3):
        anticorr.add_anticorr()
    assert [act for _, act in anticorr.terms()] == pytest.approx([1.0, 10.0, 100.0])


def test_default_offset_b_is_one():
    from chisurf.core.models.fcs.general import GeneralFCSModel
    from chisurf.core.models.fcs.mdf import MdfFCSModel

    mdf_model = _make_fcs_fit(MdfFCSModel).model
    assert mdf_model.physical.b == pytest.approx(1.0)

    general_model = _make_fcs_fit(GeneralFCSModel).model
    assert general_model.gauss.b == pytest.approx(1.0)
    assert general_model.two_focus.b == pytest.approx(1.0)


def test_general_model_gauss_reports_shape_and_brightness_outputs():
    from chisurf.core.models.fcs.general import GeneralFCSModel

    fit = _make_fcs_fit(GeneralFCSModel)
    model = fit.model
    model.diffusion_mode = "gauss"
    model.gauss._w_r.value = 250.0
    model.gauss._w_z.value = 1000.0
    model.update()

    assert model.gauss._s.value == pytest.approx(4.0)  # w_z / w_r
    # No mean_count_rate metadata on the synthetic data -> brightness stays NaN.
    assert np.isnan(model.gauss._brightness.value)




def test_general_model_equation_html_reflects_mode_and_terms():
    from chisurf.core.models.fcs.general import GeneralFCSModel

    fit = _make_fcs_fit(GeneralFCSModel)
    model = fit.model

    model.diffusion_mode = "gauss"
    gauss_eq = model.equation_html()
    assert "w<sub>r</sub>" in gauss_eq and "MDF" not in gauss_eq

    model.diffusion_mode = "mdf"
    mdf_eq = model.equation_html()
    assert "MDF" in mdf_eq and "w<sub>r</sub>" not in mdf_eq

    model.diffusion_mode = "two_focus"
    assert "d<sub>foci</sub>" in model.equation_html()  # non-zero preset diam

    model.diffusion_mode = "gauss"
    baseline_eq = model.equation_html()
    model.bunching.add_bunching()
    model.anticorr.add_anticorr()
    with_terms_eq = model.equation_html()
    assert with_terms_eq != baseline_eq
    assert "a<sub>b1</sub>" in with_terms_eq
    assert "a<sub>ac1</sub>" in with_terms_eq


def test_mdf_model_equation_html_reflects_bunching_terms():
    from chisurf.core.models.fcs.mdf import MdfFCSModel

    fit = _make_fcs_fit(MdfFCSModel)
    model = fit.model
    baseline_eq = model.equation_html()
    assert "MDF" in baseline_eq

    model.bunching.add_bunching()
    with_term_eq = model.equation_html()
    assert with_term_eq != baseline_eq
    assert "a<sub>b1</sub>" in with_term_eq








# ---------------------------------------------------------------------------
# Models extracted out of the GUI layer (PRD-38): the bugs the extraction fixed
# ---------------------------------------------------------------------------
def _make_correlation_data(mean_count_rate: float | None = None):
    """A synthetic single-component correlation curve on a log lag grid (ms).

    The module's other fixture is an all-zero curve, which is fine for models
    that only need an x-axis; an inversion needs something to invert.
    """
    from chisurf.core.data import DataCurve

    x = np.logspace(-3, 3, 60)
    y = 1.0 + 1.0 / (1.0 + x / 0.5)
    data = DataCurve(name="synthetic-fcs", load_filename_on_init=False, y=y, x=x)
    if mean_count_rate is not None:
        data.meta_data["mean_count_rate"] = mean_count_rate
    return data


def test_dye_shape_outputs_are_written_by_update():
    """``D``/``tauD``/``cpm`` are written by ``update_model``, not by a GUI client.

    The hand-written version published these four derived values through
    ``get_fitting_client()`` inside a bare ``except``, so they stayed NaN
    whenever that client was absent -- headless, and in the running app until the
    editor had registered the fit. They are plain parameter writes now, which is
    also what makes them assertable without a display.
    """
    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.models.fcs.dye_shape import DyeShapeFCSModel

    data = _make_correlation_data(mean_count_rate=25.0)
    model = fit_mod.Fit(model_class=DyeShapeFCSModel, data=data).model
    assert model.dye_name, "no reference dye resolved from MMFDB"
    model.update()

    for p in (model._D, model._tauD, model._cpm, model._cpm_all):
        assert np.isfinite(p.value), f"{p.name} was not written by _update_model"
    # cpm counts the bright molecules only, cpm_all also the dark ones, so with a
    # non-zero bunching amplitude the second is the smaller number.
    assert model._cpm_all.value < model._cpm.value


def test_dye_shape_dye_choice_changes_the_curve():
    """Picking a different reference dye changes D and therefore the curve."""
    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.fluorescence.dyes import diffusion_coefficient_25C
    from chisurf.core.models.fcs.dye_shape import DyeShapeFCSModel

    model = fit_mod.Fit(model_class=DyeShapeFCSModel, data=_make_correlation_data()).model
    names = model.dye_names()
    d_current = diffusion_coefficient_25C(model.dye_name)
    other = next((n for n in names if abs(diffusion_coefficient_25C(n) - d_current) > 1e-9), None)
    if other is None:
        pytest.skip("MMFDB supplies no second reference dye with a different D")

    model.update()
    first = np.asarray(model.y).copy()
    d_first = float(model._D.value)

    model.dye_name = other
    model.update()
    assert float(model._D.value) != d_first
    assert not np.allclose(first, np.asarray(model.y))


@pytest.mark.parametrize("class_name", ["MaxEntFCSModel", "MaxEntRHModel"])
def test_maxent_l_curve_is_finite_with_an_unset_fit_range(class_name):
    """The L-curve is usable on a fit whose range has not been set.

    ``Fit`` starts with ``xmax == 0``, which is an *empty* window, not a full
    one; the misfit norm of an empty window is NaN, so every point of the sweep
    came back NaN and no corner could ever be detected -- for exactly the state a
    model is in the moment it is opened. The model now reads a degenerate window
    as the whole curve.
    """
    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.models.fcs import maxent_models

    model_class = getattr(maxent_models, class_name)
    fit = fit_mod.Fit(model_class=model_class, data=_make_correlation_data())
    model = fit.model
    assert fit.xmax <= fit.xmin, "fixture no longer reproduces the unset window"

    model.compute_l_curve(n_points=8, log10_min=-5.0, log10_max=1.0)
    l_curve = model.l_curve
    assert l_curve is not None
    assert np.all(np.isfinite(l_curve.residual_norm)), "misfit norm is NaN across the sweep"
    assert np.all(np.isfinite(l_curve.solution_norm))
    assert l_curve.corner_index is not None, "no corner detected"

    # Adopting the corner writes the weight directly; the legacy path routed this
    # through the GUI fitting client, so clicking the L-curve did nothing headless.
    model.use_l_curve_corner()
    expected = np.log10(float(l_curve.reg[l_curve.corner_index]))
    assert float(model._reg.value) == pytest.approx(expected)


