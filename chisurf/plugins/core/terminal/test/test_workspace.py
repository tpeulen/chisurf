"""The terminal workspace: panes like tmux, driven without processes.

:class:`~chisurf.plugins.core.terminal.workspace.TerminalWorkspace` owns the
panes and their layout; the app draws a toolbar plus the workspace's dock
regions. These tests drive it with fake sessions through emtk's
:class:`~emtk.testing.Driver`, the way the shell-parity tests drive the shell.
"""

from __future__ import annotations

import pytest
from emtk.events import CONTROL_MODIFIER
from emtk.keys import KEY_TAB
from emtk.testing import Driver

pytest.importorskip("emtk")

from chisurf.plugins.core.terminal.screen import TerminalScreen
from chisurf.plugins.core.terminal.workspace import TerminalWorkspace


class FakeSession:
    """The engine seam, fake: a screen and a record of writes."""

    def __init__(self, columns=80, rows=24):
        self.screen = TerminalScreen(columns, rows)
        self.written: list[bytes] = []
        self.resized: list[tuple[int, int]] = []
        self.alive = True

    def write(self, data):
        self.written.append(bytes(data))

    def resize(self, columns, rows):
        self.resized.append((int(columns), int(rows)))
        self.screen.resize(columns, rows)

    def close(self):
        self.alive = False


@pytest.fixture
def ws():
    work = TerminalWorkspace(session_factory=FakeSession)
    work.new_pane()
    return work


def make(size=(640, 400)):
    from chisurf.plugins.core.terminal.app import TerminalApp

    app = TerminalApp(session_factory=FakeSession)
    driver = Driver(app, size)
    return app, driver


# ── panes ────────────────────────────────────────────────────────────────


def test_first_pane_starts_in_the_root_region(ws):
    assert len(ws.panes) == 1
    assert ws.docks.region_of("term.1") == "root"
    assert ws.active_key == "term.1"


def test_new_pane_tabs_into_the_active_region(ws):
    second = ws.new_pane()
    assert len(ws.panes) == 2
    assert ws.docks.region_of(second.key) == ws.docks.region_of("term.1")
    assert ws.active_key == second.key  # the new pane takes focus


def test_split_right_makes_two_regions(ws):
    ws.split_active("right")
    keys = list(ws.panes)
    regions = {ws.docks.region_of(key) for key in keys}
    assert len(regions) == 2  # side by side
    assert ws.active_key == keys[1]  # the new pane took focus


def test_split_down_stacks_regions(ws):
    ws.split_active("down")
    keys = list(ws.panes)
    regions = {ws.docks.region_of(key) for key in keys}
    assert len(regions) == 2


def test_close_active_removes_the_pane_and_prunes(ws):
    ws.new_pane()
    ws.close(ws.active_key)
    assert len(ws.panes) == 1
    assert ws.active_key is not None


def test_close_last_pane_makes_a_fresh_one(ws):
    ws.close(ws.active_key)
    assert len(ws.panes) == 0  # closed...
    # ...and the workspace reports it can open another
    assert ws.docks is not None


def test_close_kills_the_session(ws):
    key = ws.active_key
    session = ws.panes[key].session
    ws.close(key)
    assert not session.alive


def test_cycle_moves_focus(ws):
    first = ws.active_key
    second = ws.new_pane().key
    third = ws.new_pane().key
    assert ws.active_key == third
    ws.cycle()
    assert ws.active_key == first
    ws.cycle()
    assert ws.active_key == second


def test_titles_number_the_panes(ws):
    ws.new_pane()
    assert [ws.panes[k].title for k in ws.panes] == ["1", "2"]


# ── the app ──────────────────────────────────────────────────────────────


def test_app_draws_toolbar_and_first_pane():
    app, driver = make()
    driver.draw(2)
    assert set(app.item_rects) >= {"new", "split_right", "split_down", "close"}
    assert app.workspace.panes  # a pane exists


def test_new_button_adds_a_pane():
    app, driver = make()
    driver.draw(2)
    driver.click(app.item_rects["new"])
    driver.draw(1)
    assert len(app.workspace.panes) == 2


def test_split_right_button_splits():
    app, driver = make()
    driver.draw(2)
    driver.click(app.item_rects["split_right"])
    driver.draw(1)
    keys = list(app.workspace.panes)
    assert len({app.workspace.docks.region_of(k) for k in keys}) == 2


def test_split_down_button_splits():
    app, driver = make()
    driver.draw(2)
    driver.click(app.item_rects["split_down"])
    driver.draw(1)
    keys = list(app.workspace.panes)
    assert len({app.workspace.docks.region_of(k) for k in keys}) == 2


def test_close_button_closes_the_pane():
    app, driver = make()
    app.workspace.new_pane()
    driver.draw(2)
    driver.click(app.item_rects["close"])
    driver.draw(1)
    assert len(app.workspace.panes) == 1


def test_ctrl_tab_cycles_panes():
    app, driver = make()
    app.workspace.new_pane()
    app.workspace.new_pane()
    driver.draw(2)
    before = app.workspace.active_key
    driver.press(KEY_TAB, mods=CONTROL_MODIFIER)
    driver.draw(1)
    assert app.workspace.active_key != before


def test_typing_goes_to_the_active_pane():
    app, driver = make()
    driver.draw(2)
    pane = app.workspace.panes[app.workspace.active_key]
    driver.click((60, 200))  # into the terminal area: focus it
    driver.type("hi")
    assert b"".join(pane.session.written) == b"hi"


def test_output_sustains_frames():
    app, driver = make()
    driver.draw(2)
    pane = app.workspace.panes[app.workspace.active_key]
    assert app.animating() is False
    pane.session.screen.feed("more")
    assert app.animating() is True
    driver.draw(1)
    assert app.animating() is False


def test_close_top_pane_snaps_bottom_pane_up():
    app, driver = make()
    ws = app.workspace
    p1 = ws.active
    p2 = ws.split_active("down")
    assert p1 is not None and p2 is not None
    assert p1.key != p2.key
    layout_before, _ = ws.docks.compute_layout((0.0, 0.0, 800.0, 600.0))
    assert len(layout_before) == 2
    top_region = ws.docks.region_of(p1.key)
    bottom_region = ws.docks.region_of(p2.key)
    assert top_region is not None and bottom_region is not None
    assert top_region != bottom_region

    # Close top pane: bottom pane must snap up to take the full layout box
    ws.close(p1.key)
    layout_after, _ = ws.docks.compute_layout((0.0, 0.0, 800.0, 600.0))
    assert list(layout_after) == [bottom_region]
    assert layout_after[bottom_region] == (0.0, 0.0, 800.0, 600.0)
    assert ws.active_key == p2.key

    # Close the remaining pane: resets to a clean root region
    ws.close(p2.key)
    assert not ws.panes
    assert list(ws.docks.regions) == ["root"]

    # Reopening a pane opens in full-size root region
    p3 = ws.new_pane()
    assert ws.docks.region_of(p3.key) == "root"
    layout_reopen, _ = ws.docks.compute_layout((0.0, 0.0, 800.0, 600.0))
    assert layout_reopen == {"root": (0.0, 0.0, 800.0, 600.0)}

