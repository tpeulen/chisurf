"""PyMOL's main menu bar, as far as chimol can honour it.

PyMOL groups its functions as File / Edit / Build / Movie / Display / Setting /
Scene / Mouse / Wizard / Plugin / Help, and a PyMOL user looks for things by that
grouping. These tests pin two things: that the menus chimol *does* offer keep
PyMOL's name and position, and that nothing on the bar is a dead button.
"""

from __future__ import annotations

import pytest
from chimol.ui.menus.bar import (
    EXTRA_MENUS,
    MENU_BAR,
    OMITTED_MENUS,
)

#: PyMOL's own bar, from pymol/_gui.py:get_menudata.
_PYMOL_BAR = [
    "File",
    "Edit",
    "Build",
    "Movie",
    "Display",
    "Setting",
    "Scene",
    "Mouse",
    "Wizard",
    "Plugin",
    "Help",
]


def test_the_bar_keeps_pymols_names_and_order():
    """PyMOL's menus keep PyMOL's order; chimol's own menus sit between them.

    The extras are declared, not inferred: a menu chimol invents (Demo,
    Tools) must be listed in EXTRA_MENUS or this fails, so the bar cannot
    quietly drift away from the PyMOL layout users navigate by. The same goes
    for one that leaves the bar: it is either OMITTED (chimol cannot fill it)
    or FOLDED (it is complete, one level down), and both are declared.
    """
    from chimol.ui.menus.bar import FOLDED_MENUS

    ours = [title for title, _ in MENU_BAR if title not in EXTRA_MENUS]
    assert ours == [t for t in _PYMOL_BAR if t not in OMITTED_MENUS and t not in FOLDED_MENUS]
    assert not (set(FOLDED_MENUS) & set(OMITTED_MENUS)), (
        "a menu is either folded or omitted, not both"
    )
    on_bar = {title for title, _ in MENU_BAR}
    assert EXTRA_MENUS <= on_bar, "an extra menu is declared but not built"
    assert not (EXTRA_MENUS & set(_PYMOL_BAR)), "a menu PyMOL also has cannot be an extra"


def test_omitted_menus_are_the_ones_chimol_cannot_fill():
    """A menu is dropped only when chimol has nothing at all to put in it."""
    assert set(OMITTED_MENUS) == {"Movie", "Scene", "Plugin", "Mouse"}
    for title, reason in OMITTED_MENUS.items():
        assert reason, f"{title} is omitted without a reason"


def test_no_menu_on_the_bar_is_empty():
    """An empty menu is a promise with nothing behind it."""
    for title, entries in MENU_BAR:
        assert entries, title
        assert any(not e.is_separator for e in entries), title


def test_the_bar_matches_a_live_pymol():
    """Guards `_PYMOL_BAR` from drifting away from PyMOL itself.

    `get_menudata` needs a real GUI instance for the New Window submenu, so the
    bar is read from the source text rather than by calling it.
    """
    pymol = pytest.importorskip("pymol")
    import pathlib
    import re

    source = (pathlib.Path(pymol.__file__).parent / "_gui.py").read_text()
    body = source[source.index("def get_menudata") :]
    live = [m.group(1) for m in re.finditer(r"^            \('menu', '([^']+)'", body, re.M)]
    assert live == _PYMOL_BAR


# --------------------------------------------------------------------------- #
# Wiring
# --------------------------------------------------------------------------- #
def test_every_command_is_a_registered_chimol_command():
    from chimol.commands.command import Cmd

    known = set(Cmd().command_names())

    def walk(entries):
        for entry in entries:
            if entry.is_separator:
                continue
            if entry.children:
                walk(entry.children)
                continue
            if not entry.command or entry.command.startswith("__"):
                continue
            for line in entry.command.split(";"):
                head = line.strip().split()[0].split(",")[0].lower()
                assert head in known, f"{entry.label!r} runs unknown '{head}'"

    for _, entries in MENU_BAR:
        walk(entries)


def test_every_setting_named_by_the_bar_exists():
    """`set <name>` entries must name a real setting, or they fail on click."""
    from chimol.core.settings import registry as settings

    def walk(entries):
        for entry in entries:
            if entry.is_separator:
                continue
            if entry.children:
                walk(entry.children)
                continue
            for line in (entry.command or "").split(";"):
                line = line.strip()
                if not line.startswith(("set ", "unset ")):
                    continue
                name = line.split(None, 1)[1].split(",")[0].strip()
                settings.resolve(name)  # raises if unknown

    for _, entries in MENU_BAR:
        walk(entries)


def test_disabled_entries_explain_themselves():
    def walk(entries):
        for entry in entries:
            if entry.is_separator:
                continue
            if entry.children:
                walk(entry.children)
                continue
            if entry.command is None:
                assert entry.note, f"{entry.label!r} is disabled without a reason"

    for _, entries in MENU_BAR:
        walk(entries)


# --------------------------------------------------------------------------- #
# On a real window: the bar the viewport draws
# --------------------------------------------------------------------------- #
def _press(gui, rect) -> None:
    """Click the middle of *rect* the way a pointer does."""
    x, y = rect.x + rect.w / 2, rect.y + rect.h / 2
    gui.mouse_move(x, y)
    gui.mouse_press(x, y)


def _row(gui, label):
    """The open menu's row labelled *label* (its rect)."""
    for rect, entry in gui._menus[-1].item_rects:
        if entry.label == label:
            return rect
    raise AssertionError(f"no {label!r} in {gui._menus[-1].title!r}")


@pytest.fixture
def window():
    from native_window import NativeWindow

    win = NativeWindow(size=(1000, 700))
    yield win
    win.close()


def test_the_bar_installs_and_acts(window):
    """The host's bar is the shipped bar plus what plugins contribute, and acts.

    Pressed through the viewport's own menu bar -- title, submenu row, entry --
    the path a pointer takes, ending in the command the entry names.
    """
    from chimol.ui.menus.bar import menu_bar

    gui = window.viewer.gui
    issued: list[str] = []
    gui.set_run_command(issued.append)
    gui.layout(*window.size)

    installed = [t for t, _ in menu_bar()]
    assert [title for title, _entries in gui.menubar] == installed
    assert installed[: len(MENU_BAR)] == [t for t, _ in MENU_BAR]

    setting = next(rect for rect, title, _e in gui._menubar_rects if title == "Setting")
    _press(gui, setting)
    assert gui._menus and gui._menus[-1].title.startswith("Setting")
    _press(gui, _row(gui, "Ambient Occlusion"))
    assert gui._menus[-1].title.startswith("Ambient Occlusion")
    _press(gui, _row(gui, "Off"))
    assert issued == ["set occlusion.enabled, off"]
