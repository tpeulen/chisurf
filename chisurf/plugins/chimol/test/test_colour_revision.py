"""The sequence strip notices a colour change without re-deriving the colours.

The problem
-----------
Colouring is a *command* -- ``spectrum``, ``color`` -- and there is no signal for
it. So the strip re-read the whole per-residue colour array on every frame purely
to notice that it had changed. On the 234,184-bead nuclear pore that array is
234,184 x 4, and rebuilding it measured as the entire remaining CPU cost of a
frame once the chrome was cached.

Two attempts to make the *derivation* cheaper both failed, and both failed the
same way -- 50 and then 152 test failures -- because the colour pipeline is
mutated in place from many places that a key over its declared inputs does not
see. Both are recorded in ``okf/references/known-issues.md``.

The change that worked is structural rather than a cache: every assignment to a
state field already passes through one descriptor, so that descriptor counts
them. The strip compares an integer and derives the colours only when the
integer has moved.

What this pins
--------------
The counter is only useful if it moves **whenever the colours do** -- one that
misses a change gives a strip showing the previous colour scheme, with nothing
raised anywhere. So the tests drive real colour commands and assert on what the
strip actually holds, not on the counter alone.

Runs in a child process; see :mod:`.toolkit_free`.
"""
from __future__ import annotations

import pytest

from toolkit_free import probe

#: Commands that must move the counter. ``ss`` was in this list at first and
#: failed -- correctly: it is not implemented, so it changes no colours and must
#: not move it. A signal that fired for a command that did nothing would be as
#: wrong as one that missed a command that did something.
COLOUR_COMMANDS = [
    "spectrum b",
    "color red",
    "spectrum count",
    "color blue, chain A",
    "spectrum resi",
    "color yellow, resi 1-20",
]


@pytest.fixture(scope="module")
def measured():
    """Drive the colour commands and report what moved."""
    commands = "\n".join(
        f'        run({command!r})' for command in COLOUR_COMMANDS
    )
    return probe('''
        from chimol.ui.gui_state import refresh_gui_state

        app = open_app(size=(900, 600))
        app.cmd.do("fetch 148L")
        app.cmd.do("zoom all")
        viewer, gui = app.viewer, app.renderer._internal_gui
        oid = str(viewer.list_objects()[0]["id"])

        def run(command):
            before = viewer.field_revision("colors_per_ca", oid)
            app.cmd.do(command)
            after = viewer.field_revision("colors_per_ca", oid)
            emit(command, "moved" if after > before else "missed")

''' + commands + '''

        # What the strip *holds* is the thing that matters: a counter that
        # failed to move would leave the previous scheme on screen.
        def colours():
            return [tuple(c) for c in (gui.sequences[0].colors or [])[:8]]

        app.renderer.draw_frame()
        app.cmd.do("spectrum b")
        app.renderer.draw_frame()
        after_spectrum = colours()
        app.cmd.do("color red")
        app.renderer.draw_frame()
        after_red = colours()
        emit("strip_has_colours", "yes" if after_spectrum else "no")
        emit("strip_follows", "yes" if after_spectrum != after_red else "no")

        # And the point of it all: an idle frame must derive nothing.
        app.renderer.draw_frame()
        refresh_gui_state(gui, viewer)
        settled = viewer.field_revision("colors_per_ca", oid)

        calls = []
        original = type(viewer).get_residue_colors

        def counting(self, object_id=None):
            calls.append(object_id)
            return original(self, object_id)

        type(viewer).get_residue_colors = counting
        try:
            for _ in range(5):
                refresh_gui_state(gui, viewer)
        finally:
            type(viewer).get_residue_colors = original

        emit("idle_derivations", len(calls))
        emit("idle_assignments",
             viewer.field_revision("colors_per_ca", oid) - settled)
    ''')


@pytest.mark.parametrize("command", COLOUR_COMMANDS)
def test_a_colour_command_moves_the_revision(measured, command):
    """Every command that recolours bumps the counter the strip watches."""
    assert measured.get(command) == "moved", (
        f"{command!r} changed colours without moving the revision"
    )


def test_the_strip_follows_a_colour_command(measured):
    """The counter existing is not the point; the strip updating is."""
    assert measured.get("strip_has_colours") == "yes", "the strip has no colours"
    assert measured.get("strip_follows") == "yes", (
        "the sequence strip kept the previous colour scheme -- the revision did "
        "not move, or refresh_gui_state stopped consulting it"
    )


def test_an_idle_frame_does_not_re_derive_the_colours(measured):
    """The whole point: a frame that changes nothing does no colour work.

    Pinned because it is easy to lose. Anything that assigns ``colors_per_ca``
    during a repaint -- a scene rebuild, a well-meant refresh -- puts the
    per-frame cost straight back, and nothing else would notice.
    """
    assert int(measured["idle_assignments"]) == 0, (
        "something assigned the colours during an idle refresh"
    )
    assert int(measured["idle_derivations"]) == 0, (
        f"idle frames still derived the colours {measured['idle_derivations']} "
        "time(s); that is the cost this signal exists to remove"
    )
