"""Where a wheel notch goes, and why that is not obvious.

The viewport is one surface with several scrollable things stacked on it: an
open menu, the info panel, the sequence strip, and the molecule behind them
all. A notch belongs to exactly one of them, and the rule is *what is under the
pointer*, not *what has focus* -- there is no focus here.

Two mistakes are easy and neither raises:

1. **Routing by the wrong reachability.** ``scroll_info`` used to be called only
   from inside ``scroll_menu``, which itself only runs when a menu is open. So
   the info panel was scrollable *only while a menu happened to be open*, which
   is never in practice, and every other notch fell through to the camera --
   pointing at a ``help`` listing longer than the panel and turning the wheel
   zoomed the molecule behind it and left the text where it was.

2. **Treating "did not move" as "not mine".** At either end of its travel a
   panel has nowhere to go. If the router reads that as "not consumed", the
   notch falls through and the molecule *behind the text* zooms -- so scrolling
   to the bottom of a listing and continuing quietly starts moving the camera.

Why this runs in a subprocess
-----------------------------
The routing lives in the toolkit-free :mod:`chimol.renderer.canvas_base`, and
exercising it needs the toolkit-free viewer -- which is selected by
``CHIMOL_TOOLKIT=none`` **before** ``renderer.view`` is imported, because
``class MolView(WidgetBase)`` binds its base at class-definition time.

That is process-wide, and setting it here first cost four failures in
``test_headless_scene.py``: every later test in the session then had a viewer
that was no longer a ``QWidget``. Setting it *back* is not available either --
the base is already bound. And simply not setting it does not work: with Qt
present ``MolView`` is a ``QWidget``, and building one over an offscreen
``rendercanvas`` surface aborts the interpreter.

So the whole probe runs in a child process, which is the same device
``test_engine_is_portable.py`` uses and for the same reason: a global that can
only be set once is a global that has to be set somewhere disposable.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import textwrap

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[4]
_PDB = _ROOT / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"

#: The probe. Each check prints ``name=PASS`` or ``name=FAIL: why``, so a
#: failure names the behaviour rather than only the exit status.
_PROBE = '''
import sys

failures = []


def check(name, condition, why=""):
    print(f"{name}={'PASS' if condition else 'FAIL: ' + why}")
    if not condition:
        failures.append(name)


from chisurf.plugins.chimol.chimol.host.run import ChimolApp

app = ChimolApp(backend="offscreen", size=(900, 640))
app.load(PDB)
app.cmd.do("help")          # a listing far longer than the panel
app.draw_frame()

renderer = app.renderer
gui = renderer._internal_gui
rect = gui._info_rect
inside = (rect.x + rect.w / 2.0, rect.y + rect.h / 2.0)
outside = (min(rect.x + rect.w + 150.0, 895.0), rect.y + 50.0)


def wheel(point, dy):
    renderer._on_wheel({"x": point[0], "y": point[1], "dy": dy, "modifiers": []})


check("panel_is_scrollable", gui.info_visible and gui.info_max_scroll() > 0,
      "nothing to scroll, so the rest proves nothing")
check("no_menu_open", not gui.has_menu(), "a menu was open; the old path would pass")

# 1. the notch reaches the panel with no menu open
before = gui._info_scroll
wheel(inside, 100)
check("wheel_reaches_info", gui._info_scroll > before, "the panel did not move")

# 2. and it does not also move the camera
distance = renderer._distance
wheel(inside, 100)
check("info_does_not_zoom", abs(renderer._distance - distance) < 1e-9,
      "the notch scrolled the panel and zoomed the scene behind it")

# 3. at the end of its travel the panel keeps the notch
wheel(inside, -100)
wheel(inside, -100)
check("scrolled_to_top", gui._info_scroll == 0, "expected to be back at the top")
distance = renderer._distance
wheel(inside, -100)
check("end_of_travel_consumed", abs(renderer._distance - distance) < 1e-9,
      "a notch at the top fell through to the camera")

# 4. the ordinary case still works
distance = renderer._distance
wheel(outside, -100)
check("scene_still_zooms", abs(renderer._distance - distance) > 1e-9,
      "the wheel stopped zooming the scene")

# 5. hiding the panel hands its area back
gui.info_visible = False
check("hidden_panel_not_hit", not gui.info_contains(*inside), "still claiming the point")
distance = renderer._distance
wheel(inside, -100)
check("hidden_panel_zooms", abs(renderer._distance - distance) > 1e-9,
      "the hidden panel still swallowed the notch")

# 6. Escape puts the panel away, but only once the prompt has let go of it
app.cmd.do("help")
app.draw_frame()
gui.info_visible = True
gui.focus_command(True)
from chisurf.plugins.chimol.chimol.host.keys import KEY_ESCAPE
gui.key_press(KEY_ESCAPE, "", 0)
check("esc_leaves_prompt_first", gui.info_visible and not gui.command_line.focused,
      "the first Escape closed the panel instead of leaving the prompt")
gui._info_scroll = 5
gui.key_press(KEY_ESCAPE, "", 0)
check("esc_closes_info", not gui.info_visible, "Escape did not close the info panel")
check("esc_resets_scroll", gui._info_scroll == 0,
      "the next answer would open part-way down")

# 7. the listing is live: hover describes, click types, and a press on the
#    panel never reaches the camera
app.cmd.do("help")
app.draw_frame()
gui.info_visible = True
from chisurf.plugins.chimol.chimol.renderer.internal_gui import char_width
rect = gui._info_rect
cw = char_width(gui.FONT_PT)
spot = (rect.x + gui.PAD + 2 * cw + 1, rect.y + gui.PAD + 3 * gui.INFO_ROW_H + 2)
token = gui.info_token_at(*spot)
check("token_under_cursor", bool(token), "no word found under a name in the listing")
check("hit_kind_is_info", gui.hit_test(*spot).kind == "info",
      "the panel is not hit-tested, so a press falls through to the camera")
described = gui.info_describe(token) if token else None
check("hover_describes", bool(described) and token in described,
      f"no description for {token!r}")
distance = renderer._distance
gui.command_line.text = ""
gui.mouse_press(*spot)
check("click_types_at_prompt", gui.command_line.text.strip().startswith(token or "!"),
      f"clicking {token!r} left the prompt as {gui.command_line.text!r}")
check("click_does_not_rotate", abs(renderer._distance - distance) < 1e-9,
      "the press on the listing also moved the camera")
check("click_closes_listing", not gui.info_visible,
      "picking a name left the listing covering the prompt it was typed into")

# and all three closers through the *renderer*, which is what the window calls
from chisurf.plugins.chimol.chimol.host.events import LEFT_BUTTON
for label, act in (
    ("esc", lambda: renderer.on_key_press(KEY_ESCAPE, "", 0)),
    ("outside", lambda: renderer.on_pointer_press(
        rect.x + rect.w + 60.0, rect.y + 40.0, LEFT_BUTTON, 0)),
    ("on_cmd", lambda: renderer.on_pointer_press(*spot, LEFT_BUTTON, 0)),
):
    app.cmd.do("help")
    app.draw_frame()
    gui.info_visible = True
    # Escape is layered: a focused prompt takes it first, which is deliberate.
    # The earlier click_types_at_prompt check leaves the prompt focused, so the
    # precondition has to be reset or this measures the layering, not the close.
    gui.focus_command(False)
    act()
    # Draw a frame before believing it. `refresh_gui_state` re-asserts
    # `info_visible` from the viewer every frame, so a close that only clears
    # the chrome's copy survives exactly until the next one -- which is what
    # made this look fixed while the app still ignored Escape.
    app.draw_frame()
    check(f"renderer_close_{label}", not gui.info_visible,
          f"the listing survived {label} through the renderer's own entry point")

# 8. clicking away dismisses the panel but never the chrome
app.cmd.do("help")
app.cmd.do("settings_panel")
app.draw_frame()
before = {w.key for w in gui.windows if w.visible}
gui.dismiss_overlays(rect.x + rect.w + 40.0, rect.y + rect.h - 20.0)
after = {w.key for w in gui.windows if w.visible}
check("click_away_closes_info", not gui.info_visible, "the panel stayed open")
check("click_away_closes_settings", "settings" not in after, "Settings stayed open")
check("click_away_keeps_chrome", {"mouse", "objects"} & before <= after,
      "a click away also closed the object list / mouse block")

app.close()
sys.exit(1 if failures else 0)
'''


@pytest.fixture(scope="module")
def probe():
    """Run the whole probe once in a toolkit-free child process."""
    pytest.importorskip("rendercanvas", reason="the canvas host needs rendercanvas")
    if not _PDB.is_file():
        pytest.skip(f"missing fixture {_PDB}")

    env = dict(os.environ)
    env["CHIMOL_TOOLKIT"] = "none"
    # Never write into the developer's own settings while testing.
    env.setdefault("CHIMOL_SETTINGS_DIR", str(_ROOT / "build" / "test-chimol-settings"))
    script = f"PDB = {str(_PDB)!r}\n" + textwrap.dedent(_PROBE)
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, cwd=str(_ROOT), env=env,
    )
    results = dict(
        line.split("=", 1)
        for line in result.stdout.splitlines()
        if "=" in line and not line.startswith(" ")
    )
    if not results:
        pytest.fail(
            "the wheel probe produced nothing:\n"
            + (result.stdout + result.stderr)[-3000:]
        )
    return results


@pytest.mark.parametrize(
    "check",
    [
        "panel_is_scrollable",
        "no_menu_open",
        "wheel_reaches_info",
        "info_does_not_zoom",
        "scrolled_to_top",
        "end_of_travel_consumed",
        "scene_still_zooms",
        "hidden_panel_not_hit",
        "hidden_panel_zooms",
        "esc_leaves_prompt_first",
        "esc_closes_info",
        "esc_resets_scroll",
        "token_under_cursor",
        "hit_kind_is_info",
        "hover_describes",
        "click_types_at_prompt",
        "click_does_not_rotate",
        "click_closes_listing",
        "renderer_close_esc",
        "renderer_close_outside",
        "renderer_close_on_cmd",
        "click_away_closes_info",
        "click_away_closes_settings",
        "click_away_keeps_chrome",
    ],
)
def test_wheel_goes_where_the_pointer_is(probe, check):
    """Each routing rule, reported separately so a failure names itself."""
    assert check in probe, f"the probe never reached {check}"
    assert probe[check] == "PASS", probe[check]
