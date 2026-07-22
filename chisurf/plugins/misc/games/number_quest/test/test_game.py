"""Tests for Number Quest game rules."""

import pytest

from chisurf.plugins.misc.games.number_quest.core import GuessStatus, NumberQuestGame


def test_game_guides_the_player_to_the_target():
    game = NumberQuestGame(target=42)

    low = game.guess(20)
    high = game.guess(70)
    won = game.guess(42)

    assert low.message == "Higher! Try again."
    assert high.message == "Lower! Try again."
    assert won.status is GuessStatus.WON
    assert won.attempts_remaining == 4
    assert won.score == 700


def test_game_reveals_the_target_after_the_final_attempt():
    game = NumberQuestGame(target=100)

    for _ in range(game.max_attempts - 1):
        game.guess(1)
    result = game.guess(1)

    assert result.status is GuessStatus.LOST
    assert result.attempts_remaining == 0
    assert result.message == "Out of turns — the number was 100."


def test_game_rejects_out_of_range_guesses():
    game = NumberQuestGame(target=50)

    with pytest.raises(ValueError, match="guess must be between 1 and 100"):
        game.guess(101)
