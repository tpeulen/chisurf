"""The browser loads a burst run inside a .pto container (not a file on disk; the model opens it)."""

from __future__ import annotations

from chisurf.plugins.burst.burst_browser.gui.controller import BurstBrowserController


class _Model:
    _observers: list = []


def test_a_container_run_starts_a_load_and_a_missing_path_does_not(tmp_path):
    controller = BurstBrowserController(_Model())
    try:
        controller.load(tmp_path / "missing" / "bursts")
        assert controller.status.startswith("Input does not exist") and not controller.running
        controller.load(tmp_path / "m000.pto" / "sliding_window_All 0.1500#60")
        assert controller.running and controller.status.startswith("Loading bursts")
    finally:
        controller.close()
