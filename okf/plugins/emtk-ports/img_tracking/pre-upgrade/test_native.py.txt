from chisurf.plugins.microscopy.img_tracking.app import ImgTrackingApp, make_app


def test_native_factory_defaults():
    app = make_app()
    assert isinstance(app, ImgTrackingApp)
    assert app.model.use_simulation is False

def test_simulation_can_run_without_a_file():
    app = ImgTrackingApp()
    app.model.use_simulation = True
    assert app.model.can_run() == ""

