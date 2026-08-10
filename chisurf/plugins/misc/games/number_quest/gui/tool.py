"""Number Quest, on the chigame engine.

The rules were already Qt-free in :mod:`..core.game`, so this is a *view* port:
the same :class:`NumberQuestGame` decides everything and none of its logic moves.

The theme is not decoration. Guessing a hidden number by narrowing an interval
*is* what fitting a parameter does, so the hidden value is read as a
fluorescence lifetime -- the core's 1..100 becomes 0.1..10.0 ns -- and the
player's current estimate is drawn as the decay it implies. "Higher" and
"Lower" become "longer" and "shorter", which is the same information in the
language of the measurement.

Number Quest is the engine's menu-and-readout test, and it has to work with no
text entry at all: the estimate is dialled with the pad rather than typed.
"""

from __future__ import annotations

import math

from qtpy import QtWidgets

from chisurf.gui import chigame
from chisurf.gui.chigame.input import Action

from ..core.game import GuessStatus, NumberQuestGame

try:
    from chisurf.gui.misc_helpers import persist_plugin_state
except ImportError:  # pragma: no cover - stand-alone use

    def persist_plugin_state(name):
        """Return an identity decorator when the host is unavailable."""
        return lambda cls: cls


#: The core counts 1..100; the instrument reads 0.1..10.0 ns.
NS_PER_UNIT = 0.1

#: The excitation line the simulated decay is driven at.
PROBE_NM = 488.0

#: Panel geometry in world units.
VIEW_W = 420.0
VIEW_H = 340.0
PLOT_X = 40.0
PLOT_Y = 96.0
PLOT_W = 340.0
PLOT_H = 120.0

#: Samples across the plotted decay. Enough to read as a curve, few enough that
#: the whole frame is still one draw call's worth of quads.
CURVE_POINTS = 70

#: Held-direction auto-repeat, so dialling across the range is not 100 presses.
REPEAT_DELAY = 0.28
REPEAT_RATE = 0.045

BINDINGS = {
    "ArrowLeft": Action.LEFT,
    "ArrowRight": Action.RIGHT,
    "a": Action.LEFT,
    "d": Action.RIGHT,
    "Enter": Action.CONFIRM,
    " ": Action.CONFIRM,
    "r": Action.CANCEL,
    "q": Action.SHOULDER_L,
    "e": Action.SHOULDER_R,
}


