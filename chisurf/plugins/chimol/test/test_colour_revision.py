"""The sequence strip notices a colour change without re-deriving the colours.

The problem
-----------
Colouring is a *command* -- ``spectrum``, ``color``, ``ss`` -- and there is no
signal for it. So the strip re-read the whole per-residue colour array on every
frame purely to notice that it had changed. On the 234,184-bead nuclear pore
that array is 234,184 x 4, and rebuilding it measured as the entire remaining
CPU cost of a frame once the chrome was cached.

Two attempts to make the *derivation* cheaper both failed, and both failed the
same way -- 50 and then 152 test failures -- because the colour pipeline is
mutated in place from many places that a key over its declared inputs does not
see. Those are recorded in ``okf/references/known-issues.md``.

The change that worked is structural rather than a cache: every assignment to a
state field already passes through one descriptor, so that descriptor counts
them. The strip compares an integer, and derives the colours only when the
integer has moved.

What this pins
--------------
The counter is only useful if it moves **whenever the colours do** -- a counter
that misses a change gives a strip that shows the previous colour scheme, with
nothing raised anywhere. So the test drives real colour commands and asserts on
what the strip actually holds afterwards, not on the counter alone.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("CHIMOL_TOOLKIT", "none")
os.environ.setdefault("CHIMOL_CANVAS", "offscreen")


@pytest.fixture
def app():
    run = pytest.importorskip("chisurf.plugins.chimol.chimol.host.run")
    try:
        instance = run.ChimolApp(backend="offscreen", size=(900, 600))
    except Exception as exc:  # pragma: no cover - no WebGPU adapter here
        pytest.skip(f"no offscreen renderer: {exc}")
    instance.cmd.do("fetch 148L")
    instance.cmd.do("zoom all")
    return instance


def _object_id(app) -> str:
    return str(app.viewer.list_objects()[0]["id"])


@pytest.mark.parametrize(
    "command",
    [
        "spectrum b",
        "color red",
        "spectrum count",
        "color blue, chain A",
        "spectrum resi",
        "color yellow, resi 1-20",
    ],
)
def test_a_colour_command_moves_the_revision(app, command):
    """Every command that recolours bumps the counter the strip watches.

    ``ss`` was in this list at first and failed -- correctly: it is not
    implemented, so it changes no colours and must not move the counter. A
    signal that fired for a command that did nothing would be as wrong as one
    that missed a command that did something.
    """
    oid = _object_id(app)
    before = app.viewer.field_revision("colors_per_ca", oid)
    app.cmd.do(command)
    after = app.viewer.field_revision("colors_per_ca", oid)
    assert after > before, f"{command!r} changed colours without moving the revision"


def test_the_strip_follows_a_colour_command(app):
    """What the strip *holds* changes -- which is the thing that matters.

    The counter existing is not the point; the strip showing the new colours is.
    A counter that failed to move would leave the previous scheme on screen with
    nothing raised, which is why this asserts on the row rather than the signal.
    """
    gui = app.renderer._internal_gui
    app.renderer.draw_frame()
    if not gui.sequences:
        pytest.skip("no sequence rows")

    def colours():
        return [tuple(c) for c in (gui.sequences[0].colors or [])[:8]]

    app.cmd.do("spectrum b")
    app.renderer.draw_frame()
    after_spectrum = colours()

    app.cmd.do("color red")
    app.renderer.draw_frame()
    after_red = colours()

    assert after_spectrum, "the strip has no colours at all"
    assert after_spectrum != after_red, (
        "the sequence strip kept the previous colour scheme -- the revision "
        "did not move, or refresh_gui_state stopped consulting it"
    )


def test_an_idle_frame_does_not_re_derive_the_colours(app):
    """The whole point: a frame that changes nothing does no colour work.

    Pinned because it is easy to lose. Anything that assigns ``colors_per_ca``
    during a repaint -- a scene rebuild, a well-meant refresh -- puts the
    per-frame cost straight back, and nothing else would notice.
    """
    from chisurf.plugins.chimol.chimol.renderer.gui_state import refresh_gui_state

    viewer = app.viewer
    gui = app.renderer._internal_gui
    app.renderer.draw_frame()
    refresh_gui_state(gui, viewer)

    oid = _object_id(app)
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

    assert viewer.field_revision("colors_per_ca", oid) == settled, (
        "something assigned the colours during an idle refresh"
    )
    assert not calls, (
        f"idle frames still derived the colours {len(calls)} time(s); "
        "that is the cost this signal exists to remove"
    )
