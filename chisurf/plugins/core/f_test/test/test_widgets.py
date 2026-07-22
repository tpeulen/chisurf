"""Headless tests for the AutoForm F-test / χ²-max calculator."""

from __future__ import annotations

import math

from scipy.stats import f as fdist

from chisurf.core.math.statistics import chi2_max


def test_model_recompute_matches_reference_formulas():
    """The model's recompute methods reproduce the legacy F-distribution formulas."""
    from chisurf.plugins.core.f_test.gui.tool import _FTestModel

    m = _FTestModel()
    m.chi2_1, m.n1, m.chi2_2, m.n2 = 1.0, 100, 1.5, 5

    m.recompute_conf()
    assert math.isclose(m.conf_level, float(fdist.cdf(1.5, 100, 5)))

    m.conf_level = 0.95
    m.recompute_chi2_2()
    assert math.isclose(m.chi2_2, 1.0 * 5 / 100 * float(fdist.isf(0.05, 100, 5)))

    m.chi2_min, m.npars, m.dof, m.conf_level_2 = 1.0, 3, 20, 0.95
    m.recompute_chi2_max()
    assert math.isclose(
        m.chi2_max,
        chi2_max(chi2_value=1.0, number_of_parameters=3, nu=20, conf_level=0.95),
    )
    # Regression against the documented reference value.
    assert math.isclose(m.chi2_max, 1.464758681821117, rel_tol=1e-9)


def test_view_spec_declares_all_fields():
    """ftest.view.json binds exactly the model's editable + output fields."""
    from chisurf.plugins.core.f_test.gui.tool import _FTestModel

    spec = _FTestModel().view_spec()

    def _attrs(sections):
        for s in sections:
            if getattr(s, "attr", None):
                yield s.attr
            yield from _attrs(getattr(s, "sections", []) or [])

    attrs = set(_attrs(spec.sections))
    assert attrs == {
        "chi2_1", "n1", "chi2_2", "n2", "conf_level",
        "chi2_min", "npars", "dof", "conf_level_2", "chi2_max",
    }


def test_tool_builds_and_edit_recomputes(qtbot):
    """The tool constructs headlessly and an edit triggers a coupled recompute."""
    from chisurf.plugins.core.f_test.gui.tool import FTestTool

    w = FTestTool()
    qtbot.addWidget(w)

    w._model.conf_level = 0.99
    w._on_field_edited("conf_level")
    expected = w._model.chi2_1 * w._model.n2 / w._model.n1 * float(
        fdist.isf(1.0 - 0.99, w._model.n1, w._model.n2)
    )
    assert math.isclose(w._model.chi2_2, expected)
