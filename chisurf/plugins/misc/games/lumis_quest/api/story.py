"""The story: the Fading, the three orders, and why any of it is worth walking.

The premise is one idea taken seriously. **Everything alive in this world
carries light.** A person, a hound, a thing in the long grass — each holds a
quantum of it, absorbs it, and gives it back changed. That is not a metaphor
laid over the mechanics; it *is* the mechanics. A creature's brightness is how
hard it can strike. Emitting spends it. A creature driven dark can be carried
home.

And knowledge is the same substance. A page somebody has read and vouched for
is **lit**, and its keeper stands outside it. A page nobody has opened is dark,
and something has moved into it. That is why the map looks the way it does.

**The Fading** is the premise's consequence: light is leaving. Not dramatically —
a lamp at a time, a page at a time, until a whole land is dark and nobody
remembers it was ever otherwise. You are **Iris**, a probe: a photon given a
body and sent in to find where it is going. **Lumi** is a hound of light, who
can smell where light has been.

Two rules keep the arc honest, and they are the same two as before:

* **A beat completes because the documentation changed**, not because the player
  pressed something. Every condition is a query over the world.
* **The spine is data**, so it can be read, reviewed and argued with.
"""

from __future__ import annotations

import dataclasses

from .world import SCOUTED, SETTLED, World

#: The opening. Shown once, on a fresh run, before the world appears -- so a
#: player arrives knowing what they are looking at rather than deducing it.
PROLOGUE: tuple[tuple[str, str], ...] = (
    (
        "The Fading",
        "Everything alive here carries light. A person, a hound, a thing in the "
        "long grass — each holds a little, spends it, and gives back what is "
        "left, changed.",
    ),
    (
        "The Fading",
        "Knowledge is the same substance. A page somebody has read and vouched "
        "for burns steadily, and its keeper stands at the door. A page nobody "
        "has opened goes dark, and something moves into the dark.",
    ),
    (
        "The Fading",
        "Lately the light has been leaving. Not all at once — a lamp at a time, "
        "a page at a time, until a whole land has gone quiet and no one recalls "
        "it was ever otherwise.",
    ),
    (
        "Iris",
        "You are a probe: a single quantum given a body and sent in to find "
        "where it is going. You will be spent doing it. That is what a probe "
        "is for.",
    ),
    (
        "Lumi",
        "The hound at your heel is made of the same light, and does not spend "
        "it. Lumi can smell where light has been — which is how you will find "
        "the places it has left.",
    ),
)

#: The three orders. They agree the light is going and disagree entirely about
#: what to do, which is what makes choosing one a decision rather than a menu.
ORDERS: dict[str, dict[str, str]] = {
    "rigour": {
        "name": "The Order of Rigour",
        "creed": "Light that misleads is worse than dark.",
        "wants": "every derivation checked, every symbol defined, every source named",
        "critical": "an unstated assumption, a wrong unit, a claim with nothing behind it",
        "belief": (
            "They hold that a page lit wrongly is a lamp hung over a pit. Better "
            "an honest dark than a light that walks people off the edge."
        ),
    },
    "clarity": {
        "name": "The Order of Clarity",
        "creed": "Light nobody can reach is light nobody has.",
        "wants": "a stranger at the door and through it in five minutes",
        "critical": "a term used before it is defined, a step nobody explains",
        "belief": (
            "They hold that the Fading is not a loss of light but a loss of "
            "doors. The knowledge is still burning; it is only that nobody can "
            "get to it any more."
        ),
    },
    "discovery": {
        "name": "The Order of Discovery",
        "creed": "What is unwritten is not therefore unimportant.",
        "wants": "the gaps found, the unlinked mapped, the silence named",
        "critical": "an orphan, a dead link, a hole in the tree",
        "belief": (
            "They hold that the worst dark was never lit at all — and that "
            "counting the lamps you already have is how a world quietly agrees "
            "to stop looking."
        ),
    },
}


@dataclasses.dataclass(frozen=True)
class Beat:
    """One step of the arc.

    Attributes
    ----------
    key : str
        Stable identifier.
    headline : str
        One line, shown in the world.
    body : str
        What is happening and why it matters.
    goal : str
        What the player has to do, in plain words.
    """

    key: str
    headline: str
    body: str
    goal: str


