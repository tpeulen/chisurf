"""The run, as the one thing scripts are allowed to see.

:mod:`.engine` evaluates conditions and :mod:`.actions` applies effects, and
both of them talk to *this* -- never to the window, the renderer or a global.
That is what keeps a story file testable: a scene runs against a context built
in three lines in a test, with no world on screen and no Qt imported.

It is deliberately a facade rather than the state itself. The team lives in the
game loop because the fight mutates it every turn; the corpus lives in the
world; the arc lives in :mod:`.story`. This object knows where each of them is
and presents one surface to the scripts.
"""

from __future__ import annotations

import dataclasses

from . import gear as gear_api
from . import npcs as npcs_api
from . import story as story_api


@dataclasses.dataclass
class GameContext:
    """Everything a script may read or change.

    Attributes
    ----------
    world : chisurf.plugins.misc.games.lumis_quest.api.world.World
        The corpus as a map.
    story : chisurf.plugins.misc.games.lumis_quest.api.story.Story
        The arc, which owns the witnessed flags and the seals.
    team : list
        The player's beasts, as :class:`..battle.Fighter`. Mutated by fights,
        so it is held by reference rather than copied.
    bodies : list of str
        Species keys of animals travelling with you.
    labels : list of int
        Probe ids of labels taken off marked beasts.
    inventory : list
        Optical gear held.
    loadout : chisurf.plugins.misc.games.lumis_quest.api.gear.Loadout
        What is fitted.
    cleared : list of str
        Page addresses whose guardian has been faced.
    dark : bool
        Whether the player currently stands in the dark manifold.
    village : object
        The settlement being stood in, for rumours. May be ``None``.
    tick : int
        Advanced by the host each time a scene starts, so a line chosen from a
        list is not the same line every visit.
    """

    world: object
    story: story_api.Story
    team: list = dataclasses.field(default_factory=list)
    bodies: list[str] = dataclasses.field(default_factory=list)
    labels: list[int] = dataclasses.field(default_factory=list)
    inventory: list = dataclasses.field(default_factory=list)
    loadout: gear_api.Loadout = dataclasses.field(default_factory=gear_api.Loadout)
    cleared: list[str] = dataclasses.field(default_factory=list)
    dark: bool = False
    village: object = None
    tick: int = 0
    #: What is being spoken to right now -- a Warden key, an order key. Scripts
    #: reach it as ``$subject``, which is how one ``warden`` scene serves all
    #: five of them.
    subject: str = ""

    def __post_init__(self) -> None:
        """Let the arc read the whole run when it evaluates a beat."""
        self.story.context = self

    # -- what conditions read ---------------------------------------------

    @property
    def flags(self) -> set[str]:
        """Story beats already witnessed.

        Returns
        -------
        set of str
            Live -- adding to it is how a scene records a beat.
        """
        return self.story.seen

    @property
    def seals(self) -> set[str]:
        """Warden seals held.

        Returns
        -------
        set of str
            Warden keys.
        """
        return self.story.seals

    @property
    def unbound(self) -> int:
        """How many labels have been taken off marked animals.

        Returns
        -------
        int
            Ever, across the run.
        """
        return self.story.unbound

    @property
    def order(self) -> str | None:
        """The order pledged to.

        Returns
        -------
        str or None
            ``None`` before the choice.
        """
        return self.story.chosen_order

    @property
    def has_lumi(self) -> bool:
        """Whether the hound travels with you.

        Returns
        -------
        bool
            True once found.
        """
        return self.story.has_lumi

    @has_lumi.setter
    def has_lumi(self, value: bool) -> None:
        """Set whether the hound travels with you.

        Parameters
        ----------
        value : bool
            True once found.
        """
        self.story.has_lumi = bool(value)

    def room_counts(self) -> dict[str, int]:
        """How much of the corpus is in each state.

        Returns
        -------
        dict
            Keys ``wild``, ``withered``, ``scouted``, ``settled``.
        """
        return self.world.counts()

    def doctrine_work(self) -> int:
        """Rooms cleared for the pledged order since pledging.

        Returns
        -------
        int
            Zero before a pledge.
        """
        progress = self.story.work_progress
        return progress[0] if progress else 0

    # -- what actions change ----------------------------------------------

    def pledge(self, order: str) -> None:
        """Commit to an order, from here.

        Parameters
        ----------
        order : str
            One of :data:`..story.ORDERS`.
        """
        self.story.choose(
            order, baseline=story_api.cleared_in_lands(self.cleared, order)
        )

    def grant_seal(self, key: str) -> None:
        """Record a Warden beaten.

        Parameters
        ----------
        key : str
            The Warden's key.
        """
        self.story.seal(key)

    def restore_team(self, fraction: float = 1.0) -> None:
        """Bring the team's photon budgets back up.

        Parameters
        ----------
        fraction : float, optional
            1 for a full restore, less for a meal and a sit-down.
        """
        for fighter in self.team:
            gain = int(round(fighter.beast.max_hp * max(0.0, min(fraction, 1.0))))
            fighter.hp = min(fighter.beast.max_hp, fighter.hp + gain)
            fighter.bleed = 0
            fighter.stunned = False

    def rumours(self) -> tuple[str, ...]:
        """What the tavern in this settlement has heard.

        Returns
        -------
        tuple of str
            Read off the world, so every line points at something real.
        """
        if self.village is None:
            return ()
        return npcs_api.rumours(self.world, self.village)

    def offer_gear(self, kind: str = "match") -> gear_api.Gear | None:
        """Give the player a piece of optical gear.

        Parameters
        ----------
        kind : str, optional
            ``match`` picks the filter that best passes the active beast's
            band; ``wide`` gives a forgiving one; ``narrow`` gives a selective
            one.

        Returns
        -------
        Gear or None
            ``None`` when the catalogue has nothing new to give.
        """
        pool = [part for part in gear_api.load_gear() if part.slot == "emission"]
        held = {part.probe_id for part in self.inventory}
        pool = [part for part in pool if part.probe_id not in held]
        if not pool:
            return None
        if kind == "wide":
            part = max(pool, key=lambda one: one.bandwidth_nm)
        elif kind == "narrow":
            part = min(pool, key=lambda one: one.bandwidth_nm or 1e9)
        else:
            band = next((f.beast.emission_nm for f in self.team
                         if f.beast.marked), 520.0)
            part = max(pool, key=lambda one: one.passes(band))
        self.inventory.append(part)
        return part

    def grind_filter(self) -> gear_api.Gear | None:
        """Swap the fitted filter for a narrower one over the same band.

        Returns
        -------
        Gear or None
            The newly fitted part, or ``None`` when nothing is fitted or
            nothing narrower exists.
        """
        fitted = self.loadout.emission
        if fitted is None:
            return None
        centre = fitted.center_nm
        candidates = [
            part for part in gear_api.load_gear()
            if part.slot == "emission"
            and abs(part.center_nm - centre) < 25.0
            and 0 < part.bandwidth_nm < fitted.bandwidth_nm
        ]
        if not candidates:
            return None
        part = min(candidates, key=lambda one: one.bandwidth_nm)
        if part not in self.inventory:
            self.inventory.append(part)
        self.loadout.emission = part
        return part
