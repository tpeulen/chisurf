"""Burstwise → PTO Converter Plugin.

Imports legacy burstwise analysis folders (bi4_bur/bg4/br4/BIDs/Info/.mti)
into .mmfdb.pto containers.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from chisurf.core.fio.fluorescence.burstwise_import import (
    BurstwiseImportError,
    ImportReport,
    convert_folder,
    dictionary_columns,
    parse_info,
    parse_mti,
    read_legacy_table,
    rename_columns,
    scan_folder,
)
from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
    icon = _manifest.icon or "📥"
else:
    name = "File:Data:Burstwise→PTO"
    icon = "📥"


def create_mti_resolver(
    old_prefix: str, new_prefix: str
) -> Callable[[str, dict[str, float]], Path | None]:
    """Resolve raw TTTR from .mti paths by replacing old root prefix with local root prefix.

    Parameters
    ----------
    old_prefix : str
        Old root prefix recorded in .mti (e.g. ``N:\\``).
    new_prefix : str
        Local directory path replacing the old prefix.

    Returns
    -------
    Callable[[str, dict[str, float]], Path | None]
    """
    old_clean = old_prefix.strip().replace("\\", "/").rstrip("/")
    new_path = Path(new_prefix.strip()).expanduser().resolve()

    def resolver(stem: str, mti: dict[str, float]) -> Path | None:
        norm_stem = stem.lower()
        matching_key = None
        for key in mti:
            p_name = key.replace("\\", "/").split("/")[-1]
            if Path(p_name).stem.lower() == norm_stem:
                matching_key = key
                break
        if not matching_key:
            for key in mti:
                if norm_stem in key.lower():
                    matching_key = key
                    break
        if not matching_key:
            return None

        key_norm = matching_key.replace("\\", "/")
        if old_clean and key_norm.lower().startswith(old_clean.lower()):
            rel = key_norm[len(old_clean) :].lstrip("/")
        elif old_clean and (":/" in key_norm or ":\\" in matching_key):
            drive_stripped = (
                re.sub(r"^[a-zA-Z]:[/|\\]+", "", matching_key).replace("\\", "/").lstrip("/")
            )
            rel = drive_stripped
        else:
            rel = key_norm.lstrip("/")

        cand = new_path / rel
        if cand.is_file():
            return cand
        if cand.parent.is_dir():
            for ext in (".ht3", ".spc", ".ptu", ".pt3", ".phu", ".t3r", ".ht2"):
                alt = cand.parent / f"{cand.stem}{ext}"
                if alt.is_file():
                    return alt
        return None

    return resolver


def create_beside_resolver(
    folder: str | Path,
) -> Callable[[str, dict[str, float]], Path | None]:
    """Match <stem>.ht3/.spc/.ptu next to the burstwise folder.

    Parameters
    ----------
    folder : str or Path
        The burstwise analysis directory.

    Returns
    -------
    Callable[[str, dict[str, float]], Path | None]
    """
    base_dir = Path(folder).expanduser().resolve().parent

    def resolver(stem: str, mti: dict[str, float]) -> Path | None:
        for ext in (".ht3", ".spc", ".ptu", ".pt3", ".phu", ".t3r", ".ht2"):
            cand = base_dir / f"{stem}{ext}"
            if cand.is_file():
                return cand
        return None

    return resolver


__all__ = [
    "BurstwiseImportError",
    "ImportReport",
    "convert_folder",
    "create_beside_resolver",
    "create_mti_resolver",
    "dictionary_columns",
    "icon",
    "name",
    "parse_info",
    "parse_mti",
    "read_legacy_table",
    "rename_columns",
    "scan_folder",
]
