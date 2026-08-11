"""A creature that decides on the grid cannot end a step inside a wall."""

from __future__ import annotations

import random

import pytest

from chisurf.plugins.misc.games.lumis_quest.api import steering
from chisurf.plugins.misc.games.lumis_quest.api.steering import (
    DOWN,
    LEFT,
    RIGHT,
    STUCK,
    UP,
)
from chisurf.plugins.misc.games.lumis_quest.api.tiles import TILE


def _open(direction: int) -> bool:
    """Nothing in the way, whichever direction is asked for."""
    return True


def _walled(*blocked: int):
    """A passability test that refuses the given directions."""
    def passable(direction: int) -> bool:
        return direction not in blocked
    return passable


def _centre(cell: int) -> float:
    """The world coordinate of the middle of a cell."""
    return (cell + 0.5) * TILE


# --------------------------------------------------------------------------
# lined_up
# --------------------------------------------------------------------------

def test_sharing_a_column_reads_as_up_or_down():
    """The player above you is up; below you is down."""
    assert steering.lined_up(100.0, 100.0, 102.0, 20.0) == UP
    assert steering.lined_up(100.0, 100.0, 102.0, 200.0) == DOWN


def test_sharing_a_row_reads_as_left_or_right():
    """The same, along the other axis."""
    assert steering.lined_up(100.0, 100.0, 20.0, 103.0) == LEFT
    assert steering.lined_up(100.0, 100.0, 200.0, 103.0) == RIGHT


def test_a_target_off_both_axes_is_not_lined_up_at_all():
    """This is the rule that keeps a creature from walking straight at you.

    A creature does not approach; it wanders until it shares your row or your
    column, and only then does it come. Take this away and homing degenerates
    into a bad pathfinder crawling along the diagonal.
    """
    assert steering.lined_up(100.0, 100.0, 300.0, 300.0) == STUCK


def test_the_column_is_tested_before_the_row():
    """Diagonally adjacent within reach on both axes goes vertically.

    Faithful to the original, invisible in play, and the sort of thing that
    shows up only when somebody reads the two side by side.
    """
    assert steering.lined_up(100.0, 100.0, 101.0, 101.0, reach=TILE) == DOWN


# --------------------------------------------------------------------------
# The wander
# --------------------------------------------------------------------------

def test_a_creature_that_never_turns_walks_in_a_straight_line():
    """Rate zero keeps the heading it already had."""
    temper = steering.Temper(rate=0, speed=TILE)
    drift = steering.Drift(facing=RIGHT)
    rng = random.Random(1)
    x, y = _centre(4), _centre(4)
    start_y = y
    for _ in range(60):
        x, y = steering.advance(temper, drift, x, y, 0.1, _open, rng)
    assert y == pytest.approx(start_y)
    assert x > _centre(4) + TILE * 4


def test_it_stays_on_the_grid_however_long_it_wanders():
    """The anti-wedge property, and the reason for the whole port.

    Every decision is taken from a tile centre, so a creature is either aligned
    or mid-leg. It can never come to rest half inside something.
    """
    temper = steering.Temper(rate=16, speed=TILE * 2)
    drift = steering.Drift()
    rng = random.Random(7)
    x, y = _centre(10), _centre(10)
    for _ in range(400):
        x, y = steering.advance(temper, drift, x, y, 0.05, _open, rng)
        if drift.remaining <= 0.0:
            assert (x / TILE - 0.5) == pytest.approx(round(x / TILE - 0.5), abs=1e-6)
            assert (y / TILE - 0.5) == pytest.approx(round(y / TILE - 0.5), abs=1e-6)


def test_a_leg_is_exactly_one_tile():
    """It decides at every tile it crosses, not on a timer."""
    temper = steering.Temper(rate=0, speed=TILE)
    drift = steering.Drift(facing=DOWN)
    x, y = _centre(3), _centre(3)
    x, y = steering.advance(temper, drift, x, y, 1.0, _open, random.Random(0))
    assert y == pytest.approx(_centre(4))
    assert drift.remaining == pytest.approx(0.0)


def test_a_slow_frame_does_not_slide_it_past_a_turning():
    """The frame-rate independence the original got for free by being locked.

    One enormous step must still stop at the wall it would have decided at,
    rather than carrying a tile and a half through it.
    """
    temper = steering.Temper(rate=0, speed=TILE * 4)
    drift = steering.Drift(facing=RIGHT)
    # Open to the right for one tile, then a wall: from cell 5 onwards, right
    # is refused, so the creature must turn rather than continue.
    calls = {"n": 0}

    def passable(direction: int) -> bool:
        calls["n"] += 1
        return direction != RIGHT if calls["n"] > 1 else True

    x, y = _centre(4), _centre(4)
    x, y = steering.advance(temper, drift, x, y, 1.0, passable, random.Random(3))
    assert drift.facing != RIGHT
    assert x <= _centre(5) + 1e-6


