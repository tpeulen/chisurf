"""Unit tests for GAMELOGIC pause menu tab, ImGui controls, and Ninja audio in Lumis Quest."""

from __future__ import annotations

import pytest
from chisurf.plugins.misc.games.lumis_quest.gui import overworld
from chisurf.gui.chigame import audio, assets


@pytest.fixture
def game():
    return overworld.OverworldGame()


def test_gamelogic_tab_presence_and_menu_rows(game):
    """GAMELOGIC tab exists in TABS and supplies menu rows."""
    assert "GAMELOGIC" in game.TABS
    game.menu_tab = game.TABS.index("GAMELOGIC")
    rows = game._menu_rows()
    assert len(rows) == 13
    assert "soundtrack:" in rows[0]
    assert "enemy aggro:" in rows[1]
    assert "sprint boost:" in rows[2]
    assert "encounter rate:" in rows[3]
    assert "action combat:" in rows[6]
    assert "particle effects:" in rows[7]
    assert "crt retro shader:" in rows[8]
    assert "ui accent tone:" in rows[9]


def test_gamelogic_confirm_and_stepping(game):
    """Confirming or stepping options in GAMELOGIC modifies game settings."""
    game.menu_tab = game.TABS.index("GAMELOGIC")

    # Row 0: Soundtrack combo
    game.menu_row = 0
    game._gamelogic_confirm(direction=1)
    assert game.soundtrack_theme == "Classic Chiptune"
    game._gamelogic_confirm(direction=1)
    assert game.soundtrack_theme == "Synthesiser"

    # Row 1: Enemy aggro slider
    game.menu_row = 1
    game._gamelogic_confirm(direction=1)
    assert pytest.approx(game.enemy_aggro_radius) == 5.0

    # Row 2: Sprint multiplier slider
    game.menu_row = 2
    game._gamelogic_confirm(direction=1)
    assert pytest.approx(game.sprint_multiplier) == 2.8

    # Row 3: Encounter rate slider
    game.menu_row = 3
    game._gamelogic_confirm(direction=1)
    assert pytest.approx(game.encounter_rate) == 1.1

    # Row 6: Action combat checkbox
    game.menu_row = 6
    initial_combat = game.action_combat_enabled
    game._gamelogic_confirm()
    assert game.action_combat_enabled is not initial_combat

    # Row 7: Particle effects checkbox
    game.menu_row = 7
    initial_fx = game.particle_fx_enabled
    game._gamelogic_confirm()
    assert game.particle_fx_enabled is not initial_fx

    # Row 8: CRT retro shader checkbox
    game.menu_row = 8
    initial_crt = game.crt_filter_enabled
    game._gamelogic_confirm()
    assert game.crt_filter_enabled is not initial_crt

    # Row 9: UI accent tone swatch
    game.menu_row = 9
    game._gamelogic_confirm(direction=1)
    assert game.ui_accent_tone == "Cyan"


def test_ninja_music_tracks_in_assets():
    """Verify Ninja Adventure music tracks are mapped in assets TRACKS."""
    assert assets.TRACKS["overworld"]["clip"] == "ninja_plain"
    assert assets.TRACKS["town"]["clip"] == "ninja_lost_village"
    assert assets.TRACKS["battle"]["clip"] == "ninja_dream"
    assert assets.TRACKS["underworld"]["clip"] == "ninja_swamp"


def test_ninja_music_clips_decoding():
    """Verify Ninja Adventure music clips load and decode properly."""
    for clip_name in ("ninja_plain", "ninja_lost_village", "ninja_dream", "ninja_swamp"):
        data = audio.clip(clip_name, "music")
        assert data is not None, f"Clip {clip_name} must be loadable"
        pcm, rate = data
        assert len(pcm) > 0
        assert rate == 22050
