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


def test_arrow_angle_convention(qapp):
    """``Plot.arrow`` places the tip and aims in chiplot's convention (RF-141).

    chiplot measures the pointing angle counter-clockwise from ``+x``; the
    pyqtgraph arrow is drawn at ``0`` pointing left and rotates clockwise on
    screen, so the backend must convert. Getting that wrong silently mirrors
    every directed edge (a rate arrow between two states pointing the wrong way
    reads as the reverse transition).
    """
    plot = cp.Plot()
    arrow = plot.arrow(2.0, 3.0, angle=45.0, size=18, brush="r")

    assert isinstance(arrow, cp.handles.Arrow)
    assert arrow.position == (2.0, 3.0)
    assert arrow.angle == pytest.approx(45.0)
    # pyqtgraph's own convention, as converted by the backend.
    assert arrow.native.opts["angle"] == pytest.approx(135.0)

    arrow.set_angle(-90.0)
    assert arrow.angle == pytest.approx(-90.0)
    assert arrow.native.opts["angle"] == pytest.approx(270.0)

    arrow.set_position(-1.0, 0.5)
    assert arrow.position == (-1.0, 0.5)

    plot.remove(arrow)
    assert arrow.native not in plot.native.items


def test_arrow_from_edge_direction(qapp):
    """An edge ``(x0, y0) -> (x1, y1)`` arrows with ``degrees(arctan2(dy, dx))``.

    This is the documented call-site idiom; the tip must sit on the edge's end
    point and face along the segment for any quadrant.
    """
    plot = cp.Plot()
    for x0, y0, x1, y1 in ((0, 0, 1, 1), (0, 0, -1, 1), (0, 0, -1, -1), (0, 0, 1, -1)):
        ang = float(np.degrees(np.arctan2(y1 - y0, x1 - x0)))
        arrow = plot.arrow(x1, y1, angle=ang)
        assert arrow.position == (float(x1), float(y1))
        assert arrow.angle == pytest.approx(ang)


def test_text_does_not_drive_autorange(qapp):
    """A text annotation must not blow the view auto-range (PRD-64 Batch 22).

    Text items are added with ignoreBounds=True; a label placed at a far data
    coordinate (e.g. a raw value on a log axis) must not stretch the range.
    """
    x = np.logspace(-2, 3, 60)
    y = 1.0 + 0.8 * np.exp(-x / 2.0)
    plot = cp.Plot()
    plot.set_log(x=True, y=False)
    plot.line(x, y, pen="w")
    plot.text("inset", (float(x.max()), float(y.max())), color="y")  # raw coord on log-x
    plot.autoscale()
    (x0, x1) = plot.native.getViewBox().viewRange()[0]
    # log10(data-x) spans -2..3; the text at raw x=1000 would push x1 to ~1000
    # without ignoreBounds. Assert the range stays near the data.
    assert x1 < 10.0, f"text drove the x auto-range out (x1={x1})"


def test_scatter_is_log_aware(qapp):
    """Scatter points must transform under log mode (PRD-64 Batch 20 fix).

    A raw pyqtgraph ScatterPlotItem ignores log mode and would leave the view
    auto-ranged at the linear default (~[0,1]); a log-aware PlotDataItem makes
    the view span the data's log10 range.
    """
    x = np.logspace(-3, 1, 60)
    y = np.exp(-x / 0.5) * 1000 + 5  # ~5 .. ~1000
    plot = cp.Plot()
    plot.set_log(x=True, y=True)
    plot.scatter(x, y, size=3, brush=(60, 120, 200, 90), symbol="o")
    plot.autoscale()
    (y0, y1) = plot.native.getViewBox().viewRange()[1]
    # log10(data) spans ~0.7 .. 3.0; a linear-default view would be ~[0, 1].
    assert y1 > 2.0, f"scatter did not autorange under log mode (y1={y1})"


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


