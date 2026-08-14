"""Steering behaviors — how non-player figures choose where to walk.

A port of the reference's ``system/behavior``: follow a target inside a comfort
band (:class:`Follow`), patrol waypoints with waits (:class:`Patrol`), and
notice things within a radius (:class:`Sense`). Each behavior is a small object
that writes ``move_vector`` on its actor once per frame; the actor still owns
movement and collision, so a behavior can never shove a figure through a wall.
"""

from __future__ import annotations

import math
import random

import numpy as np

from .actors import Actor


class Follow:
    """Track a target, keeping a comfortable distance.

    The port of ``behavior_follow.gd``: walk at the target while farther than
    ``max_distance``, back off while closer than ``min_distance``, and stop in
    the band between.

    Parameters
    ----------
    actor : Actor
        Who is steered.
    target : callable or Actor
        What to follow — an actor, or a zero-argument callable returning a
        position, so a follower can chase a marker the player moves.
    min_distance : float, optional
        Stop closing inside this radius.
    max_distance : float, optional
        Start closing beyond this radius.
    """

    def __init__(
        self,
        actor: Actor,
        target,
        min_distance: float = 8.0,
        max_distance: float = 24.0,
    ) -> None:
        self.actor = actor
        self.target = target
        self.min_distance = min_distance
        self.max_distance = max_distance

    def update(self, dt: float) -> None:
        """Steer the actor for this frame.

        Parameters
        ----------
        dt : float
            Frame step in seconds (unused; the band logic is stateless).
        """
        position = self._target_position()
        away = position - self.actor.position
        distance = float(np.hypot(*away))
        if distance > self.max_distance:
            self.actor.move_vector[:] = away / distance
        elif distance < self.min_distance and distance > 1e-6:
            self.actor.move_vector[:] = -away / distance
        else:
            self.actor.move_vector[:] = 0.0

    def _target_position(self) -> np.ndarray:
        if isinstance(self.target, Actor):
            return self.target.position
        value = self.target()
        return np.asarray(value, dtype=np.float64)


class Patrol:
    """Walk a waypoint loop, pausing at points.

    The port of ``behavior_follow_path.gd``: nearest-point entry, one point at
    a time, optional waits at each point or only at the ends, and either a loop
    or a ping-pong.

    Parameters
    ----------
    actor : Actor
        Who is steered.
    points : iterable of tuple of float
        Waypoints in order.
    loop : bool, optional
        Wrap at the end rather than reversing.
    wait_time : float, optional
        Seconds to pause where a wait applies.
    wait_each_point : bool, optional
        Wait everywhere rather than only at the ends.
    wait_chance : float, optional
        Probability each point triggers its wait, 0..1.
    precision : float, optional
        How close counts as reached.
    """

    def __init__(
        self,
        actor: Actor,
        points,
        loop: bool = False,
        wait_time: float = 1.0,
        wait_each_point: bool = False,
        wait_chance: float = 0.0,
        precision: float = 3.0,
    ) -> None:
        self.actor = actor
        self.points = [np.asarray(p, dtype=np.float64) for p in points]
        self.loop = loop
        self.wait_time = wait_time
        self.wait_each_point = wait_each_point
        self.wait_chance = wait_chance
        self.precision = precision
        self.index = self._closest_point()
        self.direction = 1
        self.wait_timer = 0.0

    def _closest_point(self) -> int:
        if not self.points:
            return 0
        deltas = [float(np.hypot(*(p - self.actor.position))) for p in self.points]
        return int(np.argmin(deltas))

    def update(self, dt: float) -> None:
        """Advance the patrol.

        Parameters
        ----------
        dt : float
            Frame step in seconds.
        """
        if not self.points:
            self.actor.move_vector[:] = 0.0
            return
        if self.wait_timer > 0.0:
            self.wait_timer = max(0.0, self.wait_timer - dt)
            self.actor.move_vector[:] = 0.0
            return
        target = self.points[self.index]
        away = target - self.actor.position
        distance = float(np.hypot(*away))
        if distance <= self.precision:
            self._arrive()
            return
        self.actor.move_vector[:] = away / distance

    def _arrive(self) -> None:
        at_end = self.index in (0, len(self.points) - 1)
        waits = self.wait_each_point or (at_end and self.wait_chance == 0.0)
        if random.random() < self.wait_chance:
            waits = True
        if waits and self.wait_time > 0.0:
            self.wait_timer = self.wait_time
        if self.loop:
            self.index = (self.index + 1) % len(self.points)
        else:
            if self.index == len(self.points) - 1:
                self.direction = -1
            elif self.index == 0:
                self.direction = 1
            self.index += self.direction


class Sense:
    """A radius that notices actors.

    The port of ``area_target_finder.gd``: while something eligible is inside
    the radius it is the found target; when it leaves, the target is dropped.

    Parameters
    ----------
    radius : float, optional
        Sense range.
    eligible : callable, optional
        ``actor -> bool`` filter; everything qualifies when omitted.
    """

    def __init__(self, radius: float = 48.0, eligible=None) -> None:
        self.radius = radius
        self.eligible = eligible
        self.target: Actor | None = None

    def update(self, actor: Actor, actors: list[Actor]) -> Actor | None:
        """(Re)pick the target among nearby actors.

        Parameters
        ----------
        actor : Actor
            The sensing actor, excluded from candidates.
        actors : list of Actor
            The field to sense in.

        Returns
        -------
        Actor or None
            The current target.
        """
        if self.target is not None:
            distance = float(np.hypot(*(self.target.position - actor.position)))
            gone = (
                self.target.health is not None and not self.target.health.alive
            ) or distance > self.radius * 1.15
            if gone:
                self.target = None
        if self.target is None:
            best = None
            best_distance = self.radius
            for other in actors:
                if other is actor:
                    continue
                if other.health is not None and not other.health.alive:
                    continue
                if self.eligible is not None and not self.eligible(other):
                    continue
                distance = float(np.hypot(*(other.position - actor.position)))
                if distance < best_distance:
                    best, best_distance = other, distance
            self.target = best
        return self.target


def wander(actor: Actor, dt: float, scale: float = 24.0, drag: float = 2.0) -> None:
    """A drifting walk for idle wildlife.

    Not in the reference — its animals follow paths — but a top-down world of
    documents wants beasts that amble. A heading performs a random walk and
    decays toward rest, so the figure wanders without leaving its neighbourhood.

    Parameters
    ----------
    actor : Actor
        Who is steered.
    dt : float
        Frame step in seconds.
    scale : float, optional
        Heading noise magnitude.
    drag : float, optional
        How quickly the walk settles toward standing.
    """
    heading = getattr(actor, "_wander_heading", 0.0)
    heading += random.uniform(-scale, scale) * dt
    heading *= max(0.0, 1.0 - drag * dt)
    actor._wander_heading = heading
    speed = min(1.0, abs(heading) / math.pi)
    actor.move_vector[:] = (math.cos(heading), math.sin(heading)) if speed > 0.15 else 0.0
