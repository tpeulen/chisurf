"""Breakout, on the chigame engine.

Ported from a hand-written ``QPainter`` board. Rules, speeds, level layout and
scoring carry over unchanged; what changes is that it draws through
:mod:`chisurf.gui.chigame` and is driven by the abstract controller.

Breakout is the engine's batching test: eighty bricks, a paddle, a ball and a
particle shower all resolve to a single instanced draw call.
"""

from __future__ import annotations

import math
import random

from qtpy import QtWidgets

from chisurf.gui import chigame
from chisurf.gui.chigame.input import Action

try:
    from chisurf.gui.misc_helpers import persist_plugin_state
except ImportError:  # pragma: no cover - stand-alone use

    def persist_plugin_state(name):
        """Return an identity decorator when the host is unavailable."""
        return lambda cls: cls


#: Play field in world units, at the original board's pixel dimensions so every
#: speed and size below carries over without rescaling.
W = 800.0
H = 650.0

PADDLE_W = 100.0
PADDLE_H = 16.0
PADDLE_Y = H - 40.0
PADDLE_SPEED = 520.0

BALL_SIZE = 12.0
BASE_BALL_SPEED = 330.0

BRICK_ROWS = 8
BRICK_COLS = 10
BRICK_W = (W - 60.0) / BRICK_COLS
BRICK_H = 22.0
BRICK_TOP = 50.0
BRICK_PAD = 30.0

LIVES = 3

#: One colour per row, and how many hits each row takes. The top three rows are
#: tougher, which is what makes clearing downward feel like progress.
ROW_COLORS = [
    (1.00, 0.24, 0.24),
    (1.00, 0.47, 0.16),
    (1.00, 0.78, 0.16),
    (0.39, 0.86, 0.24),
    (0.24, 0.71, 1.00),
    (0.39, 0.39, 1.00),
    (0.71, 0.31, 1.00),
    (1.00, 0.31, 0.78),
]
ROW_HARDNESS = [2, 2, 2, 1, 1, 1, 1, 1]

BINDINGS = {
    "ArrowLeft": Action.LEFT,
    "ArrowRight": Action.RIGHT,
    "a": Action.LEFT,
    "d": Action.RIGHT,
    " ": Action.CONFIRM,
    "Enter": Action.CONFIRM,
    "p": Action.MENU,
    "r": Action.CANCEL,
    "m": Action.SHOULDER_R,
}


class Brick:
    """One brick.

    Parameters
    ----------
    x, y : float
        Centre in world units.
    w, h : float
        Size in world units.
    color : tuple of float
        sRGB RGB.
    hp : int
        Hits remaining.
    """

    def __init__(self, x, y, w, h, color, hp) -> None:
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.color = color
        self.hp = hp
        self.max_hp = hp

    @property
    def alive(self) -> bool:
        """Whether the brick is still standing.

        Returns
        -------
        bool
            True while it has hits left.
        """
        return self.hp > 0

    def hit(self) -> bool:
        """Take one hit.

        Returns
        -------
        bool
            True when this hit destroyed the brick.
        """
        self.hp -= 1
        return self.hp <= 0


class Particle:
    """A brick fragment.

    Parameters
    ----------
    x, y : float
        Starting position.
    vx, vy : float
        Velocity in world units per second.
    color : tuple of float
        sRGB RGB.
    life : float, optional
        Lifetime in seconds.
    """

    def __init__(self, x, y, vx, vy, color, life: float = 0.45) -> None:
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.color = color
        self.life = life
        self.max_life = life

    def update(self, dt: float) -> None:
        """Advance the fragment.

        Parameters
        ----------
        dt : float
            Seconds elapsed.
        """
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += 700.0 * dt
        self.life -= dt


