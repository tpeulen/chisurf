"""What the console prints for the session's datasets and fits (found 2026-10-11, guide 59).

``cs.imported_datasets`` printed every curve as its IMP.bff SWIG proxy
(``<chisurf.core.data.DataCurve; proxy of <Swig Object ...>>``), ``print`` of a curve group
raised ``TypeError: __str__ returned non-string (type list)``, a short curve's summary ran
all its rows into one line, and ``fit.chi2r`` printed as ``np.float64(5.08...)``.
"""

from __future__ import annotations

import numpy as np

import chisurf.core.fitting.fit as F
from chisurf.core.data import DataCurve, DataCurveGroup


def _curve(n: int = 15, name: str = "Kristine_with_error") -> DataCurve:
    return DataCurve(x=np.arange(float(n)), y=np.ones(n), ey=np.ones(n), name=name)


def test_a_curve_and_a_group_print_their_names():
    curve = _curve()
    group = DataCurveGroup([curve], name="Kristine_with_error")
    assert repr(curve) == "<DataCurve 'Kristine_with_error' n=15>"
    assert repr(group) == "<DataCurveGroup 'Kristine_with_error' [<DataCurve 'Kristine_with_error' n=15>]>"
    assert "Swig" not in repr([group])


def test_str_of_a_group_is_a_string():
    group = DataCurveGroup([_curve(), _curve(4, "b")], name="g")
    text = str(group)
    assert isinstance(text, str) and "------" in text
    assert "Dataset: b" in text


def test_every_row_of_a_short_curve_is_its_own_line():
    text = str(_curve(4, "short"))
    rows = [line for line in text.splitlines() if line.startswith(("0.000e", "1.000e", "2.000e", "3.000e"))]
    assert len(rows) == 4


def test_a_long_curve_shows_its_last_rows():
    text = str(_curve(15, "long"))
    assert text.splitlines()[-1].startswith("1.400e+01"), text


def test_chi2r_is_a_python_float():
    curve = _curve(20, "flat")
    from chisurf.core.models.fcs.general import GeneralFCSModel

    fit = F.Fit(model_class=GeneralFCSModel, data=curve)
    fit.model.find_parameters()
    assert type(fit.chi2r) is float
