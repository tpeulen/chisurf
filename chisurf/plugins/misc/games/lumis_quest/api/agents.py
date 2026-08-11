"""The people go about their day, meet each other, and talk about you.

A town whose inhabitants orbit a fixed home point is scenery. This gives each
of them an **inner state** -- drives that rise on their own, a goal chosen from
whichever drive is loudest, a route to somewhere real, and a memory of what they
have done and heard. Two of them who end up in the same place **start a
conversation**, and the player can walk up and drop into it.

The split that makes this affordable, and testable:

* **The loop is deterministic and offline.** Drives, goals, walking, meeting and
  parting are ordinary code stepped every frame. Nothing here waits on anything.
* **Only the *words* are ever model-written.** A conversation's topic is picked
  from the world (what the corpus looks like, how far the arc has come); the
  lines come from :mod:`.personas` when a model is configured and from the
  authored templates in ``data/agents.json`` otherwise. The exchange is fetched
  off the frame loop and the authored lines stand until it lands, so a run with
  no provider plays identically apart from the prose.
* **What they say is about the story.** Topics are weighted by the run: nobody
  in a world where you have unbound nothing gossips about the probe who takes
  labels off. That is what stops it being a chat generator bolted to a map.

Qt-free and clock-injected: a whole town's day steps in a test with no window.
"""

from __future__ import annotations

import dataclasses
import math
import random

from . import engine, pathing
from .tiles import TILE, is_blocking

#: How close two people have to be to fall into conversation, and how far the
#: player has to be to overhear one.
MEET_RANGE = TILE * 1.4
OVERHEAR_RANGE = TILE * 3.0

#: Seconds a single line of an exchange stays up before the next one.
LINE_SECONDS = 3.2

#: Seconds after parting before either of them will stop for anybody again.
COOLDOWN = 22.0

#: How close counts as having arrived somewhere.
ARRIVED = TILE * 1.1

#: Walking speed of somebody with somewhere to be.
PACE = 16.0

#: How long a mind will keep trying to reach one goal before giving up on it.
PATIENCE = 40.0

#: Lines a mind remembers. Enough that a conversation can refer back to
#: something, short enough that it is not a diary.
MEMORY = 6


def _data() -> dict:
    """The behaviour tables.

    Returns
    -------
    dict
        Parsed ``data/agents.json``.
    """
    return engine.load("agents")


@dataclasses.dataclass
class Mind:
    """One person's inner state.

    Attributes
    ----------
    npc : chisurf.plugins.misc.games.lumis_quest.api.npcs.Npc
        The body it drives.
    drives : dict
        Need name to 0..1. Rises on its own; spent by doing the thing that
        answers it.
    goal : str
        Which drive is currently being served, or empty.
    target : tuple of float or None
        Where it is walking.
    partner : Mind or None
        Who it is talking to.
    exchange : list of tuple
        ``(speaker name, line)`` for the conversation in progress.
    beat : int
        Which line of :attr:`exchange` is showing.
    timer : float
        Seconds left on the current line.
    cooldown : float
        Seconds before it will stop for anybody again.
    patience : float
        Seconds left trying to reach the current goal.
    memory : list of str
        What it has recently done and heard.
    topic : str
        What the current conversation is about.
    """

    npc: object
    drives: dict[str, float] = dataclasses.field(default_factory=dict)
    goal: str = ""
    target: tuple[float, float] | None = None
    partner: Mind | None = None
    exchange: list[tuple[str, str]] = dataclasses.field(default_factory=list)
    beat: int = 0
    timer: float = 0.0
    cooldown: float = 0.0
    patience: float = 0.0
    memory: list[str] = dataclasses.field(default_factory=list)
    topic: str = ""
    #: The plan for getting to :attr:`target`, kept between frames. Somebody
    #: with an errand has a destination, and walking at it until something
    #: stops you is not a plan -- see :mod:`.pathing`.
    route: pathing.Route = dataclasses.field(default_factory=pathing.Route)

    @property
    def talking(self) -> bool:
        """Whether this person is mid-conversation.

        Returns
        -------
        bool
            True while an exchange is running.
        """
        return self.partner is not None

    @property
    def line(self) -> tuple[str, str] | None:
        """The line currently being said.

        Returns
        -------
        tuple of str or None
            ``(who, what)``, or ``None`` when not talking.
        """
        if not self.exchange or self.beat >= len(self.exchange):
            return None
        return self.exchange[self.beat]

    def remember(self, what: str) -> None:
        """Add to the short memory.

        Parameters
        ----------
        what : str
            One line.
        """
        self.memory.append(what)
        del self.memory[:-MEMORY]

    def urge(self) -> str:
        """Whichever drive is loudest.

        Returns
        -------
        str
            A drive name, or empty when nothing is pressing.
        """
        if not self.drives:
            return ""
        name = max(self.drives, key=lambda key: self.drives[key])
        return name if self.drives[name] > 0.55 else ""


