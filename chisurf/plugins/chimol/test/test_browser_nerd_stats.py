"""Stats for nerds report the frames the page is actually drawing.

The screenshot said it: nerd mode "on", nothing drawn into the backdrop, and a
Frame tab whose counted rows were all zero -- ``draws 0``, ``instances 0``,
``objects 0``, ``chrome 0 quads``, ``pipelines -``, ``gpu ? (?)`` -- while the
timings ticked along. An instrument reporting "0 draws" about a viewer that is
drawing is worse than one reporting nothing.

Both halves were the same mistake: reaching for the counters through
``renderer._gpu``. In a page the viewer's renderer is a ``SceneSink`` that
rasterises nothing -- the page owns the renderer that draws -- so the overlay
found no stats and published nothing, and the dbg window snapshotted a
``None``. The renderer that draws is asked for its stats now
(``CanvasRenderer.frame_stats``), the page installs its own, and the dbg window
asks *per draw* rather than keeping whatever existed when it was opened.
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


def _do(page, command: str) -> None:
    page.evaluate("(c) => globalThis.chimolViewer.cmd.do(c)", command)
    page.evaluate("() => globalThis.chimolViewer.draw()")


_LINES = """() => {
  const g = globalThis.chimolViewer.gui;
  const out = [];
  const l = g.nerd_lines;
  if (!l) return out;
  for (let i = 0; i < l.length; i++) out.push(String(l[i]));
  return out;
}"""


@pytest.fixture(scope="module")
def readout(page):
    _do(page, "nerd_mode on")
    for _ in range(6):
        page.evaluate("() => globalThis.chimolViewer.draw()")
        page.wait_for_timeout(60)
    return page


def test_the_overlay_has_something_to_draw(readout):
    lines = readout.evaluate(_LINES)
    assert lines, "nerd mode is on and the overlay has no lines at all"
    assert any("fps" in line or "frame" in line for line in lines), lines


def test_the_counted_rows_are_not_all_zero(readout):
    """The screenshot: `draws 0  instances 0`, `chrome 0 quads`, on a drawing page."""
    lines = readout.evaluate(_LINES)
    draws = next((l for l in lines if l.strip().startswith("draws")), "")
    chrome = next((l for l in lines if l.strip().startswith("chrome") and "quads" in l), "")
    assert draws and "draws     0" not in draws, f"nothing was counted: {draws!r}"
    assert chrome and "0 quads" not in chrome, f"the chrome counted no quads: {chrome!r}"


def test_switching_it_off_takes_the_readout_away(readout):
    """`nerd off` is a switch, not a suggestion -- and it switches the counting off too."""
    _do(readout, "nerd_mode off")
    readout.evaluate("() => globalThis.chimolViewer.draw()")
    assert readout.evaluate(_LINES) == [], "the readout survived being switched off"
    counting = readout.evaluate("""() => {
      const s = globalThis.chimolViewer.renderer.stats;
      return s ? String(s.enabled) : 'none';
    }""")
    assert counting in ("False", "false"), (
        f"the counters are still being collected with nobody reading them: {counting}"
    )
    _do(readout, "nerd_mode on")  # leave it as the later tests expect
    for _ in range(4):
        readout.evaluate("() => globalThis.chimolViewer.draw()")
        readout.wait_for_timeout(60)
    assert readout.evaluate(_LINES), "switching it back on left it blank"


def test_the_dbg_window_reads_the_same_live_stats(readout):
    """It used to snapshot `viewer.renderer._gpu.stats`, which a page has not got."""
    _do(readout, "dbg")
    readout.evaluate("() => globalThis.chimolViewer.draw()")
    same = readout.evaluate("""() => {
      const v = globalThis.chimolViewer;
      const panel = v.gui.panels.get('dbg');
      if (!panel) return 'no panel';
      const stats = panel.stats;
      if (!stats) return 'no stats';
      return String(stats.last_draws);
    }""")
    assert same not in ("no panel", "no stats"), same
    assert int(same) > 0, f"the dbg window reports {same} draws on a drawing page"
