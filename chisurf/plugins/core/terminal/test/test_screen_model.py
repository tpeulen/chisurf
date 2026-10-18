"""The terminal screen model: ANSI bytes in, a grid of coloured cells out.

These tests run without a PTY and without emtk drawing: they feed byte strings
and assert on the model (lines, runs, cursor), the way the console's ANSI
parser is tested.

A note on newlines: the model is a vt100, where LF moves down *without*
returning to column 0 (a PTY's ONLCR delivers a program's newline as ``\r\n``).
The tests write ``\r\n`` where they mean "a new line", and one test pins the
bare-LF behaviour itself.
"""

from __future__ import annotations

import pytest

from chisurf.plugins.core.terminal.screen import TerminalScreen


def make(columns: int = 20, rows: int = 5) -> TerminalScreen:
    return TerminalScreen(columns=columns, rows=rows)


# ── plain text ────────────────────────────────────────────────────────────


def test_plain_text_appends_lines():
    s = make()
    s.feed("hello\r\nworld")
    assert s.line_text(0) == "hello"
    assert s.line_text(1) == "world"
    assert s.cursor == (1, 5)


def test_bare_linefeed_keeps_the_column():
    # A vt100 LF moves down only; the PTY's ONLCR is what adds the CR.
    s = make()
    s.feed("hello\nworld")
    assert s.line_text(1) == "     world"


def test_text_after_feed_without_newline_continues_the_line():
    s = make()
    s.feed("hel")
    s.feed("lo")
    assert s.line_text(0) == "hello"


def test_wrap_at_columns():
    s = TerminalScreen(columns=5, rows=4)
    s.feed("abcdefgh")
    assert s.line_text(0) == "abcde"
    assert s.line_text(1) == "fgh"


def test_tab_advances_to_the_next_eight_column_stop():
    s = make()
    s.feed("a\tb")
    assert s.line_text(0).rstrip() == "a" + " " * 7 + "b"
    assert s.cursor == (0, 9)


# ── in-place redraw (progress bars) ───────────────────────────────────────


def test_carriage_return_overwrites_the_line():
    s = make()
    s.feed("10%\r20%")
    assert s.line_text(0) == "20%"


def test_erase_line_leaves_the_prompt():
    s = make()
    s.feed("10%\r\x1b[K100%")
    assert s.line_text(0) == "100%"


def test_partial_escape_held_across_chunks():
    s = make()
    s.feed("a\x1b[")
    s.feed("31mb")
    assert s.line_text(0) == "ab"
    assert s.line_runs(0)[1].state.fg == 1


# ── colour ────────────────────────────────────────────────────────────────


def test_sgr_runs_share_state_within_a_line():
    s = make()
    s.feed("a\x1b[31mb\x1b[0mc")
    runs = s.line_runs(0)
    assert [r.text for r in runs] == ["a", "b", "c"]
    assert runs[0].state.fg is None
    assert runs[1].state.fg == 1
    assert runs[2].state.fg is None


def test_truecolour_sgr_resolves_to_hex():
    s = make()
    s.feed("\x1b[38;2;10;20;30mX")
    assert s.line_runs(0)[0].state.fg == "#0a141e"


def test_state_survives_a_chunk_boundary():
    s = make()
    s.feed("\x1b[1;32m")
    s.feed("bold-green")
    run = s.line_runs(0)[0]
    assert run.state.bold and run.state.fg == 2


# ── cursor addressing ─────────────────────────────────────────────────────


def test_cursor_position_writes_in_the_grid():
    s = TerminalScreen(columns=10, rows=4)
    s.feed("\x1b[3;5HX")
    assert s.line_text(2).rstrip() == "    X"
    assert s.cursor == (2, 5)


def test_relative_cursor_moves():
    s = TerminalScreen(columns=10, rows=4)
    s.feed("\x1b[3;3H")
    s.feed("\x1b[A\x1b[DZ")  # up one, left one, write
    assert s.line_text(1).rstrip() == " Z"


