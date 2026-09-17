"""What is drawn on top is what takes the click.

The chrome's draw order is one hand-written sequence (``paint_under`` then the
windows then ``paint_over``) and its hit order is a *different* hand-written
sequence -- a ladder of ``if`` tests in ``hit_test``. The two must be exact
inverses, and nothing checks that they are. The source records two bugs from
them drifting, in its own words::

    # Order matters and cost a test: tried above the windows first, and a
    # `help` listing tall enough to reach the mouse block then swallowed every
    # click meant for it -- the mode line stopped cycling. Hit order has to
    # match paint order, and the windows are painted last.

and the reason the info panel had no hit kind at all was the same fault from
the other side: a press over a page of ``help`` fell through to the camera and
rotated the molecule under the text being read.

The invariant, stated once here rather than maintained twice by hand: at any
point where two pieces of chrome overlap, the one painted **later** is the one
``hit_test`` names. Elements that never overlap can be in any relative order in
either list and nothing notices -- which is exactly why this drifts unpunished
until someone opens a panel that reaches a little further than before.
"""

from __future__ import annotations

import pytest
from chimol.ui.gui.layers import CHROME_LAYERS
from toolkit_free import probe

#: Bottom to top -- **read from the stack**, not restated here. A test that
#: kept its own copy of the order would be a fourth list to drift.
PAINT_ORDER = [layer.key for layer in CHROME_LAYERS]

SCRIPT = f'''
app = open_app(size=(1200, 820))
cmd, viewer = app.cmd, app.viewer
gui = viewer.gui
cmd.do("load 148l.pdb")
cmd.do("panels_all on")
app.renderer._draw()

PAINT_ORDER = {PAINT_ORDER!r}

def rects():
    """Where each piece of chrome is, as predicates on a point."""
    def window_at(x, y):
        return gui._window_hit(x, y) is not None

    def menu_at(x, y):
        return gui._menu_at(x, y)[0] is not None

    def panel_row(x, y):
        return any(r.contains(x, y) for r in gui._row_rects)

    return {{
        "info": lambda x, y: gui.info_contains(x, y),
        "sequence": lambda x, y: (gui.visible and gui.sequence_visible
                                  and (gui._seq_strip.contains(x, y)
                                       or gui._seq_track.contains(x, y))),
        "column": lambda x, y: gui.visible and gui.docked and gui.panel_rect.contains(x, y),
        "panel": lambda x, y: gui.visible and any(r.contains(x, y) for r in gui._row_rects),
        "wizard": lambda x, y: gui.visible and gui._wizard_rect.contains(x, y),
        "block": lambda x, y: gui.visible and gui._block.contains(x, y),
        "prompt": lambda x, y: False,
        "command": lambda x, y: gui.command_line.visible and gui._cmd_rect.contains(x, y),
        "nerd": lambda x, y: bool(gui.nerd and gui.nerd_lines) and _in(gui.nerd_rect(), x, y),
        "windows": window_at,
        "menubar": lambda x, y: gui._menubar_hit(x, y) is not None,
        "toolbar": lambda x, y: gui._toolbar_hit(x, y) is not None,
        "splitter": lambda x, y: gui.visible and gui.docked and gui._splitter.contains(x, y),
        "status": lambda x, y: gui._ui_scale_rect.contains(x, y),
        "menu": menu_at,
        "tour": lambda x, y: (gui._tour_next_rect.contains(x, y)
                              or gui._tour_close_rect.contains(x, y)),
        "tooltip": lambda x, y: False,
        "progress": lambda x, y: False,
    }}

def _in(box, x, y):
    bx, by, bw, bh = box
    return bx <= x < bx + bw and by <= y < by + bh

where = rects()

#: kinds `hit_test` may answer that mean the same element as the key.
SAME = {{
    "sequence": {{"sequence", "residue", "scrollbar"}},
    # The mouse-mode block *is* a window when the panels are floating -- its
    # rect and the `mouse` window's body are the same pixels -- so a click
    # there resolving to either is the same element answering.
    # The object list and the mouse-mode block are *windows* when the panels
    # float: their rects and their windows' bodies are the same pixels, so a
    # click resolving to either is the same element answering.
    "windows": {{"window", "wintitle", "winbody", "winclose", "wincollapse",
                "winresize", "row", "eye", "button", "group", "measurement",
                "name", "panel", "objects_bar",
                "block", "mode", "selecting", "timeline", "stride", "average",
                "movie", "playback_slider"}},
    "status": {{"uiscale", "status"}},
    "splitter": {{"splitter"}},
    "column": {{"row", "eye", "button", "group", "measurement", "name", "panel",
               "objects_bar", "block", "mode",
               "selecting", "timeline", "stride", "average", "movie",
               "playback_slider", "wizard", "sequence", "residue", "scrollbar",
               ""}},
    "panel": {{"row", "eye", "button", "group", "measurement", "name", "panel",
              "objects_bar"}},
    "block": {{"block", "mode", "selecting", "timeline", "stride", "average",
              "movie", "playback_slider"}},
    "wizard": {{"wizard"}},
    "info": {{"info"}},
    "command": {{"command"}},
    "nerd": {{"nerd"}},
    "menubar": {{"menubar"}},
    "toolbar": {{"toolbar"}},
    "menu": {{"menu"}},
    "tour": {{"tour"}},
}}

def topmost(x, y):
    """The piece painted last at this point -- the one the eye sees."""
    found = None
    for name in PAINT_ORDER:
        try:
            if where[name](x, y):
                found = name
        except Exception:
            continue
    return found

bad = {{}}
overlaps = 0
for y in range(2, 818, 3):
    for x in range(2, 1198, 3):
        painted = topmost(x, y)
        if painted is None:
            continue
        # Only where two pieces actually overlap is the order observable.
        covering = [n for n in PAINT_ORDER if where[n](x, y)]
        if len(covering) < 2:
            continue
        overlaps += 1
        kind = str(gui.hit_test(x, y).kind)
        if kind not in SAME.get(painted, {{painted}}):
            key = "%s over %s -> hit %s" % ("+".join(covering), painted, kind or "(scene)")
            bad[key] = bad.get(key, 0) + 1

emit("overlapping_points", overlaps)
emit("panels", ",".join(sorted(w.key for w in gui.windows if w.visible)))
emit("mismatches", "; ".join("%s x%d" % (k, v) for k, v in sorted(bad.items())) or "none")
'''


