"""Metadata checks for the internal Breakout plugin."""

from pathlib import Path

from chisurf.core.plugin import load_manifest


def test_manifest_is_hidden_and_loads():
    manifest = load_manifest(Path(__file__).parents[1] / "manifest.json")

    assert manifest is not None
    assert manifest.id == "breakout"
    assert manifest.entrypoints.emtk == "chisurf.plugins.misc.games.breakout.app:make_app"
    assert not manifest.entrypoints.gui
    assert manifest.menu_hidden is True
