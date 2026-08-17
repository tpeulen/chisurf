"""Tab completion in the viewport prompt, and the two docks that went away.

`CommandLine.complete()` had been written all along with **nothing calling it**:
`key()` did not handle Tab, and Tab would not have arrived anyway — Qt resolves
it in `QWidget.event` and moves the focus before any key handler sees it. So the
completion existed, was documented, and could not be reached.

The **Objects** and **Command** docks are deleted rather than ported: the object
list has been in the viewport's panel column all along, and the prompt is the
in-viewport command line. Two views of one thing that can disagree is worse than
one — and only one of them exists in a browser.
"""
from __future__ import annotations

import pytest

pytest.importorskip("qtpy")

from chimol.cmtk.keys import KEY_TAB  # noqa: E402
from chimol.cmtk.command_line import (  # noqa: E402
    CommandLine,
)


# --------------------------------------------------------------------------- #
# Completion
# --------------------------------------------------------------------------- #
def test_tab_completes_a_unique_prefix():
    line = CommandLine()
    line.completions = lambda _text, _cursor: ["distance"]
    line.set_focus(True)
    line.set_text("distanc")

    assert line.key(KEY_TAB, "", 0), "Tab was not consumed"
    assert line.text == "distance"
    assert line.cursor == len(line.text)


def test_tab_extends_to_the_common_prefix():
    line = CommandLine()
    line.completions = lambda _t, _c: ["colour_by", "colour_ramp"]
    line.set_focus(True)
    line.set_text("col")
    line.key(KEY_TAB, "", 0)
    assert line.text == "colour_"


def test_an_ambiguous_tab_lists_rather_than_doing_nothing(qapp):
    """A shell lists; silence reads as "there is no such command"."""
    line = CommandLine()
    line.completions = lambda _t, _c: ["dist", "disable", "delete"]
    line.set_focus(True)
    line.set_text("d")
    before = len(line.log)
    line.key(KEY_TAB, "", 0)
    assert len(line.log) > before


def test_tab_is_consumed_even_with_nothing_to_complete():
    """Otherwise it falls through and moves the focus out of the prompt."""
    line = CommandLine()
    line.set_focus(True)
    line.set_text("zzz")
    assert line.key(KEY_TAB, "", 0)


@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture(scope="module")
def window():
    from qtpy import QtWidgets

    from chimol.hosts.qt.window import MolViewPluginWindow

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    win = MolViewPluginWindow()
    win.resize(900, 640)
    win.show()
    for _ in range(6):
        app.processEvents()
    yield win
    win.close()


def test_the_prompt_has_a_completer(window):
    """It is the dispatcher the console used, so both complete identically."""
    gui = window.viewer.gui
    assert gui.command_line.completions is not None


def test_tab_completes_through_the_whole_path(window):
    gui = window.viewer.gui
    gui.command_line.visible = True
    gui.focus_command(True)
    gui.command_line.set_text("distanc")
    assert gui.key_press(KEY_TAB, "", 0)
    assert gui.command_line.text == "distance"
    gui.focus_command(False)


def test_the_widget_claims_tab_while_something_is_being_typed(window):
    """Qt gives Tab to focus navigation first; the widget has to take it back."""
    from qtpy import QtCore, QtGui

    gui = window.viewer.gui
    renderer = window.viewer.renderer
    gui.command_line.visible = True
    gui.focus_command(True)
    gui.command_line.set_text("zoo")

    event = QtGui.QKeyEvent(
        QtCore.QEvent.KeyPress, QtCore.Qt.Key_Tab, QtCore.Qt.NoModifier
    )
    assert renderer.event(event)
    assert event.isAccepted()
    assert gui.command_line.text.startswith("zoo")
    gui.focus_command(False)


# --------------------------------------------------------------------------- #
# The docks
# --------------------------------------------------------------------------- #
def test_the_3d_view_is_the_window(window):
    """No docks at all, and no dock area to hold one.

    Every panel that used to sit beside the viewport -- objects, the prompt,
    the hierarchy, the density controls, the menus, the toolbar -- is drawn
    *inside* it. A second widget would be a second copy of something already on
    screen, and one that no browser has.
    """
    from qtpy import QtWidgets

    assert window.dock_area is None
    assert window.centralWidget() is window.viewer
    assert not hasattr(window, "hierarchy"), "the Qt hierarchy dock came back"
    visible = [
        bar for bar in window.findChildren(QtWidgets.QToolBar) if bar.isVisible()
    ]
    assert visible == [], visible
    assert not window.menuBar().isVisible(), "the menus are drawn in the viewport"


def test_nothing_but_the_viewport_is_drawn_on_the_window(window):
    """A `QWidget` parented to the window that no layout owns is drawn at
    (0, 0), 100 x 30 -- a grey `Command line` box over the toolbar row.

    Four were stacked there once the dock area went (`Chinsole`, `VolumeDock`
    and two bare containers), all still constructed because a few call sites
    read them. Hiding is not enough for all of them, so the parent link is cut.

    The viewport is now the *only* one: the Qt status bar went the same way as
    the Qt menu bar, replaced by the chrome's own status line, which obeys
    `show_status` and exists in a browser host too.
    """
    from qtpy import QtWidgets

    drawn = [
        type(child).__name__
        for child in window.findChildren(QtWidgets.QWidget)
        if child.isVisible() and child.parentWidget() is window
    ]
    assert drawn == ["MolView"], drawn
    # Cut off the window, not deleted: the call sites that read them still work.
    assert window.command_panel is not None
    assert window.volume_panel is not None


def test_the_object_list_is_still_there_in_the_viewport(window):
    """Removing the dock must not remove the thing it duplicated."""
    window.sync_internal_gui()
    gui = window.viewer.gui
    names = [row.name for row in gui.rows]
    assert "all" in names and "sele" in names


def test_the_prompt_is_still_there(window):
    gui = window.viewer.gui
    assert gui.command_line.visible
