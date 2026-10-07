"""A real generated PTU teaches histogram controls without external data or settings."""

import numpy as np


def test_demo_click_writes_real_ptu_and_compute_recovers_declared_counts(tmp_path, monkeypatch):
    """The standard action queues photons; only a separate Compute click starts analysis."""
    import tttrlib
    from emtk.testing import Driver

    from chisurf.plugins.tttr.microtime_histogram.gui.app import create_app

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    app = create_app()
    driver = Driver(app, (1280, 900))
    try:
        driver.frame(3)
        assert "demo" in driver.ids()
        driver.click("demo")
        assert not app.job.running
        assert app.model.cumulative_ps is None
        assert "Synthetic" in app.model.message
        source = app.model.selected_files()[0]
        assert source.is_relative_to(tmp_path / "cache")
        stream = tttrlib.TTTR(str(source), "PTU")
        assert len(stream.micro_times) == 4500
        assert stream.header.micro_time_resolution == 32e-12
        assert stream.header.macro_time_resolution == 25e-9
        reading = app.editor.model.data["tttr_reading"]
        assert reading["micro_time_resolution"] == 32.0
        assert reading["macro_time_resolution"] == 25.0
        assert not reading["override_timing"]
        original_bytes = source.read_bytes()
        original_mtime = source.stat().st_mtime_ns
        driver.click("compute")
        app.job.future.result(timeout=15)
        app.job.poll()
        model = app.model
        expected = np.zeros_like(model.cumulative_parallel)
        expected[20:29] = [0, 100, 300, 600, 1000, 600, 300, 100, 0]
        np.testing.assert_array_equal(model.cumulative_parallel, expected)
        np.testing.assert_array_equal(model.cumulative_perpendicular, expected // 2)
        assert model.dt_ns == 0.032
        assert model.fwhm_bins == 4
        assert model.fwhm_ns == 0.128
        assert model.cumulative_ps.sum() == 4500
        driver.click("demo")
        assert source.read_bytes() == original_bytes
        assert source.stat().st_mtime_ns == original_mtime
    finally:
        app.close()


def test_demo_guide_waits_for_the_real_button(tmp_path, monkeypatch):
    """Opening the tour never queues or presses the demo on the user's behalf."""
    import json

    from emtk.testing import Driver

    from chisurf.plugins.tttr.microtime_histogram.gui.app import HERE, create_app

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    steps = json.loads((HERE / "guide.json").read_text())["steps"]
    demo_step = next(step for step in steps if step.get("target", {}).get("name") == "demo")
    assert demo_step.get("await")
    app = create_app()
    driver = Driver(app, (1280, 900))
    try:
        driver.frame(3)
        driver.click("guide")
        assert app.model.files == []
        assert not app.job.running
        index = steps.index(demo_step)
        app.tour.start(index)
        driver.frame(3)
        assert app.tour.awaiting
        driver.click("demo")
        assert app.model.files
        assert not app.tour.awaiting
        assert not app.job.running
    finally:
        app.close()
