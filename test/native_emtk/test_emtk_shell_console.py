"""The emtk shell's Console dock and Macro menu (W9 S4), against the Qt console's behaviours.

``shell_s4_qt_inventory.json`` (made by ``capture_shell_s4_qt_before.py``) lists what the Qt console did
when driven with keys -- run, history, completion, calltip, pager, the kill ring, ``chisurf.run``,
macro recording and replay. ``test_parity_with_the_qt_console`` drives the emtk console through the same
behaviours, with keys sent to the shell as a user types them (:class:`emtk.testing.Driver`), and
requires every behaviour the Qt console had. The other tests cover what only the emtk side has to
prove: the macro menu's file round trip, ``chisurf.run`` from a worker thread, composed (IME) input,
the console's own session connection, and the screenshots.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import pytest
from emtk.events import CONTROL_MODIFIER, SHIFT_MODIFIER
from emtk.keys import KEY_DOWN, KEY_END, KEY_ESCAPE, KEY_HOME, KEY_RETURN, KEY_TAB, KEY_UP
from emtk.testing import Driver

from chisurf.emtk.main_app import EmtkShellApp

SHOTS = Path(os.environ.get("CHISURF_NATIVE_SCREENSHOTS", "/private/tmp/chisurf-native-gpu"))
BEFORE = json.loads(Path(__file__).with_name("shell_s4_qt_inventory.json").read_text("utf-8"))

#: Qt console behaviours the emtk console does not have yet; each is an open item of the ledger
#: (``okf/subsystems/qt-retirement.md``, slice S4). This list only shrinks.
KNOWN_GAPS: dict[str, str] = {}


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Working folder, recent projects and the operation history in ``tmp_path``."""
    import chisurf
    from chisurf.core.project import recent

    monkeypatch.setattr(recent, "recent_projects_file", lambda: tmp_path / "recent_projects.json")
    monkeypatch.setattr(chisurf, "working_path", tmp_path, raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def shell(isolated):
    """A shell with no plugins and no session; the console's history and log in ``tmp_path``."""
    app = EmtkShellApp(
        {},
        loader=lambda plugin_id: None,
        console_history=isolated / "history.txt",
        console_session_file=isolated / "session.py",
    )
    yield app
    app.close()


@pytest.fixture
def driver(shell):
    drv = Driver(shell, size=(1400, 900))
    drv.frame(3)
    drv.click(shell.console.item_rects["console.input"])
    return drv


def _submit(driver: Driver, text: str) -> None:
    driver.app.console.set_input("")
    driver.type(text)
    driver.press(KEY_RETURN)


def _chord(driver: Driver, letter: str, mods: int = CONTROL_MODIFIER) -> None:
    driver.press(ord(letter), mods)


def _behaviours(driver: Driver, shell, tmp: Path) -> dict[str, tuple[bool, object]]:
    """Drive the emtk console through the Qt capture's behaviours, in its order."""
    import chisurf
    from chisurf.history import get_history

    console = shell.console
    seen: dict[str, tuple[bool, object]] = {}
    text = console.transcript.text
    buf = lambda: console.input_text  # noqa: E731

    console.push({"s4_alpha_value": 1, "s4_beta_value": 2})
    _submit(driver, "2 + 40")
    seen["run_expression"] = ("Out[1]: 42" in text(), text()[-40:])
    _submit(driver, "print('hello s4')")
    seen["stdout"] = ("hello s4" in text(), "")
    before = text()
    _submit(driver, "s4_x = 7")
    silent = "Out[" not in text()[len(before) :]
    _submit(driver, "s4_x")
    seen["statement_silent"] = (silent and "7" in text()[len(before) :], silent)
    _submit(driver, "1/0")
    seen["stderr_traceback"] = (
        "ZeroDivisionError" in text() and any(k == "stderr" for _t, k in console.transcript.lines),
        "",
    )

    console.set_input("")
    driver.type("for s4_i in range(2):")
    driver.press(KEY_RETURN)
    seen["continuation_indent"] = (buf().endswith("    ") and "for" in buf(), buf())
    driver.type("print(s4_i * 10)")
    driver.press(KEY_RETURN)
    driver.press(KEY_RETURN)
    tail = text().split("for s4_i")[-1]
    seen["multiline_block"] = ("\n0\n10" in tail, tail[-40:])

    _submit(driver, "s4_x + 1")
    console.set_input("")
    driver.press(KEY_UP)
    seen["history_up"] = (buf() == "s4_x + 1", buf())
    driver.press(KEY_DOWN)
    seen["history_down"] = (buf() == "", buf())
    console.set_input("")
    driver.type("pri")
    driver.press(KEY_UP)
    seen["history_prefix"] = (buf().startswith("print('hello s4')"), buf())

    console.set_input("")
    driver.type("s4_alp")
    driver.press(KEY_TAB)
    seen["completion_single"] = (buf() == "s4_alpha_value", buf())
    console.set_input("")
    driver.type("s4_")
    driver.press(KEY_TAB)
    listed = list(console.completions)
    seen["completion_list"] = (
        {"s4_alpha_value", "s4_beta_value"} <= set(listed)
        and "s4_alpha_value" in driver.painter.strings,
        listed,
    )
    driver.screenshot(SHOTS / "emtk_console_completion.png")
    driver.press(KEY_ESCAPE)

    console.set_input("")
    driver.type("max(")
    seen["calltip"] = (
        bool(console.calltip_text) and "calltip" in console.control.boxes,
        console.calltip_text,
    )
    driver.screenshot(SHOTS / "emtk_console_calltip.png")
    driver.press(KEY_ESCAPE)

    _submit(driver, "max?")
    seen["pinfo_pager"] = (
        bool(console.pager_title) and "builtin" in console.control.pager.text,
        console.pager_title,
    )
    driver.screenshot(SHOTS / "emtk_console_pager.png")
    driver.press(KEY_ESCAPE)

    console.set_input("")
    driver.type("hello")
    _chord(driver, "r")
    seen["search_ctrl_r"] = (buf() == "print('hello s4')", buf())

    console.set_input("")
    driver.type("abcdef")
    driver.press(KEY_HOME)
    _chord(driver, "k")
    seen["kill_ctrl_k"] = (buf() == "", buf())
    _chord(driver, "y")
    seen["yank_ctrl_y"] = (buf() == "abcdef", buf())
    driver.press(KEY_END)
    _chord(driver, "u")
    seen["kill_ctrl_u"] = (buf() == "", buf())

    _submit(driver, "%pwd")
    seen["magic"] = (os.getcwd() in text(), os.getcwd())

    history = get_history()
    events_before = len(history.list_events())
    chisurf.run("s4_from_run = 5")
    driver.frame(1)
    seen["cs_run"] = (
        console.engine.user_ns.get("s4_from_run") == 5,
        console.engine.user_ns.get("s4_from_run"),
    )
    recorded = [str(e.get("summary", "")) for e in history.list_events()[events_before:]]
    seen["cs_run_history"] = (any(r.startswith("run command") for r in recorded), recorded)

    driver.click("menu.Macro")
    driver.click("Record")
    _submit(driver, "s4_m = 3")
    driver.click("menu.Macro")
    driver.click("Record")
    assert shell.project.file_dialog is not None, "stopping the recording offers to save it"
    shell.project.choose_file(tmp / "s4.cm.py")
    macro = (tmp / "s4.cm.py").read_text("utf-8")
    seen["record_macro"] = ("s4_m = 3" in macro, macro)
    console.engine.user_ns.pop("s4_m", None)
    driver.click("menu.Macro")
    driver.click("Run Macro…")
    shell.project.choose_file(tmp / "s4.cm.py")
    driver.frame(1)
    seen["replay_macro"] = (
        console.engine.user_ns.get("s4_m") == 3,
        console.engine.user_ns.get("s4_m"),
    )

    logged = console.session_file.read_text("utf-8") if console.session_file else ""
    seen["session_log"] = ("2 + 40" in logged, str(console.session_file))
    driver.screenshot(SHOTS / "emtk_console.png")
    _chord(driver, "l")
    seen["clear_ctrl_l"] = ("hello s4" not in text(), len(text()))
    console.set_input("half typed")
    _chord(driver, "c")
    seen["interrupt_ctrl_c"] = (buf() == "" and "KeyboardInterrupt" in text(), buf())
    return seen


def test_parity_with_the_qt_console(driver, shell, isolated):
    """Every behaviour of the Qt console works in the emtk console, or is a listed gap."""
    seen = _behaviours(driver, shell, isolated)
    order = BEFORE["behaviour_order"]
    assert list(seen) == order, "the emtk drive follows the capture's order"
    lost = [name for name in order if BEFORE["behaviours"][name]["ok"] and not seen[name][0]]
    unexplained = [name for name in lost if name not in KNOWN_GAPS]
    assert not unexplained, {name: seen[name][1] for name in unexplained}
    closed = [name for name in KNOWN_GAPS if seen.get(name, (False,))[0]]
    assert not closed, f"these gaps are closed now; strike them from KNOWN_GAPS: {closed}"


def test_the_macro_menu_has_the_qt_items(driver, shell):
    """The Qt Macro menu's Record (checkable) is there, checked while recording; Run Macro… is added."""
    menus = dict(shell.session_menus())
    macro = menus["Macro"]
    labels = [action.label for action in macro]
    for item in BEFORE["menus"]["Macro"]:
        assert item["text"] in labels
        action = next(a for a in macro if a.label == item["text"])
        assert (action.checked is not None) == item["checkable"]
    record = next(a for a in macro if a.key == "record")
    assert record.checked() is False
    driver.click("menu.Macro")
    driver.click("Record")
    assert record.checked() is True and shell.console.recording
    driver.click("menu.Macro")
    driver.screenshot(SHOTS / "emtk_shell_menu_macro.png")
    assert "Run Macro…" in driver.painter.strings
    driver.escape()
    driver.click("menu.Macro")
    driver.click("Record")
    # Nothing ran: the Qt "Nothing was recorded." message, no save dialog.
    assert shell.project.file_dialog is None
    assert shell.project.dialogs.current is not None


def test_the_console_keys_win_over_the_menu_shortcuts_while_it_has_the_keys(driver, shell):
    """Ctrl+R searches the history in the console (Reinitialize otherwise), as in the Qt console."""
    _submit(driver, "s4_search_me = 1")
    shell.console.set_input("search_me")
    _chord(driver, "r")
    assert shell.console.input_text == "s4_search_me = 1"
    assert shell.project.dialogs.current is None, "Reinitialize did not ask"


def test_shift_enter_adds_a_line_and_a_block_runs_on_a_blank_line(driver, shell):
    console = shell.console
    driver.type("s4_a = 1")
    driver.press(KEY_RETURN, SHIFT_MODIFIER)
    driver.type("s4_b = 2")
    assert console.input_text == "s4_a = 1\ns4_b = 2"
    driver.press(KEY_RETURN)
    assert console.engine.user_ns["s4_b"] == 2
    assert "   ...: s4_b = 2" in console.transcript.text()


def test_chisurf_run_from_a_worker_runs_on_the_next_frame(driver, shell):
    import chisurf

    thread = threading.Thread(target=lambda: chisurf.run("s4_from_worker = 11"))
    thread.start()
    thread.join()
    assert "s4_from_worker" not in shell.console.engine.user_ns, "queued, not run on the worker"
    driver.frame(1)
    assert shell.console.engine.user_ns["s4_from_worker"] == 11
    chisurf.log("s4_logged_only = 1")
    driver.frame(1)
    assert "s4_logged_only" not in shell.console.engine.user_ns
    assert "s4_logged_only = 1" in shell.console.session_file.read_text("utf-8")


def test_the_console_gives_chisurf_run_back_on_close(isolated):
    import chisurf

    before = chisurf.run
    app = EmtkShellApp(
        {}, loader=lambda plugin_id: None, console_history=False, console_session_file=False
    )
    assert chisurf.run == app.console.run_threadsafe and chisurf.console is app.console
    app.close()
    assert chisurf.run is before


def test_the_history_persists_across_consoles(shell, isolated, driver):
    _submit(driver, "s4_persisted = 1")
    shell.close()
    again = EmtkShellApp(
        {},
        loader=lambda plugin_id: None,
        console_history=isolated / "history.txt",
        console_session_file=False,
    )
    try:
        assert "s4_persisted = 1" in again.console.engine.history.entries
    finally:
        again.close()


def test_composed_input_types_into_the_console(driver, shell):
    """IME: the preedit is drawn at the caret, not typed; the commit is typed (emtk.ime)."""
    console = shell.console
    driver.type("s4_jp = '")
    driver.compose("にほん", 3)
    assert console.input_text == "s4_jp = '"
    assert console.control.input.preedit == "にほん"
    assert "にほん" in driver.painter.strings
    driver.screenshot(SHOTS / "emtk_console_ime_preedit.png")
    driver.commit("日本")
    driver.compose("´")
    driver.commit("é")
    driver.type("'")
    driver.press(KEY_RETURN)
    assert console.engine.user_ns["s4_jp"] == "日本é"
    assert shell.ime_caret() is not None


def test_the_console_reaches_the_session_through_its_own_connection(isolated):
    """``api`` is the session's API on a connection of the console's own; a command that changes the
    science is one undo step, named after the command."""
    from chisurf.emtk.session import start_session
    from chisurf.server.session import SessionState
    from test.native_emtk.test_emtk_shell_session import _demo_fit, _idle, _settle, _value

    session = start_session(state=SessionState())
    app = EmtkShellApp(
        {}, loader=lambda plugin_id: None, console_history=False, console_session_file=False
    )
    app.data.adopt(session)
    try:
        driver = Driver(app, size=(1500, 950))
        driver.frame(2)
        uid = _demo_fit(driver, app)
        driver.frame(2)
        api = app.console.engine.user_ns["api"]
        assert api is not session.api, "the console has a connection of its own"
        before = _value(app, "N")
        import chisurf

        chisurf.run(f"api.set_parameter_value('N', {before + 1.0}, fit_uid={uid!r})")
        _settle(
            driver,
            lambda: _idle(app) and _value(app, "N") == pytest.approx(before + 1.0),
            "the command's edit",
        )
        _settle(driver, lambda: _idle(app) and app.project.can_undo(), "the undo step")
        summaries = [str(e.get("summary", "")) for e in app.project.history.list_events()]
        assert any(s.startswith("run command: api.set_parameter_value") for s in summaries), (
            summaries
        )
    finally:
        app.close()
        session.close()


def test_the_console_screenshots(driver, shell):
    """A realistic console state, written for inspection."""
    _submit(driver, "import math")
    _submit(driver, "math.pi * 2")
    shell.console.set_input("for k in range(3):\n    print(k, k ** 2)")
    driver.press(KEY_RETURN)
    driver.press(KEY_RETURN)
    _submit(driver, "undefined_name")
    driver.type("math.sq")
    driver.press(KEY_TAB)
    driver.frame(2)
    driver.screenshot(SHOTS / "emtk_console_session.png")
    assert any("NameError" in line for line, _kind in shell.console.transcript.lines)
    assert "2 4" in shell.console.transcript.text()
