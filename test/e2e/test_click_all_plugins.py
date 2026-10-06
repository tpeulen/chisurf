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
IDS_QT = sorted(i for i, m in CATALOG.items()
                if m.get("entrypoints", {}).get("gui") and not m.get("entrypoints", {}).get("emtk"))
SIZE = (1100, 720)
HARNESS_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
# The documented baseline remains recognizable; extra exclusions protect real
# accounts, remote jobs and hardware even when a plugin calls them "Run".
SKIP = re.compile(r"(open|load_file|save|browse|export|import|choose|folder|quit|close_window|delete)", re.I)
EXTERNAL = re.compile(
    r"(oauth|auth|login|logout|signin|account|credential|token|connect|disconnect|"
    r"upload|download|publish|deploy|submit|remote|server|hardware|device|acquire|"
    r"acquisition|record|start|run|compute|analyse|analyze|fit|simulate|shutdown|"
    r"remove|clear|reset_database|drop|erase|terminate|install|uninstall|archive|"
    r"sync|execute|send|commit|apply|activate|generate|train|retrain|optimize|"
    r"measure|capture|stream|emit|laser|shutter|update|user[ _-]*editor|switch[ _-]*user|"
    r"lsp|editor[ _-]*rpc|enable_rpc|python_lsp|show[ _-]*(key|token|secret)|reveal)", re.I,
)
CLICKABLE = frozenset({"button", "small_button", "checkbox", "radio_button", "selectable",
                       "combo", "input_text", "input_text_multiline", "input_float", "input_int",
                       "input_double", "slider_float", "slider_int", "drag_float", "drag_int",
                       "color_edit3", "color_edit4", "menu_item", "collapsing_header"})
CLICKABLE |= {"begin_tab_item", "tree_node", "list_box", "input_scalar"}
CLICKABLE |= {"autoform_fold"}


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


def _isolated(plugin_id, mode):
    """Launch one worker, retaining output and explicit crash/timeout evidence."""
    directory = artifact_dir()
    directory.mkdir(parents=True, exist_ok=True)
    result_path = directory / f"{artifact_stem(plugin_id)}.json"
    (directory / f"{artifact_stem(plugin_id)}.png").unlink(missing_ok=True)
    result_path.write_text(json.dumps({"plugin": plugin_id, "mode": mode, "status": "running",
                                      "errors": ["worker did not finish"]}, indent=2), encoding="utf-8")
    env = dict(os.environ)
    env.update(QT_QPA_PLATFORM="offscreen", MPLBACKEND="Agg", PYTHONUNBUFFERED="1",
               CHISURF_E2E_DIR=str(directory))
    sources = [str(REPO), str(REPO / "test"), str(REPO / "modules" / "chinet"),
               str(REPO / "modules" / "imp-tricks" / "src"), str(REPO / "modules" / "mmfdb" / "src")]
    if env.get("PYTHONPATH"):
        sources.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(sources)
    timeout = float(os.environ.get("CHISURF_E2E_TIMEOUT", "120"))
    command = [sys.executable, str(Path(__file__).resolve()), "--run-one", plugin_id, "--mode", mode]
    try:
        completed = subprocess.run(command, cwd=REPO, env=env, capture_output=True,
                                   text=True, timeout=timeout)
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
        result_path.write_text(json.dumps({"plugin": plugin_id, "mode": mode, "status": "failed",
                              "errors": [f"worker exited {completed.returncode} without result"]}, indent=2))
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
@pytest.mark.parametrize("plugin_id", IDS_QT, ids=str)
def test_qt_plugin_survives_every_button(plugin_id):
    """Exercise the remaining legacy Qt factories with native state isolated."""
    _isolated(plugin_id, "qt")


