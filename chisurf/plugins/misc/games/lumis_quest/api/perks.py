"""Character perks unlocked by level advancement.

As Iris earns XP and levels up through documentation reviews and Warden victories,
she unlocks passive skill perks that enhance overworld exploration, spell efficiency,
and unbinding success rates.
"""

from __future__ import annotations

import dataclasses
import json
import pathlib

_DATA_FILE = pathlib.Path(__file__).resolve().parent.parent / "data" / "perks.json"
_DATA = json.loads(_DATA_FILE.read_text(encoding="utf-8"))


@dataclasses.dataclass(frozen=True)
class Perk:
    """A passive character upgrade unlocked at a specific level.

    Attributes
    ----------
    key : str
        Unique identifier for save state.
    name : str
        Display title.
    level_req : int
        Minimum level required to activate this perk.
    text : str
        Description of perk benefits.
    """

    key: str
    name: str
    level_req: int
    text: str


PERKS: tuple[Perk, ...] = tuple(
    Perk(key=e["key"], name=e["name"], level_req=e["level_req"], text=e["text"])
    for e in _DATA["perks"]
)

BY_KEY: dict[str, Perk] = {perk.key: perk for perk in PERKS}


def unlocked_perks(level: int) -> tuple[Perk, ...]:
    """Return all perks unlocked at the current level.

    Parameters
    ----------
    level : int
        Player's current 1-based level.

    Returns
    -------
    tuple of Perk
    """
    return tuple(perk for perk in PERKS if level >= perk.level_req)
