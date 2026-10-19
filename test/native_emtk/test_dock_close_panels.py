"""The shell's dock tab menu: Close all / Close other panels, its height, and tab titles in the UI language.

Driven with :class:`emtk.testing_realistic.RealisticDriver` -- a real right-click on a tab, then a click on
the menu row -- on the shell with probe tools standing in for plugins.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from emtk import i18n as toolkit_i18n
from emtk.app import ImApp
from emtk.events import RIGHT_BUTTON
from emtk.testing_realistic import RealisticDriver

from chisurf.emtk.main_app import EmtkShellApp

SHOTS = Path(os.environ.get("CHISURF_NATIVE_SCREENSHOTS", "/private/tmp/chisurf-native-gpu"))
CATALOG = {
    "setup": {"display_name": "Setup:Settings", "entrypoints": {"emtk": "x:y"}},
    "filetools": {"display_name": "File:Data:File tools", "entrypoints": {"emtk": "x:y"}},
    "games": {"display_name": "Tools:System:Games", "entrypoints": {"emtk": "x:y"}},
}
#: The core docks of the shell's outer dock manager. Start is not among them: it lives in the
#: workspace (``shell.workspace_docks``), which is itself the core ``workspace`` dock.
CORE = {"tools", "workspace", "log", "console", "data.read", "data.sets", "fit.analysis", "fit.plot"}


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch):
    """Preferences go to a scratch folder; the language is put back after the test."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    before = toolkit_i18n.get_locale()
    yield
    toolkit_i18n.set_locale(before)


def _shell_with_tools():
    from chisurf.emtk import i18n

    i18n.install("en")
    shell = EmtkShellApp(CATALOG, loader=lambda plugin_id: ImApp(lambda: None))
    driver = RealisticDriver(shell, (1440, 900), real_painter=False)
    driver.frame(3)
    for plugin_id in CATALOG:
        shell.open_plugin(plugin_id)
        driver.frame(2)
    for _ in range(200):
        if all(h.build is None for h in shell.hosted.values()):
            break
        driver.frame(1)
    driver.frame(3)
    return shell, driver


def _shown(shell) -> set[str]:
    return {key for key, win in shell.docks.windows.items() if win.visible}


def _right_click_tab(shell, driver, key: str) -> None:
    region = shell.docks.region_of(key)
    rect = next(r for k, r in shell.docks._tab_rects[region] if k == key)
    driver.click((rect[0] + rect[2] / 2, rect[1] + rect[3] / 2), button=RIGHT_BUTTON)
    driver.frame(2)


def _row(driver, label: str):
    return next(t[:4] for t in driver.painter.texts if t[5].strip() == label)


def test_close_all_panels_leaves_only_the_core_docks():
    shell, driver = _shell_with_tools()
    assert {"plugin.setup", "plugin.filetools", "plugin.games"} <= _shown(shell)
    _right_click_tab(shell, driver, "plugin.filetools")
    driver.click(_row(driver, "Close all panels"))
    driver.frame(4)
    assert _shown(shell) == CORE
    assert shell.hosted == {}
    assert shell.workspace_docks.is_visible("start"), "the workspace keeps its Start page"


def test_close_other_panels_keeps_the_clicked_tool_and_the_core_docks():
    shell, driver = _shell_with_tools()
    _right_click_tab(shell, driver, "plugin.filetools")
    driver.click(_row(driver, "Close other panels"))
    driver.frame(4)
    assert _shown(shell) == CORE | {"plugin.filetools"}
    assert list(shell.hosted) == ["filetools"]


def test_restore_default_layout_still_resets_after_close_all():
    shell, driver = _shell_with_tools()
    _right_click_tab(shell, driver, "plugin.setup")
    driver.click(_row(driver, "Close all panels"))
    driver.frame(4)
    _right_click_tab(shell, driver, "log")
    driver.click(_row(driver, "Restore default layout"))
    driver.frame(3)
    assert CORE <= _shown(shell)


def test_tab_menu_has_no_blank_row_and_is_read_in_a_screenshot():
    shell, driver = _shell_with_tools()
    _right_click_tab(shell, driver, "plugin.setup")
    labels = {
        "Undock",
        "Close panel",
        "Close other panels",
        "Close all panels",
        "Restore default layout",
    }
    rows = [t for t in driver.painter.texts if t[5].strip() in labels]
    assert {t[5].strip() for t in rows} == labels
    height = shell.docks._context_heights[next(iter(shell.docks._context_heights))]
    text_span = max(t[1] + t[3] for t in rows) - min(t[1] for t in rows)
    assert height - text_span < 0.9 * shell.docks._title_h
    SHOTS.mkdir(parents=True, exist_ok=True)
    driver.screenshot(SHOTS / "dock_tab_menu.png")


def test_tab_titles_follow_the_language_switched_after_the_tool_opened():
    shell, driver = _shell_with_tools()
    from chisurf.emtk import i18n

    i18n.set_locale("de")
    driver.frame(3)
    drawn = {t[5].strip() for t in driver.painter.texts}
    assert {"Einstellungen", "Datei-Werkzeuge", "Spiele"} <= drawn
    assert not {"Settings", "File tools"} & drawn


def test_tab_menu_is_translated_into_german_and_french():
    shell, driver = _shell_with_tools()
    from chisurf.emtk import i18n

    for code, close_all, close_other in (
        ("de", "Alle Bereiche schließen", "Andere Bereiche schließen"),
        ("fr", "Fermer tous les panneaux", "Fermer les autres panneaux"),
    ):
        i18n.set_locale(code)
        driver.frame(2)
        _right_click_tab(shell, driver, "plugin.setup")
        drawn = {t[5].strip() for t in driver.painter.texts}
        assert {close_all, close_other} <= drawn
        if code == "de":
            SHOTS.mkdir(parents=True, exist_ok=True)
            driver.screenshot(SHOTS / "dock_tab_menu_de.png")
        driver.click((700, 880))  # a click away closes the menu
        driver.frame(2)
