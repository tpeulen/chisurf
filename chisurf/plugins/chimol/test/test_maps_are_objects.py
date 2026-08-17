"""A density map is an object, and the object list is where objects are.

The report
----------
"Density maps must be listed in the object list (a density map is an object).
Also: loaded a density, then loaded a second density, and only the first shows
in the density panel."

Both halves are one defect with one root, and a third sat underneath them.

1. **The object list never learned about maps.** It is refreshed by the *host*,
   which the loader calls after a structure arrives -- and nothing else did.
   `load_map`, `fetch EMD-xxxx`, `molmap`, `create` and `delete` all changed the
   object list and told the panel nothing. A map was therefore invisible in the
   one place objects are listed.

2. **So a map could not be made active**, and the density panel edits "the
   active object's map, else the newest". With no row to click there was no way
   to go back to the first map: the panel was not stuck, it was unreachable.

3. **And `activate` was broken anyway.** It imported `LoaderMixin` from a module
   whose class is `LoaderCommands` -- a rename that took the call site with it in
   one direction only -- so every `activate` raised ImportError. The stale name
   survived in that module's `__all__` too, where nothing imports it and nothing
   checked.

The panel also *named the wrong thing*: the grid's name is the **file** it came
from, so two maps loaded from one file showed one header between them, which is
exactly what "only the first shows" looks like from the outside.
"""
from __future__ import annotations

import pathlib

import pytest

from toolkit_free import probe

_MAP = pathlib.Path.home() / ".chisurf/structures/chimol/chimol_emdb_EMD-3061.map.gz"


@pytest.fixture(scope="module")
def measured():
    if not _MAP.exists():
        pytest.skip("no cached EMDB map to load twice")
    return probe(f'''
        app = open_app(size=(900, 620))
        errors = []
        app.cmd.set_error_callback(errors.append)
        viewer = app.viewer
        gui = app.renderer._internal_gui

        def rows():
            return [r.name for r in gui.rows]

        app.cmd.do("fetch 148L")
        emit("after_structure", ",".join(rows()))

        app.cmd.do("load_map {_MAP.as_posix()}, deposited")
        emit("after_map", ",".join(rows()))

        app.cmd.do("molmap 148l, 6, simulated")
        emit("after_second_map", ",".join(rows()))

        app.cmd.do("density_panel on")
        app.renderer.draw_frame()
        panel = viewer._renderer._internal_gui.panels["density"]
        emit("panel_newest", panel.model.summary()[:24])

        errors.clear()
        app.cmd.do("activate deposited")
        emit("activate_errors", "; ".join(errors) or "none")
        app.renderer.draw_frame()
        emit("panel_after_activate", panel.model.summary()[:24])
        emit("active_id", str(viewer.get_active_object_id()))
        # The header, read while that map is the active one: it must name the
        # *object*, since both maps here could carry one file name between them.
        emit("title", panel.model.map_title())

        app.cmd.do("activate simulated")
        app.renderer.draw_frame()
        emit("panel_back", panel.model.summary()[:24])

        app.cmd.do("delete simulated")
        emit("after_delete", ",".join(rows()))
    ''')


def test_a_map_appears_in_the_object_list(measured):
    """The report, directly."""
    before = measured["after_structure"].split(",")
    after = measured["after_map"].split(",")
    assert "deposited" not in before
    assert "deposited" in after, f"the map is not listed: {after}"


def test_a_second_map_appears_too(measured):
    rows = measured["after_second_map"].split(",")
    assert "deposited" in rows and "simulated" in rows, rows


def test_the_structure_is_still_there(measured):
    """A refresh that dropped the structures would be a worse bug than the one
    it fixed."""
    rows = measured["after_second_map"].split(",")
    assert rows[0] == "all" and rows[-1] == "sele", rows
    assert "148l" in rows


def test_deleting_a_map_removes_its_row(measured):
    """The list follows both ways, or it is a list of what once was."""
    rows = measured["after_delete"].split(",")
    assert "simulated" not in rows, rows
    assert "deposited" in rows, rows


def test_activate_does_not_raise(measured):
    """It imported a class that had been renamed, and raised on every run."""
    assert measured["activate_errors"] == "none", measured["activate_errors"]


def test_the_density_panel_follows_the_active_map(measured):
    """The second half of the report: two maps, and a way back to the first.

    The panel edits the active object's map, so with maps in the object list
    (and `activate` working) both are reachable -- which they were not.
    """
    assert measured["panel_newest"] != measured["panel_after_activate"], (
        "activating the other map did not change what the panel edits"
    )
    assert measured["panel_back"] == measured["panel_newest"], (
        "activating back did not return to the first map"
    )


def test_the_panel_names_the_object_not_the_file(measured):
    """Two maps from one file are otherwise one header between them."""
    assert "deposited" in measured["title"], measured["title"]


def test_the_loader_class_is_named_once():
    """The rename that broke `activate` left a second name behind.

    `__all__` is where a stale name survives longest: nothing imports from it,
    so nothing fails, and the next reader takes it for the real class name --
    which is how the broken call site was written in the first place.
    """
    from chimol.commands import loader

    for name in loader.__all__:
        assert hasattr(loader, name), f"loader.__all__ names {name!r}, which does not exist"
