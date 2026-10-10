"""The shipped demonstration is real synthetic TTTR data with declared ground truth."""

import time

import numpy as np


def test_demo_writes_real_clocked_photons_and_exact_burst_rows(tmp_path):
    """Read the generated PTU/BUR through the same providers used for measurements."""
    from chisurf.plugins.burst.burst_mle_analysis.demo import (
        BURST_COUNT,
        BURST_PHOTONS,
        MICRO_RESOLUTION_S,
        SETUP,
        SIGNAL_LIFETIME_NS,
        make_demo,
    )
    from chisurf.plugins.burst.burst_mle_analysis.engine import MleSession

    path = make_demo(tmp_path / "demo")
    session = MleSession()
    session.set_definition(SETUP)
    session.add_burst_files([path])
    from chisurf.core.datastore import row_count

    assert row_count(session.df_bursts) == BURST_COUNT
    stream = session.current_tttr()
    assert stream.header.micro_time_resolution == MICRO_RESOLUTION_S
    assert len(session.burst_indices()) == BURST_COUNT * BURST_PHOTONS
    bins = np.asarray(stream.micro_times)[session.burst_indices()]
    measured = (bins.mean() - 20.0) * MICRO_RESOLUTION_S * 1e9
    assert abs(measured - SIGNAL_LIFETIME_NS) < 0.08
    assert make_demo(tmp_path / "demo") == path


def test_actual_native_demo_button_loads_and_syncs_definition(tmp_path, monkeypatch):
    """The declared button loads the demo while computation remains an explicit user action."""
    from emtk.testing import Driver

    from chisurf.plugins.burst.burst_mle_analysis.gui.native import create_app

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    app = create_app()
    driver = Driver(app, (1280, 900))
    try:
        driver.frame(3)
        assert "load_example" in driver.ids()
        step = next(
            i
            for i, step in enumerate(app.tour.steps)
            if step.get("target", {}).get("name") == "load_example"
        )
        app.docks.focus("detectors")
        app.tour.start(step)
        driver.frame(3)
        assert app.tour.get_target_rect("load_example") is not None
        assert app.tour.awaiting
        driver.click("load_example")
        driver.frame(3)
        assert not app.tour.awaiting
        app.tour.stop()
        assert app.model.n_bursts == 16
        assert app.editor.model.get_settings()["detectors"] == app.model.session.detectors
        assert app.model.session.outcome is None
        assert app.tour.get_target_rect("load_example") is not None
        assert "synthetic" in app.model.status_text.lower()
        step = next(
            i
            for i, step in enumerate(app.tour.steps)
            if step.get("target", {}).get("name") == "fit_model"
        )
        app.tour.start(step)
        assert app.tour.awaiting
        from chisurf.core.registry import catalog

        while not catalog.prefetch():  # the registries are read on a worker thread; the choice lists them once read
            time.sleep(0.01)
        driver.frame(3)
        driver.click("fit_model")
        driver.click(dict(app.model.fit_model_choices())["fit24"])
        assert app.model.fit_model == "fit24"
        assert not app.tour.awaiting
    finally:
        app.close()
