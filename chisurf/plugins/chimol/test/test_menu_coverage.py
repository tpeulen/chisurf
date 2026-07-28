"""Every representation must be reachable from the menus, and the plane readable.

Two findings from a sweep of all 17 buttons on the main window plus the menu
tables:

* **``trace``, ``nonbonded`` and ``metaball`` were reachable only from the
  toolbar.** A menu-driven session could not get at them at all, which defeats
  the point of the menus. ``metaball`` is a ChiMOL representation PyMOL has no
  equivalent for, so it is exactly the kind of thing a PyMOL user would never
  think to look for on a toolbar;
* **the reference plane was an aliased grey sheet.** ``_grid_spacing`` is 1.0 in
  *scene* units while a protein's radius is a couple of hundred, so it drew ~415
  lines each way and buried the molecule. The spacing now follows the extent.

A note on how the sweep itself misled twice, which is why these tests assert what
they do. A scene signature counting only *vertices* reported every colour button
as having no effect — a recolour changes no geometry. And ``button_plane``
reported no effect under offscreen Qt, where there is no GL context at all; with a
real window it drew, far too much of it.
"""

from __future__ import annotations

import pathlib

import pytest

from chisurf.plugins.chimol.chimol import object_menus as om
from chisurf.plugins.chimol.chimol.cmd.command import Cmd

_FRAGMENT = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "solvated_fragment.pdb"
)

#: PyMOL spells the atom representation ``spheres`` in its menus, so the internal
#: name never appears there and its absence is not a gap.
_SPELLED_DIFFERENTLY = {"atoms": "spheres"}


def _commands(entries, out=None):
    out = [] if out is None else out
    for entry in entries:
        if getattr(entry, "is_submenu", False):
            _commands(entry.children, out)
        elif entry.command:
            out.append(entry.command)
    return out


def _verbs(entries, verb):
    return {
        command.split(",")[0].replace(f"{verb} ", "").strip()
        for command in _commands(entries)
        if command.startswith(f"{verb} ")
    }


# --------------------------------------------------------------------------- #
# Menu coverage
# --------------------------------------------------------------------------- #
def test_every_representation_can_be_shown_from_the_menu():
    """Including the ones ChiMOL has and PyMOL does not."""
    shown = _verbs(om.SHOW_MENU, "show")
    missing = [
        rep for rep in Cmd._ALL_REPRESENTATIONS
        if rep not in shown and _SPELLED_DIFFERENTLY.get(rep) not in shown
    ]
    assert not missing, f"not reachable from the S menu: {missing}"


def test_every_representation_can_be_hidden_from_the_menu():
    hidden = _verbs(om.HIDE_MENU, "hide")
    missing = [
        rep for rep in Cmd._ALL_REPRESENTATIONS
        if rep not in hidden and _SPELLED_DIFFERENTLY.get(rep) not in hidden
    ]
    assert not missing, f"not reachable from the H menu: {missing}"


def test_the_chimol_only_representations_are_present():
    """`metaball` above all: a PyMOL user has no reason to look for it."""
    shown = _verbs(om.SHOW_MENU, "show")
    assert {"trace", "nonbonded", "metaball"} <= shown


def test_the_extra_entries_explain_themselves():
    """A representation PyMOL does not have needs a note saying what it is."""
    notes = {}
    def walk(entries):
        for entry in entries:
            if getattr(entry, "is_submenu", False):
                walk(entry.children)
            elif entry.command:
                notes[entry.label] = entry.note or ""
    walk(om.SHOW_MENU)
    for label in ("trace", "nonbonded", "metaball"):
        assert notes.get(label), f"{label} has no explanation"


# --------------------------------------------------------------------------- #
# The representations themselves
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def session(qapp):
    pytest.importorskip("chisurf.core.structure")
    from chisurf.plugins.chimol.chimol.app.molview_main_window import (
        MolViewPluginWindow,
    )
    from chisurf.plugins.chimol.chimol.cmd import cmd as shared

    win = MolViewPluginWindow()
    win.resize(800, 600)
    win.show()
    for _ in range(12):
        qapp.processEvents()
    win._load_structure_from_path(_FRAGMENT)
    for _ in range(20):
        qapp.processEvents()

    errors: list[str] = []
    shared.set_window(win)
    shared.set_message_callback(lambda _m: None)
    shared.set_error_callback(errors.append)

    def do(line: str) -> None:
        shared.do(line)
        for _ in range(10):
            qapp.processEvents()

    yield win, do, errors
    win.close()


def _vertices(viewer):
    scene = viewer.get_current_scene()
    return sum(
        len(o.geometry.positions) if o.geometry.positions is not None else 0
        for o in scene.objects
    )


@pytest.mark.parametrize("representation", ["trace", "nonbonded", "metaball"])
def test_a_newly_exposed_representation_actually_draws(session, representation):
    """Adding a menu entry for something that draws nothing would be worse than
    leaving it out."""
    win, do, errors = session
    do("hide everything")
    empty = _vertices(win.viewer)
    do(f"show {representation}, all")
    assert errors == [], errors
    assert _vertices(win.viewer) > empty, f"{representation} produced no geometry"


# --------------------------------------------------------------------------- #
# The reference plane
# --------------------------------------------------------------------------- #
def test_the_grid_spacing_follows_the_scene(session):
    """A fixed spacing gives four lines on a peptide and four hundred on a
    ribosome; the second is a grey sheet that buries the molecule."""
    win, _do, _errors = session
    renderer = win.viewer._renderer

    small = renderer._build_grid_draw_data(10.0)
    large = renderer._build_grid_draw_data(2000.0)
    assert small is not None and large is not None
    # Line count stays bounded whatever the extent -- that is the whole point.
    assert len(large.positions) < 4 * len(small.positions)


def test_the_grid_line_count_is_bounded(session):
    win, _do, _errors = session
    renderer = win.viewer._renderer
    for radius in (1.0, 50.0, 200.0, 5000.0):
        draw = renderer._build_grid_draw_data(radius)
        assert draw is not None
        # Two vertices per line, two directions.
        lines = len(draw.positions) // 2
        assert lines <= 8 * renderer.GRID_LINES_ACROSS, (
            f"radius {radius} gives {lines} lines"
        )


def test_the_grid_is_translucent(session):
    """It is a reference, not a subject: at full strength it competes with the
    molecule for attention."""
    win, _do, _errors = session
    draw = win.viewer._renderer._build_grid_draw_data(100.0)
    assert draw is not None
    assert float(draw.colors[0][3]) < 1.0


def test_showing_the_plane_adds_geometry(session):
    """`_grid_visible` alone proves nothing -- the draw list has to grow."""
    win, _do, _errors = session
    renderer = win.viewer._renderer
    before = len(renderer._draw_data)
    renderer.set_grid_visible(True)
    assert renderer._grid_visible is True
    assert len(renderer._draw_data) > before
    renderer.set_grid_visible(False)
    assert len(renderer._draw_data) == before
