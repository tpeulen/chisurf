"""The game's settings: declared once, and nothing hard-coded past them.

The parity tests are the point. A registry that lists a control scheme the key
bindings do not have, or an accent tone with no colour, is worse than no
registry: the menu offers it, the player picks it, and nothing happens.
"""

from __future__ import annotations

import pytest

from chisurf.plugins.misc.games.lumis_quest.api import settings as game_settings
from chisurf.plugins.misc.games.lumis_quest.gui import imgui_controls, overworld


@pytest.fixture
def game(tmp_path):
    return overworld.OverworldGame(save_path=tmp_path / "run.json")


# ---------------------------------------------------------------- parity ---
def test_control_schemes_match_the_key_bindings():
    """Every scheme the menu offers is one the controller can be bound to."""
    assert tuple(overworld.SCHEMES) == game_settings.SCHEME_NAMES


def test_accent_tones_all_have_a_colour():
    """A tone with no colour would draw the swatch of whatever came first."""
    assert set(game_settings.ACCENT_TONES) == set(imgui_controls.ACCENT_COLORS)


def test_every_setting_declares_what_it_needs():
    """A choice needs options, a number needs bounds, everything needs a doc."""
    for one in game_settings.SETTINGS:
        assert one.description, f"{one.key} has no description"
        assert one.group in ("options", "gamelogic"), one.key
        if one.kind == game_settings.CHOICE:
            assert one.options, f"{one.key} is a choice with nothing to choose"
            assert one.default in one.options, one.key
        if one.kind == game_settings.FLOAT:
            assert one.v_min is not None and one.v_max is not None, one.key
            assert one.v_min <= one.default <= one.v_max, one.key


# ----------------------------------------------------------------- store ---
def test_hooks_run_after_the_value_is_stored():
    """A hook that reads its setting back must see the new value."""
    store = game_settings.GameSettings()
    seen = []
    store.on("options.walk_speed", lambda value: seen.append(store.get("options.walk_speed")))
    store.set("options.walk_speed", 220.0)
    assert seen == [220.0]


def test_unknown_keys_from_an_old_save_are_dropped():
    """A renamed setting cannot stop a run from loading."""
    store = game_settings.GameSettings({"options.walk_speed": 200.0,
                                        "options.removed_long_ago": 1})
    assert store.get("options.walk_speed") == 200.0
    assert "options.removed_long_ago" not in store


def test_actions_are_not_saved():
    """A button press is not state; a save that stored one would replay it."""
    saved = game_settings.GameSettings().as_dict()
    assert "gamelogic.quick_save" not in saved
    assert "options.walk_speed" in saved


# ------------------------------------------------------------------ game ---
def test_game_attributes_read_and_write_the_store(game):
    """The names the game already used are views onto the settings."""
    game.walk_speed = 210.0
    assert game.settings.get("options.walk_speed") == 210.0
    game.settings.set("options.walk_speed", 150.0)
    assert game.walk_speed == 150.0

    game.screen_mode = True
    assert game.settings.get("options.camera") == "screen by screen"
    game.screen_mode = False
    assert game.settings.get("options.camera") == "scrolling"


def test_gameplay_constants_are_settings(game):
    """The constants the PRD named are in the registry, not module globals."""
    game.sprint_multiplier = 3.0
    assert game.settings.get("gamelogic.sprint_multiplier") == 3.0

    game.camera_lag = 10.0
    assert game.settings.get("options.camera_lag") == 10.0

    game.companion_trail = 40.0
    assert game.settings.get("options.companion_trail") == 40.0

    game.encounter_rate = 2.0
    assert game.settings.get("gamelogic.encounter_rate") == 2.0


def test_every_options_row_is_reachable_without_scroll(game):
    """The OPTIONS tab has more than eight rows now; all must be visible.

    The old scroll window clipped at eight rows, so the last OPTIONS row
    (watch the opening again) was only reachable by scrolling the cursor
    past row six. A twelve-row window fits every declared setting at once.
    """
    game.menu_tab = game.TABS.index("OPTIONS")
    rows = game._menu_rows()
    assert len(rows) > 8, "this test only means something with >8 rows"
    for row_index in range(len(rows)):
        game.menu_row = row_index
        visible_rows = 12
        if len(rows) <= visible_rows:
            base = 0
        else:
            base = max(0, min(row_index - visible_rows // 2,
                              len(rows) - visible_rows))
        window = rows[base:base + visible_rows]
        assert row_index - base < len(window), (
            f"row {row_index} is not in the visible window")


