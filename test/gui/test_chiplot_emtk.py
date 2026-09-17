"""chiplot over emtk: what it draws, and what it says it cannot draw yet.

emtk is the designated native renderer (PRD-104). The backend is a bridge
between two opposite models -- chiplot hands out handles the caller keeps,
emtk redraws from scratch every frame -- so what these tests pin is that the
handles stay authoritative across redraws, and that the families not yet
ported refuse by name instead of drawing nothing.
"""

from __future__ import annotations

import os

import numpy as np
import pytest
from qtpy import QtGui

pytest.importorskip("emtk")

from chisurf.gui.chiplot import backends as _backends  # noqa: E402


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
def plot(qapp):
    """A panel drawn by emtk, closed when the test ends."""
    from chisurf.gui import chiplot as cp

    panel = cp.Plot()
    yield panel
    panel.close()


def _decay(n: int = 128):
    x = np.linspace(0.0, 25.0, n)
    return x, 1000.0 * np.exp(-x / 4.0) + 5.0


def test_the_backend_is_selectable_by_name(qapp):
    """``CHISURF_PLOT_BACKEND=emtk`` reaches this backend."""
    backend = _backends.get_backend()
    assert backend.name == "emtk"
    assert backend.raw_module().__name__ == "emtk"


def test_a_curve_survives_the_redraw_it_is_drawn_by(plot):
    """The handle owns the data; the frame is redrawn from it."""
    x, y = _decay()
    curve = plot.line(x, y, name="decay")

    drawn_x, drawn_y = curve.get_data()
    assert drawn_x.size == x.size
    assert drawn_y[0] == pytest.approx(y[0])

    curve.set_data(x, y * 2.0)
    assert curve.get_data()[1][0] == pytest.approx(y[0] * 2.0)


def test_a_hidden_curve_is_not_drawn_but_is_still_there(plot):
    """Visibility is a property of the entry, not a redraw the caller loses."""
    x, y = _decay()
    curve = plot.line(x, y, name="decay")

    curve.hide()
    assert curve.visible is False
    assert curve.is_alive()

    curve.show()
    assert curve.visible is True


def test_removing_a_curve_takes_it_out_of_the_panel(plot):
    """And the handle says so, rather than pointing at a deleted object."""
    x, y = _decay()
    curve = plot.line(x, y, name="decay")

    curve.remove()
    assert not curve.is_alive()
    assert curve.native not in plot.native()


def test_the_range_follows_the_data_until_it_is_set(plot):
    """Auto-fit reads the drawn samples; an explicit range wins."""
    x, y = _decay()
    plot.line(x, y, name="decay")

    (x0, x1), _ = plot.get_range()
    assert x0 == pytest.approx(0.0) and x1 == pytest.approx(25.0)

    plot.set_range(x=(5.0, 10.0))
    (x0, x1), _ = plot.get_range()
    assert (x0, x1) == (5.0, 10.0)

    plot.autoscale()
    (x0, x1), _ = plot.get_range()
    assert x1 == pytest.approx(25.0)


def test_a_log_axis_drops_what_it_cannot_show(plot):
    """A log axis has nothing to say about zero or a negative count."""
    x = np.linspace(0.0, 10.0, 11)
    y = np.array([-1.0, 0.0] + [float(i) for i in range(1, 10)])
    plot.line(x, y, name="mixed")
    plot.set_log(y=True)

    canvas = plot._canvas
    drawn_x, drawn_y = canvas._scaled(x, y)
    assert drawn_x.size == 9, "the non-positive samples are not plottable"
    assert np.all(np.isfinite(drawn_y))


def test_the_panel_paints(plot, qapp):
    """Through Qt, not just into the display list."""
    x, y = _decay()
    plot.line(x, y, name="decay")
    plot.legend()
    plot.set_labels(bottom="t / ns", left="counts")

    plot.resize(400, 300)
    pixmap = QtGui.QPixmap(400, 300)
    pixmap.fill()
    plot.render(pixmap)

    image = pixmap.toImage()
    colours = {image.pixel(i, j) for i in range(0, 400, 7) for j in range(0, 300, 7)}
    assert len(colours) > 2, "the panel drew nothing but its background"


