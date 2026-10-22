"""The web release (``chisurf.web``): what ships, and that its boot works.

Three gates, mirroring how ndXplorer tests its page:

* the *bundle* -- the archive ships the shell, the emtk plugin tree and the
  wheels, and leaves behind exactly the Qt GUI package and the plugins' test
  trees;
* the *site* -- ``--build-only`` produces a page whose configuration
  ``boot.js`` reads is well-formed, and that boot.js runs against this
  configuration under node with DOM stand-ins and a stubbed Pyodide (the
  :mod:`emtk.web` runtime harness's shape) -- no browser needed;
* the *factory* -- ``chisurf.web.make_app`` boots in a subprocess where Qt
  cannot import and ``socket.socket`` raises, as it does in Pyodide: the
  session comes up in ``local`` API mode, the shared event bus reaches the
  docks, and the shell draws text.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _bundle():
    from chisurf.web import bundle

    return bundle()


def _config(site: Path) -> dict:
    text = (site / "index.html").read_text(encoding="utf-8")
    payload = re.search(
        r'<script id="emtk-config" type="application/json">(.*?)</script>', text, re.S
    ).group(1)
    return json.loads(payload.replace("<\\/", "</"))


# -- the wheels --------------------------------------------------------------- #

def test_required_tttrlib_wheel_is_found():
    from chisurf.web import find_wheel

    wheel = find_wheel("tttrlib")
    assert wheel is not None and wheel.is_file(), (
        "no tttrlib Pyodide wheel; a page without it cannot open a single tttr file"
    )


def test_optional_impbff_wheel_is_found_or_the_page_degrades():
    from chisurf.web import find_wheel

    wheel = find_wheel("IMP.bff")
    if wheel is None:
        pytest.skip("no IMP.bff Pyodide wheel built; the page boots without it")
    assert wheel.is_file()


# -- the bundle --------------------------------------------------------------- #

def test_bundle_ships_shell_emtk_and_wheels_without_qt_or_test_trees(tmp_path):
    from emtk.web.serve import pack_zip

    bundle = _bundle()
    assert bundle.app == "chisurf.web:make_app"
    assert bundle.wheels and all(Path(w).is_file() for w in bundle.wheels)
    names = zipfile.ZipFile(pack_zip(bundle, tmp_path / "app.zip")).namelist()

    # The shell and its plugins...
    assert "chisurf/web/__init__.py" in names
    assert "chisurf/emtk/main_app.py" in names
    manifests = [n for n in names if n.endswith("manifest.json")]
    assert len(manifests) >= 120, f"only {len(manifests)} plugin manifests shipped"

    # ...without the Qt GUI package, the template, or the plugins' test trees.
    assert not [n for n in names if n.startswith("chisurf/gui/")]
    assert not [n for n in names if "cookiecutter" in n]
    tests = [n for n in names
             if re.match(r"chisurf/plugins/[^/]+/.*/(test|tests)/", n)
             or re.match(r"chisurf/plugins/[^/]+/(test|tests)/", n)]
    assert not tests, f"{len(tests)} plugin test files shipped (e.g. {tests[:3]})"

    # The runtime dependencies ndX pages also carry, plus emtk's draw data.
    assert "mmfdb/config.py" in names and "chimol/io/__init__.py" in names
    assert any(n.startswith("emtk/atlas/") for n in names), "no glyph atlas: no label draws"
    assert any(n.endswith(".wgsl") for n in names), "no shader: nothing draws"
    # A wheel would have been tidier; compiled desktop extensions must not ride.
    assert not [n for n in names if n.endswith((".so", ".node", ".dylib"))]

    # The tttrlib Pyodide wheel ships only the compiled extension; the
    # pure-Python submodules chisurf imports at module level ride in the
    # archive and make_app() installs them (caught by the real-browser run:
    # fret_line died on 'No module named tttrlib.matfile').
    compat = [n for n in names if n.startswith("chisurf/web/_tttrlib_compat/")]
    assert sorted(compat) == [
        "chisurf/web/_tttrlib_compat/interpolate.py",
        "chisurf/web/_tttrlib_compat/matfile.py",
        "chisurf/web/_tttrlib_compat/ndimage.py",
        "chisurf/web/_tttrlib_compat/signal.py",
    ], f"compat modules missing from the archive: {compat}"


def test_every_plugin_manifest_icon_is_a_baked_glyph(tmp_path):
    """The icons the plugin menus spell are in the atlas the page ships.

    The browser has no font engine: the runtime glyph cache has nothing to
    load there, so a manifest ``icon`` outside the baked rows drew the ``¤``
    placeholder -- the owner's "all emoticons and icons are missing". The
    icons are read from the packed manifests themselves, so a plugin that adds
    a new pictograph fails here until the atlas is re-baked.
    """
    import json

    from emtk.grapheme import glyph_of

    from emtk.web.serve import pack_zip

    bundle = _bundle()
    archive = zipfile.ZipFile(pack_zip(bundle, tmp_path / "app.zip"))
    meta = json.loads(archive.read("emtk/atlas/chrome.json").decode("utf-8"))
    charset = set(meta["charset"])
    tables = meta["glyphs"]

    checked = 0
    missing = []
    for name in archive.namelist():
        parts = name.split("/")
        if len(parts) < 4 or parts[0] != "chisurf" or parts[1] != "plugins" \
                or parts[-1] != "manifest.json":
            continue
        icon = json.loads(archive.read(name).decode("utf-8")).get("icon", "")
        if not icon or icon.endswith((".png", ".svg")):
            continue
        checked += 1
        base = glyph_of(icon[0])
        if base not in charset:
            missing.append(f"{'/'.join(parts[2:-1])}: {icon!r} ({base!r} not baked)")
            continue
        for face in ("regular", "bold"):
            assert base in tables[face], f"{name}: {icon!r} missing from {face}"
    assert checked >= 9, f"only {checked} manifest icons found -- enumeration broke"
    assert not missing, f"manifest icons the shipped atlas cannot draw: {missing}"


# -- the site, and its boot under node ---------------------------------------- #

@pytest.mark.slow
def test_build_only_site_boots_under_node(tmp_path):
    from emtk.web.serve import build

    site = build(_bundle(), tmp_path / "site")
    for needed in ("index.html", "boot.js", "app.zip"):
        assert (site / needed).is_file()
    wheels = list((site / "wheels").glob("*.whl"))
    assert len(wheels) == len(_bundle().wheels)

    config = _config(site)
    assert config["app"] == "chisurf.web:make_app"
    assert config["archive"].startswith("app.zip")
    # fonttools: a frame module's import chain reaches fontTools at boot --
    # the real-browser run caught it (the node harness stubs Pyodide's
    # package loader, so it cannot see a missing distribution package).
    assert config["pyodide_packages"] == [
        "numpy", "Pillow", "scipy", "pyyaml", "lzma", "fonttools",
    ]
    joined = " ".join(config["wheels"])
    assert "tttrlib" in joined, "the required tttrlib wheel is not on the page"
    assert all((site / w).is_file() for w in config["wheels"])

    _assert_boot_js_runs(site, config, tmp_path)


def _assert_boot_js_runs(site: Path, config: dict, tmp_path: Path) -> None:
    """Run the real ``boot.js`` under node: stub DOM, stub Pyodide, our config.

    The page is 'up' when the loader has loaded the Pyodide packages, fetched
    and unpacked the archive, requested the GPU device and mounted our factory
    -- every step a real browser takes, with the browser stood in for.
    """
    harness = r"""
