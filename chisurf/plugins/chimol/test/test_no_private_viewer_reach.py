"""The command layer and the plugins use the viewer's public face, not its privates.

``viewer._objects`` (71 sites), ``viewer._update_view`` (52), ``_renderer._internal_gui``
and friends were how the commands drove the viewer; a plugin written that way
breaks whenever the viewer's insides move -- which is what the service split
does. They are ``viewer.objects``, ``viewer.update_view()``, ``viewer.gui``,
``viewer.playback``, ``viewer.measurements`` now, and this test keeps the
remaining private reaches to a **listed, shrinking** set: a name may leave the
list when it gets a public door; a new one may not appear.
"""
from __future__ import annotations

import pathlib
import re

import pytest

import chimol

ROOT = pathlib.Path(chimol.__file__).resolve().parent
SCOPES = ("commands", "plugins")

#: What still reaches a private, and why it may (for now).
ALLOWED = {
    # the per-object representation flags, until the representation registry (plan §3.3)
    "_show_atoms", "_show_cartoon", "_show_lines", "_show_nonbonded", "_show_sticks",
    "_show_surface", "_show_trace",
    # object-state readers the ViewerAPI will name (plan §3.2)
    "_get_active_state", "_select_state_frame", "_scale_factor", "_selected_residues",
    "_selected_atoms", "_atoms", "_all_atom_coords", "_raw_center", "_residue_ids",
    "_scene", "_window", "_info_visible", "_request_chrome_redraw",
}

_ATTR = re.compile(r"\b(?:viewer|self\.viewer|self\._viewer|ctx\.viewer)\.(_[a-zA-Z]\w*)")
_GETATTR = re.compile(r"getattr\((?:viewer|self\.viewer|self\._viewer|ctx\.viewer), \"(_[a-zA-Z]\w*)\"")


def _reaches() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for scope in SCOPES:
        for path in sorted((ROOT / scope).rglob("*.py")):
            text = path.read_text()
            for pattern in (_ATTR, _GETATTR):
                for name in pattern.findall(text):
                    found.setdefault(name, set()).add(str(path.relative_to(ROOT)))
    return found


def test_only_the_listed_privates_are_reached():
    found = _reaches()
    new = {n: sorted(f) for n, f in found.items() if n not in ALLOWED}
    assert not new, f"new private viewer reach(es) in commands/plugins: {new}"


def test_the_allowlist_only_shrinks():
    found = _reaches()
    stale = sorted(n for n in ALLOWED if n not in found)
    assert not stale, f"delete from ALLOWED (no longer reached): {stale}"


@pytest.fixture
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_the_public_doors_exist(qapp):
    from chimol.core.viewer import MolView

    view = MolView()
    try:
        for name in ("objects", "update_view", "gui", "renderer", "playback", "measurements",
                     "activate_object", "create_object", "end_scrub"):
            assert hasattr(view, name), name
    finally:
        view.deleteLater()
