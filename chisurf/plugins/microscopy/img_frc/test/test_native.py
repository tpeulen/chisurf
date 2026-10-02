from chisurf.plugins.microscopy.img_frc.gui.app import ImgFrcApp, make_app


def test_native_factory_defaults():
    app = make_app()
    assert isinstance(app, ImgFrcApp)
    assert app.model.split == "even_odd"

def test_empty_model_reports_no_image():
    app = ImgFrcApp()
    assert app.model.compute() is False
    assert "No image" in app.model.status