const calls = [];
const elements = {};
const targets = () => ({
  listeners: {},
  addEventListener(name, fn) { this.listeners[name] = fn; },
});
const canvas = Object.assign(targets(), {
  clientWidth: 960, clientHeight: 640, width: 0, height: 0,
  getBoundingClientRect: () => ({left: 0, top: 0}),
  setPointerCapture() {}, hasPointerCapture: () => false,
  releasePointerCapture() {}, classList: {add() {}, remove() {}},
});
elements.view = canvas;
elements['emtk-config'] = {textContent: JSON.stringify(CONFIG)};
elements.status = {textContent: ''};
globalThis.document = Object.assign(targets(), {
  getElementById: name => elements[name] || null, title: 'ChiSurf',
});
globalThis.location = new URL('https://page.local/index.html');
globalThis.window = Object.assign(targets(), {devicePixelRatio: 2});
Object.defineProperty(globalThis, 'navigator', {value: {gpu: {}, platform: 'Mac'}});
globalThis.setInterval = () => 1;
globalThis.clearInterval = () => {};
globalThis.requestAnimationFrame = () => 1;
globalThis.cancelAnimationFrame = () => {};
globalThis.ResizeObserver = class { observe() {} disconnect() {} };
WebAssembly.Suspending = function () {};
const page = {
  app: {}, DROP_DIR: '/drop', MOUNT_DIR: '/mount',
};
for (const name of ['draw', 'title', 'animating', 'wake_in', 'move', 'wheel', 'resize',
                    'press', 'release', 'key', 'key_up', 'clear_keys', 'copy', 'paste',
                    'open_path']) {
  page[name] = () => name !== 'animating';
}
page.key.callPromising = async (...args) => page.key(...args);
const pyodide = {
  globals: {set(name, value) { calls.push(['global', name, value === canvas]); }},
  loadPackage: async names => { calls.push(['packages', names]); },
  unpackArchive: (buffer, kind, options) => {
    calls.push(['archive', kind, options.extractDir]);
  },
  runPythonAsync: async code => {
    if (!code.includes('request_device_async')) throw Error('unexpected async: ' + code);
    calls.push(['gpu']);
  },
  runPython: code => {
    if (code.includes('mount(')) {
      if (!code.includes('mount(_emtk_canvas')) throw Error('wrong canvas binding');
      calls.push(['mount', 'chisurf.web:make_app']);
      return page;
    }
    if (code.includes('sys.path')) calls.push(['path']);
    return undefined;
  },
};
let loaded = 0;
globalThis.loadPyodide = async options => { loaded++; calls.push(['pyodide', options]); return pyodide; };
globalThis.fetch = async url => ({ok: true, arrayBuffer: async () => new ArrayBuffer(0)});
console.log = () => {};
BOOT
(async () => {
  for (let i = 0; i < 100 && !globalThis.emtkReady; i++) {
    await new Promise(resolve => setImmediate(resolve));
  }
  if (!globalThis.emtkReady) throw Error(globalThis.emtkError || 'boot never became ready');
  const out = {loaded, calls};
  process.stdout.write(JSON.stringify(out));
})().catch(e => {process.stderr.write(String(e.stack || e)); process.exitCode = 1;});
"""
    boot = (site / "boot.js").read_text(encoding="utf-8")
    script = tmp_path / "boot_harness.js"
    script.write_text(
        harness.replace("CONFIG", json.dumps(config)).replace("BOOT", boot),
        encoding="utf-8",
    )
    result = subprocess.run(
        ["node", str(script)], capture_output=True, text=True, timeout=60, check=True
    )
    out = json.loads(result.stdout)
    assert out["loaded"] == 1, "the loader did not start Pyodide exactly once"
    calls = out["calls"]
    assert calls[0][0] == "pyodide"
    packages = next(c for c in calls if c[0] == "packages")[1]
    for wanted in config["pyodide_packages"]:
        assert any(wanted.lower() in str(p).lower() for p in packages), (
            f"{wanted} was not loaded from the Pyodide distribution"
        )
    assert ["path"] in calls, "the archive's directory never reached sys.path"
    assert ["archive", "zip", config["extract_dir"]] in calls
    assert ["gpu"] in calls, "no WebGPU device was requested"
    assert ["mount", "chisurf.web:make_app"] in calls, "the shell was never mounted"


# -- the factory, without Qt or sockets (the Pyodide shape) -------------------- #

_PROBE = r"""
import json, socket, sys

