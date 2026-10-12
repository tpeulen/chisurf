"""The Datasets dock gives its height to the datasets and fits tables, not to the status line.

Both tables declare ``"stretch": 1`` (``chisurf/emtk/views/datasets.view.json``): they share what the
dock has left after the Model choice, the button row and the one-line status, which emtk measures
(``emtk.layout.Fill``). Before, they had fixed heights (170 and 130 px), so a tall dock showed a
short table over a stretch of empty space, and a short one scrolled its buttons away.
"""

from __future__ import annotations

import pytest
from emtk.testing import Driver

from chisurf.emtk.fit_docks import DATASETS_KEY
from test.native_emtk.test_emtk_shell_fits import shell  # noqa: F401  (the fixture)

#: The dock's tab strip above its content, logical pixels.
TAB_STRIP = 22.0


def _dock(shell, size):  # noqa: F811
    driver = Driver(shell, size=size)
    shell.docks.focus(DATASETS_KEY)
    driver.frame(4)
    region = shell.docks.region_boxes[shell.docks.region_of(DATASETS_KEY)]
    rects = shell.item_rects
    return driver, region, rects


@pytest.mark.parametrize("size, share", [((1100, 720), 0.70), ((800, 600), 0.45)])
def test_the_tables_take_the_dock_and_the_status_one_line(shell, size, share):  # noqa: F811
    driver, (x, y, w, h), rects = _dock(shell, size)
    data, fits = rects["datasets.dataset_rows"], rects["datasets.fit_rows"]
    buttons = rects["datasets.remove_selected"]
    bottom = y + h
    content = h - TAB_STRIP
    tables = data[3] + fits[3]
    assert tables >= share * content, (tables, content)
    assert abs(data[3] - fits[3]) <= 1  # 1:1
    # Everything is inside the dock -- nothing scrolled away -- and what is left under the
    # buttons is the status line (one text line and its rule), not a slab of empty space.
    assert buttons[1] + buttons[3] <= bottom
    assert bottom - (buttons[1] + buttons[3]) <= 34, (buttons, bottom)


def test_the_layout_settles_and_stays(shell):  # noqa: F811
    driver, _, rects = _dock(shell, (1100, 720))
    first = {k: v for k, v in rects.items() if k.startswith("datasets.")}
    driver.frame(3)
    again = {k: v for k, v in shell.item_rects.items() if k.startswith("datasets.")}
    assert first == again
