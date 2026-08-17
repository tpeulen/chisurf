"""Menus and picks on the **page** -- real DOM clicks, replayed in order.

What broke, and why a page test
-------------------------------
Every menu on the browser page opened and closed within one click: the
menu bar, the object list's ``A/S/H/L/C`` buttons, the right-click object
menu. ``Viewer.release`` in ``hosts/web/page.py`` rebuilt the whole panel after
*every* release ("so the sequence strip follows the pick") and
``InternalGui.set_rows`` dismisses menus -- so the release of the click
that opened a menu put it away before a frame was drawn. The Qt window and
the toolkit-free host never did that, which is why no probe saw it: the
defect was in the browser host's own twenty lines, and only the page runs
them.

The second failure this replays: the DOM's ``dblclick`` is a fifth event
with no ``pointerup`` of its own (``BUGS/001``), so the double press left
``_gui_grab`` standing and the *next* click's release was swallowed
before it could pick (``BUGS/002``). Users double-click the panel first
and then wonder why nothing selects.

Both are asserted from the page's own objects **after** the DOM's exact
delivery, and from the frame (the chrome quad count grows when a menu is
drawn), never from a pristine gesture.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import time

import pytest

from test_browser_render import CHROMIUM_FLAGS, _free_port

pytestmark = pytest.mark.slow

_ROOT = pathlib.Path(__file__).resolve().parents[4]

#: A JS getter for the page state the assertions read: open menus, the gui
#: grab, the viewer's selection, the strip's selected columns, and the
#: chrome quad count of a fresh frame.
_STATE = """() => {
  const v = globalThis.chimolViewer;
  const seqs = v.gui.sequences;
  const strip = [];
  for (let i = 0; i < seqs.length; i++) strip.push(seqs.get(i).selected.length);
  return {
    menus: v.gui._menus.length,
    grab: v.sink._gui_grab,
    selected: v.view._selected_residues.length,
    strip: strip,
    quads: v.draw(),
  };
}"""

#: The centre of a named control, in CSS pixels, read from the panel's own
#: layout so the test does not hard-code a screenshot's coordinates.
_MENUBAR_TITLE = """(title) => {
  const g = globalThis.chimolViewer.gui;
  const rects = g._menubar_rects;
  for (let i = 0; i < rects.length; i++) {
    const t = rects.get(i);
    const r = t.get(0), name = t.get(1);
    if (name === title) return [r.x + r.w / 2, r.y + r.h / 2];
  }
  return null;
}"""

_ROW_BUTTON = """(args) => {
  const [rowName, key] = args;
  const g = globalThis.chimolViewer.gui;
  for (let i = 0; i < g.rows.length; i++) {
    if (g.rows.get(i).name !== rowName) continue;
    const r = g._button_rects.get(i).get(key);
    return [r.x + r.w / 2, r.y + r.h / 2];
  }
  return null;
}"""

_ROW_NAME = """(rowName) => {
  const g = globalThis.chimolViewer.gui;
  for (let i = 0; i < g.rows.length; i++) {
    if (g.rows.get(i).name !== rowName) continue;
    const r = g._row_rects.get(i);
    return [r.x + r.w * 0.4, r.y + r.h / 2];
  }
  return null;
}"""


@pytest.fixture(scope="module")
def server():
    """Serve the browser build for the duration of the module."""
    pytest.importorskip("playwright.sync_api", reason="needs Playwright")
    port = _free_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "chimol.hosts.web.serve", "--port", str(port),
         "--no-open"],
        cwd=str(_ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    import socket

    url = f"http://127.0.0.1:{port}/"
    for _ in range(100):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    else:
        process.kill()
        pytest.skip("the dev server did not start")
    yield url
    process.kill()
    process.wait(timeout=10)


@pytest.fixture(scope="module")
def page(server):
    """One drawn page for the module -- Pyodide costs a minute to start."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=CHROMIUM_FLAGS)
        pg = browser.new_page(viewport={"width": 1280, "height": 800})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(server, wait_until="domcontentloaded")
        if not pg.evaluate("() => !!navigator.gpu"):
            browser.close()
            pytest.skip("this Chromium has no WebGPU even with --enable-unsafe-webgpu")
        pg.wait_for_function(
            "() => { const s = document.getElementById('status');"
            " return s && (s.textContent.includes('drawn')"
            " || s.textContent.includes('failed')); }",
            timeout=300_000,
        )
        status = pg.evaluate("() => document.getElementById('status')?.textContent || ''")
        if "drawn" not in status:
            browser.close()
            pytest.fail(f"the page did not draw: {status}")
        pg.errors = errors  # type: ignore[attr-defined]
        yield pg
        browser.close()


def _state(page):
    return page.evaluate(_STATE)


