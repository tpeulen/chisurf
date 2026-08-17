"""The camera stays where you put it.

`MolView._update_view` used to refit the camera on **every** rebuild, and a
rebuild is what colouring, a representation change, a label, a bond edit and
every `set` all trigger. Measured on 148L before the fix: ``zoom resi 20-26``
put the camera at 357, and **12 of 12** ordinary commands put it straight back
to 1730. In a viewer, that is a serious thing to get wrong -- framing a binding
site is the first half of almost every task, and the second half undid it.

PyMOL moves the camera for a camera command or a load, and nothing else. These
tests pin both halves of that: the commands that must *not* move it, and the
ones that must.

The fix was recorded as attempted-and-reverted once, because `ray` then traced
an empty image for every representation. That had nothing to do with framing:
a window that is never shown has no viewport, `_aspect` read 1/30 off the
one-pixel column that left, and the camera went thirty times too far away.
Refitting on every rebuild hid it, because the last rebuild landed after the
widget had a size. See ``test_camera_framing.py`` for the guard on that.
"""

from __future__ import annotations

import pathlib

import pytest

_PDB = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files"
)


@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def session(qapp):
    pytest.importorskip("chisurf.core.structure")
    from chimol.hosts.qt.window import MolViewPluginWindow
    from chimol.commands import cmd as shared

    win = MolViewPluginWindow()
    win._load_structure_from_path(_PDB / "148l.pdb")
    for _ in range(20):
        qapp.processEvents()

    errors: list[str] = []
    shared.set_window(win)
    shared.set_message_callback(lambda _m: None)
    shared.set_error_callback(errors.append)

    def do(line: str) -> None:
        errors.clear()
        shared.do(line)
        for _ in range(8):
            qapp.processEvents()

    yield win, do, errors, qapp
    win.close()


def _distance(win) -> float:
    return float(win.viewer._renderer._distance)


#: One of each kind of rebuild: a setting, a colour, two representation changes,
#: a label, a property colouring, a bond edit, a rename, an edit that changes
#: the atom count, and one that changes an atom property.
ORDINARY_COMMANDS = [
    "set sphere_scale, 1.2",
    "set cartoon_loop_radius, 0.25",
    "color red, resi 30",
    "show sticks, resi 40",
    "hide cartoon, resi 60",
    "as spheres",
    "label resi 50 and name CA, resi",
    "spectrum b",
    "bond resi 30 and name CA, resi 31 and name CA",
    "set_name 148l, lyso",
    "h_add resi 20",
    "alter resi 20, b=5",
]


@pytest.mark.parametrize("command", ORDINARY_COMMANDS)
def test_an_ordinary_command_leaves_the_framing_alone(session, command):
    win, do, errors, _qapp = session
    do("zoom resi 20-26")
    framed = _distance(win)
    assert framed > 0.0

    do(command)
    assert errors == [], f"{command} -> {errors[-1]}"
    assert _distance(win) == pytest.approx(framed, rel=1e-9), (
        f"{command} threw the framing away"
    )


def test_h_add_re_derives_without_re_framing(session):
    """The load path reused to rebuild, which is not a load.

    ``_rebuild_after_coordinate_change`` calls ``set_structure`` to re-derive
    the trace, the bonds and the bounding sphere after atoms move. That is the
    same entry point a file load uses, so it framed -- and ``h_add`` on a
    residue you had zoomed into jumped back out to the whole molecule.
    """
    win, do, _errors, _qapp = session
    do("zoom resi 20-26")
    framed = _distance(win)
    do("h_add resi 20")
    assert _distance(win) == pytest.approx(framed, rel=1e-9)


# --------------------------------------------------------------------------- #
# ... and the ones that must still move it
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "setup, command",
    [
        ("zoom resi 20-26", "zoom"),
        ("zoom", "orient resi 20-26"),
        ("zoom resi 20-26", "reset"),
    ],
)
def test_a_camera_command_still_moves_the_camera(session, setup, command):
    """Half a fix is a viewer whose `zoom` does nothing.

    Each case has to start from a *different* framing than it asks for --
    ``orient resi 20-26`` after ``zoom resi 20-26`` frames the same atoms and
    correctly leaves the distance alone, which reads as a broken command.
    """
    win, do, errors, _qapp = session
    do(setup)
    framed = _distance(win)
    do(command)
    assert errors == [], f"{command} -> {errors[-1]}"
    assert _distance(win) != pytest.approx(framed, rel=1e-9), (
        f"{command} did not move the camera"
    )


def test_loading_a_second_structure_frames_it(session):
    """PyMOL's ``auto_zoom``, which is what the load path keeps."""
    win, do, _errors, qapp = session
    do("zoom resi 20-26")
    framed = _distance(win)
    win._load_structure_from_path(_PDB / "1rtd.pdb")
    for _ in range(20):
        qapp.processEvents()
    assert _distance(win) > framed, "a newly loaded structure was not framed"
