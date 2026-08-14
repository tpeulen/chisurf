"""`reinitialize` puts the viewer back, all of it.

The report
----------
"Reinitialize does not reinit to baseline -- the background does not change
back to black. This seems to be an architecture issue, as some parts reinit but
not all."

That reading was right, and there were four defects behind it, each an instance
of the same thing: **a value with more than one home, and no one owner**.

1. `bg_color` wrote the renderer and not the setting. The screen went red while
   `get bg_rgb` still answered ``k`` and the settings panel drew black -- so a
   reset that puts settings back had nothing to put back. The background was
   the one thing that never came back because it was the one thing the config
   did not really hold.
2. `diff_against_package` walked exactly two levels, section then key, and
   skipped anything else. ``background`` is the shipped config's one top-level
   scalar, so it was invisible to the comparison and could not be restored even
   in principle.
3. The reset compared the **file** against the package rather than the live
   session, so it restored what had been saved and reported a count for it.
4. Restoring the config did not reach the renderer, which *holds* a few of
   those values rather than re-reading them. Putting ``k`` back in the config
   left the screen exactly as red as it was.

And three stores the config does not own at all -- the renderer's lighting
overrides, the camera, and the chrome -- had no baseline, so a lighting preset,
a camera framed on a deleted molecule, and an info panel describing it all
survived.

What this pins
--------------
The reported symptom, the sync that caused it, and -- the point of the file --
that the viewer as a whole comes back, measured in **pixels** against a viewer
that has just started. A per-key assertion only covers the keys somebody
thought of, which is precisely how "some parts reinit but not all" happens.
"""
from __future__ import annotations

import pytest

from toolkit_free import probe

#: What a session does before deciding it wants the tool back.
MUTATIONS = (
    "bg_color red",
    "fetch 148L",
    "lighting soft",
    "set field_of_view, 45",
    "show surface",
    "set label_size, 24",
    "set sphere_scale, 0.8",
)


@pytest.fixture(scope="module")
def measured():
    return probe(f'''
        from chimol import settings as s
        app = open_app(size=(700, 500))
        r = app.renderer

        def corner():
            r.draw_frame()
            return tuple(int(v) for v in np.asarray(r.grab_image())[5, 5, :3])

        def frame():
            r.draw_frame()
            # Everything above the prompt. The command log lives at the bottom
            # and correctly reports what just ran -- "Reinitialized everything"
            # is output, not drift, and comparing it would fail for the one
            # reason that is right.
            return np.asarray(r.grab_image())[:-60, :, :3].copy()

        r.draw_frame()
        fresh, fresh_corner = frame(), corner()
        emit("fresh_corner", fresh_corner)
        emit("fresh_bg", tuple(r._background))

        for line in {MUTATIONS!r}:
            app.cmd.do(line)

        # The sync: `bg_color` must have written the setting, not gone behind it.
        emit("setting_after_bg_color", s.get_setting("bg_rgb"))
        emit("dirty_corner", corner())
        emit("dirty_fov", r._fov)
        emit("dirty_lighting", len(r._lighting_overrides))
        emit("dirty_distance", round(float(r._distance), 3))

        app.cmd.do("reinitialize")
        after, after_corner = frame(), corner()

        emit("after_corner", after_corner)
        emit("after_bg", tuple(r._background))
        emit("after_setting", s.get_setting("bg_rgb"))
        emit("after_fov", r._fov)
        emit("after_lighting", len(r._lighting_overrides))
        emit("after_distance", round(float(r._distance), 3))
        emit("objects", len(app.viewer.list_objects()))
        emit("differing_pixels", int((fresh != after).any(axis=2).sum()))
        emit("total_pixels", int(fresh.shape[0] * fresh.shape[1]))
    ''')


def test_the_background_goes_back_to_black(measured):
    """The report, in the pixels it was reported in."""
    assert measured["dirty_corner"] != measured["fresh_corner"], (
        "the premise: `bg_color red` has to change the background"
    )
    assert measured["after_corner"] == measured["fresh_corner"], (
        f"the background stayed {measured['after_corner']} instead of returning "
        f"to {measured['fresh_corner']}"
    )
    assert measured["after_bg"] == measured["fresh_bg"]


def test_bg_color_writes_the_setting_it_shares(measured):
    """The cause. Two homes for one value, and the command wrote the other one.

    With the renderer written directly, `get bg_rgb` answered ``k`` while the
    screen was red -- so the settings panel disagreed with the view, and the
    reset had nothing to reset.
    """
    value = measured["setting_after_bg_color"]
    assert value not in ("k", "black"), (
        f"bg_color did not reach the setting: bg_rgb is still {value!r}"
    )


def test_renderer_held_values_come_back(measured):
    """Values the renderer *holds* rather than re-reads, and so must be pushed."""
    assert float(measured["dirty_fov"]) == 45.0, "the premise"
    assert float(measured["after_fov"]) == 20.0, (
        "the field of view stayed where the session put it: restoring the "
        "config does not reach a value the renderer holds"
    )


def test_the_stores_the_config_does_not_own_come_back(measured):
    """Lighting overrides and the camera have no config entry to restore."""
    assert int(measured["dirty_lighting"]) > 0, "the premise: `lighting soft` sets overrides"
    assert int(measured["after_lighting"]) == 0, "the lighting preset survived"

    assert measured["dirty_distance"] != measured["after_distance"], (
        "the premise: loading a molecule moves the camera"
    )


def test_the_objects_are_gone(measured):
    """The half that always worked, kept honest."""
    assert int(measured["objects"]) == 0


def test_the_viewer_as_a_whole_returns(measured):
    """The assertion that catches the *next* store somebody forgets.

    Per-key checks only cover the keys somebody thought of. This compares the
    frame against a viewer that has just started, which is what "reinitialize"
    means and what no list of keys can stand in for.
    """
    differing = int(measured["differing_pixels"])
    total = int(measured["total_pixels"])
    assert differing == 0, (
        f"{differing} of {total} pixels differ from a freshly started viewer; "
        "something the reset does not know about survived it"
    )


def test_the_shipped_defaults_are_compared_at_every_depth():
    """The shape assumption that hid the background from the reset.

    The comparison walked section-then-key and skipped anything else, so the
    one top-level scalar in the shipped config was invisible to it -- and to
    the start-up "your settings differ" prompt as well.
    """
    from chimol import config as cfg

    shipped = {"background": "k", "camera": {"field_of_view": 20.0},
               "deep": {"a": {"b": 1.0}}}
    mine = {"background": "red", "camera": {"field_of_view": 45.0},
            "deep": {"a": {"b": 2.0}}}

    # The public function reads the package half from disk, so the walk itself
    # is what is exercised here -- with a shipped config shaped like the real
    # one: a top-level scalar, a section, and something nested deeper.
    out: dict = {}
    cfg._collect_differences(mine, shipped, (), out)
    assert "background" in out, (
        "a top-level scalar is still invisible to the comparison"
    )
    assert "camera.field_of_view" in out
    assert "deep.a.b" in out, "nested keys deeper than two levels are skipped"