def _guards(stack, result):
    """Cancel OS dialogs and block browsers/network while preserving local rendering."""
    import socket
    import webbrowser

    from emtk.file_dialog import FileDialog
    from qtpy import QtGui, QtWidgets

    from chisurf.gui.dialogs import ChiSurfMessageBox, auto_answer

    for method, answer in (("getOpenFileName", ("", "")), ("getOpenFileNames", ([], "")),
                           ("getSaveFileName", ("", "")), ("getExistingDirectory", "")):
        stack.enter_context(patch.object(QtWidgets.QFileDialog, method, return_value=answer))
    stack.enter_context(auto_answer(question=ChiSurfMessageBox.No, warning=None,
                                   critical=None, information=None, about=None))
    def reject_modal(dialog, *args, **kwargs):
        """Construct real dialogs, but reject synchronous modal execution."""
        result["dialogs_closed"] += 1
        result.setdefault("cancelled_modals", []).append(type(dialog).__name__)
        dialog.reject()
        return QtWidgets.QDialog.Rejected
    for method in ("exec", "exec_"):
        if hasattr(QtWidgets.QDialog, method):
            stack.enter_context(patch.object(QtWidgets.QDialog, method, reject_modal))
    for method in ("question", "warning", "critical", "information", "about", "aboutQt"):
        stack.enter_context(patch.object(QtWidgets.QMessageBox, method, return_value=QtWidgets.QMessageBox.No))
    stack.enter_context(patch.object(webbrowser, "open", return_value=False))
    stack.enter_context(patch.object(webbrowser, "open_new", return_value=False))
    stack.enter_context(patch.object(webbrowser, "open_new_tab", return_value=False))
    stack.enter_context(patch.object(QtGui.QDesktopServices, "openUrl", return_value=False))
    def cancel_file_dialog(*args, **kwargs):
        """Native dialogs are exercised as cancel, never file selection or saving."""
        result["dialogs_closed"] += 1
        return False
    stack.enter_context(patch.object(FileDialog, "draw", cancel_file_dialog))
    connect = socket.socket.connect
    def local_only(sock, address):
        """Prevent plugin side effects through any IPv4/IPv6 service."""
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            result["blocked_actions"].append("socket.connect")
            raise RuntimeError("E2E blocks network/service connections")
        return connect(sock, address)
    stack.enter_context(patch.object(socket.socket, "connect", local_only))
    stack.enter_context(patch.object(socket.socket, "connect_ex", local_only))
    import zmq
    def no_zmq_connection(sock, address):
        """Keep C-level ZeroMQ sockets away from the user's actual daemons."""
        result["blocked_actions"].append({"operation": "zmq.Socket.connect",
                                        "phase": result.get("phase"),
                                        "control": result.get("current_control")})
        raise RuntimeError("E2E blocks real ZeroMQ service connections")
    stack.enter_context(patch.object(zmq.Socket, "connect", no_zmq_connection))
    stack.enter_context(patch.object(zmq.Socket, "bind", no_zmq_connection))
    def no_zmq_io(*args, **kwargs):
        """Fail offline RPC immediately rather than blocking on an unconnected socket."""
        raise RuntimeError("E2E ZeroMQ service I/O is offline")
    for method in ("send", "recv", "send_multipart", "recv_multipart"):
        stack.enter_context(patch.object(zmq.Socket, method, no_zmq_io))
    def no_external_process(*args, **kwargs):
        """Do not launch language servers, installers, or user tools from controls."""
        result["blocked_actions"].append({"operation": "external process",
                                        "phase": result.get("phase"),
                                        "control": result.get("current_control")})
        raise RuntimeError("E2E blocks external process launch")
    stack.enter_context(patch.object(subprocess, "Popen", no_external_process))
    from qtpy.QtCore import QProcess
    for method in ("start", "startDetached", "execute"):
        stack.enter_context(patch.object(QProcess, method, no_external_process))
    for method in dir(os):
        if method.startswith(("exec", "spawn")) or method in ("system", "popen", "startfile"):
            if callable(getattr(os, method)):
                stack.enter_context(patch.object(os, method, no_external_process))


def control_tags(spec, control):
    """Read declared action tags before deciding whether a control may be clicked."""
    name = str(control).split("##")[-1]
    tags = set()
    for section in walk(spec):
        candidates = [section, *(section.get("buttons") or [])]
        for item in candidates:
            if isinstance(item, dict) and name in (item.get("attr"), item.get("target"),
                                                  item.get("key"), item.get("action")):
                declared = item.get("tags", [])
                tags.update([declared] if isinstance(declared, str) else declared)
                tags.update(key for key in ("modal", "file", "dangerous", "external", "hardware")
                            if item.get(key) is True)
    return tags


def dialog_open(app):
    """Recognize native modal/file state without opening or selecting a resource."""
    for owner in (app, getattr(app, "model", None)):
        if owner is not None and any(getattr(owner, name, None) not in (None, False)
                                     for name in ("dialog", "file_dialog")):
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
    owners.extend(owner for name, owner in getattr(app, "__dict__", {}).items()
                  if name.endswith("_gui") and owner not in owners)
    for owner in owners:
        for name in ("tour", "guide"):
            tour = getattr(owner, name, None)
            if all(callable(getattr(tour, method, None)) for method in ("start", "next", "stop")):
                return tour
    return None


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
    return (left, top, right - left, bottom - top) if right - left > 2 and bottom - top > 2 else None


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


