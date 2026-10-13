"""Plugin-to-plugin hand-off: the declared contract and the emtk shell that fulfils it.

A plugin asks the host to "open plugin X with payload P" (:mod:`chisurf.core.plugin.handoff`);
the shell opens X as a dock and, once X's app is built, passes P to the receive hook X's manifest
declares under ``accepts``. These tests use stand-in plugins (a probe app, a probe hook) so they
are fast; the real tools are driven end to end in the Trace Browser's
``test_emtk_trace_browser_t5.py``.
"""

from __future__ import annotations

import importlib
import json
import pathlib
import sys
import time
import types

import pytest
from emtk.testing import Driver

from chisurf.core.plugin import handoff
from chisurf.core.plugin.manifest import PluginManifest, validate_manifest

REPO = pathlib.Path(__file__).resolve().parents[2]
HOOKS = "chisurf_test_handoff_hooks"


class ProbeApp:
    """A plugin app that draws nothing and records what it was handed."""

    def __init__(self):
        self.received = []

    def draw(self, painter, x, y, w, h):
        return None


@pytest.fixture
def hooks(monkeypatch):
    """A module of receive hooks the manifests below name."""
    module = types.ModuleType(HOOKS)

    def receive(app, payload):
        app.received.append(dict(payload))

    def broken(app, payload):
        raise ValueError("cannot read that")

    module.receive, module.broken = receive, broken
    monkeypatch.setitem(sys.modules, HOOKS, module)
    return module


CATALOG = {
    "sender": {"id": "sender", "version": "1", "display_name": "Tools:Sender", "entrypoints": {"emtk": "x:y"}},
    "target": {
        "id": "target",
        "version": "1",
        "display_name": "Tools:Target",
        "entrypoints": {"emtk": "x:y"},
        "accepts": [
            {"name": "trace", "receive": f"{HOOKS}:receive", "required": ["file"]},
            {"name": "bad", "receive": f"{HOOKS}:broken"},
        ],
    },
    "command": {
        "id": "command",
        "version": "1",
        "display_name": "Tools:Command",
        "entrypoints": {"action": {"target": "x:y", "description": "d", "requires_main_window": False}},
        "accepts": [{"name": "trace", "receive": f"{HOOKS}:receive"}],
    },
}


@pytest.fixture
def shell(tmp_path, monkeypatch, hooks):
    from chisurf.emtk.main_app import EmtkShellApp

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    built = []

    def loader(plugin_id):
        time.sleep(0.05)  # the app exists only after a frame or two, as a real build
        app = ProbeApp()
        built.append(app)
        return app

    app = EmtkShellApp(CATALOG, loader=loader)
    app.built = built
    yield app
    app.close()


def until(driver, condition, timeout=10.0):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.01)
        driver.frame(1)
    driver.frame(1)


# ---- the declaration ---------------------------------------------------------------------------
def test_the_manifest_declares_accepted_payloads_and_round_trips():
    data = dict(CATALOG["target"])
    assert validate_manifest(data) == []
    manifest = PluginManifest.from_dict(data)
    assert [a.name for a in manifest.accepts] == ["trace", "bad"]
    assert manifest.accepts[0].required == ["file"]
    assert PluginManifest.from_dict(manifest.to_dict()).accepts == manifest.accepts


@pytest.mark.parametrize(
    "accepts, why",
    [
        ({"name": "x"}, "must be an array"),
        ([{"name": "trace"}], "receive must be module:function"),
        ([{"name": "Trace", "receive": "a:b"}], "lower-case identifier"),
        ([{"name": "t", "receive": "a:b"}, {"name": "t", "receive": "a:c"}], "declared twice"),
        ([{"name": "t", "receive": "a:b", "required": "file"}], "array of strings"),
        ([{"name": "t", "receive": "a:b", "hook": "c"}], "unknown field"),
    ],
)
def test_a_malformed_declaration_is_refused(accepts, why):
    errors = validate_manifest({"id": "p", "version": "1", "accepts": accepts})
    assert any(why in e for e in errors), errors


