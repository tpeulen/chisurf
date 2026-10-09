"""Layout of the Rotate/Translate window at 1200x800 and 800x600: what the screenshots showed, asserted on the recorded draw.

Defects fixed: the save icon touched its label, Stride sat below Save, the matrix and stride were as wide as the
window, the log filled the window.
"""

import pytest

from chisurf.plugins.traj.traj_rotate_translate.app import RotateTranslateApp
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
    app = RotateTranslateApp()
    painter = draw(app, request.param)
    yield app, painter, request.param
    app.close()


def test_stride_is_with_the_inputs_above_the_save_button(drawn):
    app, _p, _s = drawn
    assert_above(app.item_rects, "stride", "save")
    assert_above(app.item_rects, "translation", "stride")


def test_short_inputs_are_not_stretched_and_share_the_label_column(drawn):
    app, _p, _s = drawn
    assert_short(app.item_rects, ["stride"], limit=140)
    assert app.item_rects["rotation_matrix"][2] < 360 and app.item_rects["translation"][2] < 360
    assert_aligned(
        app.item_rects, ["trajectory", "topology", "rotation_matrix", "translation", "stride"]
    )


def test_the_log_is_capped_and_nothing_is_cut_or_overlapped(drawn):
    app, painter, size = drawn
    assert_log_capped(app.item_rects, size)
    assert_inside(app.item_rects, size)
    assert_texts_apart(painter)
    assert_icons_clear(painter)
    assert_disjoint(
        app.item_rects,
        [
            "guide",
            "help",
            "trajectory",
            "topology",
            "rotation_matrix",
            "translation",
            "stride",
            "save",
            "log",
        ],
    )
