"""Structure source resolution helpers."""

from __future__ import annotations

import os
import re
import tempfile
import urllib.error
import urllib.request
from pathlib import Path


PDB_ID_RE = re.compile(r"^[A-Za-z0-9]{4}$")
RCSB_PDB_URL = "https://files.rcsb.org/download/{pdb_id}.pdb"
RCSB_CIF_URL = "https://files.rcsb.org/download/{pdb_id}.cif"


def is_pdb_id(value: object) -> bool:
    """Return True when *value* looks like a bare RCSB PDB identifier."""

    if not isinstance(value, str):
        return False
    return PDB_ID_RE.fullmatch(value.strip()) is not None


def default_pdb_cache_dir() -> Path:
    """Return the cache directory for downloaded PDB files."""

    return Path(os.getenv("QUEST_PDB_CACHE_DIR", Path(tempfile.gettempdir()) / "quest-pdb-cache"))


def _shared_downloader():
    """ChiSurf's shared RCSB fetch, when the host is reachable.

    Downloading a structure by accession is library work, and ChiSurf carries it
    in `chisurf.core.fio.structure.fetch` — the same code its FPS JSON editor
    uses. QuEst prefers that copy so there is one cache and one retry policy,
    and keeps its own only for running without a host.
    """
    try:
        from chisurf.core.fio.structure.fetch import download_structure
    except Exception:
        return None
    return download_structure


def download_pdb_id(pdb_id: str, cache_dir: Path | str | None = None) -> Path:
    """Download *pdb_id* from RCSB and return the cached structure path.

    Delegates to ChiSurf's shared fetch when the host is available; the local
    implementation below is the standalone fallback.
    """

    shared = _shared_downloader()
    if shared is not None:
        target_dir = Path(cache_dir) if cache_dir is not None else default_pdb_cache_dir()
        return Path(shared(pdb_id, cache_dir=target_dir))

    clean_id = pdb_id.strip().upper()
    if not is_pdb_id(clean_id):
        raise ValueError(f"Invalid PDB ID: {pdb_id!r}")

    target_dir = Path(cache_dir) if cache_dir is not None else default_pdb_cache_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    pdb_target = target_dir / f"{clean_id.lower()}.pdb"
    cif_target = target_dir / f"{clean_id.lower()}.cif"
    for target in (pdb_target, cif_target):
        if target.exists() and target.stat().st_size > 0:
            return target

    for url_template, target in ((RCSB_PDB_URL, pdb_target), (RCSB_CIF_URL, cif_target)):
        url = url_template.format(pdb_id=clean_id)
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                content = response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                continue
            raise RuntimeError(f"Failed to download PDB ID {clean_id}: HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Failed to download PDB ID {clean_id}: {exc.reason}") from exc

        if not content:
            raise RuntimeError(f"Downloaded PDB ID {clean_id} returned an empty file.")

        target.write_bytes(content)
        return target

    raise FileNotFoundError(f"PDB ID not found at RCSB: {clean_id}")


def resolve_structure_path(source: Path | str, cache_dir: Path | str | None = None) -> Path:
    """Resolve a local structure path or download a bare PDB ID."""

    if isinstance(source, Path):
        path = source.expanduser()
        if path.exists():
            return path
        source_text = str(source)
    else:
        source_text = str(source).strip()
        path = Path(source_text).expanduser()
        if path.exists():
            return path

    if is_pdb_id(source_text):
        return download_pdb_id(source_text, cache_dir=cache_dir)

    raise FileNotFoundError(f"Structure path does not exist: {path}")
