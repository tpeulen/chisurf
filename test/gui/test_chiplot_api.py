"""Construction + behaviour tests for the chiplot plotting API, on the emtk backend.

These run headlessly (offscreen Qt) and exercise the public surface through
chiplot's own verbs and handles. This file was the pyqtgraph-pinned suite;
the tests that asserted on pyqtgraph internals (``PlotDataItem.opts``, the
passthrough seam) went with that backend and the rest run on emtk, which also
has its own drawing-level suite in ``test_chiplot_emtk.py``.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytestmark = pytest.mark.gui

qtpy = pytest.importorskip("qtpy")

from qtpy import QtWidgets  # noqa: E402

from chisurf.chiplot import backends as _backends  # noqa: E402
from chisurf.gui import chiplot as cp  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _emtk_backend():
    """Pin this module to the emtk backend, whatever the environment says."""
    previous = _backends._active
    previous_env = os.environ.get("CHISURF_PLOT_BACKEND")
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


def test_eight_digit_hex_is_rrggbbaa():
    """``#rrggbbaa`` as documented, not Qt's ``#aarrggbb``.

    Qt reads an eight-digit hex as alpha-first, so handing the string straight
    to ``QColor`` swapped alpha into red and returned an opaque colour:
    ``#ff000080`` — red, half transparent — came back as dark blue at full
    alpha, and a translucent region band rendered olive.
    """
    assert cp.to_color("#ff000080").as_tuple() == (255, 0, 0, 128)
    assert cp.to_color("#26a29832").as_tuple() == (38, 162, 152, 50)
    # Six digits are unchanged, and stay opaque.
    assert cp.to_color("#26a298").as_tuple() == (38, 162, 152, 255)


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


def test_there_is_no_passthrough_to_a_backing_library(qapp):
    """chiplot offers what it offers: an unknown name is an error, not a silent fall-through.

    The pyqtgraph backend answered ``getPlotItem``, ``mkPen`` and ``LinearRegionItem``
    by forwarding to the library behind it; with that backend gone a call site
    spelled that way fails where it is written.
    """
    plot = cp.Plot()
    with pytest.raises(AttributeError):
        plot.getPlotItem
    with pytest.raises(AttributeError):
        cp.mkPen
    with pytest.raises(AttributeError):
        cp.LinearRegionItem
    with pytest.raises(AttributeError):
        plot.line([0, 1], [0, 1]).setDownsampling_not_a_chiplot_verb


def test_handle_is_alive_tracks_the_native_item(qapp):
    """``Handle.is_alive`` replaces reaching through ``.native`` for sip checks.

    A call site that asked pyqtgraph directly got "dead" from every other
    backend, so the thing it guarded — the fit-quality overlay — was created
    and then never written there.
    """
    plot = cp.Plot()
    curve = plot.line([0, 1, 2], [0, 1, 0], pen="red")
    assert curve.is_alive() is True
    text = plot.text("hi", (1.0, 0.5))
    assert text.is_alive() is True


def test_set_range_takes_data_units_on_a_log_axis(qapp):
    """``set_ylim`` is data units on every axis, exponents on none.

    A pyqtgraph view in log mode holds exponents, so a call site wrote
    ``set_ylim(log10(lo), log10(hi))`` and it looked right — on that renderer.
    The same code on the native backend drew a decay spanning 0.1 to 4 counts.
    The conversion belongs in the backend; the API cannot be renderer-dependent
    or every caller has to know which one it is talking to.
    """
    plot = cp.Plot()
    plot.line([1.0, 2.0, 3.0], [1.0, 100.0, 10000.0], pen="red")
    plot.set_log(y=True)
    plot.set_ylim(1.0, 10000.0)
    (_, (lo, hi)) = plot.canvas.get_range()
    assert 0.1 <= lo <= 2.0
    assert 5e3 <= hi <= 2e5


def test_menu_enabled_reads_back(qapp):
    """``set_menu_enabled`` has a read side that needs no renderer spelling."""
    plot = cp.Plot()
    plot.set_menu_enabled(True)
    assert plot.menu_enabled() is True
    plot.set_menu_enabled(False)
    assert plot.menu_enabled() is False
    plot.set_interactive(mouse=False, menu=True)
    assert plot.menu_enabled() is True


def test_arrow_angle_convention(qapp):
    """``Plot.arrow`` places the tip and aims in chiplot's convention (RF-141).

    chiplot measures the pointing angle counter-clockwise from ``+x`` in degrees,
    whatever the renderer does internally. Getting that wrong silently mirrors
    every directed edge (a rate arrow between two states pointing the wrong way
    reads as the reverse transition).
    """
    plot = cp.Plot()
    arrow = plot.arrow(2.0, 3.0, angle=45.0, size=18, brush="r")

    assert isinstance(arrow, cp.handles.Arrow)
    assert arrow.position == (2.0, 3.0)
    assert arrow.angle == pytest.approx(45.0)

    arrow.set_angle(-90.0)
    assert arrow.angle == pytest.approx(-90.0)

    arrow.set_position(-1.0, 0.5)
    assert arrow.position == (-1.0, 0.5)

    plot.remove(arrow)
    assert not arrow.is_alive()


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

    A label placed at a far data coordinate (e.g. a raw value on a log axis) must
    not stretch the range: the range is the data's.
    """
    x = np.logspace(-2, 3, 60)
    y = 1.0 + 0.8 * np.exp(-x / 2.0)
    plot = cp.Plot()
    plot.set_log(x=True, y=False)
    plot.line(x, y, pen="w")
    plot.text("inset", (float(x.max()) * 1e6, float(y.max())), color="y")
    plot.autoscale()
    (x0, x1) = plot.canvas.get_range()[0]
    assert x1 < 10.0 * float(x.max()), f"text drove the x auto-range out (x1={x1})"