class NumberQuestChiGame(chigame.Game):
    """Renders and drives a :class:`NumberQuestGame` with no text entry."""

    title = "Number Quest"
    background = (0.030, 0.034, 0.042, 1.0)
    music_context = "town"

    def setup(self, host) -> None:
        """Bind the controller and start a round.

        Parameters
        ----------
        host : chisurf.gui.chigame.game.GameHost
            The host running this game.
        """
        self.host = host
        host.keys.bindings = dict(BINDINGS)
        host.camera.center[:] = (VIEW_W * 0.5, VIEW_H * 0.5)
        host.camera.height = VIEW_H
        self.game = NumberQuestGame()
        self.estimate = 50
        self.message = "Dial an estimate, then confirm."
        self.history: list[int] = []
        self._repeat: dict[Action, float] = {}

    def new_round(self) -> None:
        """Start a fresh round and clear the trace history."""
        self.game.reset()
        self.estimate = 50
        self.history = []
        self.message = "Dial an estimate, then confirm."

    @property
    def tau(self) -> float:
        """Current estimate as a lifetime.

        Returns
        -------
        float
            Lifetime in nanoseconds.
        """
        return self.estimate * NS_PER_UNIT

    def update(self, dt: float, keys) -> None:
        """Advance one frame.

        Parameters
        ----------
        dt : float
            Seconds elapsed.
        keys : chisurf.gui.chigame.input.InputMap
            Controller state.
        """
        if keys.just_pressed(Action.CANCEL):
            self.new_round()
            return

        for action, step in (
            (Action.LEFT, -1),
            (Action.RIGHT, 1),
            (Action.SHOULDER_L, -10),
            (Action.SHOULDER_R, 10),
        ):
            if keys.just_pressed(action):
                self._nudge(step)
                self._repeat[action] = -REPEAT_DELAY
            elif keys.is_held(action):
                self._repeat[action] = self._repeat.get(action, 0.0) + dt
                while self._repeat[action] >= REPEAT_RATE:
                    self._repeat[action] -= REPEAT_RATE
                    self._nudge(step)
            else:
                self._repeat.pop(action, None)

        if keys.just_pressed(Action.CONFIRM):
            self.submit()

    def _nudge(self, step: int) -> None:
        """Move the estimate, clamped to the instrument's range.

        Parameters
        ----------
        step : int
            Change in core units.
        """
        self.estimate = min(max(self.estimate + step, self.game.minimum), self.game.maximum)

    def submit(self) -> None:
        """Submit the current estimate to the rules."""
        if self.game.status is not GuessStatus.ACTIVE:
            self.new_round()
            return
        self.history.append(self.estimate)
        result = self.game.guess(self.estimate)
        # The rules speak in higher/lower; the instrument speaks in lifetimes.
        self.message = (
            result.message.replace("Higher!", "Longer lifetime.")
            .replace("Lower!", "Shorter lifetime.")
            .replace("Try again.", "")
            .strip()
        )
        self.host.audio.sfx(
            "guess", 880.0 if self.game.status is GuessStatus.WON else 520.0
        )

    def _decay_point(self, index: int, tau: float) -> tuple[float, float]:
        """A point on the decay implied by a lifetime.

        Parameters
        ----------
        index : int
            Sample index across the plot.
        tau : float
            Lifetime in nanoseconds.

        Returns
        -------
        tuple of float
            Position in world units.
        """
        span_ns = self.game.maximum * NS_PER_UNIT
        t = span_ns * index / (CURVE_POINTS - 1)
        intensity = math.exp(-t / max(tau, 1e-3))
        return (
            PLOT_X + PLOT_W * index / (CURVE_POINTS - 1),
            PLOT_Y + PLOT_H * (1.0 - intensity),
        )

    def draw(self, scene) -> None:
        """Queue the frame.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            Frame under construction.
        """
        scene.text("LIFETIME ESTIMATION", at=(VIEW_W * 0.5, 30.0), height=15.0,
                   align="center", color=(0.78, 0.82, 0.88, 1.0))
        scene.text(f"Turns left: {self.game.attempts_remaining}    Score: {self.game.score}",
                   at=(VIEW_W * 0.5, 52.0), height=11.0, align="center",
                   color=(0.44, 0.48, 0.55, 1.0))

        # Plot frame: two rules rather than a box, as an instrument would draw.
        scene.draw("mount", "axis-y", at=(PLOT_X, PLOT_Y + PLOT_H * 0.5),
                   size=(1.5, PLOT_H), color=(0.30, 0.33, 0.38, 1.0))
        scene.draw("mount", "axis-x", at=(PLOT_X + PLOT_W * 0.5, PLOT_Y + PLOT_H),
                   size=(PLOT_W, 1.5), color=(0.30, 0.33, 0.38, 1.0))

        # Previous estimates stay on screen, faintly: the trace of the search is
        # the interesting part, and it is what makes narrowing an interval feel
        # like converging rather than like a sequence of unrelated tries.
        for past in self.history[:-1]:
            for index in range(CURVE_POINTS):
                at = self._decay_point(index, past * NS_PER_UNIT)
                scene.draw("ui", "trace", at=at, size=(1.6, 1.6),
                           color=(0.30, 0.34, 0.40, 1.0))

        for index in range(CURVE_POINTS):
            at = self._decay_point(index, self.tau)
            scene.draw("photon", "curve", at=at, size=(2.6, 2.6), emission_nm=PROBE_NM)

        scene.text(f"{self.tau:.1f} ns", at=(VIEW_W * 0.5, PLOT_Y + PLOT_H + 26.0),
                   height=26.0, align="center", color=(0.35, 0.85, 0.80, 1.0))

        if self.message:
            scene.text(self.message, at=(VIEW_W * 0.5, PLOT_Y + PLOT_H + 56.0),
                       height=12.0, align="center", color=(0.78, 0.82, 0.88, 1.0))

        scene.text("Left/Right  dial      L/R  coarse",
                   at=(VIEW_W * 0.5, VIEW_H - 34.0), height=11.0, align="center",
                   color=(0.44, 0.48, 0.55, 1.0))
        scene.text("Confirm  submit      Cancel  new round",
                   at=(VIEW_W * 0.5, VIEW_H - 16.0), height=11.0, align="center",
                   color=(0.44, 0.48, 0.55, 1.0))


@persist_plugin_state("number_quest")
class NumberQuestWidget(QtWidgets.QWidget):
    """Dockable container hosting the game.

    Parameters
    ----------
    parent : QWidget, optional
        Parent widget.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Number Quest")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.game = NumberQuestChiGame()
        canvas, self.host = chigame.create_widget(self.game, parent=self)
        layout.addWidget(canvas)
        self.resize(560, 420)
