"""Manifest validation for the Games hub."""

from pathlib import Path

from chisurf.core.plugin import load_manifest


def test_manifest_loads():
    manifest = load_manifest(Path(__file__).parents[1] / "manifest.json")

    assert manifest is not None
    assert manifest.id == "games"
    assert manifest.entrypoints.gui == "chisurf.plugins.misc.games.gui.tool:GamesWidget"
    assert manifest.menu_hidden is False


def test_the_gamespace_survives_the_demo_flag():
    """The games must never silently vanish again (BUGS 2026-08-08).

    The contract: the HUB stays in the menus regardless of
    ``plugins.show_demo_plugins`` (a user who opens the Games hub has chosen
    to play), every game is reachable inside it, and the individual games
    stay OUT of the production menus (``demo`` and/or ``menu_hidden``). A
    manifest edit that gates the hub as demo reads as "the games are gone"
    to anyone who does not know the flag exists.
    """
    from chisurf.plugins.misc.games.gui.tool import GAME_PANELS

    hub = load_manifest(Path(__file__).parents[1] / "manifest.json")
    assert hub.demo is False, "the hub must not be demo-gated"
    assert hub.menu_hidden is False, "the hub must stay in the menus"

    names = [p["name"] for p in GAME_PANELS]
    assert names == ["Number Quest", "Minesweeper", "Tetris", "Pong",
                     "Breakout", "Lumis Quest", "Ninja Adventure"]

    for game_dir in ("number_quest", "minesweeper", "tetris", "pong",
                     "breakout", "lumis_quest", "ninja_adventure"):
        m = load_manifest(Path(__file__).parents[1] / game_dir / "manifest.json")
        assert m.demo or m.menu_hidden, (
            f"{game_dir} would appear in the production menus"
        )
