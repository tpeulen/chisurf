"""Sheet-animated actors and the damage model.

A straight port of the reference game's character stack
(``junk/NinjaAdventure/system``): a body that accelerates toward its move
vector (:class:`Actor`), a sheet animation state machine with four direction
columns and seven animation rows (:class:`SheetAnimation`), weapons that swing
(:class:`Weapon`), a life resource (:class:`Health`), and team-tagged damage
(:class:`Team`, :class:`Damage`, :func:`strike`).

The sheets this drives are 16-pixel cells laid out four columns across — down,
up, left, right — by seven rows down, where row 0 is idle and walk frame one,
rows 0-3 are the walk cycle, 4 is the attack pose, 5 is airborne and 6 is
downed. Animation advances at six cells a second, exactly the reference's
``IMAGE_SPEED``.

Everything here is sheet-agnostic: the animation knows rows and columns, the
pack knows what pixels a row and column select. A different sheet set changes
the look without touching this module.
"""

from __future__ import annotations

import math

import numpy as np

#: Direction columns present in every character sheet (the reference's
#: ``FrameDirection``): down, up, left, right.
DOWN, UP, LEFT, RIGHT = 0, 1, 2, 3

#: Column lookup by a quantised movement angle, in angle order 0°, 90°,
#: 180°, 270° — the reference's ``round(deg/90)`` indexing into its
#: ``FrameDirection`` values.
_DIRECTIONS = (RIGHT, DOWN, LEFT, UP)

#: Animation rows: the walk cycle is rows 0-3, the rest are single poses.
ROW_MOVE = (0, 1, 2, 3)
ROW_ATTACK = 4
ROW_JUMP = 5
ROW_DEAD = 6

#: Cells a second, the reference's ``IMAGE_SPEED``.
IMAGE_SPEED = 6.0

#: The bright tint a flashing sprite takes. The reference modulates by
#: ``(5, 5, 5)``; three keeps the read without washing out every neighbour.
FLASH_TINT = (3.0, 3.0, 3.0, 1.0)


def direction_column(move: tuple[float, float] | np.ndarray) -> int:
    """Quantise a move vector to a sheet direction column.

    Parameters
    ----------
    move : tuple of float or numpy.ndarray
        Non-zero movement direction.

    Returns
    -------
    int
        One of :data:`DOWN`, :data:`UP`, :data:`LEFT`, :data:`RIGHT`.
    """
    angle = math.atan2(move[1], move[0])
    index = int(round(angle / (math.pi / 2))) % 4
    return _DIRECTIONS[index]


class SheetAnimation:
    """The four-direction sheet animation state machine.

    Attributes
    ----------
    anim : str
        ``"idle"``, ``"move"``, ``"attack"``, ``"jump"`` or ``"dead"``.
    column : int
        Facing; one of the direction constants.
    clock : float
        Seconds accumulated in the current cycle.
    flip : bool
        Mirror horizontally — for two-column animal sheets whose columns are
        frames rather than facings.
    """

    #: Rows each animation plays, matching the reference's ``ANIMATION_DATA``.
    ROWS = {
        "idle": (0,),
        "move": ROW_MOVE,
        "attack": (ROW_ATTACK,),
        "jump": (ROW_JUMP,),
        "dead": (ROW_DEAD,),
    }

    def __init__(self, column: int = DOWN, two_column: bool = False) -> None:
        self.anim = "idle"
        self.column = column
        self.clock = 0.0
        self.flip = False
        self.two_column = two_column

    def face(self, move: tuple[float, float] | np.ndarray) -> None:
        """Set the facing from a movement direction.

        Parameters
        ----------
        move : tuple of float
            The movement vector; ignored when zero.
        """
        norm = math.hypot(move[0], move[1])
        if norm < 1e-6:
            return
        if self.two_column:
            self.flip = move[0] < 0.0
            return
        self.column = direction_column(move)

    def advance(self, dt: float, moving: bool) -> None:
        """Step the animation and pick the next animation name.

        Parameters
        ----------
        dt : float
            Frame step in seconds.
        moving : bool
            Whether the body is trying to move this frame.
        """
        if self.anim == "dead":
            return
        target = "move" if moving else "idle"
        if self.anim != target:
            self.anim = target
            self.clock = 0.0
        self.clock += dt * IMAGE_SPEED

    def pose(self, attack: bool = False, airborne: bool = False) -> str:
        """The pack state string for the current pose.

        Parameters
        ----------
        attack : bool, optional
            Override with the attack pose for this frame.
        airborne : bool, optional
            Override with the airborne pose.

        Returns
        -------
        str
            ``"<row>,<column>"`` for :meth:`Scene.draw
            <chisurf.gui.chigame.scene.Scene.draw>`'s state argument.
        """
        if attack:
            return f"{ROW_ATTACK},{self.column}"
        if airborne:
            return f"{ROW_JUMP},{self.column}"
        rows = self.ROWS[self.anim]
        index = int(self.clock) % len(rows)
        if self.two_column:
            return f"{index % 2},0"
        return f"{rows[index]},{self.column}"


