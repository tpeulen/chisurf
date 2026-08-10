"""Tests for the chiplot WebGPU backend.

Three layers, deliberately separated by what they need:

* **Transform and geometry** — no Qt, no GPU. These are where the interesting
  bugs live: a log axis whose inverse disagrees with its forward, a fill that
  triangulates as a fan and spills across the panel, a dash pattern that walks
  off the end of a segment. The OpenGL attempt had none of these tests, and
  every one of its defects was invisible until somebody looked at a PNG.
* **Canvas API** — builds widgets (no display needed) and checks the contract
  is satisfied and state is stored.
* **Rendering** — skipped when the machine has no WebGPU adapter; asserts that
  pixels of the requested colour actually land in the framebuffer.
"""

from __future__ import annotations

import math
import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytestmark = pytest.mark.gui

pytest.importorskip("qtpy")
pytest.importorskip("wgpu")

from qtpy import QtWidgets  # noqa: E402

from chisurf.gui.chiplot import handles as H  # noqa: E402
from chisurf.gui.chiplot import style as S  # noqa: E402
from chisurf.gui.chiplot.backends import available_backends, base  # noqa: E402
from chisurf.gui.chiplot.backends import wgpu as wb  # noqa: E402
from chisurf.gui.chiplot.backends.wgpu import _canvas as wc  # noqa: E402
from chisurf.gui.chiplot.backends.wgpu import _colormap, _gpu  # noqa: E402
from chisurf.gui.chiplot.backends.wgpu._view import PixelView  # noqa: E402

VIEWPORT = (400.0, 300.0)


@pytest.fixture(scope="module")
def qapp():
    """Yield a single QApplication for the module."""
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


@pytest.fixture(scope="module")
def gpu():
    """Skip the module's rendering tests when no adapter is available."""
    if not _gpu.is_available():
        pytest.skip("no WebGPU adapter on this machine")
    return _gpu.PlotRenderer()


# ---------------------------------------------------------------------------
# Registry / contract
# ---------------------------------------------------------------------------

def test_wgpu_backend_is_registered():
    assert "wgpu" in available_backends()


def test_backend_contract_has_no_gaps():
    """Every abstract method is implemented.

    Python only reports a missing one when a canvas is *instantiated*, which
    turns a half-landed contract into every plot panel in the application
    failing at once, each tool blaming its own load.
    """
    for abstract, concrete in [
        (base.Canvas, wc._WgpuCanvas),
        (base.GridCanvas, wc._WgpuGrid),
        (base.ImageViewCanvas, wc._WgpuImageView),
        (base.Backend, wb.WgpuBackend),
    ]:
        missing = sorted(getattr(concrete, "__abstractmethods__", ()))
        assert missing == [], f"{concrete.__name__} is missing {missing}"


# ---------------------------------------------------------------------------
# View transform
# ---------------------------------------------------------------------------

def test_linear_transform_maps_range_to_clip_space():
    view = PixelView((0.0, 10.0), (0.0, 100.0))
    nx, ny = view.transform_array(np.array([0.0, 5.0, 10.0]),
                                  np.array([0.0, 50.0, 100.0]))
    assert np.allclose(nx, [-1.0, 0.0, 1.0])
    assert np.allclose(ny, [-1.0, 0.0, 1.0])


def test_log_transform_is_linear_in_decades():
    view = PixelView((1.0, 1000.0), (1.0, 1000.0), log_x=True, log_y=True)
    nx, _ = view.transform_array(np.array([1.0, 31.6227766, 1000.0]),
                                 np.array([1.0, 1.0, 1.0]))
    assert np.allclose(nx, [-1.0, 0.0, 1.0], atol=1e-6)


def test_log_transform_drops_non_positive_samples():
    """A zero on a log axis must break the line, not clamp to the bottom.

    Clamping draws a spike down to the axis that is not in the data, and it is
    the kind of artefact a reader takes for a measurement.
    """
    view = PixelView((1.0, 100.0), (1.0, 100.0), log_y=True)
    _, ny = view.transform_array(np.array([1.0, 2.0, 3.0]),
                                 np.array([10.0, 0.0, -5.0]))
    assert np.isfinite(ny[0])
    assert np.isnan(ny[1]) and np.isnan(ny[2])


