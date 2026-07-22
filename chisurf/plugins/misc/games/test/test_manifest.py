"""Manifest validation for the Games hub."""

from pathlib import Path

from chisurf.core.plugin import load_manifest


def test_manifest_loads():
    manifest = load_manifest(Path(__file__).parents[1] / "manifest.json")

    assert manifest is not None
    assert manifest.id == "games"
    assert manifest.entrypoints.gui == "chisurf.plugins.misc.games.gui.tool:GamesWidget"
    assert manifest.menu_hidden is False
