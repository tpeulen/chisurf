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
    """Chimol's role puts input on its own line, under the output."""
    widget = Chinsole(ConsoleConfig(role=ConsoleRole.COMMAND, history_path=False, session_log=None))
    qtbot.addWidget(widget)
    assert widget.input_line is not None


def test_output_role_takes_no_input(qtbot):
    """The code editor's panel is read-only and shows no prompt."""
    widget = Chinsole(ConsoleConfig(role=ConsoleRole.OUTPUT, history_path=False, session_log=None))
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
    widget = Chinsole(
        ConsoleConfig(role=ConsoleRole.OUTPUT, history_path=False, session_log=None, banner="")
    )
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
    widget = Chinsole(ConsoleConfig(role=ConsoleRole.COMMAND, history_path=False, session_log=None))
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


# ----------------------------------------------------------------------
# the pager
# ----------------------------------------------------------------------


def test_long_output_goes_to_the_pager(console):
    """``obj?`` fills the pager instead of burying the transcript.

    Introspecting one object can produce hundreds of lines. Left in the
    scrollback they push everything the user did out of view, which is the one
    thing a transcript exists for.
    """
    before = console.view.document().blockCount()
    run(console, "sum?")
    assert not console.pager.isHidden()
    assert "Docstring" in console.pager.view.toPlainText()
    assert console.view.document().blockCount() - before <= 3


def test_the_pager_names_what_was_asked(console):
    """The header says what produced the page, not just "Output"."""
    run(console, "sum?")
    assert console.pager._title.text() == "sum?"


def test_escape_dismisses_the_pager(console, qtbot):
    """Esc closes the page and hands focus back."""
    run(console, "sum?")
    press(console.pager.view, QtCore.Qt.Key_Escape)
    assert console.pager.isHidden()


def test_paging_none_keeps_output_in_the_scrollback(console):
    """``gui.console.paging: none`` is honoured.

    Someone who dislikes the split pane must be able to turn it off and still
    see the output.
    """
    console.paging = "none"
    run(console, "sum?")
    assert console.pager.isHidden()
    assert "Docstring" in console.view.toPlainText()


def test_the_pager_follows_the_theme(console):
    """The pager is restyled with the console.

    Its header is a plain ``QWidget``, which ignores a stylesheet background
    unless ``WA_StyledBackground`` is set -- so it kept Qt's light grey against
    a dark console until that was fixed.
    """
    console.set_style("nocolor")
    assert console.pager.styleSheet()
    assert console.theme.background in console.pager.styleSheet()


# ----------------------------------------------------------------------
# help and the guided tour
# ----------------------------------------------------------------------


def test_the_console_ships_help_and_a_tour():
    """Both files exist beside the widget.

    A console is the one panel in the window with a blinking cursor and no
    instructions, so `?` (what things mean) and the tour (what to type first)
    are not optional here.
    """
    import json
    import pathlib

    package = pathlib.Path(__file__).resolve().parents[2] / "chisurf" / "gui" / "chinsole"
    assert (package / "help.md").is_file()
    guide = json.loads((package / "guide.json").read_text(encoding="utf-8"))
    assert guide["steps"]


def test_every_tour_step_points_somewhere():
    """A step with no target spotlights nothing and reads as a broken tour."""
    import json
    import pathlib

    package = pathlib.Path(__file__).resolve().parents[2] / "chisurf" / "gui" / "chinsole"
    guide = json.loads((package / "guide.json").read_text(encoding="utf-8"))
    assert all(step.get("target") for step in guide["steps"])


def test_the_tour_waits_for_the_user():
    """At least half the steps ask the user to do something.

    The house rule is that a tour points at controls and waits, rather than
    pressing them: someone who watched a line being run has not learned to run
    one.
    """
    import json
    import pathlib

    package = pathlib.Path(__file__).resolve().parents[2] / "chisurf" / "gui" / "chinsole"
    steps = json.loads((package / "guide.json").read_text(encoding="utf-8"))["steps"]
    assert sum(1 for step in steps if "await" in step) >= len(steps) // 2


def test_tour_targets_name_widgets_that_exist(console):
    """Every ``name`` target resolves on a real console.

    The failure this prevents is silent: a tour whose target does not resolve
    still runs, still shows its text, and simply highlights nothing.
    """
    import json
    import pathlib

    package = pathlib.Path(__file__).resolve().parents[2] / "chisurf" / "gui" / "chinsole"
    steps = json.loads((package / "guide.json").read_text(encoding="utf-8"))["steps"]
    names = {
        str(w.objectName()).casefold()
        for w in console.findChildren(QtWidgets.QWidget)
        if w.objectName()
    }
    names.add(str(console.objectName()).casefold())
    missing = [
        step["target"]["name"]
        for step in steps
        if step.get("target", {}).get("name")
        and not any(n.endswith(step["target"]["name"].casefold()) for n in names)
    ]
    assert not missing, f"tour points at widgets that do not exist: {missing}"


def test_help_links_resolve():
    """Every documentation link in the help modal points at a real page.

    The modal routes a `docs/` link to ChiSurf's documentation browser, so a
    dead one is a dead end rather than a broken-looking link.
    """
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[2]
    text = (root / "chisurf" / "gui" / "chinsole" / "help.md").read_text(encoding="utf-8")
    missing = [
        target for target in re.findall(r"\]\((docs/[^)]+)\)", text) if not (root / target).exists()
    ]
    assert not missing, f"help links to pages that do not exist: {missing}"


def test_the_interactive_console_shows_the_help_buttons(console, qtbot):
    """`?` and Guide are reachable from the console itself."""
    labels = {
        (button.text() or button.toolTip())
        for button in console.findChildren(QtWidgets.QAbstractButton)
    }
    assert any("?" in label for label in labels)
    assert any("Guide" in label for label in labels)
