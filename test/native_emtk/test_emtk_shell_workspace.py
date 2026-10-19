"""The shell's Workspace is where the fits live; every tool is a dock.

Owner's rule (2026-10-13): "workspace is simply where the fits live, the plugins, ie, the tools go
separate all are in docks." So the workspace's children are the fit windows (and Start, which
fills it while it has no fit); Tile, Cascade, Tabbed, Ctrl+Tab and the window list act on them
only. A tool, the help browser and the code editor open as docks -- tabbed right of the workspace
by default, dockable anywhere else, floating over the whole window -- and never become workspace
windows. emtk enforces the rule (``DockWindow.workspace``, ``tests/test_docking_workspace.py``
there); this is the shell using it, driven as a user drives it with
:class:`emtk.testing_realistic.RealisticDriver` -- real presses, drags and keys -- with probe
tools standing in for plugins and stand-in fit windows added the way the data docks add them
(one test opens a real fit through a real session).
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from emtk import i18n as toolkit_i18n
from emtk.app import ImApp
from emtk.events import CONTROL_MODIFIER, RIGHT_BUTTON
from emtk.keys import KEY_TAB
from emtk.testing_realistic import RealisticDriver

from chisurf.emtk.main_app import TOOL_REGION, EmtkShellApp

SHOTS = Path(os.environ.get("CHISURF_NATIVE_SCREENSHOTS", "/private/tmp/chisurf-native-gpu"))
REPO = Path(__file__).resolve().parents[2]
KRISTINE = REPO / "test" / "data" / "fcs" / "kristine" / "Kristine_with_error.cor"
MODEL = "FCS (general: diffusion + bunching/anticorr)"
CATALOG = {
    "setup": {"display_name": "Setup:Settings", "entrypoints": {"emtk": "x:y"}},
    "filetools": {"display_name": "File:Data:File tools", "entrypoints": {"emtk": "x:y"}},
    "games": {"display_name": "Tools:System:Games", "entrypoints": {"emtk": "x:y"}},
    "help": {"display_name": "Help:Documentation", "entrypoints": {"emtk": "x:y"}},
}
TOOLS = ("plugin.setup", "plugin.filetools", "plugin.games")
FITS = ("fit.one", "fit.two", "fit.three")


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


def _open_fits(shell, driver):
    """Stand-in fit windows, added as :meth:`chisurf.emtk.fit_docks.DataDocks.open_window` adds them."""
    for key in FITS:
        shell.docks.add_window(
            key,
            key.split(".")[1].title(),
            lambda box: None,
            dock="center",
            scrollable=False,
            padding=0.0,
            min_size=(240.0, 160.0),
            core=True,
            workspace=True,
        )
    driver.frame(3)


def _inside(frame, bounds) -> bool:
    x, y, w, h = frame
    bx, by, bw, bh = bounds
    return x >= bx - 0.5 and y >= by - 0.5 and x + w <= bx + bw + 0.5 and y + h <= by + bh + 0.5


def _float_fits(shell, driver):
    """Float the three fits, one asked for over the Tools dock, one past the window's edge."""
    boxes = [(20.0, 150.0, 460.0, 320.0), (700.0, 350.0, 460.0, 320.0), (1300.0, 800.0, 460.0, 320.0)]
    for key, box in zip(FITS, boxes):
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


def _run_view(shell, key):
    action = next(a for _menu, actions in shell.session_menus() for a in actions if a.key == key)
    assert action.enabled()
    action.run()


def test_tools_open_as_docks_and_fits_in_the_workspace():
    shell, driver = _shell()
    _open_tools(shell, driver)
    _open_fits(shell, driver)
    docks = shell.docks
    assert docks.region_of("workspace") == "center"
    assert not docks.window("workspace").closable and docks.window("workspace").core
    for key in TOOLS:
        assert docks.region_of(key) == TOOL_REGION, key
        assert not docks.in_workspace(key)
    assert set(docks.workspace_children()) == {"start", *FITS}
    assert set(TOOLS) <= set(docks.docked("center"))
    assert "workspace" in docks.docked("center")
    driver.screenshot(SHOTS / "emtk_shell_workspace_docks.png")


