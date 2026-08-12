"""The chrome is cached between frames, and must never draw a stale one.

Why this test exists
--------------------
The chrome is immediate mode: every frame rebuilds ~2,800 quads from scratch,
and on an integrative model that was **most of the frame** while the molecule
itself cost about a millisecond. But the chrome changes on hover, focus and
state -- not on camera motion, which is the only time anybody is watching the
frame rate. So :meth:`CanvasRenderer._chrome_quads` reuses the previous frame's
vertices whenever :meth:`InternalGui.chrome_fingerprint` has not moved.

That trade has exactly one failure mode, and it is silent: a fingerprint that
omits something the paint reads shows a **stale picture**. Nothing raises,
nothing is logged, and it looks like a redraw bug somewhere else entirely.

So this test does not check the cache's *hits*; it checks its *answers*. For a
sweep of real interactions it compares what the cached path returns against a
freshly emitted build, and demands they be identical. Written first, it caught
two genuine omissions on the first run:

* ``SequenceRow.selected`` -- the strip highlights the selection, and the set is
  mutated **in place** in three separate places, so neither the row's identity
  nor the sequence list's length notices;
* the **command-line feedback log** -- every command appends a line, which is
  drawn as text. ``select everything`` moved nine quads with the rows, the
  sequences and the windows all unchanged, which is what pointed at it.

Anyone adding state that ``paint`` reads must add it to the fingerprint, and
this is what will tell them.
"""
from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("CHIMOL_TOOLKIT", "none")
os.environ.setdefault("CHIMOL_CANVAS", "offscreen")


@pytest.fixture(scope="module")
def app():
    """A real offscreen viewer with a structure in it."""
    run = pytest.importorskip("chisurf.plugins.chimol.chimol.host.run")
    try:
        instance = run.ChimolApp(backend="offscreen", size=(1100, 760))
    except Exception as exc:  # pragma: no cover - no WebGPU adapter here
        pytest.skip(f"no offscreen renderer: {exc}")
    instance.cmd.do("fetch 148L")
    instance.cmd.do("zoom all")
    return instance


def _fresh(app) -> np.ndarray | None:
    """Emit the chrome without consulting the cache."""
    from chisurf.plugins.chimol.chimol.renderer.ui.quad_painter import QuadPainter

    renderer, gui = app.renderer, app.renderer._internal_gui
    painter = QuadPainter(scale=renderer._ratio(), font_scale=gui.ui_scale)
    gui.paint(painter)
    vertices = painter.vertices()
    return vertices if len(vertices) else None


def _agree(app) -> bool:
    """Whether the cached path and a fresh build produce the same vertices."""
    cached = app.renderer._chrome_quads()
    fresh = _fresh(app)
    if cached is None or fresh is None:
        return cached is None and fresh is None
    return cached.shape == fresh.shape and np.array_equal(cached, fresh)


#: Each is applied in order, and the chrome is compared after it **and** again
#: after that -- the second comparison is the one that exercises a cache *hit*,
#: since by then the fingerprint has not moved.
INTERACTIONS = [
    ("idle", lambda app: None),
    ("hover the panel", lambda app: app.renderer._internal_gui.mouse_move(1000, 130)),
    ("hover the scene", lambda app: app.renderer._internal_gui.mouse_move(400, 400)),
    ("open a menu", lambda app: app.renderer._internal_gui.mouse_press(30, 10)),
    ("move within it", lambda app: app.renderer._internal_gui.mouse_move(40, 60)),
    ("dismiss it", lambda app: app.renderer._internal_gui.dismiss_overlays(400, 400)),
    ("show info", lambda app: app.cmd.do("info")),
    ("hide info", lambda app: app.cmd.do("info")),
    ("spectrum", lambda app: app.cmd.do("spectrum b")),
    ("colour", lambda app: app.cmd.do("color red")),
    ("hide cartoon", lambda app: app.cmd.do("hide cartoon")),
    ("show spheres", lambda app: app.cmd.do("show spheres")),
    ("debug on", lambda app: app.cmd.do("debug on")),
    ("debug off", lambda app: app.cmd.do("debug off")),
    ("chrome scale", lambda app: app.cmd.do("set ui_scale, 1.29")),
    ("chrome scale back", lambda app: app.cmd.do("set ui_scale, 1.0")),
    ("resize", lambda app: app.renderer.resize(950, 700)),
    ("resize back", lambda app: app.renderer.resize(1100, 760)),
    ("select", lambda app: app.cmd.do("select everything")),
    ("deselect", lambda app: app.cmd.do("deselect")),
    ("a second object", lambda app: app.cmd.do("fetch 1crn")),
    ("delete it", lambda app: app.cmd.do("delete 1crn")),
]


@pytest.mark.parametrize("label,act", INTERACTIONS, ids=[i[0] for i in INTERACTIONS])
def test_the_cached_chrome_matches_a_fresh_build(app, label, act):
    """After every interaction, cached vertices equal freshly emitted ones."""
    act(app)
    assert _agree(app), f"stale chrome after: {label}"
    # Again, with nothing changed in between: this is the cache *hit* path, and
    # the one that would serve a stale frame.
    assert _agree(app), f"stale chrome on the second frame after: {label}"


def test_an_animating_overlay_is_never_cached(app):
    """The progress overlay counts seconds, so it must rebuild every frame.

    A frozen progress bar is worse than no progress bar: it is the exact
    appearance of the hang it exists to deny.
    """
    gui = app.renderer._internal_gui
    gui.progress.begin("Working", message="step")
    try:
        gui.progress.update(0.25, "quarter")
        first = gui.chrome_fingerprint()
        gui.progress.update(0.5, "half")
        assert gui.chrome_fingerprint() != first
    finally:
        gui.progress.end()


def test_a_huge_selection_falls_back_to_rebuilding(app):
    """The selection is hashed only while that is cheaper than the paint.

    Past the threshold the fingerprint deliberately never compares equal, so the
    frame rebuilds -- which is the behaviour there was before the cache, and so
    is never worse than it.
    """
    gui = app.renderer._internal_gui
    if not gui.sequences:
        pytest.skip("no sequence rows to select in")
    row = gui.sequences[0]
    original = row.selected
    try:
        row.selected = set(range(gui.SELECTION_HASH_MAX + 1))
        assert gui.chrome_fingerprint() != gui.chrome_fingerprint()
    finally:
        row.selected = original
