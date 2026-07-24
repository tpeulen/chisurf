"""Construction + behaviour tests for the chiplot plotting API.

These run headlessly (offscreen Qt) and exercise the whole public surface
against the default (pyqtgraph) backend, so a backend swap can be validated by
re-running the same tests.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytestmark = pytest.mark.gui

qtpy = pytest.importorskip("qtpy")
pytest.importorskip("pyqtgraph")

from qtpy import QtWidgets  # noqa: E402

from chisurf.gui import chiplot as cp  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def test_style_coercion():
    assert cp.to_color("red").as_tuple() == (255, 0, 0, 255)
    assert cp.to_color("#00ff00").as_tuple() == (0, 255, 0, 255)
    assert cp.to_color((1.0, 0.0, 0.0)).as_tuple() == (255, 0, 0, 255)
    assert cp.to_color((0, 0, 255)).as_tuple() == (0, 0, 255, 255)
    assert cp.to_color(0xFF0000).as_tuple() == (255, 0, 0, 255)
    pen = cp.to_pen("blue", width=3)
    assert pen.width == 3 and pen.color.as_tuple() == (0, 0, 255, 255)
    assert cp.int_color(0) != cp.int_color(3)


def test_plot_draw_all_families(qapp):
    x = np.linspace(0, 10, 50)
    y = np.sin(x)
    plot = cp.Plot(title="t")
    curve = plot.line(x, y, pen="red", width=2, name="sine")
    marked = plot.line(x, y, pen="#2f80ed", symbol="o", symbol_size=5, symbol_brush="#2f80ed")
    assert isinstance(marked, cp.handles.Curve)
    marked.set_data(x, np.cos(x))
    sc = plot.scatter(x, y, size=5, brush="g", symbol="o")
    bars = plot.bars(x[:5], np.abs(y[:5]), width=0.1)
    eb = plot.errorbars(x[:5], y[:5], height=np.full(5, 0.1))
    img = plot.image(np.random.rand(8, 8), colormap="viridis", levels=(0, 1))
    reg = plot.region((2.0, 4.0), movable=True)
    vline = plot.vline(5.0, movable=True)
    txt = plot.text("hi", (1.0, 0.5), draggable=True)
    plot.legend()
    plot.set_labels(left="a", bottom="b").set_log(y=False).grid(x=True, y=True)

    # handles conform to their protocols
    assert isinstance(curve, cp.handles.Curve)
    assert isinstance(sc, cp.handles.Scatter)
    assert isinstance(reg, cp.handles.Region)
    assert isinstance(vline, cp.handles.Marker)
    assert isinstance(img, cp.handles.Image)
    assert isinstance(txt, cp.handles.Text)

    # updates
    curve.set_data(x, np.cos(x))
    sc.set_data(x, np.cos(x))
    bars.set_data(x[:5], np.abs(np.cos(x[:5])))
    eb.set_data(x[:5], np.cos(x[:5]), height=np.full(5, 0.2))
    img.set_image(np.random.rand(4, 4))


def test_region_and_marker_values(qapp):
    plot = cp.Plot()
    reg = plot.region((1.0, 3.0))
    assert reg.bounds == (1.0, 3.0)
    reg.set_bounds(2.0, 5.0)
    assert reg.bounds == (2.0, 5.0)

    seen = []
    reg.on_change(lambda lo, hi: seen.append((lo, hi)), final=False)
    reg.native.setRegion((0.0, 1.0))  # simulate a drag through the native item
    assert seen and seen[-1] == (0.0, 1.0)

    m = plot.vline(4.0, movable=True)
    assert m.value == 4.0
    m.set_value(6.5)
    assert m.value == 6.5


def test_handle_visibility_and_removal(qapp):
    plot = cp.Plot()
    c = plot.line([0, 1], [0, 1])
    c.visible = False
    assert c.visible is False
    c.visible = True
    c.hide()
    assert c.visible is False
    c.show()
    assert c.visible is True
    c.z = 5
    assert c.z == 5
    c.remove()
    plot.add(c)  # re-add round-trips
    plot.clear()


def test_fill_between_band(qapp):
    import numpy as np

    plot = cp.Plot()
    x = np.linspace(0, 1, 10)
    lo = plot.line(x, x - 0.1)
    hi = plot.line(x, x + 0.1)
    band = plot.fill_between(lo, hi, brush=(47, 128, 237, 70))
    assert isinstance(band, cp.handles.Handle)
    band.visible = False
    band.remove()


def test_curve_get_data_roundtrip(qapp):
    import numpy as np

    plot = cp.Plot()
    x = np.arange(5, dtype=float)
    c = plot.line(x, x ** 2)
    gx, gy = c.get_data()
    assert list(gx) == list(x)
    assert list(gy) == list(x ** 2)


def test_grid_panels(qapp):
    grid = cp.Grid()
    p0 = grid.add_plot(row=0, col=0, title="top")
    p1 = grid.add_plot(row=1, col=0, title="bottom")
    p0.line([0, 1, 2], [0, 1, 0], pen="c")
    p1.scatter([0, 1, 2], [1, 0, 1], brush="m")
    assert isinstance(p0, cp.Plot) and isinstance(p1, cp.Plot)


def test_image_view_and_roi(qapp):
    import numpy as np

    iv = cp.ImageView()
    iv.set_image(np.random.rand(16, 16))
    iv.set_image(np.random.rand(4, 8, 8), axes={"t": 0, "y": 1, "x": 2})  # stack
    iv.set_colormap("viridis")
    iv.set_histogram_width(120)
    iv.set_interactive(mouse=False, menu=False)
    overlay = iv.add_overlay(np.zeros((8, 8, 4), dtype=np.uint8))
    assert isinstance(overlay, cp.handles.Image)

    roi = iv.add_roi(kind="rect", pos=(1, 2), size=(3, 4), pen="y")
    assert isinstance(roi, cp.handles.Roi)
    assert roi.pos == (1.0, 2.0)
    assert roi.size == (3.0, 4.0)
    roi.set_pos(5, 6)
    roi.set_size(7, 8)
    assert roi.pos == (5.0, 6.0)
    assert roi.size == (7.0, 8.0)
    seen = []
    roi.on_change(lambda: seen.append(roi.pos), final=False)
    roi.native.setPos((2.0, 2.0))
    assert seen  # fired
    roi.visible = False
    roi.z = 10
    iv.clear()


def test_export_csv_from_series(qapp, tmp_path):
    import numpy as np

    plot = cp.Plot()
    x = np.arange(4, dtype=float)
    plot.line(x, x * 2, name="a")
    plot.scatter(x, x + 1, name="b")
    out = tmp_path / "series.csv"
    plot.export_csv(str(out))
    text = out.read_text()
    assert "a x" in text and "a y" in text and "b x" in text and "b y" in text
    # 4 data rows + 1 header
    assert len(text.strip().splitlines()) == 5


def test_context_menu_and_custom_action(qapp):
    plot = cp.Plot()
    fired = []
    plot.add_menu_action("Do thing", lambda: fired.append(True))
    plot.set_context_menu_enabled(True)
    # The extra action is registered; invoke its callback directly.
    assert plot._extra_menu_actions[0][0] == "Do thing"
    plot._extra_menu_actions[0][1]()
    assert fired == [True]
    plot.clear()  # resets series tracking
    assert plot._series == []


def test_clicked_signal_wired(qapp):
    plot = cp.Plot()
    got = []
    plot.clicked.connect(lambda x, y: got.append((x, y)))
    # Just ensure the signal exists and is connectable; emit synthetically.
    plot.clicked.emit(1.0, 2.0)
    assert got == [(1.0, 2.0)]


def test_module_passthrough_flags_and_works(qapp):
    import pyqtgraph as pg

    cp.reset_gaps()
    with pytest.warns(cp.ChiplotPassthroughWarning):
        pen = cp.mkPen("r", width=2)  # not native -> falls through to pyqtgraph
    assert isinstance(pen, pg.functions.mkPen("r").__class__)
    # a class symbol falls through too
    with pytest.warns(cp.ChiplotPassthroughWarning):
        assert cp.LinearRegionItem is pg.LinearRegionItem
    assert "module.mkPen" in cp.passthrough_gaps()
    assert "module.LinearRegionItem" in cp.passthrough_gaps()


def test_module_passthrough_warns_once(qapp, recwarn):
    cp.reset_gaps()
    cp.mkBrush("g")
    cp.mkBrush("g")  # second access: no new warning
    passthrough_warnings = [w for w in recwarn if issubclass(w.category, cp.ChiplotPassthroughWarning)]
    assert len(passthrough_warnings) == 1


def test_handle_passthrough_parity(qapp):
    # A pyqtgraph item method chiplot doesn't expose natively still works on the
    # handle, flagged as a passthrough gap.
    cp.reset_gaps()
    plot = cp.Plot()
    curve = plot.line([0, 1, 2], [0, 1, 0])
    with pytest.warns(cp.ChiplotPassthroughWarning):
        curve.setDownsampling(auto=True)  # pyqtgraph PlotDataItem method
    assert any(g.startswith("Curve.") for g in cp.passthrough_gaps())


def test_colormap_hybrid_parity(qapp):
    import pyqtgraph as pg

    # chiplot API: returns a chiplot Colormap reference
    assert isinstance(cp.colormap("viridis"), cp.Colormap)
    # pyqtgraph parity: cp.colormap.get(...) proxies to pg.colormap.get(...)
    cm = cp.colormap.get("CET-L4")
    assert isinstance(cm, pg.ColorMap)


def test_handle_setattr_forwards_to_native(qapp):
    plot = cp.Plot()
    c = plot.line([0, 1], [0, 1])
    c.customFlag = 99  # arbitrary attr assignment
    assert getattr(c.native, "customFlag", None) == 99  # landed on the native item
    assert c.customFlag == 99  # and reads back


def test_handle_truthiness_and_container_parity(qapp):
    plot = cp.Plot()
    c = plot.line([0, 1], [0, 1])
    assert bool(c) is True  # a live handle is always truthy
    if not c:  # exercises the truthiness path
        raise AssertionError("handle should be truthy")
    s = plot.scatter([0, 1, 2], [0, 1, 2])
    # ScatterPlotItem isn't sized -> len forwards the native TypeError
    with pytest.raises(TypeError):
        len(s)


def test_unknown_symbol_raises(qapp):
    with pytest.raises(AttributeError):
        cp.this_symbol_does_not_exist_anywhere


def test_instance_passthrough_to_native(qapp):
    cp.reset_gaps()
    plot = cp.Plot()
    with pytest.warns(cp.ChiplotPassthroughWarning):
        vb = plot.getViewBox()  # pyqtgraph-only method, not native chiplot
    assert vb is plot.native.getViewBox()
    assert "Plot.getViewBox" in cp.passthrough_gaps()
