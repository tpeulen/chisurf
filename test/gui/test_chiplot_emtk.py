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

from qtpy import QtGui, QtWidgets

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
    assert curve.native() not in plot.native()


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

    image.set_levels((0.0, 5.0))
    image.set_image(data * 2.0)
    assert image.native()["texture"] is None, "the texture is rebuilt, not reused"


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


@pytest.mark.parametrize(
    "call, wanted",
    [
        (lambda p: p.region((0.0, 1.0)), "region"),
        (lambda p: p.errorbars([0.0], [0.0], height=[1.0]), "error bars"),
        (lambda p: p.text("hello", (0.0, 0.0)), "text"),
    ],
)
def test_what_is_not_drawn_yet_says_so(plot, call, wanted):
    """A plot that quietly omits what it was asked for is worse than an error."""
    with pytest.raises(NotImplementedError) as excinfo:
        call(plot)
    message = str(excinfo.value)
    assert wanted in message
    assert "PRD-104" in message, "the refusal names where the work is tracked"
    assert "pyqtgraph" in message, "and what to use meanwhile"


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
