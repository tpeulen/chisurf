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
from unittest import mock as unittest_mock
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


def test_the_tttrlib_wheel_covers_the_compat_modules_fast_paths(tmp_path):
    """Every compiled call the shipped pure-Python tttrlib modules make exists
    in the shipped wheel.

    The PSF Determination page died with ``module 'tttrlib' has no attribute
    'ndi_label'``: the Pyodide wheel predated tttrlib's ndimage C ops, while
    the compat modules -- copied from a *current* install -- called fast paths
    the wheel never compiled. Nothing compared the two ends; this does,
    statically: every ``_t.<name>(`` a compat module calls must be defined by
    the wheel's generated ``tttrlib/__init__.py`` or exported by its extension.
    """
    import io

    from chisurf.web import TTTRLIB_PYTHON_MODULES, find_wheel
    from emtk.web.serve import pack_zip

    archive = zipfile.ZipFile(pack_zip(_bundle(), tmp_path / "app.zip"))
    compat = {
        name: archive.read(name).decode("utf-8")
        for name in archive.namelist()
        if name.startswith("chisurf/web/_tttrlib_compat/") and name.endswith(".py")
    }
    assert compat, (
        "the bundle ships no tttrlib compat modules; the page cannot filter an image"
    )

    wheel_path = find_wheel("tttrlib")
    assert wheel_path is not None and wheel_path.is_file()
    wheel = zipfile.ZipFile(io.BytesIO(wheel_path.read_bytes()))
    init = wheel.read("tttrlib/__init__.py").decode("utf-8", "replace")
    ext = b"".join(
        wheel.read(n) for n in wheel.namelist() if n.endswith(".so")
    )
    defined = set(re.findall(r"^def (\w+)", init, re.M))
    defined |= set(re.findall(r"^(\w+)\s*=\s*_tttrlib", init, re.M))
    defined |= set(re.findall(r"^class (\w+)", init, re.M))
    # module-level constants (``HMM_UNASSIGNED = cvar.HMM_UNASSIGNED``, plain
    # dicts) -- generated __init__ files assign them, guards miss them
    defined |= set(re.findall(r"^([A-Z][A-Z_0-9]*)\s*=", init, re.M))

    missing = []
    for name, source in compat.items():
        for call in sorted(set(re.findall(r"\b_t\.(\w+)\(", source))):
            if call not in defined and call.encode() not in ext:
                missing.append(f"{name}: _t.{call}")

    # And the direct uses: every ``tttrlib.<attr>`` / ``from tttrlib import
    # <attr>`` the packed sources make must exist in the wheel or be one of
    # the pure-Python submodules the bundle installs beside it.
    submodules = {name.rsplit("/", 1)[-1][:-3] for name in compat} | {"pipeline"}
    allowed = defined | submodules
    for src in sorted(n for n in archive.namelist()
                     if n.startswith("chisurf/") and n.endswith(".py")):
        text = archive.read(src).decode("utf-8", "replace")
        for attr in sorted(set(re.findall(r"\btttrlib\.(\w+)", text))):
            if attr.startswith("_") or attr.endswith("_"):
                continue  # dunders, and ellipses inside docstring patterns
            if attr not in allowed:
                missing.append(f"{src}: tttrlib.{attr}")
        for group in re.findall(r"from tttrlib import ([\w, ]+)", text):
            for attr in (a.strip() for a in group.split(",")):
                attr = attr.split(" as ")[0].strip()
                if attr and attr.isidentifier() and attr not in allowed:
                    missing.append(f"{src}: from tttrlib import {attr}")
    assert not missing, (
        f"the shipped tttrlib wheel lacks the compiled fast paths the shipped "
        f"compat modules call -- rebuild it (tttrlib tools/pyodide/build_wheel.sh): "
        f"{missing}"
    )


def test_optional_impbff_wheel_is_found_or_the_page_degrades():
    from chisurf.web import find_wheel

    wheel = find_wheel("IMP.bff")
    if wheel is None:
        pytest.skip("no IMP.bff Pyodide wheel built; the page boots without it")
    assert wheel.is_file()


