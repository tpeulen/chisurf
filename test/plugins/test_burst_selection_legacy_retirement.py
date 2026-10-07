"""Burst Selection retirement retains its real native factory and adapter namespace."""

import json
from importlib import import_module
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "chisurf/plugins/burst/burst_selection"


@pytest.mark.parametrize(
    "relative",
    [
        "gui/legacy/burst_selector.py",
        "gui/assets/gui.ui",
        "gui/assets/icon.png",
        "gui/assets/channel_settings.json",
    ],
)
def test_retired_legacy_source_and_resources_are_absent(relative):
    """Removing only a launcher cannot leave the old shipped UI reachable."""
    assert not (PLUGIN / relative).exists(), relative


def test_public_package_has_no_legacy_gui_switch():
    """The retired GUI cannot remain selectable through its old public toggle."""
    package = import_module("chisurf.plugins.burst.burst_selection")
    assert not hasattr(package, "USE_LEGACY_GUI")


def test_declared_native_factory_and_adapter_api_remain_available():
    """The real native declaration and portable adapter identities survive removal."""
    from chisurf.emtk.plugins import native_factory

    manifest = json.loads((PLUGIN / "manifest.json").read_text())
    target = "chisurf.plugins.burst.burst_selection.gui.native:create_app"
    assert (
        manifest["entrypoints"]["emtk"] == native_factory("burst_selection", root=PLUGIN) == target
    )
    module, name = target.split(":")
    assert callable(getattr(import_module(module), name))
    adapter = import_module("chisurf.plugins.burst.burst_selection.gui.adapter")
    public = import_module("chisurf.plugins.burst.burst_selection.gui")
    assert public.make_ui_dataframe is adapter.make_ui_dataframe
    assert public.selected_histogram_data is adapter.selected_histogram_data


def test_current_public_tool_and_wizard_bind_to_the_migrated_tool():
    """Legacy-source deletion must retain the current public launcher identity."""
    package = import_module("chisurf.plugins.burst.burst_selection")
    current = import_module("chisurf.plugins.burst.burst_selection.gui.tool")
    wizard = import_module("chisurf.plugins.burst.burst_selection.wizard")
    assert package.BurstSelectionTool is current.BurstSelectionTool
    assert wizard.BurstSelectionTool is current.BurstSelectionTool
