"""The demos are in the menu, and reachable by command.

They were on a Qt-only `&Demo` menu built by hand beside the main bar — which
on macOS lives in the *system* bar and in a browser does not exist — and there
was **no command** behind them, so nothing but that menu could start one.

Now `demo <key>` runs one, `demo` lists them, and the menu is *generated* from
the same `DEMOS` table: a demo added there and forgotten here would otherwise
ship and be unreachable.
"""

from __future__ import annotations

import pytest
from chimol.plugins.demos.catalog import DEMOS
from chimol.ui.menus.bar import DEMO_MENU, MENU_BAR


def test_the_bar_has_a_demo_menu():
    assert "Demo" in [title for title, entries in MENU_BAR if entries]


def _walk(entries):
    """Every entry, submenus included (the PetWorld demos have one)."""
    for entry in entries:
        yield entry
        yield from _walk(getattr(entry, "children", None) or ())


def test_every_shipped_demo_is_on_the_menu():
    """Generated, not transcribed, so this cannot drift."""
    commands = {entry.command for entry in _walk(DEMO_MENU) if entry.command}
    for key, _title, _note in DEMOS:
        assert f"demo {key}" in commands, f"{key} ships and is unreachable"


def test_each_entry_carries_its_description():
    notes = {entry.label: entry.note for entry in _walk(DEMO_MENU) if entry.command}
    for _key, title, note in DEMOS:
        assert notes.get(title) == note


def test_the_editor_entries_are_there_and_run_something():
    labels = {entry.label: entry.command for entry in DEMO_MENU}
    assert labels.get("Edit a demo script…") == "demo_edit"
    assert labels.get("New script…") == "demo_edit new"


def test_the_viewport_bar_lists_demo_exactly_once(window):
    """It was built twice for a while: once from MENU_BAR, once bolted on.

    Asserted against the **viewport** bar, the only bar a window has: the Qt
    one drew a second copy of these same menus directly above them, which is
    exactly the duplication this test exists to catch, one level up.
    """
    win = window
    gui = win.viewer.gui
    titles = [title for title, _entries in gui.menubar]
    assert titles.count("Demo") == 1


@pytest.fixture(scope="module")
def window():
    from native_window import NativeWindow

    win = NativeWindow(size=(900, 620))
    win.pump(3)
    yield win
    win.close()


def test_demo_with_no_argument_lists_them(window):
    """In the info panel -- the same window `help` uses -- not the prompt.

    The prompt's feedback line holds one line at a time and the demo list is
    ten of them; listing there scrolled the whole catalogue away. Each entry
    also carries its `demo <key>` command, so a click on a name runs it.
    """
    shared = window.cmd

    said: list[str] = []
    shared.set_message_callback(said.append)
    shared.set_error_callback(said.append)

    window.run_menu_command("demo")
    gui = window.viewer.gui
    assert gui._info_title == "Demos"
    assert [name for name, _doc in gui._info_items] == [key for key, _t, _n in DEMOS]
    for key, _t, _n in DEMOS:
        assert gui._info_commands.get(key) == f"demo {key}"


def test_an_unknown_demo_says_so_rather_than_doing_nothing(window):
    shared = window.cmd

    errors: list[str] = []
    shared.set_message_callback(lambda _m: None)
    shared.set_error_callback(errors.append)

    window.run_menu_command("demo nonesuch")
    assert errors and "no demo called" in errors[-1]


def test_the_demo_menu_is_reachable_in_the_viewport(window):
    gui = window.viewer.gui
    titles = [title for _rect, title, _entries in gui._menubar_rects]
    assert "Demo" in titles

    assert gui.open_menubar(titles.index("Demo"))
    opened = gui._menus[-1]
    assert opened.title.startswith("Demo")
    labels = [e.label for _r, e in opened.item_rects if e is not None]
    assert "EMDB density map" in labels
