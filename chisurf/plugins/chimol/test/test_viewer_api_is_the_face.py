"""``core/api.py::ViewerAPI`` is the face: every name commands and plugins use on ``viewer.`` is declared there.

Two directions: a name used but not declared is a new dependency a plugin
author cannot see (add it to the Protocol, deliberately); a name declared
but no longer used is a stale promise (delete it). And every declared name
exists on the real Viewer.
"""
from __future__ import annotations

import pathlib
import re

import chimol
from chimol.core.api import ViewerAPI

ROOT = pathlib.Path(chimol.__file__).resolve().parent

#: Speculative calls guarded by try/except AttributeError -- not part of the face.
SPECULATIVE = {"save_png", "set_all_atom_coords", "selection_mode", "device"}
_ATTR = re.compile(r"\b(?:viewer|ctx\.viewer|self\.viewer|self\._viewer)\.([a-zA-Z]\w*)")
_GETATTR = re.compile(r'getattr\((?:viewer|ctx\.viewer|self\.viewer|self\._viewer), "([a-zA-Z]\w*)"')


def _used() -> set[str]:
    out: set[str] = set()
    for scope in ("commands", "plugins"):
        for path in (ROOT / scope).rglob("*.py"):
            text = path.read_text()
            out.update(_ATTR.findall(text))
            out.update(_GETATTR.findall(text))
    out.discard("Viewer")
    return out - SPECULATIVE


def _declared() -> set[str]:
    names = set(getattr(ViewerAPI, "__annotations__", {}))
    names |= {n for n in vars(ViewerAPI) if not n.startswith("_") and n not in ("__protocol_attrs__",)}
    return names


def test_every_used_name_is_declared():
    missing = sorted(_used() - _declared())
    assert not missing, f"used on viewer but not in ViewerAPI: {missing}"


def test_every_declared_name_is_used():
    stale = sorted(_declared() - _used())
    assert not stale, f"declared in ViewerAPI but no caller: {stale}"


def test_every_declared_name_exists_on_the_viewer():
    from chimol.core.viewer import Viewer

    absent = sorted(n for n in _declared() if not hasattr(Viewer, n) and n not in ("bus", "objects", "playback", "renderer", "movie_step", "movie_interpolate"))
    assert not absent, absent
