"""Region MLE: Load demo, Preview, Run, Export and Open results pressed on the drawn buttons.

The input is the plugin's own simulated spot demo (four objects, lifetimes 1.0 / 3.6 / 2.2 / 0.6 ns); the outcomes are
the status line, the region list on screen, the fitted lifetimes and the table written to disk.
"""

from __future__ import annotations

import time

import numpy as np
import pytest
from emtk.testing import Driver

from .test_emtk_region_mle import REFERENCE_TAU, demo, loaded_model, taus, workdir  # noqa: F401


def _app(model=None):
    from chisurf.plugins.microscopy.region_mle.gui.app import RegionMleApp

    app = RegionMleApp(model=model) if model is not None else RegionMleApp()
    driver = Driver(app, (1200, 800))
    driver.frame(3)
    return app, driver


def _settle(driver, app, timeout=180.0):
    end = time.monotonic() + timeout
    driver.frame(1)
    while app.job.busy:
        assert time.monotonic() < end, "the job did not finish"
        time.sleep(0.02)
        driver.frame(1)
    return driver.frame(3)


def _shown(driver):
    return " ".join(t[5] for t in driver.painter.texts)


def test_buttons_do_nothing_without_files_and_say_why():
    app, driver = _app()
    for button in ("request_preview", "request_run", "request_export"):
        driver.click(button)
        assert not app.job.busy and app.dialog is None
    assert app.model.results == []


def test_preview_then_run_then_export_then_reopen(workdir, tmp_path):  # noqa: F811
    app, driver = _app(loaded_model(workdir))

    driver.click("request_preview")
    assert app.job.busy
    _settle(driver, app)
    assert app.model.results[0].n_molecules == 4
    assert all(not np.isfinite(t) for t in taus(app.model)), "a preview measures, it does not fit"
    assert "Preview: 4 region(s)" in app.model.status_text
    assert "Preview: 4 region(s)" in _shown(driver)

    driver.click("request_run")
    _settle(driver, app)
    np.testing.assert_allclose(taus(app.model), REFERENCE_TAU, rtol=2e-3)
    assert not app.model.error_text
    assert "4 region(s) in 1 file(s)" in _shown(driver)
    saved = workdir / "spot_demo_mixture_analysis" / "molecule_data.tsv"
    assert saved.exists() and (workdir / "joint_output.tsv").exists()

    # Export: the file dialog opens at the button; the table is written where the user saves it
    driver.click("request_export")
    driver.frame(2)
    assert app.dialog is not None and app.dialog.mode == "save"
    app.dialog.directory = str(tmp_path)
    app.dialog.filename = "regions.tsv"
    driver.frame(2)
    driver.click("Save")
    driver.frame(3)
    out = tmp_path / "regions.tsv"
    assert out.exists() and len(out.read_text().splitlines()) == 5  # header + 4 regions
    assert "Exported 4 region(s)" in app.model.status_text

    # Open results: a fresh app reads the saved analysis back
    other, other_driver = _app(loaded_model(workdir))
    other.model.results = []
    other_driver.click("request_open_results")
    other_driver.frame(2)
    assert other.dialog is not None
    other.dialog.directory = str(saved.parent)
    other_driver.frame(2)
    other_driver.click(saved.name)
    other_driver.click("Open")
    other_driver.frame(3)
    assert other.model.status_text.startswith("Loaded 4 region(s)")
    np.testing.assert_allclose(taus(other.model), REFERENCE_TAU, rtol=2e-3)
    app.close()
    other.close()


def test_load_demo_button_fills_the_lists_and_the_run_finds_the_known_lifetimes(
    demo,
    tmp_path,
    monkeypatch,  # noqa: F811
):  # noqa: F811
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    app, driver = _app()
    assert app.model.files == []
    driver.click("request_demo")
    _settle(driver, app, timeout=300.0)
    assert not app.model.error_text, app.model.error_text
    assert [p.rsplit("/", 1)[-1] for p in app.model.files] == ["spot_demo_mixture.ptu"]
    assert [p.rsplit("/", 1)[-1] for p in app.model.irf_files] == ["spot_demo_mixture_irf.ptu"]
    assert "Demo ready: 4 regions detected" in app.model.status_text
    assert "spot_demo_mixture.ptu" in _shown(driver)
    driver.click("request_run")
    _settle(driver, app, timeout=300.0)
    np.testing.assert_allclose(taus(app.model), REFERENCE_TAU, rtol=2e-2)
    app.close()


def test_a_file_that_cannot_be_fitted_stays_reported_after_run(workdir, tmp_path):  # noqa: F811
    bad = tmp_path / "broken.ptu"
    bad.write_bytes(b"not a photon file")
    model = loaded_model(workdir)
    model.files = [str(bad)]
    app, driver = _app(model)
    driver.click("request_run")
    _settle(driver, app)
    assert app.model.results == []
    assert app.model.status_text.startswith("broken.ptu:"), (
        "the failure was wiped when the run ended"
    )
    app.close()