def test_the_impbff_wheel_covers_the_attributes_the_page_uses(tmp_path):
    """The IMP.bff twin of the tttrlib wheel guard.

    PSF Determination's fit leg died with ``module 'IMP.bff' has no attribute
    'FitResidualFunction'``: the shipped IMP.bff wheel predated the current
    source, exactly like the tttrlib wheel did. Every ``IMP.bff.<attr>`` /
    ``from IMP.bff import <attr>`` (and ``bff.<attr>`` for the canonical
    ``import IMP.bff as bff`` alias) the packed sources use must be defined by
    the wheel's ``IMP/bff/__init__.py`` or exported by its extension.
    """
    import io

    from chisurf.web import IMPBFF_STANDALONE_ABSENT, find_wheel
    from emtk.web.serve import pack_zip

    wheel_path = find_wheel("IMP.bff")
    if wheel_path is None:
        pytest.skip("no IMP.bff Pyodide wheel built; the page boots without it")
    wheel = zipfile.ZipFile(io.BytesIO(wheel_path.read_bytes()))
    init_name = next(
        (n for n in wheel.namelist() if n.replace("\\", "/") == "IMP/bff/__init__.py"),
        None,
    )
    assert init_name, "the wheel does not install IMP/bff (import IMP.bff cannot work)"
    init = wheel.read(init_name).decode("utf-8", "replace")
    ext = b"".join(wheel.read(n) for n in wheel.namelist() if n.endswith((".so", ".pyd")))
    defined = set(re.findall(r"^def (\w+)", init, re.M))
    defined |= set(re.findall(r"^class (\w+)", init, re.M))
    defined |= set(re.findall(r"^(\w+)\s*=", init, re.M))
    defined |= set(re.findall(r"from \.(?:\w+\.)* import (.+)", init))  # re-exports
    defined = {d.strip() for group in defined for d in group.split(",") if d.strip()}

    archive = zipfile.ZipFile(pack_zip(_bundle(), tmp_path / "app.zip"))
    absent = set(IMPBFF_STANDALONE_ABSENT)  # IMP-bound, absent by design
    missing = []
    for src in sorted(n for n in archive.namelist()
                      if n.startswith("chisurf/") and n.endswith(".py")):
        text = archive.read(src).decode("utf-8", "replace")
        # docstrings quote attribute paths in prose (``bff.distance_metrics``
        # in quenching docs) -- strip them; code references survive
        text = re.sub(r'"""(?:.|\n)*?"""|\'\'\'(?:.|\n)*?\'\'\'', "", text)
        for attr in sorted(set(re.findall(r"\bIMP\.bff\.(\w+)", text))):
            if attr.startswith("_") or attr.endswith("_") or attr in absent:
                continue
            if attr not in defined and attr.encode() not in ext:
                missing.append(f"{src}: IMP.bff.{attr}")
        for group in re.findall(r"from IMP\.bff import ([\w, ]+)", text):
            for attr in (a.strip() for a in group.split(",")):
                attr = attr.split(" as ")[0].strip()
                if attr and attr.isidentifier() and attr not in defined and attr not in absent:
                    missing.append(f"{src}: from IMP.bff import {attr}")
        if re.search(r"^\s*import IMP\.bff as bff\b", text, re.M):
            for attr in sorted(set(re.findall(r"\bbff\.(\w+)", text))):
                if attr.startswith("_") or attr.endswith("_") or attr in absent:
                    continue
                if attr not in defined and attr.encode() not in ext:
                    missing.append(f"{src}: bff.{attr}")
    assert not missing, (
        f"the shipped IMP.bff wheel lacks attributes the packed sources use -- "
        f"rebuild it (imp.bff tools/pyodide/build_wheel.sh): {sorted(set(missing))[:10]}"
    )


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
    # The Zenodo deposit path ships with the credential store it reads; the
    # zenodo_deposit plugin is a window over mmfdb.deposit, so a page without
    # it cannot open the plugin (the bug the real-browser run caught).
    assert "mmfdb/deposit/__init__.py" in names, "no mmfdb.deposit: the Zenodo plugin dies"
    assert "mmfdb/deposit/zenodo.py" in names and "mmfdb/deposit/record.py" in names
    assert "mmfdb/security/credentials.py" in names, "the token store module is missing"
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