class BreakoutGame(chigame.Game):
    """The rules and the drawing, free of Qt and of GPU objects."""

    title = "Breakout"
    background = (0.055, 0.055, 0.11, 1.0)
    music_context = "overworld"

    def setup(self, host) -> None:
        """Bind the controller and start a game.

        Parameters
        ----------
        host : chisurf.gui.chigame.game.GameHost
            The host running this game.
        """
        self.host = host
        host.keys.bindings = dict(BINDINGS)
        host.camera.center[:] = (W * 0.5, H * 0.5)
        host.camera.height = H
        self.restart()

    def restart(self) -> None:
        """Reset score, level and lives, and build the first level."""
        self.score = 0
        self.level = 1
        self.lives = LIVES
        self.paused = False
        self.muted = False
        self.message: str | None = None
        self.init_level()

    def init_level(self) -> None:
        """Lay out the brick grid and re-serve."""
        self.bricks: list[Brick] = []
        self.particles: list[Particle] = []
        for row in range(BRICK_ROWS):
            color = ROW_COLORS[row % len(ROW_COLORS)]
            hp = ROW_HARDNESS[row % len(ROW_HARDNESS)]
            for col in range(BRICK_COLS):
                x = BRICK_PAD + col * BRICK_W + BRICK_W * 0.5
                y = BRICK_TOP + row * (BRICK_H + 4.0) + BRICK_H * 0.5
                self.bricks.append(Brick(x, y, BRICK_W - 8.0, BRICK_H, color, hp))
        self.paddle_x = W * 0.5
        self.serve()

    def serve(self) -> None:
        """Stick the ball to the paddle and wait for a launch."""
        self.stuck = True
        self.ball_x = self.paddle_x
        self.ball_y = PADDLE_Y - PADDLE_H * 0.5 - BALL_SIZE * 0.5
        self.ball_vx = 0.0
        self.ball_vy = 0.0

    def launch(self) -> None:
        """Send the ball upward at a random angle."""
        angle = random.uniform(-math.pi / 4, math.pi / 4)
        direction = random.choice((-1.0, 1.0))
        self.ball_vx = math.cos(angle) * BASE_BALL_SPEED * direction
        self.ball_vy = -abs(math.sin(angle) * BASE_BALL_SPEED) - BASE_BALL_SPEED * 0.6
        self.stuck = False
        self._sfx("launch", 540.0)

    def _sfx(self, name: str, frequency: float) -> None:
        """Play a sound effect unless muted.

        Parameters
        ----------
        name : str
            Effect name.
        frequency : float
            Pitch in Hz.
        """
        if not self.muted:
            self.host.audio.sfx(name, frequency)

    def spawn_particles(self, x, y, color, count: int = 15) -> None:
        """Emit brick fragments.

        Parameters
        ----------
        x, y : float
            Impact point.
        color : tuple of float
            sRGB RGB.
        count : int, optional
            Number of fragments.
        """
        for _ in range(count):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(60.0, 280.0)
            self.particles.append(
                Particle(x, y, math.cos(angle) * speed, math.sin(angle) * speed, color)
            )

    def update(self, dt: float, keys) -> None:
        """Advance one frame.

        Parameters
        ----------
        dt : float
            Seconds elapsed.
        keys : chisurf.gui.chigame.input.InputMap
            Controller state.
        """
        if keys.just_pressed(Action.MENU):
            self.paused = not self.paused
        if keys.just_pressed(Action.CANCEL):
            self.restart()
            return
        if keys.just_pressed(Action.SHOULDER_R):
            self.muted = not self.muted
        if self.message is not None:
            if keys.just_pressed(Action.CONFIRM):
                self.restart()
            return
        if self.paused:
            return

        half = PADDLE_W * 0.5
        self.paddle_x = min(
            max(self.paddle_x + keys.axis()[0] * PADDLE_SPEED * dt, half), W - half
        )

        if self.stuck:
            self.ball_x = self.paddle_x
            if keys.just_pressed(Action.CONFIRM):
                self.launch()
        else:
            self._move_ball(dt)

        for particle in self.particles:
            particle.update(dt)
        self.particles = [p for p in self.particles if p.life > 0.0]

    def _move_ball(self, dt: float) -> None:
        """Advance the ball and resolve every collision.

        Parameters
        ----------
        dt : float
            Seconds elapsed.
        """
        self.ball_x += self.ball_vx * dt
        self.ball_y += self.ball_vy * dt
        radius = BALL_SIZE * 0.5

        if self.ball_x - radius <= 0.0:
            self.ball_x = radius
            self.ball_vx = abs(self.ball_vx)
            self._sfx("wall", 420.0)
        elif self.ball_x + radius >= W:
            self.ball_x = W - radius
            self.ball_vx = -abs(self.ball_vx)
            self._sfx("wall", 420.0)
        if self.ball_y - radius <= 0.0:
            self.ball_y = radius
            self.ball_vy = abs(self.ball_vy)
            self._sfx("wall", 420.0)

        # Paddle: the strike point steers the bounce, as in the original.
        if (
            self.ball_vy > 0.0
            and abs(self.ball_y - PADDLE_Y) <= (PADDLE_H + BALL_SIZE) * 0.5
            and abs(self.ball_x - self.paddle_x) <= (PADDLE_W + BALL_SIZE) * 0.5
        ):
            offset = (self.ball_x - self.paddle_x) / (PADDLE_W * 0.5)
            speed = math.hypot(self.ball_vx, self.ball_vy)
            angle = offset * 1.0
            self.ball_vx = math.sin(angle) * speed
            self.ball_vy = -abs(math.cos(angle) * speed)
            self.ball_y = PADDLE_Y - (PADDLE_H + BALL_SIZE) * 0.5
            self._sfx("paddle", 660.0)

        self._hit_bricks()

        if self.ball_y - radius > H:
            self.lives -= 1
            self._sfx("lost", 180.0)
            if self.lives <= 0:
                self.message = "Game over"
            else:
                self.serve()

    def _hit_bricks(self) -> None:
        """Break the first brick the ball overlaps and bounce off it."""
        radius = BALL_SIZE * 0.5
        for brick in self.bricks:
            if not brick.alive:
                continue
            if (
                abs(self.ball_x - brick.x) > brick.w * 0.5 + radius
                or abs(self.ball_y - brick.y) > brick.h * 0.5 + radius
            ):
                continue
            # Bounce off whichever face was actually crossed: comparing the
            # overlap depths is what stops the ball tunnelling along a row.
            overlap_x = brick.w * 0.5 + radius - abs(self.ball_x - brick.x)
            overlap_y = brick.h * 0.5 + radius - abs(self.ball_y - brick.y)
            if overlap_x < overlap_y:
                self.ball_vx = -self.ball_vx
            else:
                self.ball_vy = -self.ball_vy
            if brick.hit():
                self.score += 10 * brick.max_hp
                self.spawn_particles(brick.x, brick.y, brick.color)
                self._sfx("break", 780.0)
            else:
                self._sfx("crack", 520.0)
            break

        if all(not brick.alive for brick in self.bricks):
            self.level += 1
            self.init_level()

    def draw(self, scene) -> None:
        """Queue the frame.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            Frame under construction.
        """
        for brick in self.bricks:
            if not brick.alive:
                continue
            # A damaged brick reads as dimmer, so hardness is visible.
            shade = 1.0 if brick.hp >= brick.max_hp else 0.55
            scene.draw(
                "ui", "bar",
                at=(brick.x, brick.y),
                size=(brick.w, brick.h),
                color=(*[c * shade for c in brick.color], 1.0),
            )

        scene.draw(
            "ui", "bar",
            at=(self.paddle_x, PADDLE_Y),
            size=(PADDLE_W, PADDLE_H),
            color=(0.42, 0.66, 1.0, 1.0),
        )

        for particle in self.particles:
            fade = max(particle.life / particle.max_life, 0.0)
            scene.draw(
                "ui", "spark",
                at=(particle.x, particle.y),
                size=(4.0 * fade + 2.0, 4.0 * fade + 2.0),
                color=(*particle.color, fade),
            )

        scene.draw("dye", "ball", at=(self.ball_x, self.ball_y),
                   size=(BALL_SIZE, BALL_SIZE), emission_nm=575.0)

        scene.text(f"Score: {self.score}", at=(14.0, 20.0), height=18.0)
        scene.text(f"Level: {self.level}", at=(W * 0.5, 20.0), height=18.0, align="center")
        scene.text("Lives:", at=(W - 76.0, 20.0), height=18.0, align="right")
        for index in range(self.lives):
            scene.draw(
                "ui", "life",
                at=(W - 62.0 + index * 20.0, 20.0),
                size=(13.0, 13.0),
                color=(1.0, 0.32, 0.42, 1.0),
            )

        if self.stuck and self.message is None and not self.paused:
            scene.text("Confirm to launch", at=(W * 0.5, H * 0.45), height=22.0,
                       align="center", color=(0.80, 0.83, 0.95, 1.0))
        if self.paused:
            scene.text("PAUSED", at=(W * 0.5, H * 0.45), height=44.0,
                       align="center", color=(1.0, 0.85, 0.30, 1.0))
        if self.message is not None:
            scene.draw("ui", "panel", at=(W * 0.5, H * 0.5), size=(420.0, 110.0))
            scene.text(self.message, at=(W * 0.5, H * 0.5 - 14.0), height=34.0,
                       align="center", color=(1.0, 0.85, 0.30, 1.0))
            scene.text("Confirm to play again", at=(W * 0.5, H * 0.5 + 24.0), height=16.0,
                       align="center")

        scene.text(
            "Left/Right move   Confirm launch   Menu pause   Cancel restart   R sound"
            + ("   [muted]" if self.muted else ""),
            at=(W * 0.5, H - 12.0), height=14.0, align="center",
            color=(0.58, 0.61, 0.75, 1.0),
        )


@persist_plugin_state("breakout")
class Breakout(QtWidgets.QWidget):
    """Dockable container hosting the game.

    Parameters
    ----------
    parent : QWidget, optional
        Parent widget.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Breakout")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.game = BreakoutGame()
        canvas, self.host = chigame.create_widget(self.game, parent=self)
        layout.addWidget(canvas)
        self.resize(820, 690)
