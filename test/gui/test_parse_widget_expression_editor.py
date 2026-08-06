"""The parse-model formula widget uses the validated ExpressionInput editor."""
import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class _MockData:
    def __init__(self, x):
        self.x = x
        self.y = np.zeros_like(x)
        self.ey = np.ones_like(x)


class _MockFit:
    def __init__(self, x):
        self.data = _MockData(x)
        self.xmin = 0
        self.xmax = len(x) - 1

    def update(self):
        pass


@pytest.fixture
def parse_widget(qapp):
    from chisurf.core.models.parse import ParseModel
    from chisurf.gui.widgets.models.parse.widget import ParseFormulaWidget

    model = ParseModel(fit=_MockFit(np.linspace(0.01, 50.0, 256)))
    return ParseFormulaWidget(model=model)


def test_expression_input_is_installed(parse_widget):
    assert getattr(parse_widget, "expr_input", None) is not None
    # The raw text box is hidden and kept only as a backing store.
    assert not parse_widget.plainTextEdit.isVisible()


def test_editor_seeded_from_catalog(parse_widget):
    assert parse_widget.expr_input.text() == parse_widget.plainTextEdit.toPlainText()
    assert parse_widget.expr_input.text() != ""


def test_edit_syncs_backing_store_and_validates(parse_widget):
    parse_widget.expr_input.setText("a1*exp(-x/tau1) + a2*exp(-x/tau2)")
    # Backing store mirrors the editor so existing readers keep working.
    assert parse_widget.plainTextEdit.toPlainText() == "a1*exp(-x/tau1) + a2*exp(-x/tau2)"
    assert parse_widget.expr_input.is_valid()
    assert parse_widget.expr_input.discovered_parameters() == ["a1", "tau1", "a2", "tau2"]


def test_unsafe_formula_flagged(parse_widget):
    parse_widget.expr_input.setText("a1 * exp(-x/tau1).__class__")
    assert not parse_widget.expr_input.is_valid()
    assert parse_widget.expr_input._badge.text() == "✗"


def test_model_change_updates_editor(parse_widget):
    if parse_widget.comboBox.count() < 2:
        pytest.skip("catalogue has a single model")
    parse_widget.comboBox.setCurrentIndex(1)
    parse_widget.onModelChanged()
    assert parse_widget.expr_input.text() == parse_widget.plainTextEdit.toPlainText()


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
