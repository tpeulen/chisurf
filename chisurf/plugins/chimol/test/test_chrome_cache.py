"""The chrome is cached between frames, and must never draw a stale one.

Why this exists
---------------
The chrome is immediate mode: every frame rebuilt ~2,800 quads from scratch, and
on an integrative model that was **most of the frame** while the molecule itself
cost about a millisecond. But the chrome changes on hover, focus and state --
not on camera motion, which is the only time anybody is watching the frame rate.
So :meth:`CanvasRenderer._chrome_quads` reuses the previous frame's vertices
whenever :meth:`InternalGui.chrome_fingerprint` has not moved.

That trade has exactly one failure mode, and it is silent: a fingerprint that
omits something the paint reads shows a **stale picture**. Nothing raises,
nothing is logged, and it looks like a redraw bug somewhere else entirely.

So this does not check the cache's *hits*; it checks its *answers*. For a sweep
of real interactions it compares what the cached path returns against a freshly
emitted build and demands they be identical. Written first, it caught two
genuine omissions on the first run:

* ``SequenceRow.selected`` -- the strip highlights the selection, and the set is
  mutated **in place** in three separate places, so neither the row's identity
  nor the sequence list's length notices;
* the **command-line feedback log** -- every command appends a line, which is
  drawn as text. ``select everything`` moved nine quads with the rows, the
  sequences and the windows all unchanged, which is what pointed at it.

The control that made the second one findable is worth keeping in mind: when
this failed, the same sweep was run with the cache *disabled*. It scored 52/54
rather than 42/54, and the two residual mismatches were the progress overlay,
which animates and counts seconds and so differs between any two paints. Without
that control the animation would have looked like a cache bug.

Runs in a child process; see :mod:`.toolkit_free`.
"""

from __future__ import annotations

import pytest
from toolkit_free import probe

#: Each interaction is applied in order, and the chrome compared after it **and**
#: again after that -- the second comparison exercises a cache *hit*, since by
#: then the fingerprint has not moved.
INTERACTIONS = [
    "idle",
    "hover the panel",
    "hover the scene",
    "open a menu",
    "move within it",
    "dismiss it",
    "show info",
    "hide info",
    "spectrum",
    "colour",
    "hide cartoon",
    "show spheres",
    "debug on",
    "debug off",
    "chrome scale",
    "chrome scale back",
    "resize",
    "resize back",
    "select",
    "deselect",
    "a second object",
    "delete it",
]


@pytest.fixture(scope="module")
def swept():
    """Drive every interaction and report whether the cache stayed honest."""
    return probe("""
        from emtk.quad_painter import QuadPainter

        app = open_app(size=(1100, 760))
        app.cmd.do("fetch 148L")
        app.cmd.do("zoom all")
        renderer, gui = app.renderer, app.renderer._internal_gui

        def fresh():
            painter = QuadPainter(scale=renderer._ratio(), font_scale=gui.ui_scale)
            gui.paint(painter)
            vertices = painter.vertices()
            return vertices if len(vertices) else None

        def agrees():
            cached, built = renderer._chrome_quads(), fresh()
            if cached is None or built is None:
                return cached is None and built is None
            return cached.shape == built.shape and np.array_equal(cached, built)

        actions = [
            ("idle", lambda: None),
            ("hover the panel", lambda: gui.mouse_move(1000, 130)),
            ("hover the scene", lambda: gui.mouse_move(400, 400)),
            ("open a menu", lambda: gui.mouse_press(30, 10)),
            ("move within it", lambda: gui.mouse_move(40, 60)),
            ("dismiss it", lambda: gui.dismiss_overlays(400, 400)),
            ("show info", lambda: app.cmd.do("info")),
            ("hide info", lambda: app.cmd.do("info")),
            ("spectrum", lambda: app.cmd.do("spectrum b")),
            ("colour", lambda: app.cmd.do("color red")),
            ("hide cartoon", lambda: app.cmd.do("hide cartoon")),
            ("show spheres", lambda: app.cmd.do("show spheres")),
            ("debug on", lambda: app.cmd.do("debug on")),
            ("debug off", lambda: app.cmd.do("debug off")),
            ("chrome scale", lambda: app.cmd.do("set ui_scale, 1.29")),
            ("chrome scale back", lambda: app.cmd.do("set ui_scale, 1.0")),
            ("resize", lambda: renderer.resize(950, 700)),
            ("resize back", lambda: renderer.resize(1100, 760)),
            ("select", lambda: app.cmd.do("select everything")),
            ("deselect", lambda: app.cmd.do("deselect")),
            ("a second object", lambda: app.cmd.do("fetch 1crn")),
            ("delete it", lambda: app.cmd.do("delete 1crn")),
        ]
        for label, act in actions:
            act()
            first = agrees()
            # Again with nothing changed: the cache *hit* path, and the one
            # that would serve a stale frame.
            emit(label, "ok" if (first and agrees()) else "stale")

        # The progress overlay counts seconds, so it must never be cached: a
        # frozen progress bar is the exact appearance of the hang it denies.
        gui.progress.begin("Working", message="step")
        gui.progress.update(0.25, "quarter")
        first = gui.chrome_fingerprint()
        gui.progress.update(0.5, "half")
        emit("progress_rebuilds", "ok" if gui.chrome_fingerprint() != first else "frozen")
        gui.progress.end()

        # A selection past the threshold deliberately never compares equal, so
        # the frame rebuilds -- which is what happened before the cache existed.
        if gui.sequences:
            row = gui.sequences[0]
            keep = row.selected
            row.selected = set(range(gui.SELECTION_HASH_MAX + 1))
            same = gui.chrome_fingerprint() == gui.chrome_fingerprint()
            row.selected = keep
            emit("huge_selection_rebuilds", "frozen" if same else "ok")
    """)


@pytest.mark.parametrize("interaction", INTERACTIONS)
def test_the_cached_chrome_matches_a_fresh_build(swept, interaction):
    """After every interaction, cached vertices equal freshly emitted ones."""
    assert swept.get(interaction) == "ok", f"stale chrome after: {interaction}"


def test_an_animating_overlay_is_never_cached(swept):
    """The progress overlay counts seconds, so it must rebuild every frame."""
    assert swept.get("progress_rebuilds") == "ok"


def test_a_huge_selection_falls_back_to_rebuilding(swept):
    """Hashing 234,184 selected residues costs more than the paint it saves."""
    assert swept.get("huge_selection_rebuilds") == "ok"
