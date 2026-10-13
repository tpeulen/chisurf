"""One wheel notch over a plot is one zoom step; the plot then holds still while hovered.

The user's report (2026-10-12): "when I use the mouse wheel in a plot, the zoom goes crazy and only
stops once the mouse leaves the plot". emtk kept the wheel "until a widget consumed it", a plot
read it without consuming it, and every following frame zoomed again. The emtk frame loop now
spends one-shot input; this guards both plot kinds ChiSurf draws -- a chiplot panel hosted in an
emtk frame (``im.host_control``, as the emtk shell and the tool windows host it) and an implot
plot -- with the real event sequence: the notch, then the hand resting on the plot while the host
keeps drawing (``emtk.testing_realistic.assert_settles``), and a trackpad swipe.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

testing_realistic = pytest.importorskip("emtk.testing_realistic")
if not hasattr(testing_realistic, "assert_settles"):  # pragma: no cover - older emtk
    pytest.skip("emtk without assert_settles", allow_module_level=True)

from emtk import im, implot  # noqa: E402
from emtk.app import ImApp  # noqa: E402
from emtk.testing_realistic import RealisticDriver, assert_settles  # noqa: E402

from chisurf.chiplot import backends as _backends  # noqa: E402


@pytest.fixture(autouse=True)
def _emtk_backend():
    previous, previous_env = _backends._active, os.environ.get("CHISURF_PLOT_BACKEND")
    os.environ["CHISURF_PLOT_BACKEND"] = "emtk"
    _backends._active = None
    try:
        yield
    finally:
        _backends._active = previous
        implot._cur.plot = None
        if previous_env is None:
            os.environ.pop("CHISURF_PLOT_BACKEND", None)
        else:
            os.environ["CHISURF_PLOT_BACKEND"] = previous_env


def _chiplot_app(qapp):
    from chisurf.gui import chiplot as cp

    panel = cp.Plot()
    x = np.linspace(0.0, 25.0, 128)
    panel.line(x, 1000.0 * np.exp(-x / 4.0) + 5.0, name="decay")
    out: dict = {}

    def gui():
        im.begin("w", (0, 0, 700, 500))
        im.host_control("##decay", panel._canvas, (600, 400))
        out["rect"] = im.get_item_rect()
        im.end()

    return ImApp(gui), out, (lambda: repr(panel._canvas.get_range())), panel


def _implot_app():
    out: dict = {}
    t = np.linspace(0.0, 10.0, 200)

    def gui():
        im.begin("w", (0, 0, 700, 500))
        implot.begin_plot("decay", (600, 400))
        implot.setup_axes_limits(0, 10, 0, 1)
        implot.plot_line("I", t, np.exp(-t / 2.5))
        out["rect"] = implot.get_plot_pos() + implot.get_plot_size()
        implot.end_plot()
        lim = implot.get_plot_limits()
        out["view"] = (lim.x_min, lim.x_max, lim.y_min, lim.y_max)
        im.end()

    return ImApp(gui), out, (lambda: out["view"]), None


def _centre(out):
    x, y, w, h = out["rect"]
    return x + w / 2.0, y + h / 2.0


@pytest.mark.parametrize("kind", ["chiplot", "implot"])
@pytest.mark.parametrize("gesture", ["notch", "notch_out", "swipe"])
def test_a_plot_zooms_once_and_then_holds_still_under_a_resting_pointer(qapp, kind, gesture):
    app, out, view, panel = _chiplot_app(qapp) if kind == "chiplot" else _implot_app()
    try:
        driver = RealisticDriver(app, (700, 500), real_painter=False)
        driver.frame(3)
        centre = _centre(out)
        before = view()
        actions = {
            "notch": lambda d: d.wheel(1, at=centre),
            "notch_out": lambda d: d.wheel(-1, at=centre),
            "swipe": lambda d: d.swipe(2, at=centre, events=20, momentum=10),
        }
        assert_settles(driver, actions[gesture], view, frames=30, label=f"{kind}/{gesture}")
        assert view() != before, f"{kind}: the {gesture} did not zoom at all"
    finally:
        if panel is not None:
            panel.close()
