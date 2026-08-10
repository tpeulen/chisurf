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
        "Somewhere out in the grass is a hound made of the same light, and it "
        "does not spend what it carries. It can smell where light has been. "
        "Find it, and it will find the rest.",
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


#: Which lands each order calls its own. Doctrine work (Act Two) is counted
#: against these, and each order's emissary stands in the first of them.
ORDER_LANDS: dict[str, tuple[str, ...]] = {
    "rigour": ("reference", "manual", "development"),
    "clarity": ("guides", "fundamentals", "getting_started"),
    "discovery": ("references", "concepts"),
}

#: Rooms to clear for your order after pledging. Small on purpose: a run must
#: be finishable in a humane number of sessions, and the corpus is the real
#: unbounded task this arc exists to break into wins.
WORK_GOAL = 3

#: The waking act. A run does not start mid-stride with a companion already at
#: heel — you come to in the wild with someone standing over you, and the hound
#: is out there to be found. A journey earns its company.
ACT_ZERO: list[Beat] = [
    Beat(
        key="wake",
        headline="Wake. Someone is standing over you.",
        body=(
            "Grass, sky, and a stranger's voice. You were sent here as a "
            "probe, and probes arrive the way light does — suddenly, and "
            "without luggage. The keeper crouched beside you has been waiting."
        ),
        goal="Hear the keeper out.",
    ),
    Beat(
        key="the-hound",
        headline="Something glows faintly in the grass.",
        body=(
            "A hound of light, run down to an ember, curled where the road "
            "bends. It does not spend what it carries, so if it is dim, it has "
            "been alone in the dark a long time. It lifts its head as you come "
            "near."
        ),
        goal="Find the dim hound and speak to it.",
    ),
]

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
        goal="Find an emissary and pledge to an order.",
    ),
]

#: The doctrine act. Pledging is a promise; this is the keeping of it. The
#: work counts *cleared rooms in your order's own lands*, mode-independent, so
#: training and expert runs both have an arc to finish.
ACT_TWO: list[Beat] = [
    Beat(
        key="the-work",
        headline="Your order has work for you.",
        body=(
            "A pledge is words until ground changes hands. Your order's lands "
            "hold rooms nobody has faced; clear them, and the doctrine you "
            "chose stops being an opinion."
        ),
        goal=f"Clear {WORK_GOAL} rooms in your order's lands.",
    ),
    Beat(
        key="the-dawn",
        headline="The dark has given ground. Come see.",
        body=(
            "Not everywhere, and not for good. But where you worked, the lamps "
            "hold — and a land that has watched light leave for years has "
            "watched it come back."
        ),
        goal="Witness the dawn.",
    ),
]

#: Every beat, in the order a run walks them.
BEATS: list[Beat] = [*ACT_ZERO, *ACT_ONE, *ACT_TWO]

#: The closing cards, one set per doctrine, shown when the work is done.
EPILOGUES: dict[str, tuple[tuple[str, str], ...]] = {
    "rigour": (
        ("The Dawn", "The lamps you lit do not flicker. Every one of them "
         "stands over ground that was checked before it was trusted, and "
         "Merel walks the shelves without a taper for the first time in years."),
        ("The Dawn", "Rigour does not celebrate. But tonight the order's "
         "ledger closes with more light than it opened with, and that has not "
         "been written in a long while."),
    ),
    "clarity": (
        ("The Dawn", "Doors stand open along the Pilgrim Road. A stranger "
         "arriving tonight would find the way in five minutes -- which is, "
         "Halden says, the only measure that was ever worth taking."),
        ("The Dawn", "The light was there all along. What you built were "
         "doors, and the Fading walks past a door it cannot close."),
    ),
    "discovery": (
        ("The Dawn", "The map has fewer blank places. Sable stands at a cairn "
         "that now points somewhere, in ground that was never dark -- only "
         "unwritten, which is the dark nobody counts."),
        ("The Dawn", "What you found was always there. Now it is *findable*, "
         "and that is the difference between a world and a rumour of one."),
    ),
}


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
        #: The hound is found in the world, not issued at the door. A journey
        #: earns its company.
        self.has_lumi = False
        #: Cleared-rooms-in-doctrine-lands at the moment of pledging, so the
        #: work beat counts what was done *for* the order, not before it.
        self.pledge_baseline: int | None = None
        #: The same count, now — fed by the game each frame (clears live in
        #: the run, not in the world).
        self.doctrine_count = 0

    @property
    def current(self) -> Beat | None:
        """The beat the player is on.

        Returns
        -------
        Beat or None
            ``None`` once the arc is walked to its end.
        """
        for beat in BEATS:
            if not self.is_complete(beat):
                return beat
        return None

    @property
    def work_progress(self) -> tuple[int, int] | None:
        """How far the doctrine work has come.

        Returns
        -------
        tuple of int or None
            ``(done, goal)`` while on the work beat; ``None`` before a pledge.
        """
        if self.chosen_order is None:
            return None
        done = max(0, self.doctrine_count - (self.pledge_baseline or 0))
        return (min(done, WORK_GOAL), WORK_GOAL)

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
        if beat.key == "wake":
            return "wake" in self.seen
        if beat.key == "the-hound":
            return self.has_lumi
        if beat.key == "arrival":
            return "arrival" in self.seen
        if beat.key == "first-light":
            return self.world.counts()[SETTLED] > 0 and "first-light" in self.seen
        if beat.key == "the-frontier":
            return self.world.counts()[SCOUTED] > 0 and "the-frontier" in self.seen
        if beat.key == "the-choice":
            return self.chosen_order is not None
        if beat.key == "the-work":
            progress = self.work_progress
            return progress is not None and progress[0] >= progress[1]
        if beat.key == "the-dawn":
            return "dawn" in self.seen
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

    def choose(self, order: str, baseline: int | None = None) -> None:
        """Commit to an order.

        Parameters
        ----------
        order : str
            One of the keys of :data:`ORDERS`.
        baseline : int, optional
            Cleared-rooms-in-doctrine-lands at this moment, so the work beat
            starts from zero. Omitted keeps whatever baseline is already set
            (a restored run passes the saved one separately).

        Raises
        ------
        KeyError
            If the order is not one of the three.
        """
        if order not in ORDERS:
            raise KeyError(f"unknown order: {order!r}")
        self.chosen_order = order
        if baseline is not None:
            self.pledge_baseline = baseline

    @property
    def order(self) -> dict[str, str] | None:
        """The chosen order's description.

        Returns
        -------
        dict or None
            ``None`` before a choice is made.
        """
        return ORDERS[self.chosen_order] if self.chosen_order else None


def cleared_in_lands(cleared, order: str | None) -> int:
    """Count cleared rooms lying in an order's own lands.

    Parameters
    ----------
    cleared : iterable of str
        Repository-relative page addresses, e.g. ``docs/guides/11_burst.md``.
    order : str or None
        An :data:`ORDERS` key.

    Returns
    -------
    int
        How many cleared addresses fall inside :data:`ORDER_LANDS` for the
        order. Zero for no order.
    """
    lands = ORDER_LANDS.get(order or "", ())
    count = 0
    for address in cleared:
        parts = address.split("/")
        if len(parts) >= 2 and parts[1] in lands:
            count += 1
    return count
