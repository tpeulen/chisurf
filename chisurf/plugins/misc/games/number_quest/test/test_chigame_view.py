"""The number-quest view dials an estimate instead of typing one.

The rules were already Qt-free, so this is a view port. The thing worth pinning
is that the whole game is reachable from the abstract controller -- no text
field, which the gamepad rule forbids.
"""

from __future__ import annotations

import pytest

pytest.importorskip("wgpu")
pytest.importorskip("rendercanvas")

from chisurf.gui import chigame  # noqa: E402
from chisurf.gui.chigame.input import Action  # noqa: E402
from chisurf.plugins.misc.games.number_quest.core.game import GuessStatus  # noqa: E402
from chisurf.plugins.misc.games.number_quest.gui.tool import (  # noqa: E402
    NS_PER_UNIT,
    NumberQuestChiGame,
)


@pytest.fixture
def game(qapp):
    """A view wired to a headless host.

    Returns
    -------
    NumberQuestChiGame
        Ready to step, on a deterministic round.
    """
    try:
        context = chigame.create_offscreen(size=(200, 160))
    except Exception as error:  # pragma: no cover - depends on the machine
        pytest.skip(f"no usable GPU adapter: {error}")
    instance = NumberQuestChiGame()
    chigame.GameHost(instance, context, with_text=False, with_audio=False)
    instance.game.reset(target=37)
    return instance


def test_the_estimate_reads_as_a_lifetime(game):
    """The core's 1..100 is presented as 0.1..10.0 ns."""
    game.estimate = 37
    assert game.tau == pytest.approx(37 * NS_PER_UNIT)


def test_the_dial_moves_by_one_and_by_ten(game):
    """Fine and coarse adjustment are both on the pad."""
    game.estimate = 50
    game.host.keys.tap(Action.RIGHT)
    game.update(1 / 60, game.host.keys)
    assert game.estimate == 51

    game.host.keys.end_frame()
    game.host.keys.tap(Action.SHOULDER_R)
    game.update(1 / 60, game.host.keys)
    assert game.estimate == 61


def test_the_dial_clamps_to_the_instrument_range(game):
    """It cannot be wound past either end."""
    game.estimate = game.game.minimum
    game._nudge(-50)
    assert game.estimate == game.game.minimum

    game.estimate = game.game.maximum
    game._nudge(50)
    assert game.estimate == game.game.maximum


def test_confirm_submits_and_the_hint_speaks_in_lifetimes(game):
    """Higher/lower become longer/shorter, which is the same information."""
    game.estimate = 20
    game.host.keys.tap(Action.CONFIRM)
    game.update(1 / 60, game.host.keys)
    assert "Longer" in game.message, game.message
    assert game.game.attempts_remaining == game.game.max_attempts - 1

    game.host.keys.end_frame()
    game.estimate = 80
    game.host.keys.tap(Action.CONFIRM)
    game.update(1 / 60, game.host.keys)
    assert "Shorter" in game.message, game.message


def test_finding_the_value_wins(game):
    """The core still decides; the view only relays."""
    game.estimate = 37
    game.submit()
    assert game.game.status is GuessStatus.WON


def test_submissions_are_kept_as_a_trace(game):
    """Past estimates stay on screen, which is what makes it read as converging."""
    for value in (50, 25, 37):
        game.estimate = value
        game.submit()
    assert game.history == [50, 25, 37]


def test_cancel_starts_a_fresh_round(game):
    """A new round resets the turns and clears the trace."""
    game.estimate = 10
    game.submit()
    game.host.keys.tap(Action.CANCEL)
    game.update(1 / 60, game.host.keys)
    assert game.history == []
    assert game.game.attempts_remaining == game.game.max_attempts


def test_the_decay_curve_falls_and_is_slower_for_a_longer_lifetime(game):
    """The plot is a real exponential, not a decorative squiggle."""
    short = [game._decay_point(i, 1.0)[1] for i in range(0, 60, 10)]
    assert short == sorted(short), "intensity must fall monotonically"

    # A longer lifetime decays more slowly, so it sits higher at the same time.
    mid = 30
    assert game._decay_point(mid, 8.0)[1] < game._decay_point(mid, 1.0)[1]


def test_it_renders(qapp):
    """A frame comes out with the panel drawn on it."""
    try:
        frame = chigame.capture(NumberQuestChiGame(), size=(280, 210), frames=2, with_audio=False)
    except Exception as error:  # pragma: no cover - depends on the machine
        pytest.skip(f"no usable GPU adapter: {error}")
    assert frame.shape == (210, 280, 4)
