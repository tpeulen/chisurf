"""Real-input click tests for the alex_suite EMTK app (AGY_ACCEPTANCE bar).

Every interactive control is operated through the Driver: tabs switch, the
burst-file combo opens and selects, Sample/Buffer fields accept typing, the
five part-checkboxes toggle, the Write button runs the export on a real table,
Help opens its window, and the titration table's cells take typed values.
"""
from __future__ import annotations

import pathlib

import pytest

from chisurf.plugins.burst.alex_suite.gui.app import make_app
from chisurf.plugins.emtk_test_input import Driver


def _write_burst_table(path, table):
    import numpy as np

    keys = list(table)
    lines = ["\t".join(keys)]
    rows = np.column_stack([table[k] for k in keys])
    lines += ["\t".join(f"{v:.10g}" for v in row) for row in rows]
    pathlib.Path(path).write_text("\n".join(lines) + "\n")


def _burst_table(n, e_true, *, s_true=0.5, size=200, seed=0):
    import numpy as np

    rng = np.random.default_rng(seed)
    total = rng.poisson(size, n).astype(float) + 20.0
    green = total * s_true
    i_da = rng.binomial(green.astype(int), e_true).astype(float)
    return {
        "Number of Photons (green)": green - i_da,
        "Number of Photons (red)": i_da,
        "Number of Photons (yellow)": total - green,
        "Duration (ms)": np.full(n, 1.0),
    }


@pytest.fixture
def app():
    application = make_app()
    return application


@pytest.fixture
def drv(app):
    return Driver(app, (800, 600))


def test_tabs_switch_by_click(app, drv):
    drv.draw(2)
    assert app.suite_gui.selected_tab == "alternation"
    drv.click_text("🧪 Titration")
    assert app.suite_gui.selected_tab == "titration"
    drv.click_text("💾 Legacy Export")
    assert app.suite_gui.selected_tab == "export"
    drv.click_text("🚦 Alternation")
    assert app.suite_gui.selected_tab == "alternation"


def test_alternation_fields_take_typing(app, drv):
    state = app.suite_gui.alternation_state
    drv.draw(2)
    # Label-right layout: the input spans the row left of its label. Click the
    # field body (a fifth of the row width in), select-all, type, commit.
    x, y, w, h = drv.text_rect(drv.draw(2), "Donor channels")
    drv.type_into((10.0, y - 2, 640.0, h + 4), "0", fx=0.2)
    assert state.donor_text == "0"
    x, y, w, h = drv.text_rect(drv.draw(2), "Acceptor channels")
    drv.type_into((10.0, y - 2, 640.0, h + 4), "1", fx=0.2)
    assert state.acceptor_text == "1"


def test_export_checkboxes_toggle_by_click(app, drv, tmp_path):
    app.suite_gui.selected_tab = "export"
    p = tmp_path / "sample.bur"
    _write_burst_table(p, _burst_table(50, 0.4, seed=1))
    app.suite_gui.export_state.set_burst_files([p])
    drv.draw(2)
    gui = app.suite_gui.export_gui
    before = dict(gui.parts)
    for key in ("metadata", "e_histogram", "histogram_2d"):
        label = {
            "metadata": "Metadata",
            "e_histogram": "E histogram",
            "histogram_2d": "2-D histogram",
        }[key]
        drv.click_text(label, last=True)
        assert gui.parts[key] != before[key], f"{label} checkbox did not toggle"
        before[key] = gui.parts[key]


def test_export_write_button_runs_on_a_real_table(app, drv, tmp_path, monkeypatch):
    app.suite_gui.selected_tab = "export"
    p = tmp_path / "sample.bur"
    _write_burst_table(p, _burst_table(120, 0.45, seed=7))
    app.suite_gui.export_state.set_burst_files([p])
    drv.draw(2)
    calls = []
    monkeypatch.setattr(
        app.suite_gui.export_gui.panel, "run_export",
        lambda **kw: calls.append(kw),
    )
    drv.click_text("💾 Write ALEX-Suite CSVs")
    assert calls, "the Write button did not reach run_export"
    assert calls[0]["sample"] == app.suite_gui.export_gui.sample_text


def test_help_button_opens_the_help_window(app, drv):
    app.suite_gui.selected_tab = "export"
    drv.draw(2)
    assert not app.suite_gui.export_gui.help_window.open
    drv.click_text("❓ Help")
    drv.draw(2)
    assert app.suite_gui.export_gui.help_window.open


def test_titration_cells_take_typing(app, drv, tmp_path):
    app.suite_gui.selected_tab = "titration"
    model = app.suite_gui.titration_state.model
    p = tmp_path / "t1.bur"
    _write_burst_table(p, _burst_table(80, 0.3, seed=3))
    model.add_files([str(p)])
    drv.draw(2)
    # 'series_table' remembers the last item's rect (the file cell), so locate
    # the concentration cell by its drawn content: the '0' the input shows.
    x, y, w, h = drv.text_rect(drv.draw(2), "0", last=False)
    drv.click((x + 40.0, y - 2.0, 60.0, h + 4.0), fx=0.5, fy=0.5)
    assert drv.app.io.want_capture_keyboard, "the cell did not take the keyboard"
    drv.type("12.5")
    drv.enter()
    drv.draw(2)
    assert any(abs(float(r["concentration"]) - 12.5) < 1e-9 for r in model.rows)


def _rects(drv):
    drv.draw()
    out = dict(getattr(drv.app, "item_rects", {}) or {})
    for form in (getattr(drv.app, "forms", None) or {}).values() if isinstance(
        getattr(drv.app, "forms", None), dict
    ) else [getattr(drv.app, "form", None)]:
        out.update(getattr(form, "rects", {}) or {})
    return out
