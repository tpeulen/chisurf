"""The games are five plugins of their own, each a button of Tools › Games."""

import importlib
from pathlib import Path

import pytest

from chisurf.core.plugin import load_manifest

GAMES = Path(__file__).parents[1]
NAMES = {
    "number_quest": "Number Quest",
    "minesweeper": "Minesweeper",
    "tetris": "Tetris",
    "pong": "Pong",
    "breakout": "Breakout",
}


def test_the_package_is_not_a_plugin():
    """There is no Games hub any more: the package only holds what the games share."""
    assert not (GAMES / "manifest.json").exists()
    assert not (GAMES / "gui").exists()


@pytest.mark.parametrize("game", sorted(NAMES))
def test_every_game_is_its_own_ribbon_button(game):
    """The games must never silently vanish again (BUGS 2026-08-08).

    With the hub gone, a game that is ``menu_hidden`` or demo-gated is unreachable
    from the GUI, which reads as "the games are gone" to anyone who does not know
    the flag exists.
    """
    manifest = load_manifest(GAMES / game / "manifest.json")
    assert manifest is not None
    assert manifest.display_name == "Tools:Games:" + NAMES[game]
    assert manifest.menu_hidden is False
    assert manifest.demo is False
    assert "games" not in (manifest.requires or {})
    module, factory = manifest.entrypoints.emtk.split(":")
    assert callable(getattr(importlib.import_module(module), factory))