def reveal_control(driver, recorder, visit_id):
    """Scroll a real scrolling region to a target, or fail its coverage explicitly."""
    for attempt in range(16):
        recorder.rows.clear()
        driver.frame()
        latest = {row["visit_id"]: row for row in recorder.rows}
        row = latest.get(visit_id)
        if row is None:
            return None
        visible = visible_rectangle(row, driver.size)
        if visible is not None:
            return row, visible
        assert row.get("scrollable"), f"coverage: offscreen control {row['id']!r} has no scroll/reveal route"
        clip = row["clip_rect"]
        area = visible_rectangle({"rect": clip, "clip_rect": clip}, driver.size)
        assert area is not None, f"coverage: scrolling region for {row['id']!r} is not visible"
        direction = -1 if row["rect"][1] + row["rect"][3] / 2 > area[1] + area[3] / 2 else 1
        driver.wheel(direction, at=(area[0] + area[2] / 2, area[1] + area[3] / 2))
    raise AssertionError(f"coverage: could not reveal {row['id']!r} after {attempt + 1} scrolls")


def resolved_tour_control(rows, target, rect):
    """Resolve the authoritative global target geometry before consulting duplicate labels."""
    unique = list({row["visit_id"]: row for row in rows}.values())
    exact = [row for row in unique if row.get("rect") is not None
             and all(abs(a - b) < 0.5 for a, b in zip(row["rect"], rect))]
    if exact:
        matches = exact
    else:
        named = [row for row in unique if row["id"].split("##")[-1] == target]
        px, py = rect[0] + rect[2] / 2, rect[1] + rect[3] / 2
        matches = [row for row in (named or unique) if row.get("rect") is not None
                   and row["rect"][0] <= px <= row["rect"][0] + row["rect"][2]
                   and row["rect"][1] <= py <= row["rect"][1] + row["rect"][3]]
    assert len(matches) <= 1, f"coverage: guide target {target!r} is ambiguous across contexts"
    return matches[0] if matches else None


def operate_awaited_tour_step(driver, tour, result, recorder):
    """Operate the first real awaited example and preserve valid tour completion."""
    before = tour.step_idx
    result.setdefault("tour_indices", [before])
    if tour.steps[before].get("await"):
        assert tour.wait_for_controls, "coverage: awaited tour is not wired to real control notifications"
        target = tour._target_key(tour.steps[before].get("target"))
        result["tour_await_target"] = target
        reason = skip_reason(target)
        assert not reason, f"tour awaits unsafe control {target!r}: {reason}"
        try:
            rect = driver.rect(target)
        except LookupError:
            rect = tour.get_target_rect(target) if callable(tour.get_target_rect) else None
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
            assert not re.search(r"(file|path|url|token|credential|secret)", target, re.I), (
                f"tour requires unsafe text edit {target!r}"
            )
            driver.press(ord("A"), CONTROL_MODIFIER)
            # Whitespace changes the real field; numeric parsing preserves its value.
            driver.type(str(value) + " ")
            driver.press(keys.KEY_RETURN)
        driver.frame(2)
        settle_with_cancel(driver, recorder, result)
        assert not tour.awaiting, f"real interaction with {target!r} did not satisfy tour await"
    tour.next()
    driver.frame(2)
    if tour.active:
        assert tour.step_idx == before + 1, f"guided tour did not advance: {before} -> {tour.step_idx}"
        result["tour_indices"].append(tour.step_idx)
    else:
        assert before == len(tour.steps) - 1, "guided tour ended before its final real example"
        result["tour_completed"] = True
    result["tour_await_exercised"] = True
    result["tour_steps"] = len(result["tour_indices"]) - 1 + int(result.get("tour_completed", False))


