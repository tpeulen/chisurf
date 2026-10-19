"""Drive every declared plugin in a bounded, hermetic subprocess.

Run selected plugin ids with pytest ``-k``. Workers always leave a JSON result,
including failed control names and traceback, beside their PNG in ``renders/e2e``.
No plugin is silently skipped when its factory, tour, or tooltip inventory fails.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import traceback
import warnings
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "test"
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

if __name__ != "__main__":
    from chisurf.emtk.plugins import manifests

    CATALOG = manifests()
else:
    # The worker installs scratch paths before importing ChiSurf settings.
    CATALOG = {}
IDS_EMTK = sorted(i for i, m in CATALOG.items() if m.get("entrypoints", {}).get("emtk"))
IDS_ACTION = sorted(
    i
    for i, m in CATALOG.items()
    if m.get("entrypoints", {}).get("action")
    and not m["entrypoints"].get("emtk")
)
SIZE = (1100, 720)
#: The real-use QA matrix (okf/workflows/testing.md, "Real-use QA matrix"). The base sweep above
#: drives every plugin at one size, English, scale 1, with instantaneous press/release; each
#: variant changes exactly one of those. ``driver: realistic`` is emtk.testing_realistic: events in
#: the platform's vocabulary through emtk.native.CanvasEvents, press and release in different
#: frames with the hand moving, the real device painter at the content scale.
VARIANTS = {
    "size_800x600": {"size": (800, 600)},
    "size_1920x1080": {"size": (1920, 1080)},
    "resize": {"size": (1100, 720), "resize_to": (800, 600)},
    "scale2": {"size": (1100, 720), "driver": "realistic", "scale": 2.0},
    "lang_de": {"size": (1100, 720), "lang": "de"},
    "lang_fr": {"size": (1100, 720), "lang": "fr"},
    "realistic": {"size": (1100, 720), "driver": "realistic"},
    # Settings > Fonts magnification 1.25 in an 800 x 600 window: a 640 x 480 layout drawn larger.
    "zoom_125": {"size": (800, 600), "driver": "realistic", "zoom": 1.25},
}
#: The variant this worker runs (``--variant``); ``{}`` is the base sweep.
VARIANT: dict = {}


def matrix_cases(ids, mode=None, sample=None):
    """``(variant, plugin)`` pairs the matrix runs.

    ``CHISURF_E2E_MATRIX``: ``off``; ``sample`` (default) -- per variant
    ``CHISURF_E2E_MATRIX_SAMPLE`` plugins (3), a deterministic hash-ranked choice rotated by
    ``CHISURF_E2E_MATRIX_SEED`` so CI covers the catalogue over successive seeds; ``full`` -- every
    variant times every plugin; or a comma list of variant names (full plugin set for those).
    """
    mode = (mode or os.environ.get("CHISURF_E2E_MATRIX", "sample")).strip().lower()
    if mode in ("", "off", "0", "none"):
        return []
    if mode == "full":
        return [(v, i) for v in VARIANTS for i in ids]
    if mode != "sample":
        chosen = [v.strip() for v in mode.split(",") if v.strip() in VARIANTS]
        return [(v, i) for v in chosen for i in ids]
    count = int(sample or os.environ.get("CHISURF_E2E_MATRIX_SAMPLE", "3"))
    seed = os.environ.get("CHISURF_E2E_MATRIX_SEED", "0")
    cases = []
    for variant in VARIANTS:
        ranked = sorted(
            ids, key=lambda i: hashlib.sha256(f"{seed}:{variant}:{i}".encode()).hexdigest()
        )
        cases += [(variant, i) for i in ranked[:count]]
    return cases


HARNESS_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
# The documented baseline remains recognizable; extra exclusions protect real
# accounts, remote jobs and hardware even when a plugin calls them "Run".
SKIP = re.compile(
    r"(open|load_file|save|browse|export|import|choose|folder|quit|close_window|close_about|close_app|close_host|delete)",
    re.I,
)
EXTERNAL = re.compile(
    r"(oauth|auth|login|logout|signin|account|credential|token|connect|disconnect|"
    r"upload|download|publish|deploy|submit|remote|server|hardware|device|acquire|"
    r"acquisition|record|start|run|compute|analyse|analyze|fit|simulate|shutdown|"
    r"remove|clear|reset_database|drop|erase|terminate|install|uninstall|archive|"
    r"sync|execute|send|commit|apply|activate|generate|train|retrain|optimize|"
    r"measure|capture|stream|emit|laser|shutter|update|user[ _-]*editor|switch[ _-]*user|"
    r"lsp|editor[ _-]*rpc|enable_rpc|python_lsp|show[ _-]*(key|token|secret)|reveal)",
    re.I,
)
CLICKABLE = frozenset(
    {
        "button",
        "small_button",
        "checkbox",
        "radio_button",
        "selectable",
        "combo",
        "input_text",
        "input_text_multiline",
        "input_float",
        "input_int",
        "input_double",
        "slider_float",
        "slider_int",
        "drag_float",
        "drag_int",
        "color_edit3",
        "color_edit4",
        "menu_item",
        "collapsing_header",
    }
)
CLICKABLE |= {"begin_tab_item", "tree_node", "list_box", "input_scalar"}
CLICKABLE |= {"autoform_fold"}


class Blocked(OSError, RuntimeError):
    """A side effect the harness refused; an OSError so a plugin's offline handling catches it."""


def artifact_dir():
    """Return the configured artifact directory as an absolute path."""
    return Path(os.environ.get("CHISURF_E2E_DIR", REPO / "renders" / "e2e")).resolve()


def artifact_stem(plugin_id):
    """Keep plugin ids filesystem-safe without flattening their identity."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", plugin_id)


def skip_reason(name, tags=()):
    """Explain the safety exclusion for a control; otherwise return None."""
    if {str(tag).lower() for tag in tags} & {"modal", "file", "dangerous", "external", "hardware"}:
        return "declared side-effect tag"
    if "↑ parent" in str(name).lower():
        return "scratch workspace boundary"
    glyphs = str(name).split()
    if glyphs and all(glyph in {"×", "✖", "✕", "＋", "➕"} for glyph in glyphs):
        return "structural create/delete glyph"
    if SKIP.search(str(name)):
        return "file/modal/destructive action"
    if EXTERNAL.search(str(name)):
        return "external/hardware/job/destructive action"
    return None


def walk(spec):
    """Yield nested sections without assuming that every plugin owns a spec."""
    sections = spec.get("sections", []) if isinstance(spec, dict) else spec
    for section in sections or ():
        if isinstance(section, dict):
            yield section
            yield from walk(section.get("sections", []))


def _isolated(plugin_id, mode, variant=None):
    """Launch one worker, retaining output and explicit crash/timeout evidence."""
    directory = artifact_dir() / variant if variant else artifact_dir()
    directory.mkdir(parents=True, exist_ok=True)
    result_path = directory / f"{artifact_stem(plugin_id)}.json"
    (directory / f"{artifact_stem(plugin_id)}.png").unlink(missing_ok=True)
    result_path.write_text(
        json.dumps(
            {
                "plugin": plugin_id,
                "mode": mode,
                "status": "running",
                "errors": ["worker did not finish"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    env = dict(os.environ)
    env.update(
        MPLBACKEND="Agg",
        PYTHONUNBUFFERED="1",
        CHISURF_E2E_DIR=str(directory),
    )
    sources = [
        str(REPO),
        str(REPO / "test"),
        str(REPO / "modules" / "chinet"),
        str(REPO / "modules" / "imp-tricks" / "src"),
        str(REPO / "modules" / "mmfdb" / "src"),
    ]
    if env.get("PYTHONPATH"):
        sources.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(sources)
    timeout = float(os.environ.get("CHISURF_E2E_TIMEOUT", "120"))
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--run-one",
        plugin_id,
        "--mode",
        mode,
    ]
    if variant:
        command += ["--variant", variant]
        # A realistic click takes 8 frames, not 3; a big window draws more per frame.
        timeout *= 3.0 if VARIANTS[variant].get("driver") == "realistic" else 1.5
    try:
        completed = subprocess.run(
            command, cwd=REPO, env=env, capture_output=True, text=True, timeout=timeout
        )
        output = completed.stdout + completed.stderr
    except subprocess.TimeoutExpired as exc:
        output = str(exc.stdout or "") + str(exc.stderr or "")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        result.update(status="failed", errors=[f"worker exceeded {timeout:g}s"])
        result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        (directory / f"{artifact_stem(plugin_id)}.log").write_text(output, encoding="utf-8")
        pytest.fail(f"{plugin_id}: worker exceeded {timeout:g}s; {result_path}")
    (directory / f"{artifact_stem(plugin_id)}.log").write_text(output, encoding="utf-8")
    if not result_path.exists():
        result_path.write_text(
            json.dumps(
                {
                    "plugin": plugin_id,
                    "mode": mode,
                    "status": "failed",
                    "errors": [f"worker exited {completed.returncode} without result"],
                },
                indent=2,
            )
        )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if completed.returncode and result.get("status") in ("passed", "running"):
        result["status"] = "failed"
        result.setdefault("errors", []).append(f"worker exited {completed.returncode}")
        result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    assert completed.returncode == 0 and result.get("status") == "passed", (
        f"{plugin_id}: {result.get('errors', [])}; worker exit {completed.returncode}; "
        f"artifacts: {result_path}\n{output[-4000:]}"
    )


@pytest.mark.e2e
@pytest.mark.parametrize("plugin_id", IDS_EMTK, ids=str)
def test_emtk_plugin_survives_every_control(plugin_id):
    """Assert each native manifest's factory and safe interaction scenario."""
    _isolated(plugin_id, "emtk")


@pytest.mark.e2e
@pytest.mark.parametrize(("variant", "plugin_id"), matrix_cases(IDS_EMTK), ids=lambda v: str(v))
def test_emtk_plugin_real_use(variant, plugin_id):
    """The same sweep under one real-use variant: size, resize, scale, language or input."""
    _isolated(plugin_id, "emtk", variant)


@pytest.mark.e2e
@pytest.mark.parametrize("plugin_id", IDS_ACTION, ids=str)
def test_action_plugin_resolves_to_a_callable(plugin_id):
    """An action entrypoint opens no window: prove its target imports and is callable.

    Running it needs the live main window (``requires_main_window``), so it is
    classified as an action and resolved, never driven as a window.
    """
    import importlib

    action = CATALOG[plugin_id]["entrypoints"]["action"]
    module, attribute = action["target"].split(":", 1)
    assert callable(getattr(importlib.import_module(module), attribute))
    assert action.get("description"), "an action entrypoint states what it does"


