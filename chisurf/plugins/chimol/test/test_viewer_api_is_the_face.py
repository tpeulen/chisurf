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
from toolkit_free import probe

ROOT = pathlib.Path(chimol.__file__).resolve().parent

#: Names probed with ``getattr(viewer, name, default)`` because they belong to
#: *some* hosts and not to the viewer -- an optional capability, not the face.
#:
#: This held four names and hid two dead branches. `save_png` and
#: `set_all_atom_coords` were called inside a `try`, raised `AttributeError` on
#: every host because no viewer has ever had either, and the `except` clause was
#: the implementation -- so the product always took the fallback while the tests
#: took the branch. Both calls are gone. `selection_mode` was in here too and is
#: simply a real attribute of every viewer, now declared in `ViewerAPI` like any
#: other. An exemption list that nobody can add to without proving the name is
#: absent is the point of `test_an_exemption_has_to_earn_its_place` below.
SPECULATIVE = {"device"}
_ATTR = re.compile(r"\b(?:viewer|ctx\.viewer|self\.viewer|self\._viewer)\.([a-zA-Z]\w*)")
_GETATTR = re.compile(
    r'getattr\((?:viewer|ctx\.viewer|self\.viewer|self\._viewer), "([a-zA-Z]\w*)"'
)


def _used() -> set[str]:
    out: set[str] = set()
    for scope in ("commands", "plugins", "ui/wizards"):
        for path in (ROOT / scope).rglob("*.py"):
            text = path.read_text()
            out.update(_ATTR.findall(text))
            out.update(_GETATTR.findall(text))
    out.discard("Viewer")
    return out - SPECULATIVE


def _declared() -> set[str]:
    names = set(getattr(ViewerAPI, "__annotations__", {}))
    names |= {
        n for n in vars(ViewerAPI) if not n.startswith("_") and n not in ("__protocol_attrs__",)
    }
    return names


def test_every_used_name_is_declared():
    missing = sorted(_used() - _declared())
    assert not missing, f"used on viewer but not in ViewerAPI: {missing}"


def test_every_declared_name_is_used():
    stale = sorted(_declared() - _used())
    assert not stale, f"declared in ViewerAPI but no caller: {stale}"


_HASATTR = re.compile(
    r'hasattr\(\s*(?:viewer|ctx\.viewer|self\.viewer|self\._viewer)\s*,\s*"([a-zA-Z]\w*)"'
)


def test_nobody_asks_whether_a_declared_name_exists():
    """A declared name is there. Asking is a branch nothing can run.

    Six of these stood in the command layer -- `turn`, `move`, `clip`, `undo`,
    `create_object`, `apply_transform_to_object` -- each an `if not hasattr(...)
    : return`, so the command they guarded would have done nothing and said
    nothing had the guard ever fired. It could not: all six are declared in
    `ViewerAPI` and present on every viewer. What they actually tracked was a
    partial test double, which is the wrong way round -- the double is what
    should follow the face.

    An *optional* name is different, and is spelled `getattr(viewer, name,
    default)`; those are listed in `SPECULATIVE` above and must be absent from
    the viewer, which the next test checks.
    """
    offenders = {}
    declared = _declared()
    for scope in ("commands", "plugins", "ui/wizards"):
        for path in (ROOT / scope).rglob("*.py"):
            asked = [n for n in _HASATTR.findall(path.read_text()) if n in declared]
            if asked:
                offenders[str(path.relative_to(ROOT))] = sorted(set(asked))
    assert not offenders, f"declared in ViewerAPI and still probed for: {offenders}"


def test_an_exemption_has_to_earn_its_place():
    """A name is exempt only while it is optional *and* still called.

    Otherwise the list outlives its reasons, which is what happened: two of its
    four entries named methods that had been dead for as long as they had
    existed, and a third named an ordinary attribute. Both failure modes are
    checked here -- absent from the viewer, and still used by somebody.
    """
    from chimol.core.viewer import Viewer

    used = _used() | SPECULATIVE  # `_used` subtracts them; add them back
    for name in SPECULATIVE:
        assert not hasattr(Viewer, name), (
            f"{name} is a real attribute of the viewer: declare it in ViewerAPI "
            f"rather than exempting it"
        )
        assert name in used, f"{name} is exempt but nothing calls it any more"
        hits = [
            path
            for scope in ("commands", "plugins", "ui/wizards")
            for path in (ROOT / scope).rglob("*.py")
            if f'"{name}"' in path.read_text() and "getattr(" in path.read_text()
        ]
        assert hits, f"{name} is exempt but is not probed with a getattr default"


def test_every_declared_name_exists_on_the_viewer():
    """The methods, on the class. The data attributes are not class attributes.

    `ViewerAPI` already says which is which -- a name in `__annotations__` is a
    data attribute, written in `Viewer.__init__` and therefore absent from the
    class -- so the two are asked different questions. They used to be asked
    the same one, with the data attributes listed by hand beside it; that list
    had six of them and went stale the moment a seventh was declared.
    """
    from chimol.core.viewer import Viewer

    data = set(getattr(ViewerAPI, "__annotations__", {}))
    absent = sorted(n for n in _declared() - data if not hasattr(Viewer, n))
    assert not absent, f"declared in ViewerAPI but not on the Viewer: {absent}"


def test_every_declared_data_attribute_exists_on_a_real_viewer():
    """The other half, and it needs a viewer that has actually been built.

    A data attribute is written in `__init__`, so the class cannot answer for
    it and the check above deliberately does not ask. Asking nothing is how a
    declared attribute that no viewer carries would sit in the face unnoticed,
    so it is asked here, of a running one.
    """
    declared = sorted(getattr(ViewerAPI, "__annotations__", {}))
    written = probe(
        "app = open_app(size=(320, 240))\n"
        f"missing = [n for n in {declared!r} if not hasattr(app.viewer, n)]\n"
        "emit('missing', ','.join(missing))\n"
    )
    assert written["missing"] == "", (
        f"declared in ViewerAPI but absent from a built viewer: {written['missing']}"
    )
