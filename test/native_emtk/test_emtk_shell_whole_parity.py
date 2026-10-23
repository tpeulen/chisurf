"""Whole-app parity: everything the Qt main window offers, reachable in the emtk shell.

The slice tests (S2..S4) each compare one area of the shell against its Qt before-half. The
owner still found the emtk shell without a ribbon -- no slice owned the ribbon, so nothing
compared it. This test compares the *whole* window: the Qt record
``shell_whole_qt_inventory.json`` (ribbon tabs, panels, buttons and corner controls; every
menu action; every toolbar action; every dock's title and its labels and buttons; written by
``capture_shell_whole_qt_before.py``) against what a user reaches in the emtk shell by
looking at it, opening each menu of its menu bar and showing each of its docks.

Matching is by caption (:func:`emtk_port_parity.normalize`), so a ribbon button that became a
menu item is present -- with one exception: a **ribbon tab** is a tab or a button, never a
menu header of the same name, because "the shell has a File menu" is exactly how a missing
ribbon hides.

A Qt control missing in the emtk shell fails unless :data:`KNOWN_GAPS` names it with a reason.
:data:`KNOWN_GAPS` only shrinks: an entry the shell now has fails too, so it is struck.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "gui"))

from emtk_port_parity import ControlRecorder, _is_pictogram_char, normalize  # noqa: E402


def _key(text: str) -> str:
    """:func:`normalize`, also dropping a trailing pictogram run (``Decay Analysis ⚠️``)."""
    out = normalize(text)
    while out and (_is_pictogram_char(out[-1]) or out[-1] in "\ufe0f\u200d"):
        out = out[:-1]
    return out


BEFORE = json.loads((HERE / "shell_whole_qt_inventory.json").read_text("utf-8"))
SIZE = (1440, 900)

#: Qt controls the emtk shell does not have yet, by inventory key, with the reason / owner.
#: This only shrinks (okf/subsystems/qt-retirement.md). Empty since the Log dock, the fit
#: export/import, Menu Switch, the ribbon pin and the File/Main tabs' groups were reached.
KNOWN_GAPS: dict[str, str] = {}

#: Qt controls the emtk shell has under another caption, by inventory key: the emtk control's
#: drawn rectangle (``item_rects`` key, of the shell, the console or the Terminal app the Console
#: dock hosts) must be there, and why
#: the caption differs. Unlike :data:`RENAMED`, presence is checked, not assumed.
ALIASES: dict[str, tuple[str, str]] = {
    "ribbon_corner:?": ("ribbon.help", "the shared Help action, drawn ❓ Help in every window"),
    "ribbon_corner:Language: English": (
        "ribbon.language",
        "🌍 EN; the full 'Language: English' is its tooltip",
    ),
    "ribbon_corner:P": ("ribbon.pin", "a drawn push-pin; its tooltip says pin / unpin (auto-fold)"),
    "dock_control:Console/?": (
        "console_terminal.help",
        "the shared Help action, drawn ❓ Help on the strip of the Terminal app the dock hosts",
    ),
}

#: Qt captions present in the emtk shell under another spelling, or not controls at all.
RENAMED = {
    "tttrheadereditor": "the menu row and ribbon button say TTTR Inspector, the tool's current name",
    "clsmgenerator": "the menu row and ribbon button say CLSM Simulator, the tool's current name",
    "dataset": "the Docks toggle is called Read data, the dock's own title",
    "fit": "the Docks toggle is called Analysis, the dock's own title",
    "plot-options": "the Docks toggle is called Plot settings, the dock's own title",
    "typehere": "Qt Designer's empty placeholder submenu, never had an item",
    "logging": "the Qt dock's title; the emtk dock is called Log",
    "plugins": "the Qt Plugins menu's submenus are the emtk shell's top-level menus",
    "dev": "an empty Qt submenu (no plugin declares it)",
    "cascadefitwindows": "View > Cascade Windows: it cascades every window of the Workspace, not only "
    "the fits (test_emtk_shell_workspace.py runs it)",
}


def _qt_items() -> dict[str, str]:
    """``inventory key -> caption`` for every Qt control a user can reach from the window."""
    items: dict[str, str] = {}
    for category, panels in BEFORE.get("ribbon", {}).items():
        items[f"ribbon_tab:{category}"] = category
        for panel, buttons in panels.items():
            items[f"ribbon_panel:{category}/{panel}"] = panel
            for button in buttons:
                items[f"ribbon_button:{category}/{panel}/{button['text']}"] = button["text"]
                if "\u26a0" in button["text"]:
                    items[f"experimental_marker:{button['text']}"] = button["text"]
    for row in BEFORE.get("ribbon_corner", []):
        items[f"ribbon_corner:{row['text']}"] = row["text"]

    def walk(path, rows):
        for row in rows:
            key = f"menu:{path}/{row['text']}"
            items[key] = row["text"]
            if row.get("menu") is not None:
                walk(f"{path}/{row['text']}", row["menu"])

    for menu, rows in BEFORE.get("menus", {}).items():
        items[f"menu:{menu}"] = menu
        walk(menu, rows)
    for bar, record in BEFORE.get("toolbars", {}).items():
        for action in record["actions"]:
            items[f"toolbar:{bar}/{action}"] = action
    for dock in BEFORE.get("docks", {}).values():
        title = dock["title"]
        items[f"dock:{title}"] = title
        for text in dock.get("labels", []) + dock.get("buttons", []):
            items[f"dock_control:{title}/{text}"] = text
    return items


@pytest.fixture(scope="module")
def reached():
    """What a user reaches in the emtk shell: drawn text and controls, every menu, every dock."""
    from emtk.testing import Driver

    from chisurf.emtk.main_app import EmtkShellApp
    from chisurf.emtk.session import start_session
    from chisurf.server.session import SessionState

    session = start_session(state=SessionState())
    shell = EmtkShellApp(
        loader=lambda plugin_id: None, console_history=False, console_session_file=False
    )
    shell.data.adopt(session)
    recorder = ControlRecorder()
    texts: set[str] = set()
    tabs: set[str] = set()
    raw: set[str] = set()

    def gather(driver):
        for string in driver.painter.strings:
            texts.add(_key(string))
            raw.add(str(string))
        for row in recorder.rows:
            if row["label"]:
                texts.add(_key(row["label"]))
                raw.add(str(row["label"]))
                if row["kind"] in ("begin_tab_item", "selectable", "button", "small_button"):
                    tabs.add(_key(row["label"]))
        # A ribbon draws its tabs itself and names them ``<ribbon>.tab.<title>`` (emtk.ribbon).
        for key in list(shell.item_rects):
            if ".tab." in key:
                tabs.add(_key(key.split(".tab.", 1)[1]))
        recorder.rows.clear()

    try:
        with recorder.installed():
            driver = Driver(shell, SIZE)
            driver.frame(4)
            gather(driver)
            menus = [
                key
                for key in list(shell.item_rects)
                if key.startswith("menu.") and "." not in key[len("menu.") :]
            ]
            for key in menus:
                driver.click(key)
                driver.frame(2)
                gather(driver)
                driver.escape()
            # Every ribbon tab, as a user clicks through them (File and Main hold the session groups).
            for key in [k for k in list(shell.item_rects) if k.startswith("ribbon.tab.")]:
                driver.click(key)
                driver.frame(2)
                gather(driver)
            for key in list(shell.docks.windows):
                shell.docks.focus(key)
                driver.frame(3)
                gather(driver)
            # The Log dock's tabs (Logging, RPC Monitor, History), as a user clicks them.
            shell.docks.focus("log")
            driver.frame(2)
            for name in [k for k in list(shell.log.form.rects) if k.startswith("log_tabs.")]:
                x, y, w, h = shell.log.form.rects[name]
                driver.click((x + w / 2, y + h / 2))
                driver.frame(2)
                gather(driver)
            titles = {_key(w.title) for w in shell.docks.windows.values()}
            texts |= titles
    finally:
        shell.close()
        session.close()
    texts.discard("")
    rects = (
        set(shell.item_rects)
        | {"console." + key for key in shell.console.item_rects}
        | {"console_terminal." + key for key in shell.console_terminal.item_rects}
    )
    return {"texts": texts, "tabs": tabs, "raw": raw, "rects": rects}


def _missing(reached) -> dict[str, str]:
    texts, tabs = reached["texts"], reached["tabs"]
    missing = {}
    for key, caption in _qt_items().items():
        norm = _key(caption)
        if not norm or norm in RENAMED:
            continue
        if key in ALIASES:
            present = ALIASES[key][0] in reached["rects"]
        elif key.startswith("ribbon_tab:"):
            present = norm in tabs
        elif key.startswith("experimental_marker:"):
            # The warning travels with the name: a drawn entry carrying both.
            present = any(
                "\u26a0" in text and norm in _key(text.replace("\u26a0", ""))
                for text in reached["raw"]
            )
        else:
            present = norm in texts
        if not present:
            missing[key] = caption
    return missing


def test_every_qt_control_is_reachable_in_the_emtk_shell(reached):
    missing = _missing(reached)
    unexplained = sorted(set(missing) - set(KNOWN_GAPS))
    assert not unexplained, (
        f"{len(unexplained)} Qt main-window controls are not reachable in the emtk shell "
        "(add the missing control, or name it in KNOWN_GAPS with its owner):\n  "
        + "\n  ".join(unexplained)
    )


def test_known_gaps_only_shrink(reached):
    missing = _missing(reached)
    closed = sorted(set(KNOWN_GAPS) - set(missing))
    assert not closed, f"now present in the emtk shell, strike from KNOWN_GAPS: {closed}"


def test_the_inventory_covers_the_whole_window():
    """A capture that lost an area (the ribbon builds late) would pass every comparison."""
    assert BEFORE.get("ribbon"), "the Qt ribbon is missing from the record: recapture"
    assert BEFORE.get("menus") and BEFORE.get("docks")
    assert len(_qt_items()) > 100


def test_behaviours_the_qt_shell_has_that_no_inventory_shows(tmp_path):
    """The console draws a figure as a picture, as the Qt console does -- not its text repr."""
    behaviours = BEFORE.get("behaviours", {})
    figure = behaviours.get("console_inline_figure")
    assert figure is not None, "recapture: the Qt record has no console behaviours"
    assert figure["ok"], f"the Qt console itself did not draw the figure: {figure}"
    from chisurf.emtk.console import ShellConsole

    console = ShellConsole({}, history_path=False, session_file=False)
    try:
        console.execute("import matplotlib.pyplot as plt; plt.plot([1, 2, 3]); plt.show()")
        transcript = console.transcript
        images = getattr(transcript, "images", [])
        images = images() if callable(images) else images
        text = "".join(str(line[0]) for line in getattr(transcript, "lines", []))
        assert images, f"no figure drawn in the emtk console; transcript ends: {text[-300:]!r}"
        assert "<Figure" not in text and "Line2D" not in text, text[-300:]
    finally:
        close = getattr(console, "close", None)
        if callable(close):
            close()
