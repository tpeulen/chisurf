"""Real-input click tests for the alex_suite EMTK app (AGY_ACCEPTANCE bar).

Every interactive control is operated through the Driver: tabs switch, the
fields accept typing, Help opens its window, and the titration table's cells
take typed values. The old ALEX-Suite CSV export is not part of the app any
more (the pipeline is pto end to end; the converter command writes those
files), which the tab test asserts.
"""

from __future__ import annotations

import pathlib

import pytest

from chisurf.plugins.burst.alex_suite.gui.app import make_app
from chisurf.plugins.emtk_layout import action_caption
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
    drv.click_text("🚦 Alternation")
    assert app.suite_gui.selected_tab == "alternation"


def test_the_legacy_export_tab_is_gone(app, drv):
    """The pto pipeline has no ALEX-Suite CSV export step: old formats are the converter's job."""
    drv.draw(2)
    assert not hasattr(app.suite_gui, "export_gui")
    assert not hasattr(app.suite_gui, "export_state")
    assert not drv.drawn("💾 Legacy Export")
    assert not drv.drawn("💾 Write ALEX-Suite CSVs")


def test_help_button_opens_the_help_window(app, drv):
    app.suite_gui.selected_tab = "titration"
    drv.draw(2)
    gui = app.suite_gui.titration_gui
    assert not gui.help_window.open
    drv.click_text(action_caption("help"), last=True)
    drv.draw(2)
    assert gui.help_window.open


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
    for form in (
        (getattr(drv.app, "forms", None) or {}).values()
        if isinstance(getattr(drv.app, "forms", None), dict)
        else [getattr(drv.app, "form", None)]
    ):
        out.update(getattr(form, "rects", {}) or {})
    return out