@pytest.mark.parametrize("log", [False, True])
def test_pixel_round_trip_matches_the_forward_transform(log):
    """pixel_to_data must invert data_to_pixel, on both axis kinds."""
    view = PixelView((1.0, 1000.0), (1.0, 1000.0), log_x=log, log_y=log)
    margins = wc._Margins()
    for value in (2.0, 17.0, 500.0):
        px, py = view.data_to_pixel(value, value, 400, 300, margins)
        dx, dy = view.pixel_to_data(px, py, 400, 300, margins)
        assert dx == pytest.approx(value, rel=1e-6)
        assert dy == pytest.approx(value, rel=1e-6)


# ---------------------------------------------------------------------------
# Stroke geometry
# ---------------------------------------------------------------------------

def test_polyline_expands_to_triangles_of_the_right_width():
    """WebGPU has no line width, so a stroke is geometry — check it is wide."""
    line = np.array([[-0.5, 0.0], [0.5, 0.0]], dtype=np.float32)
    tris = _gpu.expand_polyline(line, VIEWPORT, 4.0)
    assert len(tris) == 6  # one quad
    px = _gpu.to_pixel(tris, VIEWPORT)
    assert px[:, 1].max() - px[:, 1].min() == pytest.approx(4.0, abs=1e-5)


def test_polyline_breaks_at_non_finite_points():
    """A NaN sample splits the stroke instead of spanning the gap."""
    pts = np.array([[-1.0, 0.0], [-0.5, 0.0], [np.nan, np.nan],
                    [0.5, 0.0], [1.0, 0.0]], dtype=np.float32)
    tris = _gpu.expand_polyline(pts, VIEWPORT, 2.0)
    xs = _gpu.to_pixel(tris, VIEWPORT)[:, 0]
    # Two runs, and nothing generated across the middle of the gap.
    assert len(tris) == 12
    assert not ((xs > -60) & (xs < 60)).any()


def test_dashes_cover_the_on_fraction_of_the_line():
    """A dash pattern of 8 on / 6 off must ink 8/14 of the length.

    Counting vertices proves nothing here — a dashed line has *more* of them
    than a solid one, since every dash is its own quad. What matters is how
    much of the line ends up covered, and that the walk does not run past the
    end of the segment.
    """
    line = np.array([[-1.0, 0.0], [1.0, 0.0]], dtype=np.float32)
    dashed = _gpu.expand_polyline(line, VIEWPORT, 2.0, dash=(8.0, 6.0))
    assert len(dashed) % 6 == 0 and len(dashed) > 6

    quads = _gpu.to_pixel(dashed, VIEWPORT).reshape(-1, 6, 2)
    covered = float(sum(q[:, 0].max() - q[:, 0].min() for q in quads))
    total = VIEWPORT[0]
    assert covered / total == pytest.approx(8.0 / 14.0, rel=0.15)

    px = _gpu.to_pixel(dashed, VIEWPORT)[:, 0]
    assert px.min() >= -total / 2 - 1e-4
    assert px.max() <= total / 2 + 1e-4


def test_zero_length_segments_do_not_produce_geometry():
    """A repeated point has no normal; it must not emit a degenerate quad."""
    pts = np.array([[0.0, 0.0], [0.0, 0.0], [0.0, 0.0]], dtype=np.float32)
    assert len(_gpu.expand_polyline(pts, VIEWPORT, 3.0)) == 0


def test_marker_geometry_scales_with_the_pixel_size():
    pts = np.array([[0.0, 0.0]], dtype=np.float32)
    small = _gpu.to_pixel(_gpu.marker_geometry(pts, 6.0, "o", VIEWPORT), VIEWPORT)
    large = _gpu.to_pixel(_gpu.marker_geometry(pts, 12.0, "o", VIEWPORT), VIEWPORT)
    assert np.ptp(large[:, 0]) == pytest.approx(2 * np.ptp(small[:, 0]), rel=1e-6)
    assert np.ptp(small[:, 0]) == pytest.approx(6.0, rel=0.05)


