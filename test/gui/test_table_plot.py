"""Offscreen-Qt tests for the Data-table plot.

Exercises the plot without a live fit by driving the pieces that used to depend
on the retired third-party editor: the column layout the fit produces, the
parameter frame the "Show model" dialog edits, and the write-back that pushes an
accepted frame through the fitting client.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from chisurf.gui.plots.table_plot import (  # noqa: E402
    _BASE_COLUMNS,
    _EDITABLE_COLUMNS,
    FitTablePlot,
    _fit_column_specs,
    _parse_bool,
)


def test_column_specs_mark_only_the_editable_columns():
    specs = _fit_column_specs(_BASE_COLUMNS + ("support",))
    editable = {s.key for s in specs if s.editable}
    assert editable == set(_EDITABLE_COLUMNS)
    assert [s.key for s in specs][:5] == list(_BASE_COLUMNS)
    assert all(s.kind == "float" for s in specs)


def test_mask_column_is_documented():
    mask = next(s for s in _fit_column_specs(_BASE_COLUMNS) if s.key == "mask")
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
    df = plot._parameter_frame(params)
    assert list(df.columns) == [
        "name",
        "value",
        "lb",
        "ub",
        "fixed",
        "bounds_on",
        "linked",
        "link_target",
    ]
    assert df["name"].tolist() == ["a", "b"]
    assert df["value"].tolist() == [1.5, 2.5]
    assert df["fixed"].tolist() == [False, True]
    assert df["link_target"].tolist() == ["", ""]


def test_parameter_frame_tolerates_unreadable_bounds():
    class _Bad(_Param):
        def __init__(self):
            super().__init__("bad", float("nan"), bounds=(None, None))

    plot = FitTablePlot.__new__(FitTablePlot)
    df = plot._parameter_frame({"bad": _Bad()})
    assert np.isnan(df["lb"].iloc[0])
    assert np.isnan(df["ub"].iloc[0])


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
    monkeypatch.setattr("chisurf.gui.plots.table_plot.get_fitting_client", lambda: client)

    plot = FitTablePlot.__new__(FitTablePlot)
    plot.fit = type("_Fit", (), {"unique_identifier": "uid", "fit_idx": 0})()
    plot._refresh_arrays_into_model = lambda: None

    params = {"a": _Param("a", 1.0), "b": _Param("b", 2.0)}
    df = pd.DataFrame(
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
    plot._apply_parameter_frame(df, params)

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
    monkeypatch.setattr("chisurf.gui.plots.table_plot.get_fitting_client", lambda: client)
    plot = FitTablePlot.__new__(FitTablePlot)
    plot.fit = type("_Fit", (), {"unique_identifier": "uid", "fit_idx": 0})()
    plot._refresh_arrays_into_model = lambda: None

    df = pd.DataFrame([{"name": "ghost", "value": 1.0, "lb": np.nan, "ub": np.nan}])
    plot._apply_parameter_frame(df, {})
    assert [c[0] for c in client.calls] == ["update_fit", "model_finalize"]


def test_plot_module_does_not_import_guidata():
    import chisurf.gui.plots.table_plot as mod

    assert "guidata" not in mod.__doc__.lower()
    assert not hasattr(mod, "DataFrameEditor")


# ── end-to-end against a duck-typed fit ──────────────────────────────────


class _Curve:
    """Minimal x/y curve."""

    def __init__(self, x, y):
        self.x = np.asarray(x, dtype=float)
        self.y = np.asarray(y, dtype=float)
        self.ex = np.ones_like(self.x)
        self.ey = np.ones_like(self.y)

    def set_data(self, x, y, ex=None, ey=None):
        self.x = np.asarray(x, dtype=float)
        self.y = np.asarray(y, dtype=float)
        if ex is not None:
            self.ex = np.asarray(ex, dtype=float)
        if ey is not None:
            self.ey = np.asarray(ey, dtype=float)


class _FakeFit:
    """Duck-typed fit exposing exactly what the table plot reads."""

    unique_identifier = "test-uid"
    fit_idx = 0
    name = "test fit"
    chi2r = 1.25

    def __init__(self, n=8):
        x = np.arange(n, dtype=float)
        self.data = _Curve(x, x * 2.0)
        self.model = _Curve(x, x * 2.0 + 0.1)
        self.weighted_residuals = _Curve(x, np.full(n, 0.5))
        self.fit_range = (1, n - 2)
        self.mask = np.ones(n, dtype=float)

    def get_curves(self, copy_curves=False):
        return {"data": self.data, "model": self.model, "irf": self.model}


@pytest.fixture
def fit_plot(qapp, monkeypatch):
    """Return a shown :class:`FitTablePlot` over a fake fit plus its client.

    Returns
    -------
    tuple of (FitTablePlot, _FakeClient)
    """
    client = _FakeClient()
    monkeypatch.setattr("chisurf.gui.plots.table_plot.get_fitting_client", lambda: client)
    plot = FitTablePlot(_FakeFit())
    plot.show()
    plot._refresh_arrays_into_model()
    yield plot, client
    plot.close()
    plot.deleteLater()


def test_plot_builds_and_lists_every_column(fit_plot):
    plot, _ = fit_plot
    model = plot.table.table_model
    assert model.rowCount() == 8
    headers = [s.key for s in model.specs]
    assert headers[:5] == list(_BASE_COLUMNS)
    assert "irf" in headers  # support curves become extra columns
    assert "data" not in headers[5:]  # ...but the dedicated ones are not repeated


def test_plot_shows_residuals_inside_the_fit_range_only(fit_plot):
    plot, _ = fit_plot
    model = plot.table.table_model
    col = model.column_index("w. res.")
    first = model.data(model.index(0, col), __import__("qtpy").QtCore.Qt.DisplayRole)
    inside = model.data(model.index(1, col), __import__("qtpy").QtCore.Qt.DisplayRole)
    assert first == ""  # outside the fit range
    assert inside == "0.5"


def test_plot_mask_edit_reaches_the_client(fit_plot):
    from qtpy import QtCore

    plot, client = fit_plot
    model = plot.table.table_model
    col = model.column_index("mask")
    assert model.setData(model.index(3, col), "0", QtCore.Qt.EditRole)
    masks = [c for c in client.calls if c[0] == "set_fit_mask"]
    assert masks, "editing the mask column must push a new mask"


def test_plot_data_edit_writes_back_to_the_curve(fit_plot):
    from qtpy import QtCore

    plot, client = fit_plot
    model = plot.table.table_model
    col = model.column_index("data")
    assert model.setData(model.index(2, col), "99", QtCore.Qt.EditRole)
    assert plot.fit.data.y[2] == 99.0
    assert any(c[0] == "update_fit" for c in client.calls)


def test_plot_copy_includes_headers(fit_plot):
    plot, _ = fit_plot
    plot.on_copy_table_to_clipboard()
    from qtpy import QtWidgets

    text = QtWidgets.QApplication.clipboard().text()
    lines = text.splitlines()
    assert lines[0].split("\t")[:5] == list(_BASE_COLUMNS)
    assert len(lines) == 9  # header + 8 rows


def test_plot_filter_narrows_the_table(fit_plot):
    from chisurf.gui.widgets.chitable import ColumnFilter, FilterSpec

    plot, _ = fit_plot
    model = plot.table.table_model
    col = model.column_index("x")
    plot.table.set_filter(FilterSpec(columns=(ColumnFilter(column=col, op="ge", value=4),)))
    assert plot.table.visible_row_count() == 4
    assert plot.table.total_row_count() == 8