def advance_tour(driver, tour, result, recorder):
    """Traverse bounded introductions, then exercise the first real awaited target."""
    result["tour_indices"] = [tour.step_idx]
    for _ in range(12):
        if tour.steps[tour.step_idx].get("await"):
            return operate_awaited_tour_step(driver, tour, result, recorder)
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
        stops = [row for row in recorder.rows
                 if row["kind"] in ("button", "small_button", "menu_item")
                 and row.get("enabled", True)
                 and re.search(r"(^|[^a-z])(cancel|stop)([^a-z]|$)", row["id"], re.I)]
        if not stops:
            raise TimeoutError("job exceeded 30s and has no enabled Cancel/Stop control") from exc
        stop = stops[0]
        result.setdefault("job_cancellations", []).append({"job_control": result.get("current_control"),
                                                          "cancel_control": stop["id"]})
        result["phase"] = "cancel"
        checkpoint(result)
        driver.click(stop["rect"])
        try:
            return driver.settle(timeout=5)
        except TimeoutError as pending:
            raise TimeoutError(f"{stop['id']!r} did not restore an idle app within 5s") from pending


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
            self.pressed_ids = set()
            self.contact_ids = set()

        def capture(self, kind):
            """Record the actual item geometry, clipping, and enabled state."""
            from emtk.im_core import ItemFlags
            ctx = im.get_current_context()
            row = self.rows[-1]
            rect = im.get_item_rect()
            identity = f"{id(ctx.storage)}:{im.get_item_id()!r}"
            row.update(rect=painter_rectangle(ctx.p, rect),
                       visit_id=f"{kind}:{identity}",
                       engine_id=identity, clip_rect=painter_rectangle(ctx.p, ctx.clip_rect),
                       enabled=not bool(ctx.item_flags & ItemFlags.DISABLED),
                       scrollable=any(len(child) > 6 and child[6] for child in ctx._child))

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
            with super().installed(), patch.object(Context, "button_behavior", observe_behavior), \
                    patch.object(Context, "item_add", observe_item), patch.object(view_form, "_fold", observe_fold):
                yield self

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
    app = load_plugin(plugin_id, persist=False)
    driver = Driver(app, SIZE)
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
            controls = {row["visit_id"]: dict(row) for row in recorder.rows if row["kind"] in CLICKABLE}
            pending = sorted(controls)
            visited = set()
            while pending:
                # Finish the current page before selecting a different tab.
                pending.sort(key=lambda name: (controls[name]["kind"] == "begin_tab_item", name))
                name = pending.pop(0)
                if name in visited:
                    continue
                visited.add(name)
                assert len(visited) <= 512, "control inventory did not stabilize within 512 targets"
                control = controls[name]
                raw_name = control["id"]
                reason = skip_reason(raw_name + " " + control["label"],
                                     control_tags(getattr(app, "spec", {}), raw_name))
                if reason:
                    result["skipped"].append({"control": name, "reason": reason})
                    continue
                revealed = reveal_control(driver, recorder, name)
                if revealed is None:
                    visited.remove(name)
                    result["skipped"].append({"control": name, "reason": "no longer drawn after prior control"})
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
                proof = (recorder.pressed_ids if control["kind"] in
                         {"button", "small_button", "radio_button", "selectable", "menu_item", "autoform_fold"}
                         else recorder.pressed_ids | recorder.contact_ids)
                assert current["engine_id"] in proof, f"coverage: visible {raw_name!r} did not receive an actual click"
                if current.get("expanded"):
                    # An already open group must stay reachable for its child controls.
                    driver.click(click_box)
                result["clicked"].append(raw_name)
                result.setdefault("clicked_ids", []).append(name)
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
                settle_with_cancel(driver, recorder, result)
                assert not getattr(app, "running", False), "long-running control without cancel"
                recorder.rows.clear()
                driver.frame()
                for row in recorder.rows:
                    if row["kind"] in CLICKABLE:
                        controls[row["visit_id"]] = dict(row)
                        if row["visit_id"] not in visited and row["visit_id"] not in pending:
                            pending.append(row["visit_id"])
            result["controls"] = list(controls.values())
            for section in walk(getattr(app, "spec", {})):
                if section.get("type") == "choice":
                    name = str(section.get("attr") or section.get("target") or section.get("key") or "")
                    if name and name in driver.ids() and not skip_reason(name):
                        driver.click(name)
                        driver.escape()
                        result["combos"].append(name)
            for _ in range(20):
                driver.press(keys.KEY_TAB)
            result["tab_presses"] = 20
            result["phase"] = "tour"
            checkpoint(result)
            tour = tour_for(app)
            if tour is None:
                result["errors"].append("missing guided tour on app or its declared guide owner")
            else:
                tour.start()
                driver.frame(2)
                if not tour.active:
                    result["errors"].append("guided tour did not activate")
                else:
                    advance_tour(driver, tour, result, recorder)
                tour.stop()
            recorder.rows.clear()
            driver.frame()
        inventory = emtk_inventory(app, SIZE)
        result["inventory"] = inventory
        missing = sorted(set(inventory["controls_without_tooltip"]) |
                         {f"{row['kind']}: {row['label'] or row['id']}" for row in controls.values()
                          if not row["tooltip"]})
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


