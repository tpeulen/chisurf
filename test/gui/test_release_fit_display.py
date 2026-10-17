"""The parameter catalogue DTO marks the selected equation without dropping inactive ports."""

from __future__ import annotations

import numpy as np
import pytest


@pytest.fixture
def equation_session():
    """Two real catalogue models."""
    from chisurf.core.data import DataCurve
    from chisurf.core.fitting.fit import Fit
    from chisurf.core.models.fcs.parse import ParseFCSModel

    x = np.geomspace(0.001, 100, 64)
    fits = []
    for name in ("A", "B"):
        fit = Fit(
            data=DataCurve(x=x, y=1 + 0.01 / (1 + x), ey=np.full_like(x, 0.01)),
            model_class=ParseFCSModel,
        )
        fit.name = name
        fit.model.model_name = "3D Gauss, 1 bunching"
        fit.model.update()
        fits.append(fit)
    return fits


def test_catalogue_dto_retains_inactive_ports_and_marks_the_selected_equation(equation_session):
    """Transport retains all topology while supplying six active presentation flags."""
    from chisurf.server.services._stats import _collect_param_list

    fit = equation_session[0]
    entries = _collect_param_list(fit)
    assert len(entries) == len(fit.model.parameters_all) == 134
    active = [entry for entry in entries if entry["active_in_structure"]]
    assert {entry["name"] for entry in active} == {"b", "N", "td", "s", "ba", "bt"}
    # Selection changes visibility, never parameter identity or DTO inventory.
    before = {entry["uid"] for entry in entries}
    fit.model.model_name = fit.model.catalogue_names[1]
    changed = _collect_param_list(fit)
    assert {entry["uid"] for entry in changed} == before
    wanted = set(fit.model.structure_parameter_ids())
    by_uid = {p.unique_identifier: p for p in fit.model.parameters_all}
    assert all(
        entry["active_in_structure"] == (by_uid[entry["uid"]].canonical_id in wanted)
        for entry in changed
    )
