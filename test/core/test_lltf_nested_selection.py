"""Scientific regression oracles for lifetime-count scans."""
from __future__ import annotations

import json
import types

import numpy as np
import pytest
from scipy.stats import f

from chisurf.plugins.fluorescence_decay.lltf.core import fitter


def _decay():
    """Return a small usable decay with a delta instrument response."""
    times = np.arange(64, dtype=float) * 0.1
    irf = np.zeros(64)
    irf[0] = 1
    return fitter.Decay(1000 * np.exp(-times / 2), irf, times)


def _scan_with_records(monkeypatch, records, **kwargs):
    """Inject known residual sums to isolate model-selection mathematics."""
    decay = _decay()
    calls = []

    def fit(self, n_lifetimes=1, **options):
        calls.append(options)
        self.lifetime_spectrum = np.tile([1 / n_lifetimes, 2.0], n_lifetimes)
        chi, dof = records[n_lifetimes - 1]
        self.fit_result = {"chi_square": chi, "dof": dof, "reduced_chi_square": chi / dof}
        self.model_decay = self.decay.copy()
        return self.fit_result

    monkeypatch.setattr(decay, "fit", types.MethodType(fit, decay))
    result = decay.find_optimal_lifetime_spectrum(
        maximum_number_of_lifetimes=len(records), plot_probabilities=False,
        plot_weighted_residuals=False, save_intermediate_results=False, **kwargs,
    )
    return result, calls


def test_confidence_uses_extra_sum_of_squares_and_stored_dof(monkeypatch):
    """A known residual reduction gives F=99.8, not a chi-square ratio."""
    result, _ = _scan_with_records(monkeypatch, [(1200.0, 1000), (1000.0, 998)])
    assert result["probabilities"][1] == pytest.approx(f.cdf(99.8, 2, 998))
    assert result["chi_squares"] == [1200.0, 1000.0]
    assert result["dofs"] == [1000, 998]


def test_same_relative_improvement_has_more_support_with_more_data(monkeypatch):
    """Ten-percent improvement across many observations carries more evidence."""
    small, _ = _scan_with_records(monkeypatch, [(22.0, 20), (18.0, 18)])
    large, _ = _scan_with_records(monkeypatch, [(1100.0, 1000), (998.0, 998)])
    assert small["probabilities"][1] < 0.95 < large["probabilities"][1]


def test_nonimproving_fit_has_zero_improvement_confidence(monkeypatch):
    """An optimizer failure cannot support the extra component."""
    result, _ = _scan_with_records(monkeypatch, [(20.0, 20), (30.0, 18)])
    assert result["probabilities"][1] == 0


def test_scan_maps_nuisance_flags_and_seed_to_every_count(monkeypatch):
    """The tail nuisance flags retain their identities as the spectrum grows."""
    _, calls = _scan_with_records(
        monkeypatch, [(40.0, 30), (20.0, 28), (19.0, 26)],
        fixed=[False, False, True, True, False], seed=17,
    )
    assert [c["fixed"] for c in calls] == [
        [False] * 2 + [True, True, False],
        [False] * 4 + [True, True, False],
        [False] * 6 + [True, True, False],
    ]
    assert all(c["seed"] == 17 for c in calls)


def test_scan_rejects_lifetime_specific_fixed_flags():
    """A changing-count scan cannot silently reinterpret a fixed lifetime slot."""
    with pytest.raises(ValueError, match="lifetime.*fixed|fixed.*lifetime"):
        _decay().fit(find_optimal=True, fixed=[True, False, False, False, False],
                     plot_probabilities=False, plot_weighted_residuals=False,
                     save_intermediate_results=False)


def test_nested_scan_retains_exact_embedding_when_optimizer_worsens(monkeypatch, tmp_path):
    """The smaller fitted decay remains representable in every larger model."""
    def bad_optimizer(objective, params, **kwargs):
        result = params.copy()
        if len(params) > 5:
            result[1:-3:2] = 9.0
        objective(result)
        return result, 1

    monkeypatch.setattr(fitter, "minimize", bad_optimizer)
    decay = _decay()
    result = decay.find_optimal_lifetime_spectrum(
        maximum_number_of_lifetimes=3, min_lifetime=2, max_lifetime=2,
        plot_probabilities=False, plot_weighted_residuals=False,
        save_intermediate_results=True,
        intermediate_results_base_filename=str(tmp_path / "nested"),
    )
    assert all(b <= a for a, b in zip(result["chi_squares"], result["chi_squares"][1:]))
    for n, stored_chi in enumerate(result["chi_squares"], start=1):
        stored = json.loads((tmp_path / f"nested_n{n}.json").read_text())
        independent = _decay()
        independent.lifetime_spectrum = np.asarray(stored["lifetime_spectrum"])
        for name in ("irf_shift", "irf_background", "decay_background"):
            setattr(independent, name, stored[name])
        independent.calculate_model_decay()
        residual = (independent.decay - independent.model_decay)[independent.start:independent.stop]
        weights = 1 / np.sqrt(np.maximum(independent.decay[independent.start:independent.stop], 1))
        recomputed_chi = float(np.sum((residual * weights) ** 2))
        assert recomputed_chi == pytest.approx(stored_chi, rel=1e-12, abs=1e-12)
        np.testing.assert_array_equal(independent.model_decay, decay.model_decay)
        if n > 1:
            assert stored["lifetime_spectrum"][-2] == 0
    assert result["best_number_of_lifetimes"] == 1
    assert decay.fit_result["n_lifetimes"] == 1
    assert decay.lifetime_spectrum.tolist() == [1.0, 2.0]


