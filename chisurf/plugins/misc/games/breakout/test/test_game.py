"""Breakout's rules survived the move to the chigame engine."""

from __future__ import annotations

import pytest

pytest.importorskip("wgpu")
pytest.importorskip("rendercanvas")

from chisurf.gui import chigame  # noqa: E402
from chisurf.gui.chigame.input import Action  # noqa: E402
from chisurf.plugins.misc.games.breakout.breakout import (  # noqa: E402
    BRICK_COLS,
    BRICK_ROWS,
    H,
    LIVES,
    PADDLE_W,
    W,
    BreakoutGame,
)


@pytest.fixture
def game(qapp):
    """A game wired to a headless host.

    Returns
    -------
    BreakoutGame
        Ready to step.
    """
    try:
        context = chigame.create_offscreen(size=(160, 130))
    except Exception as error:  # pragma: no cover - depends on the machine
        pytest.skip(f"no usable GPU adapter: {error}")
    instance = BreakoutGame()
    chigame.GameHost(instance, context, with_text=False, with_audio=False)
    return instance


def test_the_level_is_a_full_brick_grid(game):
    """Every row and column is laid out, and all bricks start alive."""
    assert len(game.bricks) == BRICK_ROWS * BRICK_COLS
    assert all(brick.alive for brick in game.bricks)
    assert game.lives == LIVES and game.score == 0 and game.level == 1


def test_the_ball_sticks_to_the_paddle_until_launched(game):
    """A served ball tracks the paddle, then leaves on Confirm."""
    assert game.stuck
    game.host.keys.press(Action.RIGHT)
    for _ in range(10):
        game.update(1 / 60, game.host.keys)
    assert game.ball_x == pytest.approx(game.paddle_x)

    game.host.keys.end_frame()
    game.host.keys.tap(Action.CONFIRM)
    game.update(1 / 60, game.host.keys)
    assert not game.stuck and game.ball_vy < 0.0, "the ball must launch upward"


def test_the_paddle_clamps_to_the_field(game):
    """Holding a direction cannot walk the paddle off the edge."""
    game.host.keys.press(Action.LEFT)
    for _ in range(600):
        game.update(1 / 60, game.host.keys)
    assert game.paddle_x == pytest.approx(PADDLE_W * 0.5)


def test_hitting_a_brick_scores_and_bounces(game):
    """A struck brick loses a hit, the ball reverses, and hard rows take two."""
    game.stuck = False
    brick = game.bricks[0]
    hp_before = brick.hp
    game.ball_x = brick.x
    game.ball_y = brick.y + brick.h * 0.5
    game.ball_vx = 0.0
    game.ball_vy = -200.0
    game.update(1 / 60, game.host.keys)
    assert brick.hp == hp_before - 1
    assert game.ball_vy > 0.0, "the ball must bounce back down off the underside"


def test_a_two_hit_brick_survives_the_first_strike(game):
    """The top rows are harder, which is what makes clearing downward progress."""
    top = game.bricks[0]
    assert top.max_hp == 2
    assert top.hit() is False
    assert top.hit() is True


def test_losing_the_ball_costs_a_life_and_re_serves(game):
    """Dropping the ball re-serves until lives run out."""
    game.stuck = False
    game.ball_y = H + 50.0
    game.ball_vy = 300.0
    game.update(1 / 60, game.host.keys)
    assert game.lives == LIVES - 1
    assert game.stuck, "a lost ball must re-serve"


def test_running_out_of_lives_ends_the_game(game):
    """The last life produces a message and stops play."""
    game.lives = 1
    game.stuck = False
    game.ball_y = H + 50.0
    game.ball_vy = 300.0
    game.update(1 / 60, game.host.keys)
    assert game.message == "Sample bleached"

    before = game.ball_y
    game.update(1 / 60, game.host.keys)
    assert game.ball_y == before, "play must stop once the game is over"


def test_clearing_every_brick_advances_the_level(game):
    """An empty grid rebuilds and increments the level."""
    for brick in game.bricks:
        brick.hp = 0
    game.stuck = False
    game._hit_bricks()
    assert game.level == 2
    assert len(game.bricks) == BRICK_ROWS * BRICK_COLS
    assert all(brick.alive for brick in game.bricks)


def test_menu_pauses_and_cancel_restarts(game):
    """The pad actions replace the old P and R keys."""
    game.host.keys.tap(Action.MENU)
    game.update(1 / 60, game.host.keys)
    assert game.paused is True

    game.host.keys.end_frame()
    game.score = 500
    game.host.keys.tap(Action.CANCEL)
    game.update(1 / 60, game.host.keys)
    assert game.score == 0 and game.paused is False


def test_it_renders(qapp):
    """A frame comes out with the brick wall on it."""
    try:
        frame = chigame.capture(BreakoutGame(), size=(400, 325), frames=2, with_audio=False)
    except Exception as error:  # pragma: no cover - depends on the machine
        pytest.skip(f"no usable GPU adapter: {error}")
    assert frame.shape == (325, 400, 4)
    # The wall occupies the upper quarter; the empty middle must be darker.
    wall = int(frame[40, :, :3].sum())
    empty = int(frame[220, :, :3].sum())
    assert wall > empty * 3, (wall, empty)


def test_the_wall_is_a_spectrum_and_hardness_follows_photon_energy():
    """Rows run violet to red, and the energetic rows are the hard ones.

    Row hardness is not a curve someone picked: it is derived from 1/lambda, so
    "bluer" and "tougher" are the same fact rather than two to memorise.
    """
    from chisurf.gui.chigame.assets import photon_energy_rank
    from chisurf.plugins.misc.games.breakout.breakout import ROW_HARDNESS, ROW_NM

    assert ROW_NM == sorted(ROW_NM), "the wall must run short to long wavelength"
    assert len(set(ROW_NM)) == BRICK_ROWS, "every band needs its own wavelength"
    for nm, hardness in zip(ROW_NM, ROW_HARDNESS):
        assert hardness == (2 if photon_energy_rank(nm) > 0.5 else 1), nm
    assert ROW_HARDNESS[0] > ROW_HARDNESS[-1]


def test_the_photon_takes_the_wavelength_of_the_band_it_strikes(game):
    """The probe's colour is a running record of what it last interacted with."""
    from chisurf.plugins.misc.games.breakout.breakout import EXCITATION_NM

    assert game.ball_nm == EXCITATION_NM
    game.stuck = False
    brick = game.bricks[0]
    game.ball_x = brick.x
    game.ball_y = brick.y + brick.h * 0.5
    game.ball_vx = 0.0
    game.ball_vy = -200.0
    game.update(1 / 60, game.host.keys)
    assert game.ball_nm == brick.nm != EXCITATION_NM
