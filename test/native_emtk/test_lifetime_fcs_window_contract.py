"""Declared Lifetime-FCS geometry preserves savedlayouts and actualsimulatedcurves."""

from __future__ import annotations

import numpy as np
import pytest
from emtk.testing import Driver

from chisurf.emtk.state import attach_native_state
from chisurf.plugins.fcs.fcs_lfcs_sim.app import make_app


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Build the actualsimulator with isolatedsettings and providerstate."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "db.sqlite"))
    instance = make_app()
    yield instance
    instance.close()


def test_primary_default_reaches_standalone_state_binding(app):
    """The truefactorydeclares the toolsizedefault beforepersistencebinds."""
    assert app.window_size == (1100, 720)
    attach_native_state("fcs-lfcs-sim", app)
    assert app.window_size == (1100, 720)
    driver = Driver(app, app.window_size)
    driver.draw(3)
    assert "lfcs_sim_controls" in driver.ids()


def test_saved_custom_geometry_and_layout_override_default(app):
    """Actualclose/reopen keeps usergeometry and dockplacement."""
    attach_native_state("fcs-lfcs-sim", app)
    Driver(app, (1100, 720)).draw(3)
    app.docks.undock("form", (40, 50, 440, 400))
    saved = app.docks.state()
    app.window_resized(1390, 910)
    app.close()
    reopened = attach_native_state("fcs-lfcs-sim", make_app())
    try:
        assert reopened.window_size == (1390, 910)
        assert reopened.docks.state()["layout"] == saved["layout"]
        assert reopened.docks.state()["windows"] == saved["windows"]
        Driver(reopened, reopened.window_size).draw(3)
    finally:
        reopened.close()


def test_loaded_primary_declaration_drives_factory(app, monkeypatch):
    """The sharedreaderreceives the actualprimaryspec and familydefault."""
    import chisurf.plugins.fcs.fcs_lfcs_sim.app as module

    original = module.window_size
    seen = []

    def declared(spec, default):
        """Record actualdeclaration and exercise a differentspecsize."""
        seen.append((spec["window"], default))
        return original({**spec, "window": {"width": 1234, "height": 789}}, default)

    monkeypatch.setattr(module, "window_size", declared)
    other = make_app()
    try:
        assert other.window_size == (1234, 789)
        assert seen == [({"width": 1100, "height": 720}, (1100, 720))]
    finally:
        other.close()


def test_actual_worker_curves_survive_resize_and_equal_independent_native_reference(app):
    """Actualbutton simulation retains allcorrelations and conditionnumber onresize."""
    from chisurf.core.fluorescence.fcs.filtered import calc_ffcs_filters, filter_condition_number
    from chisurf.core.fluorescence.fcs.simulate import simulate_lifetime_fcs
    from chisurf.plugins.fcs.fcs_correlator.core import filtered_correlation_datasets

    settings = {"tau1_ns": 1.0, "tau2_ns": 4.0, "d1_um2_ms": 2.0, "d2_um2_ms": 2.0,
                "exchange_rate_ms": 5.0, "n_photons": 60000, "seed": 7}
    for name, value in settings.items():
        setattr(app.model, name, value)
    driver = Driver(app, (1100, 720))
    driver.draw(3)
    driver.click("lfcs_sim_controls")
    if app._future is not None:
        app._future.result(timeout=120)
    app.poll()
    before = [(data["name"], data["species_a"], data["species_b"],
               np.asarray(data["x"]).copy(), np.asarray(data["y"]).copy())
              for data in app.model.datasets]
    assert len(before) == 3
    condition = app.model.condition_number
    simulation = simulate_lifetime_fcs(lifetimes_ns=(1.0, 4.0), diffusion_um2_ms=(2.0, 2.0),
                                      exchange_rate_ms=5.0, n_photons=60000, seed=7)
    filters, _, _ = calc_ffcs_filters(simulation.total_decay, simulation.reference_decays)
    reference = filtered_correlation_datasets(simulation.macro_times, simulation.micro_times,
                                             filters, simulation.macro_time_resolution_s,
                                             n_bins=8, n_casc=25, labels=["τ=1 ns", "τ=4 ns"])
    assert condition == filter_condition_number(simulation.total_decay, simulation.reference_decays)
    driver.draw(3, size=(1390, 910))
    for saved, actual, expected in zip(before, app.model.datasets, reference, strict=True):
        assert saved[:3] == (actual["name"], actual["species_a"], actual["species_b"])
        assert actual["name"] == expected["name"]
        np.testing.assert_array_equal(saved[3], actual["x"])
        np.testing.assert_array_equal(saved[4], actual["y"])
        np.testing.assert_array_equal(actual["x"], expected["x"])
        np.testing.assert_array_equal(actual["y"], expected["y"])
    assert app.model.condition_number == condition


def test_initial_clamped_species_caption_is_fully_visible_and_real_fold_reaches_fields(app):
    """The actualinitialscreenclamp retains readablefoldcaption and realfields."""
    driver = Driver(app, (736, 552))
    driver.draw(3)
    index = next(i for i, text in enumerate(driver.painter.texts) if text[5] == "Species")
    metrics = driver.painter.text_metadata[index]
    assert metrics["measured_bounds"] == metrics["visible_bounds"]
    fields = {"tau1_ns", "d1_um2_ms", "tau2_ns", "d2_um2_ms"}
    assert fields <= set(driver.ids())
    driver.click("Species")
    assert not fields & set(driver.ids())
    driver.click("Species")
    assert fields <= set(driver.ids())
