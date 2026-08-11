"""Character perks unlocked by level advancement.

As Iris earns XP and levels up through documentation reviews and Warden victories,
she unlocks passive skill perks that enhance overworld exploration, spell efficiency,
and unbinding success rates.
"""

from __future__ import annotations

import dataclasses


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


PERKS: tuple[Perk, ...] = (
    Perk("swift_step", "Swift Step", 2, "+15% overworld walk speed."),
    Perk("photon_thrift", "Photon Thrift", 3, "-25% photon cost for magic spells."),
    Perk("lens_mastery", "Lens Mastery", 4, "+15% unbind success rate in battle."),
    Perk("herbologist", "Herbologist", 5, "2x reagent drop rate from slashing grass."),
    Perk("vital_shield", "Vital Shield", 6, "FRET Shield spawns +2 rotating barrier dots."),
    Perk("sage_insight", "Sage Insight", 7, "Earn 1.5x XP from page sign-offs."),
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
