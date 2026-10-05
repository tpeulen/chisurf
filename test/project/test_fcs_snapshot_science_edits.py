"""Measured FCS fixtures with active kinetics and editable inverse distributions."""

import numpy as np
import pytest

from chisurf.core.fitting.fit import Fit
from chisurf.core.project.session import capture_session, restore_session
from chisurf.core.project.storage import load_file, save_file
from test.project.test_all_model_catalogue_roundtrip import CATALOGUE, _data, _resolve


def configure_fcs_science(model):
    """Configure the model through its declared scientific control APIs."""
    name = type(model).__name__
    if name == "FCSKineticsModel":
        model.saturation_mode = "fast"
        sat = model.saturation
        sat.n_states = 4
        sat.dark_unit = "1/ms"
        for parameter in sat.dark.parameters_all:
            parameter.value = 0.0
        # Radiative return, triplet branch/recovery and a second dark branch.
        # These are the default scheme's physical rates expressed in 1/ms,
        # plus a connected fourth state; 250000/ms is a 4 ns lifetime.
        for key, value in {
            "k2_1": 250000.0,
            "k2_3": 2500.0,
            "k3_1": 500.0,
            "k2_4": 50.0,
            "k4_1": 100.0,
        }.items():
            sat.dark.rates_by_name()[key].value = value
        sat._power.value = 20.0
        sat._extinction.value = 73000.0
        sat._N.value = 2.5
        sat._w_r.value = 250.0
        sat._w_z.value = 1250.0
        sat._D.value = 320.0
        sat._N.fixed = False
    elif name in {"MaxEntFCSModel", "MaxEntRHModel"}:
        model._reg.value = -1.0
        model.prior_kind = "lognormal"
        model._prior_width.value = 0.35
        if name == "MaxEntFCSModel":
            model._n_td.value = 24.0
            model._td_min.value = 0.003
            model._td_max.value = 8.0
            model._prior_center.value = 0.4
        else:
            model._n_rh.value = 24.0
            model._rh_min.value = 0.5
            model._rh_max.value = 50.0
            model._w0.value = 280.0
            model._temp.value = 27.0
            model._prior_center.value = 3.0
    else:
        raise ValueError(f"no scientific FCS fixture for {name}")
    model.find_parameters()


def edit_fcs_science(model):
    """Edit a real scheme rate or entropy-prior centre, retaining its fixed state."""
    parameter = (
        model.saturation.dark.rates_by_name()["k3_1"]
        if type(model).__name__ == "FCSKineticsModel"
        else model._prior_center
    )
    parameter.value = float(parameter.value) * 1.5


def fcs_scientific_observables(model):
    """Read reconstructed curves and the primary relaxation/inverse distribution."""
    observables = {"prediction": np.asarray(model.y).tolist()}
    if type(model).__name__ == "FCSKineticsModel":
        observables["relaxation_modes"] = [
            list(pair) for pair in model.saturation.update_relaxation_outputs(model.fit)
        ]
    else:
        distribution = (
            model.maxent_tauD_distribution
            if type(model).__name__ == "MaxEntFCSModel"
            else model.maxent_rH_distribution
        )
        observables["distribution"] = np.asarray(distribution[0]).tolist()
        observables["grid"] = np.asarray(distribution[1]).tolist()
    return observables


def _measured_fcs_fit(name):
    """Construct from the actual bundled Kristine correlation reader output."""
    entry = next(e for e in CATALOGUE if e["configured_path"].endswith(name))
    cls = _resolve(entry["configured_path"])
    data = _data(entry, cls)
    return Fit(data=data, model_class=cls, xmin=0, xmax=len(data.y))


def test_configured_four_state_kinetics_has_active_photochemical_observables():
    """The configured scheme must reach the prediction, beyond its zero-power limit."""
    fit = _measured_fcs_fit("FCSKineticsModel")
    configure_fcs_science(fit.model)
    assert fit.model.saturation.active
    fit.model.update()
    assert fit.model.saturation.n_states == 4
    modes = fit.model.saturation.update_relaxation_outputs(fit)
    assert len(modes) == 3
    assert np.isfinite(modes).all()
    assert all(time > 0 for time, amplitude in modes)
    assert np.isfinite(fit.model.y).all() and np.ptp(fit.model.y) > 0


@pytest.mark.parametrize("name", ["MaxEntFCSModel", "MaxEntRHModel"])
def test_configured_maxent_has_positive_nondefault_grid_and_prior(name):
    """Fixed inversion controls remain editable and produce a real distribution."""
    fit = _measured_fcs_fit(name)
    configure_fcs_science(fit.model)
    fit.model.update()
    distribution = (
        fit.model.maxent_tauD_distribution
        if name == "MaxEntFCSModel"
        else fit.model.maxent_rH_distribution
    )
    p, grid = distribution
    assert len(p) == len(grid) == 24
    assert np.isfinite(p).all() and np.all(p >= 0) and p.sum() > 0
    assert np.isfinite(grid).all() and np.all(grid > 0)
    assert fit.model.prior_kind == "lognormal"
    assert fit.model._prior_center.fixed


@pytest.mark.parametrize("name", ["FCSKineticsModel", "MaxEntFCSModel", "MaxEntRHModel"])
def test_restored_fcs_configuration_edits_primary_science_and_resaves(tmp_path, name):
    """Nondefault restored configuration changes real kinetic/inverse outputs."""
    fit = _measured_fcs_fit(name)
    configure_fcs_science(fit.model)
    fit.model.update()
    initial = fcs_scientific_observables(fit.model)
    project = capture_session([fit.data], [fit])
    restored = restore_session(load_file(save_file(project, tmp_path / "before.cs.pto")))
    assert capture_session(restored.datasets, restored.fits).fits == project.fits
    model = restored.fits[0].model
    assert fcs_scientific_observables(model) == initial
    edit_fcs_science(model)
    model.update()
    changed = fcs_scientific_observables(model)
    assert changed["prediction"] != initial["prediction"]
    primary = "relaxation_modes" if name == "FCSKineticsModel" else "distribution"
    assert changed[primary] != initial[primary]
    assert np.isfinite(model.y).all() and np.ptp(model.y) > 0
    edited = capture_session(restored.datasets, restored.fits)
    second = restore_session(load_file(save_file(edited, tmp_path / "after.cs.pto")))
    assert capture_session(second.datasets, second.fits).fits == edited.fits
    assert fcs_scientific_observables(second.fits[0].model) == changed
