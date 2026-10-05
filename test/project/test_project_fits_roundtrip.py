from __future__ import annotations

import json

import numpy as np
import pytest

pytest.importorskip("chinet")

from chisurf.core.data import DataCurve
from chisurf.core.fitting.fit import Fit
from chisurf.core.fitting.parameter import FittingParameter
from chisurf.core.models.model import ModelCurve
from chisurf.core.project import (
    ProjectArchive,
    capture_session,
    load_project,
    restore_session,
    save_project,
)


class DummyLinearModel(ModelCurve):
    """Small concrete model used for Project.fits round-trip tests.

    Uses two fitting parameters ``p0`` and ``p1`` to describe
    ``y = p0 + p1 * x``. This mirrors the setup in ``test_fit_state``
    without depending on any GUI components.
    """

    name = "DummyLinearModelForProject"

    def __init__(self, fit: Fit, **kwargs):  # type: ignore[override]
        super().__init__(fit, **kwargs)
        self.p0 = FittingParameter(name="p0", value=0.5)
        self.p1 = FittingParameter(name="p1", value=1.5)
        self.find_parameters()

    def _update_model(self, **kwargs):  # type: ignore[override]
        x = self.fit.data.x
        if x is None:
            x = np.arange(self.fit.data.y.size, dtype=float)
        self.x = x
        self.y = float(self.p0.value) + float(self.p1.value) * x

    def update(self, **kwargs) -> None:  # type: ignore[override]
        super().update(**kwargs)


def _make_dummy_fit() -> Fit:
    x = np.arange(4, dtype=float)
    y = np.ones_like(x)
    data = DataCurve(x=x, y=y)
    return Fit(model_class=DummyLinearModel, data=data)


def test_project_fits_roundtrip_with_single_fit(tmp_path):
    fit = _make_dummy_fit()
    fit.unique_identifier = "fit-uid-1"
    fit.fit_range = (1, 3)
    params = fit.model.parameters_all_dict
    params["p0"].value = 2.0
    params["p0"].bounds = (0.0, 5.0)
    params["p0"].bounds_on = True

    params["p1"].value = -0.5
    params["p1"].fixed = True

    project = capture_session([fit.data], [fit], name="proj_with_fit")
    archive_path = save_project(project, tmp_path / "proj1")
    assert archive_path.is_file()

    # Inspect the exact returned PTO path to ensure fits structure is present.
    archive = ProjectArchive.open(archive_path)
    raw = json.loads(archive.read_text("project.json"))
    archive.close()

    assert "fits" in raw
    assert len(raw["fits"]) == 1
    raw_fit = raw["fits"][0]
    assert raw_fit["uid"] == "fit-uid-1"
    assert raw_fit["members"][0]["dataset_uid"] == fit.data.unique_identifier
    assert raw_fit["members"][0]["fit_range"] == [1, 3]
    assert raw_fit["members"][0]["model"]["model_class"] == "DummyLinearModel"

    loaded_project = load_project(archive_path)
    restored = restore_session(loaded_project)
    assert len(restored.fits) == 1
    fit2 = restored.fits[0]
    params2 = fit2.model.parameters_all_dict

    assert np.isclose(params2["p0"].value, 2.0)
    assert params2["p0"].bounds_on is True
    assert np.allclose(params2["p0"].bounds, [0.0, 5.0])

    assert np.isclose(params2["p1"].value, -0.5)
    assert params2["p1"].fixed is True
    assert fit2.fit_range == (1, 3)
    assert fit2.data.unique_identifier == fit.data.unique_identifier
