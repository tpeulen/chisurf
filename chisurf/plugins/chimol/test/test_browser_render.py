"""chimol draws in a real browser, on the browser's own GPU.

Everything else about the browser backend is checked against a stand-in for
``js``. This is the one that cannot be: it starts a server, launches Chromium,
loads Pyodide, unpacks the engine, resolves a WebGPU device and renders a
frame -- and then looks at the pixels.

It is slow (a minute or two, mostly Pyodide) and marked ``slow`` so the default
run skips it. It earns that cost by being the only thing that would have caught
what it did catch:

* ``device.adapter`` is a wgpu-py convenience with no WebGPU equivalent, and the
  engine read it unguarded in its constructor -- so the browser failed several
  layers away from anything to do with adapters;
* ``createBufferWithData`` does not exist in WebGPU either; the specification's
  way is ``mappedAtCreation`` + ``getMappedRange`` + ``unmap``;
* positional arguments needed converting as much as keyword ones, which
  ``queue.writeTexture(destination, data, layout, size)`` reports only as
  ``Overload resolution failed``.

None of the three is visible from Python. All three are ordinary once the page
runs.
"""
from __future__ import annotations

import pathlib
import socket
import subprocess
import sys
import time

import pytest

pytestmark = pytest.mark.slow

#: Chromium flags. ``--enable-unsafe-webgpu`` is what makes ``navigator.gpu``
#: exist in a headless build; without it the page reports no WebGPU and the
#: failure reads like a missing feature rather than a missing flag.
CHROMIUM_FLAGS = [
    "--enable-unsafe-webgpu",
    "--enable-features=Vulkan,WebGPU",
    "--enable-gpu",
    "--ignore-gpu-blocklist",
]

_WEB = pathlib.Path(__file__).resolve().parents[1] / "chimol" / "web"


def _free_port() -> int:
    """Return a port nothing is listening on."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="module")
def server():
    """Serve the browser build for the duration of the module."""
    pytest.importorskip("playwright.sync_api", reason="needs Playwright")
    port = _free_port()
    root = pathlib.Path(__file__).resolve().parents[4]
    process = subprocess.Popen(
        [sys.executable, "-m", "chisurf.plugins.chimol.chimol.web.serve",
         "--port", str(port)],
        cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
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
def rendered(server, tmp_path_factory):
    """Render the page once and return ``(status, screenshot path, console)``."""
    from playwright.sync_api import sync_playwright

    out = tmp_path_factory.mktemp("browser") / "chimol.png"
    console: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=CHROMIUM_FLAGS)
        page = browser.new_page(viewport={"width": 1280, "height": 888})
        page.on("console", lambda m: console.append(f"{m.type}: {m.text}"))
        page.on("pageerror", lambda e: console.append(f"pageerror: {e}"))
        page.goto(server, wait_until="domcontentloaded")

        if not page.evaluate("() => !!navigator.gpu"):
            browser.close()
            pytest.skip(
                "this Chromium has no WebGPU even with --enable-unsafe-webgpu"
            )

        try:
            page.wait_for_function(
                "() => { const s = document.getElementById('status');"
                " return s && (s.textContent.includes('drawn')"
                " || s.textContent.includes('failed')); }",
                timeout=300_000,
            )
        except Exception:  # noqa: BLE001 - reported through `status` below
            pass
        status = page.evaluate(
            "() => document.getElementById('status')?.textContent || ''"
        )
        failure = page.evaluate("() => globalThis.chimolError || ''")
        page.screenshot(path=str(out))
        browser.close()
    return status, out, console, failure


def test_the_page_reports_a_drawn_frame(rendered):
    """The loader gets all the way to a drawn frame."""
    status, _path, _console, failure = rendered
    assert "drawn" in status, f"{status}\n\n{failure[-2000:]}"


def test_the_molecule_is_on_the_canvas(rendered):
    """The scene area carries a lit, spectrum-coloured molecule.

    The check that matters, and the one an earlier version of this demo would
    have passed while drawing nothing: the panel alone renders happily against
    an empty scene, and looks like a working port until someone asks where the
    molecule is.

    Measured in the scene half, away from the panel column: a rendered molecule
    is *bright* against the clear colour and *saturated* along the spectrum
    ramp, and a cleared frame is neither.
    """
    np = pytest.importorskip("numpy")
    Image = pytest.importorskip("PIL.Image")
    _status, path, _console, _failure = rendered

    frame = np.asarray(Image.open(path).convert("RGB")).astype(float)
    height, width = frame.shape[:2]
    scene = frame[int(height * 0.1): int(height * 0.85), : int(width * 0.75)]

    saturation = scene.max(axis=2) - scene.min(axis=2)
    lit = saturation > 60
    fraction = float(lit.mean())
    assert fraction > 0.05, (
        f"only {fraction:.1%} of the scene is saturated colour; the molecule "
        "is missing, and the panel alone would still pass a 'did anything "
        "render' check"
    )

    # Spectrum-coloured along the chain, so both ends of the ramp must be there
    # -- a single flat colour would mean the per-vertex colours were dropped.
    red = scene[..., 0] > scene[..., 2] + 60
    blue = scene[..., 2] > scene[..., 0] + 60
    assert red.any() and blue.any(), "the colour ramp did not survive"


def test_the_panel_is_actually_on_the_canvas(rendered):
    """The rendered frame carries the panel too.

    Checked where the panel *is* -- the right-hand column -- against the scene
    beside it.
    """
    np = pytest.importorskip("numpy")
    Image = pytest.importorskip("PIL.Image")
    _status, path, _console, _failure = rendered

    frame = np.asarray(Image.open(path).convert("RGB")).astype(float)
    height, width = frame.shape[:2]

    # Sampled where the panel's *content* is, not where its column is. Most of
    # the column is empty background by design -- an earlier version of this
    # measured a flat black band below the object rows and reported the panel
    # missing while it was plainly on screen.
    rows = frame[: int(height * 0.08), int(width * 0.79):]
    block = frame[int(height * 0.74):, int(width * 0.79):]

    assert rows.std() > 10.0, "the object rows are flat; nothing drew there"
    assert block.std() > 10.0, "the mouse-mode block is flat; nothing drew there"

    # The `C` button's rainbow is the one saturated thing in the chrome, and it
    # is the last column of the object rows -- a cheap check that colour, not
    # just coverage, survived the trip.
    spread = rows.max(axis=2) - rows.min(axis=2)
    assert spread.max() > 60, "no saturated colour in the object rows"


def test_no_page_errors(rendered):
    """Nothing raised in the page while it rendered."""
    _status, _path, console, _failure = rendered
    errors = [line for line in console if line.startswith(("error", "pageerror"))]
    assert not errors, "\n".join(errors[:5])