def test_boxed_in_on_all_four_sides_it_stops_where_it_is():
    """Never a crash, never a phase through a wall: it simply waits."""
    temper = steering.Temper(rate=8, speed=TILE)
    drift = steering.Drift()
    x, y = _centre(2), _centre(2)
    moved = steering.advance(temper, drift, x, y, 0.5,
                             _walled(UP, DOWN, LEFT, RIGHT), random.Random(5))
    assert drift.facing == STUCK
    assert moved == (pytest.approx(x), pytest.approx(y))


# --------------------------------------------------------------------------
# Homing, and the minus sign the bestiary turns on
# --------------------------------------------------------------------------

def test_certain_homing_walks_at_a_player_who_is_lined_up():
    """Homing 255 out of 256 always fires, and it fires along the axis."""
    temper = steering.Temper(rate=0, homing=255, speed=TILE)
    drift = steering.Drift(facing=LEFT)
    x, y = _centre(5), _centre(5)
    x, y = steering.advance(temper, drift, x, y, 1.0, _open, random.Random(2),
                            target=(_centre(5), _centre(9)))
    assert drift.facing == DOWN
    assert y > _centre(5)


def test_negative_homing_runs_the_other_way():
    """The whole moral position of the bestiary is this minus sign.

    A marked animal did not choose to be labelled. Almost all of them should be
    getting away from you.
    """
    temper = steering.Temper(rate=0, homing=-255, speed=TILE)
    drift = steering.Drift(facing=LEFT)
    x, y = _centre(5), _centre(5)
    x, y = steering.advance(temper, drift, x, y, 1.0, _open, random.Random(2),
                            target=(_centre(5), _centre(9)))
    assert drift.facing == UP
    assert y < _centre(5)


def test_homing_does_nothing_at_all_when_you_are_off_its_axes():
    """Stand diagonally and even a maximally alert creature only wanders."""
    temper = steering.Temper(rate=0, homing=255, speed=TILE)
    drift = steering.Drift(facing=RIGHT)
    x, y = _centre(5), _centre(5)
    steering.advance(temper, drift, x, y, 1.0, _open, random.Random(2),
                     target=(_centre(20), _centre(20)))
    assert drift.facing == RIGHT  # kept its heading; never noticed you


# --------------------------------------------------------------------------
# Bait, which here is light
# --------------------------------------------------------------------------

def test_a_phototactic_creature_closes_the_vertical_gap_first():
    """The bait rule approaches in an L, tall side first."""
    temper = steering.Temper(rate=0, greed=4, speed=TILE, reach=0.0)
    drift = steering.Drift(facing=LEFT)
    x, y = _centre(5), _centre(5)
    steering.advance(temper, drift, x, y, 1.0, _open, random.Random(1),
                     bait=(_centre(9), _centre(1)))
    assert drift.facing == UP


def test_when_the_vertical_is_blocked_it_takes_the_horizontal_rather_than_giving_up():
    """The fall-through *is* the working-around-an-obstacle behaviour.

    It does not re-roll and it does not stop; second best is taken directly,
    which is what makes a creature edge around a rock towards a lamp.
    """
    temper = steering.Temper(rate=0, greed=4, speed=TILE, reach=0.0)
    drift = steering.Drift(facing=LEFT)
    x, y = _centre(5), _centre(5)
    steering.advance(temper, drift, x, y, 1.0, _walled(UP), random.Random(1),
                     bait=(_centre(9), _centre(1)))
    assert drift.facing == RIGHT


def test_negative_greed_keeps_out_of_the_light():
    """One signed number covers drawn-to and afraid-of."""
    temper = steering.Temper(rate=0, greed=-4, speed=TILE, reach=0.0)
    drift = steering.Drift(facing=LEFT)
    x, y = _centre(5), _centre(5)
    steering.advance(temper, drift, x, y, 1.0, _open, random.Random(1),
                     bait=(_centre(9), _centre(1)))
    assert drift.facing == DOWN


def test_a_lamp_out_of_reach_pulls_at_nothing():
    """Reach is per creature, so a moth is not drawn across a whole region."""
    temper = steering.Temper(rate=0, greed=4, speed=TILE, reach=TILE * 2.0)
    drift = steering.Drift(facing=RIGHT)
    x, y = _centre(5), _centre(5)
    steering.advance(temper, drift, x, y, 1.0, _open, random.Random(1),
                     bait=(_centre(40), _centre(40)))
    assert drift.facing == RIGHT


# --------------------------------------------------------------------------
# The visual height, which is not the real one
# --------------------------------------------------------------------------

