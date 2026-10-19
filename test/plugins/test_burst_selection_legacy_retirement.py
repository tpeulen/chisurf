"""Burst Selection retirement retains its real native factory and adapter namespace; the Qt tool stays retired."""

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


def test_the_qt_tool_and_its_launchers_are_gone():
    """The Qt tool, its wizard launcher and the dead module shadowed by the ``gui`` package are retired."""
    package = import_module("chisurf.plugins.burst.burst_selection")
    assert not hasattr(package, "BurstSelectionTool")
    for relative in (
        "gui/tool.py",
        "gui/app.py",
        "gui/sections.py",
        "gui/gmm_settings_dialog.py",
        "gui/display_view_model.py",
        "gui/timeline.py",
        "gui/burst_display.view.json",
        "gui.py",
        "wizard.py",
    ):
        assert not (PLUGIN / relative).exists(), relative
    assert "gui" not in json.loads((PLUGIN / "manifest.json").read_text())["entrypoints"]