class Health:
    """A life value with change listeners — the reference's ``ResourceLife``.

    Parameters
    ----------
    maximum : float, optional
        Maximum and starting value.
    """

    def __init__(self, maximum: float = 10.0) -> None:
        self.maximum = float(maximum)
        self.current = float(maximum)
        self.listeners: list = []

    @property
    def alive(self) -> bool:
        """Whether there is life left.

        Returns
        -------
        bool
        """
        return self.current > 0.0

    def damage(self, amount: float) -> bool:
        """Remove life.

        Parameters
        ----------
        amount : float
            Life to remove.

        Returns
        -------
        bool
            Whether this hit was the killing one.
        """
        if not self.alive:
            return False
        self.current = max(0.0, self.current - amount)
        for listener in self.listeners:
            listener(self)
        return not self.alive

    def heal(self, amount: float | None = None) -> None:
        """Restore life, fully when no amount is given.

        Parameters
        ----------
        amount : float, optional
            Life to add.
        """
        self.current = self.maximum if amount is None else min(
            self.maximum, self.current + amount
        )
        for listener in self.listeners:
            listener(self)


class Team:
    """Who a damage source may not hurt.

    Parameters
    ----------
    name : str
        Team identity.
    allies : iterable of str, optional
        Team names that share this one's side.
    """

    def __init__(self, name: str, allies=()) -> None:
        self.name = name
        self.allies = frozenset(allies) | {name}

    def is_ally(self, other: "Team | None") -> bool:
        """Whether damage must skip the other team.

        Parameters
        ----------
        other : Team or None
            The target's team.

        Returns
        -------
        bool
        """
        return other is not None and other.name in self.allies


class Damage:
    """One hit: how much, and how hard it shoves.

    Parameters
    ----------
    amount : float, optional
        Life removed.
    push_force : float, optional
        Knockback impulse in world units a second.
    """

    def __init__(self, amount: float = 1.0, push_force: float = 0.0) -> None:
        self.amount = float(amount)
        self.push_force = float(push_force)