def test_legend_idempotent_refresh_loop(qapp):
    """A clear -> legend -> redraw refresh loop must not stack legends.

    Regression guard for PRD-64 Batch 9: the curve-viewer tools
    (tttr_histogram / tttr_correlate / microtime_histogram / fcs merger) call
    ``legend()`` on every refresh, so it must remove the prior legend rather
    than orphan a new box each time.
    """
    plot = cp.Plot()
    pi = plot.native  # the pyqtgraph PlotItem
    for i in range(4):
        plot.clear()
        plot.legend()
        plot.line([0, 1, 2], [i, i + 1, i], name=f"c{i}")
    # Exactly one legend survives the repeated refresh.
    assert pi.legend is not None
    scene_legends = [
        it for it in pi.scene().items()
        if it.__class__.__name__ == "LegendItem"
    ]
    assert len(scene_legends) == 1


def test_set_menu_enabled_returns_self(qapp):
    """``set_menu_enabled`` toggles the native menu and chains (returns self)."""
    plot = cp.Plot()
    assert plot.set_menu_enabled(False) is plot
    assert plot.set_menu_enabled(True) is plot


def test_link_x_shares_range(qapp):
    """link_x makes two panels share their x-range (PRD-64 linked-panel family).

    Stacked TCSPC diagnostics (residuals above data) must pan/zoom together.
    """
    a = cp.Plot()
    b = cp.Plot()
    a.line([0, 1, 2], [0, 1, 0])
    b.line([0, 1, 2], [1, 0, 1])
    assert a.link_x(b) is a
    b.native.getViewBox().setXRange(0.4, 0.6)
    ax0, ax1 = a.native.getViewBox().viewRange()[0]
    assert ax0 < 0.7 and ax1 > 0.3  # a followed b's zoom, not its own autorange


def test_text_fill_border(qapp):
    """text() accepts a background fill + border box (PRD-64 Batch 29).

    The lineplot fit-quality overlay is a boxed, draggable label.
    """
    plot = cp.Plot()
    t = plot.text(
        "chi2 = 1.0", (1.0, 1.0), color="#FF0", anchor=(0, 0),
        draggable=True, fill=(0, 0, 255, 100), border="w",
    )
    assert isinstance(t, cp.handles.Text)
    t.text = "chi2 = 2.0"
    assert "2.0" in t.text


def test_set_axis_visible_returns_self(qapp):
    """``set_axis_visible`` toggles individual axes and chains (returns self).

    Regression guard for PRD-64 Batch 26 (proteinMC network diagram), which
    hides both axes for a bare canvas.
    """
    plot = cp.Plot()
    assert plot.set_axis_visible(left=False, bottom=False) is plot
    assert plot.set_axis_visible(left=True, bottom=True, right=False, top=False) is plot


def test_set_interactive_returns_self(qapp):
    """``set_interactive`` toggles mouse+menu on a Plot and chains.

    Regression guard for PRD-64 Batch 16 (lightpath node thumbnails), which
    build static preview plots with neither pan/zoom nor a context menu.
    """
    plot = cp.Plot()
    assert plot.set_interactive(mouse=False, menu=False) is plot
    assert plot.set_interactive(mouse=True, menu=True) is plot


def test_programmatic_set_bounds_is_signal_safe(qapp):
    """A programmatic ``set_bounds`` must not re-enter the on_change callback.

    Regression guard for PRD-64 Batch 9: filter_panel positions a draggable
    region from the model on every refresh; that must not feed back into the
    handler that writes the model (the old code hand-managed ``blockSignals``).
    """
    plot = cp.Plot()
    reg = plot.region((1.0, 3.0), orientation="horizontal", movable=True)
    seen = []
    reg.on_change(lambda lo, hi: seen.append((lo, hi)), final=True)
    reg.set_bounds(2.0, 5.0)  # programmatic move -> must stay silent
    assert seen == []
    assert reg.bounds == (2.0, 5.0)
    # A genuine (native) drag still fires the callback.
    reg.native.setRegion((0.5, 0.9))
    assert seen and seen[-1] == (0.5, 0.9)