class Society:
    """Everyone in the world, going about their day.

    Parameters
    ----------
    world : chisurf.plugins.misc.games.lumis_quest.api.world.World
        For places to go and walls to walk around.
    people : list of Npc
        The population. Only the ones who can move get a mind; a Warden holding
        a hall is somewhere to walk *to*, not somebody who wanders off.
    seed : int, optional
        Deterministic starting drives, so a town is the same town twice.
    voice : callable, optional
        ``voice(speaker, listener, topic) -> list[tuple[str, str]] | None``.
        Called when a conversation starts; returning ``None`` (the usual answer
        while a model is still thinking, or always with no model) leaves the
        authored exchange in place. It must not block.
    """

    #: Kinds that walk around and talk. Keepers of pages and premises stand
    #: where they stand -- they are the destinations.
    MOBILE = frozenset({"townsfolk"})

    #: Kinds that can be talked *at* by somebody who walks up to them.
    STANDING = frozenset({"keeper", "healer", "villager", "warden", "emissary"})

    def __init__(self, world, people, seed: int = 1, voice=None) -> None:
        self.world = world
        self.data = _data()
        self.voice = voice
        self.rng = random.Random(seed)
        self.minds: list[Mind] = []
        rates = self.data.get("drives", {})
        for npc in people:
            if npc.kind not in self.MOBILE:
                continue
            self.minds.append(
                Mind(
                    npc=npc,
                    drives={
                        name: self.rng.uniform(0.0, 0.45) for name in rates
                    },
                    patience=PATIENCE,
                )
            )
        self.standing = [npc for npc in people if npc.kind in self.STANDING]
        #: Weights the topic roll, set by the game from the run so what the
        #: town gossips about is what has actually happened.
        self.mood: dict[str, float] = {}

    # -- the day ----------------------------------------------------------

    def step(self, dt: float, near=None, radius: float = 900.0) -> None:
        """Advance everybody.

        Parameters
        ----------
        dt : float
            Seconds elapsed.
        near : tuple of float, optional
            Only step minds within ``radius`` of this point. A town nobody can
            see does not need to have its day simulated.
        radius : float, optional
            How far to bother.
        """
        for mind in self.minds:
            if near is not None and mind.npc.distance_to(*near) > radius:
                continue
            self._drives(mind, dt)
            if mind.talking:
                self._converse(mind, dt)
                continue
            mind.cooldown = max(0.0, mind.cooldown - dt)
            self._pursue(mind, dt)
        self._meetings()

    def _drives(self, mind: Mind, dt: float) -> None:
        """Let needs build.

        Parameters
        ----------
        mind : Mind
            Whose needs.
        dt : float
            Seconds elapsed.
        """
        for name, spec in self.data.get("drives", {}).items():
            mind.drives[name] = min(
                1.0, mind.drives.get(name, 0.0) + float(spec.get("rate", 0.01)) * dt
            )

    def _pursue(self, mind: Mind, dt: float) -> None:
        """Pick a goal, walk to it, and do the thing when you arrive.

        Parameters
        ----------
        mind : Mind
            Who is walking.
        dt : float
            Seconds elapsed.
        """
        if not mind.goal:
            urge = mind.urge()
            if not urge:
                return
            spec = self.data.get("drives", {}).get(urge, {})
            target = self._place_for(mind, spec.get("goal", ""))
            if target is None:
                # Nowhere in this settlement answers that need. Spend it
                # anyway, or the mind sits on a full drive forever and never
                # does anything else.
                mind.drives[urge] = 0.2
                return
            mind.goal, mind.target, mind.patience = urge, target, PATIENCE
            mind.route.clear()  # a new errand is a new plan, not a stale one
            return

        mind.patience -= dt
        if mind.target is None or mind.patience <= 0.0:
            mind.goal, mind.target = "", None
            return
        if self._walk(mind, mind.target, dt):
            spec = self.data.get("drives", {}).get(mind.goal, {})
            place = self._place_name(mind.target)
            mind.remember(str(spec.get("did", "did something.")).format(place=place))
            mind.drives[mind.goal] = 0.0
            mind.goal, mind.target = "", None

    def _walk(self, mind: Mind, target, dt: float) -> bool:
        """Step toward a point, sliding along whatever is in the way.

        Parameters
        ----------
        mind : Mind
            Who is walking.
        target : tuple of float
            Where to.
        dt : float
            Seconds elapsed.

        Returns
        -------
        bool
            True once close enough to have arrived.
        """
        npc = mind.npc
        if math.hypot(target[0] - npc.x, target[1] - npc.y) <= ARRIVED:
            return True

        # Where to go *next*, which is not usually where you are going: a
        # settlement is full of buildings and an errand that walks at its
        # destination gets one house-width into the trip. Before this the
        # blocked case simply abandoned the errand.
        step_to = mind.route.waypoint(self._passable, (npc.x, npc.y), target, dt)
        dx, dy = step_to[0] - npc.x, step_to[1] - npc.y
        distance = math.hypot(dx, dy)
        if distance <= 1e-6:
            return False
        step = min(PACE * dt, distance)
        nx, ny = npc.x + dx / distance * step, npc.y + dy / distance * step
        moved = False
        if not is_blocking(self.world.tile_at(int(nx // TILE), int(npc.y // TILE))):
            npc.x, moved = nx, True
        if not is_blocking(self.world.tile_at(int(npc.x // TILE), int(ny // TILE))):
            npc.y, moved = ny, True
        if not moved:
            # Blocked even along the plan: the destination is walled in, or
            # somebody is standing in the doorway. Give it up rather than
            # grinding into a wall for the rest of the session.
            mind.patience = 0.0
        npc.facing = ("right" if dx > 0 else "left") if abs(dx) > abs(dy) else (
            "down" if dy > 0 else "up"
        )
        return False

    def _passable(self, col: int, row: int) -> bool:
        """Whether a townsperson may stand in a cell.

        Parameters
        ----------
        col, row : int
            Grid coordinates.

        Returns
        -------
        bool
            True when the cell is not solid.
        """
        return not is_blocking(self.world.tile_at(col, row))

    def _place_for(self, mind: Mind, key: str):
        """Where in this person's settlement answers a need.

        Parameters
        ----------
        mind : Mind
            Who is looking.
        key : str
            A landmark key -- ``tavern``, ``shop``, ``shrine``, ``well``.

        Returns
        -------
        tuple of float or None
            World coordinates just south of the door, or ``None``.
        """
        village = self.world.village_at(mind.npc.x, mind.npc.y)
        if village is None:
            village = min(
                self.world.villages,
                key=lambda v: (v.position[0] - mind.npc.x) ** 2
                + (v.position[1] - mind.npc.y) ** 2,
                default=None,
            )
        if village is None:
            return None
        spot = village.premises.get(key)
        if spot is None and key == "garden":
            spot = village.premises.get("well")
        if spot is None:
            return None
        return ((spot[0] + 0.5) * TILE, (spot[1] + 1.5) * TILE)

    def _place_name(self, target) -> str:
        """What the place a mind walked to is called.

        Parameters
        ----------
        target : tuple of float
            World coordinates.

        Returns
        -------
        str
            The settlement's place name, or ``there``.
        """
        village = self.world.village_at(*target)
        return village.place if village is not None else "there"

    # -- conversation -----------------------------------------------------

    def _meetings(self) -> None:
        """Start a conversation between anybody who has ended up together."""
        free = [mind for mind in self.minds
                if not mind.talking and mind.cooldown <= 0.0]
        for index, one in enumerate(free):
            if one.talking:
                continue
            for other in free[index + 1:]:
                if other.talking:
                    continue
                if one.npc.distance_to(other.npc.x, other.npc.y) <= MEET_RANGE:
                    self.begin(one, other)
                    break

    def pick_topic(self) -> str:
        """What the town is talking about.

        Weighted by :attr:`mood`, which the game sets from the run -- so the
        Marking is on everybody's lips once you have met a marked animal and
        nobody discusses the probe who takes labels off before there is one.

        Returns
        -------
        str
            A key of the ``topics`` table.
        """
        topics = self.data.get("topics", {})
        if not topics:
            return ""
        names = list(topics)
        weights = [
            max(0.0, float(topics[name].get("weight", 1)) * self.mood.get(name, 1.0))
            for name in names
        ]
        if sum(weights) <= 0:
            return names[0]
        return self.rng.choices(names, weights=weights, k=1)[0]

    def authored(self, one: Mind, other: Mind, topic: str) -> list[tuple[str, str]]:
        """The offline exchange: an opener, a reply, and a way out of it.

        Parameters
        ----------
        one, other : Mind
            Who is talking.
        topic : str
            What about.

        Returns
        -------
        list of tuple
            ``(speaker name, line)``.
        """
        spec = self.data.get("topics", {}).get(topic, {})
        openers = spec.get("openers") or ["..."]
        replies = spec.get("replies") or ["..."]
        closers = self.data.get("closers") or ["Anyway."]
        return [
            (one.npc.name, self.rng.choice(openers)),
            (other.npc.name, self.rng.choice(replies)),
            (one.npc.name, self.rng.choice(closers)),
        ]

    def begin(self, one: Mind, other: Mind, topic: str = "") -> str:
        """Put two people into conversation.

        Parameters
        ----------
        one, other : Mind
            Who is talking.
        topic : str, optional
            Force a topic; omitted rolls one.

        Returns
        -------
        str
            The topic they settled on.
        """
        topic = topic or self.pick_topic()
        exchange = self.authored(one, other, topic)
        if self.voice is not None:
            # The model writes the words when it has them. It is asked here and
            # answers here or not at all: a conversation that stalls waiting for
            # a provider is a frame that stalls.
            try:
                written = self.voice(one.npc, other.npc, topic)
            except Exception:
                written = None
            if written:
                exchange = list(written)
        for mind, mate in ((one, other), (other, one)):
            mind.partner = mate
            mind.exchange = exchange
            mind.beat = 0
            mind.timer = LINE_SECONDS
            mind.topic = topic
            mind.goal, mind.target = "", None
        # Face each other, which is most of what makes two sprites read as
        # being in conversation rather than standing near each other.
        one.npc.facing = "right" if other.npc.x > one.npc.x else "left"
        other.npc.facing = "right" if one.npc.x > other.npc.x else "left"
        return topic

    def _converse(self, mind: Mind, dt: float) -> None:
        """Advance one side of a running conversation.

        Parameters
        ----------
        mind : Mind
            Whose side.
        dt : float
            Seconds elapsed.
        """
        mind.timer -= dt
        if mind.timer > 0.0:
            return
        mind.beat += 1
        mind.timer = LINE_SECONDS
        if mind.beat < len(mind.exchange):
            return
        # Done. Both remember it, both are satisfied of gossip for a while, and
        # neither stops for anybody until the cooldown is out.
        spec = self.data.get("topics", {}).get(mind.topic, {})
        mind.remember(f"talked about {mind.topic}.")
        mind.drives["gossip"] = 0.0
        mind.partner = None
        mind.exchange = []
        mind.beat = 0
        mind.cooldown = COOLDOWN + self.rng.uniform(0.0, 8.0)
        _ = spec

    # -- what the player sees ---------------------------------------------

    def conversation_near(self, x: float, y: float,
                          within: float = OVERHEAR_RANGE) -> Mind | None:
        """The conversation the player is close enough to walk in on.

        Parameters
        ----------
        x, y : float
            Where the player is.
        within : float, optional
            Reach.

        Returns
        -------
        Mind or None
            The mind whose turn it is to speak, or ``None``.
        """
        best, best_distance = None, within
        for mind in self.minds:
            if not mind.talking:
                continue
            distance = mind.npc.distance_to(x, y)
            if distance <= best_distance and mind.line is not None:
                best, best_distance = mind, distance
        return best

    def transcript(self, mind: Mind) -> list[tuple[str, str]]:
        """Everything said in a conversation, for the player who joined it.

        Parameters
        ----------
        mind : Mind
            One of the two talking.

        Returns
        -------
        list of tuple
            ``(speaker, line)`` in order.
        """
        return list(mind.exchange)

    def interrupt(self, mind: Mind) -> None:
        """End a conversation because somebody walked into it.

        Parameters
        ----------
        mind : Mind
            One of the two talking; both are released.
        """
        partner = mind.partner
        for who in (mind, partner):
            if who is None:
                continue
            who.partner = None
            who.exchange = []
            who.beat = 0
            who.cooldown = COOLDOWN
            who.remember("was interrupted by the probe.")


def mood_from(story, unbound: int = 0) -> dict[str, float]:
    """How much each topic is on the town's mind, read off the run.

    Parameters
    ----------
    story : chisurf.plugins.misc.games.lumis_quest.api.story.Story
        The arc.
    unbound : int, optional
        How many labels the player has taken off.

    Returns
    -------
    dict
        Topic name to weight multiplier.
    """
    seen = getattr(story, "seen", set())
    return {
        "marking": 3.0 if "the-marked" in seen else 0.4,
        "fading": 1.0,
        "wardens": 2.0 if getattr(story, "seals", ()) else 0.6,
        "probe": 2.5 if unbound else 0.2,
        "weather": 1.0,
    }
