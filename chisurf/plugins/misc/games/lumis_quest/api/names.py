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
