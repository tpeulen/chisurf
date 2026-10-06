"""Layout of the Join window at 1200x800 and 800x600: what the screenshots showed, asserted on the recorded draw.

Defects fixed: the save button between the file rows and the options, stretched chunk size, icon touching label, log filling the window.
"""

import pytest

from chisurf.plugins.traj.traj_join.app import JoinTrajectoriesApp
from test.gui.emtk_layout_checks import (
    SIZES,
    assert_above,
    assert_aligned,
    assert_disjoint,
    assert_icons_clear,
    assert_inside,
    assert_log_capped,
    assert_short,
    assert_texts_apart,
    draw,
)


@pytest.fixture(params=SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def drawn(request):
    app = JoinTrajectoriesApp()
    painter = draw(app, request.param)
    yield app, painter, request.param
    app.close()


def test_the_action_comes_after_the_options_and_the_field_is_short(drawn):
    app, _p, _s = drawn
    assert_above(app.item_rects, "join_mode", "save")
    assert_above(app.item_rects, "chunk_size", "save")
    assert_short(app.item_rects, ["chunk_size"])
    assert_aligned(
        app.item_rects,
        ["trajectory_1", "trajectory_2", "topology", "join_mode.0", "reverse_traj_1", "chunk_size"],
    )


def test_log_icons_and_texts(drawn):
    app, painter, size = drawn
    assert_log_capped(app.item_rects, size)
    assert_inside(app.item_rects, size)
    assert_texts_apart(painter)
    assert_icons_clear(painter)
