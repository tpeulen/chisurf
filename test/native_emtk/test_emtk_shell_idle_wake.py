"""An idle shell sleeps: nothing asks for frames while the user does nothing.

Two wake-ups kept the shell redrawing for good, and the whole window with it (the main thread
~80 % busy after a burst search, every frame 30-90 ms): the watermark's once-a-second refresh
asked for a frame every 50 ms while a tool covered the watermark (its sample went stale and
never refreshed), and the Console, given no frame callback, took itself for a manual embedding
and asked for one every 0.1 s.
"""

from __future__ import annotations

import pytest
from emtk import i18n as toolkit_i18n
from emtk.app import ImApp, next_frame_in
from emtk.testing_realistic import RealisticDriver

from chisurf.emtk.main_app import EmtkShellApp

CATALOG = {"probe": {"display_name": "Tools:Views:Probe", "entrypoints": {"emtk": "x:y"}}}


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    before = toolkit_i18n.get_locale()
    yield
    toolkit_i18n.set_locale(before)


class Quiet(ImApp):
    """A tool with nothing to do."""

    def __init__(self):
        super().__init__(lambda: None)


def _shell():
    from chisurf.emtk import i18n

    i18n.install("en")
    shell = EmtkShellApp(CATALOG, loader=lambda plugin_id: Quiet())
    return shell, RealisticDriver(shell, (1200, 800), real_painter=False)


def test_the_console_has_a_frame_callback_and_does_not_poll():
    shell, driver = _shell()
    try:
        driver.frame(3)
        assert shell.console_terminal._frame_request_callback is not None
        assert shell.console_terminal.next_frame_in() is None
    finally:
        shell.close()


def test_a_tool_over_the_watermark_lets_the_shell_sleep():
    shell, driver = _shell()
    try:
        driver.frame(2)
        hosted = shell.open_plugin("probe", new=True)
        for _ in range(200):
            if hosted.build is None:
                break
            driver.frame(1)
        shell.docks.focus(hosted.key)
        driver.frame(5)
        assert not shell._watermark_drawn, "the tool covers the workspace and its watermark"
        assert not shell.animating()
        delay = next_frame_in(shell)
        assert delay is None or delay > 1.0, f"an idle shell woke again after {delay} s"
    finally:
        shell.close()


def test_the_watermark_refreshes_once_a_second_while_shown():
    shell, driver = _shell()
    try:
        driver.frame(5)
        if not shell._watermark_drawn:
            pytest.skip("the start layout does not show the workspace watermark")
        delay = next_frame_in(shell)
        assert delay is not None and 0.05 <= delay <= 1.0
    finally:
        shell.close()
