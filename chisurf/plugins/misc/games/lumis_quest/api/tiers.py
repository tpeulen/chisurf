"""The ladder: five tiers, five Wardens, five seals.

A world you can walk end to end on the first afternoon has no shape. This is
the shape — the oldest one the genre has, and it works because every rung is a
door rather than a number:

* A beast's **tier** is derived from what it is (see :mod:`.bestiary`), not
  assigned. Tier V is a bright, durable label in a heavy body; tier I is a moth
  wearing something dim.
* Your **licence** is how many Warden seals you carry. You may only take a
  label off a beast at or below your licence — above it, the beast simply
  shrugs the trap off, and the game says why.
* **Crossings are gated by seal.** The bridge out of a land wants a tier, so
  the map opens in an order and each opening is earned.
* Each Warden **teaches one real thing** and then makes you use it. That is the
  whole reason to have five of them rather than one big fight: the lessons are
  brightness, spectral overlap, filters, the dark state, and where light
  actually comes from.

Qt-free: this is the rule set, and the world reads it.
"""

from __future__ import annotations

import dataclasses

from . import engine

#: Tier names, index 0 unused so ``TIER_NAMES[tier]`` reads naturally.
TIER_NAMES: tuple[str, ...] = (
    "", "Ember", "Glow", "Beacon", "Blaze", "Wellspring",
)

#: A colour for each tier, as an emission wavelength the renderer can tint
#: with -- so the ladder is the same spectrum as everything else in the game.
TIER_NM: tuple[float, ...] = (0.0, 600.0, 545.0, 488.0, 460.0, 680.0)


@dataclasses.dataclass(frozen=True)
class Warden:
    """One keeper of a tier, and the lesson they hold.

    Attributes
    ----------
    key : str
        Stable identifier, stored in the save.
    name : str
        Who they are.
    title : str
        What they are called.
    tier : int
        The licence tier their seal grants.
    seal : str
        The seal's name.
    lands : tuple of str
        Documentation directories whose land they prefer to stand in, most
        wanted first.
    lesson : str
        The real thing they teach, in one line.
    body : str
        The species key of the beast they field.
    lines : tuple of str
        What they say before the fight.
    after : str
        What they say once beaten.
    """

    key: str
    name: str
    title: str
    tier: int
    seal: str
    lands: tuple[str, ...]
    lesson: str
    body: str
    lines: tuple[str, ...]
    after: str


#: The five, in the order a run meets them, read from ``data/wardens.json``.
#: Each fight is unwinnable by the strategy that beat the one before, which is
#: what makes the lesson stick -- and none of that text lives in Python, so a
#: writer can rebalance the ladder's *words* without touching the rules.
WARDENS: tuple[Warden, ...] = tuple(
    Warden(
        key=entry["key"],
        name=entry["name"],
        title=entry["title"],
        tier=int(entry["tier"]),
        seal=entry["seal"],
        lands=tuple(entry.get("lands", ())),
        lesson=entry.get("lesson", ""),
        body=entry.get("body", "hare"),
        lines=tuple(entry.get("lines", ())),
        after=entry.get("after", ""),
    )
    for entry in engine.load("wardens").get("wardens", ())
)

#: By key.
BY_KEY: dict[str, Warden] = {warden.key: warden for warden in WARDENS}


def licence(seals) -> int:
    """The highest tier the player is permitted to take a label from.

    Parameters
    ----------
    seals : iterable of str
        Warden keys already beaten.

    Returns
    -------
    int
        1 before any seal -- an unlicensed probe may still handle the ordinary
        wild -- rising by one per seal to 5 with all of them.
    """
    held = {key for key in seals if key in BY_KEY}
    return max(1, min(1 + len(held), 5))


def next_warden(seals) -> Warden | None:
    """Which Warden is next on the ladder.

    Parameters
    ----------
    seals : iterable of str
        Warden keys already beaten.

    Returns
    -------
    Warden or None
        ``None`` once all five are held.
    """
    held = {key for key in seals if key in BY_KEY}
    for warden in WARDENS:
        if warden.key not in held:
            return warden
    return None


def can_take(beast_tier: int, seals) -> bool:
    """Whether a label may be taken off a beast of this tier.

    Parameters
    ----------
    beast_tier : int
        The beast's tier.
    seals : iterable of str
        Warden keys held.

    Returns
    -------
    bool
        False when the beast outranks the licence.
    """
    return beast_tier <= licence(seals)


def refusal(beast_tier: int, seals) -> str:
    """Why a take failed, in words a player can act on.

    Parameters
    ----------
    beast_tier : int
        The beast's tier.
    seals : iterable of str
        Warden keys held.

    Returns
    -------
    str
        Empty when the take is permitted.
    """
    if can_take(beast_tier, seals):
        return ""
    warden = next_warden(seals)
    name = TIER_NAMES[min(beast_tier, len(TIER_NAMES) - 1)]
    if warden is None:
        return f"The {name} label will not come loose."
    return (f"{name} is beyond your seal. Find {warden.name}, "
            f"{warden.title}.")


def crossing_tier(region_index: int) -> int:
    """Which licence a land's crossing demands.

    The first land is open to anyone; each one after wants another seal, so the
    map unfolds in an order instead of all at once.

    Parameters
    ----------
    region_index : int
        Position of the land in layout order.

    Returns
    -------
    int
        1..5.
    """
    return max(1, min(1 + region_index // 2, 5))
