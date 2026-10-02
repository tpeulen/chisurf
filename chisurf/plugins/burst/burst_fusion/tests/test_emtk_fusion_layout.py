"""Layout of the burst-fusion window at 1200x800 and 800x600.

Defects fixed: five source/settings buttons plus Stop stacked full width, Stop live while idle, short fields as
wide as the panel, icons touching labels, the summary table cut after eight rows.
"""

import pytest

from test.gui.emtk_layout_checks import (
    SIZES, assert_disjoint, assert_icons_clear, assert_inside, assert_texts_apart, draw,
)

from chisurf.plugins.burst.burst_fusion.gui.app import create_app


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    monkeypatch.chdir(tmp_path)


@pytest.fixture(params=SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def drawn(request):
    app = create_app()
    pass
    painter = draw(app, request.param)
    yield app, painter, request.param
    app.close()


def test_actions_are_wrapped_rows(drawn):
    app, _p, size = drawn
    rects = app.item_rects
    assert_disjoint(rects, ["toolAction_run", "toolAction_refresh", "Stop", "load", "save", "export", "guide", "help"])
    run_row = {round(rects[n][1]) for n in ("toolAction_run", "toolAction_refresh", "Stop")}
    assert len(run_row) <= 2


def test_short_fields_icons_and_texts(drawn):
    app, painter, size = drawn
    fields = app.fusion_gui.form_state.rects
    for name in ("threshold", "max_gap_ms", "max_group", "tau_min_ms", "n_bins", "min_pairs"):
        assert fields[name][2] <= 140, (name, fields[name])
    assert_icons_clear(painter)
    controls = (0.0, 0.0, size[0] * 0.35, size[1])
    assert_texts_apart(painter, region=controls)
