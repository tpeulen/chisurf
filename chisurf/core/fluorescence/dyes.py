"""Reference-dye properties, read from MMFDB.

Translational diffusion is a property of the labelled species, so it is stored
in MMFDB next to quantum yield and extinction coefficient: every probe may carry
a ``d25`` property holding :math:`D` in water at 25 °C in µm²/s (see
``mmfdb.queries.probes.ProbeMixin.get_diffusion_reference``). ChiSurf keeps no
private copy of that table — this module is the single seam through which FCS
tools (the confocal diffusion/volume calculator, the dye-volume model, …) look
reference dyes up.

The lookup is cached per process. When the database cannot be reached the
shipped MMFDB reference table is used directly, so the tools stay usable in a
read-only or server-less deployment without duplicating the data in ChiSurf.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

#: Cached ``{name: entry}`` mapping; ``None`` until the first lookup.
_CACHE: dict[str, dict[str, Any]] | None = None
#: Cached ``{normalized alias: canonical name}`` mapping.
_ALIASES: dict[str, str] | None = None


def _normalized(name: str) -> str:
    """Return the case- and punctuation-insensitive comparison key for a name."""
    from mmfdb.admin.backend.duplicate_grouping import normalize_name

    return normalize_name(str(name))


def _entries_from_database() -> list[dict[str, Any]]:
    """Read the diffusion-carrying probes from the configured MMFDB database."""
    from mmfdb.repository import MFDatabase
    from mmfdb.store.database_resolver import resolve_database_path
    from mmfdb.store.sql_backend import parse_database_target

    target = parse_database_target(resolve_database_path())
    with MFDatabase(target.location) as db:
        return db.get_diffusion_reference()


def _entries_from_package() -> list[dict[str, Any]]:
    """Read the shipped MMFDB reference table without touching a database."""
    from mmfdb.models import DIFFUSION_PROPERTY_UNIT, REFERENCE_DIFFUSION

    return [
        {
            "probe_id": None,
            "name": entry["name"],
            "category": entry.get("category"),
            "source": "reference_diffusion",
            "d25_um2_s": float(entry["d25_um2_s"]),
            "unit": DIFFUSION_PROPERTY_UNIT,
            "sources": list(entry.get("sources") or []),
        }
        for entry in REFERENCE_DIFFUSION
        if entry.get("d25_um2_s") is not None
    ]


def _load() -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Build the name→entry and alias→name maps from MMFDB."""
    try:
        entries = _entries_from_database()
    except Exception as exc:  # database missing, locked, or remote-only
        logger.warning("MMFDB diffusion lookup failed (%s); using shipped table", exc)
        entries = _entries_from_package()

    dyes = {entry["name"]: entry for entry in entries}

    # Alias map so names that were used before the data moved into MMFDB (e.g.
    # "Rhodamine 6G (Rh6G)" in a saved calculator session) still resolve.
    aliases: dict[str, str] = {}
    for name in dyes:
        aliases.setdefault(_normalized(name), name)
    try:
        from mmfdb.models import REFERENCE_DIFFUSION

        for entry in REFERENCE_DIFFUSION:
            # The catalogue may hold the species under a slightly different
            # spelling (e.g. "Alexa Fluor 647™"), so resolve through the
            # normalized map rather than by exact name.
            canonical = aliases.get(_normalized(entry.get("name") or ""))
            if canonical is None:
                continue
            for alias in entry.get("aliases") or []:
                aliases.setdefault(_normalized(alias), canonical)
    except Exception:  # pragma: no cover - MMFDB always ships the table
        pass

    return dyes, aliases


def reference_dyes(refresh: bool = False) -> dict[str, dict[str, Any]]:
    """Return every MMFDB species carrying a diffusion coefficient.

    Parameters
    ----------
    refresh : bool, optional
        Re-read the database instead of using the process cache. Default False.

    Returns
    -------
    dict
        Mapping of species name to an entry with ``d25_um2_s`` (µm²/s in water
        at 25 °C), ``unit``, ``category``, ``probe_id`` and literature
        ``sources``. Empty only when MMFDB is unavailable *and* ships no table.
    """
    global _CACHE, _ALIASES
    if refresh or _CACHE is None:
        _CACHE, _ALIASES = _load()
    return _CACHE


def dye_names(refresh: bool = False) -> list[str]:
    """Return the sorted names of the reference species, for combo boxes."""
    return sorted(reference_dyes(refresh=refresh))


def get_dye(name: str) -> dict[str, Any] | None:
    """Look a reference species up by name or alias.

    Parameters
    ----------
    name : str
        Species name; matching ignores case, spacing and punctuation and
        accepts the aliases MMFDB records for the species.

    Returns
    -------
    dict or None
        The entry, or ``None`` when the species is unknown.
    """
    dyes = reference_dyes()
    entry = dyes.get(name)
    if entry is not None:
        return entry
    if _ALIASES:
        canonical = _ALIASES.get(_normalized(name))
        if canonical is not None:
            return dyes.get(canonical)
    return None


def diffusion_coefficient_25C(name: str) -> float:
    """Return ``D(25 °C, water)`` in µm²/s for a reference species.

    Parameters
    ----------
    name : str
        Species name or alias.

    Returns
    -------
    float
        Diffusion coefficient in µm²/s, or NaN when unknown.
    """
    entry = get_dye(name)
    if not entry:
        return float("nan")
    try:
        return float(entry["d25_um2_s"])
    except (KeyError, TypeError, ValueError):
        return float("nan")
