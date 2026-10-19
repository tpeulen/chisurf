"""A tool tabbed behind another still finishes its background work.

The shell draws only the tools in front, and a tool's code ran only while drawn: a file
opened in ndX #1 did not finish loading while ndX #2 was in front. A tool declaring
``poll()`` gets it on every frame it is not drawn, and keeps the shell awake while busy.
"""

from __future__ import annotations

import pytest
from emtk import i18n as toolkit_i18n
from emtk.app import ImApp
from emtk.testing_realistic import RealisticDriver

from chisurf.emtk.main_app import EmtkShellApp

CATALOG = {"probe": {"display_name": "Tools:Views:Probe", "entrypoints": {"emtk": "x:y"}}}


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    before = toolkit_i18n.get_locale()
    yield
    toolkit_i18n.set_locale(before)


class Worker(ImApp):
    """A tool with background work: busy until polled three times."""

    def __init__(self):
        super().__init__(lambda: None)
        self.polls = 0

    def poll(self):
        self.polls += 1

    def animating(self):
        return self.polls < 3 or super().animating()


def test_a_hidden_tool_is_polled_and_keeps_the_shell_awake_until_done():
    from chisurf.emtk import i18n

    i18n.install("en")
    shell = EmtkShellApp(CATALOG, loader=lambda plugin_id: Worker())
    driver = RealisticDriver(shell, (1200, 800), real_painter=False)
    try:
        driver.frame(2)
        first = shell.open_plugin("probe", new=True)
        second = shell.open_plugin("probe", new=True)
        for _ in range(200):
            if first.build is None and second.build is None:
                break
            driver.frame(1)
        shell.docks.focus(second.key)
        driver.frame(2)
        hidden = getattr(first.app, "_control", first.app)
        shown = getattr(second.app, "_control", second.app)
        assert first.key not in shell._drawn
        before, shown_before = hidden.polls, shown.polls
        assert shell.animating(), "a hidden tool still busy keeps the shell awake"
        driver.frame(3)
        assert hidden.polls >= before + 3
        assert shown.polls == shown_before, "the tool in front is drawn, not polled"
    finally:
        shell.close()
