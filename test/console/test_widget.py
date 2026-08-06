"""The console widget, driven off-screen.

Covers the behaviours that only exist once there is a document and a cursor:
prompt protection, the keymap, copy-without-prompts, and the recording round
trip. The interpreter itself is covered by ``test_engine.py``, without Qt.
"""

from __future__ import annotations

import pytest

pytest.importorskip("qtpy")

from qtpy import QtCore, QtGui, QtWidgets  # noqa: E402

from chisurf.gui.chinsole import Chinsole, ConsoleConfig, ConsoleRole  # noqa: E402
from chisurf.gui.chinsole.view import BLOCK_INPUT, PromptBlockData  # noqa: E402


@pytest.fixture()
def console(qtbot):
    """Return an interactive console with no persistent state.

    Returns
    -------
    Chinsole
    """
    widget = Chinsole(ConsoleConfig(history_path=False, session_log=None))
    qtbot.addWidget(widget)
    widget.resize(800, 400)
    return widget


def run(console, source: str) -> None:
    """Type *source* at the prompt and press Enter.

    Parameters
    ----------
    console : Chinsole
    source : str
    """
    console.view.set_input_buffer(source)
    console.view.executeRequested.emit(console.view.input_buffer())


def press(widget, key, modifier=QtCore.Qt.NoModifier, text=""):
    """Send a key press to *widget*.

    Parameters
    ----------
    widget : QtWidgets.QWidget
    key : int
    modifier : QtCore.Qt.KeyboardModifiers, optional
    text : str, optional
    """
    event = QtGui.QKeyEvent(QtCore.QEvent.KeyPress, key, modifier, text)
    QtWidgets.QApplication.sendEvent(widget, event)


# ----------------------------------------------------------------------
# execution through the widget
# ----------------------------------------------------------------------

def test_result_is_shown(console):
    """A trailing expression is echoed under an ``Out`` prompt."""
    run(console, "6*7")
    assert "Out[1]: 42" in console.view.toPlainText()


def test_output_is_streamed(console):
    """``print`` reaches the document."""
    run(console, "print('hello console')")
    assert "hello console" in console.view.toPlainText()


def test_traceback_is_shown_without_console_frames(console):
    """An error shows the user's frame, not the console's plumbing."""
    run(console, "1/0")
    text = console.view.toPlainText()
    assert "ZeroDivisionError" in text
    assert "chisurf/core/console" not in text


def test_incomplete_input_opens_a_continuation_line(console):
    """Enter on an unfinished block continues instead of executing."""
    run(console, "for i in range(3):")
    assert console.view.toPlainText().rstrip().endswith("...:")
    assert console.shell.execution_count == 1


def test_continuation_is_indented(console):
    """The continuation line is prefilled to the right depth."""
    run(console, "for i in range(3):")
    assert console.view.input_buffer().endswith("    ")


# ----------------------------------------------------------------------
# prompt protection
# ----------------------------------------------------------------------

def test_prompt_position_tracks_the_input_area(console):
    """Everything before the prompt is out of bounds."""
    run(console, "1")
    assert not console.view.is_editable(0)
    assert console.view.is_editable(console.view._prompt_pos)


def test_backspace_cannot_eat_the_prompt(console):
    """Backspace at the start of the input does nothing."""
    run(console, "1")
    before = console.view.toPlainText()
    cursor = console.view.textCursor()
    cursor.setPosition(console.view._prompt_pos)
    console.view.setTextCursor(cursor)
    press(console.view, QtCore.Qt.Key_Backspace)
    assert console.view.toPlainText() == before


def test_typing_over_old_output_types_at_the_prompt(console):
    """Clicking into the scrollback and typing does not corrupt it.

    Beeping instead would be technically defensible and infuriating; what a
    console must never do is let the character land in the transcript.
    """
    run(console, "print('earlier')")
    cursor = console.view.textCursor()
    cursor.setPosition(5)
    console.view.setTextCursor(cursor)
    press(console.view, QtCore.Qt.Key_X, text="x")
    text = console.view.toPlainText()
    assert "earlier" in text
    assert console.view.input_buffer() == "x"


def test_input_buffer_excludes_the_prompt(console):
    """What the shell receives is the typed text, never the prompt."""
    console.view.set_input_buffer("abc")
    assert console.view.input_buffer() == "abc"


def test_input_buffer_strips_continuation_prompts(console):
    """A multi-line block comes back as real Python."""
    run(console, "for i in range(2):")
    console.view.textCursor().insertText("pass")
    assert console.view.input_buffer() == "for i in range(2):\n    pass"


# ----------------------------------------------------------------------
# clipboard
# ----------------------------------------------------------------------

def test_copy_strips_prompts(console):
    """Copying a transcript yields runnable code, not ``In [1]:`` noise."""
    run(console, "x = 1")
    cursor = console.view.textCursor()
    cursor.setPosition(0)
    cursor.movePosition(QtGui.QTextCursor.End, QtGui.QTextCursor.KeepAnchor)
    console.view.setTextCursor(cursor)
    copied = console.view.createMimeDataFromSelection().text()
    assert "In [" not in copied
    assert "x = 1" in copied


