"""The PSF views show what the Display settings ask for.

Two defects the accepted screenshots carried without anyone noticing:

* the 3-D volume drew every voxel as the same blue ring (now the isosurface
  shells of the chimol view, each coloured from the Display colormap);
* the central slice asked for its own width with equal axes, which honour x
  and fit y to it, so the section was cropped to a band through its middle --
  and it ignored the colormap.
"""

from __future__ import annotations

import time

import pytest

pytest.importorskip("emtk")


def _computed_app():
    from emtk.testing import RecordingPainter

    from chisurf.plugins.calculator.psf_calculator.gui.app import make_app

    app = make_app()
    end = time.monotonic() + 120.0
    while time.monotonic() < end:
        app.draw(RecordingPainter(), 0, 0, 1200, 800)
        if app.model.volume is not None and not app.busy and not app.model.is_stale:
            break
        time.sleep(0.02)
    assert app.model.volume is not None, "the PSF was not computed"
    return app


def test_the_shells_are_coloured_by_intensity_and_follow_the_colormap():
    from emtk import colormaps
    from emtk.testing import RecordingPainter

    from chisurf.plugins.calculator.psf_calculator.gui.volume_view import COLOUR_FLOOR

    app = _computed_app()
    app.draw(RecordingPainter(), 0, 0, 1200, 800)
    view = app.volume_view
    levels = view.view.viewer.get_volume_levels(view._object_id)
    assert len(levels) == 3, "threshold shell, half maximum and core"
    colours = [tuple(level["color"][:3]) for level in levels]
    assert len(set(colours)) == len(colours), "every shell has its own colour"
    peak = float(app.model.volume.max())
    assert [round(l["level"] / peak, 4) for l in levels] == [app.model.threshold, 0.5, 0.85]
    app.model.colormap = "viridis"
    app.draw(RecordingPainter(), 0, 0, 1200, 800)
    again = view.view.viewer.get_volume_levels(view._object_id)
    core = colormaps.get("viridis")(COLOUR_FLOOR + (1 - COLOUR_FLOOR) * 0.85 ** app.model.gamma)[:3]
    assert tuple(round(c, 4) for c in again[-1]["color"][:3]) == tuple(round(float(c), 4) for c in core)


@pytest.mark.parametrize("plane, extent", [("XY", "nxy"), ("XZ", "nz")])
def test_the_slice_shows_the_whole_section(monkeypatch, plane, extent):
    from emtk import implot
    from emtk import implot_internal as I
    from emtk.testing import RecordingPainter

    app = _computed_app()
    app.slice_plane = plane
    seen = {}
    original = implot.end_plot

    def capture():
        plot = I.gp.current_plot
        if plot is not None and "Central PSF slice" in str(getattr(plot, "title", "") or ""):
            axis = plot.axes[I.AXIS_Y1]
            seen["y"] = (float(axis.range_min), float(axis.range_max))
        return original()

    monkeypatch.setattr(implot, "end_plot", capture)
    for _ in range(4):
        app.draw(RecordingPainter(), 0, 0, 1200, 800)
    model = app.model
    half = (model.nz * model.z_step_nm if extent == "nz" else model.nxy * model.pixel_size_nm) / 2
    assert "y" in seen, "the slice plot was not drawn"
    low, high = seen["y"]
    assert low <= -half * 0.98 and high >= half * 0.98, f"{plane} cropped to {seen['y']}, half {half}"


def test_the_slice_uses_the_display_colormap():
    from matplotlib import colormaps

    app = _computed_app()
    app.model.colormap = "magma"
    colours = app._slice_colours()
    top = tuple(int(round(255 * c)) for c in colormaps["magma"](1.0)[:3])
    assert colours[-1] == top