def test_programmatic_set_value_is_signal_safe(qapp):
    """A programmatic ``set_value`` must not re-enter the marker on_change."""
    plot = cp.Plot()
    m = plot.vline(4.0, movable=True)
    seen = []
    m.on_change(lambda pos: seen.append(pos), final=True)
    m.set_value(6.5)  # programmatic move -> silent
    assert seen == []
    assert m.value == 6.5
    # Simulate a user drag completing on the native item (setValue alone does
    # not emit the finished signal; a real drag release does).
    m.native.setValue(1.25)
    m.native.sigPositionChangeFinished.emit(m.native)
    assert seen and seen[-1] == 1.25


def test_migrated_panel_draw_patterns(qapp):
    """Exercise the exact draw verbs the PRD-64 Batch 9 panels rely on.

    Covers: scatter(size/brush/pen), line(style="dash"), a horizontal region
    with set_bounds, set_menu_enabled, and the legend refresh loop — the union
    of calls made by fcs_correlator's filter/merger panels and the tttr
    histogram/correlate tools.
    """
    plot = cp.Plot(title="panel")
    plot.set_labels(bottom="t", left="G").set_log(x=True)
    plot.set_menu_enabled(False)
    plot.legend()
    x = np.linspace(0, 1, 20)
    plot.scatter(x, x, size=2, brush=(80, 180, 255, 200), pen=None, symbol="o", name="pts")
    plot.line(x, x ** 2, pen="y", width=1, style="dash", name="dashed")
    plot.line(x, x, pen=cp.int_color(0, count=6).as_tuple(), width=1, name="int-color")
    reg = plot.region((0.1, 0.9), orientation="horizontal", brush=(80, 180, 255, 40), movable=True)
    reg.set_bounds(0.2, 0.8)
    assert reg.bounds == (0.2, 0.8)


def test_grid_panel_region_and_markers(qapp):
    """A Grid panel supports region/vline/hline + signal-safe redraw syncs.

    Regression guard for PRD-64 Batch 12 (tttr_lut_tools compute section): the
    draggable items live on a ``PanelPlot`` inside a ``Grid``, and a redraw
    repositions them via ``set_bounds``/``set_value`` without re-entering the
    drag handlers.
    """
    grid = cp.Grid()
    panel = grid.add_plot(row=0, col=0, title="raw")
    reg = panel.region((10.0, 40.0), brush=(255, 165, 0, 60), movable=True)
    vline = panel.vline(5.0, movable=True, pen=cp.to_pen((200, 0, 0), width=2))
    hline = panel.hline(20.0, movable=True, pen=cp.to_pen((0, 180, 0), width=2))
    fired = []
    reg.on_change(lambda lo, hi: fired.append(("r", lo, hi)), final=True)
    vline.on_change(lambda p: fired.append(("v", p)), final=True)
    hline.on_change(lambda p: fired.append(("h", p)), final=True)
    # Programmatic redraw-style sync: all silent.
    reg.set_bounds(12.0, 35.0)
    vline.set_value(7.0)
    hline.set_value(22.0)
    assert fired == []
    assert reg.bounds == (12.0, 35.0)
    assert vline.value == 7.0 and hline.value == 22.0
    # Replace-only-the-curve pattern: draw, remove, redraw keeps the items.
    curve = panel.line([0, 1, 2], [1, 2, 1], pen=cp.to_pen((255, 204, 0), width=1.5))
    panel.remove(curve)
    panel.line([0, 1, 2], [2, 1, 2], pen=cp.to_pen((255, 204, 0), width=1.5))
    assert reg.bounds == (12.0, 35.0)  # region survived the curve churn


def test_pt_plot_widget_renders(qapp):
    """The node-editor PtPlotWidget builds a chiplot curve and accepts data.

    Regression guard for PRD-64 Batch 18: the themed node plot must construct
    with a chiplot backend, expose a live curve, and round-trip set_data.
    """
    from chisurf.gui.widgets.node_editor.widgets.pt_plot_widget import PtPlotWidget

    w = PtPlotWidget("Damped sine")
    assert isinstance(w._curve, cp.handles.Curve)
    x = np.linspace(0, 12, 200)
    y = np.exp(-0.25 * x) * np.sin(3.0 * x)
    w.set_data(x, y)
    gx, gy = w._curve.get_data()
    assert len(gx) == 200 and len(gy) == 200
    w.clear()
    gx, _ = w._curve.get_data()
    assert gx is None or len(gx) == 0  # empty curve -> None or zero-length


