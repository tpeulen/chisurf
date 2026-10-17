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
from emtk.keys import KEY_TAB
from emtk.widgets.command_line import CommandLine


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


def test_an_ambiguous_tab_lists_rather_than_doing_nothing():
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


@pytest.fixture(scope="module")
def window():
    from native_window import NativeWindow

    win = NativeWindow(size=(900, 640))
    win.pump(3)
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
    """A host may give Tab to focus navigation first; the viewport takes it back.

    Through the renderer's key handler, which is where every host's canvas
    delivers a key.
    """
    gui = window.viewer.gui
    renderer = window.viewer.renderer
    gui.command_line.visible = True
    gui.focus_command(True)
    gui.command_line.set_text("zoo")

    assert renderer.on_key_press(KEY_TAB, "", 0), "Tab was not consumed"
    assert gui.command_line.text.startswith("zoo")
    gui.focus_command(False)


# --------------------------------------------------------------------------- #
# The docks
# --------------------------------------------------------------------------- #
def test_the_3d_view_is_the_window(window):
    """No docks at all, and no toolkit widget to hold one.

    Every panel that used to sit beside the viewport -- objects, the prompt,
    the hierarchy, the density controls, the menus, the toolbar -- is drawn
    *inside* it. A second widget would be a second copy of something already on
    screen, and one that no browser has.
    """
    viewer = window.viewer
    assert viewer.uses_toolkit is False
    assert viewer.view is None, "a toolkit widget came back"
    assert not hasattr(window, "hierarchy"), "a hierarchy dock came back"
    gui = viewer.gui
    assert gui.menubar, "the menus are drawn in the viewport"
    assert gui.toolbar, "the toolbar is drawn in the viewport"


def test_nothing_but_the_viewport_is_drawn_on_the_window(window):
    """The chrome is the renderer's own: one canvas, one painter.

    In the Qt window stray child widgets (a grey `Command line` box, the
    status bar, the menu bar) were drawn beside the viewport; here there is one
    surface, and the prompt, the status line and the panels are all drawn by
    the chrome that renderer owns.
    """
    renderer = window.viewer.renderer
    assert renderer._internal_gui is window.viewer.gui
    frame = window.grab()
    assert frame is not None and frame.shape[:2] == (window.size[1], window.size[0])


def test_the_object_list_is_still_there_in_the_viewport(window):
    """Removing the dock must not remove the thing it duplicated."""
    window.refresh_objects()
    gui = window.viewer.gui
    names = [row.name for row in gui.rows]
    assert "all" in names and "sele" in names


def test_the_prompt_is_still_there(window):
    gui = window.viewer.gui
    assert gui.command_line.visible
