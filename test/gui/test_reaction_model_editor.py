"""The reaction-scheme editor's declarative wiring (PRD-38).

The core tests in ``test/models/test_reaction_model.py`` cover the scheme and the
integration. What only a rendered editor can show is whether the view spec
actually reaches them: whether the reaction ``table`` gets its rows, whether the
``button_row`` buttons call the zero-arg model methods, and whether the JSON
field is bound to the property rather than to nothing.

Run headless in the arm64 env, in its own process::

    QT_QPA_PLATFORM=offscreen python -m pytest \\
        test/gui/test_reaction_model_editor.py -p no:cov -o addopts=""
"""

from __future__ import annotations

import numpy as np
import pytest


@pytest.fixture(scope="module")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture()
def editor_and_model():
    """Return ``(editor, model)`` for a reaction fit over a synthetic relaxation."""
    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.data import DataCurve
    from chisurf.core.models.stopped_flow.reaction import ReactionModel
    from chisurf.gui.widgets.models.model_editor import build_model_editor

    x = np.linspace(0.0, 10.0, 200)
    data = DataCurve(
        name="stopped-flow",
        load_filename_on_init=False,
        x=x,
        y=1.0 - 0.5 * np.exp(-x),
    )
    fit = fit_mod.Fit(model_class=ReactionModel, data=data)
    return build_model_editor(fit.model), fit.model


def _buttons(editor):
    """Return every clickable button in the editor, by text."""
    from qtpy import QtWidgets

    return {
        b.text(): b
        for b in editor.findChildren(QtWidgets.QToolButton)
        + editor.findChildren(QtWidgets.QPushButton)
    }


def test_reaction_table_shows_the_steps_by_name(qapp, editor_and_model):
    """The ``table`` section renders one row per reaction, written with names."""
    from qtpy import QtWidgets

    editor, model = editor_and_model
    tables = [
        t
        for t in editor.findChildren(QtWidgets.QTableWidget)
        if t.columnCount() == 2 and t.rowCount() == model.n_reactions
    ]
    assert tables, "the reaction table rendered no rows"
    texts = {
        tables[0].item(r, 0).text()
        for r in range(tables[0].rowCount())
        if tables[0].item(r, 0) is not None
    }
    assert texts == {"A → B", "B → A"}, texts


def test_add_and_reset_buttons_drive_the_model(qapp, editor_and_model):
    """``button_row`` actions are zero-arg model methods and are actually wired."""
    editor, model = editor_and_model
    buttons = _buttons(editor)

    add_step = next(b for label, b in buttons.items() if "Add step" in label)
    add_step.click()
    assert model.n_reactions == 3

    reset = next(b for label, b in buttons.items() if "Reset" in label)
    reset.click()
    assert model.n_reactions == 2

    add_species = next(b for label, b in buttons.items() if "Add species" in label)
    before = len(model.species_names)
    add_species.click()
    assert len(model.species_names) == before + 1


def test_scheme_json_field_is_bound_to_the_property(qapp, editor_and_model):
    """The ``value`` ``kind: "text"`` field shows the scheme the model holds."""
    from qtpy import QtWidgets

    editor, model = editor_and_model
    fields = editor.findChildren(QtWidgets.QPlainTextEdit) + editor.findChildren(
        QtWidgets.QTextEdit
    )
    assert len(fields) == 1, f"expected one scheme field, found {len(fields)}"
    text = fields[0].toPlainText()
    assert '"reactions"' in text and '"species"' in text
    assert text == model.reaction_json
