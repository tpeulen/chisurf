"""Menu Switch toggles the real ChiSurf main window through the menu/ribbon launch path."""

from __future__ import annotations

import pathlib

import pytest
import yaml

import chisurf as cs
import chisurf.gui
from chisurf.core.settings.path_utils import get_path
from chisurf.gui.misc_helpers import run_plugin_from_dir

PLUGIN_DIR = pathlib.Path(cs.__file__).parent / "plugins" / "core" / "menu_switch"


@pytest.fixture(scope="module")
def main_window():
    """Return the real main window that menu and ribbon entries launch plugins from."""
    cs.gui.get_app()
    return cs.cs


def _saved_ribbon_preference():
    """Read the persisted interface preference from the hermetic settings file."""
    data = yaml.safe_load((get_path("settings") / "settings_chisurf.yaml").read_text()) or {}
    return data["gui"]["use_ribbon_interface"]


def test_menu_switch_toggles_real_interface_and_saves_preference(main_window):
    """Each launch flips menu↔ribbon, persists the result and opens no plugin window."""
    initial = main_window._ribbon_integration is not None
    windows_before = dict(getattr(main_window, "_plugin_windows", {}))
    try:
        run_plugin_from_dir(main_window, PLUGIN_DIR)
        assert (main_window._ribbon_integration is not None) is (not initial)
        assert _saved_ribbon_preference() is (not initial)
        assert main_window.plugins_toolbar.isHidden() is (not initial)

        run_plugin_from_dir(main_window, PLUGIN_DIR)
        assert (main_window._ribbon_integration is not None) is initial
        assert _saved_ribbon_preference() is initial
    finally:
        main_window.toggle_ribbon_interface(initial)
    assert dict(getattr(main_window, "_plugin_windows", {})) == windows_before
