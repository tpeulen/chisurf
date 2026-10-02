"""Qt-free tests for the native structure-tools workspace hub."""

from __future__ import annotations

import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.modelling.structure_tools.app import StructureToolsHubApp, make_app
from chisurf.plugins.modelling.structure_tools.registry import STRUCTURE_TOOL_PANELS


def test_registry_lists_all_qt_hub_panels():
    names = [panel["name"] for panel in STRUCTURE_TOOL_PANELS]
    assert names == [
        "FPS JSON Editor", "Docking & Screening", "Kappa2 Distribution",
        "QuEst", "HydroPro", "Trajectory Tools",
    ]


def test_native_select_routes_children_and_preserves_state():
    app = make_app()
    app.select("HydroPro")
    hydro = app.children.get("HydroPro")
    assert hydro is not None
    hydro.exe_path = "/opt/hydro.exe"
    app.select("HydroPro")
    assert app.children["HydroPro"] is hydro
    assert hydro.exe_path == "/opt/hydro.exe"


def test_native_unknown_tool_raises():
    app = make_app()
    with pytest.raises(ValueError):
        app.select("Nope")


def test_native_pending_panel_for_qt_only_tools():
    app = make_app()
    app.select("QuEst")
    assert app.child is None
    painter = RecordingPainter()
    app.draw(painter, 0, 0, 900, 640)
    assert "Native version pending" in painter.strings


def test_native_state_roundtrip():
    app = StructureToolsHubApp()
    app.select("HydroPro")
    app.children["HydroPro"].exe_path = "/opt/hydro.exe"
    app.selected = "HydroPro"
    state = app.export_settings()

    fresh = StructureToolsHubApp()
    fresh.restore_settings(state)
    assert fresh.selected == "HydroPro"
    assert fresh.children["HydroPro"].exe_path == "/opt/hydro.exe"


def test_native_renders_hub_and_children():
    app = make_app()
    painter = RecordingPainter()
    app.draw(painter, 0, 0, 900, 640)
    for expected in ("Available tools", "FPS JSON Editor", "Kappa2 Distribution", "HydroPro", "Trajectory Tools"):
        assert expected in painter.strings, expected


def test_structure_ribbon_entries_resolve_native():
    """The Structure ribbon's visible entries must open the EMTK apps.

    The host dispatches through select_gui_entrypoint in "auto" mode, which
    prefers the manifest's emtk entrypoint; this pins the user-facing rule
    that the ribbon's Structure entries open native surfaces.
    """
    import json
    import pathlib

    from chisurf.core.plugin import load_manifest
    from chisurf.core.plugin.registry import select_gui_entrypoint

    root = pathlib.Path(__file__).resolve().parents[5]
    for mf in sorted((root / "chisurf" / "plugins").rglob("manifest.json")):
        if "cookiecutter" in str(mf):
            continue
        data = json.loads(mf.read_text())
        display = data.get("display_name", "")
        if not data.get("entrypoints", {}).get("gui"):
            continue
        if "Structure" not in display.split(":"):
            continue
        if data.get("menu_hidden", False):
            continue  # hidden entries are reachable via the hubs instead
        manifest = load_manifest(mf)
        selected = select_gui_entrypoint(manifest, "auto")
        assert selected is not None and selected[0] == "emtk", (
            f"{data['id']} is visible in the Structure ribbon but does not "
            f"resolve to a native entrypoint: {selected}"
        )