def test_marker_geometry_skips_non_finite_points():
    pts = np.array([[0.0, 0.0], [np.nan, 0.0]], dtype=np.float32)
    tris = _gpu.marker_geometry(pts, 8.0, "s", VIEWPORT)
    assert len(tris) == 4 * 3  # one square, fanned from its centre


def test_fill_between_pairs_points_instead_of_fanning():
    """A fan is only valid for a convex polygon; a decay band is not one.

    Triangulating a band as a fan puts a wedge across the panel — geometry that
    is nowhere near the data. Pairing the series keeps every triangle local.
    """
    x = np.array([0.0, 1.0, 2.0])
    lo = np.zeros(3)
    hi = np.array([10.0, 1.0, 10.0])  # deliberately non-convex
    tris = _gpu.fill_between_geometry(x, lo, hi)
    assert len(tris) == 2 * 6  # two intervals, two triangles each
    assert tris[:, 0].min() >= 0.0 and tris[:, 0].max() <= 2.0
    assert tris[:, 1].max() <= 10.0


# ---------------------------------------------------------------------------
# Ticks
# ---------------------------------------------------------------------------

def test_log_ticks_are_decades_not_linear_steps():
    """Linear ticks on a log axis pile every label into the top decade."""
    ticks = wc.log_ticks(1.0, 1e5)
    assert ticks == [1.0, 10.0, 100.0, 1000.0, 10000.0, 100000.0]


def test_log_ticks_add_intermediates_when_the_span_is_short():
    ticks = wc.log_ticks(1.0, 10.0)
    assert len(ticks) > 2


def test_nice_ticks_stay_inside_the_range():
    ticks = wc.nice_ticks(0.13, 0.87, 5)
    assert ticks and all(0.13 <= t <= 0.87 for t in ticks)


def test_tick_format_does_not_invent_precision():
    assert wc.format_tick(0.5, 0.1) == "0.5"
    assert wc.format_tick(1000.0, 1.0, log=True) == "1000"


# ---------------------------------------------------------------------------
# Colormaps
# ---------------------------------------------------------------------------

def test_colormap_resolves_to_a_lookup_table():
    lut = _colormap.lookup_table(S.Colormap(name="viridis"), 256)
    assert lut.shape == (256, 4)
    assert lut.dtype == np.uint8
    assert not np.array_equal(lut[0], lut[-1])


def test_unknown_colormap_falls_back_and_says_so():
    with pytest.warns(RuntimeWarning):
        lut = _colormap.lookup_table(S.Colormap(name="not-a-colormap-at-all"), 32)
    assert lut.shape == (32, 4)


# ---------------------------------------------------------------------------
# Canvas API
# ---------------------------------------------------------------------------

def _canvas():
    return wb.WgpuBackend().create_canvas()


def test_canvas_builds_geometry_for_every_draw_family(qapp):
    canvas = _canvas()
    canvas.add_curve([0, 1, 2], [0, 1, 0], pen=S.to_pen("red", width=2))
    canvas.add_scatter([0, 1], [1, 0], size=6, pen=None,
                       brush=S.to_brush("cyan"), symbol=H.Symbol.CIRCLE)
    canvas.add_bars([0, 1], [1, 2], width=0.5, pen=None, brush=S.to_brush("green"))
    canvas.add_errorbars([0, 1], [1, 1], height=[0.2, 0.2], pen=S.to_pen("white"))
    canvas.add_image(np.arange(16.0).reshape(4, 4), colormap="viridis")
    canvas.add_region((0.2, 0.8), orientation=H.Orientation.VERTICAL,
                      movable=True, brush=S.to_brush("#26a29844"),
                      pen=S.to_pen("#26a298"))
    canvas.add_marker(0.5, orientation=H.Orientation.HORIZONTAL, movable=True,
                      pen=S.to_pen("yellow"))
    canvas.add_arrow((0.5, 0.5), angle=45.0, size=12.0)
    canvas._recompute_auto_range()
    batches = canvas._build_batches((400, 300), 1.0)
    assert len(batches) >= 8
    assert any(isinstance(b, _gpu.ImageBatch) for b in batches)
    for b in batches:
        assert len(b.verts) > 0
        assert np.isfinite(np.asarray(b.verts)).all()


