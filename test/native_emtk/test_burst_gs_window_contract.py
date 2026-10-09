"""BurstGS host geometry keeps real kinetics and exposes its complete results."""

import copy
import json
from pathlib import Path

import numpy as np
import pytest
from emtk.testing import Driver, RecordingPainter

from chisurf.emtk.state import attach_native_state


def isolate(tmp_path, monkeypatch):
    """Keep detector resources, native preferences and metadata out of user state."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "db.sqlite"))


def test_consumed_primary_default_before_form_adaptation(tmp_path, monkeypatch):
    """The true app receives raw window metadata before sections are adapted."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.burst.burst_gs.gui import app as owner

    path = Path(owner.__file__).with_name("burst_gs.view.json")
    original = path.read_bytes()
    app = owner.create_app()
    try:
        assert json.loads(original)["window"] == {"width": 1100, "height": 720}
        assert app.window_size == (1100, 720)
        Driver(app, size=app.window_size).draw(3)
        assert path.read_bytes() == original
        assert {"Fit", "Export", "use_simulation", "guide", "help"} <= app.item_rects.keys()
    finally:
        app.close()


@pytest.mark.parametrize("dimensions", [(960, 640), None])
def test_authored_primary_and_missing_metadata(tmp_path, monkeypatch, dimensions):
    """A copied primary reaches the constructor, with a bounded family fallback."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.burst.burst_gs.gui import app as owner

    spec = json.loads(Path(owner.__file__).with_name("burst_gs.view.json").read_text())
    if dimensions:
        spec["window"] = dict(zip(("width", "height"), dimensions))
    else:
        spec.pop("window", None)
    (tmp_path / "burst_gs.view.json").write_text(json.dumps(spec))
    monkeypatch.setattr(owner, "__file__", str(tmp_path / "app.py"))
    app = owner.create_app()
    try:
        assert app.window_size == (dimensions or (1100, 720))
        Driver(app, size=app.window_size).draw(3)
    finally:
        app.close()


def test_saved_geometry_wins_without_claiming_analysis_restore(tmp_path, monkeypatch):
    """Preferences restore geometry/docks while inputs and fitted results are explicit."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.burst.burst_gs.gui.app import create_app

    first = attach_native_state("gs_window", create_app())
    first.window_resized(1330, 870)
    first.close()
    other = attach_native_state("gs_window", create_app())
    try:
        assert other.window_size == (1330, 870)
        assert other.model.analysis is None
        assert not other.model.bur_files
        other.draw(RecordingPainter(), 0, 0, 900, 650)
        assert other.window_size == (1330, 870)
    finally:
        other.close()


@pytest.fixture
def fitted(tmp_path, monkeypatch):
    """Run the actual seeded ThreadPool worker; no result or computation is mocked."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.burst.burst_gs.gui.app import create_app

    app = create_app()
    app.model.use_simulation = True
    app.model.sim_n_bursts = 20
    app.model.sim_photons_per_burst = 80
    app.model.max_iterations = 500
    app.model.cross_check_h2mm = True
    app.controller.run()
    app.controller._future.result(timeout=120)
    app.controller.poll()
    assert app.model.analysis is not None, app.model.results_text
    yield app
    app.close()


def test_real_fit_export_and_views_keep_photon_arrays(fitted, tmp_path):
    """Panel changes and resizing preserve actual photons, fit settings and CSV values."""
    app = fitted
    before = copy.deepcopy(app.model.analysis.to_dict())
    times = app.model._bursts.times.copy()
    colors = app.model._bursts.colors.copy()
    app.controller.export(tmp_path / "fit.csv")
    exported = (tmp_path / "fit.csv").read_bytes()
    for size in ((1100, 720), (900, 650)):
        driver = Driver(app, size=size)
        for name in ("controls", "results", "plot", "efficiency"):
            app.gs_gui.docks.focus(name)
            driver.draw(3)
        assert app.model.analysis.to_dict() == before
        np.testing.assert_array_equal(app.model._bursts.times, times)
        np.testing.assert_array_equal(app.model._bursts.colors, colors)
    app.controller.export(tmp_path / "fit.csv")
    assert (tmp_path / "fit.csv").read_bytes() == exported


def test_state_population_lines_inside_physical_axes(fitted, monkeypatch):
    """Both fitted efficiency lines lie inside the plot, away from clipped x edges."""
    from emtk import implot

    app = fitted
    limits = []
    active = []
    begin, end = implot.begin_plot, implot.end_plot

    def record_begin(title, *args, **kwargs):
        shown = begin(title, *args, **kwargs)
        if shown:
            active.append(title)
        return shown

    def record_end():
        title = active.pop()
        if title.startswith("FRET efficiency"):
            limits.append(implot.get_plot_limits())
        return end()

    monkeypatch.setattr(implot, "begin_plot", record_begin)
    monkeypatch.setattr(implot, "end_plot", record_end)
    app.gs_gui.docks.focus("efficiency")
    Driver(app, size=(900, 650)).draw(3)
    assert limits
    plot = limits[-1]
    for series in app.model.efficiency_series():
        assert plot.x_min < series["x"][0] < plot.x_max
        assert plot.y_min <= 0 < max(series["y"]) < plot.y_max


def test_last_h2mm_report_line_reachable_by_outer_wheel(fitted):
    """The existing results dock scroll reaches the complete cross-check report."""
    app = fitted
    assert "ratio_k21" in app.model.results_text
    app.gs_gui.docks.focus("results")
    driver = Driver(app, size=(900, 650))
    driver.draw(3)
    painter = driver.wheel(-30, at=(650, 120))
    assert any(
        "ratio_k21" in text[5]
        and metadata["visible_bounds"] == metadata["measured_bounds"]
        and metadata["visible_bounds"][2] > 0
        for text, metadata in zip(painter.visible_texts, painter.text_metadata)
    )


def test_custom_fit_callback_without_controller(tmp_path, monkeypatch):
    """A hosted custom action can draw, record targets and close without native callbacks."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.burst.burst_gs.gui.app import create_app

    calls = []
    app = create_app(on_fit=lambda: calls.append("fit"))
    try:
        assert app.controller is None
        Driver(app, size=(900, 650)).draw(3)
        assert "Fit" in app.item_rects
        app.gs_gui.on_fit()
        assert calls == ["fit"]
        assert not app.files_dropped(["measurement.bur"])
    finally:
        app.close()