def test_erase_display_clears_the_grid():
    s = TerminalScreen(columns=10, rows=4)
    s.feed("one\r\ntwo\r\nthree\r\nfour")
    s.feed("\x1b[2J")
    for row in range(4):
        assert s.line_text(row).strip() == ""


def test_erase_display_from_the_cursor_keeps_what_is_above():
    s = TerminalScreen(columns=10, rows=4)
    s.feed("one\r\ntwo\r\nthr\x1b[3;4H")  # cursor on "thr", column 3
    s.feed("\x1b[0J")
    assert s.line_text(0) == "one"
    assert s.line_text(2) == "thr"
    assert s.line_text(3).strip() == ""


# ── editing operations ────────────────────────────────────────────────────


def test_insert_and_delete_lines():
    s = TerminalScreen(columns=8, rows=4)
    s.feed("one\r\ntwo\r\nthree\r\nfour")
    s.feed("\x1b[2;1H\x1b[L")  # insert a blank line before "two"
    assert [s.line_text(r).rstrip() for r in range(4)] == ["one", "", "two", "three"]
    # DL shifts within the region: the line the IL pushed past the bottom
    # margin ("four") is gone, as in a vt100.
    s.feed("\x1b[M")
    assert [s.line_text(r).rstrip() for r in range(4)] == ["one", "two", "three", ""]


def test_insert_and_delete_characters():
    s = make()
    s.feed("ac")
    s.feed("\x1b[1;2H\x1b[2@")  # two blanks before "c"
    assert s.line_text(0).rstrip() == "a  c"
    s.feed("\x1b[2P")  # delete them
    assert s.line_text(0).rstrip() == "ac"


def test_erase_chars_at_the_cursor():
    s = make()
    s.feed("abcdef\x1b[1;2H\x1b[3X")
    # ECH blanks the cells in place; the line's length does not change.
    assert s.line_text(0).rstrip() == "a   ef"


# ── scrolling and scrollback ──────────────────────────────────────────────


def _filled(rows: int = 3, lines: int = 5) -> TerminalScreen:
    """A screen fed *lines* numbered lines on a *rows*-row grid."""
    s = TerminalScreen(columns=10, rows=rows)
    for n in range(1, lines + 1):
        s.feed(f"{n}\r\n")
    return s


def test_scrolling_pushes_lines_into_the_scrollback():
    s = _filled(rows=3, lines=5)
    # Lines 1..3 scrolled off; the grid holds 4, 5 and the fresh prompt line.
    assert [s.line_text(r).rstrip() for r in (0, 1, 2)] == ["1", "2", "3"]
    assert [s.line_text(r).rstrip() for r in (3, 4, 5)] == ["4", "5", ""]


def test_scrollback_is_capped():
    s = TerminalScreen(columns=10, rows=2, max_scrollback=3)
    for n in range(10):
        s.feed(f"{n}\r\n")
    assert s.total_lines == 5  # 3 scrollback + 2 grid
    assert s.line_text(0) == "6"  # the cap dropped "0".."5"


def test_explicit_scroll_up_and_down():
    s = TerminalScreen(columns=10, rows=3)
    s.feed("a\r\nb\r\nc")
    s.feed("\x1b[S")  # scroll up: "a" leaves the grid
    assert s.line_text(0) == "a"
    assert [s.line_text(r).rstrip() for r in (1, 2, 3)] == ["b", "c", ""]
    s.feed("\x1b[T")  # back down: "a" returns to the top of the grid
    assert s.scrollback_lines == 0
    assert [s.line_text(r).rstrip() for r in (0, 1, 2)] == ["a", "b", "c"]