def test_every_shipped_receive_hook_resolves_to_a_callable():
    from chisurf.emtk.plugins import manifests

    declared = {
        (plugin_id, spec.name): spec.receive
        for plugin_id, data in manifests().items()
        for spec in handoff.specs_of(data)
    }
    assert {key[0] for key in declared} >= {"intensity_trace", "tttr_time_windows", "ndxplorer"}
    for key, receive in declared.items():
        module, _, name = receive.partition(":")
        assert callable(getattr(importlib.import_module(module), name)), key


# ---- no host ----------------------------------------------------------------------------------------
def test_without_a_host_nothing_is_available_and_a_hand_off_says_why(monkeypatch):
    monkeypatch.setattr(handoff, "_HOST", None)
    assert handoff.host() is None
    assert handoff.available("target", "trace") is False
    with pytest.raises(handoff.HandoffError, match="no ChiSurf window"):
        handoff.hand_off("target", "trace", {"file": "x"})


# ---- the shell ---------------------------------------------------------------------------------------
def test_the_shell_is_the_host_and_answers_from_the_declarations(shell):
    assert handoff.host() is shell
    assert handoff.available("target", "trace") is True
    assert handoff.available("target", "other") is False
    assert handoff.available("sender", "trace") is False  # declares nothing
    assert handoff.available("command", "trace") is False  # a command opens no window
    assert handoff.available("missing", "trace") is False


def test_the_payload_is_delivered_once_the_target_app_is_built(shell):
    driver = Driver(shell, (1200, 800))
    driver.frame(2)
    hosted = handoff.hand_off("target", "trace", {"file": "a.spc", "window_ms": 1.0})
    assert hosted is shell.hosted["target"] and hosted.app is None  # opened, not yet built
    assert shell.docks.window(hosted.key) is not None  # a dock, never a workspace window
    assert shell.docks.window(hosted.key).workspace is False
    until(driver, lambda: hosted.extra.get("handoffs"))
    assert shell.built[0].received == [{"file": "a.spc", "window_ms": 1.0}]
    assert hosted.extra["handoffs"] == ["trace"]


def test_an_open_tool_keeps_its_dock_and_takes_the_next_payload_at_once(shell):
    driver = Driver(shell, (1200, 800))
    first = handoff.hand_off("target", "trace", {"file": "a.spc"})
    until(driver, lambda: first.extra.get("handoffs"))
    second = handoff.hand_off("target", "trace", {"file": "b.spc"})
    assert second is first and len(shell.built) == 1
    assert shell.built[0].received == [{"file": "a.spc"}, {"file": "b.spc"}]  # no frame needed


def test_an_undeclared_kind_or_a_missing_key_is_refused_and_opens_nothing(shell):
    with pytest.raises(handoff.HandoffError, match="does not accept a other payload"):
        handoff.hand_off("target", "other", {"file": "a"})
    with pytest.raises(handoff.HandoffError, match="needs file"):
        handoff.hand_off("target", "trace", {"window_ms": 1.0})
    with pytest.raises(handoff.HandoffError, match="not a tool of this window"):
        handoff.hand_off("missing", "trace", {"file": "a"})
    assert shell.hosted == {}


def test_a_failing_receiver_is_said_and_the_shell_keeps_drawing(shell):
    driver = Driver(shell, (1200, 800))
    hosted = handoff.hand_off("target", "bad", {})
    until(driver, lambda: "handoff_error" in hosted.extra)
    assert hosted.extra["handoff_error"] == "ValueError: cannot read that"
    assert "cannot read that" in shell.status
    driver.frame(2)


def test_a_closed_shell_is_no_host(shell):
    shell.close()
    assert handoff.host() is None
    with pytest.raises(handoff.HandoffError):
        handoff.hand_off("target", "trace", {"file": "a"})


def test_the_written_manifest_schema_declares_accepts():
    schema = json.loads(
        (REPO / "chisurf" / "core" / "plugin" / "schemas" / "manifest.schema.json").read_text()
    )
    assert schema["properties"]["accepts"]["items"] == {"$ref": "#/$defs/handoff"}
    assert schema["$defs"]["handoff"]["required"] == ["name", "receive"]