class Actor:
    """A body: moves, collides, animates, takes damage.

    The port of the reference's ``Character`` plus its ``ActorSprite`` damage
    feedback. Movement is the reference's model exactly: velocity approaches
    ``move_vector * speed`` by ``acceleration`` a second and zero by
    ``deceleration``, which is what gives the walk its weight.

    Parameters
    ----------
    position : tuple of float, optional
        Centre in world units.
    alias : str, optional
        Pack character alias drawn by :meth:`draw`.
    speed : float, optional
        Top speed in world units a second.
    solid : callable, optional
        ``solid(x, y) -> bool`` world query used for collision. A world with
        no query never blocks.
    half_extent : tuple of float, optional
        Collision box half-size. The reference walks a 16-pixel sprite against
        16-pixel tiles with a box that leaves clearance, so 6 of 8 is the feel
        being reproduced.
    team : Team, optional
        Damage side.
    maximum_life : float, optional
        Starting life; zero means no life tracking.
    """

    def __init__(
        self,
        position: tuple[float, float] = (0.0, 0.0),
        alias: str = "hero",
        speed: float = 100.0,
        solid=None,
        half_extent: tuple[float, float] = (6.0, 5.0),
        team: Team | None = None,
        maximum_life: float = 0.0,
        two_column: bool = False,
    ) -> None:
        self.position = np.array(position, dtype=np.float64)
        self.velocity = np.zeros(2, dtype=np.float64)
        self.move_vector = np.zeros(2, dtype=np.float64)
        self.speed = speed
        self.acceleration = 1000.0
        self.deceleration = 800.0
        self.solid = solid
        self.half_extent = np.array(half_extent, dtype=np.float64)
        self.alias = alias
        self.anim = SheetAnimation(two_column=two_column)
        self.team = team
        self.health = Health(maximum_life) if maximum_life else None
        self.push_velocity = np.zeros(2, dtype=np.float64)
        self.flash = 0.0
        self.shake = 0.0
        self.attack_pose = 0.0
        self.airborne = False
        self.on_damaged = None
        self.on_killed = None

    # -- simulation --------------------------------------------------------

    def update(self, dt: float) -> None:
        """Integrate one frame: steer, move, collide, animate, fade fx.

        Parameters
        ----------
        dt : float
            Frame step in seconds.
        """
        moving = bool(np.any(self.move_vector))
        target = self.move_vector * self.speed
        rate = self.acceleration if moving else self.deceleration
        step = rate * dt
        delta = target - self.velocity
        norm = np.hypot(*delta)
        if norm <= step or norm == 0.0:
            self.velocity[:] = target
        else:
            self.velocity[:] += delta / norm * step
        self._move_and_collide(self.velocity * dt)
        if np.any(self.push_velocity):
            self._move_and_collide(self.push_velocity * dt)
            self.push_velocity *= max(0.0, 1.0 - 6.0 * dt)
            if np.hypot(*self.push_velocity) < 1.0:
                self.push_velocity[:] = 0.0
        if moving:
            self.anim.face(self.move_vector)
        self.anim.advance(dt, moving)
        self.flash = max(0.0, self.flash - dt)
        self.shake = max(0.0, self.shake - dt)
        self.attack_pose = max(0.0, self.attack_pose - dt)

    def _move_and_collide(self, delta: np.ndarray) -> None:
        """Move by ``delta`` one axis at a time, stopping at solids.

        Axis-separated movement is what makes corner slip feel right: a walk
        diagonally into a wall still glides along it, and each axis is checked
        against the collision box's leading edge only.

        Parameters
        ----------
        delta : numpy.ndarray
            Displacement this frame.
        """
        if self.solid is None:
            self.position += delta
            return
        for axis in (0, 1):
            step = delta[axis]
            if step == 0.0:
                continue
            probe = self.position.copy()
            probe[axis] += step + math.copysign(self.half_extent[axis], step)
            if self._box_blocked(probe, axis, step):
                continue
            self.position[axis] += step

    def _box_blocked(self, probe: np.ndarray, axis: int, step: float) -> bool:
        """Whether the box's leading edge hits a solid at ``probe``.

        Parameters
        ----------
        probe : numpy.ndarray
            Candidate centre with the axis offset applied.
        axis : int
            0 for x, 1 for y.
        step : float
            Movement sign on that axis.

        Returns
        -------
        bool
        """
        other = 1 - axis
        lo = probe[other] - self.half_extent[other] + 1.0
        hi = probe[other] + self.half_extent[other] - 1.0
        for span in {lo, hi, (lo + hi) / 2.0}:
            point = probe.copy()
            point[other] = span
            if self.solid(point[0], point[1]):
                return True
        return False

    # -- damage ------------------------------------------------------------

    def take_damage(self, damage: Damage, source_position) -> bool:
        """Receive a hit: life, knockback, flash, shake.

        Parameters
        ----------
        damage : Damage
            The hit.
        source_position : array-like
            Where the hit came from, for knockback direction.

        Returns
        -------
        bool
            Whether this hit killed the actor.
        """
        died = False
        if self.health is not None:
            died = self.health.damage(damage.amount)
        if damage.push_force:
            away = self.position - np.asarray(source_position, dtype=np.float64)
            norm = np.hypot(*away)
            if norm > 1e-6:
                self.push_velocity[:] += away / norm * damage.push_force
        self.flash = 0.2
        self.shake = 0.1
        if self.on_damaged is not None:
            self.on_damaged(self)
        if died and self.on_killed is not None:
            self.on_killed(self)
        return died

    def attack(self) -> None:
        """Raise the attack pose for the next few frames."""
        self.attack_pose = 0.15

    # -- drawing -----------------------------------------------------------

    @property
    def draw_order(self) -> float:
        """Y position to sort draws by, so nearer figures overlap farther ones.

        Returns
        -------
        float
        """
        return self.position[1]

    def draw(self, scene, shadow: bool = True) -> None:
        """Queue the actor, with its shadow and damage feedback.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            The frame under construction.
        shadow : bool, optional
            Draw the ground shadow first.
        """
        at = (self.position[0], self.position[1])
        if self.shake > 0.0:
            at = (at[0] + (np.random.random() - 0.5) * 2.0,
                  at[1] + (np.random.random() - 0.5) * 2.0)
        if shadow and self.anim.anim != "dead":
            scene.draw("sprite", "shadow", at=(at[0], at[1] + 2.0), size=(8.0, 4.0))
        tint = FLASH_TINT if self.flash > 0.0 else None
        hints = {"flip": self.anim.flip} if self.anim.flip else {}
        if tint is not None:
            hints["tint"] = tint
        scene.draw(
            "character",
            self.alias,
            at=at,
            size=(16.0, 16.0),
            state=self.anim.pose(self.attack_pose > 0.0, self.airborne),
            **hints,
        )


