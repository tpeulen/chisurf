"""Fantasy names for the regions of the world.

A region is a top-level documentation directory, but "reference" is a folder,
not a place. The map reads as a world only if its parts are named like one, so
each directory gets a name a player would recognise as somewhere to go.

The mapping is explicit for the directories that exist, because a hand-chosen
name beats a generated one every time and there are only a handful. Anything
unrecognised falls back to a deterministic construction, so a new documentation
directory still arrives on the map with a name rather than a slug.
"""

from __future__ import annotations

import hashlib

#: Directory name -> (region name, a line the map can show under it).
REGION_NAMES: dict[str, tuple[str, str]] = {
    "concepts": ("The Arcanum", "where the principles are kept"),
    "guides": ("The Pilgrim Road", "worn smooth by those who came to learn"),
    "manual": ("The Chronicle Vaults", "every working recorded in order"),
    "reference": ("The Great Library", "vast, exact, and largely unread"),
    "development": ("The Forge", "where the tools themselves are beaten out"),
    "fundamentals": ("The Wellspring", "the source everything downstream drinks from"),
    "references": ("The Cairns", "markers left pointing elsewhere"),
    "getting_started": ("The Threshold", "the first door, and the easiest to miss"),
    "tutorials": ("The Proving Grounds", "learn by doing, and by failing"),
    "api": ("The Runeworks", "exact words that make things happen"),
    "examples": ("The Sampler's Yard", "small finished things, laid out to copy"),
    "images": ("The Gallery", "kept for looking at"),
}

#: Word banks for a directory nobody has named yet.
_QUALIFIERS = (
    "Hollow", "Reach", "Marches", "Expanse", "Hinterland", "Weald",
    "Downs", "Fastness", "Barrows", "Waystation",
)
_ADJECTIVES = (
    "Quiet", "Forgotten", "Outer", "Deep", "Wandering", "Silver",
    "Hidden", "Low", "Far", "Old",
)


#: Settlement name parts. A toctree group is called something like "Core
#: Methods", which is a section heading, not a place -- nobody says "I am
#: walking to Core Methods". A settlement gets a place name of its own and
#: keeps the group title as what it is known *for*.
_SETTLEMENT_FIRST = (
    "Lamp", "Wick", "Ember", "Glass", "Quench", "Dim", "Kindle", "Taper",
    "Beacon", "Ash", "Prism", "Lumen", "Halo", "Spark", "Candle", "Shutter",
    "Amber", "Flint", "Gleam", "Tallow",
)
_SETTLEMENT_LAST = (
    "foot", "hollow", "ford", "water", "moor", "bridge", "gate", "mere",
    "wick", "holt", "stead", "reach", "fell", "combe", "thorpe", "barrow",
)

#: What a land is made of. Chosen per region and stable, so a land you learned
#: as marshy stays marshy. The mix decides ground cover, how many lakes it
#: grows, and which animals are at home in it.
BIOMES: dict[str, tuple[str, str]] = {
    "meadow": ("meadowland", "open, and easy to be seen crossing"),
    "forest": ("deep wood", "old trees, and not much sky"),
    "marsh": ("marshland", "the ground gives, and things live under it"),
    "highland": ("highland", "stone, wind, and a cave in every cliff"),
    "coast": ("coastland", "salt, shallows, and long light"),
}

#: In the order a region cycles through them, so no two neighbouring lands
#: look alike.
BIOME_ORDER: tuple[str, ...] = ("meadow", "forest", "coast", "highland", "marsh")


def settlement_name(key: str) -> str:
    """A place name for a settlement.

    Parameters
    ----------
    key : str
        Anything stable about the settlement -- its group title is usual.

    Returns
    -------
    str
        e.g. ``Emberford``. The same key always gives the same name.
    """
    seed = int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big")
    first = _SETTLEMENT_FIRST[seed % len(_SETTLEMENT_FIRST)]
    last = _SETTLEMENT_LAST[(seed >> 9) % len(_SETTLEMENT_LAST)]
    return f"{first}{last}"


def biome_for(index: int, directory: str) -> str:
    """Which biome a land is.

    Parameters
    ----------
    index : int
        The land's position in layout order, so neighbours differ.
    directory : str
        Its documentation directory, so the choice is stable per corpus.

    Returns
    -------
    str
        A key of :data:`BIOMES`.
    """
    seed = int.from_bytes(hashlib.sha256(directory.encode("utf-8")).digest()[:4], "big")
    return BIOME_ORDER[(index + seed % 2) % len(BIOME_ORDER)]


def region_name(directory: str) -> tuple[str, str]:
    """Name a region after its documentation directory.

    Parameters
    ----------
    directory : str
        Directory name, e.g. ``guides``.

    Returns
    -------
    tuple of str
        ``(name, subtitle)``. The subtitle may be empty for a generated name.
    """
    if directory in REGION_NAMES:
        return REGION_NAMES[directory]
    seed = int.from_bytes(hashlib.sha256(directory.encode("utf-8")).digest()[:8], "big")
    adjective = _ADJECTIVES[seed % len(_ADJECTIVES)]
    qualifier = _QUALIFIERS[(seed >> 8) % len(_QUALIFIERS)]
    pretty = directory.replace("_", " ").replace("-", " ").title()
    return (f"The {adjective} {qualifier}", pretty)
