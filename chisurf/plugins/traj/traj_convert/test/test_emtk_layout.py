"""Layout of the Trajectory converter window at 1200x800 and 800x600: what the screenshots showed, asserted on the recorded draw.

Defects fixed: stretched frame range, filename and format, one label column across both panels, log filling the window.
"""

import pytest

from chisurf.plugins.traj.traj_convert.app import MDConverterApp
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
    app = MDConverterApp()
    painter = draw(app, request.param)
    yield app, painter, request.param
    app.close()


def test_short_fields_and_one_label_column(drawn):
    app, _p, _s = drawn
    assert_short(app.item_rects, ["first_frame", "last_frame", "stride"], limit=200)
    assert app.item_rects["filename"][2] <= 330 and app.item_rects["ending"][2] <= 240
    assert_aligned(app.item_rects, ["topology", "first_frame", "filename", "ending", "split"])


def test_log_icons_and_texts(drawn):
    app, painter, size = drawn
    assert_above(app.item_rects, "split", "convert")
    assert_log_capped(app.item_rects, size)
    assert_inside(app.item_rects, size)
    assert_texts_apart(painter)
