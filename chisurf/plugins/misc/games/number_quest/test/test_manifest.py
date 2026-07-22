"""Metadata checks for the internal Number Quest plugin."""

from pathlib import Path

from chisurf.core.plugin import load_manifest


def test_manifest_is_hidden_and_loads():
    manifest = load_manifest(Path(__file__).parents[1] / "manifest.json")

    assert manifest is not None
    assert manifest.id == "number_quest"
    assert manifest.menu_hidden is True
