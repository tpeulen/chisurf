"""The emtk ebFRET window, drawn headlessly and driven by clicks.

No Qt: the window is drawn into a ``PixelPainter`` and fed pointer events the
way ``emtk.qt_host`` feeds them. What is checked is what a screenshot cannot
promise -- that every declared control is on screen, that pressing it does what
the MATLAB callback did, and that the guided tour points at controls that exist.
"""

from __future__ import annotations

import json
import pathlib
import time

import pytest

emtk = pytest.importorskip("emtk")

from emtk.testing import PixelPainter, RecordingPainter  # noqa: E402

from chisurf.plugins.burst.burst_ebfret import demo  # noqa: E402
from chisurf.plugins.burst.burst_ebfret.api.client import EbfretClient  # noqa: E402
from chisurf.plugins.burst.burst_ebfret.gui import dialogs as dlg  # noqa: E402
from chisurf.plugins.burst.burst_ebfret.gui.app import App, EbfretGui  # noqa: E402

GUI_DIR = pathlib.Path(dlg.__file__).parent
W, H = 1200, 800


class Window:
    """An App with a frame/click helper."""

    def __init__(self, tmp_path):
        self.client = EbfretClient(seed=2)
        self.gui = EbfretGui(self.client, directory=str(tmp_path))
        self.app = App(self.gui)
        self.frame()

    def frame(self, n=1):
        for _ in range(n):
            self.gui._last_poll = 0.0
            # Recording, not rasterising: the layout and the input are what is
            # checked here, and a 1200x800 raster per frame costs a second.
            self.painter = RecordingPainter()
            self.app.draw(self.painter, 0, 0, W, H)

    def click(self, x, y, clicks=1):
        self.app.hover(x, y)
        self.app.press(x, y, 0, 0, W, H, 0, clicks)
        self.frame()
        self.app.release()
        self.frame()

    def click_item(self, name):
        x, y, w, h = self.gui.item_rects[name]
        self.click(x + min(6.0, w / 2), y + h / 2)

    def type(self, text, enter=True):
        for char in text:
            self.app.key(ord(char), char)
            self.frame()
        if enter:
            self.app.key(0x01000004, "\r")
            self.frame()

    def load_demo(self, tmp_path):
        path = demo.write_demo(tmp_path / "demo.dat", seed=4)
        self.gui._loaded([str(path)], 2)
        self.frame(2)


@pytest.fixture
def window(tmp_path):
    w = Window(tmp_path)
    yield w
    w.client.close()


def _names(sections):
    for section in sections:
        if section.get("sections"):
            yield from _names(section["sections"])
        elif section.get("type") == "button_row":
            yield from (b["action"] for b in section["buttons"])
        elif section.get("attr"):
            yield section["attr"] + (".slider" if section.get("style") == "slider" else "")


def test_every_declared_control_is_drawn(window, tmp_path):
    window.load_demo(tmp_path)
    spec = json.loads((GUI_DIR / "main.view.json").read_text())
    panels = [s for s in spec["sections"] if s["title"] not in ("Series List", "States Table")]
    for name in _names(panels):
        assert name in window.gui.item_rects, name
    for plot in ("signal", "raw", "obs", "mean", "noise", "dwell"):
        assert f"plot.{plot}" in window.gui.item_rects
    for menu in ("File", "Analysis", "View"):
        assert f"menu.{menu}" in window.gui.item_rects


def test_the_empty_window_disables_what_needs_data(window):
    model = window.gui.controls_model
    assert not model.enabled("run") and not model.enabled("reset")
    assert not model.enabled("crop_min") and not model.enabled("stop")


def test_menu_load_opens_the_file_dialog_with_ebfrets_filters(window):
    window.click_item("menu.File")
    load = window.app.items["load"]
    window.app.command("load")
    window.frame()
    chooser = window.gui.dialogs[-1].chooser
    assert [label for label, _ in chooser.filters][:2] == [
        "ebFRET saved session (.mat)", "Raw donor-acceptor time series (.dat)"]
    assert chooser.multiselect and load.label == "Load"


