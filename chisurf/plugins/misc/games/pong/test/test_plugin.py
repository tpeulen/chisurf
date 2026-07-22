"""Metadata checks for the internal Pong plugin."""

import importlib
from pathlib import Path

from chisurf.core.plugin import load_manifest


def test_pong_plugin_import():
    module = importlib.import_module("chisurf.plugins.misc.games.pong")
    assert module is not None


def test_manifest_is_hidden_and_loads():
    manifest = load_manifest(Path(__file__).parents[1] / "manifest.json")

    assert manifest is not None
    assert manifest.id == "pong"
    assert manifest.entrypoints.gui == "chisurf.plugins.misc.games.pong.pong:Pong"
    assert manifest.menu_hidden is True