def test_spectrum_view_plots_traces(qapp):
    """SpectrumView.plot_series draws one chiplot curve per trace + styles.

    Regression guard for PRD-64 Batch 19: the reusable spectrum widget maps
    trace dicts (color/style/width) onto chiplot ``line`` calls.
    """
    from chisurf.gui.widgets.spectrum_view import SpectrumView

    v = SpectrumView()
    wl = np.linspace(400, 700, 50)
    v.plot_series([
        {"name": "abs", "x": wl, "y": np.ones_like(wl), "color": (0, 100, 200), "style": "solid"},
        {"name": "em", "x": wl, "y": np.ones_like(wl), "color": (200, 0, 0), "style": "dash"},
        {"name": "dot", "x": wl, "y": np.ones_like(wl), "color": (145, 30, 180), "style": "dot"},
    ])
    assert len(v.plot._series) == 3
    v.plot_series([])  # empty -> placeholder, no crash
    assert v.plot._series == []


def test_migrated_modules_import(qapp):
    """The migrated Batch 9 modules import cleanly (no pyqtgraph dependency)."""
    import importlib

    for name in (
        "chisurf.plugins.tttr.tttr_histogram.gui",
        "chisurf.plugins.tttr.tttr_correlate.gui",
        "chisurf.plugins.tttr.microtime_histogram.wizard",
        "chisurf.plugins.fcs.fcs_correlator.correlator_panel",
        "chisurf.plugins.fcs.fcs_correlator.filter_panel",
        "chisurf.plugins.fcs.fcs_correlator.merger_panel",
        # Batch 11
        "chisurf.plugins.fcs.fcs_lfcs_sim.gui.tool",
        "chisurf.plugins.fluorescence_decay.tr_anisotropy.gui.irf_widget",
        "chisurf.plugins.vv_vh_anisotropy",
        # Batch 12
        "chisurf.plugins.tttr.tttr_lut_tools.gui.sections",
        # Batch 13
        "chisurf.plugins.tttr.tttr_lut_tools.gui.settings_panel",
        # Batch 14
        "chisurf.gui.autoform.sections.decay_conv_section",
        "chisurf.gui.widgets.wizard.fcs_merger.fcs_merger_ui",
        "chisurf.gui.widgets.wizard.fcs_merger.fcs_merger",
        # Batch 15
        "chisurf.plugins.modelling.fret.gui.dock_tool",
        "chisurf.plugins.modelling.fret.gui.pair_selection_wizard",
        # Batch 16
        "chisurf.plugins.core.lightpath_simulator.gui.node_types",
        # Batch 17
        "chisurf.plugins.burst.burst_2cde.gui.tool",
        # Batch 18
        "chisurf.gui.widgets.node_editor.widgets.pt_plot_widget",
        # Batch 19
        "chisurf.gui.widgets.spectrum_view",
        # Batch 20
        "chisurf.plugins.burst.burst_background.gui.sections",
        # Batch 21
        "chisurf.plugins.burst.burst_browser.gui.sections",
        # NB: burst_fcs_correlator.wizard (Batch 22) is intentionally NOT listed —
        # it imports IMP, which segfaults when loaded alongside the other heavy
        # extensions in this shared test process. It is verified to import
        # standalone + screenshot-checked instead.
        # Batch 23
        "chisurf.plugins.burst.burst_selection.gui.legacy.burst_selector",
        # NB: irf_estimator.gui.tool (Batch 24) is intentionally NOT listed — like
        # burst_fcs_correlator it transitively imports IMP, which segfaults in this
        # shared test process. Verified standalone + screenshot-checked instead.
        # Batch 25
        "chisurf.gui.plots.parameter_scan.parameter_scan",
        # Batch 26
        "chisurf.gui.plots.proteinMC",
        # Batch 27
        "chisurf.gui.plots._qwt_compat",
        "chisurf.gui.plots.global_tcspc.global_tcspc",
        # NB: surfaceplot was deleted with the orphan sweep (Batch 31) — the
        # module is gone, so it cannot be checked for import cleanliness here.
        # Batch 28
        "chisurf.plugins.fcs.fcs_filter_calculator.gui_parts.main_window",
        # Batch 32
        "chisurf.gui.plots.residual_image",
        # Batch 33
        "chisurf.plugins.fluorescence_decay.maxent_decay.gui.gui",
    ):
        assert importlib.import_module(name) is not None


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