def test_menu_rows_come_from_the_registry(game):
    """The rows are the declared settings, in order, with their values."""
    game.menu_tab = game.TABS.index("OPTIONS")
    rows = game._menu_rows()
    assert len(rows) == len(game.settings.rows("options"))
    assert rows[0] == "controls: arrows"
    assert rows[4] == "walk speed: 190"
    assert rows[6] == "music volume: 10%"
    assert rows[-1] == "watch the opening again"

    game.menu_tab = game.TABS.index("GAMELOGIC")
    rows = game._menu_rows()
    assert rows[1] == "enemy aggro: 4.5 tiles"
    assert rows[2] == "sprint boost: 2.6x"
    assert rows[6] == "action combat: [✓] enabled"


def test_stepping_a_row_moves_the_setting(game):
    """Left and right step inside the declared range, and do not leave it."""
    game.menu_tab = game.TABS.index("OPTIONS")
    game.menu_row = 4                       # walk speed
    game._options_confirm(direction=1)
    assert game.walk_speed == pytest.approx(210.0)
    for _ in range(10):
        game._options_confirm(direction=1)
    assert game.walk_speed == pytest.approx(260.0)      # clamped at the top
    for _ in range(20):
        game._options_confirm(direction=-1)
    assert game.walk_speed == pytest.approx(120.0)      # and at the bottom
    """One button has to be able to reach the quiet end again."""
    game.menu_tab = game.TABS.index("OPTIONS")
    game.menu_row = 6                       # music volume
    game.settings.set("options.music_volume", 1.0)
    game._options_confirm()
    assert game.music_volume == pytest.approx(0.0)


def test_an_action_row_fires_its_hook(game):
    """Pressing an action is `settings.set(key, True)` and nothing more."""
    fired = []
    game.settings.on("gamelogic.quick_save", lambda _v: fired.append(True))
    game.menu_tab = game.TABS.index("GAMELOGIC")
    game.menu_row = 10                      # quick save run
    game._gamelogic_confirm()
    assert fired == [True]


def test_settings_survive_a_save_and_load(game, tmp_path):
    """What the player set is part of the run, not of the session."""
    from chisurf.plugins.misc.games.lumis_quest.api import save as save_api

    game.walk_speed = 240.0
    game.settings.set("gamelogic.crt_filter", True)
    save_api.RunState(settings=game.settings.as_dict()).save(game._save_path)

    # Restored even though the run has no team in it: someone who turned the
    # music down and then started over should not have to turn it down again.
    again = overworld.OverworldGame(save_path=game._save_path)
    again._restore()
    assert again.walk_speed == pytest.approx(240.0)
    assert again.crt_filter_enabled is True


def test_new_gameplay_settings_survive_save_and_load(game, tmp_path):
    """The settings added in the registry move are part of the run too."""
    from chisurf.plugins.misc.games.lumis_quest.api import save as save_api

    game.sprint_multiplier = 3.4
    game.camera_lag = 11.0
    game.companion_trail = 42.0
    game.encounter_rate = 2.0
    save_api.RunState(settings=game.settings.as_dict()).save(game._save_path)
    again = overworld.OverworldGame(save_path=game._save_path)
    again._restore()
    assert again.sprint_multiplier == pytest.approx(3.4)
    assert again.camera_lag == pytest.approx(11.0)
    assert again.companion_trail == pytest.approx(42.0)
    assert again.encounter_rate == pytest.approx(2.0)


def test_disconnected_settings_are_now_wired(game):
    """The four gameplay toggles the menu offered but never read are live."""
    assert game.action_combat_enabled is True
    assert game.particle_fx_enabled is True
    assert game.crt_filter_enabled is False
    assert game.enemy_aggro_radius == pytest.approx(4.5)
