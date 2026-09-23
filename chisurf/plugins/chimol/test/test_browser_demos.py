"""Every shipped demo, every tour's commands, and the user's own files -- on the **page**.

"All demos must work" in the browser was the ask, and it was not close: the
Demo menu listed eleven and ran none (the browser host had no command layer
to replay a script into), then four -- everything past ``148l.pdb`` needed
material a page did not ship (``solvated_fragment.pdb``, the trajectory),
a reader a page could not import (``ihm`` for the NPC, RMF for the biofilm),
a binary-safe download (``fetch EMD-3061`` arrived as UTF-8 replacement
characters), or a module that lived in the Qt package (``density_panel``).

This drives the real page and asserts, per demo, that the prompt shows no
``error:`` line and the scene holds an object. It is the only place the
whole chain -- zip contents, Pyodide filesystem, XHR, the readers, the
command layer -- is executed together, so it is the test that means it.

The page is one Pyodide boot per module (a minute); the demos then take a
few seconds each, the network ones twenty to thirty.
"""

from __future__ import annotations

import pathlib
import socket
import subprocess
import sys
import time

import pytest
from test_browser_render import CHROMIUM_FLAGS, _free_port

pytestmark = pytest.mark.slow

_ROOT = pathlib.Path(__file__).resolve().parents[4]
#: Where the per-demo screenshots go -- a build directory, not the frozen
#: `renders/` baselines (these are evidence for a failing run, not references).
_SHOTS = _ROOT / "build" / "chimol-browser-demos"
_SHOTS.mkdir(parents=True, exist_ok=True)
_DEMO_DATA = _ROOT / "modules" / "chimol" / "chimol" / "data" / "demos"

#: The demos, in catalogue order. Those marked ``net`` reach a public
#: repository and are skipped when the host is offline.
DEMOS = [
    ("cartoon", False),
    ("selections", False),
    ("representations", False),
    ("lighting", False),
    ("publication", False),
    ("trajectory", False),
    ("measure", False),
    ("labelling", False),
    ("t4l_network", False),
    ("emdb_map", True),
    ("npc_integrative", True),
    ("biofilm", False),
]

#: What each tour tells the reader to type, in order -- the ``expect`` and
#: ``run`` lines of ``plugins/demos/tours/*.json``, flattened. A tour is interactive
#: (it waits for the reader), so the *commands* are what a page must be able
#: to run; the pointing is the chrome's business.
TOURS = {
    "fit_in_map": (
        True,
        [
            "delete all",
            "fetch EMD-3061",
            "map_info",
            "isosurface dens, EMD-3061",
            "density_panel on",
            "volume_level EMD-3061, 0.06",
            "hide_dust EMD-3061, 30",
            "fetch 5A63",
            "translate [6, -4, 3], 5a63",
            "fitmap 5a63",
            "molmap 5a63, 3.4, sim",
        ],
    ),
    "superpose": (
        True,
        [
            "delete all",
            "fetch 1DG3",
            "fetch 1F5N",
            "color skyblue, 1dg3",
            "align 1f5n, 1dg3",
            "super 1f5n, 1dg3",
            "rms 1f5n, 1dg3",
            "zoom 1f5n",
        ],
    ),
    "labelling": (
        False,
        [
            "delete all",
            "load 148l.pdb",
            "wizard labelling",
            "wizard pick, 920",
            "wizard dye, Cy5",
            "wizard apply",
            "wizard done",
        ],
    ),
}


def _online() -> bool:
    for host in ("files.rcsb.org", "ftp.ebi.ac.uk"):
        try:
            with socket.create_connection((host, 443), timeout=3):
                return True
        except OSError:
            continue
    return False


