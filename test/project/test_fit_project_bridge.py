"""A fit export must use the same schema that the fit import accepts."""

import numpy as np

import chisurf as cs
from chisurf.core.data import DataCurve
from chisurf.core.fitting.fit import FitGroup
from chisurf.macros.core_fit import load_fit_project, save_fit_project
from test.project.test_session_codec import _TwoParameterModel


def test_single_fit_save_load_uses_shared_codec_without_replacing_other_fits(monkeypatch, tmp_path):
    source = DataCurve(x=np.arange(8.0), y=np.arange(8.0) + 2, name="exported")
    fit = FitGroup([source], model_class=_TwoParameterModel)
    fit.model.amplitude.value = 4.5
    monkeypatch.setattr(cs, "fits", [fit])
    monkeypatch.setattr(cs, "imported_datasets", [source])
    monkeypatch.setattr(cs, "cs", None)
    path = save_fit_project(str(tmp_path), fit_name="single-fit")
    assert path.is_file()
    other = DataCurve(x=np.arange(8.0), y=np.ones(8), name="already-live")
    existing = FitGroup([other], model_class=_TwoParameterModel)
    cs.fits[:] = [existing]
    cs.imported_datasets[:] = [other]
    load_fit_project(str(path))
    assert cs.fits[0] is existing
    assert len(cs.fits) == 2
    assert cs.imported_datasets[0] is other
    restored = cs.fits[1]
    assert restored.unique_identifier == fit.unique_identifier
    assert restored.model.amplitude.value == 4.5
    np.testing.assert_array_equal(restored.data.y, source.y)
