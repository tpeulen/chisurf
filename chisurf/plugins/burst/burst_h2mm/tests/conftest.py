"""Hermetic settings for every test of this plugin, and a guard on the user's real ``~/.chisurf``.

* ``CHISURF_SETTINGS_DIR``, ``MMFDB_SETTINGS_DIR``, ``MMFDB_DATABASE_PATH`` and ``HOME`` point into the test's temp
  folder, so no test reads or writes the user's settings, keyring or database.
* A module-scoped guard lists the real ``~/.chisurf`` (the home found in the password database, not ``$HOME``)
  before the first test of a module and after the last one: any file added, removed or changed fails the module.
  ``~/.chisurf/logs`` is ignored (the logging set-up appends there by design).
"""

from __future__ import annotations

import os
import pwd
from pathlib import Path

import pytest

REAL_CHISURF = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".chisurf"


def _listing() -> dict[str, tuple[int, int]]:
    found: dict[str, tuple[int, int]] = {}
    if not REAL_CHISURF.is_dir():
        return found
    for path in REAL_CHISURF.rglob("*"):
        rel = path.relative_to(REAL_CHISURF)
        if (rel.parts and rel.parts[0] == "logs") or "__pycache__" in rel.parts:
            continue
        try:
            if not path.is_file():  # a directory's mtime moves when a lock file comes and goes
                continue
            stat = path.stat()
        except OSError:
            continue
        found[str(rel)] = (stat.st_size, stat.st_mtime_ns)
    return found


@pytest.fixture(scope="module", autouse=True)
def real_chisurf_untouched():
    before = _listing()
    yield
    after = _listing()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    assert not changed, f"the tests touched the real ~/.chisurf: {changed[:10]}"


@pytest.fixture(autouse=True)
def hermetic_settings(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    yield
