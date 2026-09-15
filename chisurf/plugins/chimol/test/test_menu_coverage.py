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

from chimol.ui.menus import objects as om
from chimol.commands.command import Cmd

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

from chimol.core.services.representations import REPRESENTATIONS


# --------------------------------------------------------------------------- #
# Menu coverage
# --------------------------------------------------------------------------- #
def _scopable() -> list[str]:
    """Representations the S and H menus are *for*.

    Those menus act on a selection, so they cover the representations that can
    be scoped to one -- which the registry answers. The reference plane is a
    scene aid with no per-row state: `show plane` is a viewer setting, not
    something you do to a selection, and listing it beside `sticks` would say
    otherwise.
    """
    return [name for name in REPRESENTATIONS.names()
            if REPRESENTATIONS.scoped(name) is not None]


def test_every_representation_can_be_shown_from_the_menu():
    """Including the ones ChiMOL has and PyMOL does not."""
    shown = _verbs(om.SHOW_MENU, "show")
    missing = [
        rep for rep in _scopable()
        if rep not in shown and _SPELLED_DIFFERENTLY.get(rep) not in shown
    ]
    assert not missing, f"not reachable from the S menu: {missing}"


def test_every_representation_can_be_hidden_from_the_menu():
    hidden = _verbs(om.HIDE_MENU, "hide")
    missing = [
        rep for rep in _scopable()
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
    from chimol.hosts.qt.window import MolViewPluginWindow

    win = MolViewPluginWindow()
    shared = win.cmd
    win.resize(800, 600)
    win.show()
    for _ in range(12):
        qapp.processEvents()
    win.load_structure_from_path(_FRAGMENT)
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
    renderer = win.viewer.renderer

    small = renderer._build_grid_draw_data(10.0)
    large = renderer._build_grid_draw_data(2000.0)
    assert small is not None and large is not None
    # Line count stays bounded whatever the extent -- that is the whole point.
    assert len(large.positions) < 4 * len(small.positions)


def test_the_grid_line_count_is_bounded(session):
    win, _do, _errors = session
    renderer = win.viewer.renderer
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
    draw = win.viewer.renderer._build_grid_draw_data(100.0)
    assert draw is not None
    assert float(draw.colors[0][3]) < 1.0


def test_showing_the_plane_adds_geometry(session):
    """`_grid_visible` alone proves nothing -- the draw list has to grow."""
    win, _do, _errors = session
    renderer = win.viewer.renderer
    before = len(renderer._draw_data)
    renderer.set_grid_visible(True)
    assert renderer._grid_visible is True
    assert len(renderer._draw_data) > before
    renderer.set_grid_visible(False)
    assert len(renderer._draw_data) == before


# --------------------------------------------------------------------------- #
# The disabled entries are an inventory, and it shrinks
# --------------------------------------------------------------------------- #
#: Every menu leaf that is deliberately greyed out, with the reason it is. This
#: list is a **tracker and it only shrinks** -- it is not somewhere to add an
#: entry you did not want to wire up.
#:
#: It exists because a disabled entry is only honest while its reason still
#: holds, and nothing re-checks them. Three were found stale on 2026-08-07 in
#: one sitting: `origin` ("chimol rotates about the scene centre") and `cell`
#: ("chimol does not read crystal cells") had both had working commands for a
#: while, and `generate` claimed chimol could not build symmetry mates while
#: `symexp` sat in plugins/symmetry/commands.py under 53 tests. To the user those read
#: exactly like a missing feature -- and `A > hydrogens > add` was a fourth,
#: found the same day: `h_add` has been in commands/builtin/editing.py the whole time.
DISABLED_ENTRIES = {
    # No structure editing.
    "A > clean",
    # No per-object matrix.
    "A > drag matrix",
    "A > reset matrix",
    "A > drag coordinates",
    # One solid surface: no surface_type, no per-object transparency.
    "A > preset > ligand sites > solid (better)",
    "A > preset > ligand sites > transparent surface",
    "A > preset > ligand sites > transparent (better)",
    "A > preset > ligand sites > dot surface",
    "A > preset > ligand sites > mesh surface",
    # No Poisson-Boltzmann solver.
    "A > generate > vacuum electrostatics",
    # Frames are the timeline panel's; no atom masking; no per-object motion.
    "A > state",
    "A > masking",
    "A > movement",
    # No per-atom flags, no bond orders.
    "S > flag ignore",
    "S > valence",
    "H > flag ignore",
    "H > valence",
    # No user-defined atom properties; colour is per object and selection.
    "L > other properties",
    "C > by rep",
    "C > auto",
}


def _disabled_leaves():
    """Every leaf entry with no command, as ``"A > preset > ..."`` paths."""
    from chimol.ui.menus.objects import OBJECT_MENUS

    def walk(entries, path):
        for entry in entries:
            if entry.is_separator:
                continue
            if entry.children:
                yield from walk(entry.children, path + (entry.label,))
            elif entry.command is None:
                yield " > ".join(path + (entry.label,))

    found = set()
    for key, _title, menu in OBJECT_MENUS:
        found.update(walk(menu, (key,)))
    return found


def test_the_disabled_entries_are_the_inventory():
    """Wiring one up means striking its line here; nothing else may appear."""
    found = _disabled_leaves()
    new = found - DISABLED_ENTRIES
    assert not new, (
        f"new disabled menu entries: {sorted(new)} -- wire them up, or add them "
        "here with the reason, knowing this list is meant to shrink"
    )
    closed = DISABLED_ENTRIES - found
    assert not closed, (
        f"these entries now have commands: {sorted(closed)} -- strike them "
        "from DISABLED_ENTRIES"
    )


def test_every_disabled_entry_says_why():
    """A greyed-out row with no tooltip is indistinguishable from a bug."""
    from chimol.ui.menus.objects import OBJECT_MENUS

    def walk(entries, path):
        for entry in entries:
            if entry.is_separator:
                continue
            if entry.children:
                yield from walk(entry.children, path + (entry.label,))
            elif entry.command is None:
                yield " > ".join(path + (entry.label,)), entry.note

    for key, _title, menu in OBJECT_MENUS:
        for where, note in walk(menu, (key,)):
            assert note.strip(), f"{where} is disabled with no reason given"