@pytest.fixture(scope="module")
def server():
    """Serve the browser build (freshly packed) for the duration of the module."""
    pytest.importorskip("playwright.sync_api", reason="needs Playwright")
    port = _free_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "chimol.hosts.web.serve", "--port", str(port), "--no-open"],
        cwd=str(_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
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
def page(server):
    """One drawn page for the module."""
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


_LOG = """() => {
  const l = globalThis.emtkApp.gui.command_line.log;
  const out = [];
  for (let i = 0; i < l.length; i++) out.push(l.get(i).kind + ': ' + l.get(i).text);
  return out;
}"""

_OBJECTS = """() => {
  const rows = globalThis.emtkApp.gui.rows;
  const out = [];
  for (let i = 0; i < rows.length; i++) out.push(rows.get(i).name);
  return out;
}"""


def _run(page, command: str) -> list[str]:
    """Run one command at the page and return the prompt lines it added."""
    before = len(page.evaluate(_LOG))
    page.evaluate("(c) => globalThis.emtkApp.cmd.do(c)", command)
    page.evaluate("() => globalThis.emtkPage.draw()")
    return page.evaluate(_LOG)[before:]


def _errors(lines: list[str]) -> list[str]:
    return [line for line in lines if line.startswith("error:")]


@pytest.mark.parametrize("name,needs_net", DEMOS, ids=[d[0] for d in DEMOS])
def test_every_demo_runs_without_an_error(page, name, needs_net):
    if needs_net and not _online():
        pytest.skip("offline: this demo fetches from a public repository")
    lines = _run(page, f"demo {name}")
    assert not _errors(lines), f"demo {name}: " + "; ".join(_errors(lines))
    objects = [n for n in page.evaluate(_OBJECTS) if n not in ("all", "sele")]
    assert objects, f"demo {name} left the scene empty: {lines}"
    # Something was drawn beyond the chrome: the frame's chrome quad count is
    # not the assertion, the object list is -- but a demo that loaded and
    # then said nothing is caught by the two lines above either way.
    page.screenshot(path=str(_SHOTS / f"browser_demo_{name}.png"))
    _run(page, "delete all")


@pytest.mark.parametrize("name", list(TOURS), ids=list(TOURS))
def test_every_tours_commands_run_without_an_error(page, name):
    needs_net, commands = TOURS[name]
    if needs_net and not _online():
        pytest.skip("offline: this tour fetches from a public repository")
    for command in commands:
        lines = _run(page, command)
        assert not _errors(lines), f"tour {name}, `{command}`: " + "; ".join(_errors(lines))
    _run(page, "delete all")


def test_a_dropped_file_opens(page):
    """Drop-to-load: the file lands under /mnt/dropped and `load` opens it."""
    text = (_DEMO_DATA / "solvated_fragment.pdb").read_text()
    transfer = page.evaluate_handle(
        "(text) => { const dt = new DataTransfer();"
        " dt.items.add(new File([text], 'dropped_fragment.pdb', {type: 'text/plain'}));"
        " return dt; }",
        text,
    )
    page.dispatch_event("#view", "dragover", {"dataTransfer": transfer})
    page.dispatch_event("#view", "drop", {"dataTransfer": transfer})
    page.wait_for_function(
        "() => globalThis.emtkApp.prompt_state().includes('/mnt/dropped/dropped_fragment.pdb')",
        timeout=20_000,
    )
    assert "dropped_fragment" in page.evaluate(_OBJECTS)
    assert page.evaluate("() => globalThis.emtkApp.user_files_dir()") == "/mnt/dropped"
    _run(page, "delete all")


def test_a_mounted_folder_is_the_engines_filesystem(page):
    """A directory handle mounted at /mnt/local: `load` reads it, `save` writes it.

    Driven with the origin-private file system, which is a real
    ``FileSystemDirectoryHandle`` a test can get without a picker; the button
    hands the same function the picker's handle.
    """
    text = (_DEMO_DATA / "solvated_fragment.pdb").read_text()
    where = page.evaluate(
        """async (text) => {
          const root = await navigator.storage.getDirectory();
          const fh = await root.getFileHandle('opfs_fragment.pdb', {create: true});
          const w = await fh.createWritable(); await w.write(text); await w.close();
          return await globalThis.emtkMountDirectory(root);
        }""",
        text,
    )
    assert where == "/mnt/local"
    assert page.evaluate("() => globalThis.emtkApp.user_files_dir()") == "/mnt/local"
    lines = _run(page, "load /mnt/local/opfs_fragment.pdb")
    assert not _errors(lines), lines
    assert "opfs_fragment" in page.evaluate(_OBJECTS)
    lines = _run(page, "save /mnt/local/out.pdb, opfs_fragment")
    assert not _errors(lines), lines
    size = page.evaluate(
        """async () => { await globalThis.emtkMount.syncfs();
          const root = await navigator.storage.getDirectory();
          const fh = await root.getFileHandle('out.pdb'); return (await fh.getFile()).size; }"""
    )
    assert size > 0, "the saved file did not reach the native side"
    _run(page, "delete all")


_PNG_STATS = """() => {
  const v = globalThis.emtkApp;
  const g = v.__init__.__globals__;
  const exec = g.get('__builtins__').get('exec');
  const code = [
    "import numpy as _np",
    "from PIL import Image as _Im",
    "_a = _np.asarray(_Im.open('/mnt/ray_test.png').convert('RGB'))",
    "_stats = [int(_a.shape[1]), int(_a.shape[0]), int(len(_np.unique(_a.reshape(-1, 3), axis=0)))]",
  ].join("\\n");
  exec(code, g);
  return g.get('_stats').toJs();
}"""


def test_ray_traces_a_picture_from_the_prompt(page):
    """`ray` typed at the prompt writes a traced image -- in the page.

    Three things had to hold: no Qt on the way (`ray` imported ``qtpy`` for
    a progress dialog and failed with "No module named 'qtpy'"), a GPU
    readback (WebGPU only maps a buffer asynchronously; the page enters
    Python on a suspendable JSPI stack for Return so ``run_sync`` can wait
    for it), and a compute pipeline within WebGPU's baseline of eight
    storage buffers per stage (the tracer bound eleven and traced black).
    Typed through the real key path, because that is the path that has to
    be suspendable.
    """
    _run(page, "delete all")
    _run(page, "load 148l.pdb")
    _run(page, "as cartoon")
    page.mouse.click(120, 400)  # put the info panel away
    page.keyboard.press("Enter")  # focus the prompt
    page.keyboard.type("ray /mnt/ray_test.png, 96, 72", delay=5)
    page.keyboard.press("Enter")
    page.wait_for_function(
        "() => globalThis.emtkApp.prompt_state().includes('ray: wrote')"
        " || globalThis.emtkApp.prompt_state().includes('error: ray')",
        timeout=120_000,
    )
    state = page.evaluate("() => globalThis.emtkApp.prompt_state()")
    assert "ray: wrote /mnt/ray_test.png" in state, state
    width, height, distinct = page.evaluate(_PNG_STATS)
    assert (width, height) == (96, 72)
    assert distinct > 50, "the traced image is flat: the tracer drew nothing"
    _run(page, "delete all")


def test_no_page_errors(page):
    assert not page.errors, page.errors  # type: ignore[attr-defined]
