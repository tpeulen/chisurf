"""Standalone calculators must operate when Qt imports are forbidden."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "plugin",
    [
        "fret_calculator",
        "kappa2_dist",
        "phasor_calculator",
        "rics_precision",
        "psf_calculator",
        "fcs_saturation_calc",
    ],
)
def test_factory_without_qt(plugin):
    code = """
import sys
class NoQt:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'qtpy','PyQt5','PyQt6','PySide2','PySide6'}:
            raise ImportError('Qt forbidden: ' + fullname)
sys.meta_path.insert(0, NoQt())
from importlib import import_module
module = import_module('chisurf.plugins.calculator.PLUGIN.gui.app')
app = module.make_app(restore=False)
assert callable(app.gui)
from emtk.testing import RecordingPainter
for width, height in [(900, 620), (1200, 800)]:
    painter = RecordingPainter()
    app.draw(painter, 0, 0, width, height)
    assert painter.strings
assert not any(n.split('.')[0] in {'qtpy','PyQt5','PySide6'} for n in sys.modules)
""".replace("PLUGIN", plugin)
    result = subprocess.run(
        [sys.executable, "-c", code], text=True, capture_output=True, env=os.environ.copy()
    )
    assert result.returncode == 0, result.stderr


def test_fret_inverse_and_homo_backmap():
    from chisurf.plugins.calculator.fret_calculator.gui.app import make_app

    app = make_app()
    m = app.hetero.model
    distance = m.R
    app.hetero._compute_from_efficiency()
    # Distribution-averaged forward efficiency differs from single-distance inverse;
    # use sigma=0 to test the reversible analytic contract.
    m.sigma = 0
    m.R = distance
    app.hetero._compute_forward()
    app.hetero._compute_from_rate()
    assert m.R == pytest.approx(distance)
    h = app.homo.model
    time = h.t_RM
    app.homo._compute_backmap()
    # R_DA is carried as the 2-decimal field shows it (as the Qt spin box did: 51.35, not 51.3521), so
    # the back-mapped time is the Qt tool's 0.9998, not exactly 1.
    assert h.t_RM == pytest.approx(time, rel=1e-3)


def test_boundaries_reject_nan_and_clip_edits(monkeypatch):
    from chisurf.plugins.calculator import inputs

    monkeypatch.setattr(inputs.im, "slider_float", lambda *a, **k: (True, float("nan")))
    assert inputs.bounded_float("Lifetime", 4.0, minimum=0.001, maximum=9999.0) == (False, 4.0)
    monkeypatch.setattr(inputs.im, "slider_float", lambda *a, **k: (True, -10.0))
    assert inputs.bounded_float("Lifetime", 4.0, minimum=0.001, maximum=9999.0) == (True, 0.001)
    monkeypatch.setattr(inputs.im, "slider_int", lambda *a, **k: (True, 30))
    assert inputs.bounded_int("Harmonic", 1, minimum=1, maximum=16) == (True, 16)


def test_kappa_export_preserves_histogram(tmp_path):
    from chisurf.plugins.calculator.kappa2_dist.gui.app import make_app

    app = make_app()
    path = tmp_path / "kappa.csv"
    app.write_csv(path)
    lines = path.read_text().splitlines()
    assert "# Model: cone" in lines
    assert len([line for line in lines if not line.startswith("#")]) == len(app.tool._model._k2hist)


def test_rics_export_requires_prediction(tmp_path):
    from chisurf.plugins.calculator.rics_precision.gui.app import make_app

    app = make_app()
    with pytest.raises(ValueError, match="Predict"):
        app.write_csv(tmp_path / "precision.csv")


@pytest.mark.parametrize(
    "module", ["chisurf.plugins.fcs.fcs_calculator.gui.app", "chisurf.plugins.fret_line.gui.app"]
)
def test_additional_factory_without_qt(module):
    code = """
import sys
class NoQt:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'qtpy','PyQt5','PyQt6','PySide2','PySide6'}:
            raise ImportError('Qt forbidden: ' + fullname)
