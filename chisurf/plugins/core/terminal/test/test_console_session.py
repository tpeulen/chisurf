"""A Python console as a terminal session: the built-in engine behind a pane.

:class:`~chisurf.plugins.core.terminal.console_session.ConsoleSession` speaks
the terminal plugin's engine seam (``screen`` / ``write`` / ``resize`` /
``alive`` / ``close``), so a :class:`~chisurf.plugins.core.terminal.control.TerminalControl`
draws it like any pane -- but the child is not a process: it is ChiSurf's own
console engine (:class:`chisurf.core.console.shell.Shell`), in-process, with
the ChiSurf namespace and its magics.

These tests drive the seam the way the control does: bytes in, the screen's
grid out. No emtk, no PTY.
"""

from __future__ import annotations

import pytest

pytest.importorskip("chisurf.core.console.shell")

from chisurf.plugins.core.terminal.console_session import ConsoleSession


def text(s: ConsoleSession) -> str:
    return "\n".join(s.screen.line_text(i) for i in range(s.screen.total_lines))


def type_str(s: ConsoleSession, chars: str) -> None:
    s.write(chars.encode("utf-8"))


# ── the prompt ───────────────────────────────────────────────────────────


def test_a_banner_and_prompt_appear():
    s = ConsoleSession()
    assert "ChiSurf" in text(s)
    assert "In [" in text(s)  # the In [N]: prompt appeared


def test_typed_characters_echo():
    s = ConsoleSession()
    type_str(s, "1+1")
    t = text(s)
    assert "In [" in t
    assert "1+1" in t


# ── running code ─────────────────────────────────────────────────────────


def test_enter_runs_the_line_and_shows_the_result():
    s = ConsoleSession()
    type_str(s, "1+1\r")
    assert "2" in text(s)
    assert text(s).count("In [") == 2  # the first prompt and the next one


def test_print_output_arrives():
    s = ConsoleSession()
    type_str(s, "print('hello pane')\r")
    assert "hello pane" in text(s)


def test_the_namespace_persists_between_lines():
    s = ConsoleSession()
    type_str(s, "x = 21\r")
    type_str(s, "x * 2\r")
    assert "42" in text(s)


def test_incomplete_lines_continue():
    s = ConsoleSession()
    type_str(s, "for i in (1, 2):\r")
    assert "..." in text(s).rstrip()  # the block continues (   ...: )
    type_str(s, "print(i)\r")  # the auto-indent already typed the body's indent
    assert "..." in text(s).rstrip()  # still continuing (as a REPL)
    type_str(s, "\r")  # a bare Enter ends the block
    body = text(s)
    assert "1" in body and "2" in body
    assert "In [" in body.rstrip()  # back to the In [N]: prompt


def test_errors_show_a_traceback_and_the_console_survives():
    s = ConsoleSession()
    type_str(s, "1/0\r")
    body = text(s)
    assert "ZeroDivisionError" in body
    assert s.alive
    type_str(s, "2+2\r")
    assert "4" in text(s)


# ── line editing ─────────────────────────────────────────────────────────


def test_backspace_edits_the_line():
    s = ConsoleSession()
    type_str(s, "12+34")
    type_str(s, "\x7f\x7f5")  # erase "3", "4" -> type "5": the line is "12+5"
    type_str(s, "\r")
    assert "17" in text(s)


def test_ctrl_c_cancels_the_pending_line():
    s = ConsoleSession()
    type_str(s, "1+1")
    type_str(s, "\x03")
    body = text(s)
    assert "KeyboardInterrupt" in body
    assert "In [" in body  # back to the In [N]: prompt after cancel
    type_str(s, "2+2\r")
    assert "4" in text(s)


def test_ctrl_d_on_an_empty_line_ends_the_session():
    s = ConsoleSession()
    type_str(s, "\x04")
    assert not s.alive


def test_ctrl_d_mid_line_does_not_end_it():
    s = ConsoleSession()
    type_str(s, "1")
    type_str(s, "\x04")
    assert s.alive


# ── the seam ─────────────────────────────────────────────────────────────


def test_resize_passes_through():
    s = ConsoleSession()
    s.resize(100, 30)
    assert (s.screen.columns, s.screen.rows) == (100, 30)


def test_close_ends_the_session():
    s = ConsoleSession()
    s.close()
    assert not s.alive


def test_the_magics_of_the_built_in_console_work():
    s = ConsoleSession()
    type_str(s, "%quickref\r")  # a built-in magic, not a Python statement
    assert s.alive
    assert text(s).count("In [") >= 2  # it ran and the prompt returned


def test_out_formatting_shows_execution_count():
    s = ConsoleSession()
    type_str(s, "10 + 32\r")
    t = text(s)
    assert "Out[1]: 42" in t
    assert "In [2]:" in t


def test_object_introspection_question_mark():
    s = ConsoleSession()
    type_str(s, "int?\r")
    t = text(s)
    assert "Docstring:" in t or "Convert a number" in t
    assert "In [2]:" in t


def test_tab_completion_extends_symbol():
    s = ConsoleSession()
    type_str(s, "x_special_variable = 99\r")
    type_str(s, "x_speci\t")
    t = text(s)
    assert "x_special_variable" in t
    type_str(s, "\r")
    t = text(s)
    assert "Out[2]: 99" in t


def test_history_arrow_navigation():
    s = ConsoleSession()
    type_str(s, "10 + 1\r")
    type_str(s, "20 + 2\r")
    # Press Up arrow (\x1b[A)
    type_str(s, "\x1b[A")
    t = text(s)
    assert "20 + 2" in t
    # Press Up arrow again
    type_str(s, "\x1b[A")
    t = text(s)
    assert "10 + 1" in t
    # Press Down arrow (\x1b[B)
    type_str(s, "\x1b[B")
    t = text(s)
    assert "20 + 2" in t
    type_str(s, "\r")
    assert "Out[3]: 22" in text(s)