def test_scroll_region_scrolls_at_its_bottom_margin():
    s = TerminalScreen(columns=10, rows=4)
    s.feed("one\r\ntwo\r\nthree\r\nfour")
    s.feed("\x1b[2;3r")  # rows 2..3 scroll
    s.feed("\x1b[3;1H\r\n")  # CRLF at the region's bottom margin
    assert s.line_text(0) == "one"  # above the region
    assert s.line_text(1) == "three"  # the region scrolled
    assert s.line_text(3) == "four"  # below the region


# ── the alternate screen ──────────────────────────────────────────────────


def test_alternate_screen_round_trip():
    s = TerminalScreen(columns=10, rows=4)
    s.feed("shell\r\noutput")
    s.feed("\x1b[?1049h")
    assert s.alt
    assert s.total_lines == 4  # nothing new in the scrollback
    s.feed("\x1b[2;3HTUI")
    assert s.line_text(1).rstrip() == "  TUI"
    s.feed("\x1b[?1049l")
    assert not s.alt
    assert s.line_text(0) == "shell"
    assert s.line_text(1) == "output"


def test_alternate_screen_output_never_enters_the_scrollback():
    s = TerminalScreen(columns=10, rows=2)
    s.feed("before\r\nafter\r\n")  # "before" scrolls off
    assert s.scrollback_lines == 1
    s.feed("\x1b[?1049h")
    for n in range(8):
        s.feed(f"tui{n}\r\n")
    assert s.scrollback_lines == 1  # the alt screen never scrolls to history
    s.feed("\x1b[?1049l")
    assert s.line_text(0) == "before"
    assert s.line_text(1) == "after"


# ── resize ────────────────────────────────────────────────────────────────


def test_resize_grows_and_shrinks_rows():
    s = TerminalScreen(columns=10, rows=3)
    s.feed("a\r\nb\r\nc")
    s.resize(10, 5)
    assert s.rows == 5
    assert s.line_text(2) == "c"
    s.resize(10, 2)
    assert s.rows == 2
    assert s.line_text(0) == "a"  # pushed to the scrollback
    assert s.line_text(1) == "b"


def test_resize_keeps_the_cursor_inside():
    s = TerminalScreen(columns=10, rows=5)
    s.feed("\x1b[5;5H")
    s.resize(10, 3)
    assert s.cursor == (2, 4)


# ── what the control reads to draw ────────────────────────────────────────


def test_visible_window_over_scrollback_and_grid():
    s = _filled(rows=3, lines=5)  # scrollback 1..3, grid 4, 5, ""
    # Live view: the grid.
    assert [(i, t.rstrip()) for i, t in s.visible(0)] == [(3, "4"), (4, "5"), (5, "")]
    # Scrolled one line up: the newest scrollback line plus the top of the grid.
    assert [(i, t.rstrip()) for i, t in s.visible(1)] == [(2, "3"), (3, "4"), (4, "5")]


def test_max_scroll_offset():
    s = _filled(rows=3, lines=5)
    assert s.max_scroll_offset == 3


def test_selection_text_range():
    s = make()
    s.feed("alpha\r\nbeta\r\ngamma")
    text = s.text_range((0, 2), (2, 3))
    # Start's column to end's column, whole lines between; inclusive.
    assert text == "pha\nbeta\ngamm"


def test_cursor_visibility_mode():
    s = make()
    assert s.cursor_visible
    s.feed("\x1b[?25l")
    assert not s.cursor_visible
    s.feed("\x1b[?25h")
    assert s.cursor_visible


def test_lines_beyond_the_grid_have_no_runs():
    s = TerminalScreen(columns=8, rows=2)
    assert s.line_runs(0) == []
    assert s.line_text(0) == ""


@pytest.mark.parametrize("noise", ["\x1b]0;title\x07", "\x1b(B", "\x1b=", "\x07\x00"])
def test_unmodelled_escapes_are_dropped(noise: str):
    s = make()
    s.feed(noise + "ok")
    assert s.line_text(0).rstrip() == "ok"