def _guards(stack, result):
    """Cancel OS dialogs and block browsers/network while preserving local rendering."""
    import socket
    import webbrowser

    from emtk.file_dialog import FileDialog

    # A "Copy …" button or menu row must not overwrite the user's clipboard: keep it in memory.
    from emtk import clipboard as emtk_clipboard

    copied: list = []
    stack.enter_context(patch.object(emtk_clipboard, "_hook", copied.append))
    stack.enter_context(
        patch.object(emtk_clipboard, "_paste_hook", lambda: copied[-1] if copied else "")
    )
    stack.enter_context(patch.object(webbrowser, "open", return_value=False))
    stack.enter_context(patch.object(webbrowser, "open_new", return_value=False))
    stack.enter_context(patch.object(webbrowser, "open_new_tab", return_value=False))

    def feed_file_dialog(dialog, *args, **kwargs):
        """Open/folder dialogs take the plugin's demo; save dialogs and demo-less ones cancel."""
        result["dialogs_closed"] += 1
        mode, filters = getattr(dialog, "mode", "open"), getattr(dialog, "filters", ())
        chosen = demo_choice(result.get("demo_dir"), mode, filters)
        if not chosen and mode == "open" and result.get("stub_dir"):
            chosen = stub_file(result["stub_dir"], filters)
        if chosen:
            result.setdefault("demo_fed", []).append(chosen[0])
            return chosen
        return False

    stack.enter_context(patch.object(FileDialog, "draw", feed_file_dialog))
    connect = socket.socket.connect

    def local_only(sock, address):
        """Prevent plugin side effects through any IPv4/IPv6 service."""
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            result["blocked_actions"].append("socket.connect")
            raise Blocked("E2E blocks network/service connections")
        return connect(sock, address)

    stack.enter_context(patch.object(socket.socket, "connect", local_only))
    stack.enter_context(patch.object(socket.socket, "connect_ex", local_only))
    import zmq

    def no_zmq_connection(sock, address):
        """Keep C-level ZeroMQ sockets away from the user's actual daemons."""
        result["blocked_actions"].append(
            {
                "operation": "zmq.Socket.connect",
                "phase": result.get("phase"),
                "control": result.get("current_control"),
            }
        )
        raise Blocked("E2E blocks real ZeroMQ service connections")

    stack.enter_context(patch.object(zmq.Socket, "connect", no_zmq_connection))
    stack.enter_context(patch.object(zmq.Socket, "bind", no_zmq_connection))

    def no_zmq_io(*args, **kwargs):
        """Fail offline RPC immediately rather than blocking on an unconnected socket."""
        raise Blocked("E2E ZeroMQ service I/O is offline")

    for method in ("send", "recv", "send_multipart", "recv_multipart"):
        stack.enter_context(patch.object(zmq.Socket, method, no_zmq_io))

    def no_external_process(*args, **kwargs):
        """Do not launch language servers, installers, or user tools from controls."""
        result["blocked_actions"].append(
            {
                "operation": "external process",
                "phase": result.get("phase"),
                "control": result.get("current_control"),
            }
        )
        raise Blocked("E2E blocks external process launch")

    stack.enter_context(patch.object(subprocess, "Popen", no_external_process))
    for method in dir(os):
        if method.startswith(("exec", "spawn")) or method in ("system", "popen", "startfile"):
            if callable(getattr(os, method)):
                stack.enter_context(patch.object(os, method, no_external_process))


def demo_choice(demo_dir, mode, filters):
    """Pick what a file/folder dialog should return from a plugin's demo directory.

    Parameters
    ----------
    demo_dir : str or Path or None
        Folder the plugin's own ``demo.make_demo`` wrote into, or None.
    mode : str
        ``open``, ``folder`` or ``save``; save always cancels.
    filters : sequence
        The dialog's ``(label, patterns)`` pairs; empty accepts any file.

    Returns
    -------
    list of str
        One path, or an empty list when there is nothing to offer.
    """
    import fnmatch

    if not demo_dir or mode == "save" or not Path(demo_dir).is_dir():
        return []
    root = Path(demo_dir)
    if mode == "folder":
        return [str(root)]
    patterns = [p.lower() for _, pats in filters for p in pats] or ["*"]
    files = sorted(p for p in root.rglob("*") if p.is_file())
    for pattern in patterns:
        for path in files:
            if fnmatch.fnmatch(path.name.lower(), pattern):
                return [str(path)]
    return []


#: Smallest valid text for formats a plugin can read when it ships no demo of its own.
STUBS = {
    ".pdb": "ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00  0.00           N\n"
    "ATOM      2  CA  ALA A   1       1.458   0.000   0.000  1.00  0.00           C\n"
    "ATOM      3  C   ALA A   1       2.009   1.420   0.000  1.00  0.00           C\nEND\n",
    ".csv": "x,y\n1,2\n2,4\n3,6\n",
    ".txt": "1 2\n2 4\n3 6\n",
    ".dat": "1 2\n2 4\n3 6\n",
    ".json": "{}\n",
    ".xy": "1 2\n2 4\n3 6\n",
}


def stub_file(directory, filters):
    """Write a tiny readable file for the first text format a dialog accepts.

    Parameters
    ----------
    directory : Path
        Folder to write into (created on demand).
    filters : sequence
        The dialog's ``(label, patterns)`` pairs.

    Returns
    -------
    list of str
        The new path, or an empty list when no accepted format has a stub.
    """
    for _, patterns in filters:
        for pattern in patterns:
            suffix = pattern.lower().lstrip("*")
            if suffix in STUBS:
                directory = Path(directory)
                directory.mkdir(parents=True, exist_ok=True)
                path = directory / f"stub{suffix}"
                path.write_text(STUBS[suffix], encoding="utf-8")
                return [str(path)]
    return []


def provision_demo(plugin_id, scratch, result=None):
    """Let a plugin generate its own demo data, as its guided tour would.

    Looks for ``make_demo`` / ``make_example`` in the package's ``demo`` module,
    and for the ``build(root)`` fixtures the burst plugins keep in
    ``test[s]/demo_data.py`` / ``demo_folder.py``, and calls it with a scratch folder.
    A generator that raises is recorded in ``result["demo_error"]``, never hidden.

    Parameters
    ----------
    plugin_id : str
        Manifest id.
    scratch : Path
        Hermetic scratch root.
    result : dict, optional
        Worker result, receives ``demo_error`` on failure.

    Returns
    -------
    Path or None
        Folder holding the demo, or None when the plugin ships no generator.
    """
    import importlib

    from chisurf.emtk.plugins import manifests

    # CATALOG is empty inside the worker (it must install scratch paths before importing).
    target = ((manifests().get(plugin_id) or {}).get("entrypoints") or {}).get("emtk") or ""
    parts = target.split(":")[0].split(".")
    candidates = [
        ("demo", ("make_demo", "make_example", "write_demo", "write_example")),
        ("test.demo_data", ("build",)),
        ("tests.demo_data", ("build",)),
        ("test.demo_folder", ("build",)),
        ("tests.demo_folder", ("build",)),
    ]
    for end in range(len(parts), 2, -1):
        package = ".".join(parts[:end])
        for suffix, names in candidates:
            try:
                demo = importlib.import_module(f"{package}.{suffix}")
            except ImportError:
                continue
            for name in names:
                maker = getattr(demo, name, None)
                if not callable(maker):
                    continue
                folder = Path(scratch) / "demo"
                folder.mkdir(exist_ok=True)
                try:
                    made = maker(folder)
                except Exception as exc:
                    if result is not None:
                        result["demo_error"] = f"{package}.{suffix}.{name}: {exc!r}"
                    continue
                if isinstance(made, (str, Path)) and Path(made).exists():
                    made = Path(made)
                    return made if made.is_dir() else made.parent
                return folder
    return None


def control_tags(spec, control):
    """Read declared action tags before deciding whether a control may be clicked."""
    name = str(control).split("##")[-1]
    tags = set()
    for section in walk(spec):
        candidates = [section, *(section.get("buttons") or [])]
        for item in candidates:
            if isinstance(item, dict) and name in (
                item.get("attr"),
                item.get("target"),
                item.get("key"),
                item.get("action"),
            ):
                declared = item.get("tags", [])
                tags.update([declared] if isinstance(declared, str) else declared)
                tags.update(
                    key
                    for key in ("modal", "file", "dangerous", "external", "hardware")
                    if item.get(key) is True
                )
    return tags


def dialog_open(app):
    """Recognize native modal/file state without opening or selecting a resource."""
    for owner in (app, getattr(app, "model", None)):
        if owner is not None and any(
            getattr(owner, name, None) not in (None, False) for name in ("dialog", "file_dialog")
        ):
            return True
    # A stack of open modals (burst_ebfret's ``gui.dialogs``): open while it is not empty.
    for owner in (app, getattr(app, "model", None), getattr(app, "gui", None)):
        stack = getattr(owner, "dialogs", None)
        if isinstance(stack, (list, tuple)) and stack:
            return True
    return bool(getattr(getattr(app, "picker", None), "is_open", False))


def tour_for(app):
    """Resolve real native guide owner aliases without inventing a fake tour."""
    owners = [app]
    for name in ("header_gui", "help_window", "help", "guide_owner"):
        owner = getattr(app, name, None)
        if owner is not None:
            owners.append(owner)
    # Calculator ImApps compose a stored phasor_gui/fcs_gui/etc. renderer.
    owners.extend(
        owner
        for name, owner in getattr(app, "__dict__", {}).items()
        if name.endswith("_gui") and owner not in owners
    )
    for owner in owners:
        for name in ("tour", "guide"):
            tour = getattr(owner, name, None)
            if all(callable(getattr(tour, method, None)) for method in ("start", "next", "stop")):
                return tour
    return None


#: The app the worker is driving, for helpers that need its dock managers.
CURRENT_APP = None


def checkpoint(result):
    """Retain the current phase/control even if native code crashes or hangs."""
    path = artifact_dir() / f"{artifact_stem(result['plugin'])}.json"
    path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")


def visible_rectangle(row, size):
    """Intersect the submitted control with its actual clip and canvas."""
    rect = row.get("rect")
    if rect is None:
        return None
    clip = row.get("clip_rect", (0, 0, *size))
    left, top = max(rect[0], clip[0], 0), max(rect[1], clip[1], 0)
    right = min(rect[0] + rect[2], clip[0] + clip[2], size[0])
    bottom = min(rect[1] + rect[3], clip[1] + clip[3], size[1])
    return (
        (left, top, right - left, bottom - top) if right - left > 2 and bottom - top > 2 else None
    )


def painter_rectangle(painter, rect):
    """Apply actual painter adapter geometry to produce host-global coordinates."""
    from emtk.offset_painter import OffsetPainter
    from emtk.scaled_painter import ScaledPainter

    if rect is None:
        return None
    x, y, w, h = rect
    while isinstance(painter, (OffsetPainter, ScaledPainter)):
        if isinstance(painter, OffsetPainter):
            x, y = x + painter.x, y + painter.y
        else:
            x, y, w, h = x * painter.k, y * painter.k, w * painter.k, h * painter.k
        painter = painter.painter
    return x, y, w, h


def implot_clipped(plot):
    """Samples of *plot*'s lines and scatters that lie outside its current view, as strings.

    A view that auto-ranged must contain every finite sample; on a log axis only the positive
    ones can be drawn at all. A peak sitting on (or past) the frame is the defect this finds: a
    log axis padded in linear space, a curve left out of the fit.
    """
    import math

    out = []
    x_axis, y_axis = plot.x_axis(0), plot.y_axis(0)
    for record in getattr(plot, "records", []):
        pts = record.get("pts")
        if record.get("kind") not in ("line", "scatter") or not pts:
            continue
        for axis_name, axis, index in (("x", x_axis, 0), ("y", y_axis, 1)):
            log = axis.scale == 2
            values = [
                p[index] for p in pts if math.isfinite(p[index]) and (p[index] > 0 or not log)
            ]
            if not values:
                continue
            lo, hi = axis.range_min, axis.range_max
            top, bottom = max(values), min(values)
            if top >= hi or bottom <= lo:
                out.append(
                    f"{record.get('label')} {axis_name}: data {bottom:g}..{top:g} outside {lo:g}..{hi:g}"
                )
    return out


