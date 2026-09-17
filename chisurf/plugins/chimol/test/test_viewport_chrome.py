"""What the window shows before you touch anything.

PyMOL's layout is not decoration: the molecule owns the window, a prompt and a
line of feedback are always on screen (`internal_prompt`/`internal_feedback`,
both default on), and the movie panel has *zero* height until there is a movie
(``MovieGetPanelHeight``, ``layer1/Movie.cpp``). Ours differed on all three: a
single-state PDB got a full-width scrubber and a nine-button transport for a
timeline of one, the command console was a background tab in a side stack, and
that side stack held a third of the window showing a filter box and white space.

Guarded here, because none of it is visible to a construction test:

* the movie panel appears with a movie and not before;
* the side panels start hidden, and reveal themselves when they have content;
* the command console is in the layout, not behind a tab;
* the View menu's sequence toggle drives the strip that exists.
"""

from __future__ import annotations

import pathlib
import shutil

import pytest

pytest.importorskip("qtpy")

from chimol.hosts.qt.window import _INITIALLY_HIDDEN_DOCKS
from chimol.ui.gui import InternalGui


# --------------------------------------------------------------------------- #
# The movie panel
# --------------------------------------------------------------------------- #
def test_no_movie_no_movie_panel():
    """PyMOL's rule: zero height unless a movie or more than one frame."""
    gui = InternalGui()
    gui.state = (1, 1)
    assert gui.movie_panel_visible is False


def test_a_second_frame_brings_the_panel():
    gui = InternalGui()
    gui.state = (1, 2)
    assert gui.movie_panel_visible is True


def test_the_transport_is_laid_out_only_when_it_is_shown():
    """Layout, paint and hit-testing all read the one property.

    An empty rect fails ``contains``, so a click where the transport *used* to
    be falls through to the block instead of running a movie command.
    """
    gui = InternalGui()
    gui.visible = True

    gui.state = (1, 1)
    gui.layout_block(1000, 800)
    assert gui._movie_rects == []
    assert gui._timeline_track.w == 0
    quiet_height = gui.block_rect.h

    gui.state = (1, 40)
    gui.layout_block(1000, 800)
    assert len(gui._movie_rects) > 0
    assert gui._timeline_track.w > 0
    # The block grows by exactly the rows the transport needs.
    assert gui.block_rect.h > quiet_height


def test_a_click_where_the_transport_would_be_does_not_run_a_movie_command():
    gui = InternalGui()
    gui.visible = True
    gui.state = (1, 40)
    gui.layout_block(1000, 800)
    rect = gui._movie_rects[0][0]
    x, y = rect.x + rect.w / 2, rect.y + rect.h / 2
    assert gui.hit_test(x, y).kind == "movie"

    gui.state = (1, 1)
    gui.layout_block(1000, 800)
    assert gui.hit_test(x, y).kind != "movie"


# --------------------------------------------------------------------------- #
# The window layout
# --------------------------------------------------------------------------- #
@pytest.fixture
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    from chimol.hosts.qt.window import MolViewPluginWindow

    src = (
        pathlib.Path(__file__).resolve().parents[4]
        / "test"
        / "data"
        / "atomic_coordinates"
        / "pdb_files"
        / "148l.pdb"
    )
    pdb = tmp_path / "148l.pdb"
    shutil.copyfile(src, pdb)

    win = MolViewPluginWindow()
    win.load_structure_from_path(pdb, name="148l")
    return win


def _tab_names(window) -> dict[str, int]:
    area = window.dock_area
    return {area.tabText(i): i for i in range(area.count())}


def _is_hidden(window, name: str) -> bool:
    """Whether the dock called *name* is one the area is holding out of sight."""
    area = window.dock_area
    index = _tab_names(window)[name]
    return area.widget(index) in area._hidden_widgets


def test_an_ordinary_structure_gets_the_window(window):
    """The side panels have nothing to show, so they do not take the space.

    They are hidden, not removed: the View menu and a right-click on a tab
    bring them back, and a layout that *deleted* them could not.
    """
    if window.dock_area is None:
        pytest.skip("no dock area in this build")
    names = _tab_names(window)
    for name in _INITIALLY_HIDDEN_DOCKS:
        assert name in names, f"{name} was removed rather than hidden"
        assert _is_hidden(window, name), f"{name} is showing"


def test_the_command_console_is_not_behind_a_tab(window):
    """PyMOL always shows a prompt; typing commands *is* the interface."""
    if window.dock_area is None:
        pytest.skip("no dock area in this build")
    assert "Command" in _tab_names(window)
    assert not _is_hidden(window, "Command")


