"""Qt-free checks for the native drift-correction surface."""

from chisurf.plugins.microscopy.img_drift.app import ImgDriftApp, make_app


def test_native_factory_defaults():
    app = make_app()
    assert isinstance(app, ImgDriftApp)
    assert app.model.reference == "first"
    assert app.model.mode == "wrap"


def test_empty_model_reports_no_image():
    app = ImgDriftApp()
    assert app.model.compute() is False
    assert "No image" in app.model.status
