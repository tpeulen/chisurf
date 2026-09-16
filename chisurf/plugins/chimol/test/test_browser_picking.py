"""Where the browser *draws* the molecule is where it *picks* it.

Why this file exists twice over
------------------------------
The page could rotate the molecule and never select anything: ``Viewer.press``
sent the pointer either to the panel or to the trackball, there was no third
case, so every click was consumed as a zero-length drag and
``Viewer.handle_mouse_click`` was never called from the browser at all.

Then it picked, and picked in the **wrong place** -- by up to 150 CSS pixels,
worsening toward the right edge. The page drew into ``(0, 0, scene_w*dpr,
height)``, where its own ``scene_width`` subtracted the panel's column, and
projected through a renderer that reserved no column at all. Two rectangles,
one molecule.

And a test caught neither, because the test **projected an atom and clicked
where the projection said it was**. That is self-consistent under any
projection, right or wrong: it proves the click reaches the picker and says
nothing about whether the picker agrees with the picture. So the check here
renders a frame, finds the molecule's *pixels*, and clicks those.
"""
from __future__ import annotations

import pathlib



_PDB = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
)


#: Run in a subprocess with ``CHIMOL_TOOLKIT=none``, which is the browser's
#: configuration and cannot be reached in-process.
#:
#: ``Viewer``'s base class is chosen by :mod:`chimol.hosts.toolkit` at
#: class-definition time, so by the time any test runs, ``view.py`` is imported
#: and the choice is made. An earlier version of this file asked for a
#: ``QApplication`` instead -- which made the tests pass while exercising the
#: **Qt** viewer, the one configuration the page never runs. Proving the
#: windowless path takes a fresh interpreter, the same way
#: ``test_engine_is_portable`` proves a module loads without a toolkit.
_SCRIPT = r"""
import os, sys
import numpy as np

from chimol_pkg.viewport.headless import SceneSink
from chimol_pkg.core.viewer import Viewer
from chimol_pkg.render.wgpu_backend import WgpuMeshRenderer
from chimol_pkg.commands import Cmd
from chimol_pkg.hosts.base import ViewerHost
from emtk.events import LEFT_BUTTON  # emtk is its own package, not chimol's
from chimol_pkg.hosts.toolkit import HAS_QT

assert not HAS_QT, "the toolkit was not stripped; this is not the page's configuration"

# A page's numbers, not a test's: a canvas of 1280x860 CSS pixels on a 2x
# display. The ratio is the point -- every unit confusion in this seam is a
# factor of two, and at dpr 1 both spellings agree and the test proves nothing.
CSS = (1280, 860)
DPR = 2.0

view = Viewer(renderer_factory=SceneSink)
sink = view.renderer
assert sink.widget() is None, "this backend is supposed to be windowless"
assert view._pick_surface() is not None, "a renderer that projects can pick"

sink.set_pixel_ratio(DPR)
sink.resize_viewport(int(CSS[0] * DPR), int(CSS[1] * DPR))
assert (sink.width(), sink.height()) == CSS, (sink.width(), sink.height())

gui = sink.internal_gui
gui.visible = True
gui.sequence_visible = True
from chimol_pkg.ui.menus.bar import MENU_BAR, TOOLBAR
gui.menubar = [(t, e) for t, e in MENU_BAR if e]
gui.toolbar = list(TOOLBAR)

cmd = Cmd(ViewerHost(view))
cmd.set_message_callback(lambda _m: None)
cmd.set_error_callback(lambda _m: None)
cmd.do("load " + sys.argv[1])
cmd.do("as cartoon")

# The frame the page draws, into the target the page draws into. `render` and
# `render_into` differ only in where the pixels land, so this is the browser's
# own picture -- built from `frame_arguments`, which is the single description
# of a frame both hosts use.
arguments = sink.frame_arguments()
scene = arguments.pop("scene")
view_state = arguments.pop("view_state")
# The chrome is left off *for the hunt only*: the panel's quads are pixels too,
# and "not the background" has to mean the molecule.
arguments["chrome"] = None
arguments["overlay"] = None
gpu = WgpuMeshRenderer(*sink._physical_size())
image = np.asarray(gpu.render(scene, view_state, **arguments))[..., :3].astype(np.int16)

background = np.asarray(
    [int(round(c * 255)) for c in sink._background_rgb()], dtype=np.int16
)
lit = np.abs(image - background).max(axis=2) > 8
ys, xs = np.nonzero(lit)
assert len(xs), "the frame is empty; nothing to compare against"

# Where the molecule was drawn, and where the projection says it is. Compared
# on the geometry that was actually drawn -- the packed vertices -- rather than
# on the atoms: a cartoon is a smoothed backbone ribbon, so an atom bounding box
# is tens of pixels wider than its picture and no honest tolerance survives it.
drawn = (xs.min() / DPR, ys.min() / DPR, xs.max() / DPR, ys.max() / DPR)
vertices = np.concatenate(
    [np.asarray(o.geometry.positions, dtype=float) for o in scene.objects]
)
px, py, visible = sink.project_to_screen(vertices)
px, py = px[visible], py[visible]
projected = (px.min(), py.min(), px.max(), py.max())

# Three pixels: a triangle's edge is antialiased and an impostor is a quad
# slightly larger than the sphere it stands for. The failure this guards is a
# hundred pixels wide.
TOLERANCE = 3.0
offset = [abs(drawn[i] - projected[i]) for i in range(4)]
assert max(offset) <= TOLERANCE, (
    "the browser draws the molecule somewhere other than it projects it: "
    f"drawn {tuple(round(v, 1) for v in drawn)} vs "
    f"projected {tuple(round(v, 1) for v in projected)} "
    f"(offsets {[round(v, 1) for v in offset]} CSS px)"
)

# And the click itself, on a *drawn* pixel rather than a projected one. The
# first press on a fresh viewer puts the info panel down -- that is the shared
# behaviour of every host -- so it is spent deliberately before the real one.
sink.on_pointer_press(1.0, 1.0, LEFT_BUTTON, 0)
sink.on_pointer_release(1.0, 1.0, LEFT_BUTTON, 0)

middle = len(xs) // 2
order = np.argsort(xs)
picked = None
for index in (order[middle], order[len(order) // 4], order[-len(order) // 4]):
    x, y = float(xs[index]) / DPR, float(ys[index]) / DPR
    if gui.wants(x, y):  # the floating panel is over this pixel
        continue
    picked = (x, y)
    break
assert picked is not None, "every sampled pixel of the molecule is under the panel"

before = set(view._selected_residues or ())
sink.on_pointer_press(picked[0], picked[1], LEFT_BUTTON, 0)
sink.on_pointer_release(picked[0], picked[1], LEFT_BUTTON, 0)
after = set(view._selected_residues or ())
assert after != before, f"clicking a lit pixel at {picked} selected nothing"
# The residue, not the atom: a click toggles the picked atom's *residue* in and
# out of the selection -- PyMOL's `+/-`. `_selected_atoms` stays empty here and
# that is the design, not a half-done pick.

if os.environ.get("CHIMOL_CHECK_EMPTY_CLICK") != "1":
    print("OK")
    raise SystemExit(0)

# PyMOL: "left-clicking away from any atom should deactivate the selection".
# An empty point *inside* the viewport, found from the frame rather than
# guessed: a coordinate off the surface entirely is not what a user can click,
# and a click the viewer never considers proves nothing about the rule.
dark = ~lit
empty = None
for cy in range(4, image.shape[0], 16):
    for cx in range(4, image.shape[1], 16):
        window = dark[max(cy - 40, 0):cy + 40, max(cx - 40, 0):cx + 40]
        if window.all() and not gui.wants(cx / DPR, cy / DPR):
            empty = (cx / DPR, cy / DPR)
            break
    if empty:
        break
assert empty is not None, "the molecule covers the whole viewport; nowhere to miss"
sink.on_pointer_press(empty[0], empty[1], LEFT_BUTTON, 0)
sink.on_pointer_release(empty[0], empty[1], LEFT_BUTTON, 0)
assert not set(view._selected_residues or ()), "empty space left the selection up"

print("OK")
"""