def test_a_floated_tool_floats_as_a_dock_not_as_a_workspace_window():
    shell, driver = _shell()
    _open_tools(shell, driver)
    docks = shell.docks
    docks.undock(TOOLS[0], (20.0, 200.0, 460.0, 320.0))
    driver.frame(3)
    frame = docks.window(TOOLS[0]).frame
    assert frame[0] < docks.floating_bounds()[0], "it may float over the Tools dock"
    assert TOOLS[0] not in docks.workspace_children()
    assert not docks.in_workspace(TOOLS[0])
    # Dragged onto the workspace's centre pad, it stays a dock and not a workspace child.
    x, y, w, h = docks.region_boxes["center"]
    driver.drag(_title(shell, TOOLS[0]), (x + w / 2.0, y + h / 2.0))
    driver.frame(3)
    assert not docks.in_workspace(TOOLS[0])
    # Back in a dock region it is a tab there.
    left = docks.region_boxes["left"]
    driver.drag(_title(shell, TOOLS[0]), (left[0] + left[2] / 2.0, left[1] + left[3] / 2.0))
    driver.frame(3)
    assert docks.region_of(TOOLS[0]) == "left"


def test_a_saved_layout_with_tools_in_the_workspace_puts_them_in_docks():
    """A layout from before the rule (tools docked in the workspace) reopens with them as docks."""
    shell, driver = _shell()
    _open_tools(shell, driver)
    state = shell.docks.state()
    for key in TOOLS:
        state["windows"][key]["dock"] = "center"
    state["regions"]["center"] = {"tabs": ["start", *TOOLS], "selected": TOOLS[0]}
    settings = shell.export_settings()
    shell.close()
    again, driver = _shell()
    again.docks.restore(state)
    again.restore_settings(settings)
    for _ in range(200):
        if again.hosted and all(h.build is None for h in again.hosted.values()):
            break
        driver.frame(1)
    driver.frame(3)
    for key in TOOLS:
        assert again.docks.region_of(key) == TOOL_REGION, key
    assert again.docks.workspace_children() == ["start"]


def test_fits_stay_in_the_workspace_and_reachable_after_clicking_the_window():
    shell, driver = _shell()
    _open_fits(shell, driver)
    _float_fits(shell, driver)
    docks = shell.docks
    bounds = docks.floating_bounds()
    tools_dock = docks.window("tools").frame
    driver.click((tools_dock[0] + 60.0, tools_dock[1] + 300.0))
    driver.frame(3)
    for key in FITS:
        frame = docks.window(key).frame
        assert frame is not None and docks.is_shown(key), key
        # emtk keeps a floating window's *title bar* inside (emtk 4f154f8): one asked for past
        # the bottom edge may hang below it, as a desktop window does, and is still grabbed.
        title = (frame[0], frame[1], frame[2], docks._title_h)
        assert _inside(title, bounds), f"{key} left the workspace: {frame} / {bounds}"
    for key in FITS:
        # The title's right end: the floats overlap, each one's right end is the part in view.
        x, y, w, _h = docks.window(key).frame
        driver.click((x + w - 40.0, y + docks._title_h / 2.0))
        driver.frame(2)
        assert docks.floating()[-1] == key
    driver.screenshot(SHOTS / "emtk_shell_workspace_floated.png")


def test_a_fit_dragged_off_the_window_stays_in_the_workspace_and_docks_nowhere_else():
    shell, driver = _shell()
    _open_fits(shell, driver)
    _float_fits(shell, driver)
    docks = shell.docks
    driver.drag(_title(shell, FITS[0]), (5.0, 880.0))
    driver.frame(3)
    assert docks.region_of(FITS[0]) is None
    assert _inside(docks.window(FITS[0]).frame, docks.floating_bounds())
    left = docks.region_boxes["left"]
    driver.drag(_title(shell, FITS[0]), (left[0] + left[2] / 2.0, left[1] + left[3] / 2.0))
    driver.frame(3)
    assert docks.region_of(FITS[0]) is None, "a fit is never a dock of the left column"


