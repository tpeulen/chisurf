"""Layout of the BVA window at 1200x800 and 800x600.

Defects fixed: Run/Restart/Stop/Folder/Guide wrapped one orphan ("Help") onto its own line and a second row of
three more buttons followed, Stop was live while idle, icons touched their labels.
"""

import pytest

from test.gui.emtk_layout_checks import (
    SIZES, assert_disjoint, assert_icons_clear, assert_inside, assert_texts_apart, draw,
)

from chisurf.plugins.burst.burst_bva.gui.app import create_app


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


def test_actions_are_two_rows_with_no_orphan(drawn):
    app, _p, size = drawn
    rects = app.item_rects
    first = ["run", "restart", "stop", "folder"]
    second = ["clear", "save_plot", "save_defaults"]
    third = ["guide", "help"]
    assert_disjoint(rects, first + second + third)
    for row in (first, second, third):
        assert len({round(rects[n][1]) for n in row}) == 1, f"{row} wrap apart"
    assert rects["run"][1] < rects["clear"][1] < rects["guide"][1]


def test_icons_and_texts(drawn):
    app, painter, size = drawn
    assert_icons_clear(painter)
    assert_inside(app.item_rects, size, names=["run", "restart", "stop", "folder", "clear", "guide", "help"])
    assert_texts_apart(painter, region=(0.0, 0.0, 330.0, size[1]))
