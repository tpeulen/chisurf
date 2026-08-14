"""The command line that lives in the viewport, and the focus rule around it.

Two things are being guarded here, and the second is the one that breaks.

The **editor** is ordinary: a buffer, a caret, a history, completion. The
**focus rule** is not: the viewport binds single letters to actions (``r`` for
cartoon, ``s`` for sidechains), so a prompt that swallowed every keystroke would
disable them silently -- the letters would simply stop working, with no error
and nothing on screen to explain it. The rule is therefore that keys reach the
prompt only when it has focus, and the tests below state both halves: what a
focused prompt takes, and what an unfocused one must let past.

None of this needs a GUI toolkit or a GPU. That is the point of the module it
tests, and :func:`test_the_prompt_paints_without_a_toolkit` says so by painting
a frame through the software quad rasteriser.
"""
from __future__ import annotations

import pytest

from chimol.host import events, keys
from chimol.renderer.internal_gui import (
    GuiRow,
    InternalGui,
)
from chimol.cmtk.command_line import CommandLine

SIZE = (900, 600)


def _line(run=None) -> CommandLine:
    """Return a focused command line -- the state every editing test wants."""
    line = CommandLine(run)
    line.set_focus(True)
    return line


def _type(line: CommandLine, text: str) -> None:
    """Type *text* one character at a time, as a host would deliver it."""
    for char in text:
        line.key(0, char, 0)


# ── the editor ───────────────────────────────────────────────────────────
def test_typing_and_the_caret():
    line = _line()
    _type(line, "color red")
    assert (line.text, line.cursor) == ("color red", 9)

    line.key(keys.KEY_LEFT, "", 0)
    line.key(keys.KEY_LEFT, "", 0)
    line.key(keys.KEY_LEFT, "", 0)
    _type(line, "b")
    assert line.text == "color bred"

    line.key(keys.KEY_HOME, "", 0)
    assert line.cursor == 0
    line.key(keys.KEY_BACKSPACE, "", 0)
    assert line.text == "color bred", "backspace at the start must not wrap"
    line.key(keys.KEY_DELETE, "", 0)
    assert line.text == "olor bred"


def test_control_characters_are_not_inserted():
    """A paste carries newlines and tabs; a buffer holding one is a broken line."""
    line = _line()
    line.insert("show\tspheres\nzoom")
    assert line.text == "showsphereszoom"
    assert line.cursor == len(line.text)


def test_submitting_runs_the_line_and_logs_it():
    ran: list[str] = []
    line = _line(ran.append)
    _type(line, "zoom all")
    line.key(keys.KEY_RETURN, "", 0)

    assert ran == ["zoom all"]
    assert line.text == ""
    assert [entry.kind for entry in line.log] == ["echo"]
    assert "zoom all" in line.log[0].text


def test_a_failing_command_is_logged_rather_than_raised():
    """A mistyped command must not travel up into the host's paint loop."""
    def _boom(_line: str) -> None:
        raise ValueError("no such colour")

    line = _line(_boom)
    _type(line, "color mauve")
    line.key(keys.KEY_RETURN, "", 0)

    assert [entry.kind for entry in line.log] == ["echo", "error"]
    assert "no such colour" in line.log[-1].text


def test_history_walks_back_and_returns_to_what_was_being_typed():
    line = _line(lambda _: None)
    for command in ("fetch 148l", "show spheres"):
        _type(line, command)
        line.key(keys.KEY_RETURN, "", 0)

    _type(line, "half typed")
    line.key(keys.KEY_UP, "", 0)
    assert line.text == "show spheres"
    line.key(keys.KEY_UP, "", 0)
    assert line.text == "fetch 148l"
    line.key(keys.KEY_UP, "", 0)
    assert line.text == "fetch 148l", "the oldest entry is the end of the walk"
    line.key(keys.KEY_DOWN, "", 0)
    line.key(keys.KEY_DOWN, "", 0)
    assert line.text == "half typed", "coming back must restore the pending line"


def test_a_repeated_command_is_not_stored_twice():
    line = _line(lambda _: None)
    for _ in range(3):
        _type(line, "ray")
        line.key(keys.KEY_RETURN, "", 0)
    assert line.history == ["ray"]


def test_tab_completes_to_the_common_prefix_and_lists_the_rest():
    line = _line()
    # Filtered by the prefix, as the real dispatcher does: it is the command
    # layer that knows the names, and it returns only the ones that match.
    names = ("spectrum", "split_chains", "show")
    line.completions = lambda text, cursor: [
        name for name in names if name.startswith(text[:cursor])
    ]

    _type(line, "sp")
    line.key(keys.KEY_TAB, "", 0)
    assert line.text == "sp", "'spectrum' and 'split_chains' share only 'sp'"
    assert line.log, "an ambiguous completion has to show the candidates"

    line.set_text("spe")
    line.key(keys.KEY_TAB, "", 0)
    assert line.text == "spectrum"


def test_tab_completes_the_argument_not_the_command():
    """``color re<Tab>`` completes the colour, leaving the command alone."""
    line = _line()
    line.completions = lambda text, cursor: ["red", "red_ochre"]
    _type(line, "color re")
    line.key(keys.KEY_TAB, "", 0)
    assert line.text == "color red"


@pytest.mark.parametrize("modifier", [events.CONTROL_MODIFIER, events.META_MODIFIER])
def test_the_readline_shortcuts(modifier):
    """Command on a Mac and Control elsewhere mean the same thing here."""
    line = _line()
    _type(line, "show spheres")

    line.key(0, "a", modifier)
    assert line.cursor == 0
    line.key(0, "e", modifier)
    assert line.cursor == len("show spheres")
    line.key(0, "w", modifier)
    assert line.text == "show "
    line.key(0, "u", modifier)
    assert line.text == ""