def test_resizing_the_main_window_clamps_the_fits_back_in():
    shell, driver = _shell()
    _open_fits(shell, driver)
    _float_fits(shell, driver)
    driver.resize((1000, 700), frames=4)
    bounds = shell.docks.floating_bounds()
    for key in FITS:
        assert _inside(shell.docks.window(key).frame, bounds), key


def test_tile_cascade_and_tabbed_arrange_the_fits_and_leave_the_tools_docked():
    shell, driver = _shell(size=(1920, 1080))  # room for three tiles beside the tool docks
    _open_tools(shell, driver)
    _open_fits(shell, driver)
    docks = shell.docks
    docks.hide("start")
    _run_view(shell, "tile_windows")
    driver.frame(3)
    frames = [docks.window(k).frame for k in FITS]
    assert all(f is not None for f in frames) and len({tuple(f) for f in frames}) == 3
    assert all(docks.region_of(k) == TOOL_REGION for k in TOOLS)
    driver.screenshot(SHOTS / "emtk_shell_workspace_tiled.png")
    _run_view(shell, "cascade_windows")
    driver.frame(3)
    ys = [docks.window(k).frame[1] for k in FITS]
    assert ys == sorted(ys) and len(set(ys)) == 3 and docks.floating()[-1] == FITS[-1]
    _run_view(shell, "tab_windows")
    driver.frame(3)
    assert set(FITS) <= set(shell.workspace_docks.docked("center")) and not shell.workspace_docks.floating()
    assert all(docks.region_of(k) == TOOL_REGION for k in TOOLS)


def test_the_workspace_tool_bar_and_its_window_list_name_the_fits_only():
    shell, driver = _shell(size=(1920, 1080))  # room for three tiles beside the tool docks
    _open_tools(shell, driver)
    _open_fits(shell, driver)
    docks = shell.docks
    driver.click(docks._workspace_buttons["tile"])
    driver.frame(2)
    assert all(docks.region_of(k) is None for k in FITS)
    docks.minimize("fit.three")
    driver.frame(2)
    driver.click(docks._workspace_buttons["windows"])
    driver.frame(2)
    driver.click(_text(driver, "Three (minimized)"))
    driver.frame(2)
    assert not docks.window("fit.three").minimized and docks.floating()[-1] == "fit.three"
    labels = {a.label for a in shell.workspace_actions()}
    assert {"One", "Two", "Three"} <= labels
    assert not {"Settings", "File tools", "Games"} & labels


def test_right_click_on_the_empty_workspace_offers_its_commands():
    shell, driver = _shell()
    _open_fits(shell, driver)
    shell.docks.tile_workspace()
    driver.frame(2)
    x, y, w, h = shell.workspace_docks.region_boxes["center"]
    driver.click((x + 40.0, y + 6.0), button=RIGHT_BUTTON)  # its tool bar
    driver.frame(2)
    assert len([t for t in driver.painter.texts if t[5].strip() == "Cascade"]) >= 2


def test_ctrl_tab_cycles_the_fits_even_while_a_tool_has_the_keys():
    shell, driver = _shell()
    _open_tools(shell, driver)
    _open_fits(shell, driver)
    _float_fits(shell, driver)
    docks = shell.docks
    docks.hide("start")
    driver.click(_title(shell, FITS[0]))
    driver.frame(2)
    seen = []
    for _ in range(4):
        driver.press(KEY_TAB, CONTROL_MODIFIER)
        driver.frame(2)
        seen.append(docks.focused)
    assert set(FITS) <= set(seen) and not set(TOOLS) & set(seen)
    assert docks.floating()[-1] == seen[-1]


