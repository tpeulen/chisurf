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


from .model import (
    ACCEPTOR_NM,
    BALL_SIZE,
    BASE_SPEED_X,
    BASE_SPEED_Y,
    CPU_SPEED,
    DONOR_NM,
    FIELD_H,
    FIELD_W,
    PADDLE_H,
    PADDLE_SPEED,
    PADDLE_W,
    SERVE_DELAY,
    WIN_SCORE,
    Particle,
    PongModel,
)

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


class _LegacyInput:
    """Adapt the engine's enum actions to the shared simulation vocabulary."""

    def __init__(self, keys):
        self.keys = keys

    def just_pressed(self, action):
        return self.keys.just_pressed(Action(action))

    def axis(self):
        return self.keys.axis()


class PongGame(PongModel, chigame.Game):
    """Legacy Qt renderer over the shared, toolkit-free Pong rules."""

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

    def update(self, dt, keys):
        super().update(dt, _LegacyInput(keys))

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
        scene.draw(
            "optic",
            "donor",
            at=(20.0 + PADDLE_W * 0.5, self.paddle_y),
            size=(PADDLE_W, PADDLE_H),
            emission_nm=DONOR_NM,
        )
        scene.draw(
            "optic",
            "acceptor",
            at=(FIELD_W - 20.0 - PADDLE_W * 0.5, self.cpu_y),
            size=(PADDLE_W, PADDLE_H),
            emission_nm=ACCEPTOR_NM,
        )

        for particle in self.particles:
            fade = max(particle.life / particle.max_life, 0.0)
            scene.draw(
                "ui",
                "spark",
                at=(particle.x, particle.y),
                size=(2.5 + 3.0 * fade, 2.5 + 3.0 * fade),
                color=(*particle.color, fade),
            )

        if self.winner is None:
            scene.draw(
                "photon",
                "quantum",
                at=(self.ball_x, self.ball_y),
                size=(BALL_SIZE, BALL_SIZE),
                emission_nm=self.ball_nm,
            )

        scene.text(
            f"Donor: {self.player_score}",
            at=(FIELD_W * 0.30, 26.0),
            height=20.0,
            align="center",
            color=(*wavelength_to_srgb(DONOR_NM), 1.0),
        )
        scene.text(
            f"{'Acceptor' if self.vs_computer else 'Optic 2'}: {self.cpu_score}",
            at=(FIELD_W * 0.70, 26.0),
            height=20.0,
            align="center",
            color=(*wavelength_to_srgb(ACCEPTOR_NM), 1.0),
        )
        scene.text(
            f"Transfers: {self.rally}",
            at=(FIELD_W * 0.5, 54.0),
            height=13.0,
            align="center",
            color=(0.44, 0.48, 0.55, 1.0),
        )

        if self.serve_timer > 0.0 and self.winner is None:
            scene.text(
                f"{math.ceil(self.serve_timer)}",
                at=(FIELD_W * 0.5, FIELD_H * 0.5),
                height=60.0,
                align="center",
                color=(0.62, 0.68, 0.78, 1.0),
            )
        if self.paused:
            scene.text(
                "HELD",
                at=(FIELD_W * 0.5, FIELD_H * 0.5),
                height=44.0,
                align="center",
                color=(0.35, 0.85, 0.80, 1.0),
            )
        if self.winner is not None:
            scene.draw("ui", "panel", at=(FIELD_W * 0.5, FIELD_H * 0.5), size=(440.0, 120.0))
            scene.text(
                f"{self.winner} wins",
                at=(FIELD_W * 0.5, FIELD_H * 0.5 - 16.0),
                height=34.0,
                align="center",
                color=(0.35, 0.85, 0.80, 1.0),
            )
            scene.text(
                "Confirm to run again",
                at=(FIELD_W * 0.5, FIELD_H * 0.5 + 26.0),
                height=16.0,
                align="center",
            )

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
