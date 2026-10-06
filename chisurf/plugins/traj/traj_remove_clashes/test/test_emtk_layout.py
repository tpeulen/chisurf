"""Layout of the Remove Clashed window at 1200x800 and 800x600: what the screenshots showed, asserted on the recorded draw.

Defects fixed: the save button above its inputs, stretched stride and distance, icon touching label, log filling the window.
"""

import pytest

from chisurf.plugins.traj.traj_remove_clashes.app import RemoveClashesApp
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
    app = RemoveClashesApp()
    painter = draw(app, request.param)
    yield app, painter, request.param
    app.close()


def test_the_action_comes_after_the_inputs_and_the_fields_are_short(drawn):
    app, _p, _s = drawn
    assert_above(app.item_rects, "min_distance", "save")
    assert_short(app.item_rects, ["stride", "min_distance"])
    assert_aligned(app.item_rects, ["trajectory", "atom_selection", "stride", "min_distance"])


def test_log_icons_and_texts(drawn):
    app, painter, size = drawn
    assert_log_capped(app.item_rects, size)
    assert_inside(app.item_rects, size)
    assert_texts_apart(painter)
    assert_icons_clear(painter)
