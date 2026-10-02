"""Layout of the Trajectory to FRET window at 1200x800 and 800x600: what the screenshots showed, asserted on the recorded draw.

Defects fixed: stretched stride and parameters, label columns that differed per panel, log filling the window.
"""

import pytest

from test.gui.emtk_layout_checks import (
    SIZES, assert_above, assert_aligned, assert_disjoint, assert_icons_clear, assert_inside, assert_log_capped,
    assert_short, assert_texts_apart, draw,
)

from chisurf.plugins.traj.fret_trajectory.app import FretTrajectoryApp


@pytest.fixture(params=SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def drawn(request):
    app = FretTrajectoryApp()
    painter = draw(app, request.param)
    yield app, painter, request.param
    app.close()


def test_short_fields_and_one_label_column(drawn):
    app, _p, _s = drawn
    assert_short(app.item_rects, ["stride", "forster_radius", "tau0", "t_step"])
    assert_aligned(app.item_rects, ["trajectory", "stride", "forster_radius", "tau0", "t_step", "dipoles"])


def test_log_and_texts(drawn):
    app, painter, size = drawn
    assert_above(app.item_rects, "dipoles", "process")
    assert_log_capped(app.item_rects, size)
    assert_inside(app.item_rects, size)
    assert_texts_apart(painter)