def draw_sorted(scene, actors, shadows: bool = True) -> None:
    """Draw actors back-to-front by position.

    There is no depth buffer in the batcher, so a top-down scene is ordered
    the way the reference is: painter's order on Y.

    Parameters
    ----------
    scene : chisurf.gui.chigame.scene.Scene
        The frame under construction.
    actors : iterable of Actor
        Everyone to draw; killed actors are skipped.
    shadows : bool, optional
        Pass through to :meth:`Actor.draw`.
    """
    for actor in sorted(
        (a for a in actors if a.health is None or a.health.alive),
        key=lambda a: a.draw_order,
    ):
        actor.draw(scene, shadow=shadows)


class Weapon:
    """A swung melee weapon — the reference's ``Weapon``.

    Two states, exactly as the reference draws them: carried (``held`` art
    rotated into the hand, behind the body when facing up) and striking (flat
    art offset ahead of the body with its damage area live).

    Parameters
    ----------
    alias : str, optional
        Pack sprite alias; ``"_held"`` is appended for the carried pose.
    damage : Damage, optional
        What a hit does.
    team : Team, optional
        Who the swings may not hurt.
    reach : float, optional
        Damage-area radius ahead of the holder.
    duration : float, optional
        Seconds a swing stays live.
    recharge : float, optional
        Seconds after a swing before the next may start. Without it an
        caller that polls ``swing`` every frame machine-guns the weapon,
        which the reference's attack timers exist to prevent.
    """

    def __init__(
        self,
        alias: str = "club",
        damage: Damage | None = None,
        team: Team | None = None,
        reach: float = 12.0,
        duration: float = 0.2,
        recharge: float = 0.15,
    ) -> None:
        self.alias = alias
        self.damage = damage if damage is not None else Damage(1.0, 120.0)
        self.team = team
        self.reach = reach
        self.duration = duration
        self.recharge = float(recharge)
        self.timer = 0.0
        self.direction = np.array([0.0, 1.0])
        self.cooldown = 0.0
        # Where the damage area anchors. Kept as a copy, updated by
        # :meth:`update`, because a weapon that is never drawn (an enemy's,
        # off screen) must still strike from where its holder stands.
        self.holder_position = np.zeros(2)

    def swing(self) -> bool:
        """Start a strike if one is not running or cooling.

        Returns
        -------
        bool
            Whether the swing started.
        """
        if self.timer > 0.0 or self.cooldown > 0.0:
            return False
        self.timer = self.duration
        self.cooldown = self.duration + self.recharge
        return True

    def update(self, dt: float, holder: Actor) -> None:
        """Track the holder and run the swing clock.

        Parameters
        ----------
        dt : float
            Frame step in seconds.
        holder : Actor
            Whose hand the weapon is in.
        """
        self.timer = max(0.0, self.timer - dt)
        self.cooldown = max(0.0, self.cooldown - dt)
        self.holder_position[:] = holder.position
        if np.any(holder.move_vector):
            norm = np.hypot(*holder.move_vector)
            self.direction = holder.move_vector / norm

    @property
    def striking(self) -> bool:
        """Whether the damage area is live.

        Returns
        -------
        bool
        """
        return self.timer > 0.0

    @property
    def area_centre(self) -> np.ndarray:
        """Where the damage area sits, ahead of the holder.

        Returns
        -------
        numpy.ndarray
        """
        return self.holder_position + self.direction * self.reach

    def draw(self, scene, holder: Actor) -> None:
        """Queue the weapon relative to its holder.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            The frame under construction.
        holder : Actor
            Whose hand it is in; also the anchor the damage area follows.
        """
        self.holder_position[:] = holder.position
        direction = self.direction
        if self.striking:
            at = (holder.position[0] - direction[0] * 7.0,
                  holder.position[1] - direction[1] * 5.0)
            scene.draw(
                "sprite", self.alias, at=at, size=(16.0, 16.0),
                state="idle",
            )
            return
        angle = math.atan2(direction[1], direction[0]) - math.pi / 2
        at = (holder.position[0] + direction[0] * 10.0,
              holder.position[1] + direction[1] * 10.0)
        scene.draw(
            "sprite",
            f"{self.alias}_held",
            at=at,
            size=(12.0, 12.0),
            rotation=angle,
        )


