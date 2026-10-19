"""A tool opens as often as it is asked for: "ndX", "ndX #2", ... each its own app.

Opening a tool from the menus, the tool list or the ribbon used to show the window already
open, so two data sets could not be compared side by side. Settings-like tools keep one
window (manifest ``single_instance``); programmatic opens (hand-offs, help, restore) still
reach the open one.
"""

from __future__ import annotations

import pytest
from emtk import i18n as toolkit_i18n
from emtk.app import ImApp
from emtk.testing_realistic import RealisticDriver

from chisurf.emtk.main_app import EmtkShellApp

CATALOG = {
    "ndxplorer": {"display_name": "Tools:Views:ndX", "entrypoints": {"emtk": "x:y"}},
    "setup": {"display_name": "Setup:Settings", "entrypoints": {"emtk": "x:y"},
              "single_instance": True},
}


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    before = toolkit_i18n.get_locale()
    yield
    toolkit_i18n.set_locale(before)


def _shell():
    from chisurf.emtk import i18n

    i18n.install("en")
    built = []

    def loader(plugin_id):
        app = ImApp(lambda: None)
        built.append((plugin_id, app))
        return app

    shell = EmtkShellApp(CATALOG, loader=loader)
    driver = RealisticDriver(shell, (1200, 800), real_painter=False)
    driver.frame(3)
    return shell, driver, built


def _settle(shell, driver):
    for _ in range(200):
        if all(h.build is None for h in shell.hosted.values()):
            break
        driver.frame(1)
    driver.frame(2)


def test_opening_a_tool_again_numbers_a_new_window():
    shell, driver, built = _shell()
    try:
        first = shell.open_plugin("ndxplorer", new=True)
        second = shell.open_plugin("ndxplorer", new=True)
        third = shell.open_plugin("ndxplorer", new=True)
        _settle(shell, driver)
        assert [h.instance_id for h in shell.instances("ndxplorer")] == [
            "ndxplorer", "ndxplorer#2", "ndxplorer#3"]
        assert [shell.docks.window(h.key).title for h in (first, second, third)] == [
            "ndX", "ndX #2", "ndX #3"]
        apps = [app for pid, app in built if pid == "ndxplorer"]
        assert len(apps) == 3 and len({id(a) for a in apps}) == 3, "each opening is its own app"
        # A programmatic open (hand-off, host_in_shell) reaches an open one, not a fourth.
        assert shell.open_plugin("ndxplorer") in (first, second, third)
        assert len(shell.instances("ndxplorer")) == 3
    finally:
        shell.close()


def test_a_closed_number_is_reused_and_the_layout_reopens_the_numbers():
    shell, driver, _built = _shell()
    try:
        for _ in range(3):
            shell.open_plugin("ndxplorer", new=True)
        _settle(shell, driver)
        shell.close_plugin("ndxplorer#2")
        again = shell.open_plugin("ndxplorer", new=True)
        assert again.instance_id == "ndxplorer#2"
        saved = shell.export_settings()
        assert sorted(saved["open"]) == ["ndxplorer", "ndxplorer#2", "ndxplorer#3"]
    finally:
        shell.close()
    shell, driver, _built = _shell()
    try:
        shell.restore_settings(saved)
        _settle(shell, driver)
        assert sorted(shell.hosted) == ["ndxplorer", "ndxplorer#2", "ndxplorer#3"]
    finally:
        shell.close()


def test_a_single_instance_tool_keeps_one_window():
    shell, driver, _built = _shell()
    try:
        first = shell.open_plugin("setup", new=True)
        assert shell.open_plugin("setup", new=True) is first
        _settle(shell, driver)
        assert [h.instance_id for h in shell.instances("setup")] == ["setup"]
    finally:
        shell.close()