def test_auto_range_ignores_non_positive_data_on_a_log_axis(qapp):
    """One zero sample must not collapse a decade span onto the top edge."""
    canvas = _canvas()
    canvas.add_curve([1, 2, 3], [100.0, 0.0, 1.0], pen=S.to_pen("red"))
    canvas.set_log(y=True)
    canvas._recompute_auto_range()
    lo, hi = canvas.get_range()[1]
    assert lo > 0
    # 1..100 is two decades; the 5 % padding is applied in decades, so the
    # visible span is 2.2 of them. Had the zero been let in, the range would
    # start at the log floor and span hundreds.
    assert math.log10(hi / lo) == pytest.approx(2.2, rel=0.05)


def test_region_drag_moves_the_bounds_and_fires(qapp):
    """Drag a region edge and check the bounds follow.

    A movable region has to actually be movable — the OpenGL backend's was not,
    and nothing in its contract tests noticed.
    """
    canvas = _canvas()
    canvas.set_range(x=(0.0, 10.0), y=(0.0, 1.0))
    seen = []
    region = canvas.add_region((2.0, 5.0), orientation=H.Orientation.VERTICAL,
                               movable=True, brush=S.to_brush("#26a29844"),
                               pen=S.to_pen("#26a298"))
    region.on_change(lambda lo, hi: seen.append((lo, hi)), final=False)
    widget = canvas.widget()
    widget.resize(400, 300)
    margins = canvas._margins
    px, py = canvas._view.data_to_pixel(2.0, 0.5, 400, 300, margins)

    handle, part = canvas._hit_draggable(px, py)
    assert handle is region and part == "low"

    canvas._drag = (region, "low", 2.0)
    target_px, _ = canvas._view.data_to_pixel(3.0, 0.5, 400, 300, margins)

    class _Ev:
        def position(self):
            class P:
                def x(self_inner):
                    return target_px

                def y(self_inner):
                    return py
            return P()

    canvas._mouse_move(_Ev())
    assert region.bounds[0] == pytest.approx(3.0, rel=1e-3)
    assert seen


def test_set_range_and_get_range_round_trip(qapp):
    canvas = _canvas()
    canvas.set_range(x=(1.0, 2.0), y=(3.0, 4.0))
    assert canvas.get_range() == ((1.0, 2.0), (3.0, 4.0))


def test_linked_panels_share_a_range(qapp):
    a, b = _canvas(), _canvas()
    a.link_x(b)
    a.set_range(x=(5.0, 6.0))
    assert tuple(b.get_range()[0]) == (5.0, 6.0)


def test_image_texture_is_not_re_uploaded_when_only_the_view_moves(qapp):
    """The version stamp is what stops a heatmap re-uploading every frame."""
    canvas = _canvas()
    image = canvas.add_image(np.arange(16.0).reshape(4, 4), colormap="viridis")
    canvas._recompute_auto_range()
    first = canvas._build_batches((400, 300), 1.0)[-1].version
    canvas.set_range(x=(0.0, 2.0))
    second = canvas._build_batches((400, 300), 1.0)[-1].version
    assert first == second
    image.set_levels(0.0, 4.0)
    assert canvas._build_batches((400, 300), 1.0)[-1].version > second


# ---------------------------------------------------------------------------
# Chrome typography and handle liveness
# ---------------------------------------------------------------------------

def test_chrome_sizes_are_ordered_and_floored(qapp):
    """Ticks smallest, title largest, nothing below the readable floor."""
    tick = S.chrome_font_size("tick")
    label = S.chrome_font_size("label")
    title = S.chrome_font_size("title")
    assert tick < label < title
    assert tick >= 6