def _click(page, xy, button="left"):
    assert xy is not None, "the control was not laid out"
    page.mouse.click(xy[0], xy[1], button=button)
    page.wait_for_timeout(300)


def _reset(page):
    page.keyboard.press("Escape")
    page.wait_for_timeout(150)
    # A click on empty space clears the selection and closes overlays.
    page.mouse.click(120, 400)
    page.wait_for_timeout(300)


def test_the_info_panel_a_load_raises_goes_away_on_a_click(page):
    """The load shows the info panel; a click on the scene puts it away.

    The page never wired the panel's close hook to the viewer, so the panel
    came back with the next frame -- and while it is up every press on the
    scene dismisses it instead of picking, which read as "clicks do nothing".
    """
    _run = lambda c: page.evaluate("(c) => globalThis.chimolViewer.cmd.do(c)", c)  # noqa: E731
    _run("delete all")
    _run("load 148l.pdb")
    page.evaluate("() => globalThis.chimolViewer.draw()")
    assert page.evaluate("() => globalThis.chimolViewer.gui.info_visible") is True
    page.mouse.click(120, 400)
    page.wait_for_timeout(300)
    page.evaluate("() => globalThis.chimolViewer.draw()")
    assert page.evaluate("() => globalThis.chimolViewer.gui.info_visible") is False, (
        "the info panel came back: the close hook did not reach the viewer"
    )
    _reset(page)


def test_a_menu_bar_title_stays_open_after_the_click(page):
    """Press *and release* on ``File``: the menu is open when the dust settles."""
    _reset(page)
    idle = _state(page)
    assert idle["menus"] == 0
    _click(page, page.evaluate(_MENUBAR_TITLE, "File"))
    after = _state(page)
    assert after["menus"] == 1, "the File menu did not survive its own release"
    assert after["quads"] > idle["quads"], "the menu was not drawn"
    assert after["grab"] is False, "the release did not end the gui grab"
    _reset(page)


def test_the_object_action_menu_stays_open_after_the_click(page):
    """The ``A`` button on the object row -- the menu that 'did not work'."""
    _reset(page)
    idle = _state(page)
    _click(page, page.evaluate(_ROW_BUTTON, ["148l", "A"]))
    after = _state(page)
    assert after["menus"] == 1, "the A menu did not survive its own release"
    assert after["quads"] > idle["quads"], "the menu was not drawn"
    _reset(page)
    # And the selection's own row, whose menu the user reported.
    _click(page, page.evaluate(_ROW_BUTTON, ["sele", "A"]))
    assert _state(page)["menus"] == 1, "the sele A menu did not stay open"
    _reset(page)


def test_the_right_click_object_menu_stays_open(page):
    """The object menu opens on the *release* of a right press -- and stays."""
    _reset(page)
    _click(page, (640, 400), button="right")
    assert _state(page)["menus"] == 1, "the right-click menu closed on release"
    _reset(page)


def test_a_double_click_does_not_wedge_the_next_pick(page):
    """DOM order: down, up, down, up, dblclick -- then a single click picks."""
    _reset(page)
    _click(page, (560, 470))
    picked = _state(page)["selected"]
    assert picked >= 1, "the first click did not pick anything"
    row = page.evaluate(_ROW_NAME, "148l")
    page.mouse.dblclick(row[0], row[1])
    page.wait_for_timeout(300)
    page.keyboard.press("Escape")
    page.wait_for_timeout(150)
    assert _state(page)["grab"] is False, "the double click left the gui grab held"
    _click(page, (600, 300))
    after = _state(page)
    assert after["selected"] != picked, (
        "the click after a double click was swallowed (BUGS/001, BUGS/002)"
    )
    _reset(page)


def test_a_pick_highlights_the_strip_and_the_strip_picks(page):
    """The viewer's selection is mirrored in the strip, both directions."""
    _reset(page)
    assert _state(page)["strip"] == [0]
    _click(page, (560, 470))
    picked = _state(page)
    assert picked["selected"] >= 1
    assert picked["strip"] == [picked["selected"]], "the strip did not follow the pick"
    _click(page, (120, 400))
    assert _state(page)["strip"] == [0], "clicking empty space did not clear the strip"
    # A residue clicked in the strip reaches the viewer's selection: the row
    # names itself by object *id*, and the host must resolve that.
    strip = page.evaluate(
        "() => { const g = globalThis.chimolViewer.gui; const r = g._seq_rows.get(0);"
        " return [g._seq_origin + 12 * 7, r.y + r.h / 2]; }"
    )
    _click(page, strip)
    after = _state(page)
    assert after["strip"] == [1], "the strip did not mark the clicked residue"
    assert after["selected"] == 1, "the strip's click did not reach the viewer"
    _reset(page)


def test_no_page_errors(page):
    assert not page.errors, page.errors  # type: ignore[attr-defined]
