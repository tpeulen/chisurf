"""What an interactive image dock needs from chiplot, on the native backend.

The AutoForm ``image`` section used to be a ~800-line Qt widget around
``pg.ImageView``. Its features -- frames and playback, a picture on real axes,
square pixels, symbols over the picture, a paintable layer, a resizable gate --
are chiplot's now, so each is pinned here against the view alone, with no
section in between.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

pytest.importorskip("emtk")

from chisurf.chiplot import backends as _backends  # noqa: E402


@pytest.fixture(autouse=True)
def _emtk_backend():
    """Pin this module to emtk, whatever the environment selects."""
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
def view(qapp):
    from chisurf.gui import chiplot

    iv = chiplot.ImageView()
    iv.resize(400, 300)
    yield iv
    iv.close()


def _stack(n=5, rows=6, cols=8):
    return np.stack([np.full((rows, cols), float(i)) for i in range(n)])


def _canvas(view):
    return view.native


def _paint(view):
    from emtk.qt_painter import QtPainter
    from qtpy import QtGui

    image = QtGui.QImage(400, 300, QtGui.QImage.Format_ARGB32)
    image.fill(QtGui.QColor(0, 0, 0))
    painter = QtGui.QPainter(image)
    try:
        view.native.draw(QtPainter(painter), 0.0, 0.0, 400.0, 300.0)
    finally:
        painter.end()
    return image


# -- frames -------------------------------------------------------------------
def test_a_stack_shows_a_slider_and_a_single_image_does_not(view):
    view.set_image(np.zeros((6, 8)))
    assert view.frame_count == 1 and view._frame_bar.isHidden()
    view.set_image(_stack())
    assert view.frame_count == 5 and not view._frame_bar.isHidden()
    assert view._slider.maximum() == 4


def test_the_slider_steps_frames_and_frames_move_the_slider(view):
    seen = []
    view.frame_changed.connect(seen.append)
    view.set_image(_stack())
    view._slider.setValue(3)
    assert view.frame == 3
    assert _canvas(view)._entries[0].state["data"][0, 0] == 3.0
    view.set_frame(1)
    assert view._slider.value() == 1 and seen[-1] == 1
    view.set_frame(7)  # wraps rather than raising
    assert view.frame == 2


def test_a_stack_keeps_one_colour_scale_across_frames(view):
    """Stepping must not rescale: frame 0 is all 0, frame 4 all 4."""
    view.set_image(_stack())
    low, high = _canvas(view)._entries[0].get_levels()
    assert (low, high) == (0.0, 4.0)
    view.set_frame(2)
    assert _canvas(view)._entries[0].get_levels() == (0.0, 4.0)


def test_playback_loops_or_stops_at_the_end(view):
    view.set_image(_stack(3))
    states = []
    view.playing_changed.connect(states.append)
    view.play(30, loop=False)
    assert view.playing and states == [True]
    for _ in range(5):
        view._advance()
    assert view.frame == 2 and not view.playing and states == [True, False]
    view.set_loop(True)
    view.play(30)
    view._advance()
    assert view.frame == 0, "a looping stack wraps round"
    view.stop()
    assert not view.playing and view.frame == 0


def test_playing_a_single_image_does_nothing(view):
    view.set_image(np.zeros((4, 4)))
    view.play(10)
    assert not view.playing


# -- placing the picture ------------------------------------------------------
def test_an_extent_puts_the_picture_on_real_axes_and_maps_clicks_back(view):
    view.set_image(np.zeros((20, 60)))
    view.set_extent((0.0, 6.0, 0.0, 2.0))
    assert _canvas(view)._entries[0].state["rect"] == (0.0, 0.0, 6.0, 2.0)
    assert view.pixel_at(3.05, 1.0) == (10, 30)
    assert view.pixel_at(6.5, 1.0) is None, "outside the picture"
    view.set_extent(None)
    assert view.pixel_at(30.5, 10.5) == (10, 30)


def test_axes_are_off_until_asked_for_and_carry_titles(view):
    canvas = _canvas(view)
    view.set_image(np.zeros((4, 4)))
    assert canvas._axis_visible == {"left": False, "bottom": False}
    view.set_labels(bottom="x [ns]", left="y")
    assert canvas._axis_visible == {"left": True, "bottom": True}
    assert canvas._labels["bottom"] == "x [ns]"


def test_pixels_stay_square_until_the_aspect_is_freed(view):
    view.set_image(np.zeros((20, 60)))
    _paint(view)
    plot_box = _canvas(view)._drawn
    assert plot_box["x"] is not None
    x_range, y_range = plot_box["x"], plot_box["y"]
    assert x_range[1] - x_range[0] == pytest.approx(60.0, abs=1.0)
    assert y_range[1] - y_range[0] == pytest.approx(20.0, abs=1.0)
    assert _canvas(view)._aspect == 1.0
    view.set_aspect_locked(False)
    assert _canvas(view)._aspect is None


def test_an_image_row_zero_is_at_the_top_by_default(view):
    view.set_image(np.zeros((4, 4)))
    assert _canvas(view)._y_inverted is True
    view.invert_y(False)
    assert _canvas(view)._y_inverted is False


# -- symbols over the picture -------------------------------------------------
def test_marks_are_drawn_over_the_picture_not_under_it(view):
    view.set_image(np.zeros((20, 20)))
    view.set_axes_visible(False)
    view.marks([10.0], [10.0], symbol="s", size=10, brush=(255, 0, 0, 255))
    image = _paint(view)
    # the picture is dark viridis; the red square is the only red there is
    reds = sum(
        1
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y).red() > 200 and image.pixelColor(x, y).green() < 60
    )
    assert reds > 30


def test_marks_can_be_replaced_and_removed(view):
    view.set_image(np.zeros((8, 8)))
    handle = view.marks([1, 2], [1, 2])
    handle.set_data([3.0], [3.0])
    assert list(handle.get_data()[0]) == [3.0]
    handle.remove()
    assert not handle.is_alive()


def test_a_label_is_written_at_its_position(view):
    view.set_image(np.zeros((8, 8)))
    label = view.label("tile 1", 2.0, 3.0)
    assert label.text == "tile 1" and label.position == (2.0, 3.0)


# -- painting -----------------------------------------------------------------
def test_a_brush_stamps_its_kernel_and_reports_each_stroke(view):
    view.set_image(np.zeros((10, 10)))
    seen = []
    view.enable_brush(np.ones((3, 3)), on_stroke=lambda mask, phase: seen.append((phase, mask)))
    handler = _canvas(view)._paint
    handler("start", 5.5, 5.5)
    handler("end", 5.5, 5.5)
    mask = view.brush_mask()
    assert mask.sum() == 9 and mask[4:7, 4:7].all()
    assert [phase for phase, _ in seen] == ["start", "end"]
    assert seen[0][1].sum() == 9, "the callback gets a copy at each stamp"


def test_a_stroke_has_no_gaps_when_the_pointer_jumps(view):
    view.set_image(np.zeros((10, 40)))
    view.enable_brush(np.ones((1, 1)))
    handler = _canvas(view)._paint
    handler("start", 2.5, 5.5)
    handler("move", 30.5, 5.5)
    handler("end", 30.5, 5.5)
    assert view.brush_mask()[5, 2:31].all()


def test_a_negative_kernel_erases_and_never_goes_below_zero(view):
    view.set_image(np.zeros((6, 6)))
    state = {"kernel": np.ones((1, 1))}
    view.enable_brush(lambda: state["kernel"])
    handler = _canvas(view)._paint
    handler("start", 2.5, 2.5)
    handler("end", 2.5, 2.5)
    assert view.brush_mask()[2, 2] == 1.0
    state["kernel"] = -np.ones((1, 1))
    handler("start", 2.5, 2.5)
    handler("end", 2.5, 2.5)
    handler("start", 2.5, 2.5)
    assert view.brush_mask().min() == 0.0, "an erase of an erased pixel stays at zero"


def test_a_stamp_at_the_border_is_clipped_not_wrapped(view):
    view.set_image(np.zeros((6, 6)))
    view.enable_brush(np.ones((5, 5)))
    _canvas(view)._paint("start", 0.5, 0.5)
    mask = view.brush_mask()
    assert mask[:3, :3].all() and mask.sum() == 9
    assert mask[:, 3:].sum() == 0 and mask[3:, :].sum() == 0


def test_a_painted_mask_can_be_replaced_and_a_wrong_shape_is_dropped(view):
    view.set_image(np.zeros((6, 6)))
    view.enable_brush()
    given = np.zeros((6, 6))
    given[1, 1] = 1.0
    view.set_brush_mask(given)
    assert view.brush_mask()[1, 1] == 1.0
    view.set_brush_mask(np.ones((3, 3)))
    assert view.brush_mask().sum() == 0


def test_painting_is_off_the_picture_is_ignored(view):
    view.set_image(np.zeros((6, 6)))
    view.enable_brush()
    _canvas(view)._paint("start", 50.5, 50.5)
    assert view.brush_mask().sum() == 0


def test_the_brush_gets_the_drag_but_a_shape_under_it_keeps_it(view):
    """A press on a handle moves the handle; one on bare picture paints."""
    view.set_image(np.zeros((20, 20)))
    view.set_axes_visible(False)
    roi = view.add_roi(kind="rect", pos=(2.0, 2.0), size=(4.0, 4.0))
    view.enable_brush()
    _paint(view)
    canvas = _canvas(view)
    box = roi.native["_box"]
    inside = ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)
    canvas.press(*inside, 0.0, 0.0, 400.0, 300.0)
    canvas.drag(inside[0] + 20.0, inside[1], 0.0, 0.0, 400.0, 300.0)
    canvas.release()
    assert roi.pos[0] > 2.0 and view.brush_mask().sum() == 0

    far = (box[2] + 60.0, box[3] + 40.0)
    canvas.press(*far, 0.0, 0.0, 400.0, 300.0)
    canvas.release()
    assert view.brush_mask().sum() >= 1


def test_without_a_brush_the_drag_pans(view):
    view.set_image(np.zeros((20, 20)))
    _paint(view)
    canvas = _canvas(view)
    before = view.view_range()
    canvas.press(200.0, 150.0, 0.0, 0.0, 400.0, 300.0)
    canvas.drag(150.0, 150.0, 0.0, 0.0, 400.0, 300.0)
    canvas.release()
    assert view.view_range() != before
    view.enable_brush()
    view.auto_range()
    _paint(view)
    before = view.view_range()
    canvas.press(200.0, 150.0, 0.0, 0.0, 400.0, 300.0)
    canvas.drag(150.0, 150.0, 0.0, 0.0, 400.0, 300.0)
    canvas.release()
    assert view.view_range() == before, "with a brush armed the drag paints instead"


def test_disabling_the_brush_removes_its_layer(view):
    view.set_image(np.zeros((6, 6)))
    view.enable_brush()
    assert len(_canvas(view)._entries) == 2
    view.disable_brush()
    assert len(_canvas(view)._entries) == 1 and view.brush_mask() is None


# -- a resizable gate ---------------------------------------------------------
def test_a_resizable_rectangle_is_resized_by_its_corner_grip(view):
    view.set_image(np.zeros((40, 40)))
    view.set_axes_visible(False)
    roi = view.add_roi(kind="rect", pos=(10.0, 10.0), size=(10.0, 10.0), resizable=True)
    done = []
    roi.on_change(lambda *_: done.append(roi.size), final=True)
    _paint(view)
    canvas = _canvas(view)
    gx, gy = roi.native["_grips"]["hi"]
    canvas.press(gx, gy, 0.0, 0.0, 400.0, 300.0)
    canvas.drag(gx + 30.0, gy + 20.0, 0.0, 0.0, 400.0, 300.0)
    canvas.release()
    assert roi.pos == (10.0, 10.0), "the opposite corner stays put"
    assert roi.size[0] > 10.0 and roi.size[1] > 10.0
    assert done, "and the end of the drag is reported"


def test_dragging_a_grip_past_the_opposite_corner_flips_without_collapsing(view):
    view.set_image(np.zeros((40, 40)))
    view.set_axes_visible(False)
    roi = view.add_roi(kind="rect", pos=(20.0, 20.0), size=(6.0, 6.0), resizable=True)
    _paint(view)
    canvas = _canvas(view)
    gx, gy = roi.native["_grips"]["hi"]
    canvas.press(gx, gy, 0.0, 0.0, 400.0, 300.0)
    canvas.drag(gx - 120.0, gy - 120.0, 0.0, 0.0, 400.0, 300.0)
    canvas.release()
    assert roi.pos[0] < 20.0 and roi.size[0] > 6.0


def test_a_shape_without_resizable_has_no_grip(view):
    view.set_image(np.zeros((40, 40)))
    roi = view.add_roi(kind="rect", pos=(10.0, 10.0), size=(10.0, 10.0))
    _paint(view)
    assert "_grips" not in roi.native


# -- the colour ramp ----------------------------------------------------------
def test_an_image_gets_a_colour_ramp_with_draggable_levels(view):
    assert view._ramp is None
    view.set_image(np.arange(100.0).reshape(10, 10))
    assert view._ramp is not None
    bar = view._iv._bar
    assert bar.get_levels() == (0.0, 99.0)
    bar.set_levels(10.0, 50.0)
    assert _canvas(view)._entries[0].get_levels() == (10.0, 50.0)
    view.clear()
    assert view._ramp is None and view.brush_mask() is None


# -- colour overlays ----------------------------------------------------------
def test_an_rgba_overlay_keeps_its_own_colours_and_transparency(view):
    """``add_overlay`` is documented as taking RGBA with transparency."""
    view.set_image(np.zeros((8, 8)))
    rgba = np.zeros((8, 8, 4), dtype=np.uint8)
    rgba[2:4, 2:4] = (255, 0, 0, 255)
    overlay = view.add_overlay(rgba)
    assert overlay.get_image().shape == (8, 8, 4)
    assert overlay.native["rect"] == (0.0, 0.0, 8.0, 8.0)
    view.set_axes_visible(False)
    image = _paint(view)
    reds = sum(
        1
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y).red() > 200 and image.pixelColor(x, y).green() < 60
    )
    assert reds > 20


def test_an_rgb_float_overlay_is_read_as_unit_range(view):
    view.set_image(np.zeros((4, 4)))
    rgb = np.zeros((4, 4, 3))
    rgb[..., 1] = 1.0
    overlay = view.add_overlay(rgb)
    assert overlay.native["texture"] is None
    _paint(view)
    assert overlay.native["texture"] is not None


def test_an_image_that_is_neither_2d_nor_colour_is_refused_by_name(view):
    from chisurf.chiplot import backends

    canvas = backends.get_backend().create_canvas()
    with pytest.raises(ValueError, match="2-D"):
        canvas.add_image(np.zeros((4, 4, 2)))
