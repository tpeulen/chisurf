"""The emtk main surface, the default window (``python -m chisurf``): menus, hosting, input routing, close."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from emtk import im
from emtk.app import ImApp
from emtk.testing import Driver

from chisurf.emtk.main_app import PLUGIN_KEY, EmtkShellApp, menu_entries

CATALOG = {
    "fcs": {"display_name": "Spectroscopy:Correlation:FCS", "entrypoints": {"emtk": "x:y"}},
    "pch": {"display_name": "Spectroscopy:Correlation:PCH", "entrypoints": {"emtk": "x:y"}},
    "about": {"display_name": "Help:About", "entrypoints": {"emtk": "x:y"}},
    "hidden": {
        "display_name": "Tools:Hidden",
        "entrypoints": {"emtk": "x:y"},
        "menu_hidden": True,
    },
    "qt_only": {"display_name": "Tools:Qt", "entrypoints": {"gui": "x:y"}},
    "action": {"display_name": "Setup:Switch", "entrypoints": {"action": "x:y"}},
}


class _Probe(ImApp):
    """A child app with one button, recording what reaches it."""

    def __init__(self) -> None:
        self.pressed = 0
        self.keys: list[str] = []
        self.closed = False
        self.item_rects: dict = {}
        super().__init__(self.gui)

    def gui(self) -> None:
        im.set_next_window_pos((0.0, 0.0), im.Cond.ALWAYS)
        im.set_next_window_size(im.get_main_viewport().size, im.Cond.ALWAYS)
        if im.begin("probe", flags=im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE):
            if im.button("Ping"):
                self.pressed += 1
            self.item_rects["ping"] = im.get_item_rect()
        im.end()

    def key(self, key, text="", modifiers=0):
        self.keys.append(text)
        return super().key(key, text, modifiers)

    def close(self) -> None:
        self.closed = True


def _settle(driver: Driver, shell: EmtkShellApp, timeout: float = 60.0) -> None:
    """Draw until every plugin build has landed."""
    end = time.monotonic() + timeout
    while any(h.build is not None for h in shell.hosted.values()):
        assert time.monotonic() < end, "a plugin build did not finish"
        driver.frame(1)
        time.sleep(0.02)
    driver.frame(2)


def test_menu_entries_follow_the_manifest_menu_contract():
    entries = menu_entries(CATALOG)
    # The command plugin (an ``action`` entrypoint) is offered; the Qt-only one is not.
    assert [e.plugin_id for e in entries] == ["about", "action", "fcs", "pch"]
    assert [e.action for e in entries] == [False, True, False, False]
    fcs = entries[2]
    assert (fcs.menu, fcs.group, fcs.label) == ("Spectroscopy", "Correlation", "FCS")


def test_shipped_menus_offer_every_visible_native_plugin():
    from chisurf.emtk.plugins import manifests

    catalog = manifests()
    expected = {
        key
        for key, data in catalog.items()
        if (data.get("entrypoints", {}).get("emtk") or data.get("entrypoints", {}).get("action"))
        and not data.get("menu_hidden")
    }
    assert {e.plugin_id for e in menu_entries(catalog)} == expected
    assert len(expected) > 20


def test_a_hosted_plugin_gets_its_clicks_and_keys_and_closes_with_its_window():
    probes: dict[str, _Probe] = {}

    def loader(plugin_id):
        probes[plugin_id] = _Probe()
        return probes[plugin_id]

    shell = EmtkShellApp(CATALOG, loader=loader)
    driver = Driver(shell, size=(1100, 700))
    driver.frame(2)
    driver.click("tools.fcs")
    _settle(driver, shell)
    probe = probes["fcs"]
    box = shell.hosted["fcs"].box
    assert box is not None and box[2] > 200 and box[3] > 100
    px, py, pw, ph = probe.item_rects["ping"]
    driver.click((box[0] + px + pw / 2, box[1] + py + ph / 2))
    driver.frame(2)
    assert probe.pressed == 1, "the click on the hosted plugin's button reached it"
    driver.type("ab")
    assert "".join(probe.keys).endswith("ab"), "keys go to the plugin pressed last"
    # A click on the shell's own Tools panel takes the focus away from the plugin.
    driver.click("tools.filter")
    count = len(probe.keys)
    driver.type("x")
    assert len(probe.keys) == count
    # Reopening focuses the same window rather than making a second app.
    shell.open_plugin("fcs")
    assert list(probes) == ["fcs"]
    assert shell.export_settings()["open"] == ["fcs"]
    shell.docks.hide(PLUGIN_KEY + "fcs")
    driver.frame(2)
    assert probe.closed and "fcs" not in shell.hosted
    assert shell.docks.window(PLUGIN_KEY + "fcs") is None
    shell.close()


def test_a_failing_plugin_shows_its_error_in_its_window():
    def loader(plugin_id):
        raise RuntimeError("no device")

    shell = EmtkShellApp(CATALOG, loader=loader)
    driver = Driver(shell, size=(1100, 700))
    shell.open_plugin("pch")
    _settle(driver, shell)
    assert "no device" in shell.hosted["pch"].error
    assert any("no device" in text for text in driver.painter.strings)
    shell.close()


def test_restore_reopens_the_plugins_that_were_open():
    shell = EmtkShellApp(CATALOG, loader=lambda plugin_id: _Probe())
    shell.restore_settings({"open": ["pch", "gone", "about"]})
    assert sorted(shell.hosted) == ["about", "pch"]
    shell.close()


def test_real_plugins_render_inside_the_shell():
    """The shipped About and Calculators apps, hosted as docks; the PNG is for review."""
    shell = EmtkShellApp()
    driver = Driver(shell, size=(1400, 900))
    driver.frame(2)
    # The Tools tree puts Help last, below the dock's fold: find it with the filter, as a user does.
    shell.filter = "about"
    driver.frame(2)
    driver.click("tools.about")
    shell.open_plugin("calculators")
    _settle(driver, shell, timeout=120.0)
    for plugin_id in ("about", "calculators"):
        hosted = shell.hosted[plugin_id]
        assert hosted.app is not None, hosted.error
    # The calculators hub is the active tab: its own controls are drawn into its dock.
    assert "FRET line" in driver.painter.strings
    output = Path(os.environ.get("CHISURF_NATIVE_SCREENSHOTS", "/private/tmp/chisurf-native-gpu"))
    output.mkdir(parents=True, exist_ok=True)
    driver.screenshot(output / "emtk_shell.png")
    shell.close()


def test_the_shell_module_does_not_import_qt():
    code = (
        "import sys, chisurf.emtk.main_app as m; m.EmtkShellApp(); "
        "bad = [k for k in sys.modules if k.split('.')[0] in ('PyQt5', 'PyQt6', 'PySide2', "
        "'PySide6', 'qtpy')]; print(bad); sys.exit(1 if bad else 0)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=300
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "argv", [["--screenshot", "SHOT"], ["--emtk-shell", "--screenshot", "SHOT"]]
)
def test_python_m_chisurf_opens_the_emtk_surface(argv, tmp_path):
    """``python -m chisurf`` runs the emtk host, not the Qt application; ``--emtk-shell`` is accepted."""
    pytest.importorskip("wgpu")
    pytest.importorskip("rendercanvas")
    shot = tmp_path / "shell.png"
    argv = [str(shot) if arg == "SHOT" else arg for arg in argv]
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    result = subprocess.run(
        [sys.executable, "-m", "chisurf", *argv],
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    if result.returncode != 0 and "adapter" in (result.stderr or "").lower():
        pytest.skip("no GPU adapter for the offscreen canvas")
    assert result.returncode == 0, result.stderr[-2000:]
    assert shot.is_file() and shot.stat().st_size > 1000


class _Opened(Exception):
    """Raised by the stand-ins below to report which window ``chisurf.__main__.main`` opened."""


def test_qt_flag_opens_the_qt_window_kept_for_parity(monkeypatch):
    """``--qt`` opens the Qt main window, the reference the emtk window is measured against."""
    import chisurf.__main__ as entry
    import chisurf.emtk.main_app as main_app

    def emtk(argv):
        raise _Opened("emtk")

    class _App:
        def exec(self):
            raise _Opened("qt " + " ".join(sys.argv[1:]))

    monkeypatch.setattr(main_app, "main", emtk)
    gui = pytest.importorskip("chisurf.gui")
    monkeypatch.setattr(gui, "get_app", lambda: _App())
    monkeypatch.setattr(sys, "argv", ["chisurf", "--qt", "project.cs.pto"])
    with pytest.raises(_Opened, match=r"^qt project\.cs\.pto$"):
        entry.main()
    monkeypatch.setattr(sys, "argv", ["chisurf", "project.cs.pto"])
    with pytest.raises(_Opened, match="^emtk$"):
        entry.main()
