"""Tests for the File tools hub: its panel list and the plugins it hides from the ribbon."""


def test_panels_name_plugins_with_a_native_app():
    """Every hub entry names a plugin folder whose manifest declares a resolvable emtk app."""
    import importlib
    import json
    import pathlib

    import pytest

    spec = json.loads(
        (pathlib.Path(__file__).parents[1] / "gui" / "panels.json").read_text(encoding="utf-8")
    )
    root = pathlib.Path(__file__).resolve().parents[3]
    for panel in spec["panels"]:
        if panel.get("separator"):
            continue
        manifest = json.loads(
            (root / panel["plugin"] / "manifest.json").read_text(encoding="utf-8")
        )
        module_name, _, attr = manifest["entrypoints"]["emtk"].partition(":")
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:  # pragma: no cover - optional dependency
            pytest.skip(f"{panel['name']}: {exc}")
        assert callable(getattr(module, attr)), panel["plugin"]


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
        "chisurf.plugins.burst.mfd_prepare",
    ):
        m = importlib.import_module(mod)
        manifest = json.loads(
            (pathlib.Path(m.__file__).parent / "manifest.json").read_text(encoding="utf-8")
        )
        assert manifest.get("menu_hidden") is True, mod


def test_hub_manifest_is_visible_and_loads():
    from pathlib import Path

    from chisurf.core.plugin import load_manifest

    manifest = load_manifest(Path(__file__).parents[1] / "manifest.json")

    assert manifest is not None
    assert manifest.id == "filetools"
    assert manifest.entrypoints.emtk == "chisurf.plugins.tttr.filetools.gui.app:make_app"
    assert manifest.menu_hidden is False
