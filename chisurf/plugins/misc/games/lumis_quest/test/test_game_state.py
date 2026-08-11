"""XP is the source of truth, and a headless run must never touch the real one."""

from __future__ import annotations

from chisurf.plugins.misc.games.lumis_quest.api import game_state


def test_a_custom_path_keeps_a_test_off_the_real_file(tmp_path):
    """load()/save() default to the real file; a caller can always override it."""
    custom = tmp_path / "state.json"
    state = game_state.GameState.load(path=custom)
    assert state.path == custom
    assert not game_state.STATE_FILE.exists(), "loading must not create the real file"

    state.xp = 42
    state.save()
    assert custom.exists()
    assert not game_state.STATE_FILE.exists(), "saving must not touch the real file either"

    reloaded = game_state.GameState.load(path=custom)
    assert reloaded.xp == 42


def test_record_review_pays_xp_and_can_level_up(tmp_path):
    """The variable-ratio schedule always pays something, and a big enough
    haul crosses a level threshold."""
    state = game_state.GameState.load(path=tmp_path / "state.json")
    assert state.level == 1

    total = 0
    for _ in range(20):
        reward = state.record_review(difficulty="expert", is_first_ever=True)
        assert reward["xp"] > 0
        total += reward["xp"]
    assert state.xp == total
    assert state.level > 1, "twenty expert-difficulty reviews should clear level 1"


def test_level_progress_is_zero_span_at_the_top(tmp_path):
    """The last level has nothing further to grind toward."""
    state = game_state.GameState.load(path=tmp_path / "state.json")
    state.xp = game_state.LEVELS[-1][0] + 1
    assert state.level == len(game_state.LEVELS)
    assert state.level_progress == (0, 0)


def test_a_wrong_answer_or_training_mode_never_reaches_record_review():
    """The caller (OverworldGame) only calls record_review on a real sign-off
    -- this just documents the contract the wiring in overworld.py depends on."""
    from chisurf.plugins.misc.games.lumis_quest.api import review_bridge

    verdict = review_bridge.Verdict(False, "Training run -- nothing signed off.", "training")
    assert not verdict.signed_off
