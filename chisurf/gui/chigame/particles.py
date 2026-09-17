"""Short-lived things: sparks, orbs that fly to somebody, numbers that rise.

Ported from the particle and floating-text layer of a small MIT-licensed
top-down RPG kept under ``junk/pyzelda-rpg``, generalised and made
frame-rate-independent. Three behaviours carry the whole thing, and each one is
a specific piece of game feel that is otherwise missing:

* **A number that rises and fades.** Damage, experience, "unbound". A game
  without this makes the player read a bar to find out whether anything
  happened; with it, the world says so where the thing happened.
* **An orb that flies to a target.** The pickup arc. It matters because it
  connects a cause to an effect *spatially* -- the reward visibly comes from
  the creature and goes into you -- which no HUD counter can do.
* **A one-shot burst.** Impact, footfall, a label coming off.

All three are one dataclass rather than a hierarchy, because they differ only
in which fields are set and a three-class tower for eleven floats is its own
kind of cost. The look is *semantic*: a particle names a kind and a name and
the asset pack decides what that is, exactly as :meth:`.Scene.draw` does, so
particles are as swappable as everything else.

Two things are deliberately not the way the reference had them. Motion is
integrated against ``dt`` rather than counted in frames, so a spark's life does
not depend on how fast the machine is; and the field has a **cap**, because an
emitter in a loop is the classic way a particle system turns into a frame
budget and nothing about the reference stopped it.
"""

from __future__ import annotations

import dataclasses
import math
import random

#: How many particles a field will hold before it starts refusing new ones. A
#: few hundred is far past what reads as busy at this scale, and well short of
#: what costs a frame.
LIMIT = 512

#: Default seconds a particle lives.
SPAN = 0.9

#: How close an orb must get to its target before it is considered delivered.
#: In world units; the reference used 16 pixels of a 64-pixel tile.
ARRIVAL = 3.0


@dataclasses.dataclass
class Particle:
    """One short-lived thing.

    Attributes
    ----------
    x, y : float
        Position in world units.
    vx, vy : float
        Velocity in world units per second.
    age : float
        Seconds lived so far.
    span : float
        Seconds it lives for. It dies at ``age >= span`` whatever else is true,
        which is the backstop that keeps an orb whose target walked away from
        living for ever.
    kind, name : str
        Passed to the asset pack, so what a spark *looks* like is not decided
        here.
    size : float
        Footprint in world units.
    color : tuple of float or None
        An explicit sRGB RGBA override, or ``None`` to let the pack choose.
        Alpha is multiplied by the fade, so a pack colour still fades out.
    gravity : float
        World units per second squared, added to ``vy``.
    drag : float
        Fraction of velocity shed per second, 0..1.
    rise : float
        World units to drift upward over the particle's whole life, on top of
        the velocity. This is what makes a number read as a number rather than
        as debris.
    target : tuple of float or None
        Fly towards this instead of coasting.
    speed : float
        World units per second while homing.
    text : str
        Drawn as text instead of as a sprite when set.
    height : float
        Text cell height in world units.
    hints : dict
        Extra facts for the asset pack, e.g. ``emission_nm``.
    """

    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    age: float = 0.0
    span: float = SPAN
    kind: str = "particle"
    name: str = ""
    size: float = 2.0
    color: tuple[float, float, float, float] | None = None
    gravity: float = 0.0
    drag: float = 0.0
    rise: float = 0.0
    target: tuple[float, float] | None = None
    speed: float = 0.0
    text: str = ""
    height: float = 6.0
    hints: dict = dataclasses.field(default_factory=dict)

    @property
    def progress(self) -> float:
        """How far through its life it is, 0..1.

        Returns
        -------
        float
            Clamped.
        """
        return min(self.age / self.span, 1.0) if self.span > 0.0 else 1.0

    @property
    def fade(self) -> float:
        """Its current opacity, 1 at birth and 0 at the end.

        Returns
        -------
        float
            A multiplier for alpha.
        """
        return 1.0 - self.progress

    @property
    def spent(self) -> bool:
        """Whether it should be removed.

        Returns
        -------
        bool
            True once its span is used up, or once it has reached the target it
            was flying to.
        """
        if self.age >= self.span:
            return True
        if self.target is not None:
            return math.hypot(self.target[0] - self.x, self.target[1] - self.y) <= ARRIVAL
        return False

    def step(self, dt: float) -> None:
        """Advance it by one frame.

        Parameters
        ----------
        dt : float
            Seconds elapsed.
        """
        self.age += dt
        if self.target is not None and self.speed > 0.0:
            dx = self.target[0] - self.x
            dy = self.target[1] - self.y
            gap = math.hypot(dx, dy)
            if gap > 0.0:
                # Never overshoot: the step is capped at what is left, which is
                # what stops an orb orbiting a target it is faster than.
                travel = min(self.speed * dt, gap)
                self.x += dx / gap * travel
                self.y += dy / gap * travel
            return
        if self.drag:
            keep = max(0.0, 1.0 - self.drag * dt)
            self.vx *= keep
            self.vy *= keep
        self.vy += self.gravity * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        if self.rise:
            self.y -= self.rise / self.span * dt if self.span > 0.0 else 0.0