class BlockQt:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"qtpy", "PyQt5", "PyQt6", "PySide2", "PySide6", "pyqtgraph"}:
            raise ImportError("Qt forbidden: " + fullname)
        return None

sys.meta_path.insert(0, BlockQt())

# Pyodide: the socket module imports, creating one does not. The stand-in stays
# a class (ssl.py subclasses socket.socket at import time).
class NoSocket(socket.socket):
    def __init__(self, *args, **kwargs):
        raise OSError("Pyodide simulated: cannot create sockets")

socket.socket = NoSocket

import chisurf
import chisurf.web
from emtk.testing import RecordingPainter

result = {}
app = chisurf.web.make_app()
result["app"] = type(app).__name__

painter = RecordingPainter()
frames = 0
for _ in range(300):
    app.draw(painter, 0, 0, 1200, 800)
    frames += 1
    if app.data.session is not None and not app.data.starting:
        break
result["frames"] = frames
result["strings"] = len(painter.strings)
session = app.data.session
if session is None:
    raise AssertionError("the session never started: " + str(app.data.error))
result["api_mode"] = session.api.mode
result["server"] = type(session.server).__name__
result["experiments"] = len(app.data.experiments())

# The shared bus reaches the docks: publish, drain, see the dirty flag.
before = set(app.data._dirty)
chisurf.__chisurf_rpc_server__.event_bus.publish("dataset.added", {"name": "probe"})
drained = session.events.drain()
result["drained"] = drained
result["dirty_grew"] = sorted(set(app.data._dirty) - before)

