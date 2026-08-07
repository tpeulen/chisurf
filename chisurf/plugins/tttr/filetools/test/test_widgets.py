"""Tests for the File tools hub (shared NavigationPanelTool shell)."""


def test_filetools_uses_shared_navigation_shell(qapp, qtbot):
    from chisurf.gui.widgets.navigation import NavigationPanelTool
    from chisurf.plugins.tttr.filetools.gui.tool import FILETOOLS_PANELS, FileToolsTool

    w = FileToolsTool()
    qtbot.addWidget(w)

    # same base / look as TTTR Tools, Structure Tools, Games, ...
    assert isinstance(w, NavigationPanelTool)
    assert "File tools" in w.windowTitle()

    # one navigation entry per panel
    assert w.nav_list.count() == len(FILETOOLS_PANELS)
    names = [w.nav_list.item(i).text() for i in range(w.nav_list.count())]
    assert any("Split / Convert" in n for n in names)
    assert any("Time Windows" in n for n in names)
    assert any("BID" in n for n in names)
    # The container tools: packing one, and reading one back.
    assert any(".pto" in n for n in names)
    assert any("Inspector" in n for n in names)
    assert any("header" in n for n in names)

    # panels load lazily: only the first + the (possibly persisted) current panel
    # are instantiated; every other panel stays a placeholder.
    kept = {0, w.nav_list.currentRow()}
    assert all(
        p.get("instance") is None
        for i, p in enumerate(w.panels)
        if i not in kept and not p.get("separator")
    )


def test_panels_are_data_driven_from_json():
    """The panel list is built from panels.json (entrypoint strings), not Python."""
    import json
    import pathlib

    from chisurf.plugins.tttr.filetools.gui import tool as tool_mod

    spec = json.loads((pathlib.Path(tool_mod.__file__).with_name("panels.json")).read_text())
    tool_panels = [p for p in spec["panels"] if not p.get("separator")]
    # every non-separator entry declares a resolvable "module:Class" entrypoint
    for p in tool_panels:
        module_name, _, attr = p["entrypoint"].partition(":")
        assert module_name and attr, p
    # and each becomes a panel with a generated factory
    built = [p for p in tool_mod.FILETOOLS_PANELS if not p.get("separator")]
    assert len(built) == len(tool_panels)
    assert all(callable(p["factory"]) for p in built)


def test_every_panel_entrypoint_resolves():
    """A hub entry naming a class that is not there renders an error panel."""
    import importlib
    import json
    import pathlib

    import pytest

    from chisurf.plugins.tttr.filetools.gui import tool as tool_mod

    spec = json.loads((pathlib.Path(tool_mod.__file__).with_name("panels.json")).read_text())
    for panel in spec["panels"]:
        if panel.get("separator"):
            continue
        module_name, _, attr = panel["entrypoint"].partition(":")
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:  # pragma: no cover - optional dependency
            pytest.skip(f"{panel['name']}: {exc}")
        assert callable(getattr(module, attr)), panel["entrypoint"]


def test_included_plugins_are_menu_hidden():
    """Every aggregated tool appears only inside the hub, not the ribbon."""
    import importlib
    import json
    import pathlib

    # Legacy plugins (no manifest) hide via a module-level ``menu_hidden`` attr.
    for mod in (
        "chisurf.plugins.tttr.tttr_splitter",
        "chisurf.plugins.burst.bid_to_analysis",
        "chisurf.plugins.tttr.tttr_header_edit",
    ):
        m = importlib.import_module(mod)
        assert getattr(m, "menu_hidden", False) is True, mod

    # Manifest-based plugins hide via the manifest flag.
    for mod in (
        "chisurf.plugins.tttr.tttr_time_windows",
        "chisurf.plugins.core.tttr_to_pto",
        "chisurf.plugins.core.pto_inspector",
    ):
        m = importlib.import_module(mod)
        manifest = json.loads((pathlib.Path(m.__file__).parent / "manifest.json").read_text())
        assert manifest.get("menu_hidden") is True, mod


def test_hub_manifest_is_visible_and_loads():
    from pathlib import Path

    from chisurf.core.plugin import load_manifest

    manifest = load_manifest(Path(__file__).parents[1] / "manifest.json")

    assert manifest is not None
    assert manifest.id == "filetools"
    assert manifest.entrypoints.gui == "chisurf.plugins.tttr.filetools.gui.tool:FileToolsTool"
    assert manifest.menu_hidden is False