def strike(source: Weapon, actors: list[Actor], once: set | None = None) -> list[Actor]:
    """Apply a weapon's live damage area to everyone it overlaps.

    The port of the reference's ``DamageArea.on_area_entered``: an ally is
    skipped, everyone else takes the hit once per swing (``once`` collects who
    this swing has already touched).

    Parameters
    ----------
    source : Weapon
        The striking weapon.
    actors : list of Actor
        Candidates.
    once : set, optional
        Mutable set remembering already-hit actors this swing; created when
        omitted.

    Returns
    -------
    list of Actor
        Who was hit by this call.
    """
    if not source.striking:
        return []
    if once is None:
        once = set()
    centre = source.area_centre
    radius = source.reach
    hit: list[Actor] = []
    for actor in actors:
        if actor is None or actor in once:
            continue
        if actor.health is None or not actor.health.alive:
            continue
        if source.team is not None and source.team.is_ally(actor.team):
            continue
        reach = radius + max(actor.half_extent)
        if float(np.hypot(*(actor.position - centre))) > reach:
            continue
        actor.take_damage(source.damage, centre)
        once.add(actor)
        hit.append(actor)
    return hit


class Destroyable(Actor):
    """A breakable prop — the reference's ``Destroyable`` (a crate).

    Lives, takes knockback, flashes, shakes, bursts, and is gone. The burst
    art is queued where the prop stood for a moment after the body leaves.

    Parameters
    ----------
    position : tuple of float
        World position.
    life : float, optional
        Hits it survives.
    burst : str, optional
        Pack particle alias played on destruction.
    """

    def __init__(
        self,
        position: tuple[float, float],
        life: float = 3.0,
        burst: str = "burst_wood",
    ) -> None:
        super().__init__(
            position,
            alias="crate",
            speed=0.0,
            half_extent=(7.0, 7.0),
            maximum_life=life,
        )
        self.burst = burst
        self.burst_timer = 0.0
        self.dropping: list = []
        if self.health is not None:
            self.health.listeners.append(self._on_life)

    def _on_life(self, health: Health) -> None:
        if not health.alive:
            self.burst_timer = 0.5

    def update(self, dt: float) -> None:
        """Run knockback decay and the burst timer.

        Parameters
        ----------
        dt : float
            Frame step in seconds.
        """
        super().update(dt)
        if np.any(self.push_velocity):
            self.position += self.push_velocity * dt
            self.push_velocity *= max(0.0, 1.0 - 8.0 * dt)
        self.burst_timer = max(0.0, self.burst_timer - dt)

    def draw(self, scene, shadow: bool = True) -> None:
        """Draw the crate, or its burst if it has just gone.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            The frame under construction.
        shadow : bool, optional
            Unused; kept for the :meth:`Actor.draw` signature.
        """
        if self.health is not None and self.health.alive:
            super().draw(scene, shadow=False)
            return
        if self.burst_timer > 0.0:
            alpha = self.burst_timer / 0.5
            scene.draw(
                "sprite",
                self.burst,
                at=(self.position[0], self.position[1]),
                size=(24.0, 12.0) if alpha > 0.5 else (16.0, 8.0),
                alpha=alpha,
            )
