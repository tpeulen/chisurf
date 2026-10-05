"""Explicit MaxEnt configuration survives restore before scientific evaluation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest

from chisurf.core.fitting.fit import Fit
from chisurf.core.models.description import for_family


def _description_fit(family):
    """Build a bounded inverse configuration before attaching the model."""
    from chisurf.core.experiments.tcspc.simulator import TCSPCSimulatorSetup

    data = TCSPCSimulatorSetup(
        n_tac=128,
        dt=0.1,
        lifetime_spectrum=[1.0, 3.5],
        add_noise=False,
        seed=47,
        record_provenance=False,
    ).get_data()[0]
    # The inverse uses the decay-bearing window; zero-count pre-pulse bins
    # have zero reader uncertainty and are not measurements of this decay.
    fit = Fit(data=data, xmin=45, xmax=len(data.y))
    model = for_family(family)(fit)
    model.set_scalar("max_iterations", 40.0)
    model.set_scalar("target_chisq", -1.0)
    settings = {
        "maxent.grid_from": 0.2 if family.endswith("lifetime") else 20.0,
        "maxent.grid_to": 5.5 if family.endswith("lifetime") else 80.0,
        "maxent.grid_bins": 24.0,
        "maxent.log10_nu": -1.5,
    }
    for name, value in settings.items():
        model._spec.set_parameter_value(name, value, False)
    model.set_port_values("maxent_prior", np.linspace(1.0, 2.0, 24))
    fit._model = model
    return fit


@pytest.mark.parametrize("family", ["tcspc_maxent_lifetime", "tcspc_maxent_fret"])
def test_maxent_state_preserves_nonflat_prior(family):
    """A declared vector prior is a scientific input rather than a callback."""
    fit = _description_fit(family)
    state = fit.model.get_state()
    np.testing.assert_array_equal(state["value_ports"]["maxent_prior"], np.linspace(1.0, 2.0, 24))
    replacement = for_family(family)(Fit(data=fit.data))
    replacement.set_state(state)
    np.testing.assert_array_equal(
        replacement._value_ports["maxent_prior"].value, fit.model._value_ports["maxent_prior"].value
    )


def test_maxent_state_restore_defers_solve_until_session_inputs_are_ready(monkeypatch):
    """Saved scalars, links and fit window must precede the first inverse solve."""
    fit = _description_fit("tcspc_maxent_lifetime")
    state = fit.model.get_state()
    replacement = for_family("tcspc_maxent_lifetime")(Fit(data=fit.data))

    def premature_solve(*args, **kwargs):
        """Expose evaluation while the session still has pending inputs."""
        pytest.fail("set_state eagerly evaluated before scalar/range/link restoration")

    monkeypatch.setattr(replacement, "update", premature_solve)
    replacement.set_state(state)


@pytest.mark.parametrize("family", ["tcspc_maxent_lifetime", "tcspc_maxent_fret"])
def test_description_objective_and_published_node_identities_survive_restore(family):
    """Native graph UIDs belong to the saved scientific model, including relays."""
    fit = _description_fit(family)
    state = fit.model.get_state()
    replacement = for_family(family)(Fit(data=fit.data, xmin=fit.xmin, xmax=fit.xmax))
    replacement.set_state(state)
    before, after = fit.model.problem, replacement.problem
    for key in before.get_structure_keys():
        objective = before.get_structure_objective(key)
        restored_objective = after.get_structure_objective(key)
        assert restored_objective.get_uid() == objective.get_uid()
        for name, port in objective.get_ports().items():
            assert restored_objective.get_port(name).uid == port.uid
    for name in before.get_output_names():
        port = before.get_output_port(name)
        restored_port = after.get_output_port(name)
        assert restored_port.uid == port.uid
        assert restored_port.get_node().get_uid() == port.get_node().get_uid()
    assert replacement.get_state()["native_graph_identity"] == state["native_graph_identity"]
    # A restored fit-window edit rebuilds its objective graphs and must retain
    # the identities through which consumers and the registry know the model.
    replacement.fit.xmin += 1
    assert replacement.get_state()["native_graph_identity"] == state["native_graph_identity"]


@pytest.mark.parametrize("family", ["tcspc_maxent_lifetime", "tcspc_maxent_fret"])
def test_bounded_maxent_configuration_has_positive_native_scientific_output(
    family, record_property
):
    """Real native inversion reports finite positive amplitudes and predictions."""
    fit = _description_fit(family)
    started = time.monotonic()
    fit.model.update()
    elapsed = time.monotonic() - started
    record_property("native_solve_seconds", elapsed)
    assert elapsed < 20
    prediction = np.asarray(fit.model.y)
    assert prediction.size == fit.data.y.size
    assert np.all(np.isfinite(prediction)) and np.sum(prediction) > 0
    assert np.sum(prediction) > 0.1 * np.sum(fit.data.y)
    problem = fit.model.problem
    active = problem.get_active_structure()
    amplitudes = np.asarray(problem.get_structure_port(active, f"{active}.maxent", "amplitudes"))
    assert amplitudes.size == 24
    assert np.all(np.isfinite(amplitudes)) and np.sum(amplitudes) > 0


def _deer_fit(filename="test/data/deer/deer_twostate.DSC"):
    """Retain actual measured DEER input and configure a nondefault inverse."""
    from chisurf.core.experiments.deer.reader import DeerReader
    from chisurf.core.models.deer.deer import DeerMaxEntModel

    data = DeerReader(record_provenance=False).get_data(filename=str(filename))[0]
    fit = Fit(data=data, xmin=0, xmax=len(data.y))
    model = DeerMaxEntModel(fit)
    model.grid._n.value = 24
    model.grid._r_min.value = 22
    model.grid._r_max.value = 72
    model.regularization._alpha.value = 0.2
    model.regularization.method = "lcurve"
    model.maxent_iterations = 500
    model.maxent_alpha_samples = 7
    model.maxent_prior = np.linspace(1.0, 2.0, 24)
    fit._model = model
    return fit


def test_deer_maxent_declared_inverse_configuration_survives_state_restore():
    """Grid-independent solver controls and nonuniform prior are declared state."""
    from chisurf.core.models.deer.deer import DeerMaxEntModel

    fit = _deer_fit()
    state = fit.model.get_state()
    assert state["maxent_iterations"] == 500
    assert state["maxent_alpha_samples"] == 7
    np.testing.assert_array_equal(state["maxent_prior"], np.linspace(1.0, 2.0, 24))
    replacement = DeerMaxEntModel(Fit(data=fit.data))
    replacement.set_state(state)
    assert replacement.get_state() == state


def test_deer_maxent_preserves_selected_alpha_across_restore():
    """An auto-selected entropy weight remains the same after a subsequent edit."""
    from chisurf.core.models.deer.deer import DeerMaxEntModel

    fit = _deer_fit()
    fit.model._alpha_cached = 0.017
    fit.model._alpha_used = 0.017
    state = fit.model.get_state()
    replacement = DeerMaxEntModel(Fit(data=fit.data))
    replacement.set_state(state)
    assert replacement._alpha_cached == 0.017
    assert replacement._alpha_used == 0.017


def test_deer_auto_alpha_refinement_retains_declared_prior():
    """The final chosen-weight solve uses the same entropy prior as its sweep."""
    from scipy.integrate import trapezoid

    from chisurf.core.models.deer.kernel import dipolar_kernel
    from chisurf.core.models.deer.maxent import maxent_distance_distribution, maxent_inversion

    r = np.linspace(22.0, 72.0, 16)
    kernel = dipolar_kernel(np.linspace(0.0, 2.0, 32), r)
    prior = np.exp(-0.5 * ((r - 38.0) / 6.0) ** 2) + 0.05
    target = kernel @ (prior / prior.sum())
    actual, alpha = maxent_distance_distribution(
        kernel,
        r,
        target,
        n_iter=500,
        n_alpha=3,
        prior=prior,
        method="lcurve",
    )
    reference = maxent_inversion(kernel, target, 1.0, alpha, prior=prior, n_iter=1500)
    reference /= trapezoid(reference, r)
    np.testing.assert_allclose(actual, reference, rtol=1e-12, atol=1e-12)


def test_deer_bounded_maxent_configuration_computes_real_distribution(record_property):
    """Native DEER inversion reports area-normalized positive distance density."""
    fit = _deer_fit()
    started = time.monotonic()
    fit.model.update()
    elapsed = time.monotonic() - started
    record_property("native_solve_seconds", elapsed)
    assert elapsed < 20
    assert np.all(np.isfinite(fit.model.y)) and np.sum(fit.model.y) > 0
    assert fit.model._p_r.size == 24
    assert np.all(np.isfinite(fit.model._p_r)) and np.sum(fit.model._p_r) > 0
    assert np.trapezoid(fit.model._p_r, fit.model._r) == pytest.approx(1.0)


@pytest.mark.parametrize("family", ["tcspc_maxent_lifetime", "tcspc_maxent_fret", "deer"])
def test_maxent_fresh_session_edit_recompute_resave(tmp_path, family, record_property, monkeypatch):
    """Exact scientific state survives a fresh interpreter and a subsequent edit."""
    from chisurf.core.project.session import capture_session, restore_session
    from chisurf.core.project.storage import load_file, save_file

    sources = []
    if family == "deer":
        for suffix in ("DSC", "DTA"):
            source = tmp_path / f"measured.{suffix}"
            source.write_bytes(Path(f"test/data/deer/deer_twostate.{suffix}").read_bytes())
            sources.append(source)
        fit = _deer_fit(sources[0])
    else:
        fit = _description_fit(family)
    fit.model.update()
    original = np.asarray(fit.model.y).copy()
    project = capture_session([fit.data], [fit])
    path = save_file(project, tmp_path / "maxent.cs.pto")
    for source in sources:
        source.unlink()
    expected = tmp_path / "maxent-expected.json"
    expected.write_text(json.dumps({"predictions": [original.tolist()]}))
    result = subprocess.run(
        [sys.executable, "-m", "test.project.scientific_catalogue_probe", str(path), str(expected)],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    solve_seconds = []
    cls = type(fit.model)
    native_update = cls._update_model

    def configured_update(model, **kwargs):
        """Time actual evaluations and reject any restore with default controls."""
        started = time.monotonic()
        if family == "deer":
            assert model.grid.n_points == 24 and model.maxent_iterations == 500
        else:
            assert model.get_scalar("max_iterations") == 40
            assert model.problem.get_parameter("maxent.grid_bins").value == 24
        native_update(model, **kwargs)
        solve_seconds.append(time.monotonic() - started)

    loaded = load_file(path)
    monkeypatch.setattr(cls, "_update_model", configured_update)
    started = time.monotonic()
    restored = restore_session(loaded)
    restore_seconds = time.monotonic() - started
    record_property("restore_seconds", restore_seconds)
    record_property("restore_native_solve_seconds", sum(solve_seconds))
    record_property("restore_overhead_seconds", restore_seconds - sum(solve_seconds))
    assert len(solve_seconds) == 1
    restored_fit = restored.fits[0]
    np.testing.assert_allclose(restored_fit.model.y, original, rtol=1e-12, atol=1e-12)
    assert capture_session(restored.datasets, restored.fits).fits == project.fits
    if family == "deer":
        restored_fit.model.regularization._alpha.value = 0.6
    else:
        parameter = restored_fit.model.problem.get_parameter("instrument.background")
        held = parameter.fixed
        parameter.fixed = False
        parameter.value = float(parameter.value) + 25.0
        parameter.fixed = held
    restored_fit.model.update()
    assert np.linalg.norm(np.asarray(restored_fit.model.y) - original) > 1e-8
    edited = capture_session(restored.datasets, restored.fits)
    edited_path = save_file(edited, tmp_path / "maxent-edited.cs.pto")
    final = restore_session(load_file(edited_path))
    assert capture_session(final.datasets, final.fits).fits == edited.fits
    np.testing.assert_allclose(final.fits[0].model.y, restored_fit.model.y, rtol=1e-12, atol=1e-12)


@pytest.mark.parametrize("family", ["tcspc_maxent_lifetime", "tcspc_maxent_fret", "deer"])
def test_restored_maxent_supports_bounded_outer_refit(family, monkeypatch, record_property):
    """Restored native inputs remain usable by the existing outer minimizer."""
    import chisurf.core.settings
    from chisurf.core.project.session import capture_session, restore_session

    fit = _deer_fit() if family == "deer" else _description_fit(family)
    fit.model.update()
    restored = restore_session(capture_session([fit.data], [fit])).fits[0]
    ports = [(p.unique_identifier, str(p._port.uid)) for p in restored.model.parameters_all]
    assert restored.model.n_free > 0
    before = restored.chi2
    options = dict(chisurf.core.settings.cs_settings["optimization"]["leastsq"])
    options["maxfev"] = 20
    monkeypatch.setitem(chisurf.core.settings.cs_settings["optimization"], "leastsq", options)
    started = time.monotonic()
    restored.run(record_result=False, estimate_errors=False, finalize=False, notify=False)
    elapsed = time.monotonic() - started
    record_property("outer_refit_seconds", elapsed)
    assert elapsed < 20
    assert np.isfinite(restored.chi2) and restored.chi2 <= before * 1.001
    assert np.all(np.isfinite(restored.model.y)) and np.sum(restored.model.y) > 0
    assert [(p.unique_identifier, str(p._port.uid)) for p in restored.model.parameters_all] == ports
    project = capture_session([restored.data], [restored])
    final = restore_session(project)
    assert capture_session(final.datasets, final.fits).fits == project.fits
