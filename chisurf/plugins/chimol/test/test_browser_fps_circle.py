"""The labelling network draws in the page, like every other panel.

A port that only runs on the desktop is a port that will stop running: the
circular layout is drawn with the same six painter operations as the rest of
the chrome precisely so the browser gets it for free, and this is what says
that is still true. It opens the panel in a real page, feeds it a small plan
through the command layer, and asks the chrome what it drew.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time

import pytest

pytestmark = pytest.mark.slow

import pathlib  # noqa: E402

from test_browser_render import CHROMIUM_FLAGS, _free_port  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[4]


@pytest.fixture(scope="module")
def server():
    pytest.importorskip("playwright.sync_api", reason="needs Playwright")
    port = _free_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "chimol.hosts.web.serve", "--port", str(port), "--no-open"],
        cwd=str(_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    for _ in range(100):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    else:
        process.kill()
        pytest.skip("the dev server did not start")
    yield f"http://127.0.0.1:{port}/"
    process.kill()
    process.wait(timeout=10)


@pytest.fixture(scope="module")
def page(server):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=CHROMIUM_FLAGS)
        pg = browser.new_page(viewport={"width": 1100, "height": 700})
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
        yield pg
        browser.close()


#: The real path, not a fabricated model: attach two dyes and ask for the
#: circle. Everything crosses the bridge as a string or a number -- a
#: JavaScript object handed to a Python call arrives as a `JsProxy` and is not
#: a dict, which is a fact about Pyodide rather than about this panel.
_PLAN = """() => {
  const v = globalThis.chimolViewer;
  v.cmd.do('add_dye resi 119 and name CB, AV1 20 4.5 3.5');
  v.cmd.do('add_dye resi 44 and name CB, AV1 20 4.5 3.5');
  v.cmd.do('fps_circle');
  v.draw();
  return v.gui.panels.get('fps_circle') ? 'open' : 'no panel';
}"""

_SHAPE = """() => {
  const v = globalThis.chimolViewer;
  const panel = v.gui.panels.get('fps_circle');
  if (!panel) return 'no panel';
  panel.refresh();
  const circle = panel.build(0, 0, 400, 400);
  return [circle.sectors.length, circle._points.length].join(',');
}"""


def test_the_panel_opens_in_the_page(page):
    assert page.evaluate(_PLAN) == "open"


def test_the_scenes_dyes_become_a_circle(page):
    """Two dyes on one chain: one sector, two positions on it."""
    page.evaluate(_PLAN)
    assert page.evaluate(_SHAPE) == "1,2"


def test_the_page_draws_it_without_complaint(page):
    """A panel that throws mid-draw takes the frame with it."""
    page.evaluate(_PLAN)
    quads = page.evaluate("() => globalThis.chimolViewer.draw()")
    assert int(quads) > 0