def test_curve_set_pen_restyles(qapp):
    """Curve.set_pen restyles a live curve (accepts Pen or pen-like).

    Regression guard for PRD-64 Batch 13 (tttr_lut_tools settings panel), which
    re-colours and emphasises per-channel curves via set_pen.
    """
    plot = cp.Plot()
    c = plot.line([0, 1, 2], [0, 1, 0], pen="w")
    c.set_pen(cp.to_pen((255, 0, 0), width=4))  # Pen object
    c.set_pen("g")  # pen-like string
    c.set_pen((0, 0, 255))  # rgb tuple
    # z-order is settable (used for emphasis)
    c.z = 10
    assert c.z == 10


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


def test_curve_set_opacity(qapp):
    """Curve.set_opacity sets whole-curve opacity (replaces the old 4-method
    pyqtgraph transparency fallback used by the grouped LinePlot)."""
    plot = cp.Plot()
    c = plot.line([0, 1, 2], [0, 1, 0])
    c.set_opacity(0.4)
    assert abs(float(c.native.opacity()) - 0.4) < 1e-6
    c.set_opacity(1.0)
    assert abs(float(c.native.opacity()) - 1.0) < 1e-6


def test_curve_symbol_setters(qapp):
    """Curve.set_symbol/set_symbol_size/set_symbol_brush drive point markers.

    Backs LinePlot's ``curve_styles`` path (e.g. the PCH model draws data as
    open circles with no connecting line).
    """
    plot = cp.Plot()
    c = plot.line([0, 1, 2], [0, 1, 0])
    c.set_symbol("o")
    c.set_symbol_size(6)
    c.set_symbol_brush("r")
    assert c.native.opts["symbol"] == "o"
    assert c.native.opts["symbolSize"] == 6
    # Clearing the symbol (and the line) is supported too.
    c.set_symbol(None)
    assert c.native.opts["symbol"] is None
    c.set_pen(None)  # no_line style
    assert c.native.opts["pen"] is None or c.native.opts["pen"].style() == qtpy.QtCore.Qt.NoPen


def test_region_set_limits_constrains_drag(qapp):
    """Region.set_limits bounds the draggable range (pyqtgraph setBounds), which
    is distinct from set_bounds (the current position) and must be signal-safe."""
    plot = cp.Plot()
    reg = plot.region((2.0, 4.0), movable=True)
    seen = []
    reg.on_change(lambda lo, hi: seen.append((lo, hi)), final=True)
    reg.set_limits(0.0, 10.0)  # programmatic -> silent
    assert seen == []
    # A drag beyond the limit is clamped to it.
    reg.native.setRegion((-5.0, 4.0))
    lo, _ = reg.bounds
    assert lo >= 0.0 - 1e-9


def test_anchored_text_is_screen_pinned(qapp):
    """text(anchored=True) parents to the PlotItem (fixed screen offset) rather
    than living at a data coordinate — the LinePlot fit-quality overlay."""
    plot = cp.Plot()
    data_txt = plot.text("data", (1.0, 2.0))
    anchored_txt = plot.text("pinned", (10, 0), anchored=True, draggable=True)
    # The anchored label's parent is the PlotItem itself; the data label's is not.
    assert anchored_txt.native.parentItem() is plot.native
    assert data_txt.native.parentItem() is not plot.native
    # The text property setter keeps working through the handle.
    anchored_txt.text = "updated"
    assert anchored_txt.native.toPlainText() == "updated"


