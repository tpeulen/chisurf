"""A measurement is an object, so it belongs in the object list.

In PyMOL a `distance` **is an object**: it gets a name, a row and an on/off
switch, and that is how you take one out of the picture without losing it.
chimol drew them into the scene and listed them nowhere, so a measurement could
only ever be deleted, and only by knowing the name it was given.

They are listed under `sele` — below the molecules, because they are derived
from them, which is where PyMOL keeps its non-molecule rows too.
"""
from __future__ import annotations

import pathlib

import pytest

pytest.importorskip("qtpy")

PDB = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
)


@pytest.fixture(scope="module")
def session():
    from qtpy import QtWidgets

    from chimol.app.molview_main_window import (
        MolViewPluginWindow,
    )
    from chimol.cmd import cmd as shared

    if not PDB.is_file():
        pytest.skip(f"missing fixture {PDB}")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    win = MolViewPluginWindow()
    win.resize(900, 640)
    win.show()
    for _ in range(5):
        app.processEvents()

    errors: list[str] = []
    messages: list[str] = []
    shared.set_window(win)
    shared.set_message_callback(messages.append)
    shared.set_error_callback(errors.append)

    def run(line: str) -> list[str]:
        before = len(errors)
        win._run_object_menu_command(line)
        for _ in range(3):
            app.processEvents()
        return errors[before:]

    run(f"load {PDB}")
    run("distance d1, resi 10 and name CA, resi 20 and name CA")
    run("distance d2, resi 30 and name CA, resi 40 and name CA")
    win.sync_internal_gui()
    for _ in range(3):
        app.processEvents()
    yield win, run, messages
    win.close()


def _rows(win):
    return win.viewer._renderer._internal_gui.rows


def _scene_ids(win, name):
    return [o.id for o in win.viewer._scene.objects if name in o.id]


def test_each_measurement_gets_a_row(session):
    win, _run, _said = session
    names = [row.name for row in _rows(win) if row.is_measurement]
    assert names == ["d1", "d2"]


def test_the_rows_sit_below_sele(session):
    """They are derived from the molecules, so they go under everything."""
    win, _run, _said = session
    names = [row.name for row in _rows(win)]
    assert names.index("sele") < names.index("d1")


def test_the_row_shows_the_value(session):
    """A list of `d1`, `d2`, `d3` says nothing about which is which."""
    win, _run, _said = session
    detail = {row.name: row.detail for row in _rows(win) if row.is_measurement}
    assert detail["d1"] and detail["d1"] != detail["d2"]


def test_clicking_the_row_switches_the_measurement_off_and_on(session):
    win, _run, _said = session
    gui = win.viewer._renderer._internal_gui
    gui.layout(900, 640)
    index = [i for i, row in enumerate(gui.rows) if row.name == "d1"][0]
    rect = gui._row_rects[index]

    assert _scene_ids(win, "d1"), "d1 was not drawn to begin with"
    gui.mouse_press(rect.x + 20, rect.y + rect.h / 2)
    gui.release()
    assert not _scene_ids(win, "d1"), "switching it off left it drawn"
    assert _scene_ids(win, "d2"), "switching d1 off took d2 with it"

    # Off, not gone.
    assert "d1" in win.viewer._measurements
    win._run_object_menu_command("measurement d1, on")
    assert _scene_ids(win, "d1")


def test_the_command_lists_them(session):
    win, _run, said = session
    said.clear()
    win._run_object_menu_command("measurement")
    joined = " ".join(said)
    assert "d1" in joined and "d2" in joined


def test_an_unknown_measurement_says_so(session):
    _win, run, _said = session
    complained = run("measurement nonesuch, off")
    assert complained and "no measurement called" in complained[-1]


def test_delete_removes_it_from_the_list(session):
    win, run, _said = session
    run("distance temporary, resi 50 and name CA, resi 60 and name CA")
    win.sync_internal_gui()
    assert "temporary" in [row.name for row in _rows(win)]

    run("measurement temporary, delete")
    win.sync_internal_gui()
    assert "temporary" not in [row.name for row in _rows(win)]
    assert "temporary" not in win.viewer._measurements
