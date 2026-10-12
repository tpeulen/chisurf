"""Capture the before-half of the W9 S4 migration: the Qt shell's console dock and Macro menu.

Starts the Qt main window with scratch settings and private RPC ports and drives its console
(``cs.console``, chinsole) the way a user does -- keys sent to the console view -- through a fixed
list of *behaviours*. Each behaviour is a name, whether the Qt console did it, and what was
observed. Then it records:

* ``console``: the control inventory (:func:`migration_parity.control_inventory`) of the console
  dock and a PNG of it after the behaviours ran;
* ``behaviours``: ``name -> {"ok": bool, "observed": str}``;
* ``menus``: the Macro menu (text, shortcut, checkable);
* ``namespace``: the names the console starts with that a user reaches for (``cs``, ``gui``,
  ``np``, ``os``).

``test/native_emtk/shell_s4_qt_inventory.json`` is that record; ``test_emtk_shell_console.py``
drives the emtk console through the same behaviours and compares.

Not a test (the Qt shell takes a minute to start). Run from the repository root::

    S=$(mktemp -d); QT_QPA_PLATFORM=offscreen CHISURF_SETTINGS_DIR=$S/settings HOME=$S/home \\
        python -u test/native_emtk/capture_shell_s4_qt_before.py

PNGs and ``qt_inventory.json`` go to ``$CHISURF_S4_BEFORE_DIR`` (``renders/w9_s4``).
"""

from __future__ import annotations

import faulthandler
import json
import os
import socket
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