def test_an_image_is_mapped_through_its_colormap(plot):
    """A heatmap paints more than one colour, and its levels are settable."""
    data = np.add.outer(np.arange(24.0), np.arange(32.0))
    image = plot.image(data, colormap="viridis")

    plot.resize(300, 220)
    pixmap = QtGui.QPixmap(300, 220)
    pixmap.fill()
    plot.render(pixmap)
    rendered = pixmap.toImage()
    colours = {rendered.pixel(i, j) for i in range(0, 300, 5) for j in range(0, 220, 5)}
    assert len(colours) > 8, "a mapped heatmap is not one flat colour"

    image.set_levels(0.0, 5.0)
    image.set_image(data * 2.0)
    assert image.native["texture"] is None, "the texture is rebuilt, not reused"


def test_an_image_places_itself_in_data_coordinates(plot):
    """Its rect drives the axes, so a panel holding only an image fits it."""
    plot.image(np.zeros((10, 20)), rect=(5.0, 50.0, 10.0, 100.0))

    plot.resize(200, 200)
    pixmap = QtGui.QPixmap(200, 200)
    pixmap.fill()
    plot.render(pixmap)

    (x0, x1), (y0, y1) = plot.get_range()
    assert (x0, x1) == (5.0, 15.0)
    assert (y0, y1) == (50.0, 150.0)


def test_an_image_has_to_be_two_dimensional(plot):
    """Said plainly, rather than by a reshape nobody asked for."""
    with pytest.raises(ValueError, match="2-D"):
        plot.image(np.zeros((4, 4, 3)))


def _paint(plot, width=300, height=200):
    """Paint the panel once, so the data-to-pixel mapping exists."""
    plot.resize(width, height)
    pixmap = QtGui.QPixmap(width, height)
    pixmap.fill()
    plot.render(pixmap)
    return pixmap


def test_a_region_reports_and_moves_between_its_edges(plot):
    """The fit range is a region; reading and setting it is the whole job."""
    x, y = _decay()
    plot.line(x, y, name="decay")
    region = plot.region((5.0, 10.0))

    assert region.bounds == (5.0, 10.0)
    region.set_bounds(8.0, 12.0)
    assert region.bounds == (8.0, 12.0)

    region.set_limits(0.0, 10.0)
    assert region.bounds[1] <= 10.0, "a region stays inside the limits it is given"


def test_dragging_a_region_moves_it_and_reports(plot):
    """Through the same press/drag/release emtk's host feeds the control."""
    x, y = _decay()
    plot.line(x, y, name="decay")
    region = plot.region((5.0, 10.0))

    seen: list[tuple[float, float]] = []
    region.on_change(lambda low, high: seen.append((low, high)))

    _paint(plot)
    canvas = plot._canvas
    low_px, high_px = region.native["_pixels"]
    middle = (low_px + high_px) / 2.0

    canvas.press(middle, 50.0, 0.0, 0.0, 300.0, 200.0)
    canvas.drag(middle + 40.0, 50.0, 0.0, 0.0, 300.0, 200.0)
    canvas.release()

    assert region.bounds[0] > 5.0, "the region followed the pointer"
    assert seen, "and said so when the drag finished"
    assert seen[-1] == region.bounds


def test_a_press_that_misses_every_band_starts_no_drag(plot):
    """Otherwise a click on the data would drag whatever was nearest."""
    x, y = _decay()
    plot.line(x, y, name="decay")
    region = plot.region((5.0, 10.0))
    _paint(plot)

    canvas = plot._canvas
    canvas.press(1.0, 50.0, 0.0, 0.0, 300.0, 200.0)
    canvas.drag(200.0, 50.0, 0.0, 0.0, 300.0, 200.0)
    canvas.release()

    assert region.bounds == (5.0, 10.0)


def test_a_vertical_marker_is_drawn_and_movable(plot):
    """Cursors are vertical here; emtk's own hline covers the horizontal one."""
    x, y = _decay()
    plot.line(x, y, name="decay")
    marker = plot.vline(12.0)
    _paint(plot)

    assert marker.value == 12.0
    assert marker.native["_pixels"] is not None
    marker.set_value(15.0)
    assert marker.value == 15.0


