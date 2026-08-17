"""Every object-menu entry, fired through the real window.

The A/S/H/L/C menus are how most people drive the viewer, and until now nothing
tested them: the command layer was covered, the *menus* were not. Running them one
by one through ``MolViewPluginWindow._run_object_menu_command`` — the same path a
click takes — found five broken entries at once, including "remove waters", which
crashed on any structure that actually had waters.

Two things make this worth its runtime. Each entry runs against a **freshly loaded
window**, so one failure cannot poison the next and the failures that remain are
real. And the structure is the solvated fragment, because a menu that operates on
waters or ions cannot be tested against a protein that has neither — which is
exactly how "remove waters" stayed broken.
"""

from __future__ import annotations

import copy
import pathlib

import pytest

from chimol.chrome import object_menus as om
from chimol.core.settings.config import _DISPLAY_CONFIG


@pytest.fixture(autouse=True)
def _restore_display_settings():
    """Put the global display settings back after each entry.

    A fresh window per entry is not enough isolation, because some entries are
    not window-scoped at all: several are PyMOL ``set`` commands, and a setting
    lives in one process-wide dict that every window reads. "sequence > hide"
    runs ``set seq_view, off``, and `_update_sequence_view` returns early when
    that is off -- so every window built *afterwards*, in any later test file,
    silently had no sequence at all.

    That is what it looked like: four failures in two other files, all of them
    about sequence rows that were never built, none of them reproducible on
    their own. Restore in place so the modules holding this dict by reference
    see the restoration too.
    """
    snapshot = copy.deepcopy(_DISPLAY_CONFIG)
    yield
    _DISPLAY_CONFIG.clear()
    _DISPLAY_CONFIG.update(snapshot)

_PDB = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files"
)
#: Six residues, a metal ion and eight waters -- small enough that 150-odd window
#: loads stay quick, complete enough that every menu entry has something to act
#: on. A menu that removes waters cannot be tested against a structure with none,
#: which is exactly how "remove waters" stayed broken.
_FRAGMENT = _PDB / "solvated_fragment.pdb"

_MENUS = {
    "A": om.ACTION_MENU,
    "S": om.SHOW_MENU,
    "H": om.HIDE_MENU,
    "L": om.LABEL_MENU,
    "C": om.COLOR_MENU,
}


def _leaves(entries, prefix=""):
    """Every leaf entry, with the menu path that reaches it."""
    for entry in entries:
        if not entry.label:
            continue
        path = f"{prefix}{entry.label}"
        if entry.children:
            yield from _leaves(entry.children, prefix=f"{path} > ")
        else:
            yield path, entry


def _runnable():
    """Every menu entry chimol claims to implement."""
    out = []
    for key, table in _MENUS.items():
        for path, entry in _leaves(table):
            if entry.command is not None:
                out.append(pytest.param(entry.command, id=f"{key}:{path}"))
    return out


def _disabled():
    out = []
    for key, table in _MENUS.items():
        for path, entry in _leaves(table):
            if entry.command is None:
                out.append(pytest.param(entry, id=f"{key}:{path}"))
    return out


@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _open(qapp, path, *, second_object=False):
    """Open a real plugin window on ``path``, with error capture wired in."""
    pytest.importorskip("chisurf.core.structure")
    from chimol.hosts.qt.window import MolViewPluginWindow

    win = MolViewPluginWindow()
    shared = win.cmd
    win.resize(700, 500)
    win.show()
    for _ in range(5):
        qapp.processEvents()
    win._load_structure_from_path(path)
    for _ in range(10):
        qapp.processEvents()

    errors: list[str] = []
    shared.set_window(win)
    shared.set_message_callback(lambda _m: None)
    shared.set_error_callback(errors.append)
    panel = getattr(win, "command_panel", None)
    if panel is not None:
        panel.append_message = lambda _m: None
        panel.append_error = errors.append

    if second_object:
        # `align to ...` and `super to ...` need something to align *to*.
        shared.do(f"copy other, {path.stem}")
        for _ in range(5):
            qapp.processEvents()
        errors.clear()
    return win, errors


@pytest.fixture
def window(qapp):
    """Build a window on the fragment, with a second object to align against.

    Fresh per test: a menu entry that breaks the session would otherwise make
    every later entry look broken too.
    """
    win, errors = _open(qapp, _FRAGMENT, second_object=True)
    yield win, errors
    win.close()


@pytest.fixture
def solvated(qapp):
    """Build a window on the fragment that actually has waters and an ion."""
    win, errors = _open(qapp, _FRAGMENT)
    yield win, errors
    win.close()


#: The window names an object after the file it came from, so that is the name a
#: menu entry is given -- not one the test picks.
OBJECT = _FRAGMENT.stem
SOLVATED = OBJECT


