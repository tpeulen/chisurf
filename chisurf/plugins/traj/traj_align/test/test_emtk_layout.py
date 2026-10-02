"""Layout of the Align window at 1200x800 and 800x600: what the screenshots showed, asserted on the recorded draw.

Defects fixed: the save button above the inputs it acts on, stretched atom selection and stride, icon touching label, log filling the window.
"""

import pytest

from test.gui.emtk_layout_checks import (
    SIZES, assert_above, assert_aligned, assert_disjoint, assert_icons_clear, assert_inside, assert_log_capped,
    assert_short, assert_texts_apart, draw,
)

from chisurf.plugins.traj.traj_align.app import AlignTrajectoryApp


@pytest.fixture(params=SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def drawn(request):
    app = AlignTrajectoryApp()
    painter = draw(app, request.param)
    yield app, painter, request.param
    app.close()


def test_the_action_comes_after_the_inputs_and_the_fields_are_short(drawn):
    app, _p, size = drawn
    assert_above(app.item_rects, "atom_selection", "save")
    assert_above(app.item_rects, "stride", "save")
    assert_short(app.item_rects, ["stride"])
    assert app.item_rects["atom_selection"][2] <= 330
    assert_aligned(app.item_rects, ["trajectory", "atom_selection", "stride"])


def test_log_icons_and_texts(drawn):
    app, painter, size = drawn
    assert_log_capped(app.item_rects, size)
    assert_inside(app.item_rects, size)
    assert_texts_apart(painter)
    assert_icons_clear(painter)

