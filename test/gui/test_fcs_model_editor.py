"""Headless model-editor tests for the MDF and general composable FCS models (PRD-62).

Mirrors ``test_ics_model_editor.py``: each pure model builds through the real
AutoForm seam (table-view parameter groups + dynamic bunching/anticorrelation
groups render), and the model computes a finite correlation curve. A synthetic
log-spaced lag grid (ms) avoids any file I/O.
"""

from __future__ import annotations

import numpy as np
import pytest


@pytest.fixture(scope="module")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _make_fcs_data():
    """Return a DataCurve with a synthetic log-spaced FCS lag grid (ms)."""
    from chisurf.core.data import DataCurve

    x = np.logspace(-3, 3, 60)   # 1 us .. 1 s, in ms
    y = np.zeros_like(x)
    return DataCurve(name="synthetic-fcs", load_filename_on_init=False, y=y, x=x)


def _make_fcs_fit(model_class):
    import chisurf.core.fitting.fit as fit_mod

    return fit_mod.Fit(model_class=model_class, data=_make_fcs_data())


def _table_rows(editor):
    from chisurf.gui.autoform.sections.parameter_table import ParameterGroupTableWidget

    return sum(t.table_model.rowCount() for t in editor.findChildren(ParameterGroupTableWidget))


def test_mdf_model_editor_renders_and_computes(qapp):
    from qtpy import QtWidgets

    from chisurf.core.models import view_spec as vs
    from chisurf.core.models.fcs.mdf import MdfFCSModel
    from chisurf.gui.widgets.models.auto_model_widget import AutoModelWidget
    from chisurf.gui.widgets.models.model_editor import build_model_editor

    fit = _make_fcs_fit(MdfFCSModel)
    model = fit.model

    editor = build_model_editor(model)
    assert isinstance(editor, AutoModelWidget)
    QtWidgets.QVBoxLayout().addWidget(editor)
    assert _table_rows(editor) > 3, "MDF parameter tables rendered empty"

    spec = model.view_spec()
    for section in spec.flat_sections():
        if isinstance(section, (vs.ParameterGroupSection, vs.ParameterGroupTableSection)):
            group = getattr(model, section.target)
            assert list(group.parameters_all), f"group {section.target!r} has no parameters"

    model.update()
    y = np.asarray(model.y)
    assert y.size > 0 and np.all(np.isfinite(y))
    assert np.isfinite(model.outputs._Veff.value)
    assert np.isfinite(model.outputs._tauD.value)


def test_mdf_bunching_terms_change_the_curve(qapp):
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


def test_mdf_wem_parameter_is_not_labeled_as_foerster_radius(qapp):
    """Regression guard: MdfFCSModel's emission waist must not inherit FRET's R0 text."""
    from chisurf.core.models.fcs.mdf import MdfFCSModel

    fit = _make_fcs_fit(MdfFCSModel)
    model = fit.model
    assert "R0" not in [p.name for p in model.physical.parameters_all]
    wem = model.physical._wem
    assert "orster" not in (wem.description or "")


@pytest.mark.parametrize("diffusion_mode", ["mdf", "gauss", "two_focus"])
def test_general_model_editor_renders_and_computes(qapp, diffusion_mode):
    from qtpy import QtWidgets

    from chisurf.core.models.fcs.general import GeneralFCSModel
    from chisurf.gui.widgets.models.auto_model_widget import AutoModelWidget
    from chisurf.gui.widgets.models.model_editor import build_model_editor

    fit = _make_fcs_fit(GeneralFCSModel)
    model = fit.model
    model.diffusion_mode = diffusion_mode

    editor = build_model_editor(model)
    assert isinstance(editor, AutoModelWidget)
    QtWidgets.QVBoxLayout().addWidget(editor)
    assert _table_rows(editor) > 3, "general FCS model parameter tables rendered empty"

    model.update()
    y = np.asarray(model.y)
    assert y.size > 0 and np.all(np.isfinite(y))


