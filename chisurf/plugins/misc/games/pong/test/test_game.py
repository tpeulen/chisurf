"""Pong's rules survived the move to the chigame engine.

The game holds no Qt and no GPU objects, so its whole simulation is steppable
here with a fixed timestep. Only the render check needs an adapter.
"""

from __future__ import annotations

import pytest

pytest.importorskip("wgpu")
pytest.importorskip("rendercanvas")

from chisurf.gui import chigame  # noqa: E402
from chisurf.gui.chigame.input import Action  # noqa: E402
from chisurf.plugins.misc.games.pong.pong import (  # noqa: E402
    FIELD_H,
    FIELD_W,
    PADDLE_H,
    WIN_SCORE,
    PongGame,
)


@pytest.fixture
def game(qapp):
    """A game wired to a headless host.

    Returns
    -------
    PongGame
        Ready to step.
    """
    try:
        context = chigame.create_offscreen(size=(160, 120))
    except Exception as error:  # pragma: no cover - depends on the machine
        pytest.skip(f"no usable GPU adapter: {error}")
    instance = PongGame()
    chigame.GameHost(instance, context, with_text=False, with_audio=False)
    return instance


def test_a_new_game_starts_level_and_serving(game):
    """Scores start at zero and the ball waits before launching."""
    assert (game.player_score, game.cpu_score) == (0, 0)
    assert game.serve_timer > 0.0
    assert game.ball_vx == 0.0 and game.ball_vy == 0.0


def test_the_serve_countdown_launches_the_ball(game):
    """After the delay the ball is moving."""
    for _ in range(120):
        game.update(1 / 60, game.host.keys)
    assert game.ball_vx != 0.0


def test_the_paddle_moves_and_stays_on_the_field(game):
    """Holding a direction moves the paddle, and it clamps at the edge."""
    start = game.paddle_y
    game.host.keys.press(Action.DOWN)
    for _ in range(10):
        game.update(1 / 60, game.host.keys)
    assert game.paddle_y > start

    for _ in range(600):
        game.update(1 / 60, game.host.keys)
    assert game.paddle_y <= FIELD_H - PADDLE_H * 0.5 + 1e-6


def test_a_ball_past_the_left_edge_scores_for_the_cpu(game):
    """Missing the ball concedes a point and re-serves."""
    game.serve_timer = 0.0
    game.ball_x = 5.0
    game.ball_y = FIELD_H * 0.9
    game.paddle_y = 20.0
    game.ball_vx = -400.0
    game.ball_vy = 0.0
    for _ in range(10):
        game.update(1 / 60, game.host.keys)
    assert game.cpu_score == 1
    assert game.serve_timer > 0.0


def test_the_ball_bounces_off_the_player_paddle(game):
    """A struck ball reverses, speeds up, and increments the rally."""
    game.serve_timer = 0.0
    game.paddle_y = FIELD_H * 0.5
    game.ball_y = FIELD_H * 0.5
    game.ball_x = 40.0
    game.ball_vx = -300.0
    game.ball_vy = 0.0
    for _ in range(20):
        game.update(1 / 60, game.host.keys)
        if game.ball_vx > 0:
            break
    assert game.ball_vx > 0.0
    assert game.rally == 1


def test_reaching_the_win_score_ends_the_game(game):
    """The winner is declared and play stops."""
    game.player_score = WIN_SCORE - 1
    game.serve_timer = 0.0
    # Out of play is a ball-width beyond the edge, not the edge itself.
    game.ball_x = FIELD_W + 40.0
    game.ball_vx = 400.0
    game.update(1 / 60, game.host.keys)
    assert game.winner == "Player"

    before = game.ball_x
    game.update(1 / 60, game.host.keys)
    assert game.ball_x == before, "the ball must not move after the game is over"


def test_menu_pauses_and_cancel_restarts(game):
    """The pad actions replace the old P and R keys."""
    game.host.keys.tap(Action.MENU)
    game.update(1 / 60, game.host.keys)
    assert game.paused is True

    game.host.keys.end_frame()
    game.player_score = 4
    game.host.keys.tap(Action.CANCEL)
    game.update(1 / 60, game.host.keys)
    assert game.player_score == 0 and game.paused is False


def test_shoulder_buttons_toggle_mode_and_sound(game):
    """Mode and mute are reachable without a keyboard."""
    assert game.vs_computer is True and game.muted is False
    game.host.keys.tap(Action.SHOULDER_L)
    game.update(1 / 60, game.host.keys)
    assert game.vs_computer is False

    game.host.keys.end_frame()
    game.host.keys.tap(Action.SHOULDER_R)
    game.update(1 / 60, game.host.keys)
    assert game.muted is True


def test_two_player_mode_gives_the_second_paddle_its_own_controller(game):
    """WASD drives the right-hand paddle only when the CPU is off."""
    game.vs_computer = False
    start = game.cpu_y
    game.p2.press(Action.DOWN)
    for _ in range(10):
        game.update(1 / 60, game.host.keys)
    assert game.cpu_y > start


def test_it_renders(qapp):
    """A frame comes out with the field drawn on it."""
    try:
        frame = chigame.capture(PongGame(), size=(320, 240), frames=3, with_audio=False)
    except Exception as error:  # pragma: no cover - depends on the machine
        pytest.skip(f"no usable GPU adapter: {error}")
    assert frame.shape == (240, 320, 4)
    # The net runs down the middle, so the centre column is brighter than the
    # empty quarter-width column beside it.
    assert int(frame[:, 160, :3].sum()) > int(frame[:, 80, :3].sum())