def test_explicit_initial_spectrum_preserves_nuisance_fixed_values(monkeypatch):
    """A warm fit starts from the supplied physical spectrum and fixed nuisance."""
    def unchanged(objective, params, **kwargs):
        objective(params)
        return params, 1

    monkeypatch.setattr(fitter, "minimize", unchanged)
    decay = _decay()
    decay.irf_background = 0.25
    result = decay.fit(n_lifetimes=2, initial_lifetime_spectrum=[0.7, 1.5, 0.3, 4.0],
                       fixed=[False] * 4 + [False, True, False])
    assert result["lifetime_spectrum"] == pytest.approx([0.7, 1.5, 0.3, 4.0])
    assert result["irf_background"] == 0.25
    assert result["dof"] == len(decay.decay[decay.start:decay.stop]) - 6


def test_api_routes_config_seed_and_fixed_irf_background(tmp_path, monkeypatch):
    """File API forwards configured randomness and the established fixed flag."""
    decay = _decay()
    data = tmp_path / "decay.dat"
    irf = tmp_path / "irf.dat"
    np.savetxt(data, np.column_stack([decay.time_axis, decay.decay]))
    np.savetxt(irf, np.column_stack([decay.time_axis, decay.irf]))
    seen = {}

    def capture(self, **kwargs):
        seen.update(kwargs)
        return {"n_lifetimes": kwargs["n_lifetimes"]}

    monkeypatch.setattr(fitter.Decay, "fit", capture)
    fitter.fit_lifetime(str(data), str(irf), n_lifetimes=2, config={
        "estimate_background_parameter": {"enabled": False, "fit_irf_background": False},
        "estimate_irf_shift_parameters": {"enabled": False},
        "lifetime_fit_parameter": {"randomize_initial_values": {"enabled": True, "seed": 23}},
    })
    assert seen["seed"] == 23
    assert seen["fixed"] == [False] * 5 + [True, False]


def test_selected_result_counts_only_the_fixed_nuisance_slots(monkeypatch):
    """The selected scan result uses its own expanded nuisance-mask dof."""
    def unchanged(objective, params, **kwargs):
        objective(params)
        return params, 1

    monkeypatch.setattr(fitter, "minimize", unchanged)
    decay = _decay()
    decay.irf_background = 0.25
    result = decay.fit(find_optimal=True, n_lifetimes=1,
                       fixed=[False, False, True, True, True],
                       maximum_number_of_lifetimes=3,
                       plot_probabilities=False, plot_weighted_residuals=False,
                       save_intermediate_results=False)
    expected = (decay.stop - decay.start) - 2 * result["n_lifetimes"]
    assert result["dof"] == expected
    assert result["irf_background"] == 0.25
    assert result["irf_shift"] == 0
    assert result["decay_background"] == 0
    assert result["optimal_fitting"]["dofs"] == [61, 59, 57]


def test_actual_scan_recovers_biexponential_with_fixed_nuisance():
    """Known lifetimes remain recoverable while all nuisance parameters are fixed."""
    from chisurf.plugins.fluorescence_decay.lltf.test.test_optimal_n_lifetimes import (
        _bi_exponential_decay,
    )

    counts, irf, times = _bi_exponential_decay()
    decay = fitter.Decay(counts, irf, times)
    decay.set_analysis_range(20, 900)
    result = decay.fit(find_optimal=True, fixed=[False, False, True, True, True],
                       maximum_number_of_lifetimes=3, min_lifetime=0.2, max_lifetime=6,
                       plot_probabilities=False, plot_weighted_residuals=False,
                       save_intermediate_results=False, seed=29)
    assert result["n_lifetimes"] == 2
    assert sorted(result["lifetime_spectrum"][1::2]) == pytest.approx([0.5, 4.0], rel=0.03)
    assert result["irf_shift"] == result["irf_background"] == result["decay_background"] == 0
    assert result["dof"] == 876
