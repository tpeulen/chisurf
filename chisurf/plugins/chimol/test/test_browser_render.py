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

_WEB = pathlib.Path(__import__("chimol").__file__).resolve().parent / "hosts" / "web"


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
        [sys.executable, "-m", "chimol.hosts.web.serve",
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


#: Typed at the page once it has drawn, one ``keydown`` per character, to prove
#: the in-viewport command line reaches a real command layer. ``bg_color`` is
#: the command to pick: its effect is *in the frame*, so the assertion can be
#: made on pixels rather than on the prompt agreeing with itself.
TYPED_COMMAND = "bg_color white"

#: Typed after it. Selecting is the second thing the browser could not do: the
#: marker geometry lived in the Qt widget, so a selection made in the page
#: highlighted nothing in 3-D.
SELECT_COMMAND = "select sele, resi 20-40"

#: And the third: a representation change. The page opens on a cartoon -- the
#: viewer's own default -- so this asks for the other one, which covers far more
#: of the frame and is therefore measurable.
SHOW_COMMAND = "as spheres"


@pytest.fixture(scope="module")
def rendered(server, tmp_path_factory):
    """Render the page, then type a command at it.

    Returns ``(status, screenshot, console, failure, typed screenshot, prompt)``.
    Both screenshots come from one browser session because starting one costs a
    minute of Pyodide, and the second is the first with a command run at it.
    """
    from playwright.sync_api import sync_playwright

    directory = tmp_path_factory.mktemp("browser")
    out = directory / "chimol.png"
    typed_out = directory / "chimol_typed.png"
    selected_out = directory / "chimol_selected.png"
    cartoon_out = directory / "chimol_cartoon.png"
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

        # Typed through the browser's own key handling -- `page.keyboard` emits
        # real `keydown` events, so this exercises the page listener, the DOM
        # key translation and the engine's editor, not a Python call dressed up
        # as one.
        prompt = ""
        if "drawn" in status:
            page.keyboard.press("Enter")          # focuses the prompt
            page.keyboard.type(TYPED_COMMAND, delay=5)
            page.keyboard.press("Enter")          # runs it
            page.wait_for_timeout(500)
            prompt = page.evaluate(
                "() => globalThis.chimolViewer.prompt_state()"
            )
            page.screenshot(path=str(typed_out))

            page.keyboard.type(SELECT_COMMAND, delay=5)
            page.keyboard.press("Enter")
            page.wait_for_timeout(500)
            prompt += "\n" + page.evaluate(
                "() => globalThis.chimolViewer.prompt_state()"
            )
            page.screenshot(path=str(selected_out))

            page.keyboard.type(SHOW_COMMAND, delay=5)
            page.keyboard.press("Enter")
            page.wait_for_timeout(1500)
            prompt += "\n" + page.evaluate(
                "() => globalThis.chimolViewer.prompt_state()"
            )
            page.screenshot(path=str(cartoon_out))

        browser.close()
    return status, out, console, failure, typed_out, prompt, selected_out, cartoon_out


def test_the_page_reports_a_drawn_frame(rendered):
    """The loader gets all the way to a drawn frame."""
    status, _path, _console, failure, _typed, _prompt, _selected, _cartoon = rendered
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
    _status, path, _console, _failure, _typed, _prompt, _selected, _cartoon = rendered

    frame = np.asarray(Image.open(path).convert("RGB")).astype(float)
    height, width = frame.shape[:2]
    scene = frame[int(height * 0.1): int(height * 0.85), : int(width * 0.75)]

    saturation = scene.max(axis=2) - scene.min(axis=2)
    lit = saturation > 60
    fraction = float(lit.mean())
    # A cartoon, which is what the viewer opens on: a ribbon covers a few per
    # cent of the frame where a space-filling model covers a fifth of it, so
    # the bar is where a *ribbon* sits and not where spheres did.
    assert fraction > 0.015, (
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
    _status, path, _console, _failure, _typed, _prompt, _selected, _cartoon = rendered

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


def test_a_command_can_be_typed_at_the_page(rendered):
    """Return focuses the prompt, the characters land, and the line runs.

    This is what the in-viewport command line exists for. A browser has no
    console to dock beside the viewer, so before this the page could render a
    molecule and had no way to say anything to it -- every command reached it
    only by editing Python and reloading.
    """
    _status, _path, _console, _failure, _typed, prompt, _selected, _cartoon = rendered
    assert prompt, "the prompt reported nothing; did the page draw?"
    assert f"echo: ChiMOL> {TYPED_COMMAND}" in prompt, (
        f"the typed line did not reach the command layer:\n{prompt}"
    )
    assert "error:" not in prompt, f"the command was refused:\n{prompt}"
    assert "line=" in prompt.splitlines()[1], "the editor did not clear"
    assert prompt.splitlines()[1] == "line=", (
        "a submitted line must leave the editor empty"
    )


def test_the_typed_command_changed_the_frame(rendered):
    """``bg_color white`` is visible in the pixels, not only in the log.

    A prompt that logs a command it did not run looks identical to one that ran
    it, which is why this is measured in the frame: the scene's clear colour was
    dark grey before and is white after.
    """
    np = pytest.importorskip("numpy")
    Image = pytest.importorskip("PIL.Image")
    _status, path, _console, _failure, typed, _prompt, _selected, _cartoon = rendered
    if not typed.exists():
        pytest.skip("the page never drew, so nothing was typed at it")

    def _corner(image_path) -> float:
        """Mean brightness of a scene corner the molecule does not reach."""
        frame = np.asarray(Image.open(image_path).convert("RGB")).astype(float)
        height, width = frame.shape[:2]
        return float(frame[int(height * 0.15): int(height * 0.3),
                           int(width * 0.02): int(width * 0.12)].mean())

    before, after = _corner(path), _corner(typed)
    assert after > before + 80.0, (
        f"the background did not turn white: {before:.0f} -> {after:.0f}"
    )


def test_a_selection_made_in_the_page_is_visible_in_3d(rendered):
    """The markers are on the canvas, in the selection colour.

    Measured against the frame *before* the selection, both with a white
    background: the marker is pink and nothing else in this scene is, so the
    count of pink pixels is the selection. A prompt that reported "21 residues
    selected" and drew nothing would pass every other check here.
    """
    np = pytest.importorskip("numpy")
    Image = pytest.importorskip("PIL.Image")
    _status, _path, _console, _failure, typed, prompt, selected, _cartoon = rendered
    if not selected.exists():
        pytest.skip("the page never drew, so nothing was selected in it")

    assert "defined with 162 atoms" in prompt, (
        f"the select command did not run:\n{prompt}"
    )

    def _pink(image_path) -> int:
        """Selection-coloured pixels **in the scene**, not in the chrome.

        Cropped deliberately. The sequence strip highlights a selected residue
        with a pink cell, so a count over the whole frame goes up whether or not
        anything was drawn in 3-D -- which is exactly the false pass this test
        was written to avoid, and did not avoid on its first attempt.
        """
        frame = np.asarray(Image.open(image_path).convert("RGB")).astype(int)
        height, width = frame.shape[:2]
        scene = frame[int(height * 0.08): int(height * 0.9), : int(width * 0.8)]
        red, green, blue = scene[..., 0], scene[..., 1], scene[..., 2]
        return int(((red > 150) & (blue > 70) & (green + 60 < red)).sum())

    before, after = _pink(typed), _pink(selected)
    assert after > before + 200, (
        f"no selection markers appeared: {before} -> {after} pink pixels"
    )


def test_a_representation_change_redraws_the_molecule(rendered):
    """``as spheres`` in the browser, through the viewer's own scene builder.

    Asserted as a *change of shape*, not as "something drew": a space-filling
    model covers far more of the frame than the cartoon the page opens on, and
    the colours are the same, so a check on colour alone would pass on either.
    """
    np = pytest.importorskip("numpy")
    Image = pytest.importorskip("PIL.Image")
    _status, _path, _console, _failure, _typed, prompt, selected, cartoon = rendered
    if not cartoon.exists():
        pytest.skip("the page never drew, so nothing was shown in it")

    assert f"ChiMOL> {SHOW_COMMAND}" in prompt, (
        f"the representation command did not run:\n{prompt}"
    )

    def _covered(image_path) -> int:
        frame = np.asarray(Image.open(image_path).convert("RGB")).astype(int)
        height, width = frame.shape[:2]
        scene = frame[int(height * 0.08): int(height * 0.9), : int(width * 0.8)]
        # Anything that is not the white background this run set.
        return int((scene.min(axis=2) < 220).sum())

    ribbon, spheres = _covered(selected), _covered(cartoon)
    assert spheres > 5_000, "the spheres cover almost nothing; nothing rebuilt"
    assert spheres > ribbon * 1.25, (
        f"the frame did not change shape: {ribbon} -> {spheres} covered pixels"
    )


def test_no_page_errors(rendered):
    """Nothing raised in the page while it rendered."""
    _status, _path, console, _failure, _typed, _prompt, _selected, _cartoon = rendered
    errors = [line for line in console if line.startswith(("error", "pageerror"))]
    assert not errors, "\n".join(errors[:5])
