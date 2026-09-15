"""``reset_session``: the reset is the owners', not an inventory in a command.

The report was "still seems an arch issue, reinit should clear all and reinit,
what you do is patch the issue instead of fixing at arch level" -- and it was
right about the shape of the old code. ``reinitialize`` *was* the inventory:
delete the objects, then put back these eight display flags, then the lighting
overrides, then the camera, then the chrome flags, then -- as each new thing
was found still standing -- close that panel too, stop that clock too. A list
kept by the caller is a list of what somebody remembered, so every new panel,
plugin or clock is a thing nobody has remembered yet, and each round ends in
another "reinit does not reset X".

What is pinned here is the arrangement that replaced it:

* every store resets **itself** -- ``Playback.reset``,
  ``InternalGui.reset_session``, the wizard's own ``finish``;
* the chrome closes the windows commands opened because *it* knows which those
  are (its ``panels`` dict), so a plugin's panel closes without anything
  naming it;
* anything that is not one of the viewer's own stores hears ``session.reset``
  on the bus;
* the command is three steps -- ask the viewer, restore the settings, refresh
  the host -- and names no panel, no flag and no clock.

The last point is asserted on the *source*: a reset that starts enumerating
again is the regression this file exists to catch.
"""
from __future__ import annotations

import ast
import inspect
import pathlib

import pytest

import chimol
from toolkit_free import probe

ROOT = pathlib.Path(chimol.__file__).resolve().parent


@pytest.fixture(scope="module")
def reset():
    """One viewer with everything open, reset once, measured after."""
    return probe('''
        app = open_app(size=(900, 600))
        cmd, gui, viewer = app.cmd, app.viewer.gui, app.viewer

        heard = []
        viewer.bus.subscribe("session.reset", lambda p: heard.append("yes"), owner="probe")

        cmd.do("demo trajectory")
        cmd.do("help")                      # a listing in the info panel
        cmd.do("scores")                    # a plugin's panel
        cmd.do("settings")                  # a core panel
        cmd.do("editor /tmp/scratch.cml")   # a window no registry opened
        cmd.do("wizard measurement")
        cmd.do("mplay")
        app.renderer._draw()

        def windows():
            return ",".join(sorted(w.key for w in gui.windows if w.visible))

        emit("before_windows", windows())
        emit("before_playing", viewer.playback.running)

        cmd.do("reinit")
        app.renderer._draw()

        emit("heard_on_the_bus", ",".join(heard))
        emit("after_windows", windows())
        emit("after_panels", ",".join(sorted(gui.panels)))
        emit("after_playing", viewer.playback.running)
        emit("after_wizard", viewer.wizard is not None)
        emit("after_objects", len(list(viewer.objects.items())))
        emit("after_frame", viewer.get_frame_position())
        emit("after_info", str(gui.info_text))

        # And the viewer can do it on its own, with no command layer at all:
        # that is what makes it the viewer's behaviour rather than a command's.
        cmd.do("demo trajectory")
        cmd.do("scores")
        viewer.reset_session()
        emit("direct_windows", windows())
        emit("direct_objects", len(list(viewer.objects.items())))

        # The representations are the same argument one level down: what a
        # reset puts back is read from the registry, over every object.
        from chimol.core.services.representations import REPRESENTATIONS
        cmd.do("load 148l.pdb"); cmd.do("load 148l.pdb")
        keys = list(viewer.objects)
        emit("objects_for_reps", str(len(keys)))
        for name in ("lines", "nonbonded", "labels", "sticks", "spheres"):
            cmd.do("show %s" % name)
        viewer.update_view()

        def shown(object_id):
            st = viewer.objects[object_id].state
            return sorted(spec.name for spec in REPRESENTATIONS.specs()
                          if spec.flag_field and getattr(st, spec.flag_field, False))

        emit("reps_before", ",".join(shown(keys[0])))
        viewer.reset_session(keep_objects=True)
        viewer.update_view()
        emit("reps_after_first", ",".join(shown(keys[0])))
        emit("reps_after_second", ",".join(shown(keys[1])))
        emit("reps_default", ",".join(sorted(
            spec.name for spec in REPRESENTATIONS.specs() if spec.default_visible)))
    ''')


def test_the_windows_a_command_opened_are_closed(reset):
    assert "scores" in reset["before_windows"]
    assert "editor:scratch.cml" in reset["before_windows"]
    # The chrome's own furniture is what a started viewer has, and it stays.
    assert reset["after_windows"] == "mouse,objects"
    assert reset["after_panels"] == ""


def test_the_clock_and_the_wizard_stop(reset):
    assert reset["before_playing"] == "True"
    assert reset["after_playing"] == "False"
    assert reset["after_wizard"] == "False"
    assert float(reset["after_frame"]) == 0.0


def test_the_scene_is_empty_and_the_panel_says_nothing_is_loaded(reset):
    assert int(reset["after_objects"]) == 0
    assert reset["after_info"] in ("(no system loaded)", "")


def test_anything_else_hears_it_on_the_bus(reset):
    """A plugin holding a cache is told; it does not have to be listed anywhere."""
    assert reset["heard_on_the_bus"] == "yes"


def test_the_viewer_resets_itself_without_the_command(reset):
    assert reset["direct_windows"] == "mouse,objects"
    assert int(reset["direct_objects"]) == 0


def test_the_representations_a_reset_puts_back_are_the_registry_s(reset):
    """Not a table beside it, and not on one object out of two.

    The same inventory habit, one level down: eight setter names and their
    startup values were written out here, and `lines`, `nonbonded` and
    `labels` were registered afterwards without anybody adding them -- so a
    reset left those three exactly as the last session had them. The list that
    cannot disagree with the registry is the registry.

    And it reached one object: ten of the eleven setters wrote to the *active*
    object, while spheres alone had a `set_atoms_visible_all`, so a reset with
    two molecules loaded put the cartoon back on one of them.
    """
    assert int(reset["objects_for_reps"]) == 2
    assert "lines" in reset["reps_before"] and "labels" in reset["reps_before"]
    assert reset["reps_after_first"] == reset["reps_default"]
    assert reset["reps_after_second"] == reset["reps_default"]


def test_the_command_does_not_enumerate_what_to_reset():
    """The regression this whole arrangement exists to prevent.

    ``reinitialize`` may ask the viewer, restore the settings and refresh the
    host. It may not start naming panels, flags or clocks again -- that is the
    inventory coming back, one remembered symptom at a time.
    """
    from chimol.commands.builtin.lifecycle import LifecycleMixin

    source = inspect.getsource(LifecycleMixin.reinitialize)
    body = ast.parse(inspect.cleandoc(source).replace("@command", "# @command", 1))
    names = {
        node.attr
        for node in ast.walk(body)
        if isinstance(node, ast.Attribute)
    }
    forbidden = {
        "playback", "wizard", "panels", "windows", "remove_window", "end_tour",
        "close_menus", "restore_baseline", "set_cartoon_visible", "info_text",
        "_lighting_overrides", "restore_camera_baseline", "remove_object",
    }
    assert not (names & forbidden), (
        "reinitialize is enumerating again: " + ", ".join(sorted(names & forbidden))
    )


def test_each_owner_carries_its_own_reset():
    """Where the knowledge went: three objects, three methods."""
    from chimol.core.services.playback import Playback
    from chimol.core.viewer import Viewer
    from chimol.ui.gui import InternalGui

    assert callable(Playback.reset)
    assert callable(InternalGui.reset_session)
    assert callable(Viewer.reset_session)
