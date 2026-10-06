"""Layout of the photon-by-photon kinetics window at 1200x800 and 800x600.

Defects fixed: six full-width buttons stacked in the left panel (now wrapped rows), "Stop fit" live while idle,
the report cut off at the window's bottom with no scrollbar, short fields as wide as the panel, icons touching labels.
"""

import pytest

from chisurf.plugins.burst.burst_gs.gui.app import create_app
from test.gui.emtk_layout_checks import (
    SIZES,
    assert_disjoint,
    assert_icons_clear,
    assert_inside,
    assert_texts_apart,
    draw,
)


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    monkeypatch.chdir(tmp_path)


@pytest.fixture(params=SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def drawn(request):
    app = create_app()
    app.model.sim_n_bursts, app.model.sim_photons_per_burst, app.model.max_iterations = 30, 60, 200
    painter = draw(app, request.param)
    yield app, painter, request.param
    app.close()


ACTIONS = ["Fit", "Stop", "Export", "guide", "help"]


def test_actions_are_wrapped_rows_not_a_stack(drawn):
    app, _p, size = drawn
    rects = app.item_rects
    assert_disjoint(rects, ["bur_files", *ACTIONS])
    ys = {round(rects[n][1]) for n in ACTIONS}
    assert len(ys) <= (1 if size[0] >= 1200 else 3), (
        f"the action buttons stack in {len(ys)} rows: {sorted(ys)}"
    )


def test_the_report_scrolls_inside_the_window_and_short_fields_are_short(drawn):
    app, _p, size = drawn
    app.model.use_simulation = True
    app.model.compute()
    painter = draw(app, size)
    report = app.item_rects["report"]
    assert report[1] + report[3] <= size[1] + 0.5 and report[0] + report[2] <= size[0] + 0.5
    fields = app.gs_gui.form_state.rects
    for name in ("sim_seed", "sim_n_bursts", "n_states", "max_iterations"):
        assert fields[name][2] <= 140, (name, fields[name])
    assert_icons_clear(painter)