qt = sorted(n for n in sys.modules
            if n.split(".")[0] in {"qtpy", "PyQt5", "PyQt6", "PySide2", "PySide6", "pyqtgraph"})
result["qt_modules"] = qt
result["project_degrades"] = "not available" in app.project.status
print(json.dumps(result))
"""


def test_page_factory_boots_without_qt_or_sockets():
    """The Pyodide shape of the boot: no Qt, sockets raise, and yet the shell
    comes up with a local-mode session over the shared bus."""
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=str(ROOT),
        env={**os.environ},
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    out = json.loads(result.stdout.strip().splitlines()[-1])
    assert out["app"] == "EmtkShellApp"
    assert out["strings"] > 100, "the shell rendered no text"
    assert out["api_mode"] == "local", "the web session must not go through sockets"
    assert out["server"] == "WebEventHost"
    assert out["experiments"] >= 5
    assert out["drained"] >= 1 and "datasets" in out["dirty_grew"], (
        "a bus event never reached the docks"
    )
    assert out["project_degrades"], "the project actions should say they are off"
    assert not out["qt_modules"], f"Qt loaded: {out['qt_modules']}"


# -- the bus subscriber, on its own ------------------------------------------- #

def test_bus_event_subscriber_mirrors_the_socket_subscriber():
    from chisurf.server.eventbus import InProcessEventBus
    from chisurf.web import BusEventSubscriber

    bus = InProcessEventBus()
    wakes = []
    sub = BusEventSubscriber(bus, wake=lambda: wakes.append(1))
    assert sub.running and sub.pending == 0

    seen, other = [], []
    sub.subscribe("fit.", seen.append)
    sub.subscribe("dataset.", other.append)
    bus.publish("fit.updated", {"fit_uid": "u1"})
    bus.publish("dataset.added", {})
    bus.publish("macro.ran", {})
    assert sub.pending == 3 and len(wakes) == 3 and sub.received == 3

    assert sub.drain(limit=1) == 1
    assert seen and seen[0]["fit_uid"] == "u1" and seen[0]["topic"] == "fit.updated"
    assert sub.drain() == 2
    assert other and other[0]["topic"] == "dataset.added"
    assert sub.pending == 0 and sub.drain() == 0
    # "macro.ran" matched no prefix and is gone, as on the PUB socket.
    assert sub.drain() == 0

    # stop() unsubscribes from the bus; queued events stay drainable.
    bus.publish("fit.ran", {})
    sub.stop()
    assert sub.drain() == 1 and seen[-1]["topic"] == "fit.ran"
    bus.publish("fit.ran", {})
    assert sub.drain() == 0, "after stop() the bus must not queue new events"


# -- the batch, on a host with no threads -------------------------------------- #

def test_background_build_falls_back_to_the_calling_thread(monkeypatch):
    """Pyodide without cross-origin isolation cannot start a worker: the batch
    then runs inline and collect() still hands it over (the page's session
    start, fits and plugin opens all ride on this)."""
    import threading

    from chisurf.emtk.background_build import BackgroundBuild

    def refuse(self, *args, **kwargs):
        raise RuntimeError("Pyodide simulated: cannot start a thread")

    monkeypatch.setattr(threading.Thread, "start", refuse)
    wakes = []
    build = BackgroundBuild(wake=lambda: wakes.append(1))
    made = object()
    assert build.start({"tool": lambda: made}) is True
    assert wakes == [1], "the inline batch must still wake the hub"
    assert build.busy and not build.running
    results = build.collect()
    assert results == {"tool": (made, None)}
    assert not build.busy and build.collect() is None
