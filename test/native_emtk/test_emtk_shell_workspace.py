"""The shell's Workspace: every unbound window lives in it, none can fall behind or out of reach.

Driven as a user drives it, with :class:`emtk.testing_realistic.RealisticDriver` -- real presses,
drags and keys through the platform layer -- on the shell with probe tools standing in for
plugins. The mechanics (clamping, tiling, minimizing, the menu) are emtk's
(``tests/test_docking_workspace.py`` there); this is the shell using them.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from emtk import i18n as toolkit_i18n
from emtk.app import ImApp
from emtk.events import CONTROL_MODIFIER, RIGHT_BUTTON
from emtk.keys import KEY_TAB
from emtk.testing_realistic import RealisticDriver

from chisurf.emtk.main_app import EmtkShellApp

SHOTS = Path(os.environ.get("CHISURF_NATIVE_SCREENSHOTS", "/private/tmp/chisurf-native-gpu"))
CATALOG = {
    "setup": {"display_name": "Setup:Settings", "entrypoints": {"emtk": "x:y"}},
    "filetools": {"display_name": "File:Data:File tools", "entrypoints": {"emtk": "x:y"}},
    "games": {"display_name": "Tools:System:Games", "entrypoints": {"emtk": "x:y"}},
    "help": {"display_name": "Help:Documentation", "entrypoints": {"emtk": "x:y"}},
}
TOOLS = ("plugin.setup", "plugin.filetools", "plugin.games")


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch):
    """Preferences go to a scratch folder; the language is put back after the test."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    before = toolkit_i18n.get_locale()
    yield
    toolkit_i18n.set_locale(before)


def _shell(size=(1440, 900), language="en"):
    from chisurf.emtk import i18n

    i18n.install(language)
    shell = EmtkShellApp(CATALOG, loader=lambda plugin_id: ImApp(lambda: None))
    driver = RealisticDriver(shell, size, real_painter=False)
    driver.frame(3)
    return shell, driver


def _open_tools(shell, driver):
    for plugin_id in ("setup", "filetools", "games"):
        shell.open_plugin(plugin_id)
        driver.frame(2)
    for _ in range(200):
        if all(h.build is None for h in shell.hosted.values()):
            break
        driver.frame(1)
    driver.frame(3)


def _inside(frame, bounds) -> bool:
    x, y, w, h = frame
    bx, by, bw, bh = bounds
    return x >= bx - 0.5 and y >= by - 0.5 and x + w <= bx + bw + 0.5 and y + h <= by + bh + 0.5


def _float_all(shell, driver):
    """Float the three tools, one asked for over the Tools dock, one past the window's edge."""
    boxes = [(20.0, 200.0, 460.0, 320.0), (700.0, 300.0, 460.0, 320.0), (1300.0, 800.0, 460.0, 320.0)]
    for key, box in zip(TOOLS, boxes):
        shell.docks.undock(key, box)
    driver.frame(3)


def _text(driver, label):
    """The drawn rectangle of *label* (a menu row is drawn indented, so compared stripped)."""
    hits = [t[:4] for t in driver.painter.texts if t[5].strip() == label]
    assert hits, f"{label!r} was not drawn"
    return hits[-1]


def _title(shell, key):
    x, y, w, _h = shell.docks.window(key).frame
    return (x + w / 2.0, y + shell.docks._title_h / 2.0)


def test_floated_tools_stay_in_the_workspace_and_reachable_after_clicking_the_window():
    shell, driver = _shell()
    _open_tools(shell, driver)
    _float_all(shell, driver)
    docks = shell.docks
    assert docks.workspace == "center"
    bounds = docks.floating_bounds()
    tools_dock = docks.window("tools").frame
    # A click on the main window's background (the Tools dock) ...
    driver.click((tools_dock[0] + 60.0, tools_dock[1] + 300.0))
    driver.frame(3)
    for key in TOOLS:
        frame = docks.window(key).frame
        assert frame is not None and docks.is_shown(key), key
        assert _inside(frame, bounds), f"{key} left the workspace: {frame} / {bounds}"
        assert frame[0] >= tools_dock[0] + tools_dock[2], f"{key} covers the Tools dock"
    # ... and each one comes to the front with a press on its title bar.
    for key in TOOLS:
        driver.click(_title(shell, key))
        driver.frame(2)
        assert docks.floating()[-1] == key
    driver.screenshot(SHOTS / "emtk_shell_workspace_floated.png")


def test_a_title_dragged_off_the_window_keeps_the_tool_in_the_workspace():
    shell, driver = _shell()
    _open_tools(shell, driver)
    _float_all(shell, driver)
    docks = shell.docks
    driver.drag(_title(shell, TOOLS[0]), (5.0, 880.0))
    driver.frame(3)
    assert docks.region_of(TOOLS[0]) is None
    assert _inside(docks.window(TOOLS[0]).frame, docks.floating_bounds())


def test_resizing_the_main_window_clamps_the_tools_back_in():
    shell, driver = _shell()
    _open_tools(shell, driver)
    _float_all(shell, driver)
    driver.resize((1000, 700), frames=4)
    bounds = shell.docks.floating_bounds()
    for key in TOOLS:
        assert _inside(shell.docks.window(key).frame, bounds), key


def _run_view(shell, key):
    action = next(a for _menu, actions in shell.session_menus() for a in actions if a.key == key)
    assert action.enabled()
    action.run()


