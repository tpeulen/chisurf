"""Headless tests for the AutoForm F-test / χ²-max calculator.

These pin the *properties* that define the F-test rather than the exact
expression the tool happens to evaluate. The previous version of this file
asserted equality with the shipped formulas and therefore locked in BUG-05:
``recompute_conf`` and ``recompute_chi2_2`` were supposed to be inverses but
were not, so asking for 95% confidence returned a χ² the tool itself scored at
0.09%.
"""

from __future__ import annotations

import math

import pytest
from scipy.stats import f as fdist

from chisurf.core.math.statistics import chi2_max, f_test_chi2r, f_test_confidence


@pytest.mark.parametrize("conf", [0.5, 0.68, 0.95, 0.99])
def test_confidence_and_chi2_threshold_are_inverses(conf):
    """Solving for χ²(2) at a confidence must score back as that confidence."""
    from chisurf.plugins.core.f_test.gui.tool import _FTestModel

    m = _FTestModel()
    m.chi2_1, m.n1, m.n2 = 1.0, 100, 98
    m.conf_level = conf
    m.recompute_chi2_2()
    m.recompute_conf()
    assert m.conf_level == pytest.approx(conf, abs=1e-9)


def test_equal_reduced_chi2_gives_no_preference():
    """Two models fitting equally well leave the choice at a coin flip.

    Exactly 0.5 when the degrees of freedom also match (the F distribution is
    then symmetric under inversion of its ratio); merely close to it otherwise.
    """
    from chisurf.plugins.core.f_test.gui.tool import _FTestModel

    m = _FTestModel()
    m.chi2_1, m.chi2_2, m.n1, m.n2 = 1.0, 1.0, 100, 100
    m.recompute_conf()
    assert m.conf_level == pytest.approx(0.5, abs=1e-9)

    m.n2 = 98
    m.recompute_conf()
    assert m.conf_level == pytest.approx(0.5, abs=1e-3)


def test_confidence_rises_as_the_complex_model_improves():
    """A larger χ² drop must raise, never lower, the confidence.

    This is the orientation half of BUG-05: the tool divided complex by
    simple, so it reported *falling* confidence exactly when the extra
    parameters were most justified.
    """
    from chisurf.plugins.core.f_test.gui.tool import _FTestModel

    m = _FTestModel()
    m.n1, m.n2, m.chi2_2 = 897, 895, 1.0

    confidences = []
    for chi2_1 in (1.00, 1.01, 1.05, 1.10):
        m.chi2_1 = chi2_1
        m.recompute_conf()
        confidences.append(m.conf_level)

    assert confidences == sorted(confidences)
    assert confidences[0] == pytest.approx(0.5, abs=1e-3)
    assert confidences[-1] > 0.9, "a 10% χ² drop over ~900 points is significant"


def test_model_delegates_to_the_shared_statistics_helpers():
    """The GUI model must not carry its own copy of the statistics."""
    from chisurf.plugins.core.f_test.gui.tool import _FTestModel

    m = _FTestModel()
    m.chi2_1, m.chi2_2, m.n1, m.n2 = 1.2, 1.0, 300, 296

    m.recompute_conf()
    assert m.conf_level == pytest.approx(f_test_confidence(1.2, 1.0, 300, 296))

    m.conf_level = 0.95
    m.recompute_chi2_2()
    assert m.chi2_2 == pytest.approx(f_test_chi2r(1.2, 0.95, 300, 296))


def test_chi2_max_panel_matches_the_support_plane_threshold():
    """The χ²-max panel is a different statistic and stays as it was.

    It is the support-plane threshold ``χ²min·(1 + p/ν·F(p, ν))`` -- note the
    ``F(p, ν)`` dof order, which is correct here and is *not* the ``F(ν₁, ν₂)``
    of the two-model panel above.
    """
    from chisurf.plugins.core.f_test.gui.tool import _FTestModel

    m = _FTestModel()
    m.chi2_min, m.npars, m.dof, m.conf_level_2 = 1.0, 3, 20, 0.95
    m.recompute_chi2_max()
    assert math.isclose(
        m.chi2_max,
        chi2_max(chi2_value=1.0, number_of_parameters=3, nu=20, conf_level=0.95),
    )
    # Regression against the documented reference value.
    assert math.isclose(m.chi2_max, 1.464758681821117, rel_tol=1e-9)
    assert math.isclose(
        m.chi2_max, 1.0 * (1.0 + 3 / 20 * float(fdist.isf(0.05, 3, 20))), rel_tol=1e-9
    )


def test_default_state_is_self_consistent():
    """The tool opens showing a confidence that matches its own χ² values."""
    from chisurf.plugins.core.f_test.gui.tool import _FTestModel

    m = _FTestModel()
    shown = m.conf_level
    m.recompute_conf()
    assert m.conf_level == pytest.approx(shown, abs=1e-12)


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
    m = w._model
    assert m.chi2_2 == pytest.approx(f_test_chi2r(m.chi2_1, 0.99, m.n1, m.n2))

    # …and the round trip holds through the widget layer too.
    w._on_field_edited("chi2_2")
    assert m.conf_level == pytest.approx(0.99, abs=1e-9)