def test_the_console_runs_what_is_typed_and_shows_the_answer(window, qapp):
    from qtpy import QtCore, QtTest

    window.resize(1200, 800)
    window.show()
    for _ in range(10):
        qapp.processEvents()

    line = window.command_panel.input_line
    line.setText("count_atoms polymer")
    QtTest.QTest.keyClick(line, QtCore.Qt.Key_Return)
    for _ in range(10):
        qapp.processEvents()

    text = window.command_panel.view.toPlainText()
    assert "> count_atoms polymer" in text, text
    assert "1314" in text, text
    assert line.text() == "", "the prompt kept the command after running it"


def test_the_sequence_toggle_drives_the_strip_that_exists(window):
    """It used to toggle a dock retired when the strip moved into the viewport.

    ``_set_tab_visible`` looped over every tab, matched the name "Sequence"
    against none of them, and returned -- so the menu entry ticked and unticked
    and nothing moved.
    """
    from chimol.core.settings.registry import get_setting

    window._set_sequence_visible(False)
    assert bool(get_setting("seq_view")) is False
    window._set_sequence_visible(True)
    assert bool(get_setting("seq_view")) is True


def test_a_menu_entry_that_needs_a_value_reaches_the_command_line(window, qapp):
    """It used to be skipped: clicked, and nothing happened at all.

    The in-viewport panel has nowhere to type, so ``_emit`` dropped every
    template carrying ``{text}`` -- which is a menu entry that does nothing, in
    the panel that is now the primary one. The command line is one row below it,
    so the entry goes *there*, with the placeholder selected.
    """
    from chimol.ui.menus.objects import MenuEntry

    window.resize(1200, 800)
    window.show()
    for _ in range(10):
        qapp.processEvents()

    gui = window.viewer.gui
    gui.on_prompt_command = window._prefill_command_line
    gui._emit(
        "group {text}, {sele}",
        "lig",
        prompt=MenuEntry("x", prompt=("Move to group", "Group name:")).prompt,
    )
    for _ in range(5):
        qapp.processEvents()

    line = window.command_panel.input_line
    assert line.text() == "group <group name>, lig", line.text()
    assert line.selectedText() == "<group name>", (
        "the placeholder is not selected, so typing appends instead of replacing"
    )


def test_a_menu_entry_naming_a_file_opens_the_host_dialog(window, qapp):
    """``Save Molecule As...`` clicked in the viewport bar must open a dialog.

    The viewport menu bar is the one the user sees -- the Qt bar is hidden --
    and its ``{text}`` path used to feed *every* prompted entry into the
    command line, ``file_prompt`` or not. A filename typed blind lands
    wherever the process is running, which for a menu action is nowhere the
    user chose.
    """
    window.resize(1200, 800)
    window.show()
    for _ in range(10):
        qapp.processEvents()

    gui = window.viewer.gui
    assert gui.on_file_prompt is not None, "the app did not wire the file-dialog hook"

    asked: list[tuple[str, str, str, str]] = []
    gui.on_file_prompt = lambda line, mode, title, filt: asked.append((line, mode, title, filt))
    ran: list[str] = []
    gui.set_run_command(ran.append)
    gui._emit(
        "save {text}",
        "",
        file_prompt=("save", "Save molecule", "Structures (*.pdb)"),
    )
    assert asked == [("save {text}", "save", "Save molecule", "Structures (*.pdb)")]
    assert ran == [], "the template must not run before the dialog fills it"


def test_without_a_dialog_a_file_entry_falls_back_to_the_command_line(window, qapp):
    """In the browser there is no dialog; the CLI placeholder is the fallback."""
    window.resize(1200, 800)
    window.show()
    for _ in range(10):
        qapp.processEvents()

    gui = window.viewer.gui
    gui.on_file_prompt = None
    gui.on_prompt_command = window._prefill_command_line
    gui._emit(
        "save {text}",
        "",
        prompt=("Save", "File name:"),
        file_prompt=("save", "Save molecule", "Structures (*.pdb)"),
    )
    for _ in range(5):
        qapp.processEvents()

    line = window.command_panel.input_line
    assert line.text() == "save <file name>", line.text()


def test_an_ordinary_menu_entry_still_runs(window, qapp):
    """The prompt path must not swallow the commands that need no value."""
    window.resize(1200, 800)
    window.show()
    for _ in range(10):
        qapp.processEvents()

    gui = window.viewer.gui
    ran: list[str] = []
    gui.set_run_command(ran.append)
    gui._emit("zoom {sele}", "148l")
    assert ran == ["zoom 148l"]