def test_tile_cascade_and_tabbed_from_the_view_menu():
    shell, driver = _shell()
    _open_tools(shell, driver)
    docks = shell.docks
    docks.hide("start")
    _run_view(shell, "tile_windows")
    driver.frame(3)
    frames = [docks.window(k).frame for k in TOOLS]
    assert all(f is not None for f in frames) and len({tuple(f) for f in frames}) == 3
    driver.screenshot(SHOTS / "emtk_shell_workspace_tiled.png")
    _run_view(shell, "cascade_windows")
    driver.frame(3)
    ys = [docks.window(k).frame[1] for k in TOOLS]
    assert ys == sorted(ys) and len(set(ys)) == 3 and docks.floating()[-1] == TOOLS[-1]
    _run_view(shell, "tab_windows")
    driver.frame(3)
    assert set(TOOLS) <= set(docks.docked("center")) and not docks.floating()


def test_the_workspace_tool_bar_and_its_window_list():
    shell, driver = _shell()
    _open_tools(shell, driver)
    docks = shell.docks
    driver.click(docks._workspace_buttons["tile"])
    driver.frame(2)
    assert all(docks.region_of(k) is None for k in TOOLS)
    docks.minimize("plugin.games")
    driver.frame(2)
    driver.click(docks._workspace_buttons["windows"])
    driver.frame(2)
    driver.click(_text(driver, "Games (minimized)"))
    driver.frame(2)
    assert not docks.window("plugin.games").minimized and docks.floating()[-1] == "plugin.games"
    # The same list in the View menu.
    labels = {a.label for a in shell.workspace_actions()}
    assert {"Settings", "File tools", "Games"} <= labels


def test_right_click_on_the_empty_workspace_offers_its_commands():
    shell, driver = _shell()
    _open_tools(shell, driver)
    shell.docks.tile_workspace()
    driver.frame(2)
    x, y, w, h = shell.docks.region_boxes["center"]
    driver.click((x + 40.0, y + 6.0), button=RIGHT_BUTTON)  # its tool bar
    driver.frame(2)
    assert len([t for t in driver.painter.texts if t[5].strip() == "Cascade"]) >= 2


def test_ctrl_tab_cycles_the_tools_even_while_one_has_the_keys():
    shell, driver = _shell()
    _open_tools(shell, driver)
    _float_all(shell, driver)
    docks = shell.docks
    driver.click(_title(shell, TOOLS[0]))
    driver.frame(2)
    seen = []
    for _ in range(4):
        driver.press(KEY_TAB, CONTROL_MODIFIER)
        driver.frame(2)
        seen.append(docks.focused)
    assert set(TOOLS) <= set(seen)
    assert docks.floating()[-1] == seen[-1]


def test_the_workspace_cannot_be_closed():
    shell, driver = _shell()
    _open_tools(shell, driver)
    docks = shell.docks
    docks.close_panels()
    driver.frame(4)
    assert "center" in docks.region_boxes and docks.workspace == "center"
    assert "Workspace" in {t[5].strip() for t in driver.painter.texts}
    toggles = [a for _m, actions in shell.session_menus() for a in actions if a.key.startswith("dock.")]
    assert all("workspace" not in a.key and a.label != "Workspace" for a in toggles)


def test_the_arrangement_and_the_open_tools_survive_a_restart():
    shell, driver = _shell()
    _open_tools(shell, driver)
    shell.docks.tile_workspace()
    shell.docks.minimize("plugin.filetools")
    driver.frame(3)
    layout, settings = shell.docks.state(), shell.export_settings()
    boxes = {k: shell.docks.window(k).box for k in TOOLS}
    shell.close()

    again, driver = _shell()
    again.docks.restore(layout)
    again.restore_settings(settings)
    for _ in range(200):
        if again.hosted and all(h.build is None for h in again.hosted.values()):
            break
        driver.frame(1)
    driver.frame(3)
    assert set(again.hosted) == {"setup", "filetools", "games"}
    assert again.docks.window("plugin.filetools").minimized
    for key in TOOLS:
        assert again.docks.window(key).box == pytest.approx(boxes[key], abs=0.01)
    driver.screenshot(SHOTS / "emtk_shell_workspace_restored.png")


def test_a_help_link_opens_the_help_browser_in_the_workspace_not_a_second_process(monkeypatch):
    import subprocess

    from chisurf.emtk import code_links

    spawned = []
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: spawned.append(a))
    shell, driver = _shell()
    shown = []
    assert code_links.host_in_open_shell("help", lambda: shown.append(True))
    for _ in range(200):
        if all(h.build is None for h in shell.hosted.values()):
            break
        driver.frame(1)
    driver.frame(2)
    assert shown == [True] and not spawned
    assert shell.docks.region_of("plugin.help") == "center"
    shell.close()
    assert not code_links.host_in_open_shell("help"), "no shell, no hosting: the caller goes on"


def test_the_workspace_speaks_german():
    shell, driver = _shell(language="de")
    _open_tools(shell, driver)
    texts = {t[5].strip() for t in driver.painter.texts}
    assert {"Arbeitsbereich", "Kacheln", "Kaskadieren", "Als Tabs", "Fenster"} <= texts
    labels = {a.label for a in shell.workspace_actions()}
    assert "Nächstes Fenster" in labels
