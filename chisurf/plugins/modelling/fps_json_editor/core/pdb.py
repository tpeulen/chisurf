"""PDB helpers for the FPS JSON Editor.

The RCSB fetch moved to :mod:`chisurf.core.fio.structure.fetch` — it is library
code, wanted by QuEst as well, and a plugin cannot be imported by another
plugin. This module re-exports it so the plugin's own imports keep working.
"""

from __future__ import annotations

from chisurf.core.fio.structure.fetch import (  # noqa: F401
    RCSB_PDB_URL_TEMPLATE,
    default_cache_dir as _shared_cache_dir,
    download_pdb_file,
    download_structure,
    pdb_source_url,
)
from pathlib import Path

__all__ = [
    "RCSB_PDB_URL_TEMPLATE",
    "default_cache_dir",
    "pdb_source_url",
    "download_pdb_file",
    "download_structure",
]


def default_cache_dir() -> Path:
    """The editor's own cache location, kept for continuity."""
    return Path.home() / ".chisurf" / "fps_json_editor" / "pdb"