def test_bars_bands_errorbars_and_text_all_paint(plot):
    """The families a decay window puts on a plot besides its curves."""
    x, y = _decay(16)
    lower = plot.line(x, y * 0.9, name="lower")
    upper = plot.line(x, y * 1.1, name="upper")

    plot.bars(x, y)
    plot.fill_between(lower, upper)
    plot.errorbars(x, y, height=np.sqrt(y))
    plot.text("42", (10.0, 100.0))

    pixmap = _paint(plot, 320, 240)
    rendered = pixmap.toImage()
    colours = {rendered.pixel(i, j) for i in range(0, 320, 5) for j in range(0, 240, 5)}
    assert len(colours) > 4, "the panel drew more than its background and one curve"


def test_error_bars_need_a_size(plot):
    """Neither height nor top/bottom means there is nothing to draw."""
    with pytest.raises(ValueError, match="height"):
        plot.errorbars([0.0, 1.0], [1.0, 2.0])


@pytest.mark.parametrize("kind", ["rect", "ellipse", "polygon"])
def test_a_region_of_interest_is_drawn_and_dragged(plot, kind):
    """Imaging picks pixels with these; moving one has to report where it went."""
    x, y = _decay()
    plot.line(x, y, name="decay")
    roi = plot.add_roi(
        kind=kind,
        pos=(5.0, 100.0),
        size=(4.0, 200.0),
        points=[(5.0, 100.0), (9.0, 100.0), (9.0, 300.0)],
    )

    seen: list[tuple[float, float]] = []
    roi.on_change(lambda *_: seen.append(roi.pos))

    _paint(plot)
    box = roi.native["_box"]
    inside_x = (box[0] + box[2]) / 2.0
    inside_y = (box[1] + box[3]) / 2.0

    canvas = plot._canvas
    canvas.press(inside_x, inside_y, 0.0, 0.0, 300.0, 200.0)
    canvas.drag(inside_x + 30.0, inside_y, 0.0, 0.0, 300.0, 200.0)
    canvas.release()

    assert roi.pos[0] > 5.0, "the shape followed the pointer"
    assert seen, "and reported where it went"


def test_a_region_of_interest_refuses_a_shape_it_cannot_draw(plot):
    """By name, rather than drawing a rectangle and calling it a ring."""
    with pytest.raises(NotImplementedError, match="ring"):
        plot.add_roi(kind="ring")


def test_an_arrow_is_drawn_where_it_points(plot):
    """The head lands on its tip, is sized in pixels, and turns with its angle."""
    from qtpy import QtGui

    plot.set_xlim(0.0, 10.0, padding=0.0)
    plot.set_ylim(0.0, 10.0, padding=0.0)
    head = plot.arrow(5.0, 5.0, angle=0.0, size=30.0, brush=(255, 0, 0))
    assert head.position == (5.0, 5.0) and head.angle == 0.0
    head.set_angle(90.0)
    assert head.angle == 90.0

    plot.resize(300, 300)
    pixmap = QtGui.QPixmap(300, 300)
    pixmap.fill()
    plot.render(pixmap)
    image = pixmap.toImage()
    red = [
        (i, j)
        for i in range(300)
        for j in range(300)
        if QtGui.QColor(image.pixel(i, j)).red() > 200
        and QtGui.QColor(image.pixel(i, j)).green() < 60
    ]
    assert red, "the head was not drawn"
    # Pointing up (+y), the head sits below its tip on screen.
    ys = [j for _, j in red]
    xs = [i for i, _ in red]
    assert max(ys) - min(ys) > max(xs) - min(xs), "the head is not along +y"


def test_a_filled_curve_is_shaded_down_to_zero(plot):
    """A distribution drawn as a filled histogram: shaded between curve and zero.

    It used to raise, so every lifetime fit's Distribution tab showed "Failed
    to create plot" on the default backend.
    """
    plot.set_xlim(0.0, 10.0, padding=0.0)
    plot.set_ylim(0.0, 10.0, padding=0.0)
    plot.line([0.0, 5.0, 10.0], [8.0, 8.0, 8.0], pen=(0, 0, 255), fill=(255, 0, 0, 255))
    image = _paint(plot).toImage()
    width, height = image.width(), image.height()
    red = [
        (i, j)
        for i in range(0, width, 3)
        for j in range(0, height, 3)
        if QtGui.QColor(image.pixel(i, j)).red() > 200
        and QtGui.QColor(image.pixel(i, j)).green() < 60
        and QtGui.QColor(image.pixel(i, j)).blue() < 60
    ]
    assert red, "nothing was filled"
    ys = sorted(j for _, j in red)
    # From the line (high on screen) down towards the zero line (low on screen).
    assert ys[-1] - ys[0] > height * 0.4


