"""The emtk shell's ribbon, plugin menus and Tools tree (W9 S5) against the Qt ribbon.

The before-half is ``shell_s5_qt_inventory.json`` (``capture_shell_s5_qt_before.py``): every Qt
ribbon tab, group and button in order, with its tooltip and whether it has an icon, and the
controls in the ribbon's corner. The emtk ribbon is built from the same manifests through the
same placement rules (:mod:`chisurf.core.plugin.ribbon_layout`), so the comparison is tab for
tab and group for group. Buttons are pressed the way a user presses them, through
:class:`emtk.testing.Driver`.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import pytest
from emtk.testing import Driver

from chisurf.emtk.main_app import EmtkShellApp

SHOTS = Path(os.environ.get("CHISURF_NATIVE_SCREENSHOTS", "/private/tmp/chisurf-native-gpu"))
BEFORE = json.loads(Path(__file__).with_name("shell_s5_qt_inventory.json").read_text("utf-8"))

#: Qt ribbon buttons the emtk shell does not have yet; each is an open item of the ledger
#: (``okf/subsystems/qt-retirement.md``). This list only shrinks.
KNOWN_GAPS = {
    "loadfit": "fit import of a .fit.json into the session: no Qt-free service yet (S3 gap)",
    "currentfit": "fit export is Qt-bound in core_fit.save_fit (S3 gap)",
    "allfits": "the same export for every fit (S3 gap)",
}
#: Qt ribbon controls replaced on purpose, and by what.
DELIBERATE = {
    "menuswitch": "switches the Qt shell between ribbon and menu bar; the emtk shell has both, "
    "and its ▴ toggle folds the ribbon",
    "unpinribbon(enableauto-fold)": "the Qt pin and auto-fold are one fold toggle (ribbon.fold): "
    "a folded ribbon shows its band for one pick after a tab click",
}
#: The Qt ribbon's corner controls, by tooltip or class, and the emtk control that replaces each.
CORNER = {
    "Collapse Ribbon": "ribbon.fold",
    "Unpin ribbon (enable auto-fold)": "ribbon.fold",
    "Open Help Plugin": "ribbon.help",
    "QLineEdit": "ribbon.search",
    "LanguageFlagSwitcher": "ribbon.language",
    "QWidget": None,  # the search field's frame
}


def _norm(text: str) -> str:
    text = re.sub(r"[⚠⛔️]", "", str(text).replace("&", ""))
    return re.sub(r"\s+|\.\.\.|…", "", text).lower()


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Recent projects and the language setting in ``tmp_path``: the tests never touch real settings."""
    import chisurf
    from chisurf.core.project import recent
    from chisurf.core.settings import settings_utils

    monkeypatch.setattr(recent, "recent_projects_file", lambda: tmp_path / "recent_projects.json")
    monkeypatch.setattr(chisurf, "working_path", tmp_path, raising=False)
    saved: list[str] = []
    monkeypatch.setattr(settings_utils, "set_language", lambda code: saved.append(code) or True)
    from chisurf.emtk.i18n import install, set_locale

    install("en")
    yield saved
    set_locale("en")


@pytest.fixture
def shell(isolated):
    """The shell over the shipped manifests; plugins are recorded, not built."""
    opened: list[str] = []

    def loader(plugin_id):
        opened.append(plugin_id)

    app = EmtkShellApp(loader=loader, console_history=False, console_session_file=False)
    app.opened = opened
    yield app
    app.close()


def _built(shell) -> dict[str, dict[str, list[str]]]:
    return {
        tab.title: {group.title: [button.label for button in group.buttons] for group in tab.groups}
        for tab in shell.ribbon.tabs()
    }


def test_parity_with_the_qt_ribbon(shell):
    """Every Qt tab, group and button, in order, is in the emtk ribbon -- or a listed gap."""
    built = _built(shell)
    qt_tabs = list(BEFORE["tabs"])
    assert list(built) == qt_tabs
    missing, deliberate = [], []
    for tab, groups in BEFORE["tabs"].items():
        assert list(built[tab]) == list(groups), (tab, list(built[tab]))
        for group, buttons in groups.items():
            ours = [_norm(label) for label in built[tab][group]]
            qt = [_norm(button["text"]) for button in buttons]
            for name in qt:
                if name in ours:
                    continue
                (deliberate if name in DELIBERATE else missing).append(name)
            # The ones present come in the Qt order.
            present = [name for name in qt if name in ours]
            assert [name for name in ours if name in present] == present, (tab, group)
    assert sorted(missing) == sorted(KNOWN_GAPS), "update KNOWN_GAPS: it only shrinks"
    assert set(deliberate) <= set(DELIBERATE)


def test_every_plugin_button_and_menu_row_carries_its_manifest_icon(shell):
    for tab in shell.ribbon.tabs():
        for group in tab.groups:
            for button in group.buttons:
                assert button.icon, (tab.title, group.title, button.label)
    for menu, groups in shell.menus.items():
        for caption, entries in groups.items():
            for entry in entries:
                assert entry.icon, (menu, caption, entry.label)


def test_the_corner_controls_have_their_emtk_counterparts(shell):
    driver = Driver(shell, size=(1440, 900))
    driver.frame(2)
    for control in BEFORE["right"]:
        key = CORNER.get(control["tooltip"]) or CORNER.get(control["class"], "missing")
        if key is None:
            continue
        assert key in driver.ids(), control


