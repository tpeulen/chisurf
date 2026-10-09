"""HydroPro's native host metadata leaves parser, settings and exports intact."""

import json

from emtk.testing import Driver

from chisurf.emtk.state import attach_native_state
from chisurf.plugins.modelling.hydropro import app as owner
from chisurf.plugins.modelling.hydropro.core import HydroResult, parse_diffusion_coefficient
from chisurf.plugins.modelling.hydropro.gui.model import HydroProModel, format_diffusion


def test_primary_dimensions_reach_the_host():
    """The native-only primary, rather than Qt parameter metadata, owns the size."""
    app = owner.make_app()
    try:
        assert app.window_size == (1100, 720)
        spec = json.loads((owner.GUI / "hydropro_emtk.view.json").read_text())
        assert spec["window"] == {"width": 1100, "height": 720}
    finally:
        app.close()


def test_authored_primary_dimensions_are_read(monkeypatch):
    """A different valid native declaration reaches the production reader."""
    read = owner.window_size
    received = []

    def authored(spec, fallback):
        """Exercise metadata validation without adapting the parameter panels."""
        received.append(spec["window"])
        return read({**spec, "window": {"width": 960, "height": 680}}, fallback)

    monkeypatch.setattr(owner, "window_size", authored)
    app = owner.make_app()
    try:
        assert app.window_size == (960, 680)
        assert received == [{"width": 1100, "height": 720}]
    finally:
        app.close()


def test_format_fixture_and_csv_survive_default_and_narrow(tmp_path):
    """Rendering preserves a declared parser fixture, without claiming a computation."""
    fixture = owner.GUI.parent / "test/data/recorded/148l-res.txt"
    assert "NOT a computation" in fixture.read_text()
    coefficient = parse_diffusion_coefficient(fixture)
    assert coefficient == 1.047e-6
    model = HydroProModel(work_dir=tmp_path)
    model.struct_files = str(tmp_path / "148l.pdb")
    model.results = [HydroResult(model.struct_files, coefficient)]
    model.cells[model.struct_files] = format_diffusion(coefficient)
    model.status = "Parser fixture, not computation"
    app = owner.HydroProApp(model)
    try:
        rows = model.result_rows()
        settings = model.export_settings()
        for size in [(1100, 720), (736, 552)]:
            Driver(app, size).draw(3)
            assert model.result_rows() == rows
            assert model.export_settings() == settings
            assert {"run", "save_csv", "select_files", "select_exe"} <= app.form.rects.keys()
        export = tmp_path / "result.csv"
        assert model.write_csv(export)
        assert "DiffusionCoefficient(cm^2/s)" in export.read_text()
        assert "1.047e-06" in export.read_text()
    finally:
        app.close()


def test_saved_geometry_and_settings_win(tmp_path, monkeypatch):
    """Existing persistence retains the user's host size and scientific input settings."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    first = attach_native_state("hydro_window_contract", owner.make_app())
    first.model.aer = 6.1
    first.model.indmode = "4"
    first.window_resized(1330, 870)
    first.close()
    restored = attach_native_state("hydro_window_contract", owner.make_app())
    try:
        assert restored.window_size == (1330, 870)
        assert restored.model.aer == 6.1
        assert restored.model.indmode == "4"
    finally:
        restored.close()
