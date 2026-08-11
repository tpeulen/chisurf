"""How everything that is not the player decides where to go.

Ported from the steering model of the classic top-down engine this game takes
its shape from, where the whole of it is one function with three rules tried in
order. It is worth stating what that function gets right, because a wandering
creature is one of those things that looks trivial and is not:

1. **A creature decides at tile boundaries, not every frame.** It snaps to the
   grid, picks a direction, walks exactly one tile, and only then decides
   again. That single choice is why the originals never had a monster wedged in
   a doorway: a creature is either aligned or mid-leg, and a mid-leg creature
   is not making decisions. Deciding every frame -- which is the obvious way,
   and the way this game did it before -- is what produces the jitter, the
   diagonal smearing along walls, and the thing that quivers in a corner.

2. **Homing is a probability, and only along an axis.** A creature does not
   walk towards you. It rolls, out of 256, for whether it *may* home this
   decision; and even then it only homes if you share its row or column within
   half a tile. So it wanders, wanders -- and then you step into its column and
   it comes straight down it. Every memory anyone has of these games being
   tense is that rule. Chasing directly reads as a bad pathfinder; snapping to
   an axis and charging reads as being *noticed*.

3. **Negative homing means flee**, and negative bait-greed means repelled. One
   signed number covers drawn-to and afraid-of, which matters here more than it
   did there: Lumis Quest's marked animals are **victims**, not monsters. Most
   of them should be running away from you, and the ones with an aggressive
   trait should be the exception. That is the difference between a bestiary and
   a moral position, and it costs a minus sign.

The bait rule is the same shape and, here, the bait is **light**: a lamp post
draws the phototactic and drives off everything that has learned better. A
creature with a dye fixed into it that is drawn to a lamp is not a metaphor --
it is what the label does.

Qt-free, deterministic given a seeded generator, and unaware of the renderer.
"""

from __future__ import annotations

import dataclasses
import math
import random

from .tiles import TILE

#: The four ways anything can face, in the order the original used. The
#: ordering is load-bearing: opposite directions are adjacent, so reversing is
#: ``direction ^ 1`` and both the flee rule and a creature recoiling from a hit
#: are one exclusive-or rather than a lookup table.
UP, DOWN, LEFT, RIGHT = 0, 1, 2, 3

#: Unit step per direction, in grid cells.
STEPS: tuple[tuple[int, int], ...] = ((0, -1), (0, 1), (-1, 0), (1, 0))

#: Name per direction, matching what the rest of the game calls facings.
NAMES: tuple[str, ...] = ("up", "down", "left", "right")

#: Nothing to do -- boxed in on all four sides.
STUCK = -1

#: How close two things must be on one axis to count as sharing a row or a
#: column. Half a tile, as in the original, where it was 8 of 16.
LINE = TILE * 0.5

#: How far out of line with the bait a creature must be before it corrects
#: *vertically* rather than horizontally. The original's 14-of-16 -- close
#: enough to a whole tile that a creature nearly in line commits to the
#: horizontal, which is why they approach in an L rather than a staircase.
BAIT_LINE = TILE * 0.875

#: How many times to re-roll a blocked direction before giving up and scanning
#: for any legal one at all. Blocked rolls are re-rolled rather than kept, and
#: that is the whole of the wall-following behaviour: a creature against a wall
#: effectively has a higher turn rate than one in the open.
TRIES = 32


@dataclasses.dataclass
class Temper:
    """What kind of mover something is. Constant for its lifetime.

    Attributes
    ----------
    rate : int
        Out of 16, the chance at each decision of picking a fresh direction
        rather than carrying on. 0 walks in a straight line until it hits
        something; 16 changes its mind at every tile.
    homing : int
        Out of 256, signed. Positive seeks the player, negative flees. Either
        way it only applies when the player is lined up, so a high value reads
        as alertness rather than as a heat-seeking missile.
    greed : int
        Out of 4, signed. Positive is drawn to light, negative avoids it.
    reach : float
        How far away light still pulls, in world units. 0 means no limit.
    notice : float
        How far away this creature is aware of the player at all, in world
        units. Ported from the notice radius of a modern reference, and it
        fixes a real hole: alignment alone has no distance in it, so without
        this a beast forty tiles down your column reacts to you through a
        forest it cannot see over. It is also what makes *being noticed* a
        moment -- a creature outside its notice radius is not stalking you, it
        simply has not seen you, and those should not look the same.
    hover : float
        A purely visual height, in world units. It never touches collision --
        the original kept a second, fake z for exactly this, so a thing can
        bob or float without becoming something you can walk underneath.
    speed : float
        World units per second.
    """

    rate: int = 4
    homing: int = 0
    greed: int = 0
    reach: float = TILE * 6.0
    notice: float = TILE * 9.0
    hover: float = 0.0
    speed: float = 20.0


