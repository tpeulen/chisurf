"""Plot framing and hermetic Qt-free proof of the filter calculator's emtk app (partial upgrade: see the port's REPORT.md)."""

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


def test_native_filters_are_bit_identical_to_the_qt_widgets_for_the_same_inputs():
    """Same total, species, nuisance patterns and fit range give the Qt widget's filters (``qt_reference.json``).

    The reference is what the retired Qt widget computed for its built-in example. The example differs only by its
    detector table: the Qt widget left it empty (detector "default": width 0.2 ns, no shift) while the native example
    fills "green" with the IRF the example patterns were generated with (width 0.16 ns, shift 0.03 ns), so the
    native model is put on the Qt defaults here.
    """
    import json
    from pathlib import Path

    from chisurf.plugins.fcs.fcs_filter_calculator.gui.model import FilterModel

    reference = json.loads((Path(__file__).parent / "qt_reference.json").read_text())
    assert reference["detector_defaults"] == [0.2, 0.0, 0.0]
    native = FilterModel()
    assert (native.detectors.width("green"), native.detectors.shift("green")) == (
        0.16,
        pytest.approx(0.03),
    )
    native.detectors.set_width("green", 0.2)
    native.detectors.set_skew("green", 0.0)
    native.detectors.set_shift("green", 0.0)
    native._fit_bounds = tuple(reference["fit_range"])
    native.compute()
    assert np.array_equal(native._result.filters, np.asarray(reference["filters"]))
    assert np.array_equal(native._result.reconstruction, np.asarray(reference["reconstruction"]))


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