def test_pressing_a_ribbon_button_opens_its_plugin(shell):
    driver = Driver(shell, size=(1440, 900))
    driver.frame(2)
    assert shell.ribbon.ribbon.current == "Spectroscopy"
    driver.click("ribbon.button.plugin.fcs_toolbox")
    driver.frame(2)
    assert "fcs_toolbox" in shell.hosted
    driver.click("ribbon.tab.Structure")
    driver.click("ribbon.button.plugin.chimol")
    driver.frame(2)
    assert "chimol" in shell.hosted


def test_a_session_button_runs_its_action(shell, monkeypatch):
    calls = []
    monkeypatch.setattr(shell.docks, "reset", lambda: calls.append("reset"))
    driver = Driver(shell, size=(1440, 900))
    driver.frame(2)
    driver.click("ribbon.tab.Main")
    driver.click("ribbon.button.action.reset_layout")
    assert calls == ["reset"]
    # Without a session the project buttons are there, and disabled.
    driver.click("ribbon.tab.File")
    driver.click("ribbon.button.action.save_project")
    assert shell.project.status == ""


def test_narrow_widths_keep_every_plugin_reachable(shell):
    """Groups collapse from the right, then overflow; a collapsed group's menu opens its tool."""
    driver = Driver(shell, size=(560, 800))
    driver.frame(2)
    modes = shell.ribbon.ribbon.group_modes
    assert modes["Decay"] == "full" and modes["Imaging"] != "full", modes
    collapsed = next(group for group, mode in modes.items() if mode == "collapsed")
    driver.click(f"ribbon.group.Spectroscopy.{collapsed}")
    driver.frame()
    tab = next(t for t in shell.ribbon.tabs() if t.title == "Spectroscopy")
    group = next(g for g in tab.groups if g.title == collapsed)
    driver.click(group.buttons[0].label)
    driver.frame(2)
    assert group.buttons[0].key.removeprefix("plugin.") in shell.hosted
    driver.draw(size=(330, 800))
    assert "overflow" in shell.ribbon.ribbon.group_modes.values()
    assert "ribbon.overflow" in driver.ids()


def test_the_ribbon_search_finds_tools_of_every_tab(shell):
    driver = Driver(shell, size=(1440, 900))
    driver.frame(2)
    shell.ribbon.ribbon.query = "games"
    painter = driver.frame(2)
    assert "Games" in painter.strings
    driver.click("ribbon.button.plugin.games")
    driver.frame()
    assert "games" in shell.hosted


def test_the_tools_tree_follows_the_ribbon_and_filters(shell):
    from chisurf.emtk.shell_ribbon import plugin_tree

    menus = list(shell.menus)
    assert menus == ["File", "Spectroscopy", "Structure", "Tools", "Help"]
    assert list(shell.menus["Spectroscopy"]) == list(plugin_tree(shell.entries)["Spectroscopy"])
    hidden = {
        entry.plugin_id for groups in shell.menus.values() for e in groups.values() for entry in e
    }
    from chisurf.emtk.plugins import manifests

    assert not {pid for pid in hidden if manifests()[pid].get("menu_hidden")}
    driver = Driver(shell, size=(1440, 900))
    driver.frame(2)
    assert "tools.menu.Spectroscopy" in driver.ids()
    assert driver.rect("tools.alex_suite")[1] < driver.rect("tools.burst_analysis")[1]
    shell.filter = "burst"
    driver.frame(2)
    ids = driver.ids()
    assert "tools.burst_analysis" in ids and "tools.fcs_toolbox" not in ids
    driver.click("tools.burst_analysis")
    driver.frame()
    assert "burst_analysis" in shell.hosted


def test_the_language_button_switches_the_running_shell(shell, isolated):
    from emtk import i18n as toolkit_i18n

    driver = Driver(shell, size=(1440, 900))
    driver.frame(2)
    driver.click("ribbon.language")
    driver.frame()
    driver.click("Deutsch (de)")
    driver.frame(2)
    assert toolkit_i18n.get_locale().startswith("de")
    assert isolated == ["de"]
    strings = driver.frame(2).strings
    assert "Werkzeuge" in strings and "Datei" in strings


@pytest.mark.parametrize("language", ["en", "de"])
def test_screenshots_wide_and_narrow(shell, language):
    """The PNGs the ledger's S5 entry was judged on (read them)."""
    from chisurf.emtk.i18n import set_locale

    set_locale(language)
    SHOTS.mkdir(parents=True, exist_ok=True)
    driver = Driver(shell, size=(1440, 900))
    driver.frame(3)
    driver.screenshot(SHOTS / f"emtk_shell_ribbon_{language}_wide.png")
    driver.draw(size=(640, 760))
    driver.frame(2)
    driver.screenshot(SHOTS / f"emtk_shell_ribbon_{language}_narrow.png")
    collapsed = [g for g, m in shell.ribbon.ribbon.group_modes.items() if m == "collapsed"]
    assert collapsed
    driver.click(f"ribbon.group.Spectroscopy.{collapsed[0]}")
    driver.frame(2)
    driver.screenshot(SHOTS / f"emtk_shell_ribbon_{language}_narrow_menu.png")
    driver.escape()
    driver.draw(size=(1440, 900))
    driver.click("menu." + ("Werkzeuge" if language == "de" else "Tools"))
    driver.frame(2)
    driver.screenshot(SHOTS / f"emtk_shell_ribbon_{language}_menu.png")
    time.sleep(0)
