"""The progressive ray tracer runs in the page (PRD-128 round 5).

``render_mode quality`` traces the still view one jittered sample per frame
and shows the running mean over the scene column. Until round 5 the mean was
a CPU array -- every sample read the trace back, which a page can only wait
for on a JSPI stack, and the animation frame is not one -- so the page skipped
it. The mean now lives on the GPU (``render/progressive_ray.py``,
``ray_accumulate.wgsl``): this drives the real page, switches the preset on,
lets the frame loop converge and checks that the samples were taken, that
nothing failed, and that the scene column changed from the raster to the
traced picture -- and back when the view moves.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time

import numpy as np
import pytest
from test_browser_render import CHROMIUM_FLAGS, _free_port

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def page():
    pytest.importorskip("playwright.sync_api", reason="needs Playwright")
    import pathlib

    from playwright.sync_api import sync_playwright

    root = pathlib.Path(__file__).resolve().parents[4]
    port = _free_port()
    server = subprocess.Popen(
        [sys.executable, "-m", "chimol.hosts.web.serve", "--port", str(port), "--no-open"],
        cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    for _ in range(100):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    else:
        server.kill()
        pytest.skip("the dev server did not start")
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=CHROMIUM_FLAGS)
            pg = browser.new_page(viewport={"width": 1100, "height": 760})
            errors: list[str] = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
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
            pg.errors = errors
            yield pg
            browser.close()
    finally:
        server.kill()
        server.wait(timeout=10)


_STATE = """() => {
  const p = globalThis.emtkApp.sink._progressive;
  if (p === undefined || p === null) return null;
  return [p.count, p.showing, p.samples];
}"""

_COLUMN = """() => {
  const v = globalThis.emtkApp.sink._scene_viewport();
  return [v.get(0), v.get(1), v.get(2), v.get(3)];
}"""


def _run(page, command):
    page.evaluate("(c) => globalThis.emtkApp.cmd.do(c)", command)
    page.evaluate("() => globalThis.emtkPage.draw()")


def _column(page, path):
    from PIL import Image

    page.screenshot(path=str(path))
    img = np.asarray(Image.open(path).convert("RGB"), dtype=int)
    x, y, w, h = (int(round(v)) for v in page.evaluate(_COLUMN))
    dpr = page.evaluate("() => window.devicePixelRatio || 1")
    # The viewport is in device pixels; the screenshot in CSS pixels at dpr 1.
    s = 1.0 / float(dpr)
    return img[int(y * s):int((y + h) * s), int(x * s):int((x + w) * s)]


def test_quality_traces_the_still_view_on_the_gpu(page, tmp_path):
    _run(page, "delete all")
    _run(page, "load 148l.pdb")
    _run(page, "hide everything")
    _run(page, "show spheres")
    _run(page, "set depth_cue, 0")
    page.wait_for_timeout(500)
    raster = _column(page, tmp_path / "raster.png")

    _run(page, "set render_mode, quality")
    # The frame loop keeps drawing while samples are due (`Page.animating`).
    page.wait_for_function(
        "() => { const p = globalThis.emtkApp.sink._progressive;"
        " return p && p.count >= p.samples; }",
        timeout=120_000,
    )
    count, showing, samples = page.evaluate(_STATE)
    assert count == samples == 32
    assert showing, "the trace failed in the page (the mean is not shown)"
    page.evaluate("() => globalThis.emtkPage.draw()")
    traced = _column(page, tmp_path / "traced.png")
    assert traced.shape == raster.shape
    # The traced picture replaced the raster in the scene column: PyMOL's
    # lighting and ray shadows, not the rasteriser's.
    assert np.abs(traced - raster).mean() > 2.0, np.abs(traced - raster).mean()
    # The molecule is still there (not a blank or background-only column).
    assert (traced.max(-1) > 40).mean() > 0.05

    # Moving the view drops the mean and starts over.
    _run(page, "turn y, 30")
    count, showing, _ = page.evaluate(_STATE)
    assert count < samples
    _run(page, "set render_mode, performance")
    _run(page, "delete all")


def test_no_page_errors(page):
    assert not page.errors, page.errors
