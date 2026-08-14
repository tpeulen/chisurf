"""An object name addresses exactly one object.

The report
----------
"Issues when two objects with the same name exist." Loading 148L twice, or two
maps under one name, gave two objects with one name between them -- and every
command that takes a name resolves the **first** match. So the second was
unreachable: `color red, twin` painted one of them and said nothing, `activate
twin` could never select the other, and `delete twin` left a `twin` behind.

The fix, and whose it is
------------------------
PyMOL's, verbatim where it counts: `ExecutiveProcessObjectName` appends
``_%d`` starting at **2**, so the second `twin` is `twin_2`. The setting that
gates it, ``auto_rename_duplicate_objects``, is registered under PyMOL's own
name.

The **default** differs and does so deliberately: PyMOL ships it off, because
loading over an existing name there stacks states inside that object. chimol
has no state stacking, so "off" would mean losing the first object. It ships
on; turning it off restores PyMOL's behaviour of letting duplicates exist.

What this pins
--------------
* the suffix scheme, because it is a compatibility surface;
* that every name-addressed command reaches its own object;
* that the *messages* name the object that now exists -- a load that says
  ``148l`` when it made ``148l_2`` sends the user to the wrong one, which is
  the original bug wearing a different hat;
* that renaming is the same rule, since it was the other way in.
"""
from __future__ import annotations

import pathlib

import pytest

from toolkit_free import probe

_MAP = pathlib.Path.home() / ".chisurf/structures/chimol/chimol_emdb_EMD-3061.map.gz"


@pytest.fixture(scope="module")
def measured():
    if not _MAP.exists():
        pytest.skip("no cached map to load twice")
    return probe(f'''
        app = open_app(size=(700, 500))
        viewer = app.viewer
        errors, messages = [], []
        app.cmd.set_error_callback(errors.append)
        app.cmd.set_message_callback(messages.append)

        def names():
            return ",".join(str(o.get("name")) for o in viewer.list_objects())

        def run(label, command):
            errors.clear()
            messages.clear()
            app.cmd.do(command)
            emit(label, messages[-1] if messages else "")
            emit(label + ":errors", "; ".join(errors) or "none")

        run("first", "fetch 148L")
        run("second", "fetch 148L")
        run("third", "fetch 148L")
        run("map1", "load_map {_MAP.as_posix()}, twin")
        run("map2", "load_map {_MAP.as_posix()}, twin")
        run("create1", "create sub, 148l and resi 1-10")
        run("create2", "create sub, 148l and resi 1-10")
        emit("names", names())

        # Each name reaches its own object.
        run("activate", "activate 148l_3")
        emit("active_name", str(
            getattr(viewer._objects.get(viewer.get_active_object_id()), "name", "")
        ))
        run("delete", "delete twin")
        emit("after_delete", names())

        # Renaming onto a taken name is the same rule.
        run("rename", "set_name twin_2, 148l")
        emit("after_rename", names())

        # And PyMOL's own default, restored by its own setting.
        app.cmd.do("set auto_rename_duplicate_objects, off")
        app.cmd.do("fetch 148L")
        emit("with_setting_off", names())
    ''')


def test_duplicates_get_pymols_suffix(measured):
    """``_2``, ``_3`` -- the scheme is a compatibility surface, not a taste."""
    names = measured["names"].split(",")
    assert names[:3] == ["148l", "148l_2", "148l_3"], names
    assert "twin" in names and "twin_2" in names, names
    assert "sub" in names and "sub_2" in names, names
    assert len(names) == len(set(names)), f"a name is still shared: {names}"


def test_the_message_names_the_object_that_now_exists(measured):
    """A load that says `148l` when it made `148l_2` sends you to the wrong one."""
    assert "148l_2" in measured["second"], measured["second"]
    assert "148l_3" in measured["third"], measured["third"]
    assert "twin_2" in measured["map2"], measured["map2"]
    assert "sub_2" in measured["create2"], measured["create2"]


def test_each_name_reaches_its_own_object(measured):
    """The report: the second object could not be addressed at all."""
    assert measured["activate:errors"] == "none"
    assert measured["active_name"] == "148l_3", measured["active_name"]


def test_delete_removes_the_one_it_named(measured):
    """It used to leave another object with the same name standing."""
    after = measured["after_delete"].split(",")
    assert "twin" not in after, after
    assert "twin_2" in after, after


def test_renaming_onto_a_taken_name_is_the_same_rule(measured):
    """The other way in, and it was open."""
    assert measured["rename:errors"] == "none"
    after = measured["after_rename"].split(",")
    assert len(after) == len(set(after)), f"a rename created a duplicate: {after}"
    assert "twin_2" not in after


def test_pymols_default_is_restored_by_pymols_setting(measured):
    """Off, duplicates are allowed again -- which is what PyMOL ships."""
    names = measured["with_setting_off"].split(",")
    assert names.count("148l") == 2, names


def test_the_setting_is_registered_under_pymols_name():
    """A setting under a different name is a different setting."""
    from chimol import settings as settings_api

    spec = settings_api.resolve("auto_rename_duplicate_objects")
    assert spec.kind == "bool"
    assert spec.default is True, "chimol ships it on; see the module docstring"