def _run_in_page_configuration(tmp_path):
    """Run :data:`_SCRIPT` with no toolkit, and return its output."""
    import os
    import subprocess
    import sys

    pkg = pathlib.Path(__import__("chimol").__file__).resolve().parent
    script = tmp_path / "page_config.py"
    script.write_text(
        "import sys, importlib\n"
        f"sys.path.insert(0, {str(pkg.parent)!r})\n"
        "import chimol as chimol_pkg\n"
        "sys.modules['chimol_pkg'] = chimol_pkg\n" + _SCRIPT,
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["CHIMOL_TOOLKIT"] = "none"
    env["CHIMOL_SETTINGS_DIR"] = str(tmp_path / "settings")
    return subprocess.run(
        [sys.executable, str(script), str(_PDB)],
        capture_output=True, text=True, env=env, timeout=600,
    )


def test_the_browser_picks_where_it_draws(tmp_path):
    """The page's configuration, end to end: no Qt, no window, a real frame.

    Covers two failures at once -- the pick that was never asked for, and the
    pick that was asked for in a rectangle the frame was not drawn into.
    """
    result = _run_in_page_configuration(tmp_path)
    assert result.returncode == 0, (
        "picking failed in the toolkit-free configuration:\n"
        + result.stdout[-4000:] + "\n" + result.stderr[-4000:]
    )
    assert "OK" in result.stdout


def test_a_click_in_empty_space_clears_the_selection(tmp_path):
    """The other half of PyMOL's click rule: clicking away deselects.

    This was a strict ``xfail``, and it was **the test that was wrong**, not
    the viewer. It reached past the mode table into
    ``handle_mouse_click(event)`` with no action, and it looked for empty space
    by distance from *projected* atoms -- which, with the projection and the
    frame disagreeing, could be squarely on the drawn molecule. Asked properly
    -- a press and a release, at a pixel the frame shows as background -- the
    rule holds.
    """
    import os

    env_key = "CHIMOL_CHECK_EMPTY_CLICK"
    os.environ[env_key] = "1"
    try:
        result = _run_in_page_configuration(tmp_path)
    finally:
        os.environ.pop(env_key, None)
    assert result.returncode == 0, (
        result.stdout[-3000:] + "\n" + result.stderr[-3000:]
    )


def test_the_browser_delivers_the_same_gestures_as_the_desktop():
    """One host claiming fewer gestures is a control nobody can reach.

    Judged against :class:`~chimol.hosts.native.canvas.CanvasView` -- the
    toolkit-free desktop host, which is the like-for-like reference: both are a
    canvas, a command layer and the in-viewport chrome, and neither has a
    ``QPainter``.
    """
    from chimol.hosts.native.canvas import CanvasView
    from chimol.hosts.web.page import Page

    # A *windowed* toolkit-free canvas is the comparison. `file_drop` is
    # answered by the canvas rather than declared on the class -- an offscreen
    # canvas has no window to drop on -- so the reference is the base set plus
    # the drop a real window delivers, which is what the page delivers too.
    windowed = CanvasView._BASE_FEATURES | {"file_drop"}
    assert Page.supported_features == windowed


def test_the_browser_takes_its_scene_rectangle_from_the_renderer():
    """The page must not compute a second scene column of its own.

    The first version did, and the two disagreed by the panel's 220-pixel
    column -- which is a click landing where the molecule is not. Asserted as
    *delegation* rather than as an equal number: two implementations that agree
    today are two implementations.
    """
    from chimol.hosts.web.page import Page

    for name in ("scene_width", "scene_height"):
        source = Page.__dict__[name].__code__.co_names
        assert "sink" in source and name in source, (
            f"Viewer.{name} does not ask the renderer for it"
        )