def test_line_step_string_modes(qapp):
    """line(step=...) accepts the equal-length pyqtgraph step modes as strings.

    ``step=True`` maps to centered bins (needs ``len(x) == len(y) + 1``) while
    ``"left"``/``"right"``/``"center"`` keep x and y the same length — the mode
    the DistributionPlot histograms (data/model) use, together with a fill.
    """
    plot = cp.Plot()
    x = [0.0, 1.0, 2.0, 3.0]
    y = [1.0, 3.0, 2.0, 0.0]
    # Equal-length "right" step must not raise (a bare True would demand N+1).
    c = plot.line(x, y, step="right", pen="b", fill=(0, 0, 255, 127))
    assert c.native.opts["stepMode"] == "right"
    # The fill brush survives to the backend item.
    assert c.native.opts["fillLevel"] == 0.0
    assert c.native.opts["fillBrush"].color().alpha() == 127


def test_errorbars_set_data_replaces_extents(qapp):
    """set_data replaces the extents rather than merging them.

    pyqtgraph's ``ErrorBarItem.setData`` only updates the keys it is handed and
    lets a stale ``height`` override ``top``/``bottom``. A handle created with
    ``height`` and later updated with ``top``/``bottom`` therefore kept the old
    ``height`` and — with a different point count — crashed while painting
    (BVA proximity-ratio profile: ``height`` of length 0 vs. 31 points).
    """
    plot = cp.Plot()
    eb = plot.errorbars(np.array([]), np.array([]), height=np.array([]), beam=0.01)

    x = np.linspace(0.0, 1.0, 31)
    y = np.sin(x)
    sd = np.full(31, 0.05)
    eb.set_data(x, y, top=sd, bottom=sd)

    assert eb.native.opts["height"] is None
    assert len(eb.native.opts["top"]) == 31
    eb.native.drawPath()  # would raise a broadcast ValueError with a stale height

    # ...and the other way round: switching back to symmetric clears top/bottom.
    eb.set_data(x, y, height=np.full(31, 0.1))
    assert eb.native.opts["top"] is None and eb.native.opts["bottom"] is None
    eb.native.drawPath()


def test_grid_colorbar_binds_image(qapp):
    """Grid.add_colorbar replaces the pyqtgraph HistogramLUTItem passthrough."""
    grid = cp.Grid()
    plot = grid.add_plot(row=0, col=0)
    img = plot.image(np.random.rand(8, 8), axis_order="col-major")

    bar = grid.add_colorbar(img, colormap="CET-L4", row=0, col=1)
    assert isinstance(bar, cp.handles.ColorBar)
    assert bar.native.imageItem() is img.native

    bar.set_levels(0.25, 0.75)
    assert bar.get_levels() == pytest.approx((0.25, 0.75))

    seen = []
    bar.on_levels_changed(lambda lo, hi: seen.append((lo, hi)))
    bar.set_levels(0.0, 1.0)
    assert seen and seen[-1] == pytest.approx((0.0, 1.0))

    bar.set_colormap("viridis")  # a name is accepted as well as a Colormap


def test_to_colormap_coercion():
    assert cp.to_colormap(None) is None
    cm = cp.to_colormap("viridis")
    assert isinstance(cm, cp.Colormap) and cm.name == "viridis"
    assert cp.to_colormap(cm) is cm
    with pytest.raises(TypeError):
        cp.to_colormap(3.5)