@dataclasses.dataclass
class Drift:
    """Where one creature is in its current decision, mutated as it walks.

    Attributes
    ----------
    facing : int
        One of :data:`UP`, :data:`DOWN`, :data:`LEFT`, :data:`RIGHT`, or
        :data:`STUCK`.
    remaining : float
        World units left in the current leg. At zero it is time to decide.
    phase : float
        Running seconds, for the visual bob.
    noticed : bool
        Whether the player was within notice range at the last decision. The
        *rising edge* of this is the interesting event -- it is the frame a
        creature saw you -- and it is why this is kept rather than recomputed.
    """

    facing: int = DOWN
    remaining: float = 0.0
    phase: float = 0.0
    hover: float = 0.0
    noticed: bool = False

    @property
    def name(self) -> str:
        """The facing under the name the rest of the game uses.

        Returns
        -------
        str
            ``up``, ``down``, ``left`` or ``right``; a stuck creature keeps
            facing whichever way it last did, which here is down.
        """
        return NAMES[self.facing] if self.facing >= 0 else "down"

    def fake_z(self) -> float:
        """The visual-only height, if this thing hovers.

        Returns
        -------
        float
            World units to lift the drawing by, never the hitbox -- so a
            hovering thing still blocks and is still blocked at ground level.
            Keeping the two heights separate is the reason a bob can be added
            to anything without auditing what it can now pass over.
        """
        if not self.hover:
            return 0.0
        # Two frequencies, so it reads as a hover rather than a metronome.
        return self.hover * (0.5 + 0.5 * math.sin(self.phase * 2.1)) * (
            0.85 + 0.15 * math.sin(self.phase * 0.7)
        )


def lined_up(x: float, y: float, tx: float, ty: float,
             reach: float = LINE) -> int:
    """Which way a target lies, if it shares a row or a column.

    The column is tested first, exactly as the original did: a creature
    standing at a crossing where the player is diagonally adjacent will go
    *vertically*. That asymmetry is invisible in play and matters for parity
    with anyone reading the two side by side.

    Parameters
    ----------
    x, y : float
        Where the creature is, in world units.
    tx, ty : float
        Where the target is.
    reach : float, optional
        How close on the perpendicular axis counts as lined up.

    Returns
    -------
    int
        A direction, or :data:`STUCK` when the target is off both axes.
    """
    if abs(tx - x) <= reach:
        return UP if ty < y else DOWN
    if abs(ty - y) <= reach:
        return LEFT if tx < x else RIGHT
    return STUCK


def choose(temper: Temper, drift: Drift, x: float, y: float, passable,
           rng: random.Random, target: tuple[float, float] | None = None,
           bait: tuple[float, float] | None = None) -> int:
    """Pick a direction: bait, then homing, then wander.

    Parameters
    ----------
    temper : Temper
        What kind of mover this is.
    drift : Drift
        Its current state; read for the direction it is already going, which
        is what it keeps when the wander roll says not to turn.
    x, y : float
        Where it is, in world units.
    passable : callable
        ``passable(direction) -> bool`` for the cell one step that way. Walls,
        water and the creature's own leash all arrive through here, which is
        why a leashed creature turns back rather than pressing against a
        boundary that is not there.
    rng : random.Random
        Seeded per creature, so a world replays.
    target : tuple of float, optional
        The player. Homing does nothing without one.
    bait : tuple of float, optional
        The nearest light. Greed does nothing without one.

    Returns
    -------
    int
        A direction, or :data:`STUCK` when every way is blocked.
    """
    if temper.greed and bait is not None and rng.getrandbits(2) < abs(temper.greed):
        chosen = _towards_bait(temper, x, y, bait, passable)
        if chosen != STUCK:
            return chosen

    if temper.homing and target is not None and \
            _within(x, y, target, temper.notice) and \
            rng.getrandbits(8) < abs(temper.homing):
        chosen = lined_up(x, y, target[0], target[1])
        if chosen != STUCK:
            if temper.homing < 0:
                chosen ^= 1
            if passable(chosen):
                return chosen

    # Wander. One draw serves both the decision and the direction, as in the
    # original -- the low nibble against the rate, the next two bits as the
    # heading. Cheap, and it keeps the two correlated in the same way, which
    # is the sort of thing that shows up in a side-by-side and nowhere else.
    for _ in range(TRIES):
        roll = rng.getrandbits(16)
        chosen = (roll >> 4) & 3 if (roll & 15) < temper.rate else drift.facing
        if chosen >= 0 and passable(chosen):
            return chosen

    for chosen in (UP, DOWN, LEFT, RIGHT):
        if passable(chosen):
            return chosen
    return STUCK


