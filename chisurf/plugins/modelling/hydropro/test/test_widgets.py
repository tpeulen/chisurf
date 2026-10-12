"""The HydroPro window (the native emtk app), its view spec, and its settings model."""

import pytest


def test_hydropro_tool_creation():
    """The window is built with its title, the parameter form and the results table drawn."""
    from emtk.testing import Driver

    from chisurf.plugins.modelling.hydropro.app import HydroProApp, make_app

    app = make_app()
    try:
        assert isinstance(app, HydroProApp)
        assert "HYDRO" in app.window_title
        drv = Driver(app, size=app.window_size)
        strings = drv.draw(frames=3).strings
        # AutoForm + controls are present: the parameter panels and the results table.
        assert app.form is not None and app.panels and app.results_sections
        assert "Executable & input" in strings and "Primary model" in strings
        table = next(s for s in app.results_sections if s.get("key") == "data_table")
        assert [c["title"] for c in table["options"]["columns"]][0] == "File"
        assert "File" in strings  # the results table's header is drawn
    finally:
        app.close()


def test_view_spec_loads():
    from chisurf.plugins.modelling.hydropro.app import build_spec

    titles = [s.get("title") for s in build_spec()["params"]]
    assert "Executable & input" in titles
    assert "Primary model" in titles


def test_model_to_settings_roundtrip():
    from chisurf.plugins.modelling.hydropro.core import HydroProSettings
    from chisurf.plugins.modelling.hydropro.gui.model import HydroProModel

    m = HydroProModel()
    m.indmode = "4"
    m.idif = False
    s = m.to_settings()
    assert s.indmode == 4
    assert s.idif == 0
    # load back
    m.load_settings(HydroProSettings(indmode=2, idif=1))
    assert m.indmode == "2"
    assert m.idif is True


def test_settings_validation():
    from chisurf.plugins.modelling.hydropro.core import HydroProSettings

    HydroProSettings().validate()  # defaults are valid
    with pytest.raises(ValueError):
        HydroProSettings(indmode=3).validate()
    with pytest.raises(ValueError):
        HydroProSettings(nq=5, qmax=0.0).validate()


def test_parse_diffusion_coefficient(tmp_path):
    from chisurf.plugins.modelling.hydropro.core import parse_diffusion_coefficient

    res = tmp_path / "case-res.txt"
    res.write_text("Translational diffusion coefficient:  3.760E-07 cm^2/s\n")
    assert parse_diffusion_coefficient(res) == pytest.approx(3.760e-07)
    assert parse_diffusion_coefficient(tmp_path / "missing.txt") is None
