"""Metadata checks for the internal Pong plugin."""

import importlib
from pathlib import Path

from chisurf.core.plugin import load_manifest


def test_pong_plugin_import():
    module = importlib.import_module("chisurf.plugins.misc.games.pong")
    assert module is not None


def test_manifest_is_a_listed_games_button_and_loads():
    # Since fb08bbdd4 (games hub removed) each game is its own Tools > Games button:
    # listed in the ribbon and not demo-gated, or it would be unreachable.
    manifest = load_manifest(Path(__file__).parents[1] / "manifest.json")

    assert manifest is not None
    assert manifest.id == "pong"
    assert manifest.entrypoints.emtk == "chisurf.plugins.misc.games.pong.app:make_app"
    assert not manifest.entrypoints.gui
    assert manifest.menu_hidden is False
    assert manifest.demo is False
    assert manifest.display_name.startswith("Tools:Games:")
