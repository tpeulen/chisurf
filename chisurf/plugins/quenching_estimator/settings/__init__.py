"""Access to the shipped settings data: the parameter catalog and dye library.

These JSON files are package data, so they are resolved relative to this
module rather than to the current working directory or a guessed repository
root — that is what makes them readable from an installed wheel, a frozen
desktop bundle, or a host application that loaded QuEst as a plugin.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, MutableMapping

__all__ = [
    "SETTINGS_DIR",
    "PARAMETER_CATALOG_PATH",
    "DYE_REPOSITORY_PATH",
    "parameter_catalog",
    "dye_repository",
    "save_dye",
    "quenching_defaults",
]

SETTINGS_DIR = Path(__file__).resolve().parent
PARAMETER_CATALOG_PATH = SETTINGS_DIR / "parameter_catalog.json"
DYE_REPOSITORY_PATH = SETTINGS_DIR / "dye_repository.json"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing QuEst settings file: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def parameter_catalog() -> dict[str, Any]:
    """Return the parameter catalog — the single source of parameter help text.

    The same document drives the web UI's labels and tooltips and the generated
    ``doc/parameters.md``.
    """

    return _read_json(PARAMETER_CATALOG_PATH)


def _with_stickiness_defaults(dye: Mapping[str, Any]) -> dict[str, Any]:
    from chisurf.plugins.quenching_estimator.core.dye_diffusion import normalize_amino_acid_interactions

    normalized = dict(dye)
    normalized.setdefault("slow_radius", 8.5)
    normalized["amino_acid_interactions"] = dict(
        normalize_amino_acid_interactions(normalized.get("amino_acid_interactions"))
    )
    return normalized


def dye_repository(*, with_defaults: bool = True) -> dict[str, Any]:
    """Return the dye presets, keyed by dye name.

    Parameters
    ----------
    with_defaults : bool
        Fill in the stickiness fields (``slow_radius``,
        ``amino_acid_interactions``) that a preset may omit, so every entry is
        complete before it reaches the simulation.
    """

    dyes = _read_json(DYE_REPOSITORY_PATH)
    if not with_defaults:
        return dyes
    return {
        name: _with_stickiness_defaults(dye) if isinstance(dye, dict) else dye
        for name, dye in dyes.items()
    }


def save_dye(dye: Mapping[str, Any]) -> MutableMapping[str, Any]:
    """Add or replace one dye in the repository and return the stored entry.

    Raises
    ------
    ValueError
        If the dye carries no ``name``; the name is its key.
    """

    name = str(dye.get("name") or "").strip()
    if not name:
        raise ValueError("A dye must define a non-empty 'name'.")

    dyes = _read_json(DYE_REPOSITORY_PATH) if DYE_REPOSITORY_PATH.exists() else {}
    entry = _with_stickiness_defaults(dye)
    entry["name"] = name
    dyes[name] = entry
    DYE_REPOSITORY_PATH.write_text(
        json.dumps(dyes, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return entry


def quenching_defaults() -> dict[str, Any]:
    """Return the residue-type chemistry that makes quenching amino-acid specific."""

    from chisurf.plugins.quenching_estimator.core.dye_diffusion import (
        DEFAULT_QUENCHER_ATOMS,
        REFERENCE_PET_QUENCHING,
        STANDARD_AMINO_ACID_RESIDUES,
        normalize_amino_acid_interactions,
    )

    return {
        "residues": list(STANDARD_AMINO_ACID_RESIDUES),
        "default_interactions": dict(normalize_amino_acid_interactions()),
        "default_quench_atoms": {
            residue: list(atoms) for residue, atoms in DEFAULT_QUENCHER_ATOMS.items()
        },
        "reference_pet_quenching": dict(REFERENCE_PET_QUENCHING),
    }