def test_the_workspace_cannot_be_closed():
    shell, driver = _shell()
    _open_tools(shell, driver)
    docks = shell.docks
    docks.close_panels()
    driver.frame(4)
    assert "center" in docks.region_boxes and docks.window("workspace").visible and not docks.window("workspace").closable
    assert shell.workspace_docks.workspace == "center"
    assert "Workspace" in {t[5].strip() for t in driver.painter.texts}
    toggles = [a for _m, actions in shell.session_menus() for a in actions if a.key.startswith("dock.")]
    assert all("workspace" not in a.key and a.label != "Workspace" for a in toggles)


def test_the_arrangement_and_the_open_tools_survive_a_restart():
    shell, driver = _shell()
    _open_tools(shell, driver)
    _open_fits(shell, driver)
    shell.docks.tile_workspace()
    shell.docks.minimize("fit.two")
    driver.frame(3)
    layout, settings = shell.docks.state(), shell.export_settings()
    boxes = {k: shell.docks.window(k).box for k in FITS}
    shell.close()

    again, driver = _shell()
    again.docks.restore(layout)
    again.restore_settings(settings)
    _open_fits(again, driver)
    for _ in range(200):
        if again.hosted and all(h.build is None for h in again.hosted.values()):
            break
        driver.frame(1)
    driver.frame(3)
    assert set(again.hosted) == {"setup", "filetools", "games"}
    assert all(again.docks.region_of(k) == TOOL_REGION for k in TOOLS)
    assert again.docks.window("fit.two").minimized
    for key in FITS:
        assert again.docks.window(key).box == pytest.approx(boxes[key], abs=0.01)
    driver.screenshot(SHOTS / "emtk_shell_workspace_restored.png")


def test_a_help_link_opens_the_help_browser_as_a_dock_not_a_second_process(monkeypatch):
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
    assert shell.docks.region_of("plugin.help") == TOOL_REGION
    assert not shell.docks.in_workspace("plugin.help")
    shell.close()
    assert not code_links.host_in_open_shell("help"), "no shell, no hosting: the caller goes on"


def test_the_workspace_speaks_german():
    shell, driver = _shell(language="de")
    _open_fits(shell, driver)
    texts = {t[5].strip() for t in driver.painter.texts}
    assert {"Arbeitsbereich", "Kacheln", "Kaskadieren", "Als Tabs", "Fenster"} <= texts
    actions = {a.key: a for a in shell.workspace_actions()}
    assert actions["next_window"].label == "Nächstes Fenster"
    assert actions["tile_windows"].description == "Alle Anpassungsfenster nebeneinander anzeigen."


def test_a_real_fit_opens_in_the_workspace():
    """Through a real session: the data docks open a fit's window as a workspace document."""
    from emtk.testing import Driver

    from chisurf.emtk.fit_docks import DATASETS_KEY, READ_KEY
    from chisurf.emtk.session import start_session
    from chisurf.server.session import SessionState

    session = start_session(state=SessionState())
    shell = EmtkShellApp({}, loader=lambda plugin_id: None)
    shell.data.adopt(session)
    try:
        driver = Driver(shell, size=(1440, 900))
        driver.frame(2)
        data = shell.data

        def settle(predicate, what):
            end = time.monotonic() + 120.0
            while not predicate():
                assert time.monotonic() < end, f"timed out waiting for {what}: {data.status}"
                driver.frame(1)
                time.sleep(0.02)
            driver.frame(2)

        idle = lambda: not data.busy and not data._dirty  # noqa: E731
        shell.docks.focus(READ_KEY)
        driver.frame(2)
        data.read.experiment = "FCS"
        data.read.experiment_changed("FCS")
        data.read.setup = "Seidel Kristine"
        data.read.path = str(KRISTINE)
        driver.click("read.load")
        settle(lambda: idle() and len(data.datasets.datasets) > 1, "the dataset")
        shell.docks.focus(DATASETS_KEY)
        driver.frame(2)
        data.datasets.model = MODEL
        driver.click("datasets.add_fit")
        settle(lambda: idle() and data.windows, "the fit window")
        uid = data.current_uid
        key = shell.data.windows[uid].key
        assert shell.docks.in_workspace(key)
        assert key in shell.docks.workspace_children()
    finally:
        shell.close()
