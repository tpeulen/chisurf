"""Fixtures that keep an emtk plugin test off the user's real ChiSurf and MMFDB state.

Import both into a test module (``from chisurf.plugins.emtk_hermetic import hermetic, real_chisurf_untouched``): the first
points ``HOME`` and the settings / database environment at a temporary folder for every test, the second fails the
module if anything in the real ``~/.chisurf`` (apart from ``logs``, which every ChiSurf process writes) changed.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

REAL_CHISURF = Path(os.path.expanduser("~")) / ".chisurf"


def snapshot(root: Path) -> dict:
    """``{path: (size, mtime_ns)}`` under *root*, ignoring ``logs`` and bytecode."""
    out = {}
    if not root.exists():
        return out
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if rel.parts and rel.parts[0] == "logs" or "__pycache__" in rel.parts:
            continue
        stat = path.stat()
        out[str(rel)] = (stat.st_size, stat.st_mtime_ns)
    return out


@pytest.fixture(scope="module", autouse=True)
def real_chisurf_untouched():
    """Nothing in the real ``~/.chisurf`` (apart from ``logs``) changes while the module runs."""
    before = snapshot(REAL_CHISURF)
    yield
    assert snapshot(REAL_CHISURF) == before


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    """Temporary HOME, settings folder and metadata database for one test."""
    for name in ("settings", "mmfdb", "home"):
        (tmp_path / name).mkdir()
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return tmp_path