def test_mouse_events_are_panel_scoped(qapp):
    """Clicks/motion only reach the panel they happened in (RF-131).

    pyqtgraph's mouse signals are scene-wide and grid panels share one scene, so
    an unscoped handler fired on every panel with a coordinate extrapolated
    through that panel's own view range.
    """
    from qtpy import QtCore

    class _Click:
        """Minimal stand-in for pyqtgraph's MouseClickEvent."""

        def __init__(self, scene_pos):
            self._pos = scene_pos

        def scenePos(self):  # noqa: N802 (Qt spelling)
            return self._pos

        def button(self):
            return QtCore.Qt.LeftButton

    grid = cp.Grid()
    grid.resize(600, 400)
    p0 = grid.add_plot(row=0, col=0)
    p1 = grid.add_plot(row=1, col=0)
    p0.line([0, 1, 2], [0, 1, 0])
    p1.line([0, 1, 2], [0, 500, 0])
    qapp.processEvents()

    seen = []
    p0.clicked.connect(lambda x, y: seen.append(("p0", x, y)))
    p1.clicked.connect(lambda x, y: seen.append(("p1", x, y)))

    target = p1.native.getViewBox().sceneBoundingRect().center()
    grid.native.scene().sigMouseClicked.emit(_Click(target))

    assert [name for name, _, _ in seen] == ["p1"]


def test_line_symbol_uses_renderer_default_colors(qapp):
    """line(symbol=...) with no colours draws a *visible* marker (RF-132)."""
    from qtpy import QtCore

    plot = cp.Plot()
    c = plot.line([0, 1, 2], [0, 1, 0], pen="w", symbol="o", symbol_size=6)
    scatter = c.native.scatter
    assert scatter.opts["brush"].style() != QtCore.Qt.NoBrush
    assert scatter.opts["pen"].style() != QtCore.Qt.NoPen
    # An explicit colour still wins.
    c2 = plot.line([0, 1], [1, 0], symbol="o", symbol_brush="#ff0000")
    assert c2.native.scatter.opts["brush"].color().getRgb()[:3] == (255, 0, 0)


def test_background_paints_whole_widget(qapp):
    """background= paints the axis margins too, and None means transparent (RF-133)."""
    from qtpy import QtCore

    cp.configure(background="k")
    plot = cp.Plot(background="w")
    view = plot._canvas.widget()
    assert view.backgroundBrush().color().getRgb()[:3] == (255, 255, 255)
    assert plot.native.getViewBox().state["background"] == (255, 255, 255, 255)

    transparent = cp.Plot(background=None)
    assert transparent._canvas.widget().backgroundBrush().style() == QtCore.Qt.NoBrush

    # A grid panel must not repaint the widget it shares with its siblings.
    grid = cp.Grid()
    p0 = grid.add_plot(row=0, col=0)
    grid.add_plot(row=1, col=0)
    p0.set_background("w")
    assert grid.native.backgroundBrush().color().getRgb()[:3] != (255, 255, 255)


def test_to_color_float_tuple_detection():
    """Mixed float/int tuples follow the documented <= 1 rule (RF-134)."""
    assert cp.to_color((1.0, 0, 0)).as_tuple() == (255, 0, 0, 255)
    assert cp.to_color((0.5, 0.5, 1)).as_tuple() == (128, 128, 255, 255)
    assert cp.to_color((1.0, 0.0, 0.0)).as_tuple() == (255, 0, 0, 255)
    # Anything above 1 is still the 0-255 scale.
    assert cp.to_color((255, 128, 0)).as_tuple() == (255, 128, 0, 255)


def test_backend_contract_matches_implementation():
    """The abstract Canvas signatures are what the wrapper actually calls (RF-135).

    Also that every abstract method is *implemented*, not merely inherited
    (RF-141): a method added to the contract without a backend body leaves the
    concrete class abstract, and Python only complains at instantiation — i.e.
    when a user opens the tool ("Can't instantiate abstract class _PgCanvas
    without an implementation for abstract method 'add_arrow'"), taking every
    chiplot panel in the application down with it.
    """
    import inspect

    from chisurf.gui.chiplot.backends import base
    from chisurf.gui.chiplot.backends import pyqtgraph_backend as pgb

    for abstract, concrete in (
        (base.Canvas, pgb._PgCanvas),
        (base.GridCanvas, pgb._PgGrid),
        (base.ImageViewCanvas, pgb._PgImageView),
        (base.Backend, pgb.PyQtGraphBackend),
    ):
        unimplemented = sorted(getattr(concrete, "__abstractmethods__", ()))
        assert not unimplemented, f"{concrete.__name__} does not implement {unimplemented}"
        for name, method in vars(abstract).items():
            if not getattr(method, "__isabstractmethod__", False) or isinstance(method, property):
                continue
            expected = set(inspect.signature(method).parameters)
            actual = set(inspect.signature(getattr(concrete, name)).parameters)
            missing = expected - actual
            assert not missing, f"{concrete.__name__}.{name} lacks {sorted(missing)}"


