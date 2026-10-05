"""The Data-table plot page drawn by emtk.

The fit window's "Data table" page was the last plot page whose whole content
was a classic Qt widget stack (``ChiTableWidget`` plus Qt tool buttons). The
emtk port renders the table, the toolbar and the status line through emtk's
``DataTable``/``Button`` widgets and keeps every routing behaviour (x/data and
mask edits reach the fit and the fitting client). The fit window is one emtk
surface, so this is the only Data-table page it can show.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from chisurf.gui.plots.table_plot import _BASE_COLUMNS  # noqa: E402


class _Curve:
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


class _FakeClient:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def _record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return {"ok": True}

        return _record


@pytest.fixture
def emtk_plot(qapp, monkeypatch):
    """A shown emtk Data-table plot over a fake fit, plus the recorded client."""
    from chisurf.gui.plots.table_plot_emtk import FitTablePlotEmtk

    client = _FakeClient()
    monkeypatch.setattr("chisurf.gui.plots.table_plot.get_fitting_client", lambda: client)
    plot = FitTablePlotEmtk(_FakeFit())
    plot.resize(760, 420)
    plot.show()
    yield plot, client
    # Tear down while the interpreter is alive: a host whose control wrapper
    # dies at shutdown raises inside focusOutEvent and aborts the process.
    try:
        plot._host.clearFocus()
        plot.table.cancel_edit()
    except RuntimeError:
        pass
    plot.close()
    plot.deleteLater()
    from qtpy import QtCore

    QtCore.QTimer.singleShot(0, lambda: None)
    qapp.processEvents()


def _draw_once(plot):
    """Draw one frame so the table's hit geometry exists, like emtk's tests."""
    from emtk.testing import RecordingPainter

    painter = RecordingPainter()
    plot.draw_content(painter, 0.0, 0.0, float(plot.width()), float(plot.height()))
    return painter


def _cell(table, position, column_key):
    """Centre of a cell, emtk's test idiom (drawn geometry -> coordinates)."""
    col_index = next(i for i, c in enumerate(table.visible_columns()) if c.key == column_key)
    bx, by = table._body_box[0], table._body_box[1]
    x = bx + sum(table._widths[:col_index]) + table._widths[col_index] * 0.5
    return x, by + table._row_h * (position + 0.5)


def test_plot_is_emtk_drawn(emtk_plot):
    from emtk.widgets.buttons import SmallButton
    from emtk.widgets.data_table import DataTable

    plot, _ = emtk_plot
    assert getattr(plot, "emtk", False) is True
    assert isinstance(plot.table, DataTable)
    assert not hasattr(plot.table, "table_model")  # no ChiTableWidget inside
    assert isinstance(plot.btn_copy, SmallButton)
    assert plot._host is not None


def test_plot_lists_every_column(emtk_plot):
    plot, _ = emtk_plot
    table = plot.table
    assert table.row_count() == 8
    keys = [c.key for c in table.columns]
    assert list(keys[:5]) == list(_BASE_COLUMNS)
    assert "irf" in keys
    assert "data" not in keys[5:]


def test_data_edit_via_real_input_reaches_the_fit(emtk_plot):
    from emtk.keys import KEY_BACKSPACE, KEY_RETURN

    plot, client = emtk_plot
    _draw_once(plot)
    table = plot.table
    x, y = _cell(table, 2, "data")
    assert table.press(x, y, 0.0, 0.0, 760.0, 420.0, 0, 2), "double click opens the cell"
    assert table.editing is not None
    for _ in range(10):
        assert table.key(KEY_BACKSPACE, "", 0)  # clear the current value
    for ch in "99":
        assert table.key(0, ch, 0)
    assert table.key(KEY_RETURN, "", 0)  # Enter commits
    assert plot.fit.data.y[2] == 99.0
    assert any(c[0] == "update_fit" for c in client.calls)


