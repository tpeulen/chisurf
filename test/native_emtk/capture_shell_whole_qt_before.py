"""Capture the whole Qt main window's control inventory: ribbon, menus, toolbars and docks.

The slice before-halves (``capture_shell_s2..s5``) each pin one area of the shell. Bugs the owner
found anyway -- the emtk shell had no ribbon at all -- sat *between* the slices: no slice owned
the ribbon, so no parity test could miss it. This records everything a user of the Qt main
window can reach from the window itself, in one file:

* ``ribbon``: ``category -> panel -> [button captions]`` (and each button's tooltip), with the
  category tab bar itself as a control;
* ``menus``: the ``.ui`` menu bar walked recursively (text, shortcut, checkable);
* ``toolbars``: each ``QToolBar``'s action texts;
* ``docks``: each ``QDockWidget``'s title and control inventory
  (:func:`migration_parity.control_inventory`), with a PNG of each.

``test/native_emtk/shell_whole_qt_inventory.json`` is that record; ``test_emtk_shell_whole_parity.py``
draws the emtk shell, walks its menus and docks the way a user would, and fails on any Qt
control the emtk shell lacks that is not a documented ``KNOWN_GAPS`` entry.

Not a test (the Qt shell takes a minute to start). Run from the repository root::

    S=$(mktemp -d); QT_QPA_PLATFORM=offscreen CHISURF_SETTINGS_DIR=$S/settings HOME=$S/home \\
        python -u test/native_emtk/capture_shell_whole_qt_before.py

PNGs go to ``$CHISURF_WHOLE_BEFORE_DIR`` (``renders/shell_whole``).
"""

from __future__ import annotations

import faulthandler
import json
import os
import socket
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT_JSON = Path(__file__).with_name("shell_whole_qt_inventory.json")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _clean(text: str) -> str:
    return str(text or "").replace("&", "").strip()


def _menu_rows(menu) -> list:
    rows = []
    for action in menu.actions():
        if action.isSeparator():
            continue
        row = {
            "text": _clean(action.text()),
            "shortcut": action.shortcut().toString(),
            "checkable": bool(action.isCheckable()),
            "visible": bool(action.isVisible()),
        }
        sub = action.menu()
        if sub is not None:
            row["menu"] = _menu_rows(sub)
        rows.append(row)
    return rows


def _ribbon(gui) -> dict:
    """``{category: {panel: [{"text", "tooltip"}]}}`` from the live ribbon bar."""
    from qtpy import QtWidgets

    integration = getattr(gui, "_ribbon_integration", None)
    bar = getattr(integration, "ribbon_bar", None)
    if bar is None:
        return {}
    out: dict = {}
    for name, category in bar.categories().items():
        panels = {}
        try:
            category_panels = category.panels()
        except Exception:  # noqa: BLE001 - the application-menu category has none
            category_panels = {}
        for title, panel in category_panels.items():
            buttons = []
            for button in panel.findChildren(QtWidgets.QAbstractButton):
                text = _clean(button.text()) or _clean(button.toolTip()).split("\n")[0]
                if not text:
                    continue
                buttons.append({"text": text, "tooltip": _clean(button.toolTip())[:200]})
            panels[_clean(title)] = buttons
        out[_clean(name)] = panels
    return out


def _ribbon_corner(gui) -> list:
    """The ribbon bar's own controls outside any category: search, help, language, collapse."""
    from qtpy import QtWidgets

    integration = getattr(gui, "_ribbon_integration", None)
    bar = getattr(integration, "ribbon_bar", None)
    if bar is None:
        return []
    categories = list(bar.categories().values())
    rows = []
    for widget in bar.findChildren(QtWidgets.QWidget):
        if any(category.isAncestorOf(widget) for category in categories):
            continue
        if isinstance(widget, QtWidgets.QLineEdit):
            text = _clean(widget.placeholderText()) or _clean(widget.toolTip())
            kind = "line_edit"
        elif isinstance(widget, QtWidgets.QAbstractButton):
            text = _clean(widget.text()) or _clean(widget.toolTip()).split("\n")[0]
            kind = "button"
        else:
            continue
        if text:
            rows.append(
                {
                    "kind": kind,
                    "text": text,
                    "tooltip": _clean(widget.toolTip())[:200],
                    "visible": widget.isVisible(),
                }
            )
    return rows


