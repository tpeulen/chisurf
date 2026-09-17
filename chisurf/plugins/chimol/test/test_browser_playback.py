"""``mplay`` moves the molecule in the browser -- the page's frame loop is its clock.

The report was "movie play does not work in browser", and it was exact. A page
has no toolkit timer and no ``rendercanvas`` loop; ``Playback`` asked its timer
stand-in for a tick, the stand-in had nowhere to schedule itself, and quietly
did nothing. ``mplay`` therefore set *running* and printed "Playing movie...",
and the frame never changed -- the one failure mode where everything says it
worked.

A page that draws does have a clock, though: ``requestAnimationFrame``. So the
frame loop pumps the movie (``Playback.pump``) and keeps asking for frames
while ``Page.animating()`` is true. This drives the real page: run a
trajectory demo, start the movie, wait a moment in *browser* time, and see the
frame move -- then stop it and see it stay.
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


_FRAME = "() => globalThis.chimolViewer.view.get_frame_position()"
_RUNNING = "() => globalThis.chimolViewer.animating()"


def _do(page, command: str) -> None:
    page.evaluate("(c) => globalThis.chimolViewer.cmd.do(c)", command)
    page.evaluate("() => globalThis.chimolViewer.draw()")


@pytest.fixture(scope="module")
def playing(page):
    """A trajectory loaded and the movie started, once for the module."""
    _do(page, "demo trajectory")
    assert page.evaluate("() => globalThis.chimolViewer.view.get_total_frames()") > 1
    return page


def test_the_movie_advances_while_it_plays(playing):
    page = playing
    _do(page, "frame 1")
    start = page.evaluate(_FRAME)
    _do(page, "mplay")
    assert page.evaluate(_RUNNING), "the page does not think it is animating"
    # Browser time, not test time: the frames come from `requestAnimationFrame`,
    # so the page has to be left alone to draw them.
    page.wait_for_timeout(1200)
    moved = page.evaluate(_FRAME)
    assert moved != start, f"the movie did not advance ({start} -> {moved})"


def test_stopping_it_stops_the_frames(playing):
    page = playing
    _do(page, "mstop")
    assert not page.evaluate(_RUNNING)
    page.wait_for_timeout(400)
    at_stop = page.evaluate(_FRAME)
    page.wait_for_timeout(600)
    assert page.evaluate(_FRAME) == at_stop, "the movie kept running after `mstop`"


def test_the_page_reports_no_errors_from_the_loop(playing):
    """A pump that raised every frame would flood the prompt rather than stop."""
    lines = playing.evaluate("""() => {
      const l = globalThis.chimolViewer.gui.command_line.log;
      const out = [];
      for (let i = 0; i < l.length; i++) out.push(l.get(i).kind + ': ' + l.get(i).text);
      return out;
    }""")
    assert not [line for line in lines if line.startswith("error:")], lines[-5:]
