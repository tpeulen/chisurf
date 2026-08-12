"""The parse editors' equation field: validity badge, preview, parameter discovery.

These controls were the only reason ``parse/widget.py`` and ``parseWidget.ui``
existed after the parse models became data-described (PRD-38). They are a
``value`` section of ``kind: "expression"`` now, rendered by the shared
:class:`~chisurf.gui.widgets.expression_input.ExpressionInput` — so this drives
the *generated* editor rather than a hand-written widget, and the behaviour it
asserts is the one every parse model gets.
"""
from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture()
def equation_field(qapp):
    """Return the ``ExpressionInput`` of a generated TCSPC parse editor."""
    import chisurf.core.fitting.fit as fit_mod

    from chisurf.core.data import DataCurve
    from chisurf.core.models.tcspc.parse.tcspc_parse import ParseDecayModel
    from chisurf.gui.widgets.expression_input import ExpressionInput
    from chisurf.gui.widgets.models.model_editor import build_model_editor

    x = np.linspace(0.05, 25, 256)
    data = DataCurve(name="synthetic", load_filename_on_init=False,
                     x=x, y=np.exp(-x / 4.0) + 1.0)
    model = fit_mod.Fit(model_class=ParseDecayModel, data=data).model
    editor = build_model_editor(model)
    fields = editor.findChildren(ExpressionInput)
    assert len(fields) == 1, f"expected one equation field, found {len(fields)}"
    return fields[0], model


def test_equation_field_is_the_shared_expression_input(equation_field):
    """The parse editor's equation field is the validated shared widget."""
    field, _model = equation_field
    assert field.text(), "the equation field opened empty"
    assert field.is_valid()
    # The ✓/✗ badge and the names reference are what the old .ui was kept for.
    assert field._badge.text() == "✓"


def test_field_is_seeded_from_the_catalogue(equation_field):
    """It opens showing the equation the selected catalogue entry defines."""
    field, model = equation_field
    assert field.text() == str(model.func).strip()


def test_editing_discovers_the_free_parameters(equation_field):
    """Every name that is not x, a function or a constant is a parameter."""
    field, _model = equation_field
    field.setText("a1*exp(-x/tau1) + a2*exp(-x/tau2)")
    assert field.is_valid()
    assert field.discovered_parameters() == ["a1", "tau1", "a2", "tau2"]


def test_unsafe_formula_is_flagged(equation_field):
    """An expression reaching for attributes is rejected, not merely unparsed."""
    field, _model = equation_field
    field.setText("a1 * exp(-x/tau1).__class__")
    assert not field.is_valid()
    assert field._badge.text() == "✗"


def test_committing_an_equation_reaches_the_model(equation_field):
    """Pressing Return on a valid equation writes it through to the model."""
    field, model = equation_field
    field.setText("a1*exp(-x/tau1) + b")
    field._on_return()
    assert "b" in str(model.func)
    assert "b" in model.parameters_all_dict


def test_choosing_a_catalogue_entry_changes_the_equation(equation_field):
    """The `choice` over ``catalogue_names`` drives ``func`` through the model."""
    _field, model = equation_field
    names = list(model.catalogue_names)
    if len(names) < 2:
        pytest.skip("catalogue has fewer than two entries")
    before = str(model.func)
    model.model_name = next(n for n in names if n != model.model_name)
    assert str(model.func) != before
