"""Detector names: ``emission|excitation`` colours, the names that replace green / red / yellow.

A detector of a fluorescence setup is named by the colour it detects and the colour that excited
what it detects, ``E|X``: ``G|G`` is green emission under green (donor) excitation, ``R|G`` red
emission under green excitation (the FRET acceptor signal), ``R|R`` red emission under red
excitation (the acceptor directly excited, PIE / ALEX). The colours, in wavelength order, are
blue ``B``, green ``G``, yellow ``Y`` and red ``R`` -- enough for three-colour FRET (``B|B``,
``G|B``, ``R|B``, ``G|G``, ``R|G``, ``R|R``).

Every setup, container, table and export carries these names. A saved setup with the historic
names is converted once when the store is read (:data:`LEGACY`: ``green`` is ``G|G``, ``red`` is
``R|G``, ``yellow`` is ``R|R``, ``blue`` is ``B|B``); old burst files are not translated.

``|`` cannot be part of a Windows file name: where a detector names a file, :func:`slug` gives
``G-G``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

#: The colours, in wavelength order: (letter, word).
COLOURS: tuple[tuple[str, str], ...] = (("B", "blue"), ("G", "green"), ("Y", "yellow"), ("R", "red"))
_ORDER = {letter: i for i, (letter, _w) in enumerate(COLOURS)}
#: Separates the emission from the excitation colour.
SEPARATOR = "|"


def name(emission: str, excitation: str) -> str:
    """The detector name of *emission* under *excitation* (``name("R", "G") == "R|G"``)."""
    return f"{emission.upper()}{SEPARATOR}{excitation.upper()}"


#: Every default name: an emission no bluer than its excitation, in wavelength order of the
#: excitation, then the emission (B|B, G|B, Y|B, R|B, G|G, Y|G, R|G, Y|Y, R|Y, R|R).
DEFAULT_NAMES: tuple[str, ...] = tuple(
    name(em, ex)
    for ex, _w in COLOURS
    for em, _v in COLOURS
    if _ORDER[em] >= _ORDER[ex]
)

#: The names of a two-colour PIE / ALEX setup, in their usual order.
DONOR = "G|G"
ACCEPTOR = "R|G"
ACCEPTOR_DIRECT = "R|R"
TWO_COLOUR = (DONOR, ACCEPTOR, ACCEPTOR_DIRECT)

#: Historic name -> name: the one-time conversion of saved setups (:func:`canonical`).
LEGACY: dict[str, str] = {"green": DONOR, "red": ACCEPTOR, "yellow": ACCEPTOR_DIRECT, "blue": "B|B"}

_NAME = re.compile(r"^([BGYR])\|([BGYR])$")


def is_default(detector: str) -> bool:
    """Whether *detector* is one of :data:`DEFAULT_NAMES`."""
    return str(detector) in DEFAULT_NAMES


def canonical(detector: str) -> str:
    """*detector* under its name: a historic name (any case) becomes ``E|X``; ``g|g`` -> ``G|G``;
    any other name is kept as it is (a user's own name)."""
    text = str(detector)
    legacy = LEGACY.get(text.strip().lower())
    if legacy is not None:
        return legacy
    if _NAME.match(text.strip().upper()):
        return text.strip().upper()
    return text


def canonical_detectors(detectors: Mapping[str, object]) -> dict:
    """*detectors* (``{name: definition}``) with every name :func:`canonical`; the order is kept.
    Two names that become the same (``green`` and ``G|G``) keep the first definition."""
    out: dict = {}
    for key, value in detectors.items():
        out.setdefault(canonical(key), value)
    return out


def emission(detector: str) -> str | None:
    """The emission colour letter of *detector* (``"R"`` for ``R|G``), or ``None``."""
    found = _NAME.match(canonical(detector))
    return found.group(1) if found else None


def excitation(detector: str) -> str | None:
    """The excitation colour letter of *detector* (``"G"`` for ``R|G``), or ``None``."""
    found = _NAME.match(canonical(detector))
    return found.group(2) if found else None


def find(detectors: Iterable[str], wanted: str) -> str | None:
    """The detector of *detectors* that is *wanted* -- a name or a historic name -- in the
    spelling *detectors* uses; ``None`` when there is none (``find(["green"], "G|G") == "green"``)."""
    target = canonical(wanted)
    for detector in detectors:
        if canonical(detector) == target:
            return detector
    return None


#: The FRET roles of a two-colour PIE setup, by name.
ROLES: dict[str, str] = {DONOR: "donor", ACCEPTOR: "acceptor", ACCEPTOR_DIRECT: "acceptor_direct"}


def role(detector: str) -> str | None:
    """``"donor"``, ``"acceptor"`` (FRET-sensitised) or ``"acceptor_direct"`` -- the part
    *detector* plays in two-colour FRET -- or ``None``. By name (``G|G``, ``R|G``, ``R|R`` and their
    historic aliases), else by a ``donor`` / ``acceptor`` in a custom name."""
    found = ROLES.get(canonical(detector))
    if found is not None:
        return found
    lowered = str(detector).lower()
    if "donor" in lowered:
        return "donor"
    if "acceptor" in lowered:
        return "acceptor"
    return None


def detector_of_role(detectors: Iterable[str], wanted: str) -> str | None:
    """The detector of *detectors* that plays *wanted* (``"donor"``, ``"acceptor"``,
    ``"acceptor_direct"``), in the spelling *detectors* uses, or ``None``."""
    for detector in detectors:
        if role(detector) == wanted:
            return detector
    return None


_IN_COLUMN = re.compile(r"\(([^()]+)\)")


def column_detector(column_name: str) -> str | None:
    """The detector a burst-table column belongs to (``Number of Photons (R|G)`` -> ``R|G``,
    ``R|G Count Rate (KHz)`` -> ``R|G``), or ``None``."""
    text = str(column_name)
    for found in _IN_COLUMN.findall(text):
        if _NAME.match(found) or found.lower() in LEGACY:
            return canonical(found)
    head = text.split(" ", 1)[0]
    return head if _NAME.match(head) else None


def slug(detector: str) -> str:
    """*detector* as part of a file name: ``|`` is not allowed on Windows (``G|G`` -> ``G-G``)."""
    return str(detector).replace(SEPARATOR, "-")


def label(detector: str) -> str:
    """How a column header shows *detector*: a name as it is, a historic one capitalised as before
    (``{Detector} Count Rate`` -> ``G|G Count Rate``, but ``Green Count Rate`` for ``green``)."""
    text = str(detector)
    return text if _NAME.match(text) else text.capitalize()


__all__ = [
    "ACCEPTOR",
    "ACCEPTOR_DIRECT",
    "COLOURS",
    "DEFAULT_NAMES",
    "DONOR",
    "LEGACY",
    "SEPARATOR",
    "TWO_COLOUR",
    "canonical",
    "canonical_detectors",
    "column_detector",
    "detector_of_role",
    "emission",
    "excitation",
    "find",
    "is_default",
    "label",
    "name",
    "role",
    "slug",
]