sys.meta_path.insert(0,NoQt())
from importlib import import_module
from emtk.testing import RecordingPainter
app=import_module('MODULE').make_app()
app.draw(RecordingPainter(),0,0,1200,800)
""".replace("MODULE", module)
    result = subprocess.run(
        [sys.executable, "-c", code], text=True, capture_output=True, env=os.environ.copy()
    )
    assert result.returncode == 0, result.stderr


def test_confocal_constraints_occupancy_and_settings():
    from chisurf.plugins.fcs.fcs_calculator.gui.app import make_app

    app = make_app()
    app.model.num_mols = 2
    app.edited("num_mols")
    assert app.model.invN == pytest.approx(0.5)
    old_D = app.model.D_um2_s
    app.model.constraint = "V"
    app.model.recompute()
    assert app.model.D_um2_s == pytest.approx(old_D)
    snapshot = app.settings()
    app.model.tau_us = 100
    app.model.apply_settings(snapshot)
    assert app.model.tau_us == 70
    app.shape = 0
    app.model.shape_size_nm = 2
    app.model.apply_shape()
    assert app.model.rh_nm == pytest.approx(1.0)


def test_fret_line_collection_and_export(tmp_path):
    from chisurf.plugins.fret_line.gui.app import make_app

    app = make_app()
    app.model.n_points = 5
    line = app.model.add_line()
    assert len(line["result"]["tau_f"]) == 5
    app.model.add_line()
    path = tmp_path / "lines.csv"
    app.model.write_csv(path)
    assert len(path.read_text().splitlines()) == 12


def test_saturation_scheme_roundtrip_and_units(tmp_path):
    from chisurf.plugins.calculator.fcs_saturation_calc.gui.model import SaturationModel

    model = SaturationModel()
    matrix = model.saturation.dark.rate_matrix().copy()
    model.rate_unit = "1/ns"
    assert model.saturation.dark.rate_matrix() == pytest.approx(matrix * 0.001)
    path = tmp_path / "scheme.json"
    model.save_scheme_to_file(str(path))
    model.load_scheme_from_file(str(path))
    assert model.saturation.dark.rate_matrix() == pytest.approx(matrix * 0.001)
    assert len(model.fcs_curves_series) >= 2


def test_psf_full_volume_export_and_native_render(tmp_path):
    import numpy as np
    from emtk.testing import RecordingPainter

    from chisurf.plugins.calculator.psf_calculator.gui.app import make_app

    app = make_app()
    app.model.model = "gaussian"
    app.model.nxy = 16
    app.model.nz = 3
    app.model.compute()
    app.draw(RecordingPainter(), 0, 0, 1200, 800)
    path = tmp_path / "psf.npy"
    app.model.save(path)
    assert np.load(path) == pytest.approx(app.model.volume)


def test_fret_live_parameter_bounds_fixed_and_donor_reference():
    from chisurf.core.registry.parameter_groups import get_registered_parameter_group
    from chisurf.plugins.fret_line.core.algorithms import _parameters_of
    from chisurf.plugins.fret_line.gui.app import make_app

    app = make_app()
    model = app.model.components[0]["model"]
    parameter = _parameters_of(model)[0]
    parameter.bounds = (0.1, 10.0)
    parameter.bounds_on = True
    parameter.fixed = True
    parameter.value = 2.0
    assert parameter.fixed and parameter.bounds == (0.1, 10.0)
    app.model.apply_donor_reference(
        {("amplitude", 0): 0.6, ("tau", 0): 3.0, ("amplitude", 1): 0.4, ("tau", 1): 1.0}
    )
    from chisurf.core.fluorescence.fret.fret_line import find_parameter

    assert find_parameter(model, "donor.tau.0").value == pytest.approx(3.0)
    assert find_parameter(model, "donor.tau.1").value == pytest.approx(1.0)
    owner = next(iter(app.model._registered))
    assert get_registered_parameter_group(owner) is model
    app.close()
    assert get_registered_parameter_group(owner) is None


@pytest.mark.parametrize("efficiency", [0.0, 1.0])
def test_fret_efficiency_endpoints_keep_finite_plot_state(efficiency):
    import numpy as np

    from chisurf.plugins.calculator.fret_calculator.gui.app import make_app

    app = make_app()
    app.hetero.model.E = efficiency
    app.hetero._compute_from_efficiency()
    assert np.isfinite(app.hetero.model.R)
    assert np.isfinite(app.hetero.model.kFRET)
    assert np.isfinite(app.hetero.model.tau)
    for series in app.hetero.model.distance_plot_series():
        assert np.isfinite(series["x"]).all()


def test_saturation_restored_rate_units_preserve_physics(tmp_path):
    from chisurf.plugins.calculator.fcs_saturation_calc.gui.model import SaturationModel

    model = SaturationModel()
    model.rate_unit = "1/ns"
    expected = model.saturation.dark.rate_matrix().copy()
    path = tmp_path / "session.json"
    model.get_user_settings_path = lambda: str(path)
    model.save_user_settings()
    restored = SaturationModel()
    restored.get_user_settings_path = lambda: str(path)
    restored.load_user_settings()
    assert restored.rate_unit == "1/ns"
    assert restored.saturation.dark_unit == "1/ns"
    assert restored.saturation.dark.rate_matrix() == pytest.approx(expected)


def test_default_fret_sweep_is_visible_and_preserves_editor_values():
    import numpy as np

    from chisurf.plugins.fret_line.core.algorithms import _parameters_of
    from chisurf.plugins.fret_line.gui.app import make_app

    app = make_app()
    parameters = _parameters_of(app.model.components[0]["model"])
    values = [p.value for p in parameters]
    app.model.n_points = 10
    result = app.model.add_line()["result"]
    assert np.ptp(result["tau_f"]) > 0.1
    assert [p.value for p in parameters] == pytest.approx(values)
    ordinary = len(app.model.sweep_targets())
    target = app.model.sweep_targets()[app.model.sweep_index]["name"]
    app.model.show_all_parameters = True
    assert len(app.model.sweep_targets()) > ordinary
    assert app.model.sweep_targets()[app.model.sweep_index]["name"] == target


def test_fret_input_curve_bind_unload_and_catalog_are_real(monkeypatch):
    import numpy as np

    import chisurf
    from chisurf.core.data import DataCurve, ExperimentDataCurveGroup
    from chisurf.plugins.fret_line.gui.app import make_app

    curve = DataCurve(
        x=np.arange(32) * 0.1, y=np.exp(-0.5 * ((np.arange(32) - 10) / 2) ** 2), name="Measured IRF"
    )
    monkeypatch.setattr(chisurf, "imported_datasets", [ExperimentDataCurveGroup([curve])])
    app = make_app()
    assert curve in app.input_curves()
    model = app.model.components[0]["model"]
    assert "response" in model.dataset_slots()
    app.model.bind_input("response", curve)
    assert model.has_dataset("response")
    assert model.get_scalar("generated_response") == 0.0
    app.model.unload_input("response")
    assert not model.has_dataset("response")
    assert model.get_scalar("generated_response") == 1.0