def test_the_glyph_vocabulary_and_the_split_buttons_are_baked(tmp_path):
    """chisurf's own glyph vocabulary is in the atlas the page ships.

    The manifest-icon test below guards the plugin menus; the shell's own
    buttons spell their marks with ``chisurf.core.glyphs`` and plain UI
    strings, which no manifest carries -- so the Console dock's *Split ⇥* /
    *Split ⇣* drew the ``¤`` placeholder on the web page ("still characters
    missing, for vertical and horz splitting of the terminals") and every
    Glyphs.* pictograph added since the last bake did the same. The glyphs
    are read from the installed ``chisurf.core.glyphs`` plus a short list of
    UI strings that spell marks inline, so a vocabulary addition fails here
    until the atlas is re-baked.
    """
    import ast as _ast
    import inspect as _inspect

    import chisurf.core.glyphs as glyphs_mod

    import emtk  # noqa: F401 - the atlas the page ships is emtk's

    from emtk.grapheme import glyph_of

    from emtk.web.serve import pack_zip

    bundle = _bundle()
    archive = zipfile.ZipFile(pack_zip(bundle, tmp_path / "app.zip"))
    meta = json.loads(archive.read("emtk/atlas/chrome.json").decode("utf-8"))
    charset = set(meta["charset"])
    colour_cells = meta.get("icons") or {}

    # every non-ASCII constant of the glyph vocabulary...
    wanted: set[str] = set()
    for node in _ast.walk(_ast.parse(_inspect.getsource(glyphs_mod))):
        if isinstance(node, _ast.Assign):
            values = node.value.elts if isinstance(node.value, (_ast.Tuple, _ast.List)) else [node.value]
            for v in values:
                if isinstance(v, _ast.Constant) and isinstance(v.value, str):
                    wanted |= {c for c in v.value if ord(c) > 127}
    # ...plus the marks UI strings spell inline (terminal split, LUT steps,
    # the script letters the FRET literature writes units with)
    wanted |= set("⇥⇣①②ℓ′†★☆☐☑✗✖✎✏⏸⏹⏭⏮↺↻⬆⬇●◉⦿∠⊛ϵ")
    wanted = {glyph_of(c) if ord(c) > 0x1F000 else c for c in wanted}
    wanted -= {"\ufe0f", "\u200d"}

    missing = sorted(
        f"{c!r} (U+{ord(c):04X})" for c in wanted
        if c not in charset and c not in colour_cells
    )
    assert not missing, (
        f"shell glyphs the shipped atlas cannot draw -- re-bake "
        f"emtk's atlas (tools/bake_chrome_atlas.py): {missing}"
    )