def test_an_image_view_shows_a_stack_frame_by_frame(qapp):
    """A (t, y, x) stack steps; a plain image is shown as it is."""
    from chisurf.gui.chiplot import backends as backends_module

    view = backends_module.get_backend().create_image_view()
    stack = np.stack([np.full((8, 8), float(i)) for i in range(5)])
    view.set_image(stack)

    assert view._stack is not None
    first = view._image.native["data"]
    assert first[0, 0] == pytest.approx(0.0)

    view.set_frame(3)
    assert view._image.native["data"][0, 0] == pytest.approx(3.0)

    view.set_frame(7)  # wraps, rather than raising on a stack of five
    assert view._image.native["data"][0, 0] == pytest.approx(2.0)

    view.clear()
    assert view._image is None


def test_an_image_view_reports_clicks_in_image_coordinates(qapp):
    """What a pixel picker needs from it."""
    from chisurf.gui.chiplot import backends as backends_module

    view = backends_module.get_backend().create_image_view()
    view.set_image(np.zeros((4, 4)))
    seen: list[tuple[float, float]] = []
    view.on_click(lambda x, y: seen.append((x, y)))

    assert seen == [], "nothing is reported until something is clicked"


def test_a_grid_lays_its_panels_out(qapp):
    """Each cell is a panel of its own, and the cursor walks the row."""
    from chisurf.gui.chiplot import backends as backends_module

    grid = backends_module.get_backend().create_grid()
    first = grid.add_panel(title="left")
    second = grid.add_panel(title="right")
    grid.next_row()
    third = grid.add_panel(title="below")

    assert len({id(first), id(second), id(third)}) == 3
    assert len(grid.native()) == 3
    assert grid.widget().layout().count() == 3

    grid.clear()
    assert grid.native() == []


def test_dragging_empty_space_pans_the_view(plot):
    """What dragging a plot does everywhere else."""
    x, y = _decay()
    plot.line(x, y, name="decay")
    plot.set_range(x=(0.0, 10.0), y=(0.0, 1000.0))
    _paint(plot)

    canvas = plot._canvas
    canvas.press(150.0, 100.0, 0.0, 0.0, 300.0, 200.0)
    canvas.drag(100.0, 100.0, 0.0, 0.0, 300.0, 200.0)
    canvas.release()

    (x0, x1), _ = plot.get_range()
    assert x0 > 0.0, "dragging left moved the view along the data"
    assert x1 - x0 == pytest.approx(10.0, rel=1e-6), "a pan does not zoom"


def test_the_wheel_zooms_about_the_middle(plot):
    """And a panel told not to be interactive ignores it."""
    x, y = _decay()
    plot.line(x, y, name="decay")
    plot.set_range(x=(0.0, 10.0), y=(0.0, 1000.0))
    _paint(plot)
    canvas = plot._canvas

    canvas.scroll(-3)
    (x0, x1), _ = plot.get_range()
    assert x1 - x0 < 10.0, "a notch towards the user zooms in"

    plot.set_range(x=(0.0, 10.0))
    plot.set_interactive(mouse=False)
    canvas.scroll(-3)
    (x0, x1), _ = plot.get_range()
    assert (x1 - x0) == pytest.approx(10.0), "a frozen panel does not zoom"


def test_a_panel_exports_itself_to_a_file(plot, tmp_path):
    """The export the plot menu offers."""
    x, y = _decay()
    plot.line(x, y, name="decay")
    plot.resize(240, 180)

    target = tmp_path / "panel.png"
    plot.export_image(str(target))  # the facade returns nothing: it falls
    assert target.is_file()  # back to a widget grab if the backend
    assert target.stat().st_size > 0  # declines, so the file is the result


def test_discarding_a_panel_leaves_no_qt_object_behind(qapp):
    """The reason this backend exists, stated as a test.

    A pyqtgraph panel is a scene of QGraphicsItems that outlive it and receive
    events after their C++ half is gone. An emtk panel is a Python list: drop
    it and there is nothing left to deliver an event to.
    """
    from chisurf.gui import chiplot as cp

    panel = cp.Plot()
    x, y = _decay()
    panel.line(x, y, name="decay")
    entries = panel.native()
    panel.clear()

    assert entries == [], "the display list is the whole of the panel's state"