class Field:
    """Every live particle, updated and drawn together.

    Parameters
    ----------
    limit : int, optional
        How many to hold. Emitting into a full field is a no-op rather than an
        error: a visual flourish must never be the thing that raises.
    seed : int, optional
        For the scatter, so a replay is a replay.
    """

    def __init__(self, limit: int = LIMIT, seed: int = 0x5EED) -> None:
        self.limit = int(limit)
        self.particles: list[Particle] = []
        self._rng = random.Random(seed)

    def __len__(self) -> int:
        """How many are alive.

        Returns
        -------
        int
            Live particle count.
        """
        return len(self.particles)

    def clear(self) -> None:
        """Drop everything, e.g. on a scene change."""
        self.particles.clear()

    def add(self, particle: Particle) -> Particle | None:
        """Put one in, if there is room.

        Parameters
        ----------
        particle : Particle
            The particle.

        Returns
        -------
        Particle or None
            The particle, or ``None`` when the field was full.
        """
        if len(self.particles) >= self.limit:
            return None
        self.particles.append(particle)
        return particle

    def rise(
        self,
        text: str,
        at: tuple[float, float],
        color: tuple[float, float, float, float] = (1.0, 0.92, 0.45, 1.0),
        span: float = 1.2,
        distance: float = 16.0,
        height: float = 7.0,
    ) -> Particle | None:
        """A number or a word that floats up from a point and fades.

        Parameters
        ----------
        text : str
            What it says. Keep it short -- this is a reaction, not a sentence.
        at : tuple of float
            Where it starts, in world units.
        color : tuple of float, optional
            sRGB RGBA.
        span : float, optional
            Seconds.
        distance : float, optional
            How far it climbs over its life, in world units.
        height : float, optional
            Text cell height.

        Returns
        -------
        Particle or None
            The particle, or ``None`` when the field was full.
        """
        return self.add(
            Particle(
                x=at[0], y=at[1], span=span, rise=distance, color=color, text=text, height=height
            )
        )

    def orbs(
        self,
        at: tuple[float, float],
        target: tuple[float, float],
        count: int = 5,
        speed: float = 70.0,
        kind: str = "photon",
        name: str = "",
        size: float = 2.6,
        span: float = 1.5,
        scatter: float = 4.0,
        **hints,
    ) -> list[Particle]:
        """A handful of things that fly from one place to another.

        The scatter at the spawn point is what makes several orbs read as
        several rather than as one thick one, and it is why they arrive spread
        out in time.

        Parameters
        ----------
        at : tuple of float
            Where they come from.
        target : tuple of float
            Where they go. A fixed point, not a live reference -- an orb chasing
            a moving player never lands cleanly and reads as a bug.
        count : int, optional
            How many.
        speed : float, optional
            World units per second.
        kind, name : str, optional
            What the pack should draw.
        size : float, optional
            Footprint.
        span : float, optional
            Seconds before giving up and vanishing.
        scatter : float, optional
            Spawn spread, in world units.
        **hints
            Extra facts for the pack, e.g. ``emission_nm``.

        Returns
        -------
        list of Particle
            Those that fitted.
        """
        made = []
        for _ in range(max(0, int(count))):
            one = self.add(
                Particle(
                    x=at[0] + self._rng.uniform(-scatter, scatter),
                    y=at[1] + self._rng.uniform(-scatter, scatter),
                    span=span,
                    target=tuple(target),
                    speed=speed * self._rng.uniform(0.8, 1.25),
                    kind=kind,
                    name=name,
                    size=size,
                    hints=dict(hints),
                )
            )
            if one is not None:
                made.append(one)
        return made

    def burst(
        self,
        at: tuple[float, float],
        count: int = 8,
        kind: str = "photon",
        name: str = "",
        size: float = 1.8,
        span: float = 0.55,
        speed: float = 40.0,
        gravity: float = 0.0,
        drag: float = 2.4,
        radius: float = 0.0,
        **hints,
    ) -> list[Particle]:
        """A one-shot spray outward from a point.

        Parameters
        ----------
        at : tuple of float
            The origin.
        count : int, optional
            How many.
        kind, name : str, optional
            What the pack should draw. The default is the *bright core* rather
            than the halo: a spark drawn as a halo over something that is
            already glowing is invisible, which is not a thing an assertion
            will ever tell you.
        size : float, optional
            Footprint.
        span : float, optional
            Seconds.
        speed : float, optional
            Initial speed, varied per particle.
        gravity : float, optional
            World units per second squared.
        drag : float, optional
            Fraction of speed shed per second. A little drag is what turns a
            spray into an impact rather than a firework.
        radius : float, optional
            Spawn the ring this far out instead of at the point. Needed more
            often than it sounds: a spark thrown from the middle of something
            that is already glowing spends its whole life inside that glow and
            is invisible, and no assertion will ever say so. Starting at the
            glow's edge puts it against the dark.
        **hints
            Extra facts for the pack.

        Returns
        -------
        list of Particle
            Those that fitted.
        """
        made = []
        for index in range(max(0, int(count))):
            angle = (index / max(1, count)) * math.tau + self._rng.uniform(-0.25, 0.25)
            rate = speed * self._rng.uniform(0.55, 1.35)
            one = self.add(
                Particle(
                    x=at[0] + math.cos(angle) * radius,
                    y=at[1] + math.sin(angle) * radius,
                    vx=math.cos(angle) * rate,
                    vy=math.sin(angle) * rate,
                    span=span * self._rng.uniform(0.7, 1.3),
                    kind=kind,
                    name=name,
                    size=size,
                    gravity=gravity,
                    drag=drag,
                    hints=dict(hints),
                )
            )
            if one is not None:
                made.append(one)
        return made

    def update(self, dt: float) -> None:
        """Advance everything and drop what is finished.

        Parameters
        ----------
        dt : float
            Seconds elapsed.
        """
        if not self.particles:
            return
        for particle in self.particles:
            particle.step(dt)
        self.particles = [one for one in self.particles if not one.spent]

    def draw(self, scene) -> None:
        """Emit every particle into a frame.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            The frame under construction.
        """
        for one in self.particles:
            fade = one.fade
            if one.text:
                colour = one.color or (1.0, 1.0, 1.0, 1.0)
                scene.text(
                    one.text,
                    at=(one.x, one.y),
                    height=one.height,
                    color=(colour[0], colour[1], colour[2], colour[3] * fade),
                    align="center",
                )
                continue
            hints = dict(one.hints)
            if one.color is not None:
                hints["color"] = one.color
            # `alpha` is a Scene-level hint that scales whatever the pack
            # chose, so a particle fades without knowing its own colour.
            hints["alpha"] = fade * float(hints.get("alpha", 1.0))
            scene.draw(one.kind, one.name, at=(one.x, one.y), size=(one.size, one.size), **hints)