def test_ctrl_a_arrives_as_a_control_character_from_qt():
    r"""Qt reports ctrl+A as ``\x01``; the editor must still read it as 'a'."""
    line = _line()
    _type(line, "zoom")
    line.key(0, "\x01", events.CONTROL_MODIFIER)
    assert line.cursor == 0


def test_escape_clears_before_it_unfocuses():
    line = _line()
    _type(line, "half typed")
    line.key(keys.KEY_ESCAPE, "", 0)
    assert (line.text, line.focused) == ("", True)
    line.key(keys.KEY_ESCAPE, "", 0)
    assert line.focused is False


def test_the_log_is_capped_and_split_on_newlines():
    line = _line()
    line.append("one\ntwo\nthree")
    assert [entry.text for entry in line.log] == ["one", "two", "three"]
    for index in range(CommandLine.MAX_LOG * 2):
        line.append(str(index))
    assert len(line.log) == CommandLine.MAX_LOG


# ── the focus rule ───────────────────────────────────────────────────────
def _gui(run=None) -> InternalGui:
    gui = InternalGui(run)
    gui.set_rows([GuiRow(name="all", is_header=True), GuiRow(name="148l")])
    gui.layout(*SIZE)
    return gui


def test_an_unfocused_prompt_lets_the_viewport_shortcuts_through():
    gui = _gui()
    for char in "rcbsd":
        assert gui.key_press(0, char, 0) is False, (
            f"'{char}' is a viewer shortcut and must reach the viewer"
        )


def test_return_focuses_the_prompt_and_then_it_takes_everything():
    gui = _gui()
    assert gui.key_press(keys.KEY_RETURN, "\r", 0) is True
    assert gui.command_line.focused is True
    assert gui.key_press(0, "r", 0) is True
    assert gui.command_line.text == "r"


def test_clicking_the_prompt_focuses_it_and_places_the_caret():
    gui = _gui()
    rect = gui.command_rect()
    assert rect.w > 0.0 and rect.h > 0.0

    gui.command_line.set_text("show spheres")
    assert gui.mouse_press(rect.x + rect.w / 2, rect.y + rect.h / 2) is True
    assert gui.command_line.focused is True

    from chimol.renderer.internal_gui import char_width
    from chimol.cmtk.command_line import PROMPT

    advance = char_width(gui.FONT_PT)
    origin = rect.x + gui.MARGIN + advance * (len(PROMPT) + 1)
    gui.mouse_press(origin + advance * 4.5, rect.y + rect.h / 2)
    assert gui.command_line.cursor == 4


def test_clicking_away_gives_the_keyboard_back():
    gui = _gui()
    gui.focus_command(True)
    # The middle of the scene: no panel, no prompt.
    gui.mouse_press(SIZE[0] * 0.3, SIZE[1] * 0.4)
    assert gui.command_line.focused is False


def test_the_prompt_is_reachable_even_with_the_panel_hidden():
    """``internal_gui`` and ``internal_prompt`` are separate settings."""
    gui = _gui()
    gui.visible = False
    rect = gui.command_rect()
    assert gui.hit_test(rect.x + 20.0, rect.y + rect.h / 2).kind == "command"


def test_a_command_typed_in_the_viewport_runs_through_the_panel_sink():
    """One sink for the panel's buttons and for the prompt."""
    ran: list[str] = []
    gui = _gui()
    gui.set_run_command(ran.append)
    gui.focus_command(True)
    for char in "bg_color white":
        gui.key_press(0, char, 0)
    gui.key_press(keys.KEY_RETURN, "\r", 0)
    assert ran == ["bg_color white"]


def test_escape_closes_a_menu_before_it_reaches_the_prompt():
    gui = _gui()
    rect = gui._button_rects[1]["A"]
    gui.mouse_press(rect.x + rect.w / 2, rect.y + rect.h / 2)
    assert gui.has_menu()
    assert gui.key_press(keys.KEY_ESCAPE, "", 0) is True
    assert not gui.has_menu()


def test_focusing_the_prompt_closes_an_open_menu():
    """Two things cannot both own the next keystroke."""
    gui = _gui()
    rect = gui._button_rects[1]["A"]
    gui.mouse_press(rect.x + rect.w / 2, rect.y + rect.h / 2)
    assert gui.has_menu()
    gui.focus_command(True)
    assert not gui.has_menu()


# ── drawing ──────────────────────────────────────────────────────────────
def test_the_prompt_paints_without_a_toolkit():
    """Quads, from the same painter the rest of the chrome uses."""
    from chimol.cmtk.quad_painter import QuadPainter

    gui = _gui()
    gui.focus_command(True)
    gui.command_line.set_text("color red")
    gui.command_line.feedback = 2
    gui.command_line.append("loaded 148l", "message")
    gui.command_line.append("no such colour", "error")
    gui.layout(*SIZE)

    bare = QuadPainter()
    gui.command_line.visible = False
    gui.paint(bare)

    with_prompt = QuadPainter()
    gui.command_line.visible = True
    gui.layout(*SIZE)
    gui.paint(with_prompt)

    assert len(with_prompt.vertices()) > len(bare.vertices()), (
        "the prompt has to add quads: text, background and a caret"
    )


def test_the_dom_key_names_translate():
    """A browser reports strings; the engine decides on integers."""
    assert keys.key_from_dom("ArrowUp") == keys.KEY_UP
    assert keys.key_from_dom("Enter") == keys.KEY_RETURN
    assert keys.key_from_dom("a") == 0, "a printable key carries its own text"
    assert keys.modifiers_from_dom(True, False, False, False) == events.CONTROL_MODIFIER
    assert keys.modifiers_from_dom(False, True, False, True) == (
        events.SHIFT_MODIFIER | events.META_MODIFIER
    )
