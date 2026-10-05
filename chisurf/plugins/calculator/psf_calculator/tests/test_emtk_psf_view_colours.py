"""The PSF views show what the Display settings ask for.

Two defects the accepted screenshots carried without anyone noticing:

* the 3-D volume drew every voxel as the same blue ring: only the marker *fill*
  took the colormap band, and at 2 px a marker is mostly outline, which took
  the item's automatic colour -- one colour, because all twelve bands shared
  one item id (``"Intensity k##psf"`` is the id ``psf`` in emtk);
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


def test_the_volume_is_coloured_by_intensity_band(monkeypatch):
    from emtk import implot3d

    app = _computed_app()
    specs = []
    original = implot3d.plot_scatter

    def record(label, *args, spec=None, **kwargs):
        specs.append((label, spec))
        return original(label, *args, spec=spec, **kwargs)

    monkeypatch.setattr(implot3d, "plot_scatter", record)
    from emtk.testing import RecordingPainter

    app.draw(RecordingPainter(), 0, 0, 1200, 800)
    bands = [(label, spec) for label, spec in specs if label.startswith("Intensity")]
    assert len(bands) >= 6
    ids = {label.split("##", 1)[1] for label, _ in bands}
    assert len(ids) == len(bands), "bands share an item id, so they share one colour"
    for _label, spec in bands:
        assert tuple(spec.marker_line_color) == tuple(spec.marker_fill_color), (
            "the outline is not the band's colour"
        )
    assert len({tuple(spec.marker_fill_color) for _l, spec in bands}) == len(bands)


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
