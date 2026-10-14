"""The reaction-scheme editor's declarative wiring.

The core tests in ``test/models/test_reaction_model.py`` cover the scheme and the
integration. What the view spec adds is the set of ``button_row`` actions, which must
name zero-argument model methods, and the scheme JSON field, which must be bound to the
property. Both are checked on the model; the rendered editor is covered by the emtk shell
tests (``test/native_emtk/test_emtk_shell_model_sections.py``).
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import numpy as np
import pytest

import chisurf.core.models.stopped_flow as stopped_flow


@pytest.fixture()
def model():
    """Return the reaction model of a fit over a synthetic relaxation."""
    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.data import DataCurve
    from chisurf.core.models.stopped_flow.reaction import ReactionModel

    x = np.linspace(0.0, 10.0, 200)
    data = DataCurve(
        name="stopped-flow",
        load_filename_on_init=False,
        x=x,
        y=1.0 - 0.5 * np.exp(-x),
    )
    return fit_mod.Fit(model_class=ReactionModel, data=data).model


def _button_actions() -> dict[str, str]:
    """Return ``{label: action}`` for every ``button_row`` button of the spec."""
    spec = json.loads((Path(stopped_flow.__file__).parent / "reaction.view.json").read_text())
    found: dict[str, str] = {}

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "button_row":
                for b in node["buttons"]:
                    found[b["label"]] = b["action"]
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(spec)
    return found


def test_every_button_action_is_a_zero_argument_model_method(model):
    """``button_row`` actions name callable model methods that take no arguments."""
    actions = _button_actions()
    assert actions, "the spec declares no buttons"
    for label, action in actions.items():
        method = getattr(model, action)
        assert callable(method), f"{label}: {action} is not callable"
        required = [
            p
            for p in inspect.signature(method).parameters.values()
            if p.default is p.empty and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ]
        assert not required, f"{label}: {action} needs {required}"


def test_add_and_reset_buttons_drive_the_model(model):
    """The actions the buttons name extend and reset the scheme."""
    actions = {label.split(" ", 1)[-1]: action for label, action in _button_actions().items()}
    getattr(model, actions["Add step"])()
    assert model.n_reactions == 3

    getattr(model, actions["Reset"])()
    assert model.n_reactions == 2

    before = len(model.species_names)
    getattr(model, actions["Add species"])()
    assert len(model.species_names) == before + 1


def test_scheme_json_holds_the_species_and_reactions(model):
    """The scheme field shows the scheme the model holds."""
    text = model.reaction_json
    assert '"reactions"' in text and '"species"' in text
