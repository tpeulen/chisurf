"""Reference diffusion from configured MMFDB or a versioned portable snapshot.

The ChiSurf-owned JSON asset is an exact export of MMFDB's curated definitions,
not an independently maintained scientific table. Its origin manifest pins the
upstream revision, units, conditions and digest. No optional package or database
is needed for ordinary reference selection. Explicit database deployments are
read without bootstrap or authentication changes; their errors propagate.
"""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any

_CACHE: dict[str, dict[str, Any]] | None = None
_ALIASES: dict[str, str] | None = None


class ReferenceSourceUnavailable(FileNotFoundError):
    """An explicitly configured reference package or local database is absent."""


def _normalized(name: str) -> str:
    """Compare display names using the upstream name rule, never scientific UIDs."""
    text = str(name or "").lower()
    for filler in ("fluor", "dye", "fluorescent"):
        text = text.replace(filler, "")
    if text.startswith(("af-", "af ")):
        text = text.replace("af", "alexa", 1)
    elif text.startswith("af") and len(text) > 2 and text[2].isdigit():
        text = "alexa" + text[2:]
    text = text.replace("cyanine", "cy")
    return re.sub(r"[^a-z0-9]", "", text)


def validate_reference(entry: Any) -> dict[str, Any]:
    """Copy a finite, unit-explicit scientific reference into data-only state.

    Parameters
    ----------
    entry : dict
        Selected source entry, including its identity and literature provenance.

    Returns
    -------
    dict
        Detached JSON-compatible entry with a positive D(25 °C, water).

    Raises
    ------
    ValueError
        The name, coefficient, units or provenance are invalid.
    """
    if not isinstance(entry, dict):
        raise ValueError("reference must be a mapping")
    name = entry.get("name")
    value = entry.get("d25_um2_s")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("reference must name a species")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("reference diffusion must be numeric")
    if not math.isfinite(value) or value <= 0:
        raise ValueError("reference diffusion must be finite and positive")
    if entry.get("unit") != "um^2/s":
        raise ValueError("reference diffusion requires um^2/s at 25 °C in water")
    if not isinstance(entry.get("sources"), list) or any(
        not isinstance(source, dict) for source in entry["sources"]
    ):
        raise ValueError("reference literature sources must be a list of mappings")
    for source in entry["sources"]:
        if any(key in source and not isinstance(source[key], str) for key in ("citation", "url")):
            raise ValueError("reference citations and URLs must be strings")
        if "methods" in source and (
            not isinstance(source["methods"], list)
            or any(not isinstance(method, str) for method in source["methods"])
        ):
            raise ValueError("reference methods must be strings")
    aliases = entry.get("aliases", [])
    if not isinstance(aliases, list) or any(not isinstance(alias, str) for alias in aliases):
        raise ValueError("reference aliases must be strings")
    try:
        result = json.loads(json.dumps(entry, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise ValueError("reference provenance must contain only finite JSON data") from exc
    return result


def _entries_from_database() -> list[dict[str, Any]] | None:
    """Read an explicitly configured existing repository, with no seed writes."""
    config = sys.modules.get("mmfdb.config")
    if config is None:
        if not any(os.environ.get(key) for key in ("MMFDB_DATABASE_PATH", "MMFDB_DATABASE_URL")):
            return None
        try:
            config = importlib.import_module("mmfdb.config")
        except ModuleNotFoundError as exc:
            if exc.name == "mmfdb" or (exc.name or "").startswith("mmfdb."):
                raise ReferenceSourceUnavailable("configured MMFDB package is absent") from exc
            raise

    location = config.configured_database_url() or config.configured_database_path()
    if location is None:
        return None
    from mmfdb.repository import MFDatabase
    from mmfdb.store.sql_backend import parse_database_target

    target = parse_database_target(location)
    if target.is_sqlite and target.location != ":memory:" and not Path(target.location).is_file():
        raise ReferenceSourceUnavailable("configured MMFDB reference database is absent")
    with MFDatabase(target.location, readonly=True) as db:
        return db.get_diffusion_reference(seed_if_empty=False)


def _entries_from_package() -> list[dict[str, Any]]:
    """Read ChiSurf's exact versioned reference export, without optional assets."""
    root = Path(__file__).parent
    origin = json.loads((root / "reference_diffusion.origin.json").read_text(encoding="utf-8"))
    raw = (root / "reference_diffusion.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != origin["sha256"]:
        raise ValueError("portable reference export does not match its origin manifest")
    entries = json.loads(raw)
    return [
        validate_reference(
            {
                **entry,
                "probe_id": None,
                "source": "reference_diffusion",
                "unit": origin["unit"],
                "reference_origin": origin,
            }
        )
        for entry in entries
    ]


def _load() -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Build display-name and alias maps while retaining actual source values."""
    portable = _entries_from_package()
    entries = _entries_from_database()
    if entries is None:
        entries = portable
    dyes = {entry["name"]: validate_reference(entry) for entry in entries}
    aliases = {_normalized(name): name for name in dyes}
    for entry in [*portable, *entries]:
        canonical = aliases.get(_normalized(entry["name"]))
        if canonical is not None:
            for alias in entry.get("aliases", []):
                aliases.setdefault(_normalized(alias), canonical)
                recorded = dyes[canonical].setdefault("aliases", [])
                if alias not in recorded:
                    recorded.append(alias)
    return dyes, aliases


def reference_dyes(refresh: bool = False) -> dict[str, dict[str, Any]]:
    """Return source entries in um²/s at 25 °C in water, detached from the cache.

    Parameters
    ----------
    refresh : bool, optional
        Re-read the configured source rather than its process lookup cache.

    Returns
    -------
    dict
        Species names mapped to scientific inputs and literature provenance.
    """
    global _CACHE, _ALIASES
    if refresh or _CACHE is None:
        _CACHE, _ALIASES = _load()
    return copy.deepcopy(_CACHE)


def dye_names(refresh: bool = False) -> list[str]:
    """Return sorted available reference names for selection controls."""
    return sorted(reference_dyes(refresh=refresh))


def get_dye(name: str) -> dict[str, Any] | None:
    """Look up a display name or legacy alias without normalizing source IDs.

    Parameters
    ----------
    name : str
        Reference species name or alias.

    Returns
    -------
    dict or None
        Detached scientific entry, or None for an unknown species.
    """
    dyes = reference_dyes()
    if name in dyes:
        return dyes[name]
    canonical = (_ALIASES or {}).get(_normalized(name))
    return dyes.get(canonical) if canonical is not None else None


def diffusion_coefficient_25C(name: str) -> float:
    """Return D(25 °C, water) in um²/s, or NaN for an unknown species."""
    entry = get_dye(name)
    return float(entry["d25_um2_s"]) if entry else float("nan")
