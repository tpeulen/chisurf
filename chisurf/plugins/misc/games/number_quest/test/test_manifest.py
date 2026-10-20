"""Metadata checks for the internal Number Quest plugin."""

from pathlib import Path

from chisurf.core.plugin import load_manifest


def test_manifest_is_a_listed_games_button_and_loads():
    # Since fb08bbdd4 (games hub removed) each game is its own Tools > Games button:
    # listed in the ribbon and not demo-gated, or it would be unreachable.
    manifest = load_manifest(Path(__file__).parents[1] / "manifest.json")

    assert manifest is not None
    assert manifest.id == "number_quest"
    assert manifest.menu_hidden is False
    assert manifest.demo is False
    assert manifest.display_name.startswith("Tools:Games:")