def main() -> None:
    """Start the Qt main window and write the whole-shell inventory."""
    faulthandler.enable()
    faulthandler.dump_traceback_later(300, exit=True)
    sys.path.insert(0, str(REPO / "test" / "gui"))
    from mmfdb.security import credentials

    # The OS keystore is the user's: startup's autologin would write a session token there.
    credentials.store_session_token = lambda *args, **kwargs: False
    credentials.load_session_token = lambda *args, **kwargs: None

    from migration_parity import control_inventory
    from qtpy import QtWidgets

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

    pump(3)
    # The ribbon is built when the tools load, after the window shows; wait for it.
    end = time.monotonic() + 90
    while time.monotonic() < end:
        bar = getattr(getattr(gui, "_ribbon_integration", None), "ribbon_bar", None)
        if bar is not None and bar.categories():
            break
        pump(0.5)
    pump(1)
    wizard = QtWidgets.QApplication.activeModalWidget()
    if wizard is not None:
        wizard.reject()
        pump(0.5)

    out = Path(os.environ.get("CHISURF_WHOLE_BEFORE_DIR", REPO / "renders" / "shell_whole"))
    out.mkdir(parents=True, exist_ok=True)
    record: dict = {
        "_comment": (
            "Whole Qt main window control inventory (ribbon, menus, toolbars, docks), "
            "written by test/native_emtk/capture_shell_whole_qt_before.py; compared by "
            "test_emtk_shell_whole_parity.py."
        ),
        "window_size": [1440, 900],
    }
    print("stage: ribbon", flush=True)
    record["ribbon"] = _ribbon(gui)
    record["ribbon_corner"] = _ribbon_corner(gui)
    print("stage: menus", flush=True)
    # The ribbon replaces the menu bar widget: QMainWindow.menuBar() would segfault, so the
    # .ui's own attribute is read (see the S3 capture).
    menubar = getattr(gui, "menuBar", None)
    menubar = menubar() if callable(menubar) and not hasattr(menubar, "actions") else menubar
    record["menus"] = {}
    for action in menubar.actions() if menubar is not None else ():
        if action.menu() is not None:
            record["menus"][_clean(action.text())] = _menu_rows(action.menu())
    print("stage: toolbars", flush=True)
    record["toolbars"] = {}
    for bar in gui.findChildren(QtWidgets.QToolBar):
        texts = [_clean(a.text()) for a in bar.actions() if not a.isSeparator() and a.text()]
        if texts:
            record["toolbars"][bar.objectName() or _clean(bar.windowTitle())] = {
                "visible": bar.isVisible(),
                "actions": texts,
            }
    print("stage: docks", flush=True)
    record["docks"] = {}
    for dock in gui.findChildren(QtWidgets.QDockWidget):
        name = dock.objectName() or _clean(dock.windowTitle())
        was_visible = dock.isVisible()
        dock.setVisible(True)
        pump(0.3)
        try:
            dock.grab().save(str(out / f"qt_dock_{name}.png"))
        except Exception:  # noqa: BLE001 - a dock that cannot grab still has an inventory
            pass
        inventory = control_inventory(dock)
        inventory["title"] = _clean(dock.windowTitle())
        inventory["visible_at_start"] = was_visible
        record["docks"][name] = inventory
    print("stage: behaviours", flush=True)
    # What a control inventory cannot see: the console draws a figure, not its repr.
    from qtpy import QtCore, QtTest

    record["behaviours"] = {}
    console = chisurf.console
    view = console.view
    drawn: list = []
    for name in ("append_image", "append_svg"):
        original = getattr(view, name, None)
        if callable(original):

            def counted(*args, _original=original, **kwargs):
                drawn.append(1)
                return _original(*args, **kwargs)

            setattr(view, name, counted)
    gui.dockWidget_console.setVisible(True)
    view.setFocus()
    pump(0.5)
    view.set_input_buffer("")
    QtTest.QTest.keyClicks(view, "import matplotlib.pyplot as plt; plt.plot([1, 2, 3]); plt.show()")
    QtTest.QTest.keyClick(view, QtCore.Qt.Key_Return)
    pump(3)
    record["behaviours"]["console_inline_figure"] = {
        "ok": bool(drawn),
        "observed": f"{len(drawn)} image(s) appended to the console view",
    }
    gui.grab().save(str(out / "qt_main_window.png"))
    OUT_JSON.write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT_JSON}", flush=True)
    os._exit(0)  # the Qt shell's post-show services keep the loop alive


if __name__ == "__main__":
    main()
