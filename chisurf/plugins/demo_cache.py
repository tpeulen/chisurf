"""The settings-owned cache every plugin demo writes into, and the stamp that says it is still good.

A demo (``demo.py`` beside a plugin) simulates a small known data set. Writing it again on every press of
*Load example* would be slow and would change file times under a tool that watches them, so the files are
kept under ``<settings>/demos/<plugin>`` with a stamp (``demo.meta.json``) recording the demo parameters and
a checksum per file. :func:`is_current` is true only while both still match.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

STAMP = "demo.meta.json"


def cache_folder(plugin: str) -> Path:
    """Return the cache directory of *plugin*'s demo (not created)."""
    from chisurf.core.settings.path_utils import get_path

    return get_path("settings") / "demos" / plugin


def _digest(path: Path) -> str:
    """Return the SHA-256 of *path*."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_current(folder: Path, names: Iterable[str], demo: dict[str, Any]) -> bool:
    """Say whether *names* in *folder* are the files written for exactly these *demo* parameters."""
    try:
        stamp = json.loads((folder / STAMP).read_text(encoding="utf-8"))
        return stamp.get("demo") == json.loads(json.dumps(demo)) and stamp.get("sha256") == {
            name: _digest(folder / name) for name in names
        }
    except (OSError, ValueError):
        return False


def record(folder: Path, names: Iterable[str], demo: dict[str, Any]) -> None:
    """Stamp *names* in *folder* as written for these *demo* parameters."""
    (folder / STAMP).write_text(
        json.dumps(
            {"demo": demo, "sha256": {n: _digest(folder / n) for n in names}}, sort_keys=True
        ),
        encoding="utf-8",
    )