#: The opening act, shared by all three orders. Short on purpose: the player
#: chooses a doctrine at the end of it, and that choice only means something
#: once they have seen what the world is actually like.
ACT_ONE: list[Beat] = [
    Beat(
        key="arrival",
        headline="Lumi is dimming. Find ground that is still lit.",
        body=(
            "You arrive somewhere that was recently brighter. Lumi is running "
            "down faster than a hound of light should, which means the Fading "
            "is not distant history here — it is happening around you."
        ),
        goal="Reach a village whose buildings are still burning.",
    ),
    Beat(
        key="first-light",
        headline="Lit ground still exists. Learn what keeps it burning.",
        body=(
            "A lit page is one a person read and vouched for, and its keeper is "
            "standing at the door. There are far fewer keepers than doors. The "
            "difference between a lamp and a dark house is only ever whether "
            "somebody came."
        ),
        goal="Stand in a village where at least one house is lit.",
    ),
    Beat(
        key="the-frontier",
        headline="Something walked this ground ahead of you.",
        body=(
            "Some houses are half-lit — a cold, borrowed glow with nobody at the "
            "door. Something passed through, read what was there and wrote down "
            "what it saw, and no person has confirmed a word of it. That band of "
            "half-light is the frontier, and it is where the three orders stop "
            "agreeing with one another."
        ),
        goal="Find half-lit ground — a house burning with nobody keeping it.",
    ),
    Beat(
        key="the-choice",
        headline="Three orders will each tell you what the Fading is.",
        body=(
            "Rigour says the light is going because too much of it lies. "
            "Clarity says the light is fine and the doors have closed. "
            "Discovery says the worst dark was never lit at all. They cannot all "
            "be served first, and whichever you serve decides what counts as "
            "having won."
        ),
        goal="Choose an order.",
    ),
]


class Story:
    """Tracks which beat the world is on.

    Progress is *derived*: the story asks the world what state it is in rather
    than being told by the game. A beat cannot be advanced by fiddling with the
    interface, only by the corpus actually changing — and a saved game does not
    need to record how far along the arc it is.

    Parameters
    ----------
    world : chisurf.plugins.misc.games.lumis_quest.api.world.World
        The world to read.
    """

    def __init__(self, world: World) -> None:
        self.world = world
        self.chosen_order: str | None = None
        self.seen: set[str] = set()

    @property
    def current(self) -> Beat | None:
        """The beat the player is on.

        Returns
        -------
        Beat or None
            ``None`` once the opening act is complete and an order is chosen.
        """
        for beat in ACT_ONE:
            if not self.is_complete(beat):
                return beat
        return None

    def is_complete(self, beat: Beat) -> bool:
        """Whether a beat's condition is satisfied by the world.

        Parameters
        ----------
        beat : Beat
            The beat to test.

        Returns
        -------
        bool
            True when the world already shows what the beat asks for.
        """
        if beat.key == "arrival":
            return "arrival" in self.seen
        if beat.key == "first-light":
            return self.world.counts()[SETTLED] > 0 and "first-light" in self.seen
        if beat.key == "the-frontier":
            return self.world.counts()[SCOUTED] > 0 and "the-frontier" in self.seen
        if beat.key == "the-choice":
            return self.chosen_order is not None
        return False

    def witness(self, key: str) -> None:
        """Record that the player has seen what a beat asks for.

        Parameters
        ----------
        key : str
            The beat key that was satisfied.
        """
        self.seen.add(key)

    def observe(self, room) -> None:
        """Update the arc from wherever Iris is standing.

        Parameters
        ----------
        room : Room or None
            The nearest room, or ``None``.
        """
        self.witness("arrival")
        if room is None:
            return
        if room.state == SETTLED:
            self.witness("first-light")
        elif room.state == SCOUTED:
            self.witness("the-frontier")

    def choose(self, order: str) -> None:
        """Commit to an order.

        Parameters
        ----------
        order : str
            One of the keys of :data:`ORDERS`.

        Raises
        ------
        KeyError
            If the order is not one of the three.
        """
        if order not in ORDERS:
            raise KeyError(f"unknown order: {order!r}")
        self.chosen_order = order

    @property
    def order(self) -> dict[str, str] | None:
        """The chosen order's description.

        Returns
        -------
        dict or None
            ``None`` before a choice is made.
        """
        return ORDERS[self.chosen_order] if self.chosen_order else None
