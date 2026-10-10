"""Tests for the TTTR Tools hub: its panel list and the plugins it hides from the ribbon."""


def test_panels_name_plugins_with_a_native_app():
    """Every toolbox entry names a plugin folder whose manifest declares a resolvable emtk app."""
    import importlib
    import json
    import pathlib

    spec = json.loads(
        (pathlib.Path(__file__).parents[1] / "gui" / "panels.json").read_text(encoding="utf-8")
    )
    root = pathlib.Path(__file__).resolve().parents[3]
    panels = [p for p in spec["panels"] if not p.get("separator")]
    assert len(panels) == 5
    for panel in panels:
        manifest = json.loads(
            (root / panel["plugin"] / "manifest.json").read_text(encoding="utf-8")
        )
        module_name, _, attr = manifest["entrypoints"]["emtk"].partition(":")
        assert callable(getattr(importlib.import_module(module_name), attr)), panel["plugin"]


def test_included_plugins_are_menu_hidden():
    import importlib

    for mod in (
        "chisurf.plugins.tttr.ptu_alex_creator",
        "chisurf.plugins.tttr.tttr_microtime_shifter",
        "chisurf.plugins.tttr.photon_table",
        "chisurf.plugins.tttr.tttr_count_rate_analysis",
        "chisurf.plugins.tttr.audifier",
    ):
        m = importlib.import_module(mod)
        assert getattr(m, "menu_hidden", False) is True, mod
