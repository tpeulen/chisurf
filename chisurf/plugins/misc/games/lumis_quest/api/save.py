"""The run: what carries between sessions.

Separate from :mod:`.game_state`, which tracks review progression -- XP,
streaks, achievements -- because the two answer different questions and
tangling them would make either hard to change. This one answers "where was I,
what was I carrying, and how bleached is my team".

Everything is stored by **identifier, not by value**. A creature is a probe id
and a current HP, not a copy of its stat block; a filter is a probe id. That
way a corrected extinction coefficient in the database reaches a saved game,
instead of the save quietly preserving a number that has since been fixed.
"""

from __future__ import annotations

import dataclasses
import json
import pathlib

from .gear import Gear, Loadout, load_gear
from .roster import Creature, load_roster

#: Where a run lives. Beside the review progression, not inside it.
SAVE_DIR = pathlib.Path.home() / ".chisurf"
SAVE_FILE = SAVE_DIR / "lumis_quest_run.json"

#: Bumped when the shape changes in a way an older file cannot satisfy.
VERSION = 1


@dataclasses.dataclass
class RunState:
    """One player's progress through the world.

    Attributes
    ----------
    position : tuple of float
        Where Iris stood, in world units.
    team : list of tuple
        ``(probe_id, hp)`` for each creature in the party.
    collection : list of int
        Probe ids of every creature caught.
    inventory : list of int
        Probe ids of every piece of gear held.
    emission_id : int or None
        Fitted emission filter.
    detector_id : int or None
        Fitted detector.
    cleared : list of str
        Addresses of rooms whose guardian has been beaten.
    order : str or None
        The order the player committed to, if any.
    tutorial : list of str
        Teaching steps already completed, so the banners appear once per
        player rather than once per session.
    has_lumi : bool
        Whether the hound has been found and befriended. Defaults True so a
        save from before the waking act keeps its companion.
    story_seen : list of str
        Story beats the player has witnessed, so a resumed run does not
        replay its own opening.
    pledge_baseline : int or None
        Cleared-rooms-in-doctrine-lands at the moment of pledging.
    lab : list
        Growing cultures, ``[probe_id, planted_at, duration]`` per plot —
        wall-clock timestamps, because maturation is real time.
    """

    position: tuple[float, float] = (0.0, 0.0)
    team: list[tuple[int, int]] = dataclasses.field(default_factory=list)
    collection: list[int] = dataclasses.field(default_factory=list)
    inventory: list[int] = dataclasses.field(default_factory=list)
    emission_id: int | None = None
    detector_id: int | None = None
    cleared: list[str] = dataclasses.field(default_factory=list)
    order: str | None = None
    tutorial: list[str] = dataclasses.field(default_factory=list)
    has_lumi: bool = True
    story_seen: list[str] = dataclasses.field(default_factory=list)
    pledge_baseline: int | None = None
    lab: list = dataclasses.field(default_factory=list)

    def as_dict(self) -> dict:
        """Serialise to plain JSON types.

        Returns
        -------
        dict
            Ready for :func:`json.dumps`.
        """
        return {
            "version": VERSION,
            "position": list(self.position),
            "team": [list(entry) for entry in self.team],
            "collection": list(self.collection),
            "inventory": list(self.inventory),
            "emission_id": self.emission_id,
            "detector_id": self.detector_id,
            "cleared": list(self.cleared),
            "order": self.order,
            "tutorial": list(self.tutorial),
            "has_lumi": bool(self.has_lumi),
            "story_seen": list(self.story_seen),
            "pledge_baseline": self.pledge_baseline,
            "lab": [list(row) for row in self.lab],
        }

    def save(self, path: pathlib.Path | None = None) -> pathlib.Path:
        """Write the run to disk.

        Parameters
        ----------
        path : pathlib.Path, optional
            Destination. Defaults to :data:`SAVE_FILE`.

        Returns
        -------
        pathlib.Path
            Where it was written.
        """
        target = path or SAVE_FILE
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return target

    @classmethod
    def load(cls, path: pathlib.Path | None = None) -> "RunState":
        """Read a run from disk.

        A missing, unreadable or future-versioned file yields a fresh run rather
        than raising: losing a save is annoying, and refusing to start the game
        because of one is worse.

        Parameters
        ----------
        path : pathlib.Path, optional
            Source. Defaults to :data:`SAVE_FILE`.

        Returns
        -------
        RunState
            The stored run, or an empty one.
        """
        source = path or SAVE_FILE
        try:
            raw = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        if not isinstance(raw, dict) or raw.get("version") != VERSION:
            return cls()
        try:
            return cls(
                position=tuple(raw.get("position", (0.0, 0.0)))[:2],
                team=[tuple(entry)[:2] for entry in raw.get("team", [])],
                collection=[int(value) for value in raw.get("collection", [])],
                inventory=[int(value) for value in raw.get("inventory", [])],
                emission_id=raw.get("emission_id"),
                detector_id=raw.get("detector_id"),
                cleared=[str(value) for value in raw.get("cleared", [])],
                order=raw.get("order"),
                tutorial=[str(value) for value in raw.get("tutorial", [])],
                has_lumi=bool(raw.get("has_lumi", True)),
                story_seen=[str(value) for value in raw.get("story_seen", [])],
                pledge_baseline=raw.get("pledge_baseline"),
                lab=[list(row) for row in raw.get("lab", [])],
            )
        except (TypeError, ValueError):
            return cls()


def creatures_by_id(pool=None) -> dict[int, Creature]:
    """Index the roster by probe id.

    Parameters
    ----------
    pool : sequence of Creature, optional
        Defaults to the whole roster.

    Returns
    -------
    dict
        Probe id to creature.
    """
    return {creature.probe_id: creature for creature in (pool if pool is not None else load_roster())}


def gear_by_id(pool=None) -> dict[int, Gear]:
    """Index the gear catalogue by probe id.

    Parameters
    ----------
    pool : sequence of Gear, optional
        Defaults to the whole catalogue.

    Returns
    -------
    dict
        Probe id to gear.
    """
    return {part.probe_id: part for part in (pool if pool is not None else load_gear())}


def restore_loadout(state: RunState, pool=None) -> Loadout:
    """Rebuild the fitted optics from a saved run.

    Parameters
    ----------
    state : RunState
        The run.
    pool : sequence of Gear, optional
        Catalogue to resolve against.

    Returns
    -------
    Loadout
        With whatever could be resolved. A part that has vanished from the
        catalogue is simply left unfitted rather than failing the load.
    """
    index = gear_by_id(pool)
    return Loadout(
        emission=index.get(state.emission_id) if state.emission_id is not None else None,
        detector=index.get(state.detector_id) if state.detector_id is not None else None,
    )