def test_typing_a_series_number_selects_it(window, tmp_path):
    window.load_demo(tmp_path)
    window.click_item("series_value.edit")
    window.app.key(0x01000003, "")  # backspace the "1"
    window.frame()
    window.type("7")
    assert window.client.status()["controls"]["series_value"] == 7


def test_run_button_runs_on_the_backend_and_the_window_follows(window, tmp_path):
    window.load_demo(tmp_path)
    window.client.set("max_states", 2)
    window.frame()
    window.click_item("run")
    deadline = time.monotonic() + 120
    while window.client.status()["running"] and time.monotonic() < deadline:
        window.frame()
        time.sleep(0.1)
    window.frame(2)
    assert window.gui.view["analysis"]["analysed"] == demo.DEMO["n_series"]
    viterbi_markers = [line for line in window.gui.view["plots"]["signal"]["lines"]
                       if line.get("marker")]
    assert viterbi_markers, "the Viterbi overlay must be drawn after a run"


def test_every_dialog_draws_and_cancels(window, tmp_path):
    window.load_demo(tmp_path)
    openers = [window.gui.remove_bleaching, window.gui.clip_outliers, window.gui.init_priors,
               lambda: window.gui.show(dlg.select_channels_dialog(lambda c: None)),
               lambda: window.gui.show(dlg.assign_smd_channels_dialog(["a", "b"], lambda c: None)),
               lambda: window.gui.show(dlg.select_analysis_dialog([2, 3], ["group 1"],
                                                                  lambda k, g: None))]
    for open_dialog in openers:
        open_dialog()
        window.frame()
        dialog = window.gui.dialogs[-1]
        dx, dy, dw, dh = window.gui.item_rects["dialog"]
        window.click(dx + dw - 4, dy + 10)  # a click on the dialog must not fall through
        cancel = dialog.state.rects["cancel"]
        window.click(cancel[0] + 5, cancel[1] + cancel[3] / 2)
        assert not window.gui.dialogs, type(dialog.form).__name__


def test_remove_bleaching_dialog_values_reach_the_backend(window, tmp_path):
    window.load_demo(tmp_path)
    seen = {}
    dialog = dlg.remove_bleaching_dialog(lambda method, params: seen.update(m=method, p=params))
    window.gui.show(dialog)
    window.frame()
    toggle = dialog.state.rects["acc"]
    window.click(toggle[0] + 5, toggle[1] + toggle[3] / 2)
    ok = dialog.state.rects["ok"]
    window.click(ok[0] + 5, ok[1] + ok[3] / 2)
    assert seen["m"] == 1 and seen["p"]["acc"] == 0.0 and seen["p"]["don"] is None


def test_selecting_a_row_in_the_series_list_shows_that_series(window, tmp_path):
    window.load_demo(tmp_path)
    window.app.command("table_series")
    window.frame(2)
    x, y, w, h = window.gui.item_rects["series_records"]
    window.click(x + 40, y + 4 * 19 + 30)
    window.frame(2)
    assert window.client.status()["controls"]["series_value"] > 1


def test_the_guided_tour_points_at_real_controls(window, tmp_path):
    from chisurf.plugins.burst.burst_ebfret.gui.tool import ANCHORS

    window.load_demo(tmp_path)
    guide = json.loads((GUI_DIR / "guide.json").read_text())
    for step in guide["steps"]:
        name = step["target"].get("name")
        if name:
            assert name in ANCHORS, name
            assert ANCHORS[name] in window.gui.item_rects, name
    waits = [s for s in guide["steps"] if "await" in s]
    assert len(waits) >= 5


def test_the_window_rasterises(window, tmp_path):
    """One real raster frame, so a painter-level failure cannot hide behind the recorder."""
    window.load_demo(tmp_path)
    painter = PixelPainter(W, H)
    window.app.draw(painter, 0, 0, W, H)
    lit = sum(1 for i in range(0, len(painter.px), 4 * 97) if painter.px[i] > 100)
    assert lit > 50
