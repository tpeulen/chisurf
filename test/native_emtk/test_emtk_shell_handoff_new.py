"""A hand-off can ask for a new window of the tool instead of the one open.

The deposit review's "Open in ndX" replaced whatever ndX was showing.
"""

from __future__ import annotations

import pytest
from emtk import i18n as toolkit_i18n
from emtk.app import ImApp
from emtk.testing_realistic import RealisticDriver

from chisurf.emtk.main_app import EmtkShellApp

CATALOG = {"ndxplorer": {
    "display_name": "Tools:Views:ndX", "entrypoints": {"emtk": "x:y"},
    "accepts": [{"name": "open_path", "required": ["path"],
                 "receive": "test.native_emtk.test_emtk_shell_handoff_new:receive"}]}}
RECEIVED: list = []


def receive(app, payload):
    RECEIVED.append((id(app), payload["path"]))


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    before = toolkit_i18n.get_locale()
    RECEIVED.clear()
    yield
    toolkit_i18n.set_locale(before)


def _settle(shell, driver):
    for _ in range(200):
        if all(h.build is None for h in shell.hosted.values()):
            break
        driver.frame(1)
    driver.frame(2)


@pytest.mark.parametrize("new, windows", [(False, 1), (True, 2)])
def test_a_hand_off_reuses_the_open_window_unless_it_asks_for_a_new_one(new, windows):
    from chisurf.emtk import i18n

    i18n.install("en")
    shell = EmtkShellApp(CATALOG, loader=lambda pid: ImApp(lambda: None))
    driver = RealisticDriver(shell, (1200, 800), real_painter=False)
    driver.frame(3)
    try:
        shell.hand_off("ndxplorer", "open_path", {"path": "a.pto"})
        _settle(shell, driver)
        shell.hand_off("ndxplorer", "open_path", {"path": "b.pto"}, new=new)
        _settle(shell, driver)
        assert len(shell.instances("ndxplorer")) == windows
        assert [p for _, p in RECEIVED] == ["a.pto", "b.pto"]
        assert (RECEIVED[0][0] != RECEIVED[1][0]) == new
    finally:
        shell.close()
