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
    assert recon and recon[-1].y_min >= 0.4 and recon[-1].y_max == pytest.approx(3011.0, rel=0.05)


def test_the_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    verdict = qt_free("fcs_filter_calculator")
    assert verdict["ok"], verdict["output"]