def _within(x: float, y: float, point: tuple[float, float],
            reach: float) -> bool:
    """Whether a point is close enough to matter.

    Squared distance, because this runs per creature per decision and a square
    root buys nothing a comparison needs.

    Parameters
    ----------
    x, y : float
        Where the creature is.
    point : tuple of float
        What it might be aware of.
    reach : float
        World units. 0 means no limit.

    Returns
    -------
    bool
        True when in range.
    """
    if not reach:
        return True
    dx, dy = point[0] - x, point[1] - y
    return dx * dx + dy * dy <= reach * reach


def _towards_bait(temper: Temper, x: float, y: float,
                  bait: tuple[float, float], passable) -> int:
    """The bait rule: close the larger gap first, and take second best.

    Note what happens when the preferred direction is blocked -- it does not
    re-roll or give up, it falls through to the horizontal. A creature working
    its way around an obstacle towards a lamp is that fall-through and nothing
    else.

    Parameters
    ----------
    temper : Temper
        For :attr:`Temper.greed`'s sign and :attr:`Temper.reach`.
    x, y : float
        Where the creature is.
    bait : tuple of float
        Where the light is.
    passable : callable
        ``passable(direction) -> bool``.

    Returns
    -------
    int
        A direction, or :data:`STUCK` when the light is out of reach or both
        ways are blocked.
    """
    bx, by = bait
    if temper.reach:
        if abs(bx - x) > temper.reach or abs(by - y) > temper.reach:
            return STUCK

    if abs(y - by) > BAIT_LINE:
        chosen = UP if by < y else DOWN
        if temper.greed < 0:
            chosen ^= 1
        if passable(chosen):
            return chosen

    chosen = LEFT if bx < x else RIGHT
    if temper.greed < 0:
        chosen ^= 1
    return chosen if passable(chosen) else STUCK


