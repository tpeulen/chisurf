"""Pong, on the chigame engine.

This replaces a hand-written ``QPainter`` board. The rules, speeds and scoring
are carried over unchanged so the port is a change of renderer and input model,
not of the game; what changes is that it draws through
:mod:`chisurf.gui.chigame` and is driven by the abstract controller, which makes
it gamepad-playable and scriptable in a headless test.

Pong is the engine's first consumer because it exercises the parts everything
else needs: per-frame simulation, collision, input, text and audio.
"""

from __future__ import annotations

import math
import random

from qtpy import QtWidgets

from chisurf.gui import chigame
from chisurf.gui.chigame.assets import wavelength_to_srgb
from chisurf.gui.chigame.input import Action

try:
    from chisurf.gui.misc_helpers import persist_plugin_state
except ImportError:  # pragma: no cover - stand-alone use
    def persist_plugin_state(name):
        """Return an identity decorator when the host is unavailable."""
        return lambda cls: cls

#: The two sides are a FRET pair: the left optic emits as a donor, the right
#: absorbs and re-emits as an acceptor. A photon crossing the field therefore
#: changes colour at each bounce, which is the transfer made visible rather
#: than a decoration -- and it is why the field is worth watching.
DONOR_NM = 520.0
ACCEPTOR_NM = 612.0

#: Play field, in world units. Kept at the original board's pixel dimensions so
#: every speed and size below carries over without rescaling.
FIELD_W = 800.0
FIELD_H = 600.0

PADDLE_W = 12.0
PADDLE_H = 90.0
PADDLE_SPEED = 480.0

BALL_SIZE = 14.0
BASE_SPEED_X = 360.0
BASE_SPEED_Y = 300.0
CPU_SPEED = 420.0

WIN_SCORE = 7
SERVE_DELAY = 1.0

#: Arrows drive player one, WASD player two. The default binding table maps both
#: to the same actions, which is right for a single-player game and wrong here.
P1_BINDINGS = {
    "ArrowUp": Action.UP,
    "ArrowDown": Action.DOWN,
    "Enter": Action.CONFIRM,
    " ": Action.CONFIRM,
    "p": Action.MENU,
    "r": Action.CANCEL,
    "m": Action.SHOULDER_L,
    "n": Action.SHOULDER_R,
}
P2_BINDINGS = {"w": Action.UP, "s": Action.DOWN}


class Particle:
    """A single impact spark.

    Parameters
    ----------
    x, y : float
        Starting position in world units.
    vx, vy : float
        Velocity in world units per second.
    color : tuple of float
        sRGB RGB.
    life : float, optional
        Lifetime in seconds.
    """

    def __init__(self, x, y, vx, vy, color, life: float = 0.35) -> None:
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.color = color
        self.life = life
        self.max_life = life

    def update(self, dt: float) -> None:
        """Advance the spark.

        Parameters
        ----------
        dt : float
            Seconds elapsed.
        """
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += 600.0 * dt
        self.life -= dt


