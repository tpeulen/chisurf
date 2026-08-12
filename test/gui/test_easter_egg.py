"""The hidden way into Lumis Quest.

The sequence matching is deliberately Qt-free, because a code that can only be
entered through a real key event is a code nobody can test -- and an easter egg
that quietly stopped working is one nobody would report.
"""

from __future__ import annotations

from chisurf.gui import easter_egg


def _feed(watcher, keys) -> int:
    """Enter a run of keys and report how many times the code fired."""
    return sum(1 for key in keys if watcher.feed(key))


def test_the_code_fires_once_when_it_is_entered():
    fired = []
    watcher = easter_egg.CodeWatcher(easter_egg.KONAMI, lambda: fired.append(True))
    assert _feed(watcher, easter_egg.KONAMI) == 1
    assert fired == [True]
    # And it is ready to be entered again straight away.
    assert _feed(watcher, easter_egg.KONAMI) == 1


def test_a_wrong_key_does_not_fire():
    fired = []
    watcher = easter_egg.CodeWatcher(easter_egg.KONAMI, lambda: fired.append(True))
    _feed(watcher, ["Up", "Up", "Down", "X", "Down", "Left"])
    assert fired == []


def test_a_false_start_restarts_the_match_rather_than_dropping_it():
    """`Up Up Up Down …` still counts -- it is how people actually type it."""
    fired = []
    watcher = easter_egg.CodeWatcher(easter_egg.KONAMI, lambda: fired.append(True))
    assert _feed(watcher, ("Up",) + easter_egg.KONAMI) == 1


def test_typing_something_else_entirely_never_fires():
    fired = []
    watcher = easter_egg.CodeWatcher(easter_egg.KONAMI, lambda: fired.append(True))
    _feed(watcher, list("the quick brown fox"))
    assert fired == []


def test_install_is_a_no_op_without_an_application():
    """Headless callers get None rather than an import error."""
    assert easter_egg.install(None) is None


def test_the_game_stays_out_of_the_menu():
    """If it were listed, it would not be hidden -- and this would be pointless."""
    import json
    import pathlib

    manifest = json.loads(
        (pathlib.Path(__file__).resolve().parents[2]
         / "chisurf/plugins/misc/games/lumis_quest/manifest.json").read_text()
    )
    assert manifest["menu_hidden"] is True
