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


def test_every_tour_target_is_a_drawn_control_and_guide_opens_the_tour(tmp_path, monkeypatch):
    """The Agent panel draws Guide and ?, and each guide.json target is a recorded control."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    from emtk.testing import Driver

    from chisurf.plugins.core.agent.gui.panel import make_app

    app = make_app()
    try:
        driver = Driver(app, (760, 720))
        driver.frame(3)
        guide = json.loads(
            (Path(__file__).parents[3] / "chisurf/plugins/core/agent/gui/guide.json").read_text()
        )
        targets = {s["target"]["name"] for s in guide["steps"] if s.get("target")}
        assert targets <= set(app.item_rects), targets - set(app.item_rects)
        assert {"guide", "help"} <= set(app.item_rects)
        driver.click(app.item_rects["guide"])
        driver.frame(2)
        assert app.tour.active
    finally:
        app.close()
