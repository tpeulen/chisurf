"""Units, from the dictionary rather than from three conventions.

A unit was encoded in-band, in a name, three different ways: `Duration (ms)` in
a burst table, `Name | unit` in an expression column header, and bare factor
dictionaries in the DEER and FCS readers. None of them agreed on spelling, none
could be checked, and all of them failed on the columns that omitted the suffix.

The unit vocabulary is `_mmfdb_units` in the MMFDB dictionary: a code, the
symbol a person reads, and the SI factor a converter needs. This module is the
only thing in ChiSurf that reads it, so a display layer asks for a symbol and a
reader asks for a factor, and neither invents one. This is the vocabulary half
of a broader plan to carry units through parameters, axes and files across the
whole stack.
"""

from __future__ import annotations

import functools
import re
from typing import Any, NamedTuple

__all__ = [
    "Unit",
    "canonical",
    "convert",
    "known_units",
    "split_label",
    "symbol",
    "unit",
]


class Unit(NamedTuple):
    """One row of the dictionary's unit table."""

    code: str
    symbol: str
    si_factor: float | None
    si_unit: str


#: Legacy spellings seen in file headers and column names, mapped to the code.
#: Reading these is supported; writing them is not — a writer uses the code.
_LEGACY = {
    "s": "seconds", "sec": "seconds",
    "ms": "milliseconds",
    "us": "microseconds", "µs": "microseconds", "μs": "microseconds",
    "ns": "nanoseconds",
    "ps": "picoseconds",
    "fs": "femtoseconds",
    "hz": "hertz", "khz": "kilohertz", "mhz": "megahertz",
    "cps": "counts_per_second",
    "nm": "nanometres", "um": "micrometres", "µm": "micrometres",
    "a": "angstroms", "å": "angstroms",
    "px": "pixels", "deg": "degrees", "rad": "radians",
    "k": "kelvins", "c": "celsius",
    "m": "molar", "mm": "millimolar", "um_conc": "micromolar",
    "nm_conc": "nanomolar", "pm": "picomolar",
}


@functools.lru_cache(maxsize=1)
def known_units() -> dict[str, Unit]:
    """Return every unit the dictionary declares, keyed by code.

    Returns
    -------
    dict of str to Unit
    """
    from mmfdb.schema.pdbx_metadata import MmcifDictionary

    paths = [
        MmcifDictionary._resolve_dic(name)
        for name in (*MmcifDictionary.BUNDLED_DICTS, *MmcifDictionary.EXPORT_ONLY_DICTS)
    ]
    rows = MmcifDictionary(*paths).category_rows("mmfdb_units")
    out: dict[str, Unit] = {}
    for row in rows:
        factor = row.get("si_factor", "")
        out[row["code"]] = Unit(
            code=row["code"],
            symbol="" if row.get("symbol", ".") == "." else row.get("symbol", ""),
            si_factor=float(factor) if factor not in ("", ".", "?") else None,
            si_unit="" if row.get("si_unit", ".") == "." else row.get("si_unit", ""),
        )
    return out


def canonical(text: str) -> str:
    """Return the unit code for *text*, or ``""`` if it names no unit.

    Accepts a code as it is, and the legacy spellings that appear in file
    headers and column names — ``ns``, ``µs``, ``KHz``. Reading those is
    supported because the files exist; writing them is not.

    Parameters
    ----------
    text : str
        A code, a symbol, or a legacy abbreviation.

    Returns
    -------
    str
        The canonical code, or ``""``.
    """
    if not text:
        return ""
    raw = text.strip()
    units = known_units()
    if raw in units:
        return raw
    lowered = raw.lower()
    if lowered in units:
        return lowered
    for code, u in units.items():
        if u.symbol and u.symbol.lower() == lowered:
            return code
    return _LEGACY.get(lowered, "")


def unit(code: str) -> Unit | None:
    """Return the dictionary row for a unit code, or ``None``."""
    return known_units().get(code)


def symbol(code: str) -> str:
    """Return how a unit is written for a person.

    Parameters
    ----------
    code : str
        A canonical unit code.

    Returns
    -------
    str
        ``"ns"`` for ``"nanoseconds"``. Empty for a unit with no symbol, and
        for a code the dictionary does not know — an unknown unit is shown as
        nothing rather than as its own code, because a made-up symbol on an
        axis is worse than a bare number.
    """
    u = known_units().get(code)
    return u.symbol if u else ""


def convert(value: float, frm: str, to: str) -> float:
    """Convert between two units of the same SI quantity.

    Parameters
    ----------
    value : float
    frm, to : str
        Canonical unit codes.

    Returns
    -------
    float

    Raises
    ------
    ValueError
        If either unit is unknown, has no SI factor, or they measure different
        quantities. Refusing is the point: silently returning the value
        unchanged is how a millisecond becomes a nanosecond.
    """
    a, b = known_units().get(frm), known_units().get(to)
    if a is None or b is None:
        raise ValueError(f"unknown unit in {frm!r} -> {to!r}")
    if a.si_factor is None or b.si_factor is None:
        raise ValueError(f"{frm!r} or {to!r} is not a scaled SI quantity")
    if a.si_unit != b.si_unit:
        raise ValueError(f"{frm!r} is {a.si_unit}, {to!r} is {b.si_unit}")
    return value * a.si_factor / b.si_factor


#: ``Name (unit)`` and ``Name | unit`` — the two in-band conventions this
#: replaces. Matched only to *read* files and headers already written that way.
_SUFFIX = re.compile(r"^(?P<name>.*?)\s*[(\[]\s*(?P<unit>[^)\]]+?)\s*[)\]]\s*$")


def split_label(label: str) -> tuple[str, str]:
    """Split a legacy column header into its name and unit code.

    Handles both conventions that grew up in this tree: ``"Duration (ms)"`` and
    ``"Tau | ns"``. Used to *understand* existing files and headers — a writer
    records the unit as metadata instead, so nothing new is produced in either
    shape.

    Parameters
    ----------
    label : str

    A label may carry both conventions at once, and one in this tree does: a
    burst table's window rate is ``"S prompt green (kHz) | 0-2048"``, where the
    bar separates a *range* rather than a unit and the unit is in the brackets
    before it. So a bar whose right-hand side is not a unit falls through to the
    bracket on its left-hand side, instead of ending the search. Reading the
    whole label as a suffix cannot find it — the regex is anchored at the end,
    and the label ends in the range.

    Returns
    -------
    tuple of (str, str)
        The name, and the unit code (``""`` when the label carries none). The
        name comes back unchanged when no unit was recognised, so a bracketed
        qualifier that is not a unit — ``"Tau (green)"`` — is left alone.
    """
    if "|" in label:
        name, _, rest = label.partition("|")
        code = canonical(rest)
        if code:
            return name.strip(), code
        match = _SUFFIX.match(name.strip())
        if match:
            code = canonical(match.group("unit"))
            if code:
                return label.strip(), code

    match = _SUFFIX.match(label)
    if match:
        code = canonical(match.group("unit"))
        if code:
            return match.group("name").strip(), code
    return label.strip(), ""
