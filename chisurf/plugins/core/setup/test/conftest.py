"""Keep this directory runnable on its own (offscreen Qt for the few tests that build the Qt reference)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pathlib

import pytest

_REAL_ROOT = pathlib.Path.home() / ".chisurf"
#: Written by every chisurf process, not settings: session logs and the bytecode cache (``PYTHONPYCACHEPREFIX``).
_IGNORED = {"logs", "cache"}


def real_settings_state() -> dict:
    """``{path: (size, mtime)}`` of the user's real ``~/.chisurf`` without its logs and bytecode cache."""
    state = {}
    if _REAL_ROOT.exists():
        for dirpath, dirs, files in os.walk(_REAL_ROOT):
            dirs[:] = [d for d in dirs if not (pathlib.Path(dirpath) == _REAL_ROOT and d in _IGNORED)]
            for name in files:
                path = pathlib.Path(dirpath) / name
                try:
                    stat = path.stat()
                except OSError:
                    continue
                state[str(path)] = (stat.st_size, stat.st_mtime_ns)
    return state


@pytest.fixture(autouse=True)
def real_settings_untouched():
    """The user's real ``~/.chisurf`` (apart from logs and bytecode) is exactly as it was after every test."""
    before = real_settings_state()
    yield
    assert real_settings_state() == before, "a test touched the real ~/.chisurf"
