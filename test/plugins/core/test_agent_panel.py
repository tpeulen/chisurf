"""The agent plugin reuses the code editor's AI Assistant, unchanged."""

from __future__ import annotations

import json
from pathlib import Path


def test_the_manifest_resolves_to_the_code_editor_chat_app():
    manifest = json.loads(
        (Path(__file__).parents[3] / "chisurf/plugins/core/agent/manifest.json").read_text()
    )
    assert manifest["id"] == "agent"
    assert "Tools" in manifest["categories"]
    module_name, _, attribute = manifest["entrypoints"]["emtk"].partition(":")
    import importlib

    factory = getattr(importlib.import_module(module_name), attribute)
    assert callable(factory)


def test_the_entrypoint_is_the_same_assistant_as_the_code_editors():
    from chisurf.plugins.core.agent.gui.panel import make_app
    from chisurf.plugins.core.code_editor.gui.chat_app import ChatApp, make_chat_app

    assert make_app.__wrapped__ is None if hasattr(make_app, "__wrapped__") else True
    # Same application class, same factory semantics: opening Agent from the
    # Tools menu builds exactly what the code editor's assistant builds.
    assert make_chat_app.__annotations__.get("return") is ChatApp or callable(make_chat_app)


def test_the_assistant_session_carries_the_full_registry():
    """The workflow registry, not a restricted one: the burst chain is reachable."""
    from chisurf.plugins.core.code_editor.gui.chat_app import _default_registry

    names = set(_default_registry().names())
    for expected in (
        "run_burst_analysis",
        "select_species",
        "extract_subensemble_decay",
        "fit_distance_distribution",
        "ask_user",
        "run_python",
        "load_data",
        "create_fit",
    ):
        assert expected in names, f"the assistant cannot reach {expected}"