def test_remove_drops_series_from_export(qapp, tmp_path):
    """A removed curve is not exported any more (RF-136)."""
    plot = cp.Plot()
    gone = plot.line([0, 1], [0, 1], name="gone")
    plot.line([0, 1], [1, 0], name="kept")
    plot.remove(gone)

    path = tmp_path / "export.csv"
    plot.export_csv(str(path))
    header = path.read_text().splitlines()[0]
    assert "gone" not in header and "kept" in header


def test_image_view_clear_removes_overlays(qapp):
    """ImageView.clear() takes the overlays/ROIs with it (RF-137)."""
    iv = cp.ImageView()
    iv.set_image(np.random.rand(16, 16))
    overlay = iv.add_overlay(np.zeros((8, 8, 4), dtype=np.uint8))
    roi = iv.add_roi(kind="rect", pos=(1, 2), size=(3, 4), pen="y")
    view = iv.native.getView()
    assert overlay.native in view.addedItems and roi.native in view.addedItems

    iv.clear()
    assert overlay.native not in view.addedItems
    assert roi.native not in view.addedItems


def test_image_restyles_without_reuploading_data(qapp):
    """An image already on the canvas can be re-levelled and recoloured.

    The 2-D residual view drives contrast and colormap from spin boxes and a
    combo box while the data stands still, so both must be settable on the
    handle rather than only through ``set_image``.

    ``RdBu`` is the case that matters: ``pg.colormap.get("RdBu")`` with no
    source raises ``FileNotFoundError`` (it is a matplotlib name, not a
    pyqtgraph one), which is what left every residual image grayscale before
    the port. chiplot resolves the matplotlib namespace first.
    """
    plot = cp.Plot()
    data = np.linspace(-1.0, 1.0, 64).reshape(8, 8)
    img = plot.image(data, axis_order="col-major")

    img.set_levels(-0.5, 0.5)
    assert tuple(img.native.getLevels()) == pytest.approx((-0.5, 0.5))

    img.set_colormap("RdBu")
    assert img.native.lut is not None
    img.set_colormap(None)  # back to the grayscale ramp
    assert img.native.lut is None

    # the data itself is untouched by either restyle
    assert np.array_equal(img.native.image, data)


def test_a_renamed_pyqtgraph_name_says_what_chiplot_calls_it(qapp, recwarn):
    """A rename is not a gap, and the warning must say the replacement.

    ``Plot.plot`` is not a chiplot method, so it falls through to pyqtgraph —
    where a chiplot ``Pen`` is unreadable and dies with an unrelated "not sure
    how to make a color from" deep in the backend. Naming the chiplot spelling
    turns that into a one-line fix.
    """
    import warnings

    from chisurf.gui import chiplot as cp
    from chisurf.gui.chiplot import _passthrough

    _passthrough.reset_gaps()
    plot = cp.Plot()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        plot.plot([0, 1], [0, 1])          # the pyqtgraph spelling
    messages = [str(w.message) for w in caught
                if issubclass(w.category, cp.ChiplotPassthroughWarning)]
    assert messages, "falling through must warn"
    assert "Plot.line" in messages[0], messages[0]
    assert "Plot.plot" in _passthrough.passthrough_gaps()

    # A genuine gap still reads as a gap, not as a rename.
    _passthrough.reset_gaps()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        cp.LinearRegionItem  # noqa: B018 - attribute access is the call
    gap = [str(w.message) for w in caught
           if issubclass(w.category, cp.ChiplotPassthroughWarning)]
    assert gap and "migration gap" in gap[0], gap
