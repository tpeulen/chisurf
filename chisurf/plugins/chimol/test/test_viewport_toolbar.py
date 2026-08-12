"""The toolbar, migrated from Qt into the 3-D view.

The Qt row's buttons were wired to Qt **slots**, so the toolbar worked only on
the desktop and taught nobody the command behind it. Every button here is a
command, which is what lets the same row serve the browser and what makes each
press echo at the prompt like a typed one.

Two commands had to exist for that: `toggle_rep` (a button that only ever
*shows* is a button you press once — the Qt widget was checkable, which is
exactly the coupling being removed) and `info_panel`.
"""
from __future__ import annotations

import pytest

pytest.importorskip("qtpy")

from chisurf.plugins.chimol.chimol.app.menu_bar import TOOLBAR  # noqa: E402
from chisurf.plugins.chimol.chimol.renderer.internal_gui import (  # noqa: E402
    InternalGui,
    SequenceRow,
)

SIZE = (900, 640)


@pytest.fixture
def gui():
    ran: list[str] = []
    panel = InternalGui(run_command=ran.append)
    panel.toolbar = list(TOOLBAR)
    panel.menubar = [("File", ())]          # a bar with no entries: height only
    panel.sequence_visible = True
    panel.sequences = [
        SequenceRow(name="148l/E", codes="MNIFEMLRIDEGLRL", object_id="o1",
                    chain="E", numbers=list(range(1, 16)),
                    residue_indices=list(range(15)))
    ]
    panel.layout(*SIZE)
    panel.ran = ran
    return panel


def _button(gui, label):
    for rect, name, command, _note in gui._toolbar_rects:
        if name == label:
            return rect, command
    raise AssertionError(f"no {label!r} button")


def test_every_button_is_laid_out(gui):
    drawn = [label for _r, label, _c, _n in gui._toolbar_rects]
    assert drawn == [label for label, _c, _n in TOOLBAR]


def test_the_buttons_do_not_overlap(gui):
    rects = [rect for rect, *_rest in gui._toolbar_rects]
    for left, right in zip(rects, rects[1:]):
        assert left.x + left.w <= right.x + 0.5


def test_a_button_is_reachable_and_runs_its_command(gui):
    rect, command = _button(gui, "Surf")
    hit = gui.hit_test(rect.x + rect.w / 2, rect.y + rect.h / 2)
    assert hit.kind == "toolbar"

    assert gui.mouse_press(rect.x + rect.w / 2, rect.y + rect.h / 2)
    assert gui.ran == [command]


def test_every_button_carries_a_command(gui):
    """A drawn button with nothing behind it is worse than no button."""
    for _rect, label, command, _note in gui._toolbar_rects:
        assert command, f"{label} runs nothing"


def test_the_toolbar_takes_a_band_and_the_strip_stacks_under_it(gui):
    """The strip's rows were placed from an absolute origin and drew over it."""
    assert gui.toolbar_height() > 0
    assert gui.top_band_height() == (
        gui.menubar_height() + gui.toolbar_height() + gui.sequence_height()
    )
    assert gui._seq_strip.y >= gui.menubar_height() + gui.toolbar_height()
    for rect in gui._seq_rows:
        assert rect.y >= gui._seq_strip.y, "a sequence row is above its strip"


def test_no_toolbar_when_the_host_supplies_none():
    bare = InternalGui()
    bare.layout(*SIZE)
    assert bare.toolbar_height() == 0
    assert bare.hit_test(20, 25).kind != "toolbar"


# --------------------------------------------------------------------------- #
# The commands the buttons needed
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def window():
    import pathlib

    from qtpy import QtWidgets

    from chisurf.plugins.chimol.chimol.app.molview_main_window import (
        MolViewPluginWindow,
    )
    from chisurf.plugins.chimol.chimol.cmd import cmd as shared

    pdb = (
        pathlib.Path(__file__).resolve().parents[4]
        / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
    )
    if not pdb.is_file():
        pytest.skip(f"missing fixture {pdb}")

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    win = MolViewPluginWindow()
    win.resize(*SIZE)
    win.show()
    for _ in range(5):
        app.processEvents()
    shared.set_window(win)
    shared.set_message_callback(lambda _m: None)
    shared.set_error_callback(lambda _m: None)
    win._run_object_menu_command(f"load {pdb}")
    for _ in range(3):
        app.processEvents()
    yield win
    win.close()


def test_toggle_rep_flips_rather_than_only_showing(window):
    viewer = window.viewer
    before = bool(viewer._surface_visible)
    window._run_object_menu_command("toggle_rep surface")
    assert bool(viewer._surface_visible) is not before
    window._run_object_menu_command("toggle_rep surface")
    assert bool(viewer._surface_visible) is before


def test_toggle_rep_refuses_an_unknown_representation(window):
    from chisurf.plugins.chimol.chimol.cmd import cmd as shared

    errors: list[str] = []
    shared.set_error_callback(errors.append)
    try:
        window._run_object_menu_command("toggle_rep hologram")
        assert errors and "unknown representation" in errors[-1]
    finally:
        shared.set_error_callback(lambda _m: None)


def test_info_panel_toggles_and_can_be_set(window):
    viewer = window.viewer
    window._run_object_menu_command("info_panel on")
    assert viewer._info_visible
    window._run_object_menu_command("info_panel toggle")
    assert not viewer._info_visible
    window._run_object_menu_command("info_panel off")
    assert not viewer._info_visible


def test_the_window_hands_the_toolbar_to_the_chrome(window):
    gui = window.viewer._renderer._internal_gui
    assert [label for label, _c, _n in gui.toolbar] == [
        label for label, _c, _n in TOOLBAR
    ]
