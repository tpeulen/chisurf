"""Optimizer convergence is provenance, independent of a valid fit/export."""
from __future__ import annotations

import importlib
import json
from pathlib import Path

import numpy as np
import pytest
import yaml
from click.testing import CliRunner

from chisurf.plugins.fluorescence_decay.lltf.core import fitter


def _small_decay():
    """Return a physical single-component decay with a delta IRF."""
    time = np.arange(64, dtype=float) * 0.1
    irf = np.zeros(64)
    irf[0] = 1
    return fitter.Decay(1000 * np.exp(-time / 2), irf, time)


@pytest.mark.parametrize("status", [-1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 99])
def test_optimizer_status_is_machine_readable_and_exported(monkeypatch, status):
    """Only MINPACK statuses 1 through 4 claim convergence."""
    def report_status(objective, params, **kwargs):
        objective(params)
        return params, status

    monkeypatch.setattr(fitter, "minimize", report_status)
    decay = _small_decay()
    result = decay.fit(n_lifetimes=2)
    exported = json.loads(decay.to_json())
    for record in (result, exported):
        assert record["optimizer_status"] == status
        assert record["converged"] is (1 <= status <= 4)
        assert record["optimizer_message"]
        assert record["optimizer_source"] == "minpack"
    if status == 5:
        assert "maxfev=1600" in result["optimizer_message"]


def test_selected_scan_and_intermediate_json_keep_actual_optimizer_status(monkeypatch, tmp_path):
    """A selected fit with status 5 remains unconverged even when it improves SSE."""
    from chisurf.plugins.fluorescence_decay.lltf.test.test_optimal_n_lifetimes import (
        _bi_exponential_decay,
    )

    original = fitter.minimize

    def reported(objective, params, **kwargs):
        fitted, status = original(objective, params, **kwargs)
        return fitted, 5 if len(params) > 5 else status

    monkeypatch.setattr(fitter, "minimize", reported)
    counts, irf, time = _bi_exponential_decay()
    decay = fitter.Decay(counts, irf, time)
    decay.set_analysis_range(20, 900)
    result = decay.fit(find_optimal=True, maximum_number_of_lifetimes=2,
                       min_lifetime=0.2, max_lifetime=6,
                       plot_probabilities=False, plot_weighted_residuals=False,
                       intermediate_results_base_filename=str(tmp_path / "scan"))
    assert result["n_lifetimes"] == 2
    intermediate = json.loads((tmp_path / "scan_n2.json").read_text())
    for record in (result, intermediate, json.loads(decay.to_json())):
        assert record["optimizer_status"] == 5
        assert record["converged"] is False
        assert record["optimizer_source"] == "minpack"
    assert result["optimal_fitting"]["optimizer_results"][1]["optimizer_status"] == 5


def test_exact_embedding_reports_no_new_convergence_and_keeps_attempt(monkeypatch, tmp_path):
    """An exact nested fallback is not the solution returned by its optimizer."""
    def worse(objective, params, **kwargs):
        fitted = params.copy()
        if len(params) > 5:
            fitted[1:-3:2] = 9
        objective(fitted)
        return fitted, 5 if len(params) > 5 else 1

    monkeypatch.setattr(fitter, "minimize", worse)
    decay = _small_decay()
    decay.find_optimal_lifetime_spectrum(
        maximum_number_of_lifetimes=2, min_lifetime=2, max_lifetime=2,
        plot_probabilities=False, plot_weighted_residuals=False,
        intermediate_results_base_filename=str(tmp_path / "fallback"),
    )
    record = json.loads((tmp_path / "fallback_n2.json").read_text())
    assert record["optimizer_status"] is None
    assert record["converged"] is False
    assert record["optimizer_source"] == "embedded_smaller_model"
    assert record["optimizer_attempt"]["optimizer_status"] == 5
    assert record["optimizer_attempt"]["converged"] is False
    assert record["embedded_from_n_lifetimes"] == 1
    assert decay.fit_result["optimizer_status"] == 1
    assert decay.fit_result["converged"] is True


@pytest.mark.parametrize("converged", [False, True])
def test_cli_completion_text_respects_convergence(monkeypatch, tmp_path, converged):
    """A completed calculation/export may still carry an optimizer warning."""
    module = importlib.import_module("chisurf.plugins.fluorescence_decay.lltf.core.cli")
    record = {"n_lifetimes": 1, "lifetime_spectrum": [1, 2], "irf_shift": 0,
              "decay_background": 0, "reduced_chi_square": 1,
              "optimizer_status": 1 if converged else 5,
              "converged": converged, "optimizer_message": "Reached maxfev=1200"}
    monkeypatch.setattr(module, "fit_lifetime", lambda **kwargs: record)
    data = tmp_path / "data.dat"
    data.touch()
    result = CliRunner().invoke(module.cli, ["fit", str(data), str(data), "-sp", str(tmp_path)])
    assert result.exit_code == 0
    if converged:
        assert "Fit completed successfully." in result.output
    else:
        assert "Fit completed with optimizer warning." in result.output
        assert "Reached maxfev=1200" in result.output
        assert "Fit completed successfully." not in result.output


def test_actual_shipped_file_numerics_do_not_depend_on_reported_status(monkeypatch, tmp_path):
    """Changing only reported status preserves every numeric JSON output exactly."""
    example = Path(fitter.__file__).parents[1] / "example"
    config = yaml.safe_load((example / "config.yml").read_text())
    config["verbose"] = False
    config["lifetime_fit_parameter"]["find_optimal"] = False
    kwargs = {"decay_file": str(example / "5-44_D0.dat"),
              "irf_file": str(example / "IRF_D0.dat"), "n_lifetimes": 2,
              "config": config, "save_intermediate_results": False}
    original = fitter.minimize
    first = fitter.fit_lifetime(**kwargs, output_file=str(tmp_path / "actual.json"))

    def change_only_status(*args, **options):
        params, status = original(*args, **options)
        return params, 5

    monkeypatch.setattr(fitter, "minimize", change_only_status)
    second = fitter.fit_lifetime(**kwargs, output_file=str(tmp_path / "reported.json"))
    excluded = {"optimizer_status", "converged", "optimizer_message", "optimizer_source"}
    def numeric(record):
        """Remove only explicitly additive optimizer provenance."""
        return {key: value for key, value in record.items() if key not in excluded}

    first_json = json.loads((tmp_path / "actual.json").read_text())
    second_json = json.loads((tmp_path / "reported.json").read_text())
    assert numeric(first) == numeric(second)
    assert numeric(first_json) == numeric(second_json)
    (tmp_path / "numeric-reference.json").write_text(json.dumps(first_json, indent=2))
    assert second["optimizer_status"] == 5
    assert second["converged"] is False
