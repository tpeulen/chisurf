"""The story spine, and how it reads the world.

Until now the answer to "where is the story?" was "phase six", which is not an
answer -- a world with no reason to walk it is a map. This is the authored
spine: three orders who disagree about what knowledge is *for*, and a sequence
of beats whose progress is measured against the real corpus rather than against
a flag the game sets for itself.

Two rules keep it honest:

* **A beat completes because the documentation changed**, not because the player
  pressed something. Every beat's condition is a query over the world -- pages
  settled, a land's villages tended, the unlinked found. You cannot advance the
  story without improving the docs, which is the whole point.
* **The spine is data.** It is a list of beats here, and the per-page prose is
  generated later against a page's own content. Nothing about the arc is
  computed at run time, so it can be read, reviewed and argued with.

The three orders are the doctrines a player eventually chooses between; the
opening act is shared, because a choice offered before the world means anything
is a menu, not a decision.
"""

from __future__ import annotations

import dataclasses

from .world import SCOUTED, SETTLED, World

#: The three orders, and what each believes documentation is for.
ORDERS: dict[str, dict[str, str]] = {
    "rigour": {
        "name": "The Order of Rigour",
        "creed": "A claim without its derivation is a rumour.",
        "wants": "every derivation checked, every symbol defined, every source cited",
        "critical": "an unstated assumption, a wrong unit, a missing citation",
    },
    "clarity": {
        "name": "The Order of Clarity",
        "creed": "Knowledge nobody can reach is knowledge nobody has.",
        "wants": "a newcomer at the door and through it in five minutes",
        "critical": "a term used before it is defined, a jump nobody explains",
    },
    "discovery": {
        "name": "The Order of Discovery",
        "creed": "What is unwritten is not therefore unimportant.",
        "wants": "the gaps found, the unlinked mapped, the silence named",
        "critical": "an orphan, a dead link, a hole in the tree",
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


#: The opening act, shared by all three orders. It is deliberately short: the
#: player is choosing a doctrine at the end of it, and that choice is only
#: meaningful once they have seen what the world is actually like.
ACT_ONE: list[Beat] = [
    Beat(
        key="arrival",
        headline="Lumi is dimming. Find someone who is still keeping records.",
        body=(
            "You are Iris, a probe photon, and you were sent in to look at "
            "something. Whatever it was, the record of it is gone. Lumi -- the "
            "small light that came with you -- is running down, and the lands "
            "that once held the knowledge have gone dark in patches."
        ),
        goal="Reach a village whose buildings are still lit.",
    ),
    Beat(
        key="first-light",
        headline="Settled ground still exists. Learn what keeps it lit.",
        body=(
            "A settled page is one a person has read and vouched for. There are "
            "far fewer than there should be, and the difference between a lit "
            "building and a dark one is simply whether anyone came."
        ),
        goal="Stand in a village where at least one building is settled.",
    ),
    Beat(
        key="the-frontier",
        headline="Something has been through here ahead of you.",
        body=(
            "Some buildings are half-lit: scouted, not settled. An agent walked "
            "this ground and wrote down what it saw, but no person has confirmed "
            "any of it. That band of half-light is the frontier, and it is where "
            "the three orders stop agreeing with each other."
        ),
        goal="Find scouted ground -- a building lit but unconfirmed.",
    ),
    Beat(
        key="the-choice",
        headline="Three orders will each tell you what to do about it.",
        body=(
            "Rigour wants the derivations checked. Clarity wants the door made "
            "wide enough to walk through. Discovery wants the unwritten found. "
            "They cannot all be served first, and whichever you serve changes "
            "what counts as a victory."
        ),
        goal="Choose an order.",
    ),
]


class Story:
    """Tracks which beat the world is on.

    Progress is *derived*: the story asks the world what state it is in rather
    than being told by the game. That means a beat cannot be advanced by
    fiddling with the UI, only by the corpus actually changing -- and that a
    saved game does not need to store how far along the arc it is.

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
        """Record that the player has seen something a beat asks for.

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