def test_a_hover_lifts_the_drawing_and_not_the_creature():
    """Two heights, and only one of them is allowed near the collision.

    Keeping them apart is why a bob can be given to anything without going back
    through what it may now pass over.
    """
    temper = steering.Temper(rate=0, hover=4.0, speed=TILE)
    drift = steering.Drift(facing=RIGHT)
    x, y = _centre(5), _centre(5)
    lifted = set()
    for _ in range(40):
        x, y = steering.advance(temper, drift, x, y, 0.1, _open, random.Random(1))
        lifted.add(round(drift.fake_z(), 3))
        assert y == pytest.approx(_centre(5))  # the real position never rises
    assert len(lifted) > 5
    assert max(lifted) <= 4.0 + 1e-6
    assert min(lifted) >= 0.0


def test_something_that_does_not_hover_is_drawn_on_the_ground():
    """No hover, no lift, no per-frame cost for the hundred that do not."""
    drift = steering.Drift()
    assert drift.fake_z() == 0.0


# --------------------------------------------------------------------------
# The bestiary decides the steering, rather than the steering being assigned
# --------------------------------------------------------------------------

def test_a_marked_hare_runs_and_a_marked_boar_charges():
    """Read off the trait, which is read off the animal."""
    hare = steering.temper_for("beast", ("bolt",), tier=3)
    boar = steering.temper_for("beast", ("charge",), tier=3)
    assert hare.homing < 0
    assert boar.homing > 0


def test_a_heavier_label_is_a_bolder_animal():
    """Tier moves the magnitude, in whichever direction the trait chose."""
    low = steering.temper_for("beast", ("bolt",), tier=1)
    high = steering.temper_for("beast", ("bolt",), tier=5)
    assert abs(high.homing) > abs(low.homing)
    assert high.speed > low.speed


def test_the_moth_is_the_one_that_goes_to_the_lamp():
    """Its bestiary entry already says so; the steering agrees with it."""
    moth = steering.temper_for("beast", ("phototaxis",), tier=2)
    owl = steering.temper_for("beast", ("silent",), tier=2)
    assert moth.greed > 0
    assert owl.greed < 0


def test_an_ambusher_barely_travels_but_notices_you_from_far_down_its_row():
    """Walking into one should feel like your mistake, not its patrol."""
    mantis = steering.temper_for("beast", ("ambush",), tier=2)
    fox = steering.temper_for("beast", ("cunning",), tier=2)
    assert mantis.speed < fox.speed
    assert mantis.homing > 0


def test_an_unmarked_animal_is_never_a_threat():
    """A player must not learn to be afraid of an ordinary hare."""
    assert steering.temper_for("animal").homing < 0


def test_the_shelved_drift_towards_light_and_do_not_touch_the_ground():
    """The only unsettling thing a wraith does."""
    wraith = steering.temper_for("wraith")
    assert wraith.greed > 0
    assert wraith.hover > 0.0
    assert wraith.homing > 0


def test_every_trait_the_steering_names_is_a_trait_the_bestiary_has():
    """A steering table full of invented trait keys steers nothing.

    Silent, too: an unknown key simply never matches, so every animal quietly
    falls to the default and nobody finds out.
    """
    from chisurf.plugins.misc.games.lumis_quest.api.bestiary import TRAITS
    named = steering.AGGRESSIVE | steering.LYING_IN_WAIT | steering.PHOTOTACTIC
    assert named <= set(TRAITS)


# --------------------------------------------------------------------------
# Noticing, which is not the same as reacting
# --------------------------------------------------------------------------

def test_a_creature_reacts_to_nobody_it_has_not_seen():
    """Alignment alone has no distance in it.

    Without a notice radius a beast forty tiles down your column flees from you
    through a forest it cannot see over -- and it looks, from where the player
    is standing, like nothing at all.
    """
    temper = steering.Temper(rate=0, homing=255, speed=TILE, notice=TILE * 4.0)
    drift = steering.Drift(facing=RIGHT)
    x, y = _centre(5), _centre(5)
    steering.advance(temper, drift, x, y, 1.0, _open, random.Random(2),
                     target=(_centre(5), _centre(40)))
    assert drift.facing == RIGHT
    assert not drift.noticed


def test_it_does_react_once_you_are_inside_that_radius():
    """The same creature, the same axis, closer."""
    temper = steering.Temper(rate=0, homing=255, speed=TILE, notice=TILE * 4.0)
    drift = steering.Drift(facing=RIGHT)
    x, y = _centre(5), _centre(5)
    steering.advance(temper, drift, x, y, 1.0, _open, random.Random(2),
                     target=(_centre(5), _centre(8)))
    assert drift.facing == DOWN
    assert drift.noticed


def test_no_notice_radius_means_no_limit():
    """Zero is "unlimited", which is what the rest of the module means by it."""
    temper = steering.Temper(rate=0, homing=255, speed=TILE, notice=0.0)
    drift = steering.Drift(facing=RIGHT)
    steering.advance(temper, drift, _centre(5), _centre(5), 1.0, _open,
                     random.Random(2), target=(_centre(5), _centre(300)))
    assert drift.facing == DOWN
