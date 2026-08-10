"""The in-world teaching sequence for a first run.

The ``?`` tour is the help modal: a player has to know to press ``?`` before it
teaches anything, and the prologue is story, not instruction. So a new player
was dropped into a 76,000-tile world with nine actions and no idea that
anything starts a fight or that anything opens a menu.

This is the missing piece: a sequence of one-line banners, each naming the next
real thing to do, each completing **because the game state shows it happened**
-- exactly the rule the story beats follow. Nothing here presses anything on
the player's behalf; a step waits for the real press, because someone who
watched a button being pressed has not learned where it is.

Qt-free and engine-free, like the rest of the model: the view draws the banner,
this decides what it says and when it is finished. Progress persists with the
run, so the teaching happens once per player rather than once per session.
"""

from __future__ import annotations

import dataclasses
import math

from .tiles import CLINIC, FLOOR, GATE, TILE


@dataclasses.dataclass(frozen=True)
class Step:
    """One line of teaching, and the condition that retires it.

    Attributes
    ----------
    key : str
        Stable identifier, stored in the save.
    teach : str
        The banner line. ``{talk}``, ``{confirm}``, ``{cancel}`` and ``{menu}``
        are replaced with the keys of the active control scheme, so the text
        stays true when the player rebinds.
    """

    key: str
    teach: str


#: The order a first run actually goes: walk, meet someone, get inside a
#: village, find the recovery station, survive the wilds, take a turn, and
#: answer the page. Each banner points at one real control or one real place.
STEPS: tuple[Step, ...] = (
    Step("walk", "Move with the pad. Hold {confirm} to run."),
    Step("speak", "Someone is always near a gate. Stand close and press {talk} to speak."),
    Step("enter", "A village is entered by its gate -- the gap in the south wall."),
    Step("rest", "The glowing pad inside the gate recovers a spent team. Stand on it."),
    Step("menu", "{menu} opens your pack: map, rig, party, mode, options."),
    Step("fight", "Dark houses are guarded. Walk close and press {talk} to face one."),
    Step("turn", "Emit to strike with your dye's own light. {confirm} chooses."),
    Step("answer", "A beaten guardian is not a read page. Answer what the page asks."),
)


class Tutorial:
    """Tracks how much of the teaching is done.

    Progress is *witnessed*: every frame the tutorial looks at the game and
    retires the current step when the world shows it happened. A step once
    complete stays complete -- a battle that has ended is still a battle the
    player has seen.

    Parameters
    ----------
    done : set of str, optional
        Step keys already completed, from a saved run.
    """

    def __init__(self, done: set[str] | None = None) -> None:
        self.done: set[str] = set(done or ())
        self._last: tuple[float, float] | None = None
        self._walked = 0.0

    @property
    def current(self) -> Step | None:
        """The step the player is on.

        Returns
        -------
        Step or None
            ``None`` once everything is taught.
        """
        for step in STEPS:
            if step.key not in self.done:
                return step
        return None

    @property
    def complete(self) -> bool:
        """Whether the whole sequence is done.

        Returns
        -------
        bool
            True when no banner needs drawing ever again.
        """
        return self.current is None

    def finish(self) -> None:
        """Retire every step at once.

        A run that has already cleared rooms does not need teaching, and a
        save from before the tutorial existed must not replay it.
        """
        self.done = {step.key for step in STEPS}

    def observe(self, game) -> None:
        """Advance from whatever the game shows.

        Parameters
        ----------
        game : object
            Anything with the overworld's state surface: ``iris``, ``world``,
            ``speaking``, ``resting``, ``battle``, ``verdict``.
        """
        step = self.current
        if step is None:
            return

        here = (float(game.iris[0]), float(game.iris[1]))
        if self._last is not None:
            self._walked += math.hypot(here[0] - self._last[0], here[1] - self._last[1])
        self._last = here

        if self._witnessed(step, game, here):
            self.done.add(step.key)

    def _witnessed(self, step: Step, game, here: tuple[float, float]) -> bool:
        """Whether the game shows what a step asks for.

        Parameters
        ----------
        step : Step
            The step to test.
        game : object
            The overworld's state surface.
        here : tuple of float
            Where Iris stands, in world units.

        Returns
        -------
        bool
            True when the step is done.
        """
        if step.key == "walk":
            return self._walked > TILE * 4.0
        if step.key == "speak":
            return game.speaking is not None
        if step.key == "enter":
            tile = game.world.tile_at(int(here[0] // TILE), int(here[1] // TILE))
            return tile in (GATE, FLOOR, CLINIC)
        if step.key == "rest":
            return bool(game.resting)
        if step.key == "menu":
            return bool(game.menu_open)
        if step.key == "fight":
            return game.battle is not None
        if step.key == "turn":
            return game.battle is not None and len(game.battle.log) > 0
        if step.key == "answer":
            return game.verdict is not None
        return False