@pytest.fixture(scope="module")
def sampled():
    return probe(SCRIPT, timeout=900)


def test_the_sample_actually_found_overlapping_chrome(sampled):
    """Otherwise the check below proves nothing."""
    assert sampled["panels"], "no panels were open"
    assert int(sampled["overlapping_points"]) > 100, sampled["overlapping_points"]


def test_the_topmost_thing_drawn_is_the_thing_clicked(sampled):
    assert sampled["mismatches"] == "none", (
        "hit order disagrees with paint order: " + sampled["mismatches"]
    )


# --------------------------------------------------------------------------- #
# ...and a layer is only hit where it actually drew
# --------------------------------------------------------------------------- #
COVERAGE = '''
from emtk.testing import RecordingPainter
from chimol.ui.gui.layers import CHROME_LAYERS

app = open_app(size=(1200, 820))
cmd, viewer = app.cmd, app.viewer
gui = viewer.gui
cmd.do("load 148l.pdb")
cmd.do("panels_all on")
app.renderer._draw()

def painted_boxes(layer):
    """Every rectangle this layer put on screen, this frame."""
    p = RecordingPainter()
    getattr(gui, layer.paint)(p)
    boxes = []
    for call in p.calls:
        kind = call[0]
        if kind in ("fill_rect", "stroke_rect", "gradient_rect", "text"):
            boxes.append(tuple(float(v) for v in call[1:5]))
        elif kind == "fill_triangle":
            xs = [pt[0] for pt in call[1:4]]
            ys = [pt[1] for pt in call[1:4]]
            boxes.append((min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)))
    return boxes

def covers(boxes, x, y, slack=2.0):
    for bx, by, bw, bh in boxes:
        if bx - slack <= x <= bx + bw + slack and by - slack <= y <= by + bh + slack:
            return True
    return False

bad = {}
tested = 0
for layer in CHROME_LAYERS:
    if layer.hit is None or layer.key == "windows":
        continue                      # windows paint themselves, one per body
    boxes = painted_boxes(layer)
    hit = getattr(gui, layer.hit)
    for y in range(2, 818, 5):
        for x in range(2, 1198, 5):
            if hit(x, y) is None:
                continue
            tested += 1
            if not covers(boxes, x, y):
                bad[layer.key] = bad.get(layer.key, 0) + 1

emit("hit_points_tested", tested)
emit("hit_outside_paint", "; ".join("%s x%d" % kv for kv in sorted(bad.items())) or "none")
'''


@pytest.fixture(scope="module")
def coverage():
    return probe(COVERAGE, timeout=900)


def test_a_layer_is_only_clickable_where_it_drew(coverage):
    """Dear ImGui gets this for free and chimol does not.

    There, hit-testing is a *by-product* of drawing: every widget calls
    ``ItemAdd(bb, id)`` as it is submitted, recording the rectangle it just
    drew, and ``ItemHoverable`` tests that same rectangle (``imgui.cpp``,
    ``ItemAdd`` / ``ItemHoverable``). A widget cannot be clickable somewhere it
    did not draw, because there is only one rectangle.

    Here the two are separate methods reading a shared layout, so they *can*
    disagree -- a layer that draws in one place and answers presses in another
    is a click that lands on nothing, or a dead patch over something live. This
    is that guarantee as a test rather than as a structure.
    """
    assert int(coverage["hit_points_tested"]) > 100, "nothing was hit-testable"
    assert coverage["hit_outside_paint"] == "none", (
        "clickable where nothing was drawn: " + coverage["hit_outside_paint"]
    )