def test_mask_click_flips_and_routes(emtk_plot):
    plot, client = emtk_plot
    _draw_once(plot)
    table = plot.table
    x, y = _cell(table, 3, "mask")
    assert table.press(x, y, 0.0, 0.0, 760.0, 420.0, 0, 1)
    masks = [c for c in client.calls if c[0] == "set_fit_mask"]
    assert masks, "clicking a mask checkbox must push a new mask"
    pushed = np.asarray(masks[-1][2]["mask"], dtype=float)
    assert pushed[3] == 0.0
    assert pushed.sum() == 7.0


def test_copy_includes_headers(emtk_plot):
    plot, _ = emtk_plot
    from qtpy import QtWidgets

    plot.on_copy_table_to_clipboard()
    lines = QtWidgets.QApplication.clipboard().text().splitlines()
    assert lines[0].split("\t")[:5] == list(_BASE_COLUMNS)
    assert len(lines) == 9


def test_filter_narrows_visible_rows(emtk_plot):
    plot, _ = emtk_plot
    table = plot.table
    table.filter.set_text("7")
    assert table.row_count() == 8
    assert len(table.order()) == 1


def test_the_registry_gives_the_emtk_page(qapp):
    from chisurf.gui.autoform.sections.registry import get_plot_class
    from chisurf.gui.plots.table_plot_emtk import FitTablePlotEmtk

    assert get_plot_class("fit_table") is FitTablePlotEmtk


def test_offscreen_render_is_emtk_dark(emtk_plot, qapp):
    plot, _ = emtk_plot
    _draw_once(plot)
    png = os.path.join(os.environ.get("CHISURF_EVIDENCE_DIR", "/tmp"), "fit_table_emtk.png")
    plot.grab().save(png)
    assert os.path.exists(png)


def _press_button(plot, button):
    x, y, w, h = plot._btn_boxes[id(button)]
    plot.press(x + w / 2, y + h / 2)
    plot.release()
    _draw_once(plot)


def test_the_qt_pages_table_tools_are_all_here(emtk_plot):
    """Columns, Hide empty, Shade, its scope and Export: the Qt page had all five."""
    plot, _ = emtk_plot
    _draw_once(plot)
    for button in (plot.btn_columns, plot.btn_empty, plot.btn_shade, plot.btn_scope,
                   plot.btn_export):
        assert id(button) in plot._btn_boxes
        x, y, w, h = plot._btn_boxes[id(button)]
        assert plot.tooltip_at(x + 2, y + 2), f"{button.label} has no tooltip"


def test_columns_asks_the_table_for_its_column_list(emtk_plot):
    plot, _ = emtk_plot
    _draw_once(plot)
    _press_button(plot, plot.btn_columns)
    assert plot.table.picker_at is not None


def test_shade_and_its_scope(emtk_plot):
    plot, _ = emtk_plot
    _draw_once(plot)
    assert plot.table.colour_values is None
    _press_button(plot, plot.btn_shade)
    assert plot.table.colour_values == "column"
    _press_button(plot, plot.btn_scope)
    assert plot.table.colour_values == "table"
    _press_button(plot, plot.btn_shade)
    assert plot.table.colour_values is None


def test_hide_empty_hides_only_columns_without_values(emtk_plot):
    plot, _ = emtk_plot
    _draw_once(plot)
    key = plot.table.columns[-1].key
    plot.table.arrays[key] = np.full(len(plot.table.arrays[key]), np.nan)
    _press_button(plot, plot.btn_empty)
    assert key in plot.table.hidden
    assert len(plot.table.hidden) == 1
    _press_button(plot, plot.btn_empty)
    assert key not in plot.table.hidden


def test_export_writes_the_visible_table(emtk_plot, tmp_path):
    plot, _ = emtk_plot
    _draw_once(plot)
    path = plot.export_csv(str(tmp_path / "table.csv"))
    lines = (tmp_path / "table.csv").read_text().splitlines()
    assert path and lines[0].split(",") == [c.key for c in plot.table.visible_columns()]
    assert len(lines) == plot.table.row_count() + 1
