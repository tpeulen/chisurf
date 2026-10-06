"""Every test here runs on temporary settings and a temporary HOME, and proves the real ~/.chisurf was not touched."""

import os
import pwd
import time
from pathlib import Path

import pytest

REAL_CHISURF = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".chisurf"


def _snapshot() -> dict:
    """Every file under the real ~/.chisurf (apart from its logs) with its size and mtime."""
    out = {}
    if REAL_CHISURF.exists():
        for path in REAL_CHISURF.rglob("*"):
            if {"logs", "cache"} & set(path.relative_to(REAL_CHISURF).parts):
                continue  # logs, and the bytecode cache concurrent sessions write
            try:
                st = path.stat()
            except OSError:
                continue
            out[str(path)] = (st.st_size, st.st_mtime_ns)
    return out


@pytest.fixture(autouse=True)
def hermetic_user_settings(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    monkeypatch.setenv("HOME", str(home))
    before = _snapshot()
    yield
    assert _snapshot() == before, "a test touched the real ~/.chisurf"


@pytest.fixture
def no_failed_draws(caplog):
    yield
    bad = [r.getMessage() for r in caplog.records if r.levelno >= 40]
    assert not bad, bad[:3]
