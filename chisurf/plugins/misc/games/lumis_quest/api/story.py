"""The story: the Fading, the Marking, and the woman who thought she was helping.

The premise is one idea taken seriously. **Everything alive in this world
carries light.** A person, a hound, a thing in the long grass -- each holds a
quantum of it, absorbs it, and gives it back changed. That is not a metaphor
laid over the mechanics; it *is* the mechanics. Brightness is how hard a thing
can strike. Emitting spends it. Whatever is driven all the way down goes out.

And knowledge is the same substance. A page somebody has read and vouched for is
**lit**, and its keeper stands outside it. A page nobody has opened is dark, and
something has moved into the dark. That is why the map looks the way it does.

**The Fading** is the premise's consequence: light is leaving. Not dramatically
-- a lamp at a time, a page at a time, until a whole land is dark and nobody
remembers it was ever otherwise.

**The Marking** is somebody's answer to it. Vesper, once the finest keeper
anyone had, worked out how to *fix* light into a living body so that it could
not leave. She began with a moth. She has not stopped. Every marked animal in
the world is a lamp she lit and walked away from, and a lamp burns until it does
not: driven all the way down, a marked animal does not die -- it **crosses**,
into the dark manifold, where it is still there and no longer anything. That
country is filling up.

You are **Iris**, a probe: a photon given a body and sent in to find where the
light is going. **Lumi** is a hound of light who does not spend what he carries
-- the last of a line nobody ever marked.

Three rules keep the arc honest:

* **Every beat completes on the world, not on a keypress.** Some conditions are
  queries over the documentation (a lit page exists; you have cleared three
  rooms in your order's lands) and some are queries over the run (you hold three
  seals; you have unbound a label). None of them is a cutscene flag the
  interface can set on its own.
* **The spine is data**, so it can be read, reviewed and argued with.
* **Nobody in it is stupid.** Vesper is wrong, and her argument is a good one.
"""

from __future__ import annotations

import dataclasses

from . import engine
from .world import SCOUTED, SETTLED, World

#: Everything the arc says, read from ``data/story.json``. Nothing narrative
#: lives in this module any more: a writer changes the story by editing JSON,
#: and the only thing Python still owns is what a beat *means*.
_DATA: dict = engine.load("story")

#: The opening. Shown once, on a fresh run, before the world appears -- so a
#: player arrives knowing what they are looking at rather than deducing it.
PROLOGUE: tuple[tuple[str, str], ...] = tuple(
    (card[0], card[1]) for card in _DATA.get("prologue", ())
)

#: The three orders. They agree the Marking is happening and disagree entirely
#: about what it means, which is what makes choosing one a decision rather than
#: a menu row.
ORDERS: dict[str, dict[str, str]] = _DATA.get("orders", {})

#: Which lands each order calls its own. Doctrine work is counted against
#: these, and each order's emissary stands in the first of them.
ORDER_LANDS: dict[str, tuple[str, ...]] = {
    key: tuple(value) for key, value in _DATA.get("order_lands", {}).items()
}

#: Rooms to clear for your order after pledging, and seals to hold before an
#: order will take you seriously. Small on purpose: a run must be finishable in
#: a humane number of sessions.
WORK_GOAL: int = int(_DATA.get("goals", {}).get("work", 3))
SEAL_GOAL: int = int(_DATA.get("goals", {}).get("seals", 3))

#: What Vesper says when you reach her, and what Iris says back -- one reply
#: per doctrine, because the reply *is* the doctrine's whole argument.
ANTAGONIST_LINES: tuple[str, ...] = tuple(_DATA.get("lanternwright", ()))
REPLIES: dict[str, str] = _DATA.get("replies", {})

