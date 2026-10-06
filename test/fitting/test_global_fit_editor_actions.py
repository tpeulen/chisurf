"""The global-fit editor's actions reach the global model.

``add_selected_fit``, ``remove_selected_local_fit`` and ``add_global_parameter``
called ``self.fit.<method>`` -- methods that exist only on the model -- so the
editor's ➕/➖ buttons raised ``AttributeError``; the local-fit table's
``source`` was a property, which a table calls, so it was always empty; and the
``append_global_parameter`` macro failed the same way inside a bare except.
"""

from __future__ import annotations

import chisurf as cs
from chisurf.core.fitting.fit import Fit
from chisurf.core.models.global_model.globalfit import GlobalFitModel
from chisurf.core.models.stopped_flow.parse import ParseStoppedFlowModel
from test.project.test_all_model_catalogue_roundtrip import CATALOGUE, _data


def _fits():
    entry = next(e for e in CATALOGUE if e["configured_path"].endswith("ParseStoppedFlowModel"))
    members = []
    for name in ("first", "second"):
        data = _data(entry, ParseStoppedFlowModel)
        member = Fit(data=data, model_class=ParseStoppedFlowModel, xmin=0, xmax=len(data.y))
        member.name = name
        members.append(member)
    entry = next(e for e in CATALOGUE if e["configured_path"].endswith("GlobalFitModel"))
    group = Fit(data=_data(entry, GlobalFitModel), model_class=GlobalFitModel)
    group.name = "global"
    return group, members


def test_add_and_remove_a_local_fit_from_the_editor(monkeypatch):
    group, members = _fits()
    monkeypatch.setattr(cs, "fits", [group, *members])
    model = group.model
    assert model.candidate_fit_names == ["first", "second"]
    model.selected_candidate_fit = "second"
    model.add_selected_fit()
    assert model.fits == [members[1]]
    assert model.local_fit_rows() == [{"name": "second"}]
    assert model.candidate_fit_names == ["first"]
    model.selected_local_fit = 0
    model.remove_selected_local_fit()
    assert model.fits == [] and model.selected_local_fit == -1


def test_add_a_global_parameter_from_the_editor_and_the_macro():
    group, _members = _fits()
    model = group.model
    model.new_global_parameter_name = "shared"
    model.add_global_parameter()
    assert "shared" in model._global_parameters
    assert model.new_global_parameter_name == ""

    from chisurf.macros.model import append_global_parameter

    append_global_parameter("other", fit=group)
    assert "other" in model._global_parameters


def test_the_table_source_is_callable():
    import json
    import pathlib

    import chisurf.core.models.global_model.globalfit as module

    spec = json.loads(pathlib.Path(module.__file__).with_name("globalfit.view.json").read_text())
    table = spec["sections"][0]["sections"][0]
    assert callable(getattr(GlobalFitModel, table["source"]))


def test_a_loaded_background_or_lintable_keeps_its_name(monkeypatch):
    """The editor's curve fields show the stored copy's name, so the copy needs one."""
    import numpy as np

    import chisurf.macros.model as macros
    from chisurf.core.data import DataCurve
    from chisurf.core.fitting.fit import FitGroup
    from chisurf.core.models.description import tcspc_lifetime

    x = np.linspace(0.0, 10.0, 64)
    data = DataCurve(x=x, y=np.exp(-x) * 100 + 1, ey=np.ones_like(x), name="decay")
    fit = FitGroup(data=cs.core.data.DataCurveGroup([data]), model_class=tcspc_lifetime)
    curve = DataCurve(x=x, y=np.ones_like(x), name="buffer.txt")
    monkeypatch.setattr(macros, "_resolve_selected_curve", lambda idx, name: curve)
    macros.set_background_curve(0, "buffer.txt", fit=fit)
    assert fit.model.generic.background_curve.name == "buffer.txt"
    macros.set_linearization(0, "buffer.txt", fit=fit)
    assert fit.model.corrections.lintable.name == "buffer.txt"
