"""Declared maximum-entropy geometry preserves solver inputs and native layouts."""

from __future__ import annotations

import pytest
from emtk.testing import Driver

from chisurf.emtk.state import attach_native_state
from chisurf.plugins.fluorescence_decay.maxent_decay.gui.app import make_app


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Build the real native tool with isolated preferences and worker authority."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "db.sqlite"))
    monkeypatch.chdir(tmp_path)
    instance = make_app()
    yield instance
    instance.close()


def test_primary_window_metadata_reaches_true_constructor_before_panels(app):
    """The primary declaration reaches the standalone native host before panel adaptation."""
    assert app.window_size == (1100, 720)
    attach_native_state("maxent-decay", app)
    assert app.window_size == (1100, 720)
    driver = Driver(app, app.window_size)
    driver.draw(3)
    assert "run" in driver.ids()


def test_raw_primary_spec_drives_shared_reader(app, monkeypatch):
    """The reader sees raw window metadata and the declared form panels together."""
    import chisurf.plugins.fluorescence_decay.maxent_decay.gui.app as module

    original = module.window_size
    seen = []

    def declared(spec, default):
        """Exercise a different primary declaration without replacing the factory."""
        seen.append((spec["window"], "panels" in spec, default))
        return original({**spec, "window": {"width": 1234, "height": 789}}, default)

    monkeypatch.setattr(module, "window_size", declared)
    other = make_app()
    try:
        assert other.window_size == (1234, 789)
        assert seen == [({"width": 1100, "height": 720}, True, (1100, 720))]
    finally:
        other.close()


def test_native_reopen_restores_geometry_preferences_and_docks_without_data(app):
    """Native close/reopen preserves definitions while measured arrays remain explicitly loaded."""
    attach_native_state("maxent-decay", app)
    app.model.settings.tau_bins = 24
    app.model.settings.background = 5.0
    app.model.sample_steps = 20
    app.last_dir = "measurement-workflow"
    settings = app.export_settings()
    Driver(app, (1100, 720)).draw(3)
    app.docks.undock("distribution", (20, 30, 420, 360))
    layout = app.docks.state()
    app.window_resized(1330, 870)
    app.close()
    reopened = attach_native_state("maxent-decay", make_app())
    try:
        assert reopened.window_size == (1330, 870)
        assert reopened.export_settings() == settings
        assert reopened.docks.state()["windows"] == layout["windows"]
        assert reopened.model.decay is None and reopened.model.result is None
    finally:
        reopened.close()


def test_clamped_fret_toggle_keeps_entire_caption_and_changes_real_preference(app):
    """A narrow donor-only constraint remains readable and reachable."""
    app.model.settings.mode = "fret"
    driver = Driver(app, (736, 552))
    painter = driver.draw(3)
    caption = next(record for record in painter.texts if record[5] == "fix donor-only fraction")
    x, y, _, height, _, label, *_ = caption
    dock = app.docks.region_boxes["controls"]
    assert x + painter.text_width(label) <= dock[0] + dock[2]
    driver.click((x + 6, y + height / 2))
    assert app.model.fix_x_donly


def test_distribution_caption_describes_actual_basis_coefficients(app):
    """The native plot does not present unnormalized signal amplitudes as probabilities."""
    painter = Driver(app, (1100, 720)).draw(3)
    assert "Amplitude" in painter.strings
    assert "Probability" not in painter.strings


def test_clamped_sampling_toggle_is_readable_and_reachable_after_real_fold_scroll(app):
    """The final sampling preference can be read and pressed after opening its real fold."""
    app.model.settings.mode = "fret"
    driver = Driver(app, (736, 552))
    driver.draw(3)
    for _ in range(12):
        driver.wheel(-2, at=(120, 420))
    painter = driver.draw(3)
    fold = next(record[:4] for record in painter.texts if "L-curve span and sampling" in record[5])
    assert 0 <= fold[1] < fold[1] + fold[3] <= 552
    driver.click(fold)
    for _ in range(18):
        driver.wheel(-2, at=(120, 420))
    painter = driver.draw(3)
    caption = next(record for record in painter.texts if record[5] == "Vectorized sampling")
    x, y, _, height, _, label, *_ = caption
    dock = app.docks.region_boxes["controls"]
    assert x + painter.text_width(label) <= dock[0] + dock[2]
    assert 0 <= y < y + height <= 552
    driver.click((x + 6, y + height / 2))
    assert app.model.sample_vectorized


@pytest.mark.parametrize("mode", ["lifetime", "fret"])
def test_actual_measured_worker_result_and_objective_survive_resize(app, mode):
    """Real isolated solves retain their basis, nuisance values, weighted residuals and inputs."""
    import time
    from pathlib import Path

    import numpy as np

    from chisurf.plugins.fluorescence_decay.maxent_decay.gui.model import solve_snapshot

    base = Path(__file__).resolve().parents[2] / "test/data/tcspc/EasyTau300"
    stem = "D0" if mode == "lifetime" else "DA"
    model = app.model
    model.load_file(base / f"215-268 {stem}.dat")
    model.load_file(base / f"215-268 {stem} irf.dat", irf=True)
    settings = model.settings
    settings.mode = mode
    settings.tau_bins, settings.r_bins = 16, 16
    settings.tau_min, settings.tau_max = 0.4, 8.0
    settings.r_min_frac, settings.r_max_frac = 0.5, 1.8
    settings.max_iter, settings.background = 60, 5.0
    if mode == "fret":
        donor = Path.cwd() / "explicit-assumed-donor.txt"
        np.savetxt(donor, [[1.0, 4.1]])
        model.load_donor(donor)
    model.fitrange = (700, len(model.decay) - 1)
    driver = Driver(app, (1100, 720))
    driver.draw(3)
    driver.click("run")
    deadline = time.monotonic() + 90
    while app.jobs.process is not None and time.monotonic() < deadline:
        time.sleep(0.02)
        driver.draw(1)
    assert app.jobs.process is None
    assert model.status == "run completed.", app.jobs.output
    result = model.result
    expected = solve_snapshot(model.result_snapshot)
    for name in ("p", "Fi", "H", "g0", "sigma", "y", "fit_additive"):
        np.testing.assert_array_equal(result[name], expected[name])
    basis = result["Fi"] * result["sigma"][:, None]
    fit = basis @ result["p"] + result["fit_additive"]
    residual = (result["y"] - fit) / result["sigma"]
    assert np.mean(residual**2) == pytest.approx(result["chisq"], rel=1e-10)
    assert np.mean((result["y"] - fit)**2 / np.maximum(fit, 1.0)) == pytest.approx(
        result["chisq_pearson"], rel=1e-10
    )
    np.testing.assert_allclose(result["H"], 2 / len(fit) * result["Fi"].T @ result["Fi"])
    before = {key: np.array(value) for key, value in model.arrays().items()}
    declared = app.export_settings()
    for size in ((736, 552), (800, 600), (1330, 870)):
        driver.draw(3, size=size)
    assert app.export_settings() == declared
    for key, value in before.items():
        np.testing.assert_array_equal(model.arrays()[key], value)