def test_general_model_gauss_two_focus_suppresses_g0():
    """A known inter-focus separation (diam > 0) suppresses G(0) (Dertinger two-focus)."""
    from chisurf.core.models.fcs.general import GeneralFCSModel

    fit = _make_fcs_fit(GeneralFCSModel)
    model = fit.model
    model.diffusion_mode = "gauss"
    model.gauss._b.value = 0.0
    model.update()
    g0_single = float(np.asarray(model.y)[0])

    model.gauss._diam.value = 400.0   # nm
    model.update()
    g0_two_focus = float(np.asarray(model.y)[0])

    assert g0_two_focus < g0_single


def test_fcs_kinetics_model_editor_renders_and_computes(qapp):
    from qtpy import QtWidgets

    from chisurf.core.models.fcs.kinetics import FCSKineticsModel
    from chisurf.gui.widgets.models.auto_model_widget import AutoModelWidget
    from chisurf.gui.widgets.models.model_editor import build_model_editor

    fit = _make_fcs_fit(FCSKineticsModel)
    model = fit.model

    editor = build_model_editor(model)
    assert isinstance(editor, AutoModelWidget)
    QtWidgets.QVBoxLayout().addWidget(editor)
    assert _table_rows(editor) > 3, "kinetics FCS model parameter tables rendered empty"

    # Both diffusion presets plus the saturation group are present.
    assert hasattr(model, "saturation")
    # "Active" means the saturation physics is engaged, i.e. there is excitation.
    # A scheme always exists (two states minimum), so a scheme is not the test.
    assert model.saturation.active is False
    model.saturation._power.value = 1.0
    assert model.saturation.active is True
    model.saturation._power.value = 0.0

    model.update()
    y = np.asarray(model.y)
    assert y.size > 0 and np.all(np.isfinite(y))

    # Equation reflects the analytical gauss default
    assert "w<sub>r</sub>" in model.equation_html()

    from chisurf.gui.autoform.sections.state_scheme_section import StateSchemePlot
    from chisurf.gui.widgets.models.model_editor import model_plot_specs
    specs = model_plot_specs(model)
    plot_classes = [s[0] for s in specs]
    assert StateSchemePlot in plot_classes, "StateSchemePlot missing from Fit Window plot specs."


def test_general_model_saturation_panel_powers_the_numerical_path(qapp):
    """The Saturation (Kinetic) scheme lives on the *kinetics* model.

    Power > 0 switches to the numerical saturation path (equation shows
    SatNumInt, the saturated amplitude drops below the analytical one as the
    volume expands), Power = 0 restores the analytical shape exactly. The
    general model no longer carries the saturation group.
    """
    from chisurf.core.models.fcs.general import GeneralFCSModel
    from chisurf.core.models.fcs.kinetics import FCSKineticsModel
    from chisurf.gui.widgets.collapsible_box import CollapsibleBox
    from chisurf.gui.widgets.models.model_editor import build_model_editor

    fit = _make_fcs_fit(FCSKineticsModel)
    model = fit.model
    editor = build_model_editor(model)

    # The Kinetic saturation scheme panel exists but starts collapsed (power = 0).
    boxes = [
        b for b in editor.findChildren(CollapsibleBox) if "state scheme" in b.title().lower()
    ]
    assert len(boxes) == 1

    model.update()
    baseline = np.asarray(model.y).copy()

    model.saturation_mode = "full"
    model.saturation._power.value = 2.0   # 2 mW enables the numerical path
    model.update()
    saturated = np.asarray(model.y)
    assert np.all(np.isfinite(saturated))
    assert saturated[0] != baseline[0]
    assert "G<sub>num</sub>" in model.equation_html()

    model.saturation._power.value = 0.0
    model.update()
    np.testing.assert_allclose(model.y, baseline)

    # The general model stays purely analytical — no saturation group at all.
    general = _make_fcs_fit(GeneralFCSModel).model
    assert not hasattr(general, "saturation")
    assert "SatNumInt" not in general.equation_html()


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

    model.anticorr.add_anticorr(aca=0.8, act=500.0)   # 500 ns
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

    assert model.gauss._s.value == pytest.approx(4.0)   # w_z / w_r
    # No mean_count_rate metadata on the synthetic data -> brightness stays NaN.
    assert np.isnan(model.gauss._brightness.value)