def test_every_plugin_manifest_icon_is_a_baked_glyph(tmp_path):
    """The icons the plugin menus spell are in the atlas the page ships.

    The browser has no font engine: the runtime glyph cache has nothing to
    load there, so a manifest ``icon`` outside the baked rows drew the ``¤``
    placeholder -- the owner's "all emoticons and icons are missing". The
    icons are read from the packed manifests themselves, so a plugin that adds
    a new pictograph fails here until the atlas is re-baked.

    With the colour band, *baked* is not enough: a monochrome mask in the
    text colour is the grey silhouette the owner rejected ("the icons are
    super ugly and black and white"). So every manifest icon must also be in
    the atlas's colour table -- emoji rasterised from a pinned Noto Color
    Emoji at bake time -- and the shipped PNG must actually carry the cell's
    chroma, because a table that points at an empty region draws nothing
    and a mask draws grey.
    """
    import json

    import numpy as np

    from emtk.grapheme import glyph_of

    from emtk.gpu_atlas import png_decode
    from emtk.web.serve import pack_zip

    bundle = _bundle()
    archive = zipfile.ZipFile(pack_zip(bundle, tmp_path / "app.zip"))
    meta = json.loads(archive.read("emtk/atlas/chrome.json").decode("utf-8"))
    charset = set(meta["charset"])
    tables = meta["glyphs"]
    colour_cells = meta.get("icons") or {}
    assert len(colour_cells) >= 100, \
        f"only {len(colour_cells)} colour pictographs baked"
    width, height, rgba = png_decode(archive.read("emtk/atlas/chrome.png"))
    atlas_rgba = np.frombuffer(bytes(rgba), dtype=np.uint8).reshape(height, width, 4)

    checked = 0
    missing = []
    mono_only = []
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
        # the colour band is what the page draws for it; a mono-only icon is
        # the grey bake back again. A handful of marks are monochrome *by
        # design* -- ◐ ▮ ◎ ↔ have no colour form in the pinned face (and the
        # geometric ones are drawn as text marks everywhere) -- so the floor
        # below is a count, not a per-icon demand.
        if base not in colour_cells:
            mono_only.append(f"{'/'.join(parts[2:-1])}: {icon!r}")
            continue
        x, y, w, h = colour_cells[base]
        cell = atlas_rgba[y:y + h, x:x + w]
        opaque = cell[..., 3] > 64
        assert opaque.any(), f"{name}: {icon!r}'s colour cell is blank in the PNG"
        r, g, b = (cell[..., i][opaque].astype(int) for i in range(3))
        assert ((r != g) | (g != b)).any(), \
            f"{name}: {icon!r}'s colour cell carries no chroma"
    assert checked >= 9, f"only {checked} manifest icons found -- enumeration broke"
    assert not missing, f"manifest icons the shipped atlas cannot draw: {missing}"
    assert len(mono_only) <= 6, \
        f"manifest icons that lost their colour cell (re-bake the atlas): {mono_only}"
    assert checked - len(mono_only) >= 100, \
        f"only {checked - len(mono_only)} of {checked} manifest icons draw in colour"


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
    # requests + pyodide-http: the Zenodo deposit client's transport, routed
    # over fetch (a tab has no sockets).
    assert config["pyodide_packages"] == [
        "numpy", "Pillow", "scipy", "pyyaml", "lzma", "fonttools",
        "requests", "pyodide-http",
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


def test_the_desktop_only_database_tools_are_not_packed(tmp_path):
    """The mmfdb database plugins are desktop-only: never packed, never offered.

    The 2026-10-23 browser plugin sweep opened every plugin the page offers:
    78 built, drew and closed; the four mmfdb tools died building -- their
    imports reach the database layer (``mmfdb.repository`` / ``schema`` /
    ``client`` / ``provenance``) that :data:`MMFDB_KEEP` never ships, and the
    RPC ones need loopback sockets a tab cannot bind. They are excluded from
    the page (:data:`PLUGIN_EXCLUDE`); this pins that they stay excluded and
    that the exclusion does not overmatch a working web plugin.
    """
    from chisurf.web import PLUGIN_EXCLUDE
    from emtk.web.serve import pack_zip

    archive = zipfile.ZipFile(pack_zip(_bundle(), tmp_path / "excluded.zip"))
    names = archive.namelist()
    for name in PLUGIN_EXCLUDE:
        assert not [n for n in names if n.startswith(f"chisurf/plugins/{name}/")], (
            f"chisurf/plugins/{name} is desktop-only and must not ship on the page"
        )
    # the exclusion is surgical: working web plugins still pack
    for still_ships in ("chisurf/plugins/core/zenodo_deposit/manifest.json",
                        "chisurf/plugins/tttr/tttr_time_windows/manifest.json"):
        assert still_ships in names, f"{still_ships} must still pack"


def test_the_packed_plugin_set_imports_without_the_database_layer(tmp_path):
    """Every packed plugin entrypoint imports with the database layer blocked.

    The page ships mmfdb's config, deposit and security only. A packed plugin
    whose import chain reaches any other mmfdb submodule builds into an error
    panel when opened on the page (the sweep's four findings). Importing each
    packed entrypoint module -- which executes its package ``__init__`` too --
    with those submodules blocked must succeed: this is the page's import
    reality, replayed on the desktop.
    """
    import builtins

    from emtk.web.serve import pack_zip

    archive = zipfile.ZipFile(pack_zip(_bundle(), tmp_path / "dblock.zip"))
    entrypoints = []
    for name in archive.namelist():
        if not re.fullmatch(r"chisurf/plugins/(?:[^/]+/)*manifest\.json", name):
            continue
        entry = json.loads(archive.read(name)).get("entrypoints", {}).get("emtk", "")
        module = entry.split(":", 1)[0] if entry else ""
        if module:
            entrypoints.append(module)
    assert len(entrypoints) > 60, "the packed plugin set looks truncated"

    database_layer = (
        "mmfdb.repository", "mmfdb.schema", "mmfdb.client", "mmfdb.provenance",
        "mmfdb.admin", "mmfdb.samples", "mmfdb.models", "mmfdb.users",
    )
    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        for missing in database_layer:
            if name == missing or name.startswith(missing + "."):
                raise ModuleNotFoundError(f"No module named {missing!r}")
        return real_import(name, *args, **kwargs)

    failures = []
    for module in sorted(set(entrypoints)):
        builtins.__import__ = blocked
        try:
            with unittest_mock.patch.dict(sys.modules):
                __import__(module, fromlist=["_"])
        except ModuleNotFoundError as error:
            failures.append(f"{module}: {error}")
        finally:
            builtins.__import__ = real_import
    assert not failures, (
        "packed plugins import the mmfdb database layer the page never ships:\n  "
        + "\n  ".join(failures)
    )


def test_the_packed_page_imports_only_what_it_ships(tmp_path):
    """Every module-level import reachable from the page must be shipped.

    The web shell opened the Hidden Markov model tool into an error panel:
    ``ModuleNotFoundError: No module named 'click'`` -- the GUI's view model
    imported one loader from the CLI module, and the CLI module is click from
    its first line. The page never ships click; nothing compared what the
    packed page can import with what it packs. This walks module-level
    imports transitively -- the web app's factory and every plugin GUI the
    shell can open, through every packed module they reach -- and fails on
    the first import the page cannot satisfy: not stdlib, not packed, not a
    Pyodide package, not in a shipped wheel.
    """
    import ast
    import io

    import sys as _sys

    from emtk.web.serve import DEFAULT_PYODIDE_PACKAGES, pack_zip

    bundle = _bundle()
    archive = zipfile.ZipFile(pack_zip(bundle, tmp_path / "closure.zip"))

    # The packed modules, by dotted name.
    packed = {}
    for name in archive.namelist():
        if not name.endswith(".py"):
            continue
        parts = name[:-3].split("/")
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if parts:
            packed[".".join(parts)] = name

    # Importable roots the wheels provide: each wheel's top-level packages.
    wheel_roots = set()
    for wheel_path in getattr(bundle, "wheels", []):
        wheel = zipfile.ZipFile(io.BytesIO(Path(wheel_path).read_bytes()))
        for entry in wheel.namelist():
            if entry.endswith((".py", ".so")) and "/" in entry:
                top = entry.split("/")[0]
                if not top.startswith("_"):
                    wheel_roots.add(top)
            elif entry.endswith(".py"):
                wheel_roots.add(entry[:-3])

    # Pyodide distribution packages, by the names they import as (the
    # distribution name and the import name are not always the same word).
    _IMPORT_NAME = {"Pillow": "PIL", "pyyaml": "yaml", "pyodide-http": "pyodide_http",
                    "fonttools": "fontTools"}
    pyodide_roots = {p for p in (*DEFAULT_PYODIDE_PACKAGES, *bundle.pyodide_packages)}
    pyodide_roots = {_IMPORT_NAME.get(name, name) for name in pyodide_roots}
    pyodide_roots |= set(_IMPORT_NAME.values())

    allowed = set(_sys.stdlib_module_names) | set(packed) | wheel_roots | pyodide_roots

    # Roots: the page's app factory and every plugin entry the shell can
    # open -- the ``emtk`` entrypoint each packed manifest declares, which is
    # exactly the module the shell imports when the tool opens (the bundle
    # excludes the desktop-only plugins, so what is packed is what opens).
    roots = []
    for name in archive.namelist():
        if not re.fullmatch(r"chisurf/plugins/(?:[^/]+/)*manifest\.json", name):
            continue
        entry = json.loads(archive.read(name)).get("entrypoints", {}).get("emtk", "")
        module = entry.split(":", 1)[0] if entry else ""
        if module and module in packed:
            roots.append(module)
    roots += [name for name in packed  # a manifest-less plugin still ships a GUI
              if re.fullmatch(r"chisurf\.plugins(?:\.[^.]+){1,2}\.gui\.app", name)]
    # A multi-app page mounts more than one entry: every app the build
    # names is a root, exactly like the default one.
    for spec in dict(getattr(bundle, "apps", {}) or {}).values():
        module = spec.split(":", 1)[0]
        if module in packed:
            roots.append(module)
    roots = list(dict.fromkeys([*roots, "chisurf.web"]))
    assert roots, "no plugin GUIs packed; the shell would have nothing to open"

    def module_imports(dotted: str):
        """Module-level imports of *dotted*, as (level, target, root, is_alias)."""
        source = archive.read(packed[dotted]).decode("utf-8", "replace")
        tree = ast.parse(source)
        found = []
        statements = list(ast.iter_child_nodes(tree))
        while statements:
            node = statements.pop()
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue  # runs only when called, not when the module opens
            if isinstance(node, ast.Import):
                found.extend((0, alias.name, alias.name.split(".")[0], False)
                             for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                level = node.level or 0
                base = node.module or ""
                found.append((level, base, base.split(".")[0], False))
                for alias in node.names:  # from X import name: X.name may be a module
                    found.append((level, f"{base}.{alias.name}" if base else alias.name,
                                  base.split(".")[0], True))
            elif isinstance(node, ast.If) and isinstance(node.test, ast.Name) \
                    and node.test.id == "TYPE_CHECKING":
                pass  # never executes: typing-only imports
            elif isinstance(node, ast.Try):
                optional = any(
                    getattr(handler.type, "id", getattr(handler.type, "attr", ""))
                    in ("ImportError", "ModuleNotFoundError", "Exception")
                    for handler in node.handlers
                )
                if not optional:
                    statements.extend(ast.iter_child_nodes(node))
                # an ImportError-guarded import is optional: the page runs
                # without it, and the guard says so in code
            else:
                statements.extend(ast.iter_child_nodes(node))
        return found

    def resolve(dotted: str, level: int, target: str):
        """Absolute dotted name of an import in module *dotted*, or None."""
        if not level:
            return target or None
        is_package = packed[dotted].endswith("/__init__.py")
        parts = dotted.split(".")
        drop = level if not is_package else level - 1
        package = ".".join(parts[: len(parts) - drop]) if drop else dotted
        return f"{package}.{target}" if target else (package or None)

    seen, queue, missing = set(), list(dict.fromkeys(roots)), []
    while queue:
        dotted = queue.pop()
        if dotted in seen or dotted not in packed:
            continue
        seen.add(dotted)
        for level, target, root, is_alias in module_imports(dotted):
            absolute = resolve(dotted, level, target)
            resolved_root = root if not level else (absolute or root).split(".")[0]
            if resolved_root not in allowed and absolute not in packed:
                missing.append(f"{packed[dotted]}: import {'.' * level}{target}"
                               f" (needs {resolved_root!r}, not shipped)")
                continue
            # A keep-limited package ships only some of its submodules (mmfdb
            # keeps config, deposit and security; chimol its viewer core).
            # There the root being packed is not enough: a submodule named by
            # a real import but not packed is a ModuleNotFoundError when the
            # tool opens -- the 2026-10-23 browser sweep caught
            # spectra_downloader's package __init__ importing mmfdb.repository,
            # which never ships. ``from X import name`` names are classes and
            # functions as often as modules, so only whole-module imports
            # (import X.Y, from X.Y import z) carry the requirement.
            keep_limited = {"mmfdb", "chimol"}
            if (
                not is_alias
                and absolute
                and resolved_root in keep_limited
                and absolute not in packed
            ):
                missing.append(f"{packed[dotted]}: import {'.' * level}{target}"
                               f" ({absolute!r}: its package ships, this submodule"
                               f" does not)")
                continue
            # visit the target and the packages it executes
            if absolute:
                parts = absolute.split(".")
                for depth in range(1, len(parts) + 1):
                    queue.append(".".join(parts[:depth]))

    assert not missing, (
        "the packed page imports modules it does not ship -- a tool opened "
        "on the page would die with ModuleNotFoundError:\n  "
        + "\n  ".join(sorted(set(missing))[:25])
    )
