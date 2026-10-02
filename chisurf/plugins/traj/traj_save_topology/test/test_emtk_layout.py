"""Layout of the Save Topology window at 1200x800 and 800x600: what the screenshots showed, asserted on the recorded draw.

Defects fixed: icon touching label, log filling the window.
"""

import pytest

from test.gui.emtk_layout_checks import (
    SIZES, assert_above, assert_aligned, assert_disjoint, assert_icons_clear, assert_inside, assert_log_capped,
    assert_short, assert_texts_apart, draw,
)

from chisurf.plugins.traj.traj_save_topology.app import SaveTopologyApp


@pytest.fixture(params=SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def drawn(request):
    app = SaveTopologyApp()
    painter = draw(app, request.param)
    yield app, painter, request.param
    app.close()


def test_log_icons_and_texts(drawn):
    app, painter, size = drawn
    assert_above(app.item_rects, "topology", "save")
    assert_log_capped(app.item_rects, size)
    assert_inside(app.item_rects, size)
    assert_texts_apart(painter)
    assert_icons_clear(painter)

