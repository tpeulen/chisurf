"""Fetch structures from the RCSB, with an on-disk cache.

Library code, not plugin code: the FPS JSON editor, QuEst and anything else that
accepts a bare four-character PDB ID needs exactly this, and a plugin cannot be
imported by another plugin without coupling the two through the host's plugin
tree.

Both PDB and mmCIF are handled — large entries have no PDB file at all, so a 404
on ``.pdb`` falls through to ``.cif`` rather than failing.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

__all__ = [
    "PDB_ID_RE",
    "RCSB_PDB_URL_TEMPLATE",
    "RCSB_CIF_URL_TEMPLATE",
    "default_cache_dir",
    "is_pdb_id",
    "normalize_pdb_id",
    "pdb_source_url",
    "download_structure",
]

PDB_ID_RE = re.compile(r"^[A-Za-z0-9]{4}$")
RCSB_PDB_URL_TEMPLATE = "https://files.rcsb.org/download/{pdb_id}.pdb"
RCSB_CIF_URL_TEMPLATE = "https://files.rcsb.org/download/{pdb_id}.cif"

_USER_AGENT = "ChiSurf structure fetch"


def is_pdb_id(value: object) -> bool:
    """Whether *value* looks like a bare RCSB identifier."""
    return isinstance(value, str) and PDB_ID_RE.fullmatch(value.strip()) is not None


def normalize_pdb_id(pdb_id: str) -> str:
    """Normalise and validate a four-character RCSB PDB ID."""
    if not isinstance(pdb_id, str):
        raise ValueError("pdb_id must be a string")
    normalized = pdb_id.strip().lower()
    if not PDB_ID_RE.fullmatch(normalized):
        raise ValueError("pdb_id must be a four-character RCSB PDB ID")
    return normalized


def default_cache_dir() -> Path:
    """Where downloaded structures are kept."""
    return Path.home() / ".chisurf" / "structures"


def pdb_source_url(pdb_id: str) -> str:
    """The RCSB download URL for a PDB ID."""
    return RCSB_PDB_URL_TEMPLATE.format(pdb_id=normalize_pdb_id(pdb_id))


def _download(url: str) -> bytes | None:
    """Return the body, or ``None`` when the entry is absent (404)."""
    request = Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urlopen(request, timeout=30) as response:
            return response.read()
    except HTTPError as exc:
        if exc.code == 404:
            return None
        raise RuntimeError(f"RCSB returned {exc.code} for {url}") from exc
    except URLError as exc:
        raise RuntimeError(f"Failed to download {url}: {exc}") from exc


def download_structure(
    pdb_id: str,
    output_dir: str | Path | None = None,
    cache_dir: Path | None = None,
) -> Path:
    """Download *pdb_id* from RCSB and return the cached file path.

    A cached file is returned untouched. ``.pdb`` is tried first, then ``.cif``.

    Raises
    ------
    ValueError
        If *pdb_id* is not a four-character identifier.
    FileNotFoundError
        If RCSB has neither a PDB nor an mmCIF file for it.
    RuntimeError
        On any other transport failure.
    """
    normalized_id = normalize_pdb_id(pdb_id)
    target_dir = Path(output_dir) if output_dir else (cache_dir or default_cache_dir())

    for suffix, template in (
        (".pdb", RCSB_PDB_URL_TEMPLATE),
        (".cif", RCSB_CIF_URL_TEMPLATE),
    ):
        cached = target_dir / f"{normalized_id}{suffix}"
        if cached.exists() and cached.stat().st_size > 0:
            return cached

    target_dir.mkdir(parents=True, exist_ok=True)
    for suffix, template in (
        (".pdb", RCSB_PDB_URL_TEMPLATE),
        (".cif", RCSB_CIF_URL_TEMPLATE),
    ):
        data = _download(template.format(pdb_id=normalized_id))
        if data is None:
            continue
        if not data.strip():
            raise RuntimeError(f"RCSB returned an empty file for {normalized_id!r}")
        target_path = target_dir / f"{normalized_id}{suffix}"
        target_path.write_bytes(data)
        return target_path

    raise FileNotFoundError(f"PDB ID not found at RCSB: {normalized_id}")


# Backwards-compatible alias for the FPS JSON editor's original name.
download_pdb_file = download_structure
