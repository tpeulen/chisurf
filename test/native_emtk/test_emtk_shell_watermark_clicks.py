"""The workspace watermark takes no press meant for a tool drawn over it.

The watermark (system info, top right of the workspace) folds on a click. Its hit-test
ran before the tools' and used a rectangle kept from the last frame the workspace was
shown, so with a tool tabbed over the workspace every press in that corner folded a hidden
watermark instead -- a help window's filter row did not take a click (input trace,
2026-10-19).
"""

from __future__ import annotations

import pytest
from emtk import i18n as toolkit_i18n
from emtk.app import ImApp
from emtk.events import LEFT_BUTTON
from emtk.testing_realistic import RealisticDriver

from chisurf.emtk.main_app import EmtkShellApp

CATALOG = {"probe": {"display_name": "Tools:Views:Probe", "entrypoints": {"emtk": "x:y"}}}


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    before = toolkit_i18n.get_locale()
    yield
    toolkit_i18n.set_locale(before)


def test_a_press_on_a_tool_over_the_watermark_reaches_the_tool():
    from chisurf.emtk import i18n

    i18n.install("en")
    presses = []

    class Probe(ImApp):
        def pointer_press(self, x, y, button, modifiers=0, clicks=1):
            presses.append((x, y))
            super().pointer_press(x, y, button, modifiers, clicks)

    shell = EmtkShellApp(CATALOG, loader=lambda plugin_id: Probe(lambda: None))
    driver = RealisticDriver(shell, (1440, 900), real_painter=False)
    try:
        driver.frame(3)
        hosted = shell.open_plugin("probe", new=True)
        for _ in range(200):
            if hosted.build is None:
                break
            driver.frame(1)
        driver.frame(3)
        # The watermark's rectangle as the workspace last drew it, under the tool now.
        bx, by, bw, bh = hosted.box
        shell._watermark_last = None
        shell.item_rects["system_info"] = (bx + bw - 300.0, by, 300.0, 120.0)
        folded = getattr(shell, "_watermark_folded", False)
        x, y = bx + bw - 150.0, by + 60.0
        shell.pointer_press(x, y, LEFT_BUTTON)
        shell.pointer_release(x, y, LEFT_BUTTON)
        assert presses, "the press reached the tool"
        assert getattr(shell, "_watermark_folded", False) == folded, "the hidden watermark did not fold"
    finally:
        shell.close()