def _qt(plugin_id, result, png_path, qapp):
    """Click safe legacy buttons and grab the widget before closing it."""
    from qtpy.QtWidgets import QAbstractButton

    from chisurf.core.plugin.manifest import load_manifest
    from chisurf.core.plugin.registry import build_plugin_widget
    from chisurf.core.settings import cs_settings

    path = next(p for p in (REPO / "chisurf" / "plugins").rglob("manifest.json")
                if json.loads(p.read_text(encoding="utf-8")).get("id") == plugin_id)
    cs_settings.setdefault("plugins", {})["gui_mode"] = "qt"
    result["phase"] = "factory"
    checkpoint(result)
    widget = build_plugin_widget(load_manifest(path))
    try:
        widget.resize(*SIZE)
        widget.show()
        for _ in range(3):
            qapp.processEvents()
        for button in widget.findChildren(QAbstractButton):
            if not button.isEnabled():
                continue
            name = button.objectName() + " " + button.text()
            reason = skip_reason(name)
            if reason:
                result["skipped"].append({"control": name, "reason": reason})
            else:
                result["current_control"] = name
                result["phase"] = "click"
                checkpoint(result)
                button.click()
                result["clicked"].append(name)
                for _ in range(3):
                    qapp.processEvents()
        assert widget.grab().save(str(png_path)), "Qt PNG save failed"
    finally:
        widget.close()
        widget.deleteLater()
        qapp.processEvents()


def run_one(plugin_id, mode):
    """Create scratch state before imports, then always write a worker result."""
    directory = artifact_dir()
    directory.mkdir(parents=True, exist_ok=True)
    stem = artifact_stem(plugin_id)
    result = {"plugin": plugin_id, "mode": mode, "status": "running", "size": list(SIZE),
              "harness_sha256": HARNESS_SHA256,
              "python": sys.version, "machine": platform.machine(), "clicked": [], "skipped": [],
              "dialogs_closed": 0, "combos": [], "tabs": [], "tour_steps": 0,
              "errors": [], "blocked_actions": []}
    with tempfile.TemporaryDirectory(prefix="chisurf-e2e-") as scratch:
        env = {"CHISURF_SETTINGS_DIR": str(Path(scratch) / "settings"),
               "MMFDB_SETTINGS_DIR": str(Path(scratch) / "mmfdb"),
               "MMFDB_DATABASE_PATH": str(Path(scratch) / "mmfdb.sqlite"),
               "MMFDB_OBJECT_STORE_ROOT": str(Path(scratch) / "objects"),
               "XDG_CACHE_HOME": str(Path(scratch) / "cache"),
               "LUMIS_QUEST_HOME": str(Path(scratch) / "lumis"), "QT_QPA_PLATFORM": "offscreen"}
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
                from qtpy.QtWidgets import QApplication

                from test.e2e.conftest import close_created_plots
                MFDatabase(env["MMFDB_DATABASE_PATH"]).close()
                qapp = QApplication.instance() or QApplication([])
                _guards(stack, result)
                stack.enter_context(close_created_plots())
                with warnings.catch_warnings(record=True) as seen:
                    warnings.simplefilter("always")
                    if mode == "emtk":
                        _native(plugin_id, result, directory / f"{stem}.png")
                    else:
                        _qt(plugin_id, result, directory / f"{stem}.png", qapp)
                passthrough = [str(w.message) for w in seen if w.category.__name__ == "ChiplotPassthroughWarning"]
                if passthrough:
                    result["errors"].append("chiplot passthrough: " + "; ".join(passthrough))
                if result["blocked_actions"]:
                    result["errors"].append("plugin attempted blocked service/network action")
                result["status"] = "failed" if result["errors"] else "passed"
            except Exception as exc:
                result["exception_type"] = type(exc).__name__
                if isinstance(exc, ModuleNotFoundError):
                    origin = traceback.extract_tb(exc.__traceback__)[-1]
                    result["dependency"] = {"module": exc.name, "source": origin.filename,
                                            "line": origin.lineno}
                result["errors"].append(traceback.format_exc())
            finally:
                if "qapp" in locals():
                    for widget in qapp.topLevelWidgets():
                        try:
                            widget.close()
                            widget.deleteLater()
                        except RuntimeError:
                            continue
                    qapp.processEvents()
                if result["status"] == "running":
                    result["status"] = "failed"
                (directory / f"{stem}.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-one", required=True)
    parser.add_argument("--mode", choices=("emtk", "qt"), required=True)
    args = parser.parse_args()
    raise SystemExit(run_one(args.run_one, args.mode))
