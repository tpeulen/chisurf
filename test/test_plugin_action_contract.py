"""Every shipped host action has a real typed target and explicit availability contract."""

import importlib
import inspect
import json
from pathlib import Path

from chisurf.core.api.context import PluginContext
from chisurf.core.plugin.manifest import load_manifest, validate_manifest
from chisurf.core.plugin.registry import execute_plugin_action

ROOT = Path(__file__).resolve().parents[1]


def test_all_shipped_actions_are_declared_and_report_missing_hosts():
    """Actions have their own contract instead of escaping GUI help checks by plugin name."""
    checked = []
    for path in sorted((ROOT / "chisurf/plugins").rglob("manifest.json")):
        if any("{{" in part for part in path.parts):
            continue
        data = json.loads(path.read_text())
        action = (data.get("entrypoints") or {}).get("action")
        if action is None:
            continue
        assert validate_manifest(data) == [], str(path)
        manifest = load_manifest(path)
        assert manifest is not None
        spec = manifest.entrypoints.action
        assert spec.description.strip()
        module, symbol = spec.target.split(":")
        target = getattr(importlib.import_module(module), symbol)
        assert callable(target)
        inspect.signature(target).bind(context=PluginContext())
        if spec.requires_main_window:
            result = execute_plugin_action(manifest, PluginContext())
            assert result["ok"] is False and result["available"] is False
            assert result["error"].strip()
        checked.append(manifest.id)
    assert checked, "The shipped action contract must exercise a real declared host action."