def advance(temper: Temper, drift: Drift, x: float, y: float, dt: float,
            passable, rng: random.Random,
            target: tuple[float, float] | None = None,
            bait: tuple[float, float] | None = None) -> tuple[float, float]:
    """Walk a creature for one frame, deciding at every tile it crosses.

    The leg length is one tile, and a step that would overshoot the end of a
    leg is cut at the boundary with the surplus carried into the next -- so a
    slow frame produces two decisions rather than a creature sliding a tile and
    a half past a turning it should have taken. That is the frame-rate
    independence the original got for free by being frame-locked.

    Parameters
    ----------
    temper : Temper
        What kind of mover this is.
    drift : Drift
        Mutated in place.
    x, y : float
        Where it is now, in world units.
    dt : float
        Seconds elapsed.
    passable : callable
        ``passable(direction) -> bool``, evaluated from the creature's
        *current* cell each time it decides.
    rng : random.Random
        Seeded per creature.
    target, bait : tuple of float, optional
        The player, and the nearest light.

    Returns
    -------
    tuple of float
        Where it is now.
    """
    drift.phase += dt
    drift.hover = temper.hover
    budget = max(0.0, temper.speed) * max(0.0, dt)

    for _ in range(TRIES):
        if drift.remaining <= 0.0:
            # Snap to the tile centre before deciding. After the first leg this
            # is a no-op to within floating-point noise, and that is the point:
            # a creature that decides on the grid stays on the grid, and a
            # creature on the grid cannot end a leg inside a wall.
            x = (int(x // TILE) + 0.5) * TILE
            y = (int(y // TILE) + 0.5) * TILE
            drift.noticed = target is not None and \
                _within(x, y, target, temper.notice)
            drift.facing = choose(temper, drift, x, y, passable, rng, target, bait)
            if drift.facing == STUCK:
                return x, y
            drift.remaining = TILE
        if budget <= 0.0:
            break
        moved = min(budget, drift.remaining)
        step = STEPS[drift.facing]
        x += step[0] * moved
        y += step[1] * moved
        drift.remaining -= moved
        budget -= moved
        if budget <= 0.0:
            break
    return x, y


#: Traits whose whole description is *coming at you*. A marked animal carrying
#: one of these seeks; everything else flees, which is the default and the
#: point of the bestiary. Every key here is a real trait from
#: :data:`~.bestiary.TRAITS` -- the steering is read off the animal rather than
#: assigned to it.
AGGRESSIVE: frozenset[str] = frozenset({
    "charge",    # boar: "one direction, committed to entirely"
    "venom",     # adder: "strikes once and lets the strike keep working"
    "frenzy",
    "silent",    # owl: "arrives without the sound that should have preceded it"
    "discharge",
})

#: Traits that hold still and let you come to them. They still home -- an
#: ambusher that never notices you is scenery -- they simply do not travel,
#: which is what makes walking into one feel like your mistake.
LYING_IN_WAIT: frozenset[str] = frozenset({"ambush", "mimicry"})

#: Drawn to light rather than wary of it. Exactly one animal in the bestiary
#: has this and it is the moth, whose entry already says so: "goes to the
#: brightest thing in the room. Always has."
PHOTOTACTIC: frozenset[str] = frozenset({"phototaxis"})


def temper_for(kind: str, traits: tuple[str, ...] = (), tier: int = 1) -> Temper:
    """The temper of one of the world's inhabitants.

    This is where the moral position gets its number. A marked beast **flees**
    unless something was done to it that makes it fight: the animals in this
    game did not choose to be labelled, and a wilderness full of things running
    away from you reads very differently from a wilderness full of things
    running at you. The exceptions are earned by traits, and the higher tiers
    are bolder because a brighter label is a heavier burden.

    Parameters
    ----------
    kind : str
        The :class:`~.npcs.Npc` kind.
    traits : tuple of str, optional
        The beast's traits, for a marked one.
    tier : int, optional
        1..5.

    Returns
    -------
    Temper
        Ready to hand to :func:`advance`.
    """
    tier = max(1, min(int(tier), 5))
    if kind == "beast":
        drawn = any(trait in PHOTOTACTIC for trait in traits)
        greed = 2 if drawn else -1
        if any(trait in LYING_IN_WAIT for trait in traits):
            # Barely travels, and notices you from a long way down its own row.
            return Temper(rate=2, homing=40 + 30 * tier, greed=greed,
                          speed=5.0, reach=TILE * 4.0)
        if any(trait in AGGRESSIVE for trait in traits):
            return Temper(rate=6, homing=24 + 26 * tier, greed=greed,
                          speed=17.0 + 2.0 * tier)
        # The default, and the one that matters: it runs. A wilderness of
        # things fleeing you reads very differently from one of things
        # charging you, and the difference is the minus sign.
        return Temper(rate=9, homing=-(30 + 22 * tier), greed=greed,
                      speed=16.0 + 2.0 * tier)
    if kind == "animal":
        # Unmarked animals have no opinion about you until you are close, and
        # then they leave. Nothing here should teach a player that an ordinary
        # hare is a threat.
        return Temper(rate=10, homing=-40, greed=1, speed=14.0)
    if kind == "wraith":
        # Shelved labels do not walk, they drift -- and they drift *towards*
        # light, which is the only unsettling thing they do. They hover,
        # because a thing with nothing inside it should not have weight.
        return Temper(rate=3, homing=70, greed=3, hover=2.4, speed=8.0,
                      reach=TILE * 10.0)
    if kind == "townsfolk":
        return Temper(rate=5, speed=11.0)
    return Temper(rate=6, speed=20.0)