def test_scatter_is_log_aware(qapp):
    """Scatter points must transform under log mode (PRD-64 Batch 20 fix).

    A scatter that ignored log mode would leave the view auto-ranged at the linear
    default (~[0, 1]); a log-aware one spans the data (here ~5 .. ~1000).
    """
    x = np.logspace(-3, 1, 60)
    y = np.exp(-x / 0.5) * 1000 + 5  # ~5 .. ~1000
    plot = cp.Plot()
    plot.set_log(x=True, y=True)
    plot.scatter(x, y, size=3, brush=(60, 120, 200, 90), symbol="o")
    plot.autoscale()
    (y0, y1) = plot.canvas.get_range()[1]
    assert y1 > 500.0, f"scatter did not autorange under log mode (y1={y1})"


def test_region_and_marker_values(qapp):
    plot = cp.Plot()
    reg = plot.region((1.0, 3.0))
    assert reg.bounds == (1.0, 3.0)
    reg.set_bounds(2.0, 5.0)
    assert reg.bounds == (2.0, 5.0)

    seen = []
    reg.on_change(lambda lo, hi: seen.append((lo, hi)), final=False)
    reg.set_bounds(0.0, 1.0)
    reg.native["callbacks"][0][0](*reg.bounds)  # what a drag does: report where it is
    assert seen and seen[-1] == (0.0, 1.0)

    m = plot.vline(4.0, movable=True)
    assert m.value == 4.0
    m.set_value(6.5)
    assert m.value == 6.5


def test_legend_idempotent_refresh_loop(qapp):
    """A clear -> legend -> redraw refresh loop must not stack legends.

    Regression guard for PRD-64 Batch 9: the curve-viewer tools
    (microtime_histogram / fcs merger) call ``legend()`` on every refresh.
    """
    plot = cp.Plot()
    for i in range(4):
        plot.clear()
        plot.legend()
        plot.line([0, 1, 2], [i, i + 1, i], name=f"c{i}")
    assert plot.canvas._legend is True
    assert [e.state.get("name") for e in plot.canvas._entries] == ["c3"]


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
    b.set_xlim(0.4, 0.6)
    ax0, ax1 = a.canvas.get_range()[0]
    assert ax0 == pytest.approx(0.4) and ax1 == pytest.approx(0.6)  # a followed b's zoom


