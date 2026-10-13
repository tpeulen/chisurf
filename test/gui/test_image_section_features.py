"""The AutoForm ``image`` section keeps every feature it had on pyqtgraph.

Each option of :class:`ImageMapWidget` is driven through the section, against a
small model, on the native chiplot view: colour, channel selector, movie, brush,
point pick and its marker, detected-point markers, labels, the fitted circle,
the rectangle gate, extent and axes. The section is the only importer of the
view, so what a plugin's ``view.json`` can ask for is exactly what is tested.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("emtk")


class Model:
    """Everything a spec can name, in one place."""

    def __init__(self, image=None):
        self.img = np.zeros((20, 60)) if image is None else image
        self.colormap = "magma"
        self.channel = "green"
        self.channel_calls = []
        self.selection = None
        self.draws = 0
        self.live = True
        self.picked = None
        self.pick_calls = 0
        self.points = []
        self.circle = None
        self.tiles = []
        self.span = None
        self.region = None
        self.gates = []

    def image(self):
        return self.img

    def channels(self):
        return ["green", "red"]

    def refresh(self, name=None):
        self.channel_calls.append(name)

    def kernel(self):
        return np.ones((3, 3))

    def drawn(self):
        self.draws += 1

    def pick_done(self):
        self.pick_calls += 1

    def marker_points(self):
        return self.points

    def circle_source(self):
        return self.circle

    def labels(self):
        return self.tiles

    def extent(self):
        return self.span

    def region_source(self):
        return self.region

    def gate(self, roi):
        self.gates.append(roi)


def _section(qtbot, model, **options):
    from chisurf.gui.autoform.sections.builtin import ImageMapWidget

    widget = ImageMapWidget(model, "image", **options)
    qtbot.addWidget(widget)
    widget.resize(500, 400)
    widget.refresh()
    return widget


def _entries(widget, kind):
    return [e for e in widget.view.native._entries if e.kind == kind]


def test_the_colormap_combo_writes_the_model_and_the_image(qtbot):
    m = Model()
    w = _section(qtbot, m, colormap=True, colormap_attr="colormap")
    assert w._combo.currentText() == "magma"
    assert _entries(w, "image")[0].state["colormap"] == "magma"
    w._combo.setCurrentText("gray")
    assert m.colormap == "gray" and _entries(w, "image")[0].state["colormap"] == "gray"
    m.colormap = "plasma"  # another dock sharing the attribute moved it
    w.refresh()
    assert w._combo.currentText() == "plasma"


def test_the_channel_selector_calls_back_and_redraws(qtbot):
    m = Model()
    w = _section(
        qtbot, m, channel_source="channels", channel_attr="channel", channel_call="refresh"
    )
    m.img = np.ones((20, 60))
    w._channel_combo.setCurrentText("red")
    assert m.channel == "red" and m.channel_calls[-1] == "red"
    assert _entries(w, "image")[0].state["data"].max() == 1.0, "the picture followed the choice"


def test_the_movie_controls_follow_the_stack_and_play_it(qtbot):
    m = Model(np.random.rand(4, 8, 8))
    w = _section(qtbot, m, movie=True, movie_fps=25)
    assert w._play_btn.isEnabled() and w._fps_spin.value() == 25
    w._toggle_play()
    assert w._playing and w._play_btn.text() == "⏸" and w.view.playing
    w._loop_btn.setChecked(False)
    w._fps_spin.setValue(60)
    w._toggle_play()
    assert not w._playing and w._play_btn.text() == "▶"
    w.view.set_frame(2)
    w._stop_btn.click()
    assert w.view.frame == 0
    m.img = np.random.rand(8, 8)
    w.refresh()
    assert not w._play_btn.isEnabled()


def test_a_non_looping_movie_stops_by_itself_and_the_button_follows(qtbot):
    m = Model(np.random.rand(3, 8, 8))
    w = _section(qtbot, m, movie=True)
    w._loop_btn.setChecked(False)
    w._start_play()
    for _ in range(4):
        w.view.advance()
    assert not w._playing and w._play_btn.text() == "▶"


def test_the_current_slice_survives_a_refresh(qtbot):
    m = Model(np.random.rand(5, 8, 8))
    w = _section(qtbot, m)
    w.view.set_frame(3)
    w.refresh()
    assert w.view.frame == 3


def test_painting_writes_the_selection_and_calls_back(qtbot):
    m = Model()
    w = _section(
        qtbot,
        m,
        selection_attr="selection",
        brush_kernel_source="kernel",
        on_draw="drawn",
        live_attr="live",
    )
    handler = w.view.native._paint
    handler("start", 10.5, 10.5)
    handler("end", 10.5, 10.5)
    assert m.selection.sum() == 9 and m.selection[9:12, 9:12].all()
    assert m.draws == 1, "once per stamp, not again at the end of the stroke"
    m.live = False
    handler("start", 30.5, 10.5)
    assert m.draws == 1, "live_attr gates the callback during a drag"
    assert m.selection[10, 30] == 1.0, "but the mask is still written"


def test_a_model_selection_is_shown_and_a_stale_shape_is_dropped(qtbot):
    m = Model()
    m.selection = np.zeros((20, 60))
    m.selection[2, 2] = 1.0
    w = _section(qtbot, m, selection_attr="selection")
    assert w.view.brush_mask()[2, 2] == 1.0
    m.selection = np.ones((5, 5))
    w.refresh()
    assert w.view.brush_mask().sum() == 0


def test_hovering_tells_the_pixel_and_its_value(qtbot):
    m = Model()
    m.img[4, 7] = 3.5
    w = _section(qtbot, m, selection_attr="selection")
    w._hover_event(7.5, 4.5)
    assert w._view_widget.toolTip() == "pixel (4, 7) = 3.5"
    w._hover_event(-4.0, 4.5)
    assert w._view_widget.toolTip() == ""


def test_a_click_picks_a_point_and_draws_its_ring(qtbot):
    m = Model()
    w = _section(qtbot, m, select_attr="picked", on_pick="pick_done")
    w.view.clicked.emit(45.2, 6.7)
    assert m.picked == (0, 6, 45) and m.pick_calls == 1
    (ring,) = _entries(w, "marks")
    assert ring.state["symbol"] == "o" and ring.state["size"] == 15.0
    xs, ys = ring.get_data()
    assert (xs[0], ys[0]) == (45.0, 6.0)
    w.view.clicked.emit(-3.0, 1.0)  # off the picture
    assert m.pick_calls == 1


def test_a_pick_on_a_stack_names_the_slice(qtbot):
    m = Model(np.zeros((4, 10, 10)))
    w = _section(qtbot, m, select_attr="picked")
    w.view.set_frame(2)
    w.view.clicked.emit(3.5, 4.5)
    assert m.picked == (2, 4, 3)
    assert len(_entries(w, "marks")) == 1
    w.view.set_frame(1)
    assert _entries(w, "marks") == [], "the ring belongs to its slice"


def test_detected_points_are_squares_on_their_own_slice(qtbot):
    m = Model(np.zeros((3, 10, 10)))
    m.points = [(0, 2, 3), (1, 5, 6), (1, 7, 8)]
    w = _section(qtbot, m, markers_source="marker_points")
    (squares,) = _entries(w, "marks")
    assert squares.state["symbol"] == "s" and len(squares.get_data()[0]) == 1
    w.view.set_frame(1)
    (squares,) = _entries(w, "marks")
    assert list(squares.get_data()[0]) == [6.0, 8.0]


def test_labels_are_written_on_their_slice(qtbot):
    m = Model()
    m.tiles = [{"z": 0, "y": 2, "x": 3, "text": "A"}, (0, 5, 6, "B"), (4.0, 5.0, "C")]
    w = _section(qtbot, m, labels_source="labels")
    texts = sorted(e.text for e in _entries(w, "text"))
    assert texts == ["A", "B", "C"]


def test_the_fitted_circle_is_an_ellipse_of_the_fitted_radius(qtbot):
    m = Model()
    m.circle = {"x": 30.0, "y": 10.0, "r": 4.0, "z": 0}
    w = _section(qtbot, m, roi_source="circle_source")
    (circle,) = _entries(w, "roi")
    assert circle.state["roi_kind"] == "ellipse"
    assert circle.pos == (26.0, 6.0) and circle.size == (8.0, 8.0)
    assert not circle.movable
    m.circle = None
    w.refresh()
    assert _entries(w, "roi") == []


def test_the_gate_reports_a_region_when_the_drag_ends(qtbot):
    m = Model(np.zeros((20, 60)))
    w = _section(qtbot, m, region_call="gate")
    (gate,) = _entries(w, "roi")
    assert gate.pos == (15.0, 5.0) and gate.size == (30.0, 10.0), "central half, x a column"
    assert gate.state["resizable"]
    gate.set_pos((2.0, 3.0))
    gate.set_size((6.0, 4.0))
    assert m.gates == [], "programmatic moves do not report"
    gate._notify(final=True)
    (roi,) = m.gates
    assert (roi.x0, roi.y0, roi.x1, roi.y1) == (2.0, 3.0, 8.0, 7.0)


def test_the_gate_follows_the_models_region(qtbot):
    from chisurf.core.roi import RectangleROI

    m = Model(np.zeros((20, 60)))
    m.region = RectangleROI(10, 4, 20, 8, name="g")
    w = _section(qtbot, m, region_call="gate", region_source="region_source")
    (gate,) = _entries(w, "roi")
    assert gate.pos == (10.0, 4.0) and gate.size == (10.0, 4.0)


def test_an_extent_puts_the_map_on_its_quantity_axes(qtbot):
    m = Model(np.zeros((10, 10)))
    m.span = (0.0, 1.0, 0.0, 8.0)
    w = _section(
        qtbot,
        m,
        extent_source="extent",
        axes_visible=True,
        x_label="E",
        y_label="tau [ns]",
        invert_y=False,
        aspect_locked=False,
    )
    canvas = w.view.native
    assert _entries(w, "image")[0].state["rect"] == (0.0, 0.0, 1.0, 8.0)
    assert canvas._labels["bottom"] == "E" and canvas._labels["left"] == "tau [ns]"
    assert canvas._y_inverted is False and canvas._aspect is None
    assert w.view.pixel_at(0.55, 4.0) == (5, 5)


def test_a_swapped_array_keeps_the_extent_and_the_users_zoom(qtbot):
    m = Model(np.zeros((10, 10)))
    m.span = (0.0, 1.0, 0.0, 8.0)
    w = _section(qtbot, m, extent_source="extent", axes_visible=True)
    w.view.native.set_range(x=(0.2, 0.4), y=(1.0, 2.0))
    m.img = np.ones((10, 10))
    w.refresh()
    assert _entries(w, "image")[0].state["rect"] == (0.0, 0.0, 1.0, 8.0)
    assert w.view.view_range()[0] == (0.2, 0.4), "the zoom is the user's"


def test_a_bare_picture_has_no_axes_and_square_pixels_by_default(qtbot):
    w = _section(qtbot, Model())
    canvas = w.view.native
    assert canvas._axis_visible == {"left": False, "bottom": False}
    assert canvas._aspect == 1.0 and canvas._y_inverted is True


def test_the_section_is_a_region_overlay_surface(qtbot):
    from chisurf.core.roi import EllipseROI, PolygonROI, RectangleROI, RegionCollection
    from chisurf.gui.widgets.roi import RegionOverlay

    m = Model()
    m.regions = RegionCollection()
    m.regions.add(RectangleROI(5, 4, 15, 8, name="r"))
    m.regions.add(EllipseROI(30, 10, 4, 3, name="e"))
    m.regions.add(PolygonROI([(40, 2), (50, 2), (45, 9)], name="p"))
    w = _section(qtbot, m)
    overlay = RegionOverlay(w, lambda: m.regions)
    overlay.refresh()
    assert len(overlay._handles) == 3
    assert sorted(e.state["roi_kind"] for e in _entries(w, "roi")) == [
        "ellipse",
        "polygon",
        "rect",
    ]