#: The closing cards, one set per doctrine, shown when the work is done.
EPILOGUES: dict[str, tuple[tuple[str, str], ...]] = {
    key: tuple((card[0], card[1]) for card in cards)
    for key, cards in _DATA.get("epilogues", {}).items()
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
    when : dict
        The condition that completes it, as an :mod:`.engine` expression. This
        is the whole reason the arc is data: a beat completes because the run
        or the corpus satisfies a written-down rule, not because a branch in a
        method said so.
    """

    key: str
    headline: str
    body: str
    goal: str
    when: dict = dataclasses.field(default_factory=dict)


#: Every beat, in the order a run walks them.
BEATS: list[Beat] = [
    Beat(
        key=entry["key"],
        headline=entry["headline"],
        body=entry["body"],
        goal=entry["goal"],
        when=entry.get("when", {}),
    )
    for entry in _DATA.get("beats", ())
]


class Story:
    """Tracks which beat the world is on.

    Progress is *derived*: the story asks the world and the run what state they
    are in rather than being told by the interface. A beat cannot be advanced by
    fiddling with the UI, only by the corpus or the run actually changing.

    Parameters
    ----------
    world : chisurf.plugins.misc.games.lumis_quest.api.world.World
        The world to read.
    """

    def __init__(self, world: World) -> None:
        self.world = world
        #: The run, as the scripts see it. Set by
        #: :class:`..context.GameContext` when it is built around this story,
        #: because a beat's condition is evaluated against the *whole* run --
        #: the corpus, the seals and the team -- not against the arc alone.
        self.context = None
        self.chosen_order: str | None = None
        self.seen: set[str] = set()
        #: The hound is found in the world, not issued at the door. A journey
        #: earns its company.
        self.has_companion = False
        #: Warden seals held, which is also the licence tier (see :mod:`.tiers`).
        self.seals: set[str] = set()
        #: How many labels have been taken off marked animals.
        self.unbound = 0
        #: Cleared-rooms-in-doctrine-lands at the moment of pledging, so the
        #: work beat counts what was done *for* the order, not before it.
        self.pledge_baseline: int | None = None
        #: The same count, now -- fed by the game each frame (clears live in
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
    def act(self) -> tuple[int, int]:
        """How far through the arc the run has come.

        Returns
        -------
        tuple of int
            ``(beats done, beats in all)``.
        """
        done = sum(1 for beat in BEATS if self.is_complete(beat))
        return (done, len(BEATS))

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

    @property
    def seal_progress(self) -> tuple[int, int]:
        """How far up the ladder the run has come.

        Returns
        -------
        tuple of int
            ``(held, goal)``.
        """
        return (min(len(self.seals), SEAL_GOAL), SEAL_GOAL)

    def is_complete(self, beat: Beat, context=None) -> bool:
        """Whether a beat's condition is satisfied.

        The condition is the one written in ``data/story.json`` and evaluated
        by :func:`..engine.evaluate`. There is deliberately no branch on
        ``beat.key`` here: a beat that needed one would be a beat the data
        cannot express, and that is the bug to fix rather than to work around.

        Parameters
        ----------
        beat : Beat
            The beat to test.
        context : Context, optional
            The run to ask. Defaults to :attr:`context`.

        Returns
        -------
        bool
            True when the world or the run already shows what the beat asks
            for. False when there is no context to ask at all -- an arc with
            nothing behind it has not begun.
        """
        run = context if context is not None else self.context
        if run is None:
            return False
        return engine.evaluate(beat.when, run)

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
        if room is None:
            return
        if room.state == SETTLED:
            self.witness("first-light")
        elif room.state == SCOUTED:
            self.witness("the-frontier")

    def seal(self, key: str) -> None:
        """Record a Warden beaten.

        Parameters
        ----------
        key : str
            The Warden's key.
        """
        self.seals.add(key)

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

    @property
    def reply(self) -> str:
        """What Iris says to the Lanternwright, in your doctrine's words.

        Returns
        -------
        str
            A neutral answer before any pledge.
        """
        return REPLIES.get(self.chosen_order or "none", "")


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