def test_text_fill_border(qapp):
    """text() accepts a background fill + border box (PRD-64 Batch 29).

    The lineplot fit-quality overlay is a boxed, draggable label.
    """
    plot = cp.Plot()
    t = plot.text(
        "chi2 = 1.0",
        (1.0, 1.0),
        color="#FF0",
        anchor=(0, 0),
        draggable=True,
        fill=(0, 0, 255, 100),
        border="w",
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
    handler that writes the model.
    """
    plot = cp.Plot()
    reg = plot.region((1.0, 3.0), orientation="horizontal", movable=True)
    seen = []
    reg.on_change(lambda lo, hi: seen.append((lo, hi)), final=True)
    reg.set_bounds(2.0, 5.0)  # programmatic move -> must stay silent
    assert seen == []
    assert reg.bounds == (2.0, 5.0)
    # A genuine drag still fires the callback.
    reg.set_bounds(0.5, 0.9)
    reg._notify(final=True)
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
    # A user drag completing reports where the marker ended.
    m.set_value(1.25)
    m._notify(final=True)
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
    plot.line(x, x**2, pen="y", width=1, style="dash", name="dashed")
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


def test_spectrum_view_plots_traces(qapp):
    """SpectrumView.plot_series draws one chiplot curve per trace + styles.

    Regression guard for PRD-64 Batch 19: the reusable spectrum widget maps
    trace dicts (color/style/width) onto chiplot ``line`` calls.
    """
    from chisurf.gui.widgets.spectrum_view import SpectrumView

    v = SpectrumView()
    wl = np.linspace(400, 700, 50)
    v.plot_series(
        [
            {
                "name": "abs",
                "x": wl,
                "y": np.ones_like(wl),
                "color": (0, 100, 200),
                "style": "solid",
            },
            {"name": "em", "x": wl, "y": np.ones_like(wl), "color": (200, 0, 0), "style": "dash"},
            {
                "name": "dot",
                "x": wl,
                "y": np.ones_like(wl),
                "color": (145, 30, 180),
                "style": "dot",
            },
        ]
    )
    assert len(v.plot._series) == 3
    v.plot_series([])  # empty -> placeholder, no crash
    assert v.plot._series == []


def test_migrated_modules_import(qapp):
    """The migrated Batch 9 modules import cleanly (no pyqtgraph dependency)."""
    import importlib

    for name in (
        "chisurf.plugins.tttr.microtime_histogram.gui.app",
        # Batch 11
        "chisurf.plugins.vv_vh_anisotropy",
        # Batch 12
        # Batch 13
        # Batch 14
        "chisurf.gui.autoform.sections.decay_conv_section",
        # Batch 15
        # Batch 16
        "chisurf.plugins.core.lightpath_simulator.gui.node_types",
        # Batch 17
        "chisurf.gui.widgets.spectrum_view",
        # Batches 20-21 (burst_background / burst_browser sections) were deleted with their Qt tools.
        # NB: irf_estimator.gui.tool (Batch 24) is intentionally NOT listed — like
        # burst_fcs_correlator it transitively imports IMP, which segfaults in this
        # shared test process. Verified standalone + screenshot-checked instead.
        # Batch 25
        "chisurf.emtk.fit_pages.pages.parameter_scan.parameter_scan",
        # Batch 26
        "chisurf.emtk.fit_pages.pages.proteinMC",
        # Batch 27
        # NB: surfaceplot was deleted with the orphan sweep (Batch 31) — the
        # module is gone, so it cannot be checked for import cleanliness here.
        # Batch 32
        "chisurf.emtk.fit_pages.pages.residual_image",
        # Batch 33
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
    c = plot.line(x, x**2)
    gx, gy = c.get_data()
    assert list(gx) == list(x)
    assert list(gy) == list(x**2)


def test_grid_panels(qapp):
    grid = cp.Grid()
    p0 = grid.add_plot(row=0, col=0, title="top")
    p1 = grid.add_plot(row=1, col=0, title="bottom")
    p0.line([0, 1, 2], [0, 1, 0], pen="c")
    p1.scatter([0, 1, 2], [1, 0, 1], brush="m")
    assert isinstance(p0, cp.Plot) and isinstance(p1, cp.Plot)


def test_image_view_and_roi(qapp):
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
    roi.on_change(lambda *_: seen.append(roi.pos), final=False)
    roi.set_pos(2.0, 2.0)
    roi._notify(final=False)  # what a drag does
    assert seen == [(2.0, 2.0)]
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


def test_colormap_is_a_plain_reference(qapp):
    """``cp.colormap(name)`` returns a chiplot Colormap; it is not a proxy to a library."""
    assert isinstance(cp.colormap("viridis"), cp.Colormap)
    assert cp.colormap("CET-L4", source="colorcet").source == "colorcet"
    with pytest.raises(AttributeError):
        cp.colormap.get


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


def test_curve_set_opacity(qapp):
    """Curve.set_opacity sets whole-curve opacity (the grouped LinePlot's transparency)."""
    plot = cp.Plot()
    c = plot.line([0, 1, 2], [0, 1, 0])
    c.set_opacity(0.4)
    assert abs(float(c.native["opacity"]) - 0.4) < 1e-6
    c.set_opacity(1.0)
    assert abs(float(c.native["opacity"]) - 1.0) < 1e-6


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
    assert c.native["symbol"] == "o"
    assert c.native["symbol_size"] == 6
    assert c.native["symbol_color"] == (255, 0, 0)
    c.set_symbol(None)
    assert c.native["symbol"] is None


def test_region_set_limits_constrains_drag(qapp):
    """Region.set_limits bounds the draggable range, distinct from set_bounds (the position)."""
    plot = cp.Plot()
    reg = plot.region((2.0, 4.0), movable=True)
    seen = []
    reg.on_change(lambda lo, hi: seen.append((lo, hi)), final=True)
    reg.set_limits(0.0, 10.0)  # programmatic -> silent
    assert seen == []
    # A move beyond the limit is clamped to it.
    reg.set_bounds(-5.0, -1.0)
    lo, _ = reg.bounds
    assert lo >= 0.0 - 1e-9


def test_anchored_text_is_screen_pinned(qapp):
    """text(anchored=True) is a fixed screen offset rather than a data coordinate.

    The LinePlot fit-quality overlay is one: it must stay put when the view moves.
    """
    plot = cp.Plot()
    data_txt = plot.text("data", (1.0, 2.0))
    anchored_txt = plot.text("pinned", (10, 0), anchored=True, draggable=True)
    assert anchored_txt.native["anchored"] is True
    assert not data_txt.native["anchored"]
    anchored_txt.text = "updated"
    assert anchored_txt.text == "updated"


def test_line_step_string_modes(qapp):
    """line(step=...) accepts the equal-length step modes as strings.

    ``step=True`` maps to centered bins (needs ``len(x) == len(y) + 1``) while
    ``"left"``/``"right"``/``"center"`` keep x and y the same length -- the mode
    the DistributionPlot histograms (data/model) use, together with a fill.
    """
    plot = cp.Plot()
    x = [0.0, 1.0, 2.0, 3.0]
    y = [1.0, 3.0, 2.0, 0.0]
    # Equal-length "right" step must not raise (a bare True would demand N+1).
    c = plot.line(x, y, step="right", pen="b", fill=(0, 0, 255, 127))
    assert c.native["step"] == "right"
    # The fill brush survives to the backend entry.
    assert c.native["fill"][3] == 127


def test_errorbars_set_data_replaces_extents(qapp):
    """set_data replaces the extents rather than merging them.

    A handle created with ``height`` and later updated with ``top``/``bottom``
    must not keep the old ``height`` (a different point count crashed painting).
    """
    plot = cp.Plot()
    eb = plot.errorbars(np.array([]), np.array([]), height=np.array([]), beam=0.01)

    x = np.linspace(0.0, 1.0, 31)
    y = np.sin(x)
    sd = np.full(31, 0.05)
    eb.set_data(x, y, top=sd, bottom=sd)
    assert len(eb.native["top"]) == len(eb.native["bottom"]) == 31

    # ...and the other way round: switching back to symmetric replaces top/bottom.
    eb.set_data(x, y, height=np.full(31, 0.1))
    assert np.allclose(eb.native["top"], 0.05) and np.allclose(eb.native["bottom"], 0.05)
    plot.canvas.refresh()


def test_grid_colorbar_binds_image(qapp):
    """Grid.add_colorbar binds a colour ramp to an image's levels."""
    grid = cp.Grid()
    plot = grid.add_plot(row=0, col=0)
    img = plot.image(np.random.rand(8, 8), axis_order="col-major")

    bar = grid.add_colorbar(img, colormap="CET-L4", row=0, col=1)
    assert isinstance(bar, cp.handles.ColorBar)

    bar.set_levels(0.25, 0.75)
    assert bar.get_levels() == pytest.approx((0.25, 0.75))
    assert img.get_levels() == pytest.approx((0.25, 0.75))

    seen = []
    bar.on_levels_changed(lambda lo, hi: seen.append((lo, hi)))
    bar.set_levels(0.0, 1.0, notify=True)
    assert seen and seen[-1] == pytest.approx((0.0, 1.0))

    bar.set_colormap("viridis")  # a name is accepted as well as a Colormap


def test_to_colormap_coercion():
    assert cp.to_colormap(None) is None
    cm = cp.to_colormap("viridis")
    assert isinstance(cm, cp.Colormap) and cm.name == "viridis"
    assert cp.to_colormap(cm) is cm
    with pytest.raises(TypeError):
        cp.to_colormap(3.5)


def test_background_is_set_per_panel(qapp):
    """background= colours the panel (RF-133), and a grid panel keeps its own."""
    plot = cp.Plot(background="w")
    assert plot.canvas._background == (255, 255, 255)
    plot.set_background("k")
    assert plot.canvas._background == (0, 0, 0)

    grid = cp.Grid()
    p0 = grid.add_plot(row=0, col=0)
    p1 = grid.add_plot(row=1, col=0)
    p0.set_background("w")
    assert p0.canvas._background == (255, 255, 255)
    assert p1.canvas._background != (255, 255, 255), "a panel must not repaint its siblings"


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
    concrete class abstract, and Python only complains at instantiation -- i.e.
    when a user opens the tool, taking every chiplot panel in the application
    down with it. A half-landed contract breaks this test, not every plot panel.
    """
    import inspect

    from chisurf.chiplot.backends import base
    from chisurf.chiplot.backends import emtk_backend as eb

    pairs: list[tuple[type, type]] = [
        (base.Canvas, eb.EmtkCanvas),
        (base.GridCanvas, eb.EmtkGrid),
        (base.ImageViewCanvas, eb.EmtkImageView),
        (base.Backend, eb.EmtkBackend),
    ]
    for abstract, concrete in pairs:
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
    entries = iv.native._entries
    assert overlay in entries and roi in entries

    iv.clear()
    assert iv.native._entries == []
    assert not overlay.is_alive() and not roi.is_alive()


def test_image_restyles_without_reuploading_data(qapp):
    """An image already on the canvas can be re-levelled and recoloured.

    The 2-D residual view drives contrast and colormap from spin boxes and a
    combo box while the data stands still, so both must be settable on the
    handle rather than only through ``set_image``. ``RdBu`` is a matplotlib name.
    """
    plot = cp.Plot()
    data = np.linspace(-1.0, 1.0, 64).reshape(8, 8)
    img = plot.image(data, axis_order="col-major")

    img.set_levels(-0.5, 0.5)
    assert img.get_levels() == pytest.approx((-0.5, 0.5))

    img.set_colormap("RdBu")
    assert (
        img.native["colormap"] == "RdBu" or getattr(img.native["colormap"], "name", None) == "RdBu"
    )
    img.set_colormap(None)  # back to the default ramp
    assert img.native["colormap"] is None

    # the data itself is untouched by either restyle
    assert np.array_equal(img.get_image(), data)
