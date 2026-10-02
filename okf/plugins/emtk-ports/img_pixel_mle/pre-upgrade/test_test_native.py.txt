"""Native controller workflows, output fidelity and Qt isolation."""

from __future__ import annotations

import threading

import numpy as np

from chisurf.core.datastore import numeric_column, read_table, store_from_arrays
from chisurf.plugins.microscopy.img_pixel_mle.core import PixelMleResult
from chisurf.plugins.microscopy.img_pixel_mle.gui.app import make_app


def result():
    return PixelMleResult(
        store_from_arrays({"tau": np.array([2.0, 3.0]), "rho": np.array([1.0, 1.0])}),
        np.array([[[2.0, 3.0]]]),
        np.array([[[1.0, 1.0]]]),
        2,
    )


def test_state_context_and_exports(tmp_path):
    app = make_app()
    assert app.add_files(["a.ptu", "a.ptu"])
    assert app.model.files == ["a.ptu"]
    app.apply_calibration({"Green": {"irf": "irf.ptu", "conv_stop": 128}})
    app.model.fit_model = "fit24"
    app.model.p0_value = 3.25
    restored = make_app()
    assert restored.restore_settings(app.export_settings())
    assert restored.model.p0_value == 3.25
    assert restored.model.irf_files == ["irf.ptu"]
    app.model.results, app.model.result_names, app.model.result_paths = [result()], ["a"], ["a.ptu"]
    path = tmp_path / "pixels.h5"
    assert app.export_table(path, "hdf5")
    np.testing.assert_array_equal(
        numeric_column(read_table(path, group="results"), "tau"), [2.0, 3.0]
    )
    assert app.export_table(tmp_path / "pixels.csv", "csv")
    assert "tau" in (tmp_path / "pixels.csv").read_text()


def test_async_snapshot_cancel_and_deferred_context(monkeypatch):
    app = make_app()
    app.model.files, app.model.irf_files = ["a.ptu"], ["irf.ptu"]
    started, release = threading.Event(), threading.Event()

    def run(snapshot):
        started.set()
        release.wait(5)
        assert snapshot.settings.micro_time_stop == 256
        assert snapshot.cancel_event.is_set()
        snapshot.status_text = "Cancelled"

    monkeypatch.setattr(type(app.model), "run", run)
    assert app.start_run()
    assert started.wait(2)
    assert not app.start_run()
    assert not app.add_files(["other.ptu"])
    app.apply_calibration({"Green": {"irf": "next.ptu", "conv_stop": 99}})
    app.cancel()
    release.set()
    app.job.thread.join(2)
    assert app.job.poll()
    assert app.model.status_text == "Cancelled"
    assert app._pending
    assert app.model.irf_files == ["irf.ptu"]


def test_real_core_matches_controller_and_keeps_errors(monkeypatch, tmp_path):
    import pytest

    from chisurf.plugins.microscopy.img_pixel_mle.backend import services
    from chisurf.plugins.microscopy.img_pixel_mle.core import fit_pixel_lifetimes_from_file
    from chisurf.plugins.microscopy.img_pixel_mle.gui import view_model
    from chisurf.plugins.microscopy.img_pixel_mle.test.test_pixel_mle_core import (
        _FLIM_PTU,
        _settings,
    )

    if not _FLIM_PTU.exists():
        pytest.skip("Real FLIM data unavailable")
    settings = _settings(convolution_stop=-1)
    settings.period = view_model.PixelMleViewModel._period_ns(str(_FLIM_PTU), 8)
    reference = fit_pixel_lifetimes_from_file(str(_FLIM_PTU), settings)
    app = make_app()
    app.model.files = ["missing.ptu", str(_FLIM_PTU)]
    app.model.irf_files = ["synthetic-irf.ptu"]
    app.model.settings.detector_chs_p = [0]
    app.model.settings.detector_chs_s = [1]
    app.model.settings.micro_time_binning = 8
    app.model.settings.min_photons = 20
    app.model.p0_value = 2.0
    app.model.p1_fix = app.model.p2_fix = app.model.p3_fix = True
    app.model.settings.twoi_star = settings.p2s_twoIstar
    monkeypatch.setattr(services, "_build_irf_vv_vh", lambda *_: settings.irf)
    monkeypatch.setattr(view_model.PixelMleViewModel, "_write_csv", staticmethod(lambda *_: None))
    assert app.start_run()
    app.job.thread.join(60)
    assert not app.job.thread.is_alive()
    assert app.job.poll()
    np.testing.assert_allclose(app.model.results[0].tau, reference.tau)
    np.testing.assert_allclose(
        numeric_column(app.model.results[0].dataframe, "tau"),
        numeric_column(reference.dataframe, "tau"),
    )
    assert "missing" in app.model.status_text
    assert app.model.result_paths == [str(_FLIM_PTU)]
    path = tmp_path / "real.h5"
    app.export_table(path, "hdf5")
    np.testing.assert_allclose(
        numeric_column(read_table(path, group="results"), "tau"),
        numeric_column(reference.dataframe, "tau"),
    )


def test_native_factory_blocks_qt_and_renders_both_sizes():
    import subprocess
    import sys

    command = [
        sys.executable,
        "tools/emtk_migration/check_native.py",
        "--factory",
        "chisurf.plugins.microscopy.img_pixel_mle.gui.app:make_app",
    ]
    process = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert process.returncode == 0, process.stderr + process.stdout
    assert '"qt_modules": []' in process.stdout


def test_all_six_locales_render_with_tooltips_and_maps():
    import logging

    from emtk.i18n import tr
    from emtk.testing import RecordingPainter

    from chisurf.emtk.i18n import SUPPORTED_LOCALES, set_locale

    errors = []

    class Capture(logging.Handler):
        def emit(self, record):
            if record.levelno >= logging.ERROR:
                errors.append(record.getMessage())

    handler = Capture()
    logging.getLogger().addHandler(handler)
    try:
        for locale in SUPPORTED_LOCALES:
            set_locale(locale)
            app = make_app()
            app.model.results = [result()]
            app.model.result_names = ["sample"]
            for width, height in ((1200, 800), (800, 600)):
                painter = RecordingPainter()
                app.draw(painter, 0, 0, width, height)
                assert painter.strings
            if locale != "en":
                assert tr("Lifetime map") != "Lifetime map"
            app.close()
        assert not errors
    finally:
        set_locale("en")
        logging.getLogger().removeHandler(handler)
