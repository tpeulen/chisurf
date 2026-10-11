"""Typed contextual actions are discovered lazily and do not create plugin windows."""

import copy

import pytest

from chisurf.core.api.context import PluginContext
from chisurf.core.plugin.manifest import PluginManifest, validate_manifest, validate_manifest_schema
from chisurf.core.plugin.registry import PluginRegistry, execute_plugin_action


def declaration(**overrides):
    """Declare a generic action with explicit host ownership and explanatory metadata."""
    action = {
        "target": "example.action:run",
        "description": "Update the supplied host preference.",
        "requires_main_window": True,
    }
    action.update(overrides)
    return {"id": "host_action", "version": "1.0", "entrypoints": {"action": action}}


@pytest.mark.parametrize(
    "field,value",
    [
        ("target", ""),
        ("target", "example"),
        ("target", 7),
        ("description", " "),
        ("description", None),
        ("requires_main_window", "true"),
        ("requires_main_window", None),
    ],
)
def test_action_metadata_rejects_invalid_contract_fields(field, value):
    """Both lightweight discovery and generated schema reject malformed actions."""
    data = declaration(**{field: value})
    assert validate_manifest(data)
    assert validate_manifest_schema(data)


def test_action_round_trip_and_explicit_host_requirement():
    """Actions remain typed without guessing a default host requirement."""
    data = declaration()
    assert validate_manifest(data) == validate_manifest_schema(data) == []
    parsed = PluginManifest.from_dict(data)
    assert parsed.entrypoints.action.target == "example.action:run"
    assert parsed.to_dict()["entrypoints"]["action"] == data["entrypoints"]["action"]
    for field in ("target", "description", "requires_main_window"):
        incomplete = copy.deepcopy(data)
        del incomplete["entrypoints"]["action"][field]
        assert validate_manifest(incomplete) and validate_manifest_schema(incomplete)


@pytest.mark.parametrize("kind", ["gui", "emtk", "script"])
def test_actions_cannot_silently_shadow_a_window_or_script(kind):
    """A manifest has one unambiguous menu launch contract."""
    data = declaration()
    data["entrypoints"][kind] = "example.window:create" if kind != "script" else "__init__.py"
    assert validate_manifest(data) and validate_manifest_schema(data)


class Loader:
    """Record real lazy target resolution while retaining the supplied callback."""

    def __init__(self, callback):
        self.callback = callback
        self.loaded = []

    def load(self, target):
        """Resolve only on explicit action execution."""
        self.loaded.append(target)
        return self.callback


def test_missing_required_host_returns_unavailable_before_loading():
    """Standalone invocation has a useful failure and imports no action code."""
    loader = Loader(lambda context: pytest.fail("unavailable action ran"))
    result = execute_plugin_action(
        PluginManifest.from_dict(declaration()), PluginContext(), loader=loader
    )
    assert result["ok"] is False and result["available"] is False
    assert "main window" in result["error"]
    assert loader.loaded == []


def test_action_receives_exact_context_without_registering_global_state():
    """The existing dispatcher invokes the contextual handler once with no global registry edit."""
    import chisurf

    registry = getattr(chisurf, "action_registry", None)
    before = registry.list_actions() if registry is not None else None
    context = PluginContext(main_window=object())
    calls = []
    loader = Loader(lambda context: (calls.append(context), {"ok": True})[1])
    result = execute_plugin_action(PluginManifest.from_dict(declaration()), context, loader=loader)
    assert result == {"ok": True} and calls == [context]
    assert getattr(chisurf, "action_registry", None) is registry
    if registry is not None:
        assert registry.list_actions() == before


def test_registry_qaction_is_lazy_and_creates_no_window(qapp):
    """Actual menu activation dispatches the action without a ControlHost factory."""
    from qtpy.QtWidgets import QMenu

    calls = []
    loader = Loader(lambda context: (calls.append(context), {"ok": True})[1])
    context = PluginContext(main_window=object())
    manifest = PluginManifest.from_dict(declaration())
    registry = PluginRegistry(loader)
    registry._manifests = {manifest.id: manifest}
    menu = QMenu()
    registry.register_gui(menu, context=context)
    assert loader.loaded == []
    assert menu.actions()[0].toolTip() == manifest.entrypoints.action.description
    menu.actions()[0].trigger()
    assert calls == [context] and registry._gui_windows == {}
    unavailable = QMenu()
    registry.register_gui(unavailable)
    assert not unavailable.actions()[0].isEnabled()
    assert "main window" in unavailable.actions()[0].toolTip()
    menu.close()
    unavailable.close()


def test_action_runtime_failure_is_reported_without_legacy_fallback(caplog):
    """A raised action is a reported failure rather than an exception escaping a Qt slot."""

    def fail(context):
        """Expose a genuine handler failure after host validation."""
        raise RuntimeError("expected backend refusal")

    result = execute_plugin_action(
        PluginManifest.from_dict(declaration()),
        PluginContext(main_window=object()),
        loader=Loader(fail),
    )
    assert result["ok"] is False and "expected backend refusal" in result["error"]
    assert "host_action" in caplog.text


def test_log_mirror_survives_a_deleted_relay(qapp):
    """A log call after the GUI relay is destroyed is dropped, not raised into the caller."""
    import logging

    from PyQt5 import sip
    from qtpy.QtWidgets import QPlainTextEdit

    from chisurf.gui import QTextEditLogger

    handler = QTextEditLogger(QPlainTextEdit())
    sip.delete(handler._relay)
    handler.emit(logging.LogRecord("x", logging.ERROR, __file__, 1, "after teardown", None, None))