#: The behaviours, in the order they are driven (later ones rely on the history of earlier ones).
BEHAVIOURS = (
    "run_expression",
    "stdout",
    "statement_silent",
    "stderr_traceback",
    "continuation_indent",
    "multiline_block",
    "history_up",
    "history_down",
    "history_prefix",
    "completion_single",
    "completion_list",
    "calltip",
    "pinfo_pager",
    "search_ctrl_r",
    "kill_ctrl_k",
    "yank_ctrl_y",
    "kill_ctrl_u",
    "magic",
    "cs_run",
    "cs_run_history",
    "record_macro",
    "replay_macro",
    "session_log",
    "clear_ctrl_l",
    "interrupt_ctrl_c",
)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> None:
    """Drive the Qt console through the behaviours and write the PNGs and the inventory."""
    faulthandler.enable()
    faulthandler.dump_traceback_later(300, exit=True)
    sys.path.insert(0, str(REPO / "test" / "gui"))
    from mmfdb.security import credentials

    # The OS keystore is the user's: startup's autologin would write a session token there.
    credentials.store_session_token = lambda *args, **kwargs: False
    credentials.load_session_token = lambda *args, **kwargs: None

    from migration_parity import control_inventory
    from qtpy import QtCore, QtTest, QtWidgets

    import chisurf
    import chisurf.gui
    from chisurf.core import settings

    settings.cs_settings.setdefault("mmfdb", {}).update(
        cmd_port=_free_port(), pub_port=_free_port()
    )
    app = chisurf.gui.get_app()
    gui = chisurf.cs
    gui.resize(1440, 900)

    def pump(seconds: float) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.02)

    pump(2)
    wizard = QtWidgets.QApplication.activeModalWidget()
    if wizard is not None:
        wizard.reject()
        pump(0.5)
    gui.dockWidget_console.setVisible(True)
    pump(1.0)

    console = chisurf.console
    view = console.view
    out = Path(os.environ.get("CHISURF_S4_BEFORE_DIR", REPO / "renders" / "w9_s4"))
    out.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="s4_macro_"))
    record: dict = {"console": {}, "behaviours": {}, "menus": {}, "namespace": []}

    def key(code, modifiers=QtCore.Qt.NoModifier) -> None:
        QtTest.QTest.keyClick(view, code, modifiers)
        pump(0.05)

    def type_(text: str) -> None:
        QtTest.QTest.keyClicks(view, text)
        pump(0.05)

    def submit(text: str) -> None:
        view.set_input_buffer("")
        type_(text)
        key(QtCore.Qt.Key_Return)
        pump(0.2)

    def buf() -> str:
        return view.input_buffer()

    def text() -> str:
        return view.toPlainText()

    def note(name: str, ok: bool, observed: str) -> None:
        record["behaviours"][name] = {"ok": bool(ok), "observed": str(observed)[:200]}
        print(f"  {name}: {'ok' if ok else 'NO'}  {str(observed)[:80]!r}", flush=True)

    print("stage: behaviours", flush=True)
    view.setFocus()
    console.clear()
    pump(0.3)
    record["namespace"] = sorted(n for n in ("cs", "gui", "np", "os") if n in console.shell.user_ns)
    console.push({"s4_alpha_value": 1, "s4_beta_value": 2})

    submit("2 + 40")
    note("run_expression", "42" in text(), text().strip().splitlines()[-2:])
    submit("print('hello s4')")
    note("stdout", "hello s4" in text(), "hello s4" in text())
    before = text()
    submit("s4_x = 7")
    silent = text()[len(before) :].count("Out[") == 0
    submit("s4_x")
    note("statement_silent", silent and "7" in text()[len(before) :], silent)
    submit("1/0")
    note("stderr_traceback", "ZeroDivisionError" in text(), "ZeroDivisionError" in text())

    view.set_input_buffer("")
    type_("for s4_i in range(2):")
    key(QtCore.Qt.Key_Return)
    pump(0.2)
    note("continuation_indent", buf().endswith("    ") and "for" in buf(), buf())
    type_("print(s4_i * 10)")
    key(QtCore.Qt.Key_Return)
    key(QtCore.Qt.Key_Return)
    pump(0.3)
    note(
        "multiline_block", "10" in text().split("for s4_i")[-1], text().split("for s4_i")[-1][-40:]
    )

    submit("s4_x + 1")
    view.set_input_buffer("")
    key(QtCore.Qt.Key_Up)
    note("history_up", buf() == "s4_x + 1", buf())
    key(QtCore.Qt.Key_Down)
    note("history_down", buf() == "", buf())
    view.set_input_buffer("")
    type_("pri")
    key(QtCore.Qt.Key_Up)
    note("history_prefix", buf().startswith("print('hello s4')"), buf())

    view.set_input_buffer("")
    type_("s4_alp")
    key(QtCore.Qt.Key_Tab)
    note("completion_single", buf() == "s4_alpha_value", buf())
    view.set_input_buffer("")
    type_("s4_")
    key(QtCore.Qt.Key_Tab)
    popup = console.completion_popup
    # The popup is the list; each row is "<kind glyph> <name>".
    items = [popup.item(i).text().split(" ", 1)[-1] for i in range(popup.count())]
    note(
        "completion_list",
        popup.isVisible() and {"s4_alpha_value", "s4_beta_value"} <= set(items),
        items,
    )
    key(QtCore.Qt.Key_Escape)
    popup.hide()

    view.set_input_buffer("")
    type_("max(")
    pump(0.3)
    note("calltip", console.calltip.isVisible(), console.calltip.isVisible())
    console.calltip.hide()

    submit("max?")
    pump(0.3)
    note("pinfo_pager", console.pager.isVisible(), console.pager.isVisible())
    gui.dockWidget_console.grab().save(str(out / "qt_console_pager.png"))
    console.pager.hide()

    view.set_input_buffer("")
    type_("hello")
    key(QtCore.Qt.Key_R, QtCore.Qt.ControlModifier)
    note("search_ctrl_r", buf() == "print('hello s4')", buf())

    view.set_input_buffer("")
    type_("abcdef")
    key(QtCore.Qt.Key_Home)
    key(QtCore.Qt.Key_K, QtCore.Qt.ControlModifier)
    note("kill_ctrl_k", buf() == "", buf())
    key(QtCore.Qt.Key_Y, QtCore.Qt.ControlModifier)
    note("yank_ctrl_y", buf() == "abcdef", buf())
    key(QtCore.Qt.Key_End)
    key(QtCore.Qt.Key_U, QtCore.Qt.ControlModifier)
    note("kill_ctrl_u", buf() == "", buf())

    submit("%pwd")
    note("magic", os.getcwd() in text(), os.getcwd() in text())

    from chisurf.history import get_history

    history = get_history()
    events_before = len(history.list_events())
    chisurf.run("s4_from_run = 5")
    pump(0.5)
    note(
        "cs_run",
        console.shell.user_ns.get("s4_from_run") == 5,
        console.shell.user_ns.get("s4_from_run"),
    )
    recorded = [str(e.get("summary", "")) for e in history.list_events()[events_before:]]
    note("cs_run_history", any(r.startswith("run command") for r in recorded), recorded)

    console.start_recording()
    submit("s4_m = 3")
    console.stop_recording()
    macro = console.macro
    note("record_macro", "s4_m = 3" in macro, macro)
    path = console.save_macro(str(scratch / "s4.cm.py"))
    console.shell.user_ns.pop("s4_m", None)
    console.run_file(path)
    pump(0.3)
    note("replay_macro", console.shell.user_ns.get("s4_m") == 3, console.shell.user_ns.get("s4_m"))

    session = console.session_file
    logged = (
        Path(session).read_text("utf-8", errors="ignore")
        if session and Path(session).exists()
        else ""
    )
    note("session_log", "2 + 40" in logged, session)

    gui.dockWidget_console.grab().save(str(out / "qt_console.png"))
    record["console"] = control_inventory(gui.dockWidget_console)
    key(QtCore.Qt.Key_L, QtCore.Qt.ControlModifier)
    pump(0.2)
    note("clear_ctrl_l", "hello s4" not in text(), len(text()))
    # Ctrl+C with no selection asks a running cell to stop; the cell runs on the GUI thread, so the
    # request lands between cells (the interrupter is armed by %time-like long runs). Recorded as
    # present: the binding exists.
    note("interrupt_ctrl_c", callable(getattr(console, "interrupt", None)), "binding")

    print("stage: menus", flush=True)
    for action in gui.menuBar.actions():
        menu = action.menu()
        if menu is None or action.text().replace("&", "") != "Macro":
            continue
        record["menus"]["Macro"] = [
            {
                "text": a.text().replace("&", ""),
                "shortcut": a.shortcut().toString(),
                "checkable": bool(a.isCheckable()),
            }
            for a in menu.actions()
            if not a.isSeparator()
        ]
        menu.popup(gui.mapToGlobal(gui.rect().topLeft()))
        pump(0.2)
        menu.grab().save(str(out / "qt_menu_Macro.png"))
        menu.hide()
    record["behaviour_order"] = list(BEHAVIOURS)
    missing = [name for name in BEHAVIOURS if name not in record["behaviours"]]
    assert not missing, missing
    (out / "qt_inventory.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(f"wrote {out}", flush=True)
    os._exit(0)  # the Qt shell's post-show services keep the loop alive


if __name__ == "__main__":
    main()
