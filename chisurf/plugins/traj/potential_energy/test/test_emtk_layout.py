"""Layout of the Potential energy window at 1200x800 and 800x600: what the screenshots showed, asserted on the recorded draw.

Defects fixed: a full-width Add button and choice, stretched cutoffs, weight and stride, labels in three different columns, log filling the window.
"""

import pytest

from test.gui.emtk_layout_checks import (
    SIZES, assert_above, assert_aligned, assert_disjoint, assert_icons_clear, assert_inside, assert_log_capped,
    assert_short, assert_texts_apart, draw,
)

from chisurf.plugins.traj.potential_energy.app import PotentialEnergyApp


@pytest.fixture(params=SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def drawn(request):
    app = PotentialEnergyApp()
    painter = draw(app, request.param)
    yield app, painter, request.param
    app.close()


def test_editor_fields_are_short_and_share_one_label_column(drawn):
    app, _p, _s = drawn
    assert_short(app.item_rects, ["cutoff_ca", "cutoff_hbond", "potential_weight", "stride"])
    assert app.item_rects["add"][2] <= 180 and app.item_rects["potential_type"][2] <= 180
    assert_aligned(app.item_rects, ["trajectory", "potential_type", "add", "cutoff_ca", "potential", "potential_weight",
                                    "stride"])


def test_log_and_texts(drawn):
    app, painter, size = drawn
    assert_above(app.item_rects, "added_potentials", "process")
    assert_log_capped(app.item_rects, size)
    assert_inside(app.item_rects, size)
    assert_texts_apart(painter)