def test_general_model_diffusion_panels_hide_on_mode_change(qapp):
    """Live hide: switching diffusion_mode + AutoForm.rebuild() only shows the active panel.

    Uses ``hidden_when`` (not just ``collapsed_when``) — the irrelevant
    diffusion panels are fully hidden (header included), not merely folded.
    """
    from chisurf.core.models.fcs.general import GeneralFCSModel
    from chisurf.gui.widgets.collapsible_box import CollapsibleBox
    from chisurf.gui.widgets.models.model_editor import build_model_editor

    fit = _make_fcs_fit(GeneralFCSModel)
    model = fit.model
    editor = build_model_editor(model)   # AutoForm itself (AutoModelWidget is an alias)
    assert model.diffusion_mode == "gauss"

    def _visible(title):
        # isVisible() reflects real on-screen visibility (false for everything in
        # a headless test with no shown top-level window); isHidden() reflects
        # whether setVisible(False) was called on this specific widget, which is
        # what hidden_when actually does — the right check without a real show().
        for box in editor.findChildren(CollapsibleBox):
            if box.title() == title:
                return not box.isHidden()
        return None

    assert _visible("3D Gaussian (single-focus)") is True
    assert _visible("MDF (Gauss-Lorentz)") is False
    assert _visible("3D Gaussian (two-focus)") is False

    model.diffusion_mode = "mdf"
    editor.rebuild()
    assert _visible("3D Gaussian (single-focus)") is False
    assert _visible("MDF (Gauss-Lorentz)") is True
    assert _visible("3D Gaussian (two-focus)") is False


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
    assert "d<sub>foci</sub>" in model.equation_html()   # non-zero preset diam

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


def test_general_model_editor_renders_a_live_equation_info_widget(qapp):
    from chisurf.core.models.fcs.general import GeneralFCSModel
    from chisurf.gui.autoform.sections.builtin import InfoWidget
    from chisurf.gui.widgets.models.model_editor import build_model_editor

    fit = _make_fcs_fit(GeneralFCSModel)
    model = fit.model
    editor = build_model_editor(model)

    def _equation_infos():
        return [i for i in editor.findChildren(InfoWidget) if i.toPlainText().startswith("G(τ)")]

    infos = _equation_infos()
    assert len(infos) == 1
    assert "MDF" not in infos[0].toPlainText()   # default mode is gauss

    model.diffusion_mode = "mdf"
    editor.rebuild()
    infos = _equation_infos()
    assert len(infos) == 1
    assert "MDF" in infos[0].toPlainText()


def test_clicking_add_bunching_button_refreshes_the_equation_panel(qapp):
    """Regression: dynamic_group add/remove must refresh_plots(), not just its own table.

    Previously ``on_add_table``/``on_del_table`` (and the grid-style
    ``on_add``/``on_del``) only updated their own ``PairedParameterTableWidget``
    after dispatching the fit update — every other ``AUTOFORM_REFRESH`` widget
    (e.g. the equation ``info`` panel) went stale until something else forced a
    full ``rebuild()``. Simulates the real GUI action (clicking "add") instead
    of mutating the model directly, so it only passes if the button's own
    click handler does the refresh.
    """
    from qtpy import QtWidgets

    from chisurf.core.models.fcs.general import GeneralFCSModel
    from chisurf.gui.autoform.sections.builtin import InfoWidget
    from chisurf.gui.widgets.collapsible_box import CollapsibleBox
    from chisurf.gui.widgets.models.model_editor import build_model_editor

    fit = _make_fcs_fit(GeneralFCSModel)
    model = fit.model
    editor = build_model_editor(model)

    info = editor.findChildren(InfoWidget)[0]
    before_text = info.toPlainText()

    bunching_box = next(
        b for b in editor.findChildren(CollapsibleBox) if b.title() == "Bunching terms"
    )
    add_btn = next(
        btn for btn in bunching_box.findChildren(QtWidgets.QPushButton) if btn.text() == "add"
    )
    add_btn.click()

    assert len(model.bunching) == 1
    after_text = info.toPlainText()
    assert after_text != before_text
    assert "b1" in after_text   # the new term's a_b1/tau_b1 subscript