class PongGame(chigame.Game):
    """The rules and the drawing.

    Holds no Qt and no GPU objects, so the whole game can be stepped in a test
    with a fixed timestep and no window.
    """

    title = "Pong"
    background = (0.030, 0.034, 0.042, 1.0)
    music_context = "battle"

    def setup(self, host) -> None:
        """Bind controllers and start a game.

        Parameters
        ----------
        host : chisurf.gui.chigame.game.GameHost
            The host running this game.
        """
        self.host = host
        host.keys.bindings = dict(P1_BINDINGS)
        self.p2 = host.add_player(P2_BINDINGS)
        host.camera.center[:] = (FIELD_W * 0.5, FIELD_H * 0.5)
        host.camera.height = FIELD_H
        self.restart()

    def restart(self) -> None:
        """Reset scores, paddles and serve state."""
        self.player_score = 0
        self.cpu_score = 0
        self.rally = 0
        self.paddle_y = FIELD_H * 0.5
        self.cpu_y = FIELD_H * 0.5
        self.particles: list[Particle] = []
        self.paused = False
        self.vs_computer = True
        self.muted = False
        self.winner: str | None = None
        self.begin_serve()

    def begin_serve(self) -> None:
        """Centre the photon and start the serve countdown."""
        self.ball_nm = DONOR_NM
        self.ball_x = FIELD_W * 0.5
        self.ball_y = FIELD_H * 0.5
        self.ball_vx = 0.0
        self.ball_vy = 0.0
        self.serve_timer = SERVE_DELAY

    def launch(self) -> None:
        """Send the ball out at a random angle."""
        angle = random.uniform(-0.4, 0.4)
        direction = random.choice((-1.0, 1.0))
        self.ball_vx = direction * BASE_SPEED_X * math.cos(angle)
        self.ball_vy = BASE_SPEED_Y * math.sin(angle)

    def spawn_particles(self, x: float, y: float, color, count: int = 12) -> None:
        """Emit impact sparks.

        Parameters
        ----------
        x, y : float
            Impact point.
        color : tuple of float
            sRGB RGB.
        count : int, optional
            Number of sparks.
        """
        for _ in range(count):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(60.0, 260.0)
            self.particles.append(
                Particle(x, y, math.cos(angle) * speed, math.sin(angle) * speed, color)
            )

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

    def update(self, dt: float, keys) -> None:
        """Advance one frame.

        Parameters
        ----------
        dt : float
            Seconds elapsed.
        keys : chisurf.gui.chigame.input.InputMap
            Player one's controller.
        """
        if keys.just_pressed(Action.MENU):
            self.paused = not self.paused
        if keys.just_pressed(Action.CANCEL):
            self.restart()
            return
        if keys.just_pressed(Action.SHOULDER_L):
            self.vs_computer = not self.vs_computer
        if keys.just_pressed(Action.SHOULDER_R):
            self.muted = not self.muted
        if self.winner is not None:
            if keys.just_pressed(Action.CONFIRM):
                self.restart()
            return
        if self.paused:
            return

        half = PADDLE_H * 0.5
        move = keys.axis()[1]
        self.paddle_y = min(max(self.paddle_y + move * PADDLE_SPEED * dt, half), FIELD_H - half)

        if self.vs_computer:
            self._move_cpu(dt)
        else:
            move2 = self.p2.axis()[1]
            self.cpu_y = min(max(self.cpu_y + move2 * PADDLE_SPEED * dt, half), FIELD_H - half)

        if self.serve_timer > 0.0:
            self.serve_timer -= dt
            if self.serve_timer <= 0.0:
                self.launch()
        else:
            self._move_ball(dt)

        for particle in self.particles:
            particle.update(dt)
        self.particles = [p for p in self.particles if p.life > 0.0]

    def _move_cpu(self, dt: float) -> None:
        """Track the ball, leading it when it is incoming.

        Parameters
        ----------
        dt : float
            Seconds elapsed.
        """
        target = self.ball_y
        if self.ball_vx > 0.0:
            time_to_reach = (FIELD_W - PADDLE_W - 20.0 - self.ball_x) / max(self.ball_vx, 1e-3)
            target += self.ball_vy * time_to_reach
        diff = target - self.cpu_y
        half = PADDLE_H * 0.5
        if abs(diff) > 6.0:
            self.cpu_y += CPU_SPEED * dt * (1.0 if diff > 0 else -1.0)
        self.cpu_y = min(max(self.cpu_y, half), FIELD_H - half)

    def _move_ball(self, dt: float) -> None:
        """Advance the ball, bounce it, and score it.

        Parameters
        ----------
        dt : float
            Seconds elapsed.
        """
        self.ball_x += self.ball_vx * dt
        self.ball_y += self.ball_vy * dt
        radius = BALL_SIZE * 0.5

        if self.ball_y - radius <= 0.0:
            self.ball_y = radius
            self.ball_vy = abs(self.ball_vy)
            self._sfx("wall", 420.0)
        elif self.ball_y + radius >= FIELD_H:
            self.ball_y = FIELD_H - radius
            self.ball_vy = -abs(self.ball_vy)
            self._sfx("wall", 420.0)

        half = PADDLE_H * 0.5
        player_x = 20.0 + PADDLE_W * 0.5
        cpu_x = FIELD_W - 20.0 - PADDLE_W * 0.5

        if (
            self.ball_vx < 0.0
            and abs(self.ball_x - player_x) <= (PADDLE_W + BALL_SIZE) * 0.5
            and abs(self.ball_y - self.paddle_y) <= half + radius
        ):
            self._bounce(player_x, self.paddle_y, 1.0, DONOR_NM)
        elif (
            self.ball_vx > 0.0
            and abs(self.ball_x - cpu_x) <= (PADDLE_W + BALL_SIZE) * 0.5
            and abs(self.ball_y - self.cpu_y) <= half + radius
        ):
            self._bounce(cpu_x, self.cpu_y, -1.0, ACCEPTOR_NM)

        if self.ball_x < -BALL_SIZE:
            self._score("cpu")
        elif self.ball_x > FIELD_W + BALL_SIZE:
            self._score("player")

    def _bounce(self, paddle_x: float, paddle_y: float, direction: float, nm: float) -> None:
        """Reflect the ball off a paddle, steering by where it struck.

        Parameters
        ----------
        paddle_x, paddle_y : float
            Paddle centre.
        direction : float
            ``1`` to send the photon right, ``-1`` to send it left.
        nm : float
            Wavelength the struck optic re-emits at.
        """
        offset = (self.ball_y - paddle_y) / (PADDLE_H * 0.5)
        angle = offset * 0.9
        speed = math.hypot(self.ball_vx, self.ball_vy) * 1.03
        self.ball_vx = direction * abs(math.cos(angle) * speed)
        self.ball_vy = math.sin(angle) * speed
        self.ball_x = paddle_x + direction * (PADDLE_W + BALL_SIZE) * 0.5
        self.rally += 1
        # The photon leaves at the struck optic's wavelength: donor on the left,
        # acceptor on the right.
        self.ball_nm = nm
        self.spawn_particles(self.ball_x, self.ball_y, wavelength_to_srgb(nm))
        self._sfx("paddle", 660.0)

    def _score(self, who: str) -> None:
        """Award a point and either serve again or end the game.

        Parameters
        ----------
        who : {'player', 'cpu'}
            Who scored.
        """
        if who == "player":
            self.player_score += 1
        else:
            self.cpu_score += 1
        self.rally = 0
        self._sfx("score", 880.0 if who == "player" else 220.0)
        if self.player_score >= WIN_SCORE:
            self.winner = "Donor"
        elif self.cpu_score >= WIN_SCORE:
            self.winner = "Acceptor" if self.vs_computer else "Optic 2"
        else:
            self.begin_serve()

    def draw(self, scene) -> None:
        """Queue the frame.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            The frame under construction.
        """
        # The optical axis, not a decorative net.
        axis = (0.26, 0.29, 0.34, 0.9)
        for i in range(16):
            y = 20.0 + i * (FIELD_H - 40.0) / 15.0
            scene.draw("ui", "axis", at=(FIELD_W * 0.5, y), size=(2.0, 16.0), color=axis)

        # Two optics, each tinted by the wavelength it works at.
        scene.draw("optic", "donor",
                   at=(20.0 + PADDLE_W * 0.5, self.paddle_y),
                   size=(PADDLE_W, PADDLE_H), emission_nm=DONOR_NM)
        scene.draw("optic", "acceptor",
                   at=(FIELD_W - 20.0 - PADDLE_W * 0.5, self.cpu_y),
                   size=(PADDLE_W, PADDLE_H), emission_nm=ACCEPTOR_NM)

        for particle in self.particles:
            fade = max(particle.life / particle.max_life, 0.0)
            scene.draw("ui", "spark", at=(particle.x, particle.y),
                       size=(2.5 + 3.0 * fade, 2.5 + 3.0 * fade),
                       color=(*particle.color, fade))

        if self.winner is None:
            scene.draw("photon", "quantum", at=(self.ball_x, self.ball_y),
                       size=(BALL_SIZE, BALL_SIZE), emission_nm=self.ball_nm)

        scene.text(f"Donor: {self.player_score}", at=(FIELD_W * 0.30, 26.0),
                   height=20.0, align="center",
                   color=(*wavelength_to_srgb(DONOR_NM), 1.0))
        scene.text(
            f"{'Acceptor' if self.vs_computer else 'Optic 2'}: {self.cpu_score}",
            at=(FIELD_W * 0.70, 26.0), height=20.0, align="center",
            color=(*wavelength_to_srgb(ACCEPTOR_NM), 1.0),
        )
        scene.text(f"Transfers: {self.rally}", at=(FIELD_W * 0.5, 54.0), height=13.0,
                   align="center", color=(0.44, 0.48, 0.55, 1.0))

        if self.serve_timer > 0.0 and self.winner is None:
            scene.text(f"{math.ceil(self.serve_timer)}", at=(FIELD_W * 0.5, FIELD_H * 0.5),
                       height=60.0, align="center", color=(0.62, 0.68, 0.78, 1.0))
        if self.paused:
            scene.text("HELD", at=(FIELD_W * 0.5, FIELD_H * 0.5), height=44.0,
                       align="center", color=(0.35, 0.85, 0.80, 1.0))
        if self.winner is not None:
            scene.draw("ui", "panel", at=(FIELD_W * 0.5, FIELD_H * 0.5), size=(440.0, 120.0))
            scene.text(f"{self.winner} wins", at=(FIELD_W * 0.5, FIELD_H * 0.5 - 16.0),
                       height=34.0, align="center", color=(0.35, 0.85, 0.80, 1.0))
            scene.text("Confirm to run again", at=(FIELD_W * 0.5, FIELD_H * 0.5 + 26.0),
                       height=16.0, align="center")

        scene.text(
            "Up/Down optic   Menu hold   Cancel reset   L mode   R sound"
            + ("   [muted]" if self.muted else ""),
            at=(FIELD_W * 0.5, FIELD_H - 18.0),
            height=15.0,
            align="center",
            color=(0.44, 0.48, 0.55, 1.0),
        )


@persist_plugin_state("pong")
class Pong(QtWidgets.QWidget):
    """Dockable container hosting the game.

    Parameters
    ----------
    parent : QWidget, optional
        Parent widget.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Pong")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.game = PongGame()
        canvas, self.host = chigame.create_widget(self.game, parent=self)
        bar = QtWidgets.QHBoxLayout()
        bar.setContentsMargins(4, 2, 4, 0)
        bar.addWidget(chigame.sound_button(self.host, self))
        bar.addStretch(1)
        layout.addLayout(bar)
        layout.addWidget(canvas)
        self.resize(820, 640)
