"""Picking a dye in *Dyes (database)* applies the pair.

The form (emtk ``view_form`` and the Qt AutoForm alike) commits a bound control
as ``setattr`` then ``call(value)``. ``apply_dye_selection`` took no value, so
every pick raised ``TypeError`` -- "Choosing a dye does nothing" in guide 14 --
and R0, the quantum yields and tau_D(0) never followed the dyes.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from types import SimpleNamespace

from emtk.view_form import FormState, _commit

from chisurf.plugins.burst.accurate_fret.gui.view_model import AccurateFretViewModel

VIEW = Path(__file__).resolve().parents[1] / "gui" / "accurate_fret.view.json"


def _sections(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _sections(value)
    elif isinstance(node, list):
        for value in node:
            yield from _sections(value)


def test_every_bound_call_takes_the_committed_value():
    calls = {
        s["call"] for s in _sections(json.loads(VIEW.read_text())) if "call" in s and "attr" in s
    }
    assert "apply_dye_selection" in calls
    for name in calls:
        signature = inspect.signature(getattr(AccurateFretViewModel, name))
        signature.bind(object(), "value")  # raises TypeError when it cannot take one


def test_picking_two_dyes_applies_the_pair(monkeypatch):
    import chisurf.core.fluorescence.fret.dyes as dyes

    pair = SimpleNamespace(
        forster_radius=61.5,
        donor=SimpleNamespace(name="Alexa488", quantum_yield=0.8, lifetime=4.1),
        acceptor=SimpleNamespace(name="Alexa647", quantum_yield=0.33),
        summary=lambda: "pair",
    )
    monkeypatch.setattr(dyes, "fret_pair", lambda *a, **k: pair)
    model = AccurateFretViewModel()
    state = FormState()
    section = {"type": "choice", "attr": "donor_dye", "call": "apply_dye_selection"}
    _commit(model, section, "Alexa488", state)
    _commit(model, dict(section, attr="acceptor_dye"), "Alexa647", state)
    assert model.forster_radius == 61.5
    assert model.donor_lifetime == 4.1
    assert model.quantum_yield_acceptor == 0.33
