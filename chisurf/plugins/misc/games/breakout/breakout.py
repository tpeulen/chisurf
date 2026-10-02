"""Retained Qt reference view of the shared Breakout simulation."""
from qtpy import QtWidgets
from chisurf.gui import chigame
from chisurf.gui.chigame.input import Action
from chisurf.gui.misc_helpers import persist_plugin_state
from .model import *

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


class BreakoutGame(BreakoutModel, chigame.Game):
    title = "Breakout"
    background = (0.030, 0.034, 0.042, 1.0)
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

    def update(self, dt, keys):
        class Controller:
            def just_pressed(self, action):
                return keys.just_pressed(Action(action))
            def axis(self):
                return keys.axis()
        return super().update(dt, Controller())

    def draw(self, scene) -> None:
        """Queue the frame.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            Frame under construction.
        """
        # Each band is drawn twice: a wide soft halo, then the band itself.
        # A flat fill reads as a printed swatch; the halo is what makes it read
        # as something emitting light.
        for brick in self.bricks:
            if not brick.alive:
                continue
            scene.draw(
                "photon",
                "halo",
                at=(brick.x, brick.y),
                size=(brick.w * 0.62, brick.h * 1.5),
                emission_nm=brick.nm,
                color=None,
            )
        for brick in self.bricks:
            if not brick.alive:
                continue
            scene.draw(
                "band",
                f"{brick.nm:.0f}",
                at=(brick.x, brick.y),
                size=(brick.w, brick.h),
                state="depleted" if brick.hp < brick.max_hp else "idle",
                emission_nm=brick.nm,
            )

        # The paddle is the detector: chrome hardware on a rail, not a bat.
        scene.draw("detector", "apd", at=(self.paddle_x, PADDLE_Y), size=(PADDLE_W, PADDLE_H))
        scene.draw(
            "mount",
            "rail",
            at=(W * 0.5, PADDLE_Y + PADDLE_H * 0.5 + 7.0),
            size=(W, 2.0),
            color=(0.26, 0.29, 0.34, 1.0),
        )

        for particle in self.particles:
            fade = max(particle.life / particle.max_life, 0.0)
            scene.draw(
                "photon",
                "emitted",
                at=(particle.x, particle.y),
                size=(2.5 * fade + 1.0, 2.5 * fade + 1.0),
                emission_nm=particle.nm,
            )

        scene.draw(
            "photon",
            "probe",
            at=(self.ball_x, self.ball_y),
            size=(BALL_SIZE, BALL_SIZE),
            emission_nm=self.ball_nm,
        )

        scene.text(f"Counts: {self.score}", at=(14.0, 20.0), height=17.0)
        scene.text(f"Scan: {self.level}", at=(W * 0.5, 20.0), height=17.0, align="center")
        scene.text("Pulses:", at=(W - 76.0, 20.0), height=17.0, align="right")
        for index in range(self.lives):
            scene.draw(
                "photon",
                "pulse",
                at=(W - 56.0 + index * 20.0, 20.0),
                size=(7.0, 7.0),
                emission_nm=EXCITATION_NM,
            )

        if self.stuck and self.message is None and not self.paused:
            scene.text(
                "Confirm to fire",
                at=(W * 0.5, H * 0.45),
                height=20.0,
                align="center",
                color=(0.62, 0.68, 0.78, 1.0),
            )
        if self.paused:
            scene.text(
                "HELD",
                at=(W * 0.5, H * 0.45),
                height=40.0,
                align="center",
                color=(0.35, 0.85, 0.80, 1.0),
            )
        if self.message is not None:
            scene.draw("ui", "panel", at=(W * 0.5, H * 0.5), size=(420.0, 110.0))
            scene.text(
                self.message,
                at=(W * 0.5, H * 0.5 - 14.0),
                height=30.0,
                align="center",
                color=(0.90, 0.32, 0.30, 1.0),
            )
            scene.text(
                "Confirm for a fresh sample",
                at=(W * 0.5, H * 0.5 + 24.0),
                height=15.0,
                align="center",
            )

        scene.text(
            "Left/Right detector   Confirm fire   Menu hold   Cancel reset   R sound"
            + ("   [muted]" if self.muted else ""),
            at=(W * 0.5, H - 12.0),
            height=13.0,
            align="center",
            color=(0.44, 0.48, 0.55, 1.0),
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
        bar = QtWidgets.QHBoxLayout()
        bar.setContentsMargins(4, 2, 4, 0)
        bar.addWidget(chigame.sound_button(self.host, self))
        bar.addStretch(1)
        layout.addLayout(bar)
        layout.addWidget(canvas)
        self.resize(820, 690)
