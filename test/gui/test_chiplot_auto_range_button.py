"""Every chiplot panel carries the "A" auto-range button.

Hidden while both axes follow the data; shown in the lower-left of the plot
area once the user wheels or drags the view; a click fits the view to the data
again and hides it. Driven through the same press/drag/scroll/hover calls the
emtk hosts (Qt widget and the emtk shell's fit windows) feed the canvas.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("emtk.widgets.auto_range")

from emtk.testing import RecordingPainter  # noqa: E402

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
        if previous_env is None:
            os.environ.pop("CHISURF_PLOT_BACKEND", None)
        else:
            os.environ["CHISURF_PLOT_BACKEND"] = previous_env


@pytest.fixture
def plot(qapp):
    from chisurf.gui import chiplot as cp

    panel = cp.Plot()
    x = np.linspace(0.0, 25.0, 128)
    panel.curve = panel.line(x, 1000.0 * np.exp(-x / 4.0) + 5.0, name="decay")
    yield panel
    panel.close()


BOX = (0.0, 0.0, 800.0, 600.0)


def _draw(plot, box=BOX):
    painter = RecordingPainter()
    plot._canvas.draw(painter, *box)
    return painter


def _a_texts(painter):
    return [t for t in painter.texts if t[5] == "A"]


def _centre(box=BOX):
    return box[0] + box[2] / 2.0, box[1] + box[3] / 2.0


def _click(canvas, px, py, box=BOX):
    canvas.press(px, py, *box)
    canvas.release()


def _flat(view_range):
    return [value for span in view_range for value in span]


def _button_centre(canvas):
    x, y, w, h = canvas._auto_button_rect
    return x + w / 2.0, y + h / 2.0


def test_hidden_while_both_axes_follow_the_data(plot):
    painter = _draw(plot)
    assert plot.is_auto_range() == (True, True)
    assert _a_texts(painter) == []
    assert plot._canvas._auto_button_rect is None


@pytest.mark.parametrize("box", [BOX, (0.0, 0.0, 320.0, 200.0)])
def test_a_wheel_zoom_shows_it_in_the_plot_area_lower_left(plot, box):
    _draw(plot, box)
    plot._canvas.scroll(-3, *box)
    painter = _draw(plot, box)
    assert plot.is_auto_range() == (False, False)
    (text,) = _a_texts(painter)
    bx, by, bw, bh = plot._canvas._auto_button_rect
    # Inside the panel and in its lower-left quarter: reachable.
    assert box[0] <= bx and bx + bw <= box[0] + box[2]
    assert box[1] <= by and by + bh <= box[1] + box[3]
    assert bx < box[0] + box[2] / 4.0 and by > box[1] + box[3] / 2.0
    assert text[:4] == (bx, by, bw, bh)


def test_a_drag_pan_shows_it(plot):
    _draw(plot)
    canvas = plot._canvas
    cx, cy = _centre()
    canvas.press(cx, cy, *BOX)
    canvas.drag(cx + 80.0, cy + 30.0, *BOX)
    canvas.release()
    assert len(_a_texts(_draw(plot))) == 1


def test_clicking_it_restores_the_full_data_range_and_hides_it(plot):
    _draw(plot)
    fitted = plot.get_range()
    canvas = plot._canvas
    canvas.scroll(-3, *BOX)
    _draw(plot)
    assert _flat(plot.get_range()) != pytest.approx(_flat(fitted))
    _click(canvas, *_button_centre(canvas))
    assert plot.is_auto_range() == (True, True)
    painter = _draw(plot)
    assert _flat(plot.get_range()) == pytest.approx(_flat(fitted))
    assert _a_texts(painter) == []


def test_a_click_on_it_does_not_pan(plot):
    _draw(plot)
    fitted = plot.get_range()
    canvas = plot._canvas
    canvas.scroll(-3, *BOX)
    _draw(plot)
    px, py = _button_centre(canvas)
    canvas.press(px, py, *BOX)
    canvas.drag(px + 100.0, py - 50.0, *BOX)
    canvas.release()
    _draw(plot)
    assert _flat(plot.get_range()) == pytest.approx(_flat(fitted))


def test_new_data_refits_only_while_auto_ranged(plot):
    _draw(plot)
    x = np.linspace(0.0, 100.0, 64)
    plot.curve.set_data(x, 5000.0 * np.exp(-x / 30.0))
    _draw(plot)
    assert plot.get_range()[0][1] >= 100.0, "an auto-ranged panel did not follow new data"
    plot._canvas.scroll(-3, *BOX)
    _draw(plot)
    zoomed = plot.get_range()
    plot.curve.set_data(x * 4.0, 9000.0 * np.exp(-x / 30.0))
    _draw(plot)
    assert _flat(plot.get_range()) == pytest.approx(_flat(zoomed)), (
        "a zoomed panel jumped to new data"
    )
    _click(plot._canvas, *_button_centre(plot._canvas))
    _draw(plot)
    assert plot.get_range()[0][1] >= 400.0


def test_hovering_it_shows_the_tooltip(plot):
    from emtk.widgets import auto_range

    _draw(plot)
    canvas = plot._canvas
    canvas.scroll(-3, *BOX)
    _draw(plot)
    canvas.hover(*_button_centre(canvas), *BOX)
    painter = _draw(plot)
    assert auto_range.tooltip() in painter.strings
    canvas.hover(*_centre(), *BOX)
    assert auto_range.tooltip() not in _draw(plot).strings


def test_opt_out_and_static_panels_never_show_it(plot):
    _draw(plot)
    plot.set_auto_range_button(False)
    plot._canvas.scroll(-3, *BOX)
    assert _a_texts(_draw(plot)) == []
    plot.set_auto_range_button(True)
    assert len(_a_texts(_draw(plot))) == 1
    plot.set_interactive(mouse=False)
    assert _a_texts(_draw(plot)) == []


def test_a_caller_set_range_shows_it_as_pyqtgraph_does(plot):
    plot.set_range(x=(2.0, 5.0))
    assert len(_a_texts(_draw(plot))) == 1


def test_the_image_view_has_it_too(qapp):
    from chisurf import chiplot as cp

    view = cp.ImagePanel()
    try:
        view.set_image(np.random.default_rng(1).random((32, 48)))
        canvas = view._iv._canvas
        _draw_canvas = lambda: canvas.draw(RecordingPainter(), *BOX)  # noqa: E731
        _draw_canvas()
        assert canvas._auto_button_rect is None
        canvas.scroll(-3, *BOX)
        _draw_canvas()
        assert canvas._auto_button_rect is not None
        view.set_auto_range_button(False)
        _draw_canvas()
        assert canvas._auto_button_rect is None
    finally:
        view.clear()
