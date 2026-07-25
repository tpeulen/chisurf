"""GUI tests for the general EquationTableEditor widget."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from chisurf.gui.widgets.equation_editor import EquationTableEditor


def _names():
    return {"Parameters": ["tau", "amplitude", "x0"], "Extra": ["baseline"]}


def test_round_trip_equations(qapp):
    ed = EquationTableEditor(names_provider=_names)
    eqs = [{"g": "amplitude * exp(-tau)"}, {"n": "g / baseline"}]
    ed.set_equations(eqs)
    assert ed.equations() == eqs


def test_text_is_yaml(qapp):
    import yaml

    ed = EquationTableEditor(names_provider=_names)
    ed.set_equations([{"g": "amplitude * 2"}])
    assert yaml.safe_load(ed.text()) == [{"g": "amplitude * 2"}]


def test_valid_and_invalid_rows_flagged(qapp):
    ed = EquationTableEditor(names_provider=_names)
    ed.set_equations([
        {"good": "amplitude * exp(-x0**2 / tau)"},
        {"unknown": "amplitude + nope"},
        {"unsafe": "amplitude.__class__"},
    ])
    assert ed._table.item(0, 2).text() == "✓"
    assert ed._table.item(1, 2).text() == "✗"
    assert "nope" in ed._table.item(1, 2).toolTip()
    assert ed._table.item(2, 2).text() == "✗"
    assert not ed.is_valid()


def test_output_forward_reference_is_valid(qapp):
    ed = EquationTableEditor(names_provider=_names)
    # 'n' references output 'g' declared before it -> valid.
    ed.set_equations([{"g": "amplitude"}, {"n": "g + tau"}])
    assert ed.is_valid()


def test_missing_output_name_is_invalid(qapp):
    ed = EquationTableEditor(names_provider=_names)
    ed._append_row("", "amplitude + tau")
    ed._validate_all()
    assert ed._table.item(0, 2).text() == "✗"


def test_apply_fires_callback_and_signal(qapp):
    ed = EquationTableEditor(names_provider=_names)
    ed.set_equations([{"g": "amplitude"}])
    fired = {"cb": 0, "sig": 0}
    ed.save_callback = lambda: fired.__setitem__("cb", fired["cb"] + 1)
    ed.applied.connect(lambda: fired.__setitem__("sig", fired["sig"] + 1))
    ed.apply()
    assert fired == {"cb": 1, "sig": 1}


def test_injected_validator_overrides_default(qapp):
    # A validator that rejects everything must win over the built-in engine.
    ed = EquationTableEditor(
        names_provider=_names,
        validator=lambda expr, known, outputs: (False, "always bad"),
    )
    ed.set_equations([{"g": "amplitude"}])
    assert ed._table.item(0, 2).text() == "✗"
    assert ed._table.item(0, 2).toolTip() == "always bad"


def test_quoted_names_config_disables_preview(qapp):
    ed = EquationTableEditor(names_provider=_names, quote_names=True)
    assert ed._show_preview is False


def test_setText_parses_yaml(qapp):
    ed = EquationTableEditor(names_provider=_names)
    ed.setText("- g: 'amplitude * 2'\n")
    assert ed.equations() == [{"g": "amplitude * 2"}]


def test_autoform_section_binds_model(qapp):
    from chisurf.gui.autoform.sections import get_section_factory

    class _Model:
        def __init__(self):
            self.equations = [{"g": "amplitude * 2"}]
            self.applied_count = 0

        def equation_names(self):
            return {"Parameters": ["amplitude", "tau"]}

        def recompute(self):
            self.applied_count += 1

    model = _Model()
    factory = get_section_factory("equation_editor")
    section = factory(
        model=model,
        target="",
        attr="equations",
        names="equation_names",
        call="recompute",
    )
    # Editor was seeded from the model.
    assert section.editor.equations() == [{"g": "amplitude * 2"}]
    # Editing + Apply writes back and fires the model hook.
    section.editor.set_equations([{"g": "amplitude"}, {"h": "tau + g"}])
    section.editor.apply()
    assert model.equations == [{"g": "amplitude"}, {"h": "tau + g"}]
    assert model.applied_count == 1


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
