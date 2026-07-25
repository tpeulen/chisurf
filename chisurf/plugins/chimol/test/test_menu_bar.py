"""PyMOL's main menu bar, as far as chimol can honour it.

PyMOL groups its functions as File / Edit / Build / Movie / Display / Setting /
Scene / Mouse / Wizard / Plugin / Help, and a PyMOL user looks for things by that
grouping. These tests pin two things: that the menus chimol *does* offer keep
PyMOL's name and position, and that nothing on the bar is a dead button.
"""

from __future__ import annotations

import pytest

from chisurf.plugins.chimol.chimol.app.menu_bar import (
    MENU_BAR,
    OMITTED_MENUS,
    build_menu_bar,
)

#: PyMOL's own bar, from pymol/_gui.py:get_menudata.
_PYMOL_BAR = ["File", "Edit", "Build", "Movie", "Display", "Setting", "Scene",
              "Mouse", "Wizard", "Plugin", "Help"]


def test_the_bar_keeps_pymols_names_and_order():
    ours = [title for title, _ in MENU_BAR]
    assert ours == [t for t in _PYMOL_BAR if t not in OMITTED_MENUS]


def test_omitted_menus_are_the_ones_chimol_cannot_fill():
    """A menu is dropped only when chimol has nothing at all to put in it."""
    assert set(OMITTED_MENUS) == {"Build", "Movie", "Scene", "Wizard", "Plugin"}
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
    body = source[source.index("def get_menudata"):]
    live = [
        m.group(1)
        for m in re.finditer(r"^            \('menu', '([^']+)'", body, re.M)
    ]
    assert live == _PYMOL_BAR


# --------------------------------------------------------------------------- #
# Wiring
# --------------------------------------------------------------------------- #
def test_every_command_is_a_registered_chimol_command():
    from chisurf.plugins.chimol.chimol.cmd.command import Cmd

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
    from chisurf.plugins.chimol.chimol import settings

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
# On a real window
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_the_bar_installs_and_acts(qapp):
    from qtpy import QtWidgets

    from chisurf.plugins.chimol.chimol.config import _DISPLAY_CONFIG

    issued: list[str] = []
    window = QtWidgets.QMainWindow()
    bar = build_menu_bar(window, issued.append)
    assert [a.text() for a in bar.actions()] == [t for t, _ in MENU_BAR]

    setting = next(a.menu() for a in bar.actions() if a.text() == "Setting")
    occlusion = next(
        a.menu() for a in setting.actions() if a.text() == "Ambient Occlusion"
    )
    next(a for a in occlusion.actions() if a.text() == "Off").trigger()
    assert issued == ["set occlusion.enabled, off"]
    assert _DISPLAY_CONFIG is not None  # imported for the reader's benefit


def test_a_special_entry_calls_its_handler(qapp):
    from qtpy import QtWidgets

    calls: list[str] = []
    window = QtWidgets.QMainWindow()
    bar = build_menu_bar(
        window, calls.append, special={"config": lambda: calls.append("dialog")}
    )
    setting = next(a.menu() for a in bar.actions() if a.text() == "Setting")
    next(a for a in setting.actions() if a.text() == "Edit All...").trigger()
    assert calls == ["dialog"]