def _fill(template: str) -> str:
    """Substitute the placeholders a click would fill in.

    The value has to suit the *slot*, not just the type. ``align``/``super``
    take a **target selection**, which has to name something that exists: a
    made-up name used to resolve to an empty mask, so the sweep passed while the
    command did nothing at all. An unknown name is an error now, which is what
    caught it. Aligning the object to itself is the smallest thing that exercises
    the real path.
    """
    line = template.replace("{sele}", OBJECT)
    if "{text}" in line:
        if any(word in line for word in ("transparency", "width", "radius")):
            value = "0.5"
        elif line.split(maxsplit=1)[0] in ("align", "super"):
            value = OBJECT
        else:
            # A name for something the command creates, so it need not exist.
            value = "copied"
        line = line.replace("{text}", value)
    return line


#: Errors that are the fixture's fault rather than the entry's. The sweep runs
#: every entry against one small solvated fragment, and a few entries ask the
#: structure a question it cannot answer -- there is no CRYST1 record in it, so
#: the symmetry entries have nothing to expand or draw and say so. Refusing
#: with a reason *is* the correct behaviour there, and it is covered properly in
#: `test_symmetry.py` against a file that does carry a cell.
#:
#: Keep this narrow: it is a list of *messages*, not of entries, so it cannot
#: quietly excuse a different failure of the same command.
_FIXTURE_CANNOT_ANSWER = ("carries no unit cell",)


@pytest.mark.parametrize("template", _runnable())
def test_a_menu_entry_runs(window, template):
    """Every entry with a command must run without reporting an error.

    The entry goes in **whole**, ``;`` and all, because that is what the panel
    inside the viewport emits — splitting it here is what hid RF-846, where the
    four ``preset`` entries (the only ones that are compound) each answered
    "too many positional arguments" from the viewport and worked from the dock.
    """
    win, errors = window
    win._run_object_menu_command(_fill(template))

    from qtpy import QtWidgets

    app = QtWidgets.QApplication.instance()
    for _ in range(5):
        app.processEvents()

    unexpected = [
        e for e in errors
        if not any(reason in e for reason in _FIXTURE_CANNOT_ANSWER)
    ]
    assert unexpected == [], (
        f"{template!r} -> {unexpected[-1] if unexpected else ''}"
    )


@pytest.mark.parametrize("entry", _disabled())
def test_a_disabled_entry_says_why(entry):
    """An entry chimol cannot honour must explain itself, not sit there dead.

    A greyed-out row with no tooltip is indistinguishable from a bug.
    """
    assert entry.note.strip(), f"{entry.label!r} is disabled with no explanation"


# --------------------------------------------------------------------------- #
# The ones that were broken
# --------------------------------------------------------------------------- #
def test_remove_waters_removes_the_waters(solvated):
    """The entry the user reported. It crashed on any structure that had any."""
    win, errors = solvated
    before = len(win.viewer._atoms)
    win._run_object_menu_command(f"remove solvent and {SOLVATED}")
    assert errors == []
    assert len(win.viewer._atoms) == before - 8


def test_deleting_the_last_object_leaves_a_usable_viewer(solvated):
    """Reading state from an empty viewer used to raise, so the next repaint died."""
    win, errors = solvated
    win._run_object_menu_command(f"delete {SOLVATED}")
    assert errors == []
    assert win.viewer.list_objects() == []
    # The crash was here: any reader of a state field, which a repaint is.
    assert win.viewer._atoms is None
    assert win.viewer._all_atom_coords is None


def test_copy_to_object_copies_from_the_right_one(window):
    """The template had its arguments the wrong way round.

    `copy target, source` -- so `copy {sele}, {text}` asked to copy *from* the
    name the user typed, which does not exist.
    """
    win, errors = window
    win._run_object_menu_command(f"copy duplicate, {OBJECT}")
    assert errors == []
    assert "duplicate" in [str(o["name"]) for o in win.viewer.list_objects()]


@pytest.mark.parametrize("mode", ["byelement", "bychain", "byresidue", "bysequence"])
def test_the_colour_menu_spellings_are_accepted(window, mode):
    """The menu writes them without underscores; `color` only knew `by_element`."""
    win, errors = window
    win._run_object_menu_command(f"color {mode}, {OBJECT}")
    assert errors == []


@pytest.mark.parametrize(
    "colour",
    ["wheat", "palegreen", "lightblue", "paleyellow",
     "lightpink", "palecyan", "lightorange", "bluewhite"],
)
def test_every_tint_in_the_menu_exists(colour):
    """The tints menu once listed `yellowtint`, which is not a PyMOL colour."""
    from chimol.core.colors import get_pymol_color

    assert get_pymol_color(colour) is not None
