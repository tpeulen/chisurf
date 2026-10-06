"""The Data-table page's plumbing, without drawing it.

The column layout the fit produces, the parameter frame the *Model* editor
edits, the write-back that pushes an accepted frame through the fitting client,
and the residuals placed inside the fit range. The drawn page is
``test_table_plot_emtk.py``.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from chisurf.core.datastore import column_names, numeric_column, store_from_rows  # noqa: E402
from chisurf.gui.plots.table_plot_emtk import (  # noqa: E402
    _BASE_COLUMNS,
    _EDITABLE_COLUMNS,
    _parse_bool,
    column_specs,
)
from chisurf.gui.plots.table_plot_emtk import FitTablePlotEmtk as FitTablePlot  # noqa: E402


def test_column_specs_mark_only_the_editable_columns():
    specs = column_specs(_BASE_COLUMNS + ("support",))
    editable = {s.key for s in specs if s.editable}
    assert editable == set(_EDITABLE_COLUMNS)
    assert [s.key for s in specs][:5] == list(_BASE_COLUMNS)


def test_mask_column_is_documented():
    mask = next(s for s in column_specs(_BASE_COLUMNS) if s.key == "mask")
    assert "excludes" in mask.tooltip


@pytest.mark.parametrize(
    "value,expected",
    [
        (True, True),
        (False, False),
        (1, True),
        (0, False),
        (1.0, True),
        ("True", True),
        ("yes", True),
        ("off", False),
        ("", False),
        (None, False),
    ],
)
def test_parse_bool(value, expected):
    assert _parse_bool(value) is expected


class _Param:
    """Stand-in for a fitting parameter."""

    def __init__(self, name, value, fixed=False, bounds=(0.0, 1.0)):
        self.name = name
        self.value = value
        self.fixed = fixed
        self.bounds = bounds
        self.bounds_on = False
        self.is_linked = False
        self.link = None


def test_parameter_frame_layout():
    plot = FitTablePlot.__new__(FitTablePlot)  # no Qt construction needed
    params = {"a": _Param("a", 1.5), "b": _Param("b", 2.5, fixed=True)}
    table = plot._parameter_frame(params)
    assert column_names(table) == [
        "name",
        "value",
        "lb",
        "ub",
        "fixed",
        "bounds_on",
        "linked",
        "link_target",
    ]
    assert list(np.asarray(table["name"])) == ["a", "b"]
    assert list(numeric_column(table, "value")) == [1.5, 2.5]
    assert list(numeric_column(table, "fixed")) == [0.0, 1.0]
    assert list(np.asarray(table["link_target"])) == ["", ""]


def test_parameter_frame_tolerates_unreadable_bounds():
    class _Bad(_Param):
        def __init__(self):
            super().__init__("bad", float("nan"), bounds=(None, None))

    plot = FitTablePlot.__new__(FitTablePlot)
    table = plot._parameter_frame({"bad": _Bad()})
    assert np.isnan(numeric_column(table, "lb")[0])
    assert np.isnan(numeric_column(table, "ub")[0])


class _FakeClient:
    """Records the fitting-client calls the write-back makes."""

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def _record(*args, **kwargs):
            self.calls.append((name, args))
            return {"ok": True}

        return _record


def test_apply_parameter_frame_pushes_edits(monkeypatch):
    client = _FakeClient()
    monkeypatch.setattr("chisurf.gui.plots.table_plot_emtk.get_fitting_client", lambda: client)

    plot = FitTablePlot.__new__(FitTablePlot)
    plot.fit = type("_Fit", (), {"unique_identifier": "uid", "fit_idx": 0})()
    plot._refresh_arrays_into_model = lambda: None

    params = {"a": _Param("a", 1.0), "b": _Param("b", 2.0)}
    table = store_from_rows(
        [
            {
                "name": "a",
                "value": 9.0,
                "lb": 0.0,
                "ub": 10.0,
                "fixed": True,
                "bounds_on": True,
                "linked": True,
                "link_target": "b",
            },
            {
                "name": "b",
                "value": 2.0,
                "lb": np.nan,
                "ub": np.nan,
                "fixed": False,
                "bounds_on": False,
                "linked": False,
                "link_target": "",
            },
        ]
    )
    plot._apply_parameter_table(table, params)

    names = [c[0] for c in client.calls]
    assert names.count("set_parameter_value") == 2
    assert ("set_parameter_value", ("a", 9.0)) in client.calls
    # b has no finite bounds, so only a gets a bounds call
    assert names.count("set_parameter_bounds") == 1
    assert ("set_parameter_fixed", ("a", True)) in client.calls
    assert ("link_parameters", ("a", "b")) in client.calls
    assert ("unlink_parameter", ("b",)) in client.calls
    assert "update_fit" in names and "model_finalize" in names


def test_apply_parameter_frame_skips_unknown_parameters(monkeypatch):
    client = _FakeClient()
    monkeypatch.setattr("chisurf.gui.plots.table_plot_emtk.get_fitting_client", lambda: client)
    plot = FitTablePlot.__new__(FitTablePlot)
    plot.fit = type("_Fit", (), {"unique_identifier": "uid", "fit_idx": 0})()
    plot._refresh_arrays_into_model = lambda: None

    table = store_from_rows([{"name": "ghost", "value": 1.0, "lb": np.nan, "ub": np.nan}])
    plot._apply_parameter_table(table, {})
    assert [c[0] for c in client.calls] == ["update_fit", "model_finalize"]


def test_plot_module_is_qt_free():
    import chisurf.gui.plots.table_plot_emtk as mod

    source = open(mod.__file__, encoding="utf-8").read()
    assert "qtpy" not in source and "QtWidgets" not in source
    assert not hasattr(mod, "DataFrameEditor")


def test_residuals_sit_inside_the_fit_range_only():
    from types import SimpleNamespace

    n = 8
    x = np.arange(n, dtype=float)
    curve = lambda y: SimpleNamespace(x=x, y=np.asarray(y, dtype=float))  # noqa: E731
    fit = SimpleNamespace(
        data=curve(x * 2.0),
        model=curve(x * 2.0 + 0.1),
        weighted_residuals=curve(np.full(n, 0.5)),
        fit_range=(1, n - 2),
        mask=np.ones(n),
        get_curves=lambda copy_curves=False: {},
    )
    plot = FitTablePlot.__new__(FitTablePlot)
    plot.fit = fit
    _x, _y, _ym, wres, _mask, _support = plot._get_arrays()
    assert np.isnan(wres[0]) and wres[1] == 0.5