def chiplot_clipped(canvas):
    """The chiplot equivalent of :func:`implot_clipped`: drawn axis ranges against the data extent."""
    out = []
    drawn = getattr(canvas, "_drawn", None)
    if not drawn:
        return out
    for axis, name in ((0, "x"), (1, "y")):
        data, _placed = canvas._extent(axis)
        if data is None or name not in drawn:
            continue
        lo, hi = sorted(drawn[name])
        if data[0] < lo - 1e-9 or data[1] > hi + 1e-9:
            out.append(f"{name}: data {data[0]:g}..{data[1]:g} outside {lo:g}..{hi:g}")
    return out


@contextmanager
def recorded_plots():
    """Record every plot a frame draws: implot plots and chiplot panels, in host coordinates.

    Yields a list the caller clears before a frame; each entry is a dict with ``key`` (stable
    across frames), ``area`` (the plot area), ``button`` (where the "A" auto-range button is or
    would be), ``shown`` (whether it is drawn) and ``opted_out`` (no inputs, or the per-plot
    opt-out).
    """
    from emtk import im, implot
    from emtk.widgets import auto_range

    from chisurf.chiplot.backends.emtk_backend import EmtkCanvas

    plots: list = []
    original_end, original_draw = implot.end_plot, EmtkCanvas.draw

    def end_plot():
        plot = implot.gp.current_plot
        original_end()
        if plot is None:
            return
        painter = im.get_current_context().p
        x0, y0, x1, y1 = plot.plot_rect
        area = (x0, y0, x1 - x0, y1 - y0)
        plots.append(
            {
                "key": ("implot", plot.id),
                "kind": "implot",
                "area": painter_rectangle(painter, area),
                "button": painter_rectangle(painter, auto_range.button_rect(*area)),
                "shown": implot._auto_range_shown(plot),
                "opted_out": bool(
                    plot.flags & (implot.FLAGS_NO_INPUTS | implot.FLAGS_NO_AUTO_RANGE_BUTTON)
                )
                # A plot whose every axis is input/range-locked (ndxplorer's marginals draw
                # with AXIS_FLAGS_LOCK: the view must stay where the caller put it) can never
                # leave auto-range, so its "A" button can never appear -- by design, not a
                # coverage failure. The same verdict FLAGS_NO_AUTO_RANGE_BUTTON gets.
                or not any(ax.enabled and not ax.is_input_locked() for ax in plot.axes),
                "clipped": (
                    implot_clipped(plot)
                    if not implot._auto_range_shown(plot)
                    and not any(ax.enabled and ax.has_range for ax in plot.axes)
                    else []
                ),
            }
        )

    def draw(canvas, painter, x, y, w, h):
        original_draw(canvas, painter, x, y, w, h)
        rect = canvas._auto_button_rect
        plots.append(
            {
                "key": ("chiplot", id(canvas)),
                "kind": "chiplot",
                "area": painter_rectangle(painter, (x, y, w, h)),
                "button": painter_rectangle(painter, rect) if rect else None,
                "shown": canvas._auto_button_shown(),
                "opted_out": not (canvas._auto_button and canvas._interactive),
                "clipped": chiplot_clipped(canvas) if all(canvas.is_auto_range()) else [],
            }
        )

    with patch.object(implot, "end_plot", end_plot), patch.object(EmtkCanvas, "draw", draw):
        yield plots


#: Plots per tool the auto-range phase exercises; the rest of a dense dashboard repeats them.
AUTO_RANGE_PLOTS = 4


def exercise_auto_range(driver, result):
    """Every plot drawn now: "A" hidden while auto-ranged, shown once zoomed, gone on a click.

    Run on the first frame and again after the tour, which loads the demo data most tools only
    plot once they have it; a plot already exercised is not repeated.

    The wheel is tried first and a drag pan second (a plot whose wheel a scrolling parent takes is
    still zoomable that way); a plot neither reaches is a finding. Plots that opted out (no inputs,
    or the per-plot opt-out flag) are only listed.
    """
    size = _layout_size(driver)

    def on_screen(rect, smallest=24.0):
        return (
            rect is not None
            and rect[2] > smallest
            and rect[3] > smallest
            and visible_rectangle({"rect": rect, "clip_rect": (0, 0, *size)}, size) == tuple(rect)
        )

    def drag(start, end):
        if callable(getattr(driver, "drag", None)):
            driver.drag(start, end)
            return
        from emtk.events import LEFT_BUTTON

        driver.hover(start)
        driver.surface.on_pointer_press(*start, LEFT_BUTTON, 0)
        driver.frame()
        for k in range(1, 5):
            point = tuple(a + (b - a) * k / 4.0 for a, b in zip(start, end))
            driver.surface.on_pointer_move(*point, LEFT_BUTTON, 0)
            driver.frame()
        driver.surface.on_pointer_release(*end, LEFT_BUTTON, 0)
        driver.frame()

    with recorded_plots() as plots:

        def frame():
            plots.clear()
            driver.frame()
            return {p["key"]: p for p in plots}

        first = frame()
        report = result.setdefault("auto_range", [])
        done = {entry["plot"] for entry in report}
        fresh = [
            (key, plot)
            for key, plot in first.items()
            if f"{plot['kind']}:{key[1]!r}"[-90:] not in done
        ]
        for key, plot in fresh[:AUTO_RANGE_PLOTS]:
            entry = {"plot": f"{plot['kind']}:{key[1]!r}"[-90:], "opted_out": plot["opted_out"]}
            report.append(entry)
            if plot["opted_out"] or not on_screen(plot["area"]):
                entry["skipped"] = "opted out" if plot["opted_out"] else "not fully on screen"
                continue
            entry["shown_at_start"] = plot["shown"]
            if plot["clipped"]:
                entry["clipped"] = plot["clipped"]
                result["errors"].append(
                    f"auto-range: {entry['plot']} clips its data: {plot['clipped'][0]}"
                )
            x, y, w, h = plot["area"]
            centre = (x + w / 2.0, y + h / 2.0)
            current = plot
            if not current["shown"]:
                driver.wheel(1, at=centre)
                current = frame().get(key, current)
                entry["zoomed_by"] = "wheel"
                if not current["shown"]:
                    drag(centre, (centre[0] + w / 8.0, centre[1] + h / 8.0))
                    current = frame().get(key, current)
                    entry["zoomed_by"] = "drag"
            if not current["shown"]:
                result["errors"].append(f"auto-range: {entry['plot']} shows no A after zoom/pan")
                continue
            button = current["button"]
            bx, by, bw, bh = button
            # The plot area now, not before the zoom: zooming changes the tick labels, and with
            # them the width of the axis gutter (``100`` -> ``90``), so the area moves.
            x, y, w, h = current["area"]
            inside = x <= bx and bx + bw <= x + w + 0.5 and y <= by and by + bh <= y + h + 0.5
            if not (inside and on_screen(button, smallest=7.5)):
                result["errors"].append(f"auto-range: {entry['plot']} A outside its plot {button}")
                continue
            driver.click((bx + bw / 2.0, by + bh / 2.0))
            after = frame().get(key, current)
            entry["hidden_after_click"] = not after["shown"]
            if after["shown"]:
                result["errors"].append(f"auto-range: {entry['plot']} A still shown after a click")
            driver.hover((-1, -1))


def phase_on(name):
    """Whether this worker runs phase *name*: all of them, or those in ``CHISURF_E2E_PHASES``.

    ``CHISURF_E2E_PHASES=tour,context_menu`` runs one phase across the catalogue in minutes
    instead of the whole sweep; the factory frames always run.
    """
    chosen = os.environ.get("CHISURF_E2E_PHASES", "").strip()
    return not chosen or name in {part.strip() for part in chosen.split(",")}


#: Right-click targets per tool the context-menu phase exercises (plots, tables, canvases).
CONTEXT_MENU_TARGETS = 4
#: Every way a user closes a popup; after each, the next click must land.
CONTEXT_MENU_CLOSE_PATHS = (
    "item",
    "escape",
    "click_outside",
    "right_click_again",
    "wheel",
    "hover_rows",
)


@contextmanager
def recorded_frames():
    """Every emtk frame drawn while active, as ``{id(storage): (storage, painter)}``.

    A tool's own frame and every child frame it hosts: a context menu lives in the frame that
    opened it, and its row rectangles are in that frame's coordinates (the painter maps them).
    """
    from emtk import implot
    from emtk.im_core import Context

    frames: dict = {}
    original, show_menu = Context.draw_overlays, implot._show_menu_window
    #: A plot's right-click menu is a window, not an overlay: every plot that drew one.
    frames["__implot__"] = plot_menus = {}

    def draw_overlays(ctx):
        frames[id(ctx.storage)] = (ctx.storage, ctx.p)
        return original(ctx)

    def show_menu_window(plot, subplot):
        show_menu(plot, subplot)
        plot_menus[id(plot)] = (plot, im_painter())

    def im_painter():
        from emtk import im

        return im.get_current_context().p

    with (
        patch.object(Context, "draw_overlays", draw_overlays),
        patch.object(implot, "_show_menu_window", show_menu_window),
    ):
        yield frames


def _frame_storages(frames):
    return [value[0] for key, value in frames.items() if key != "__implot__"]


def _right_click(driver, point):
    from emtk.events import RIGHT_BUTTON
    from emtk.testing_realistic import RealisticDriver

    if isinstance(driver, RealisticDriver):
        driver.click(point, button=RIGHT_BUTTON)
        return
    driver.hover(point)
    driver.surface.on_pointer_press(*point, RIGHT_BUTTON, 0)
    driver.frame()
    driver.surface.on_pointer_release(*point, RIGHT_BUTTON, 0)
    driver.frame()


def _open_popups(frames):
    """``(panel, painter)`` of every popup up: overlay popups and ``begin_popup`` context menus."""
    from emtk.overlays import open_panels

    found = []
    for plot, painter in frames["__implot__"].values():
        if plot.context_menu is not None:
            found.append((plot, painter))
    for key, value in frames.items():
        if key == "__implot__":
            continue
        storage, painter = value
        found += [(panel, painter) for panel in open_panels(storage)]
        for key, value in storage.items():
            if (
                isinstance(key, tuple)
                and len(key) == 2
                and key[0] == "__state__"
                and isinstance(key[1], tuple)
                and key[1][:1] == ("context_popup",)
                and isinstance(value, dict)
                and value.get("open")
                and value.get("popup") is not None
            ):
                found.append((value["popup"], painter))
    return found


def _safe_row(panel, painter):
    """Host-space centre of the first enabled, side-effect-safe row of *panel*, else ``None``."""
    from emtk.widgets.menus import MenuItem

    if getattr(panel, "context_menu", None) is not None:
        return None  # a plot's menu: its rows toggle the plot's own settings; Escape instead

    for index, entry in enumerate(getattr(panel, "entries", ())):
        if not isinstance(entry, MenuItem) or not entry.enabled:
            continue
        if skip_reason(str(entry.label)):
            continue
        rect = panel.row_rect(index) if callable(getattr(panel, "row_rect", None)) else None
        if rect is None:
            continue
        x, y, w, h = painter_rectangle(painter, rect)
        return entry.label, (x + w / 2.0, y + h / 2.0)
    return None


