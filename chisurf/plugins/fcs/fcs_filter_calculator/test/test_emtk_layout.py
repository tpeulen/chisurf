"""Plot framing and hermetic Qt-free proof of the filter calculator's emtk app."""

import time

import numpy as np
import pytest
from emtk import implot
from emtk.testing import RecordingPainter

from chisurf.plugins.fcs.fcs_filter_calculator.gui.app import create_app


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


def settled(size=(1200, 800)):
    app = create_app()
    end = time.monotonic() + 60
    while time.monotonic() < end:
        app.draw(RecordingPainter(), 0, 0, *size)
        if not app.job.running:
            break
        time.sleep(0.02)
    return app


def test_the_reconstruction_plot_frames_the_decay_not_the_irf_tail(monkeypatch):
    """The decay (counts ~3000) fills a log axis from 0.5 up; an IRF tail of 1e-298 used to stretch it over 300 decades."""
    seen = []
    original = implot.end_plot

    def spy():
        seen.append(implot.get_plot_limits())
        original()

    monkeypatch.setattr(implot, "end_plot", spy)
    app = settled()
    for _ in range(3):
        app.draw(RecordingPainter(), 0, 0, 1200, 800)
    recon = [r for r in seen if r.x_max == 256.0 and r.y_max > 100]
    assert (
        recon
        and recon[-1].y_min >= 0.4
        and recon[-1].y_max == pytest.approx(3011.0 * 1.2, rel=0.05)
    )


def test_the_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    verdict = qt_free("fcs_filter_calculator")
    assert verdict["ok"], verdict["output"]


def test_the_filters_are_the_weighted_least_squares_solution_on_the_fit_range():
    """The example's filters, recomputed here from the documented formula on the fit range.

    With the species and nuisance patterns ``D`` (each normalised to unit area on the range) and
    ``W = diag(1 / max(total, 1))``, the filters are ``F = (D W D^T)^-1 D W``; they are zero outside the
    range, ``F D^T`` is the identity, and the reconstruction is ``D^T (F total)`` on the range and the
    measured decay outside it.
    """
    from chisurf.plugins.fcs.fcs_filter_calculator.gui.model import FilterModel

    model = FilterModel()
    model.compute()
    result = model._result
    detector = model.detectors.selected[0]
    total = np.asarray(model._total_decay([detector]), float)
    patterns = [
        np.asarray(model._species_item_pattern(c, total.size, [detector])[0], float)
        for c in model.components
        if c.enabled
    ]
    nuisance, _ = model._nuisance_patterns(total, patterns, detector)
    start, stop = model._fit_bounds
    basis = np.array(
        [p[start:stop] / p[start:stop].sum() for p in patterns + [np.asarray(n, float) for n in nuisance]]
    )
    t = total[start:stop]
    w = np.diag(1.0 / np.maximum(t, 1.0))
    expected = np.linalg.inv(basis @ w @ basis.T) @ basis @ w
    filters = np.asarray(result.filters)
    np.testing.assert_allclose(filters[:, start:stop], expected, rtol=1e-9, atol=1e-9)
    assert not filters[:, :start].any() and not filters[:, stop:].any()
    np.testing.assert_allclose(expected @ basis.T, np.eye(len(basis)), atol=1e-9)
    reconstruction = np.asarray(result.reconstruction)
    np.testing.assert_allclose(reconstruction[start:stop], basis.T @ (expected @ t), rtol=1e-9, atol=1e-6)
    np.testing.assert_array_equal(reconstruction[:start], total[:start])


@pytest.mark.parametrize("width", [800, 1200])
def test_native_compute_caption_and_residual_axis_fit_real_dock(width):
    """The declared compute action fits its own row and short residual dock stays bounded."""
    from emtk.testing import Driver

    app = settled((width, 600))
    driver = Driver(app, size=(width, 600))
    try:
        painter = driver.draw(2)
        x, y, w, h = driver.rect("compute")
        assert w >= painter.text_width("Compute filters") + 8
        assert 0 <= x < x + w <= width
        plot = implot.gp.last_plot
        assert plot.title is None
        assert plot.frame_rect[3] <= 600
        driver.click("compute")
        app.job.future.result(timeout=30)
        app.job.poll()
        assert "computed successfully" in app.status_text()
    finally:
        app.close()


def test_narrow_sources_scroll_reaches_actual_component_action(tmp_path):
    """A new toolbar row retains lower component controls through real window scrolling."""
    import shutil
    from pathlib import Path

    from emtk.testing import Driver

    from chisurf.plugins.fcs.fcs_correlator.workflow import FcsWorkflowContext

    root = Path(__file__).resolve().parents[5]
    source = tmp_path / "BH_SPC132.spc"
    shutil.copy2(root / "test/data/tttr/BH/132/BH_SPC132.spc", source)
    app = create_app(workflow_context=FcsWorkflowContext(expanded_files=[str(source)]))
    try:
        app.job.future.result(timeout=30)
        app.job.poll()
        app.from_correlator()
        app.job.future.result(timeout=30)
        app.job.poll()
        driver = Driver(app, size=(800, 600))
        driver.draw(3)
        driver.wheel(-2, at=(15, 400))
        x, y, w, h = driver.rect("add_lifetime")
        assert 0 <= y < y + h <= 600
        before = len(app.model.components)
        driver.click("add_lifetime")
        assert app.editor["model"] == "lifetime" and app.editor["lifetime"] == 2.0
        assert len(app.model.components) == before
        assert list(map(Path, app.model._total_paths)) == [source]
    finally:
        app.close()
