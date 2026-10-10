"""The confocal calculator's emtk model: which fields are inputs and which are derived."""

from chisurf.plugins.fcs.fcs_calculator.gui.model import ConfocalModel


def test_the_model_constructs_with_a_title():
    app_module = __import__("chisurf.plugins.fcs.fcs_calculator.gui.app", fromlist=["x"])
    app = app_module.ConfocalApp()
    try:
        assert app.model is not None
    finally:
        app.close()


def test_a_computed_field_is_not_an_input():
    model = ConfocalModel()
    # Default constraint is "Fix D": D is typed in, r_h and Veff are derived.
    assert model.enabled("D_um2_s")
    assert not model.enabled("rh_nm") and not model.enabled("veff_fL")
    model.constraint = "V"
    model.recompute()
    assert model.enabled("veff_fL")
    assert not model.enabled("D_um2_s")
    model.constraint = "D"
    model.recompute()
    assert model.enabled("D_um2_s")
    assert not model.enabled("veff_fL")


def test_the_aspect_box_is_disabled_for_the_default_sphere():
    model = ConfocalModel()
    assert model.shape_type == "Sphere"
    assert not model.enabled("shape_aspect")
    model.shape_type = "Ellipsoid"
    assert model.enabled("shape_aspect")
    model.shape_type = "Sphere"
    assert not model.enabled("shape_aspect")