def test_paste_strips_doctest_prompts(console):
    """Pasting a snippet copied from a README works."""
    mime = QtCore.QMimeData()
    mime.setText(">>> a = 1\n>>> b = 2")
    console.view.insertFromMimeData(mime)
    assert console.view.input_buffer() == "a = 1\nb = 2"


def test_paste_leaves_ordinary_code_alone(console):
    """A normal paste is never altered."""
    mime = QtCore.QMimeData()
    mime.setText("value = 3")
    console.view.insertFromMimeData(mime)
    assert console.view.input_buffer() == "value = 3"


# ----------------------------------------------------------------------
# history
# ----------------------------------------------------------------------

def test_history_walks_backwards(console):
    """Up recalls the previous entry."""
    run(console, "first = 1")
    run(console, "second = 2")
    console.walk_history(-1)
    assert console.view.input_buffer() == "second = 2"
    console.walk_history(-1)
    assert console.view.input_buffer() == "first = 1"


def test_history_restores_what_was_being_typed(console):
    """Walking forward past the newest entry returns the draft."""
    run(console, "recorded = 1")
    console.view.set_input_buffer("half typed")
    console.walk_history(-1)
    assert console.view.input_buffer() == "recorded = 1"
    console.walk_history(+1)
    assert console.view.input_buffer() == "half typed"


# ----------------------------------------------------------------------
# recording
# ----------------------------------------------------------------------

def test_macro_records_only_while_recording(console):
    """Start and stop bound what ends up in the macro."""
    run(console, "before = 0")
    console.start_recording()
    run(console, "during = 1")
    console.stop_recording()
    run(console, "after = 2")
    assert console.macro == "during = 1\n"


def test_macro_round_trips_through_a_file(console, tmp_path):
    """A recorded macro saves and replays.

    The round trip is the point: *Macro ▸ Record* previously had no way to stop
    or save, so nothing ever reached a file.
    """
    console.start_recording()
    run(console, "marker = 'recorded'")
    console.stop_recording()

    path = tmp_path / "macro.py"
    assert console.save_macro(str(path)) == str(path)
    assert path.read_text(encoding="utf-8") == "marker = 'recorded'\n"

    console.shell.user_ns.pop("marker", None)
    console.run_file(path)
    assert console.shell.user_ns["marker"] == "recorded"


# ----------------------------------------------------------------------
# roles
# ----------------------------------------------------------------------

def test_command_role_has_a_line_input(qtbot):
    """chimol's role puts input on its own line, under the output."""
    widget = Chinsole(ConsoleConfig(role=ConsoleRole.COMMAND, history_path=False,
                                    session_log=None))
    qtbot.addWidget(widget)
    assert widget.input_line is not None


def test_output_role_takes_no_input(qtbot):
    """The code editor's panel is read-only and shows no prompt."""
    widget = Chinsole(ConsoleConfig(role=ConsoleRole.OUTPUT, history_path=False,
                                    session_log=None))
    qtbot.addWidget(widget)
    assert widget.input_line is None
    assert "In [" not in widget.view.toPlainText()


def test_output_role_stays_promptless_after_clear(qtbot):
    """``clear()`` must not draw a prompt into a read-only panel.

    It did: ``clear_screen`` redrew the prompt unconditionally, so every run
    of a script in the code editor put a stray ``In []:`` at the head of its
    output panel. Construction alone does not catch it — the panel is cleared
    before each run.
    """
    widget = Chinsole(ConsoleConfig(role=ConsoleRole.OUTPUT, history_path=False,
                                    session_log=None, banner=""))
    qtbot.addWidget(widget)
    widget.clear()
    widget.append_output("script output\n")
    assert widget.view.toPlainText() == "script output\n"


def test_interactive_role_reprompts_after_clear(console):
    """Clearing an interactive console leaves a usable prompt."""
    console.clear()
    assert "In [" in console.view.toPlainText()


def test_prefill_selects_the_placeholder(qtbot):
    """A menu entry can put a command in the input with a part selected."""
    widget = Chinsole(ConsoleConfig(role=ConsoleRole.COMMAND, history_path=False,
                                    session_log=None))
    qtbot.addWidget(widget)
    widget.prefill("color <colour>, sele", "<colour>")
    assert widget.input_line.selectedText() == "<colour>"


# ----------------------------------------------------------------------
# themes and output volume
# ----------------------------------------------------------------------

@pytest.mark.parametrize("style", ["linux", "lightbg", "nocolor"])
def test_legacy_style_names_apply(console, style):
    """``set_default_style`` keeps working with qtconsole's names."""
    console.set_default_style(style)
    assert console.theme.name.startswith("chisurf-")


def test_runaway_output_is_bounded(console):
    """A print loop cannot grow the document without limit.

    The cap is what stops ``while True: print(i)`` wedging the application.
    """
    console.view.set_max_blocks(200)
    run(console, "for i in range(5000):\n    print(i)\n\n")
    console.pump.flush_now()
    assert console.view.document().blockCount() <= 260


def test_prompt_survives_scrollback_trimming(console):
    """Trimming the oldest blocks must not eat the prompt."""
    console.view.set_max_blocks(50)
    run(console, "for i in range(500):\n    print(i)\n\n")
    console.pump.flush_now()
    assert console.view.toPlainText().rstrip().endswith(":")
    console.view.set_input_buffer("still_works = 1")
    run(console, console.view.input_buffer())
    assert console.shell.user_ns["still_works"] == 1