def _reference_control(recorder, avoid, size=None):
    """A drawn control whose click proves the input is free and changes nothing for good.

    A selected tab (a click on it is a no-op), else a fold header or checkbox (clicked twice).
    With *size* (the layout box) only a control that is on screen qualifies -- one scrolled out of
    its region is drawn at coordinates that belong to something else -- and the returned row's
    ``rect`` is its visible part, the place a hand would click.
    """
    kinds = ("begin_tab_item", "autoform_fold", "collapsing_header", "checkbox")
    rows = [
        row
        for row in recorder.rows
        if row.get("kind") in kinds
        and row.get("enabled", True)
        and row.get("rect")
        and not skip_reason(str(row.get("id", "")) + " " + str(row.get("label", "")))
    ]
    if size is not None:
        shown = [(row, visible_rectangle(row, size)) for row in rows]
        rows = [dict(row, rect=visible) for row, visible in shown if visible is not None]
    for kind in kinds:
        for row in rows:
            x, y, w, h = row["rect"]
            if row["kind"] != kind or w < 6 or h < 6:
                continue
            if (
                avoid
                and avoid[0] <= x + w / 2 <= avoid[0] + avoid[2]
                and avoid[1] <= y + h / 2 <= avoid[1] + avoid[3]
            ):
                continue
            return row
    return None


def exercise_context_menus(driver, recorder, result):
    """Right-click every plot, table and canvas; close each menu by every path; click elsewhere.

    The real-use invariant (okf/workflows/testing.md, "Simple user sequences"): after a popup
    closes -- a pick, Escape, a click outside, a second right-click, the wheel -- nothing holds
    the input and the next click lands on its target. A context menu whose frame kept holding
    the input after it closed took every later click in the window.
    """
    from emtk.testing_realistic import held_overlays

    report = result.setdefault("context_menus", [])
    with recorded_frames() as frames, recorded_plots() as plots:
        recorder.rows.clear()
        plots.clear()
        driver.frame()
        targets = [("plot", p["area"]) for p in plots if p.get("area") and not p["opted_out"]]
        targets += [("table", rect) for rect, _header in list(recorder.tables)]
        size = _layout_size(driver)
        seen, picked = set(), []
        for kind, rect in targets:
            if rect is None or visible_rectangle(
                {"rect": rect, "clip_rect": (0, 0, *size)}, size
            ) != tuple(rect):
                continue
            if rect[2] < 24 or rect[3] < 24:
                continue
            key = tuple(round(v) for v in rect)
            if key not in seen:
                seen.add(key)
                picked.append((kind, rect))
        for kind, rect in picked[:CONTEXT_MENU_TARGETS]:
            x, y, w, h = rect
            centre = (x + w * 0.5, y + h * 0.55)
            entry = {"target": f"{kind}@{tuple(round(v) for v in rect)}", "paths": {}}
            report.append(entry)
            for path in CONTEXT_MENU_CLOSE_PATHS:
                checkpoint(result)
                _right_click(driver, centre)
                driver.frame()
                popups = _open_popups(frames)
                if not popups:
                    entry["menu"] = False
                    # A right-click with no menu must hold nothing either.
                    held = held_overlays(*_frame_storages(frames))
                    if held:
                        result["errors"].append(
                            f"context menu: {entry['target']} right-click "
                            f"opened nothing but holds the input: {held}"
                        )
                    break
                entry["menu"] = True
                panel, painter = popups[-1]
                if getattr(panel, "context_menu", None) is not None:  # an implot plot's menu
                    (mx, my), (mw, mh) = panel.context_menu["pos"], panel.context_menu["size"]
                    area = painter_rectangle(painter, (mx, my, mw, mh))
                    entry["kind"] = "plot menu"
                else:
                    area = panel.panel_rect and painter_rectangle(painter, panel.panel_rect)
                if (
                    area is not None
                    and not entry.get("outside")
                    and (
                        area[0] < -0.5
                        or area[1] < -0.5
                        or area[0] + area[2] > size[0] + 0.5
                        or area[1] + area[3] > size[1] + 0.5
                    )
                ):
                    entry["outside"] = True
                    result["errors"].append(
                        f"context menu: {entry['target']} menu {area} runs out of the window {size}"
                    )
                outside = (
                    min(size[0] - 4.0, (area[0] + area[2] + 12.0) if area else 4.0),
                    min(size[1] - 4.0, 4.0 + (area[1] if area else 0.0)),
                )
                if area and area[0] + area[2] + 12.0 > size[0] - 4.0:
                    outside = (max(4.0, area[0] - 12.0), outside[1])
                outcome = entry["paths"][path] = {}
                if path == "item":
                    row = _safe_row(panel, painter)
                    if row is None:
                        driver.escape()
                        outcome["how"] = "no safe row: Escape"
                    else:
                        driver.click(row[1])
                        outcome["how"] = f"picked {row[0]!r}"
                elif path == "escape":
                    driver.escape()
                elif path == "hover_rows":
                    # The hand crosses every row, a submenu's and a disabled one's too (a submenu row
                    # that raised when highlighted wedged its menu open), then Escape.
                    for index in range(len(getattr(panel, "entries", ()) or ())):
                        rect = (
                            panel.row_rect(index)
                            if callable(getattr(panel, "row_rect", None))
                            else None
                        )
                        if rect is not None:
                            rx, ry, rw, rh = painter_rectangle(painter, rect)
                            driver.hover((rx + rw / 2.0, ry + rh / 2.0))
                            driver.frame()
                    driver.escape()
                elif path == "click_outside":
                    driver.click(outside)
                elif path == "right_click_again":
                    _right_click(driver, centre)
                    driver.frame()
                    # The second right-click opens a fresh menu (or none); close it the plain way.
                    if _open_popups(frames):
                        driver.escape()
                elif path == "wheel":
                    driver.wheel(-1, at=centre)
                    driver.frame()
                    if _open_popups(frames):
                        driver.escape()
                driver.frame(2)
                tour = tour_for(CURRENT_APP)
                if tour is not None and getattr(tour, "active", False):
                    tour.stop()
                if dialog_open(CURRENT_APP):
                    driver.escape()
                    driver.frame()
                still = _open_popups(frames)
                held = held_overlays(*_frame_storages(frames))
                if still or held:
                    result["errors"].append(
                        f"context menu: {entry['target']} closed by {path} "
                        f"but still holds the input: {held}"
                    )
                    outcome["released"] = False
                    driver.escape()
                    driver.frame(2)
                    continue
                recorder.rows.clear()
                driver.frame()
                reference = _reference_control(recorder, area, _layout_size(driver))
                outcome["released"] = True
                if reference is None:
                    outcome["landed"] = "no reference control to click"
                    continue
                recorder.pressed_ids.clear()
                recorder.contact_ids.clear()
                rx, ry, rw, rh = reference["rect"]
                driver.click((rx + rw / 2.0, ry + rh / 2.0))
                landed = reference["engine_id"] in (recorder.pressed_ids | recorder.contact_ids)
                if reference["kind"] != "begin_tab_item":
                    driver.click((rx + rw / 2.0, ry + rh / 2.0))  # put the fold / box back
                if not landed:
                    result["errors"].append(
                        f"context menu: after closing {entry['target']}'s menu by {path}, the "
                        f"click on {reference['kind']} {reference.get('label') or reference['id']!r} "
                        f"did not land"
                    )
                outcome["landed"] = landed


def _layout_size(driver):
    """The box the app lays itself out in: the window size divided by the interface zoom."""
    surface = getattr(driver, "surface", None)
    box = surface._box() if surface is not None and hasattr(surface, "_box") else None
    return (box[2], box[3]) if box is not None else tuple(driver.size)