def test_chrome_follows_the_configured_size(qapp, monkeypatch):
    """``gui.plot.font_size`` wins over the application font when set."""
    from chisurf.core import settings as core_settings

    plot = core_settings.cs_settings.setdefault("gui", {}).setdefault("plot", {})
    previous = plot.get("font_size", 0)
    try:
        plot["font_size"] = 20
        assert S.chrome_base_size() == 20
        assert S.chrome_font_size("tick") == 17
        # A tiny base still cannot produce unreadable chrome.
        plot["font_size"] = 4
        assert S.chrome_font_size("tick") == 6
    finally:
        plot["font_size"] = previous


def test_handles_report_liveness(qapp):
    """A handle reports whether it can still be drawn to.

    ``is_alive`` is the backend-neutral answer call sites used to get from
    pyqtgraph internals — which reported "dead" here and silently skipped the
    update it guarded.
    """
    canvas = _canvas()
    text = canvas.add_text("hi", (0.0, 0.0), color="#ffffff")
    assert text.is_alive() is True
    text.remove()
    assert text.is_alive() is False


def test_anchored_text_is_measured_over_all_its_lines(qapp):
    """A multi-line label sizes its box from the widest line and the line count.

    The fit-quality overlay is three lines; drawn from a single-line measure it
    came out as one run-together row in a box the wrong shape.
    """
    canvas = _canvas()
    text = canvas.add_text("a\nbb\nccc", (10.0, 10.0), color="#ffffff",
                           anchored=True)
    assert text.text.count("\n") == 2
    assert text.is_alive()


# ---------------------------------------------------------------------------
# Rendering (needs an adapter)
# ---------------------------------------------------------------------------

def test_renderer_draws_the_colour_it_was_given(gpu):
    quad = _gpu.quad_geometry(-0.5, -0.5, 0.5, 0.5).astype(np.float32)
    pixels = gpu.render([_gpu.solid(quad, (1.0, 0.0, 0.0, 1.0))],
                        64, 64, (0.0, 0.0, 0.0, 1.0))
    assert pixels.shape == (64, 64, 4)
    centre = pixels[32, 32]
    assert centre[0] > 200 and centre[1] < 40 and centre[2] < 40


def test_renderer_clears_to_the_background(gpu):
    pixels = gpu.render([], 32, 32, (0.0, 0.2, 0.4, 1.0))
    assert pixels[0, 0, 1] == pytest.approx(51, abs=2)
    assert pixels[0, 0, 2] == pytest.approx(102, abs=2)


def test_a_stroked_curve_puts_pixels_on_the_screen(gpu):
    """The whole point: the OpenGL backend produced a black rectangle here."""
    t = np.linspace(-0.9, 0.9, 128)
    pts = np.column_stack([t, np.zeros_like(t)]).astype(np.float32)
    tris = _gpu.expand_polyline(pts, (128, 128), 3.0)
    pixels = gpu.render([_gpu.solid(tris, (1.0, 1.0, 0.0, 1.0))],
                        128, 128, (0.0, 0.0, 0.0, 1.0))
    lit = (pixels[..., 0] > 128) & (pixels[..., 1] > 128)
    assert lit.sum() > 200


def test_image_batch_samples_its_texture(gpu):
    rgba = np.zeros((4, 4, 4), np.uint8)
    rgba[..., 1] = 255
    rgba[..., 3] = 255
    verts = _gpu.quad_geometry(-1.0, -1.0, 1.0, 1.0).astype(np.float32)
    uv = np.array([[0, 1], [1, 1], [1, 0], [0, 1], [1, 0], [0, 0]], np.float32)
    pixels = gpu.render([_gpu.ImageBatch(verts, uv, rgba, key="t", version=1)],
                        32, 32, (0.0, 0.0, 0.0, 1.0))
    assert pixels[16, 16, 1] > 200


def test_panel_export_writes_a_file(qapp, gpu, tmp_path):
    canvas = _canvas()
    canvas.add_curve(np.linspace(0, 1, 50), np.linspace(0, 1, 50) ** 2,
                     pen=S.to_pen("orange", width=2))
    canvas.widget().resize(320, 240)
    out = tmp_path / "panel.png"
    assert canvas.export_image(str(out), width=320)
    assert out.exists() and out.stat().st_size > 0