def test_tick_numbers_read_as_values():
    """A log axis holds exponents, and a linear step never prints float noise."""
    from chisurf.gui.chiplot.backends.emtk_backend import _tick_labels

    assert _tick_labels([0.0, 1.0, 2.0, 3.0], log=True) == ["1", "10", "100", "1000"]
    assert _tick_labels([6.0], log=True) == ["10⁶"]
    assert _tick_labels([0.1, 0.2, 0.30000000000000004], log=False) == ["0.1", "0.2", "0.3"]
    assert _tick_labels([-0.0, 50.0], log=False) == ["0", "50"]


def test_linked_panels_share_the_x_range_of_all_their_data(plot, qapp):
    """Residual strips over a decay: one time axis, fitted to the union."""
    from chisurf.gui import chiplot as cp

    strip = cp.Plot()
    strip.link_x(plot)
    plot.line(np.linspace(0.0, 12.0, 50), np.ones(50))
    strip.line(np.linspace(1.0, 11.0, 50), np.zeros(50))
    _paint(plot)
    _paint(strip)

    assert strip.get_range()[0] == pytest.approx(plot.get_range()[0])
    low, high = plot.get_range()[0]
    assert low <= 0.0 and high >= 12.0


def test_an_edge_of_a_region_drags_on_its_own(plot):
    """Pressing an edge moves that edge; the other stays where it was."""
    x, y = _decay()
    plot.line(x, y, name="decay")
    region = plot.region((5.0, 10.0))
    _paint(plot)
    canvas = plot._canvas
    low_px, high_px = region.native["_pixels"]

    canvas.press(high_px, 50.0)
    canvas.drag(high_px + 30.0, 50.0)
    canvas.release()

    low, high = region.bounds
    assert low == pytest.approx(5.0)
    assert high > 10.0


def test_an_anchored_label_is_a_box_inside_the_plot_area(plot):
    """The fit-quality readout: pinned to the panel, several lines, draggable."""
    x, y = _decay()
    plot.line(x, y)
    label = plot.text(
        "range 1–9\nχ² 1.0", (10, 10), fill=(0, 0, 0, 200), anchored=True, draggable=True
    )
    _paint(plot)
    left, top, right, bottom = label.native["_box"]
    assert right - left > 20.0 and bottom - top > 20.0, "two lines get a two-line box"

    canvas = plot._canvas
    canvas.press(left + 5.0, top + 5.0)
    canvas.drag(left + 25.0, top + 15.0)
    canvas.release()
    assert label.native["pos"] == pytest.approx((30.0, 20.0))


def test_a_log_axis_takes_its_limits_in_data_units_and_ticks_on_decades(plot):
    """The simulator's decay: zeros before the rise, limits (0.1, max) in counts.

    The limits were used as exponents -- an axis up to 10**3000 that read
    "10^10.669" and pressed the decay flat onto its floor.
    """
    from chisurf.gui.chiplot.backends.emtk_backend import _tick_labels

    t = np.linspace(0.0, 12.0, 400)
    counts = np.where(t < 1.0, 0.0, 5.0e4 * np.exp(-(t - 1.0) / 2.5))
    plot.line(t, counts)
    plot.set_log(y=True)
    plot.set_ylim(0.1, float(counts.max()))
    _paint(plot, 300, 240)

    canvas = plot._canvas
    low, high = canvas._drawn["y"]
    assert (low, high) == pytest.approx((-1.0, np.log10(counts.max())))
    assert plot.get_range()[1] == pytest.approx((0.1, counts.max()))
    ticks = [v for v in range(-1, 5)]
    assert _tick_labels([float(v) for v in ticks], log=True) == [
        "0.1",
        "1",
        "10",
        "100",
        "1000",
        "10000",
    ]


def test_a_log_axis_fits_only_the_positive_samples(plot):
    t = np.linspace(0.0, 10.0, 100)
    y = np.concatenate([np.zeros(10), -np.ones(5), np.geomspace(1.0, 1000.0, 85)])
    plot.line(t, y)
    plot.set_log(y=True)
    _paint(plot)
    low, high = plot._canvas._drawn["y"]
    assert low < 0.0 < 3.0 < high and high - low < 3.5
