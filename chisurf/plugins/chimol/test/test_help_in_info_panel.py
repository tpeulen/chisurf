"""`help` answers in the info panel, and the panel scrolls.

It went to the prompt's feedback line, which shows **one line**. The command
list is over a hundred names and a docstring is several paragraphs, so the
answer scrolled straight past and `help` was, in practice, unreadable.

The panel holds it. It also had to learn to scroll: a panel that silently shows
the first fifteen lines of an answer is worse than one that says nothing.
"""
from __future__ import annotations

import pathlib

import pytest

pytest.importorskip("qtpy")

PDB = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
)


@pytest.fixture(scope="module")
def session():
    from qtpy import QtWidgets

    from chimol.hosts.qt.window import MolViewPluginWindow
    from chimol.commands import cmd as shared

    if not PDB.is_file():
        pytest.skip(f"missing fixture {PDB}")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    win = MolViewPluginWindow()
    win.resize(900, 640)
    win.show()
    for _ in range(5):
        app.processEvents()
    shared.set_window(win)
    shared.set_message_callback(lambda _m: None)
    shared.set_error_callback(lambda _m: None)
    win._run_object_menu_command(f"load {PDB}")
    for _ in range(3):
        app.processEvents()
    yield win, app
    win.close()


def _laid_out(win):
    from chimol.hosts.qt.overlay import refresh_gui_state

    gui = win.viewer._renderer._internal_gui
    refresh_gui_state(gui, win.viewer)
    gui.layout(900, 640)
    return gui


def test_help_opens_the_info_panel_and_fills_it(session):
    win, _app = session
    win.viewer.set_system_info_visible(False)
    win._run_object_menu_command("help")

    assert win.viewer._info_visible, "help did not open the panel"
    gui = _laid_out(win)
    assert gui._info_lines
    assert gui._info_lines[0].startswith("Commands ("), gui._info_lines[0]


def test_help_still_returns_its_text(session):
    """A script and the console read the return value; the panel is extra."""
    from chimol.commands import cmd as shared

    win, _app = session
    text = shared.help("distance")
    assert "distance" in text
    assert win.viewer._info_text == text


def test_the_answer_is_longer_than_the_panel(session):
    """Which is why it has to scroll -- pinned so the premise stays true."""
    win, _app = session
    win._run_object_menu_command("help")
    gui = _laid_out(win)
    assert len(gui._info_lines) > gui.info_visible_rows()
    assert gui.info_max_scroll() > 0


def test_the_wheel_scrolls_it_and_stops_at_the_end(session):
    win, _app = session
    win._run_object_menu_command("help")
    gui = _laid_out(win)
    rect = gui._info_rect
    centre = (rect.x + rect.w / 2, rect.y + rect.h / 2)

    assert gui._info_scroll == 0
    assert gui.scroll_menu(*centre, -3)
    assert gui._info_scroll == 3

    gui.scroll_menu(*centre, -9999)
    assert gui._info_scroll == gui.info_max_scroll()
    assert not gui.scroll_menu(*centre, -1), "it scrolled past the end"

    gui.scroll_menu(*centre, 9999)
    assert gui._info_scroll == 0
    assert not gui.scroll_menu(*centre, 1), "it scrolled above the top"


def test_the_wheel_outside_the_panel_is_left_alone(session):
    """Otherwise the panel eats the zoom."""
    win, _app = session
    win._run_object_menu_command("help")
    gui = _laid_out(win)
    rect = gui._info_rect
    assert not gui.scroll_info(rect.x + rect.w + 50, rect.y + rect.h / 2, -3)


def test_a_new_answer_starts_at_the_top(session):
    """A position carried over from the last answer lands mid-paragraph."""
    win, _app = session
    win._run_object_menu_command("help")
    gui = _laid_out(win)
    rect = gui._info_rect
    gui.scroll_menu(rect.x + rect.w / 2, rect.y + rect.h / 2, -5)
    assert gui._info_scroll > 0

    win._run_object_menu_command("help zoom")
    gui = _laid_out(win)
    assert gui._info_scroll == 0


def test_unknown_command_help_says_so_in_the_panel(session):
    win, _app = session
    win._run_object_menu_command("help nonesuch")
    gui = _laid_out(win)
    assert any("unknown command" in line for line in gui._info_lines)


# --------------------------------------------------------------------------- #
# `help settings`, and saying that the panel scrolls
# --------------------------------------------------------------------------- #
def test_help_setting_goes_to_the_panel_too(session):
    """92 names do not fit the prompt's one-line feedback strip."""
    from chimol.commands import cmd

    from chimol.hosts.qt import overlay as qt_overlay

    window, _app = session
    cmd.set_window(window)
    text = cmd.help_setting()

    gui = window.viewer._renderer._internal_gui
    # The panel's text is *pulled* by the chrome sync, which runs on a paint --
    # `layout()` alone leaves `info_text` empty and the panel looks broken.
    qt_overlay.paint_chrome(gui, window.viewer, 1000, 700)
    assert window.viewer._info_visible
    assert len(gui._info_lines) > 10, gui._info_lines
    assert "Settings" in gui._info_lines[0]
    assert "ambient" in text


def test_the_panel_draws_a_scroll_bar_when_it_overflows(session):
    """It scrolled on the wheel and said nothing: a page that ends
    mid-sentence reads as truncated rather than scrolled."""
    from chimol.hosts.qt import overlay as qt_overlay

    window, _app = session
    gui = window.viewer._renderer._internal_gui

    window.viewer.set_system_info_text("one line only")
    window.viewer.set_system_info_visible(True)
    qt_overlay.paint_chrome(gui, window.viewer, 1000, 700)
    assert gui.info_max_scroll() == 0, "the short fixture already overflows"
    short = _filled_rects(gui, qt_overlay)

    window.viewer.set_system_info_text("\n".join(f"line {i}" for i in range(400)))
    qt_overlay.paint_chrome(gui, window.viewer, 1000, 700)
    assert gui.info_max_scroll() > 0, "the tall fixture did not overflow"
    tall = _filled_rects(gui, qt_overlay)

    assert short == 0, f"a bar was drawn for text that fits ({short} fills)"
    assert tall == 2, f"expected a track and a thumb, got {tall} fills"


def _filled_rects(gui, qt_overlay) -> int:
    """How many filled rectangles the chrome paints (the bar adds two)."""

    class _Counter:
        def __init__(self):
            self.fills = 0

        def fill_rect(self, *a, **k):
            self.fills += 1

        def stroke_rect(self, *a, **k):
            pass

        def gradient_rect(self, *a, **k):
            pass

        def text(self, *a, **k):
            pass

        def text_width(self, text):
            return 7.0 * len(str(text))

        def push_clip(self, *a, **k):
            pass

        def pop_clip(self, *a, **k):
            pass

    counter = _Counter()
    gui._paint_info(counter)
    return counter.fills
