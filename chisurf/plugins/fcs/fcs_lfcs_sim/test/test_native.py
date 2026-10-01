"""Qt-free checks for the EMTK lifetime-FCS surface."""

from chisurf.plugins.fcs.fcs_lfcs_sim.app import LifetimeFcsSimApp, LifetimeFcsSimModel, make_app


def test_native_factory_and_defaults():
    app = make_app()
    assert isinstance(app, LifetimeFcsSimApp)
    assert app.model.tau1_ns == 1.0
    assert app.model.tau2_ns == 4.0


def test_model_settings_are_bounded_by_surface_controls():
    model = LifetimeFcsSimModel()
    model.tau1_ns = 0.05
    model.d2_um2_ms = 100.0
    model.n_photons = 50_000
    assert model.tau1_ns == 0.05
    assert model.d2_um2_ms == 100.0
    assert model.n_photons == 50_000