def reveal_control(driver, recorder, visit_id):
    """Scroll a real scrolling region to a target, or fail its coverage explicitly."""
    for attempt in range(80):
        recorder.rows.clear()
        driver.frame()
        latest = {row["visit_id"]: row for row in recorder.rows}
        row = latest.get(visit_id)
        if row is None:
            return None
        visible = visible_rectangle(row, _layout_size(driver))
        if visible is not None:
            return row, visible
        assert row.get("scrollable"), (
            f"coverage: offscreen control {row['id']!r} has no scroll/reveal route "
            f"({visit_id!r} rect={row.get('rect')} clip={row.get('clip_rect')})"
        )
        clip = row["clip_rect"]
        area = visible_rectangle({"rect": clip, "clip_rect": clip}, _layout_size(driver))
        assert area is not None, f"coverage: scrolling region for {row['id']!r} is not visible"
        direction = -1 if row["rect"][1] + row["rect"][3] / 2 > area[1] + area[3] / 2 else 1
        # A notch moves 40 px: take bigger steps toward a control far down a long document.
        distance = abs(row["rect"][1] + row["rect"][3] / 2 - (area[1] + area[3] / 2))
        notches = int(min(20, max(1, (distance - area[3] / 2) // 80)))
        # A tour card or a popup can sit over the middle of the region and take the wheel, so the
        # pointer also tries the region's left and right margins, as a user moving the mouse would.
        fx = (0.5, 0.02, 0.98)[attempt % 3]
        driver.wheel(direction * notches, at=(area[0] + area[2] * fx, area[1] + area[3] / 2))
    raise AssertionError(f"coverage: could not reveal {row['id']!r} after {attempt + 1} scrolls")


#: What a full walk over the navigation controls drew, valid until the next control is pressed.
_NAV_REACH = {"epoch": None, "reach": {}}


def reach_by_navigation(driver, recorder, visit_id, controls, epoch=None):
    """Press the navigation controls (rail entries, tabs) until a control that left the screen is drawn again.

    A hub's Back/Next/>> move to another page, so the controls of the page the sweep left are no
    longer drawn; a user gets back to them through the rail or the tabs. Returns what
    :func:`reveal_control` returns, or ``None`` when no navigation control brings the target back.

    A walk that finds nothing has drawn every page once, so it records which navigation control shows
    which control (``epoch`` names the state it saw: the number of controls pressed so far). The
    controls that are also gone are then answered from that record, instead of pressing every rail
    entry again for each of them -- hundreds of missing controls times a dozen entries is minutes of
    frames on a tool with a long plot, and the walk's answer cannot change until a control is pressed.
    """

    def navigation():
        recorder.rows.clear()
        driver.frame()
        return {
            row["visit_id"]: row
            for row in recorder.rows
            if row["kind"] in ("selectable", "begin_tab_item")
            and row.get("enabled", True)
            and visible_rectangle(row, _layout_size(driver)) is not None
            and not skip_reason(row["id"] + " " + row["label"])
        }

    def press(nav_id):
        row = navigation().get(nav_id)
        if row is None:
            return None
        driver.click(visible_rectangle(row, _layout_size(driver)))
        driver.frame(2)
        return reveal_control(driver, recorder, visit_id)

    if epoch is not None and _NAV_REACH["epoch"] == epoch:
        nav_id = _NAV_REACH["reach"].get(visit_id)
        return press(nav_id) if nav_id is not None else None
    drawn_by = {}
    for nav_id in list(navigation()):
        revealed = press(nav_id)
        if revealed is not None:
            return revealed
        for row in {row["visit_id"]: row for row in recorder.rows}.values():
            drawn_by.setdefault(row["visit_id"], nav_id)
    if epoch is not None:
        _NAV_REACH.update(epoch=epoch, reach=drawn_by)
    return None


def resolved_tour_control(rows, target, rect):
    """Resolve the authoritative global target geometry before consulting duplicate labels."""
    unique = list({row["visit_id"]: row for row in rows}.values())
    exact = [
        row
        for row in unique
        if row.get("rect") is not None and all(abs(a - b) < 0.5 for a, b in zip(row["rect"], rect))
    ]
    if exact:
        matches = exact
    else:
        named = [row for row in unique if row["id"].split("##")[-1] == target]
        px, py = rect[0] + rect[2] / 2, rect[1] + rect[3] / 2
        matches = [
            row
            for row in (named or unique)
            if row.get("rect") is not None
            and row["rect"][0] <= px <= row["rect"][0] + row["rect"][2]
            and row["rect"][1] <= py <= row["rect"][1] + row["rect"][3]
        ]
    assert len(matches) <= 1, f"coverage: guide target {target!r} is ambiguous across contexts"
    return matches[0] if matches else None


def dock_managers(root, depth=3):
    """Find the DockManagers reachable from an app (they are usually one or two attributes down)."""
    found, seen = [], set()

    def scan(obj, level):
        """Walk instance attributes breadth-limited, collecting objects that own tab strips."""
        if obj is None or id(obj) in seen or level > depth:
            return
        seen.add(id(obj))
        if callable(getattr(obj, "tab_rect", None)) and isinstance(
            getattr(obj, "tabs", None), dict
        ):
            found.append(obj)
            return
        for value in list(getattr(obj, "__dict__", {}).values()):
            if not isinstance(value, (str, bytes, int, float, bool)):
                scan(value, level + 1)

    scan(root, 0)
    return found


def drawn_target_rect(driver, tour, recorder, target, result):
    """Find the awaited target's rectangle, visiting tabs the way a user would to reach it.

    A guide step may point at a control on a tab other than the one the click sweep
    ended on. The tour does not switch tabs for the user, so the harness clicks each
    visible tab header in turn (real clicks) until the target is drawn.

    Returns
    -------
    tuple or None
        The target rectangle, or None when no tab shows it.
    """

    def lookup():
        """Resolve the rectangle from the driver, then the tour's own registry."""
        try:
            return driver.rect(target)
        except LookupError:
            return tour.get_target_rect(target) if callable(tour.get_target_rect) else None

    rect = lookup()
    if rect is not None:
        return rect
    recorder.rows.clear()
    driver.frame()
    tabs = [
        (row["id"], visible_rectangle(row, getattr(driver, "size", SIZE)))
        for row in recorder.rows
        if row["kind"] == "begin_tab_item" and row.get("rect")
    ]
    # Dock regions draw their own tab strip; their DockManager reports each tab's rectangle.
    for owner in dock_managers(CURRENT_APP):
        for keys in owner.tabs.values():
            for key in keys:
                if owner.tab_rect(key) is not None:
                    tabs.append((f"dock:{key}", owner.tab_rect(key)))
    for name, visible in tabs:
        if visible is None:
            continue
        driver.click(visible)
        driver.frame(3)
        rect = lookup()
        if rect is not None:
            result.setdefault("tour_tabs_visited", []).append(name)
            return rect
    return None


def operate_awaited_tour_step(driver, tour, result, recorder, spec=None):
    """Operate the first real awaited example and preserve valid tour completion."""
    before = tour.step_idx
    result.setdefault("tour_indices", [before])
    if tour.steps[before].get("await"):
        assert tour.wait_for_controls, (
            "coverage: awaited tour is not wired to real control notifications"
        )
        target = tour._target_key(tour.steps[before].get("target"))
        result["tour_await_target"] = target
        # The guards (_guards) already neutralise files, browsers, network, processes
        # and modals, so a tour may await a button whose *name* sounds risky; only a
        # control the spec itself tags as hardware/dangerous stays off-limits.
        declared = {str(t).lower() for t in control_tags(spec, target)}
        assert not declared & {"hardware", "dangerous"}, (
            f"tour awaits unsafe control {target!r}: declared {sorted(declared)}"
        )
        rect = drawn_target_rect(driver, tour, recorder, target, result)
        assert rect is not None, f"awaited guide target {target!r} is not drawn"
        chosen = resolved_tour_control(recorder.rows, target, rect)
        matches = [chosen] if chosen is not None else []
        if matches:
            result["tour_control_id"] = chosen["visit_id"]
            revealed = reveal_control(driver, recorder, chosen["visit_id"])
            assert revealed is not None, f"coverage: awaited target {target!r} disappeared"
            row, rect = revealed
            matches = [row]
        else:
            rect = visible_rectangle({"rect": rect}, getattr(driver, "size", SIZE))
            assert rect is not None, f"coverage: awaited target {target!r} is offscreen"
        value = recorder.input_values.get(matches[-1]["visit_id"]) if matches else None
        driver.click(rect)
        if matches and matches[-1]["kind"] == "combo":
            from emtk import keys

            driver.press(keys.KEY_DOWN)
            driver.press(keys.KEY_RETURN)
        elif matches and matches[-1]["kind"] == "input_text" and value is not None:
            from emtk import keys
            from emtk.events import CONTROL_MODIFIER

            assert not re.search(r"(url|token|credential|secret)", target, re.I), (
                f"tour requires unsafe text edit {target!r}"
            )
            driver.press(ord("A"), CONTROL_MODIFIER)
            # The control's resolved name may say more than the tour key (``lineEdit`` -> ``folder``).
            named = f"{target} {matches[-1].get('id', '')}"
            folder_field = re.search(r"(folder|directory|dir\b)", named, re.I)
            demo = demo_choice(result.get("demo_dir"), "folder" if folder_field else "open", ())
            if re.search(r"(file|path|folder|directory)", named, re.I) and demo:
                # A path field takes the plugin's own demo file, never a user file.
                result.setdefault("demo_fed", []).append(demo[0])
                driver.type(demo[0])
            else:
                if re.search(r"(file|path|folder|directory)", named, re.I):
                    # No demo: a path that does not exist, inside the scratch workspace.
                    driver.type(
                        str(Path(tempfile.gettempdir()) / "chisurf-e2e-missing" / "input.dat")
                    )
                else:
                    # Whitespace changes the real field; numeric parsing preserves its value.
                    driver.type(str(value) + " ")
            driver.press(keys.KEY_RETURN)
        driver.frame(2)
        settle_with_cancel(driver, recorder, result)
        if tour.awaiting:
            # The guide may point at a read-only field whose companion button actuates
            # it (``trajectory`` / ``trajectory_browse``): press that real control.
            for suffix in ("_browse", "_button", "_open", "_add"):
                try:
                    companion = driver.rect(target + suffix)
                except LookupError:
                    continue
                driver.click(companion)
                driver.frame(2)
                settle_with_cancel(driver, recorder, result)
                result.setdefault("tour_companions", []).append(target + suffix)
                if not tour.awaiting:
                    break
        if tour.awaiting and matches == []:
            # The guide highlights a region (a list, a group); the centre may fall in a gap
            # between its rows, so click along it as a user would until something takes it.
            x0, y0, w0, h0 = rect
            for fy in (0.5, 0.25, 0.75, 0.1, 0.9, 0.35, 0.65, 0.15, 0.85, 0.05, 0.95):
                for fx in (0.5, 0.2, 0.8):
                    if not tour.awaiting:
                        break
                    driver.click((x0 + w0 * fx - 1, y0 + h0 * fy - 1, 2, 2))
                    driver.frame(2)
                    result["tour_region_probes"] = result.get("tour_region_probes", 0) + 1
        if tour.awaiting and matches == [] and callable(getattr(driver, "press", None)):
            # An untracked drop-down (``choose …``): open it and step through its entries.
            from emtk import keys

            for _ in range(6):
                if not tour.awaiting:
                    break
                x0, y0, w0, h0 = rect
                driver.click((x0 + w0 / 2 - 1, y0 + h0 / 2 - 1, 2, 2))
                driver.press(keys.KEY_DOWN)
                driver.press(keys.KEY_RETURN)
                driver.frame(2)
                result["tour_choice_steps"] = result.get("tour_choice_steps", 0) + 1
        settle_with_cancel(driver, recorder, result)
        assert not tour.awaiting, f"real interaction with {target!r} did not satisfy tour await"
    tour.next()
    driver.frame(2)
    if tour.active:
        assert tour.step_idx == before + 1, (
            f"guided tour did not advance: {before} -> {tour.step_idx}"
        )
        result["tour_indices"].append(tour.step_idx)
    else:
        assert before == len(tour.steps) - 1, "guided tour ended before its final real example"
        result["tour_completed"] = True
    result["tour_await_exercised"] = True
    result["tour_steps"] = (
        len(result["tour_indices"]) - 1 + int(result.get("tour_completed", False))
    )


def advance_tour(driver, tour, result, recorder, spec=None):
    """Traverse bounded introductions, then exercise the first real awaited target."""
    result["tour_indices"] = [tour.step_idx]
    for _ in range(12):
        if tour.steps[tour.step_idx].get("await"):
            return operate_awaited_tour_step(driver, tour, result, recorder, spec)
        before = tour.step_idx
        tour.next()
        driver.frame(2)
        assert tour.active, "coverage: tour ended without a real awaited example"
        assert tour.step_idx == before + 1, "coverage: tour introduction did not advance"
        result["tour_indices"].append(tour.step_idx)
    raise AssertionError("coverage: no real awaited example within 12 tour steps")


def settle_with_cancel(driver, recorder, result):
    """Bound a local job and test its real Cancel/Stop button when needed."""
    try:
        return driver.settle(timeout=30)
    except TimeoutError as exc:
        recorder.rows.clear()
        driver.frame()
        stops = [
            row
            for row in recorder.rows
            if row["kind"] in ("button", "small_button", "menu_item")
            and row.get("enabled", True)
            and re.search(r"(^|[^a-z])(cancel|stop)([^a-z]|$)", row["id"], re.I)
        ]
        if not stops:
            raise TimeoutError("job exceeded 30s and has no enabled Cancel/Stop control") from exc
        stop = stops[0]
        result.setdefault("job_cancellations", []).append(
            {"job_control": result.get("current_control"), "cancel_control": stop["id"]}
        )
        result["phase"] = "cancel"
        checkpoint(result)
        driver.click(stop["rect"])
        try:
            return driver.settle(timeout=5)
        except TimeoutError as pending:
            raise TimeoutError(f"{stop['id']!r} did not restore an idle app within 5s") from pending


STOP_CONTROL = re.compile(r"(^|[^a-z])(cancel|stop)([^a-z]|$)", re.I)


def settle_held_jobs(driver, recorder, result, exercised):
    """Press the real Stop of each job a click started, while the job is held open.

    A Stop/Cancel is enabled only while its job runs, so the sweep arms
    :mod:`chisurf.emtk.job_gate`: a job started by the click stays open until it is released or
    cancelled. A drawn, enabled Stop that was not yet pressed is pressed now and must end a held job
    (the gate counts the jobs its own cancel flag ended). The jobs that remain are released and
    awaited, so the next control meets an idle app. Returns the visit ids of the Stop controls pressed.
    """
    from chisurf.emtk import job_gate

    pressed = []
    driver.frame(2)
    if job_gate.active():
        recorder.rows.clear()
        driver.frame()
        stops = [
            row
            for row in recorder.rows
            if row["kind"] in ("button", "small_button", "menu_item")
            and row.get("enabled", True)
            and row["visit_id"] not in exercised
            and STOP_CONTROL.search(row["id"])
            and visible_rectangle(row, _layout_size(driver)) is not None
        ]
        for stop in stops:
            before = job_gate.stopped()
            result["phase"] = "stop"
            checkpoint(result)
            driver.click(visible_rectangle(stop, _layout_size(driver)))
            end = time.monotonic() + 5
            while job_gate.stopped() == before and time.monotonic() < end:
                driver.frame()
                time.sleep(0.01)
            assert job_gate.stopped() > before, (
                f"coverage: pressing {stop['id']!r} did not stop the job held open by "
                f"{result.get('current_control')!r}"
            )
            exercised.add(stop["visit_id"])
            pressed.append(stop["visit_id"])
            result.setdefault("held_job_stops", []).append(
                {"job_control": result.get("current_control"), "stop_control": stop["id"]}
            )
            break
    job_gate.release()
    assert job_gate.wait_idle(60), "a released job never finished"
    driver.frame(3)
    job_gate.arm()
    return pressed


#: Documentation browsers: every documentation page is a node and every page re-creates its own
#: per-block buttons, so the inventory grows with the size of the docs, not with the plugin. The sweep
#: presses this many controls (recorded as ``inventory_bounded``) instead of walking the whole tree.
#: 24, not the original 150: the markdown reader's per-frame text metrics make a control cost
#: ~4.7 s (gate 848fd9f6c: 10-16 controls in 120 s, 38 in 180 s), and the worker must fit
#: CHISURF_E2E_TIMEOUT -- 24 x 4.7 s ≈ 113 s. The toolbar, the TOC, several pages' distinct
#: blocks and the repeats sampler all still run; only the walk depth is bounded sooner.
INVENTORY_BUDGET = {"help": 24}

#: A sweep whose inventory is still growing past this many distinct controls is not converging (a control that
#: keeps making new controls). A hub of seventeen tools legitimately holds ~650 (imaging_tools: 380 pressed, 270
#: skipped with a reason), and the sweep reaches the controls behind the rail now, so the ceiling is 1024.
INVENTORY_CEILING = 1024


def _unfinished_sources(lang):
    """Sources the ``chisurf_<lang>.ts`` catalogue extracts but has not translated yet."""
    import xml.etree.ElementTree as ElementTree

    path = REPO / "chisurf" / "gui" / "i18n" / f"chisurf_{lang}.ts"
    out = set()
    try:
        root = ElementTree.parse(path).getroot()
    except (OSError, ElementTree.ParseError):
        return out
    for message in root.iter("message"):
        source = (message.findtext("source") or "").strip()
        translation = message.find("translation")
        if source and (
            translation is None
            or translation.get("type") == "unfinished"
            or not (translation.text or "").strip()
        ):
            out.add(source)
    return out


#: Controls whose drawn text is the value held in them, never a caption.
FIELD_KINDS = frozenset(
    {"input_text", "input_text_multiline", "input_float", "input_int", "input_double"}
)
#: Height of a data table's header row: text below it in the table is a cell.
TABLE_HEADER_H = 16.0
#: Control kinds whose label is a caption (clipping one is a layout defect).
CAPTION_KINDS = frozenset(
    {
        "button",
        "small_button",
        "checkbox",
        "radio_button",
        "menu_item",
        "collapsing_header",
        "begin_tab_item",
        "autoform_fold",
    }
)
#: Words a tool draws as *data*, never as a caption: the Image Browser's default detector is named "Image"
#: (a key of its detector configuration) and labels the mosaic tile.
DATA_WORDS = {"tttr_image_browser": frozenset({"Image"})}
#: Tools that display documents: their content is English by design (docs/ is not
#: translated), so drawn English there is not untranslated chrome.
CONTENT_VIEWERS = frozenset({"help"})


class RealUseFindings:
    """What a matrix variant checks on every settled frame of the sweep.

    * **clipped captions** -- a control whose own caption the active clip cuts (measured with
      the painter's real metrics, :func:`emtk.testing_realistic.clipped_texts`); under a
      language variant also any clipped *translated* string, which is what a longer German or
      French text does to a layout sized for English;
    * **untranslated text** (language variants) -- a drawn string the catalogue translates to
      something else, i.e. English source text that reached the screen without passing
      through ``tr``.

    Inactive for the base sweep, so its verdicts are unchanged.
    """

    def __init__(self, driver, recorder_rows, plugin_id="", recorder_tables=lambda: ()):
        self.tables = recorder_tables
        self.plugin_id = plugin_id
        self.driver = driver
        self.rows = recorder_rows
        self.active = bool(VARIANT)
        self.lang = VARIANT.get("lang")
        self.clipped: dict = {}
        self.untranslated: dict = {}
        self.collisions: dict = {}
        self._tr_cache: dict = {}
        self._translated: set = set()
        if self.lang:
            from emtk import i18n as toolkit

            from chisurf.core.support.i18n import register_catalogues

            register_catalogues()
            toolkit.set_language(self.lang)
            self._toolkit = toolkit
            self.missing: dict = {}
            self._unfinished = _unfinished_sources(self.lang)

    def _translation(self, text):
        """The catalogue's translation of *text* in any domain, or None."""
        if text in self._tr_cache:
            return self._tr_cache[text]
        found = None
        for domain in self._toolkit.domains():
            try:
                out = self._toolkit.tr(text, domain=domain)
            except Exception:  # noqa: BLE001 - a malformed catalogue is its own test's finding
                continue
            if out and out != text:
                found = out
                break
        self._tr_cache[text] = found
        if found:
            self._translated.add(found.strip())
        return found

    def scan(self):
        """Inspect the last drawn frame."""
        if not self.active:
            return
        painter = self.driver.painter
        if painter is None or not hasattr(painter, "text_metadata"):
            return
        from emtk.testing_realistic import clipped_texts

        # A caption is the label of a control a user reads to act on; list rows (selectable,
        # tree_node, list_box) and fields hold content -- a long file or page name in a narrow
        # list is clipped by design, so it is not a squeezed caption.
        captions = {
            str(row.get("label") or "").split("##")[0].strip()
            for row in self.rows()
            if row.get("kind") in CAPTION_KINDS
        }
        captions.discard("")
        # What a user typed or a model holds in an editable field is data, not a caption to translate:
        # a mdtraj selection ("name CA and resSeq 1 to 256") is drawn word by word, and its "to" is
        # not the French "à".
        fields = [
            row["rect"] for row in self.rows() if row.get("kind") in FIELD_KINDS and row.get("rect")
        ]

        tables = list(self.tables())

        def in_field(entry):
            """Whether the drawn text is a field's value or a cell of a data table (content, not a caption)."""
            return any(
                fx <= entry[0] <= fx + fw and fy - 1 <= entry[1] <= fy + fh
                for fx, fy, fw, fh in fields
            ) or any(
                tx <= entry[0] <= tx + tw and ty + header <= entry[1] <= ty + th
                for (tx, ty, tw, th), header in tables
            )

        data_words = DATA_WORDS.get(self.plugin_id, frozenset())
        texts = {
            str(entry[5]).strip()
            for entry in painter.texts
            if not in_field(entry) and str(entry[5]).strip() not in data_words
        }
        if self.lang:
            # Two controls whose captions translate to one word ("Back" and "Prev" are both
            # "Zurück") collide when the caption is the id: the second press goes to the first.
            seen = {}
            for row in self.rows():
                engine = row.get("engine_id")
                if engine and row.get("kind") in ("button", "small_button", "selectable"):
                    seen[engine] = seen.get(engine, 0) + 1
            for engine, count in seen.items():
                if count > 1:
                    self.collisions.setdefault(engine.split(":", 1)[-1], count)
        if self.lang and self.plugin_id not in CONTENT_VIEWERS:
            for text in texts:
                if len(text) > 1 and any(c.isalpha() for c in text):
                    translation = self._translation(text)
                    if translation and text not in self._translated:
                        self.untranslated.setdefault(text, translation)
                    elif not translation and text in self._unfinished:
                        self.missing[text] = self.missing.get(text, 0) + 1
        for hit in clipped_texts(painter):
            text = hit["text"].strip()
            if text in captions or (self.lang and text in self._translated):
                self.clipped.setdefault(
                    text,
                    {
                        "hidden_px": hit["hidden_px"],
                        "visible": hit["visible"],
                        "size": list(self.driver.size),
                    },
                )

    def report(self, result):
        """Record the findings; each kind fails the variant."""
        if not self.active:
            return
        result["clipped_labels"] = self.clipped
        if self.lang:
            result["untranslated_visible"] = self.untranslated
            # Catalogue backlog, not a code defect: the source is extracted but its
            # translation is unfinished. Recorded for the i18n job, never failing.
            result["missing_translation"] = sorted(self.missing)
        if self.clipped:
            result["errors"].append(
                f"{len(self.clipped)} clipped label(s): " + ", ".join(sorted(self.clipped)[:12])
            )
        if self.collisions:
            result["id_collisions"] = self.collisions
            result["errors"].append(
                f"{len(self.collisions)} control id(s) drawn twice in one frame: "
                + ", ".join(sorted(self.collisions)[:12])
            )
        if self.untranslated:
            result["errors"].append(
                f"{len(self.untranslated)} untranslated visible text(s): "
                + ", ".join(sorted(self.untranslated)[:12])
            )


#: Plots and scroll regions per tool the settle phase exercises.
SETTLE_TARGETS = 6
#: Idle frames, pointer held still, after which nothing may still be moving.
SETTLE_FRAMES = 30


@contextmanager
def recorded_views():
    """Every view a wheel can move, drawn while active, with a reader for its current state.

    Yields a dict ``{key: {"kind", "area", "read"}}`` filled as frames draw: implot plots (axis
    ranges), chiplot panels (view range) and emtk scroll regions that overflow (scroll offset).
    ``read()`` returns the view's state now; the settle phase compares it frame to frame.
    """
    from emtk import im, implot
    from emtk.im_core import Context

    from chisurf.chiplot.backends.emtk_backend import EmtkCanvas

    views: dict = {}
    original_end, original_draw = implot.end_plot, EmtkCanvas.draw
    original_child = Context.begin_child

    def end_plot():
        plot = implot.gp.current_plot
        original_end()
        if plot is None or plot.flags & implot.FLAGS_NO_INPUTS:
            return
        x0, y0, x1, y1 = plot.plot_rect
        area = painter_rectangle(im.get_current_context().p, (x0, y0, x1 - x0, y1 - y0))
        views[("implot", plot.id)] = {
            "kind": "plot",
            "area": area,
            "read": lambda plot=plot: tuple(
                (round(a.range_min, 9), round(a.range_max, 9)) for a in plot.axes if a.enabled
            ),
        }

    def draw(canvas, painter, x, y, w, h):
        original_draw(canvas, painter, x, y, w, h)
        if getattr(canvas, "_interactive", True):
            views[("chiplot", id(canvas))] = {
                "kind": "plot",
                "area": painter_rectangle(painter, (x, y, w, h)),
                "read": lambda canvas=canvas: repr(canvas.get_range()),
            }

    def begin_child(ctx, box, clip=True, child_id=None, scrollable=True):
        # The child's key and resolved box, as Context.begin_child derives them.
        x, y, w, h = box
        if w <= 0.0 or h <= 0.0:
            avail_w, avail_h = ctx.layout.avail()
            w = avail_w + w if w <= 0.0 else w
            h = avail_h + h if h <= 0.0 else h
        rect = (x, y, max(w, 0.0), max(h, 0.0))
        cid = child_id if child_id is not None else (round(rect[0], 1), round(rect[1], 1))
        key = ("__child__", *ctx._ids, cid)
        layout = original_child(ctx, box, clip, child_id, scrollable)
        state = ctx.storage.get(key)
        if scrollable and state and float(state.get("content_height", 0.0)) > rect[3] + 1.0:
            views[("scroll", id(ctx.storage), key)] = {
                "kind": "scroll",
                "area": painter_rectangle(ctx.p, rect),
                "read": lambda state=state: round(float(state.get("scroll_y", 0.0)), 3),
            }
        return layout

    with ExitStack() as stack:
        stack.enter_context(patch.object(implot, "end_plot", end_plot))
        stack.enter_context(patch.object(EmtkCanvas, "draw", draw))
        stack.enter_context(patch.object(Context, "begin_child", begin_child))
        yield views


def exercise_settle(driver, result):
    """One wheel notch over each plot and scroll region, then the hand rests: nothing may move.

    The real-use check for one-shot input (okf/workflows/testing.md, "Settle after every
    input"): a notch over a plot once zoomed on *every* frame until the pointer left it, and
    every test that looked only at the frame after the notch passed. Each target gets one
    notch at its centre and :data:`SETTLE_FRAMES` idle frames; the state of *every* recorded
    view (not only the target) must hold still, and the tool must stop asking for frames
    unless it was already animating before the notch.
    """
    from emtk.testing_realistic import assert_settles

    size = _layout_size(driver)
    report = result.setdefault("settle", [])
    with recorded_views() as views:
        driver.frame(2)
        targets = [
            (key, view)
            for key, view in list(views.items())
            if view["area"]
            and view["area"][2] > 24
            and view["area"][3] > 24
            and visible_rectangle({"rect": view["area"], "clip_rect": (0, 0, *size)}, size)
            == tuple(view["area"])
        ]
        # Plots first: they are what the bug report was about.
        targets.sort(key=lambda kv: kv[1]["kind"] != "plot")
        for key, view in targets[:SETTLE_TARGETS]:
            x, y, w, h = view["area"]
            centre = (x + w / 2.0, y + h / 2.0)
            entry = {"target": f"{view['kind']}:{key[1:]!r}"[-90:]}
            report.append(entry)
            animating = getattr(driver.app, "animating", None)
            busy = bool(callable(animating) and animating())

            def state():
                return tuple((k, v["read"]()) for k, v in sorted(views.items(), key=repr))

            try:
                assert_settles(
                    driver,
                    lambda d: d.wheel(1, at=centre),
                    state,
                    frames=SETTLE_FRAMES,
                    allow_animation=busy,
                    label=entry["target"],
                )
                entry["settled"] = True
            except AssertionError as error:
                entry["settled"] = False
                result["errors"].append(f"settle: {error}")
            driver.hover((-1, -1))
            driver.frame()


def _native(plugin_id, result, png_path):
    """Draw a real app, visit safe controls, audit its tour and tooltips."""
    from emtk import im, keys
    from emtk.testing import Driver

    from chisurf.emtk.plugins import load_plugin
    from test.gui.emtk_port_parity import ControlRecorder, emtk_inventory

    class Recorder(ControlRecorder):
        """Associate every measured control with its real submitted rectangle."""

        def __init__(self):
            """Keep editable field text privately, never in PNG/JSON inventories."""
            super().__init__()
            self.input_values = {}
            #: ``(rectangle, header height)`` of every data table or node graph drawn since the rows were
            #: last cleared (the sweep clears them before each frame): the scan skips their cells.
            self.tables = []
            tables = self.tables

            class Rows(list):
                """The recorded rows; clearing them starts a new frame for the tables too."""

                def clear(self):
                    super().clear()
                    tables.clear()

            self.rows = Rows(self.rows)
            self.pressed_ids = set()
            self.contact_ids = set()

        def capture(self, kind):
            """Record the actual item geometry, clipping, and enabled state."""
            from emtk.im_core import ItemFlags

            ctx = im.get_current_context()
            row = self.rows[-1]
            rect = im.get_item_rect()
            identity = f"{id(ctx.storage)}:{im.get_item_id()!r}"
            row.update(
                rect=painter_rectangle(ctx.p, rect),
                visit_id=f"{kind}:{identity}",
                engine_id=identity,
                clip_rect=painter_rectangle(ctx.p, ctx.clip_rect),
                enabled=not bool(ctx.item_flags & ItemFlags.DISABLED),
                scrollable=any(len(child) > 6 and child[6] for child in ctx._child),
            )

        @contextmanager
        def installed(self):
            """Observe real item delivery and AutoForm's direct fold controls."""
            from emtk import view_form
            from emtk.im_core import Context

            behavior, item_add, fold = Context.button_behavior, Context.item_add, view_form._fold

            def observe_behavior(ctx, box, item_id, flags=0):
                """Keep the original behavior and observe its real press result."""
                response = behavior(ctx, box, item_id, flags)
                if response[2]:
                    self.pressed_ids.add(f"{id(ctx.storage)}:{item_id!r}")
                return response

            def observe_item(ctx, box, item_id=None):
                """Record only actual hovered mouse-down delivery."""
                hovered = item_add(ctx, box, item_id)
                if hovered and ctx.io.mouse_clicked[0] and not ctx._last_item_disabled:
                    self.contact_ids.add(f"{id(ctx.storage)}:{item_id!r}")
                return hovered

            def observe_fold(section, state):
                """Let the real fold render, toggle, and assign its real tooltip."""
                title = str(section.get("title", ""))
                self.control("autoform_fold", f"##fold-{title}")
                opened = fold(section, state)
                self.capture("autoform_fold")
                self.rows[-1]["expanded"] = opened
                return opened

            from emtk.widgets import data_table

            original_table = data_table.draw_table

            def observe_table(*args, **kwargs):
                """Record a data table's rectangle: its body is content, not a caption to translate."""
                result = original_table(*args, **kwargs)
                ctx = im.get_current_context()
                rect = im.get_item_rect()
                if rect is not None:
                    self.tables.append((painter_rectangle(ctx.p, rect), TABLE_HEADER_H))
                return result

            original_editor = im.text_editor

            def observe_editor(*args, **kwargs):
                """Record a text editor's rectangle: what it shows is the user's document (a style sheet's
                ``border: none;`` is not the caption "none")."""
                result = original_editor(*args, **kwargs)
                rect = im.get_item_rect()
                if rect is not None:
                    self.tables.append((painter_rectangle(im.get_current_context().p, rect), 0.0))
                return result

            from chisurf.emtk.node_editor.control import GraphControl

            original_graph = GraphControl._draw_graph

            def observe_graph(control, box):
                """Record a node graph's rectangle: its node labels are the document's names."""
                result = original_graph(control, box)
                self.tables.append((painter_rectangle(im.get_current_context().p, tuple(box)), 0.0))
                return result

            # The widget is imported by name into the modules that draw it, so every reference is swapped.
            holders = [
                module
                for module in list(sys.modules.values())
                if getattr(module, "draw_table", None) is original_table
            ]
            for module in holders:
                setattr(module, "draw_table", observe_table)
            try:
                with (
                    super().installed(),
                    patch.object(Context, "button_behavior", observe_behavior),
                    patch.object(Context, "item_add", observe_item),
                    patch.object(view_form, "_fold", observe_fold),
                    patch.object(GraphControl, "_draw_graph", observe_graph),
                    patch.object(im, "text_editor", observe_editor),
                ):
                    yield self
            finally:
                for module in holders:
                    setattr(module, "draw_table", original_table)

        def _wrap(self, kind, func):
            wrapped = super()._wrap(kind, func)

            def record(*args, **kwargs):
                """Record only the outer control, after its real widget has drawn."""
                outer = self._depth == 0
                value = wrapped(*args, **kwargs)
                if outer and self.rows:
                    self.capture(kind)
                    if kind == "input_text" and len(args) > 1:
                        self.input_values[self.rows[-1]["visit_id"]] = args[1]
                    if kind in ("collapsing_header", "tree_node"):
                        self.rows[-1]["expanded"] = bool(value)
                return value

            return record

    result["phase"] = "factory"
    checkpoint(result)
    global CURRENT_APP
    app = CURRENT_APP = load_plugin(plugin_id, persist=False)
    size = tuple(VARIANT.get("size", SIZE))
    if VARIANT.get("zoom"):
        from emtk import fonts

        fonts.update(zoom=float(VARIANT["zoom"]))
    if VARIANT.get("driver") == "realistic":
        from emtk.testing_realistic import RealisticDriver

        driver = RealisticDriver(app, size, scale=float(VARIANT.get("scale", 1.0)))
    else:
        driver = Driver(app, size)
    findings = RealUseFindings(
        driver,
        recorder_rows=lambda: recorder.rows,
        plugin_id=plugin_id,
        recorder_tables=lambda: recorder.tables,
    )
    recorder = Recorder()
    samples = []
    try:
        with recorder.installed():
            for _ in range(6):
                recorder.rows.clear()
                start = time.perf_counter()
                driver.frame()
                samples.append((time.perf_counter() - start) * 1000)
            assert driver.painter.texts, "initial plugin frame contains no text"
            result["first_frame_ms"] = samples[0]
            result["steady_frame_ms"] = statistics.median(samples[2:])
            result["frame_samples_ms"] = samples
            controls = {
                row["visit_id"]: dict(row) for row in recorder.rows if row["kind"] in CLICKABLE
            }
            findings.scan()
            result["phase"] = "auto_range"
            checkpoint(result)
            if phase_on("auto_range"):
                exercise_auto_range(driver, result)
            if phase_on("context_menu"):
                # Before any data: an empty plot's right-click must release the input too.
                result["phase"] = "context_menu"
                checkpoint(result)
                exercise_context_menus(driver, recorder, result)
            if phase_on("settle"):
                result["phase"] = "settle"
                checkpoint(result)
                exercise_settle(driver, result)
            pending = sorted(controls) if phase_on("click") else []
            # Half-way through the sweep (after the first click for a tool with few controls).
            resize_after = max(1, len(pending) // 2) if VARIANT.get("resize_to") else None
            visited = set()
            exercised_stops = set()
            from chisurf.emtk import job_gate

            job_gate.arm()
            repeats, sampled_out = {}, set()
            while pending:
                # Finish the current page before selecting a different tab.
                pending.sort(key=lambda name: (controls[name]["kind"] == "begin_tab_item", name))
                name = pending.pop(0)
                if name in visited:
                    continue
                visited.add(name)
                budget = INVENTORY_BUDGET.get(plugin_id)
                if budget and len(visited) - len(sampled_out) > budget:
                    result["inventory_bounded"] = budget
                    break
                assert len(visited) - len(sampled_out) <= INVENTORY_CEILING, (
                    f"control inventory did not stabilize within {INVENTORY_CEILING} targets"
                )
                control = controls[name]
                raw_name = control["id"]
                # A documentation browser re-creates the same per-block button (Copy, ...) on every
                # page it opens, and it opens hundreds. Past a generous budget, a button whose
                # caption was already pressed three times is a repeat of a control that has been
                # exercised: sample it instead of walking the whole documentation tree.
                if len(visited) > 128 and control["kind"] in ("button", "small_button"):
                    key = ("repeat", control["kind"], control["label"])
                    repeats[key] = repeats.get(key, 0) + 1
                    if repeats[key] > 3:
                        result["skipped"].append(
                            {
                                "control": name,
                                "reason": "repeat of an already exercised per-page control",
                            }
                        )
                        sampled_out.add(name)
                        continue
                reason = skip_reason(
                    raw_name + " " + control["label"],
                    control_tags(getattr(app, "spec", {}), raw_name),
                )
                if reason:
                    result["skipped"].append({"control": name, "reason": reason})
                    continue
                revealed = reveal_control(driver, recorder, name)
                if revealed is None:
                    revealed = reach_by_navigation(
                        driver, recorder, name, controls, epoch=len(result["clicked"])
                    )
                if revealed is None:
                    visited.remove(name)
                    result["skipped"].append(
                        {"control": name, "reason": "no longer drawn after prior control"}
                    )
                    continue
                current, click_box = revealed
                if not current["enabled"]:
                    result["skipped"].append({"control": name, "reason": "disabled in this state"})
                    continue
                result["current_control"] = raw_name
                result["current_control_id"] = name
                result["phase"] = "click"
                checkpoint(result)
                recorder.pressed_ids.clear()
                recorder.contact_ids.clear()
                driver.click(click_box)
                proof = (
                    recorder.pressed_ids
                    if control["kind"]
                    in {
                        "button",
                        "small_button",
                        "radio_button",
                        "selectable",
                        "menu_item",
                        "autoform_fold",
                    }
                    else recorder.pressed_ids | recorder.contact_ids
                )
                if current["engine_id"] not in proof:
                    # A control that a background job removes mid-click (a "pending" Cancel whose
                    # database call just failed) is gone, not unclickable; anything still drawn must have been hit.
                    recorder.rows.clear()
                    driver.frame()
                    if not any(row["visit_id"] == name for row in recorder.rows):
                        visited.remove(name)
                        result["skipped"].append(
                            {
                                "control": name,
                                "reason": "withdrawn by a background job during the click",
                            }
                        )
                        continue
                    # A floating window a previous control opened (a preview) may sit over the target.
                    # Escape closes the window under the pointer, so a user parks it there and presses Esc.
                    driver.hover(click_box)
                    driver.escape()
                    driver.frame(2)
                    result.setdefault("covering_windows_dismissed", []).append(raw_name)
                    revealed = reveal_control(driver, recorder, name)
                    if revealed is not None:
                        current, click_box = revealed
                        recorder.pressed_ids.clear()
                        recorder.contact_ids.clear()
                        driver.click(click_box)
                        proof = (
                            recorder.pressed_ids
                            if control["kind"]
                            in {
                                "button",
                                "small_button",
                                "radio_button",
                                "selectable",
                                "menu_item",
                                "autoform_fold",
                            }
                            else recorder.pressed_ids | recorder.contact_ids
                        )
                assert current["engine_id"] in proof, (
                    f"coverage: visible {raw_name!r} did not receive an actual click"
                )
                if current.get("expanded"):
                    # An already open group must stay reachable for its child controls.
                    driver.click(click_box)
                result["clicked"].append(raw_name)
                result.setdefault("clicked_ids", []).append(name)
                if resize_after is not None and len(result["clicked"]) >= resize_after:
                    # The window manager resizes mid-session; every later click must land at
                    # the new positions (the sweep re-resolves each control from the frame).
                    driver.draw(size=tuple(VARIANT["resize_to"]))
                    result["resized_at"] = {
                        "click": len(result["clicked"]),
                        "to": list(driver.size),
                    }
                    resize_after = None
                if control["kind"] == "combo":
                    result["combos"].append(raw_name)
                elif control["kind"] == "begin_tab_item":
                    result["tabs"].append(raw_name)
                if dialog_open(app):
                    result["dialogs_closed"] += 1
                driver.escape()  # dismiss a native picker/popup without choosing a file
                tour = tour_for(app)
                if tour is not None and getattr(tour, "active", False):
                    tour.stop()
                for owner in (app, getattr(app, "header_gui", None)):
                    for attr in ("help_window", "help"):
                        help_window = getattr(owner, attr, None)
                        if callable(getattr(help_window, "hide", None)):
                            help_window.hide()
                for stop_id in settle_held_jobs(driver, recorder, result, exercised_stops):
                    visited.add(stop_id)
                    result["clicked"].append(controls.get(stop_id, {}).get("id", stop_id))
                    result.setdefault("clicked_ids", []).append(stop_id)
                settle_with_cancel(driver, recorder, result)
                assert not getattr(app, "running", False), "long-running control without cancel"
                recorder.rows.clear()
                driver.frame()
                findings.scan()
                for row in recorder.rows:
                    if row["kind"] in CLICKABLE:
                        controls[row["visit_id"]] = dict(row)
                        if row["visit_id"] not in visited and row["visit_id"] not in pending:
                            pending.append(row["visit_id"])
            job_gate.disarm()
            if resize_after is not None:
                # A sweep that ended before the half-way click still resizes, so the tour and
                # the Tab presses below run at the new size.
                driver.draw(size=tuple(VARIANT["resize_to"]))
                result["resized_at"] = {"click": len(result["clicked"]), "to": list(driver.size)}
            result["controls"] = list(controls.values())
            for section in walk(getattr(app, "spec", {})) if phase_on("click") else ():
                if section.get("type") == "choice":
                    name = str(
                        section.get("attr") or section.get("target") or section.get("key") or ""
                    )
                    if name and name in driver.ids() and not skip_reason(name):
                        driver.click(name)
                        driver.escape()
                        result["combos"].append(name)
            for _ in range(20):
                driver.press(keys.KEY_TAB)
            result["tab_presses"] = 20
            result["phase"] = "tour"
            checkpoint(result)
            tour = tour_for(app) if phase_on("tour") else False
            if tour is False:
                pass
            elif tour is None:
                result["errors"].append("missing guided tour on app or its declared guide owner")
            else:
                tour.start()
                driver.frame(2)
                if not tour.active:
                    result["errors"].append("guided tour did not activate")
                else:
                    advance_tour(driver, tour, result, recorder, getattr(app, "spec", {}))
                tour.stop()
                # The awaited press may rightly open a modal (Load example over loaded data asks
                # keep/replace); answer it the plain way before the plots are judged, or every
                # input after the tour lands on the modal instead.
                for _ in range(3):
                    if not dialog_open(app):
                        break
                    driver.escape()
                    driver.frame(2)
                    result["dialogs_closed"] += 1
            result["phase"] = "auto_range_after_tour"
            checkpoint(result)
            if phase_on("auto_range"):
                exercise_auto_range(driver, result)
            if phase_on("context_menu"):
                result["phase"] = "context_menu_after_tour"
                checkpoint(result)
                exercise_context_menus(driver, recorder, result)
            if phase_on("settle"):
                result["phase"] = "settle_after_tour"
                checkpoint(result)
                exercise_settle(driver, result)
            recorder.rows.clear()
            driver.frame()
        inventory = emtk_inventory(app, _layout_size(driver))
        result["inventory"] = inventory
        findings.report(result)
        missing = sorted(
            set(inventory["controls_without_tooltip"])
            | {
                f"{row['kind']}: {row['label'] or row['id']}"
                for row in controls.values()
                if not row["tooltip"]
            }
        )
        result["controls_without_tooltip"] = missing
        if missing:
            result["errors"].append("controls without tooltip: " + ", ".join(missing))
        assert driver.painter.texts, "settled plugin frame contains no text"
    finally:
        try:
            # Hover help is useful during interaction, but hides review controls.
            driver.hover((-1, -1))
            driver.frame(2)
            driver.screenshot(png_path)
            result["frames"] = getattr(getattr(app, "io", None), "frame_count", None)
        finally:
            close = getattr(app, "close", None)
            if callable(close):
                close()


def run_one(plugin_id, mode, variant=None):
    """Create scratch state before imports, then always write a worker result."""
    global VARIANT
    VARIANT = dict(VARIANTS[variant]) if variant else {}
    directory = artifact_dir()
    directory.mkdir(parents=True, exist_ok=True)
    stem = artifact_stem(plugin_id)
    result = {
        "plugin": plugin_id,
        "mode": mode,
        "status": "running",
        "size": list(VARIANT.get("size", SIZE)),
        "variant": variant,
        "harness_sha256": HARNESS_SHA256,
        "python": sys.version,
        "machine": platform.machine(),
        "clicked": [],
        "skipped": [],
        "dialogs_closed": 0,
        "combos": [],
        "tabs": [],
        "tour_steps": 0,
        "errors": [],
        "blocked_actions": [],
    }
    with tempfile.TemporaryDirectory(prefix="chisurf-e2e-") as scratch:
        env = {
            "CHISURF_SETTINGS_DIR": str(Path(scratch) / "settings"),
            "MMFDB_SETTINGS_DIR": str(Path(scratch) / "mmfdb"),
            "MMFDB_DATABASE_PATH": str(Path(scratch) / "mmfdb.sqlite"),
            "MMFDB_OBJECT_STORE_ROOT": str(Path(scratch) / "objects"),
            "XDG_CACHE_HOME": str(Path(scratch) / "cache"),
            "LUMIS_QUEST_HOME": str(Path(scratch) / "lumis"),
        }
        if VARIANT.get("lang"):
            env["EMTK_LANG"] = VARIANT["lang"]
        with patch.dict(os.environ, env), ExitStack() as stack:
            try:
                if plugin_id == "code_editor":
                    # make_editor_app(project_root=None) uses Path.cwd() by contract.
                    workspace = Path(scratch) / "project"
                    workspace.mkdir()
                    shutil.copy2(Path(__file__), workspace / "sample.py")
                    result["workspace_fixture"] = "scratch/project/sample.py"
                    previous_directory = Path.cwd()
                    os.chdir(workspace)
                    stack.callback(os.chdir, previous_directory)
                from mmfdb.repository import MFDatabase

                MFDatabase(env["MMFDB_DATABASE_PATH"]).close()
                demo_dir = provision_demo(plugin_id, scratch, result) if mode == "emtk" else None
                if demo_dir:
                    result["demo_dir"] = str(demo_dir)
                result["stub_dir"] = str(Path(scratch) / "stubs")
                _guards(stack, result)
                with warnings.catch_warnings(record=True) as seen:
                    warnings.simplefilter("always")
                    _native(plugin_id, result, directory / f"{stem}.png")
                # A refused network/process attempt is evidence, not a failure by itself: the
                # guard raised an OSError, so a plugin that survives its offline path passes,
                # and one that lets it escape fails with the traceback of the click.
                result["status"] = "failed" if result["errors"] else "passed"
            except Exception as exc:
                result["exception_type"] = type(exc).__name__
                if isinstance(exc, ModuleNotFoundError):
                    origin = traceback.extract_tb(exc.__traceback__)[-1]
                    result["dependency"] = {
                        "module": exc.name,
                        "source": origin.filename,
                        "line": origin.lineno,
                    }
                result["errors"].append(traceback.format_exc())
            finally:
                if result["status"] == "running":
                    result["status"] = "failed"
                (directory / f"{stem}.json").write_text(
                    json.dumps(result, indent=2, default=str), encoding="utf-8"
                )
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-one", required=True)
    parser.add_argument("--mode", choices=("emtk",), required=True)
    parser.add_argument("--variant", choices=sorted(VARIANTS), default=None)
    args = parser.parse_args()
    raise SystemExit(run_one(args.run_one, args.mode, args.variant))
