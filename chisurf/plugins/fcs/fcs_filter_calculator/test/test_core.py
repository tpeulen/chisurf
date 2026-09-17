"""Migration tests: api/core, backend RPC, manifest, CLI, GUI client wiring."""

import pathlib

import numpy as np


def _synthetic(n=64):
    rng = np.random.default_rng(0)
    total = np.abs(rng.random(n)) + 1.0
    sp1 = np.exp(-np.arange(n) / 10.0)
    sp2 = np.exp(-np.arange(n) / 30.0)
    return total, [sp1, sp2]


def test_rpc_client_matches_direct_api():
    from chisurf.plugins.fcs.fcs_filter_calculator import api
    from chisurf.plugins.fcs.fcs_filter_calculator.api import FilterResult
    from chisurf.plugins.fcs.fcs_filter_calculator.gui.client import FilterCalcClient

    total, species = _synthetic()
    direct = api.compute_filters(total, species)
    r = FilterCalcClient().compute(total.tolist(), [s.tolist() for s in species])
    assert r["ok"] is True
    rec = FilterResult.from_dict(r["result"])
    assert np.allclose(rec.filters, direct.filters)


def test_manifest_and_entrypoints():
    from chisurf.core.plugin import load_manifest

    here = pathlib.Path(__file__).resolve().parent.parent
    m = load_manifest(here / "manifest.json")
    assert m is not None and m.id == "fcs_filter_calculator"
    assert m.menu_hidden is True
    assert m.entrypoints.cli and m.entrypoints.services
    names = {rpc.name for rpc in m.rpc_methods}
    assert {"fcs_filter.compute", "fcs_filter.compute_mfd_from_files"} <= names


def test_cli_compute_and_info(tmp_path):
    from chisurf.plugins.fcs.fcs_filter_calculator.cli.main import main

    total, species = _synthetic()
    total_f = tmp_path / "total.txt"
    np.savetxt(total_f, total)
    sp_files = []
    for i, s in enumerate(species):
        f = tmp_path / f"sp{i}.txt"
        np.savetxt(f, s)
        sp_files.append(str(f))
    out = tmp_path / "filters.json"
    args = ["compute", "-t", str(total_f)]
    for f in sp_files:
        args += ["-s", f]
    args += ["-o", str(out)]
    main(args)
    assert out.exists()


def test_widget_routes_through_client(qapp, qtbot):
    from chisurf.plugins.fcs.fcs_filter_calculator.gui import FcsFilterCalculatorWidget

    w = FcsFilterCalculatorWidget()
    qtbot.addWidget(w)
    total, species = _synthetic()
    res = w._compute_filters_rpc(total, species)
    assert res.n_species == 2


def test_synthetic_decay_supports_lifetime_spectra_and_irf():
    from chisurf.plugins.fcs.fcs_filter_calculator.api import synthetic_decay

    decay = synthetic_decay(
        n_bins=128,
        lifetimes=[1.0, 4.0],
        amplitudes=[0.25, 0.75],
        bin_width=0.1,
        irf=[0.0, 1.0, 0.0],
    )

    assert decay.shape == (128,)
    assert np.all(decay >= 0.0)
    assert np.isclose(decay.sum(), 1.0)
    assert decay[0] == 0.0


def test_decay_shot_noise_is_poisson_and_reproducible():
    from chisurf.core.fluorescence.decay import sample_decay_shot_noise
    from chisurf.plugins.fcs.fcs_filter_calculator.api import synthetic_decay

    ideal = synthetic_decay(128, 3.0, bin_width=0.05)
    counts_a = sample_decay_shot_noise(ideal, photon_count=50_000, seed=17)
    counts_b = sample_decay_shot_noise(ideal, photon_count=50_000, seed=17)
    noisy_pattern = synthetic_decay(128, 3.0, bin_width=0.05, photon_count=50_000, seed=17)

    assert np.array_equal(counts_a, counts_b)
    assert np.all(counts_a == np.floor(counts_a))
    assert abs(counts_a.sum() - 50_000) < 1_500
    assert np.isclose(noisy_pattern.sum(), 1.0)
    assert np.allclose(noisy_pattern, counts_a / counts_a.sum())
    assert not np.allclose(noisy_pattern, ideal)


def test_shared_nuisance_patterns_model_afterpulse_and_scatter():
    from chisurf.core.fluorescence.decay import (
        afterpulse_decay_pattern,
        scattered_light_decay_pattern,
    )

    afterpulse = afterpulse_decay_pattern(8)
    scatter = scattered_light_decay_pattern([0.0, 2.0, 1.0], 8)

    assert np.allclose(afterpulse, np.full(8, 1.0 / 8.0))
    assert np.allclose(scatter[:3], [0.0, 2.0 / 3.0, 1.0 / 3.0])
    assert np.all(scatter[3:] == 0.0)
    assert np.isclose(scatter.sum(), 1.0)


def test_synthetic_scatter_irf_is_optimized_against_detector_decay():
    from chisurf.core.fluorescence.decay import (
        afterpulse_decay_pattern,
        optimize_synthetic_scatter_pattern,
    )
    from chisurf.core.fluorescence.tcspc.irf import synthetic_irf
    from chisurf.plugins.fcs.fcs_filter_calculator.api import synthetic_decay, unmix_decay

    n_bins = 160
    dt = 0.05
    time = np.arange(n_bins) * dt
    expected_irf = synthetic_irf(time, center_ns=0.45, fwhm_ns=0.2)
    fast = synthetic_decay(n_bins, 1.2, bin_width=dt, irf=expected_irf)
    slow = synthetic_decay(n_bins, 4.0, bin_width=dt, irf=expected_irf)
    constant = afterpulse_decay_pattern(n_bins)
    total = 12_000 * fast + 5_000 * slow + 900 * expected_irf + 300 * constant

    fitted_irf, fit = optimize_synthetic_scatter_pattern(
        total,
        [fast, slow],
        bin_width_ns=dt,
        initial_fwhm_ns=0.2,
    )
    unmixed = unmix_decay(
        total,
        [fast, slow],
        nuisance_decays=[constant, fitted_irf],
        nuisance_labels=["Afterpulse", "Scatter"],
    )

    assert abs(fit["center_ns"] - 0.45) <= 0.1
    assert 0.1 <= fit["fwhm_ns"] <= 0.32
    assert np.isclose(fitted_irf.sum(), 1.0)
    assert unmixed.nuisance_counts[1] > 500


def test_synthetic_component_can_include_shot_noise():
    from chisurf.plugins.fcs.fcs_filter_calculator.api import synthetic_component_decay

    source = {
        "model": "lifetime",
        "lifetime": 2.5,
        "bin_width": 0.05,
        "shot_noise": True,
        "photon_count": 20_000,
        "noise_seed": 9,
    }
    first = synthetic_component_decay(128, source)
    second = synthetic_component_decay(128, source)

    assert np.array_equal(first, second)
    assert np.isclose(first.sum(), 1.0)


def test_unmix_decay_recovers_nonnegative_component_counts():
    from chisurf.plugins.fcs.fcs_filter_calculator.api import (
        synthetic_decay,
        unmix_decay,
    )

    fast = synthetic_decay(256, 1.0, bin_width=0.05)
    slow = synthetic_decay(256, 4.0, bin_width=0.05)
    total = 12_000.0 * fast + 8_000.0 * slow + 2.0

    result = unmix_decay(total, [fast, slow], fit_background=True)

    assert np.allclose(result.component_counts, [12_000.0, 8_000.0], rtol=1e-4)
    assert np.isclose(result.background_counts, 512.0, rtol=1e-4)
    assert np.allclose(result.reconstruction, total, rtol=1e-6)
    assert np.all(result.component_counts >= 0.0)
    assert np.isclose(result.fractions.sum(), 1.0)


def test_nuisance_patterns_are_fitted_but_excluded_from_species_filters():
    from chisurf.core.fluorescence.decay import (
        afterpulse_decay_pattern,
        scattered_light_decay_pattern,
    )
    from chisurf.plugins.fcs.fcs_filter_calculator.api import (
        FilterResult,
        compute_filters,
        synthetic_decay,
        unmix_decay,
    )

    n_bins = 128
    fast = synthetic_decay(n_bins, 1.0, bin_width=0.05)
    slow = synthetic_decay(n_bins, 4.0, bin_width=0.05)
    afterpulse = afterpulse_decay_pattern(n_bins)
    scatter = scattered_light_decay_pattern(
        np.exp(-0.5 * ((np.arange(n_bins) - 8.0) / 1.5) ** 2), n_bins
    )
    total = 12_000 * fast + 8_000 * slow + 600 * afterpulse + 900 * scatter
    labels = ["Afterpulse / constant", "Scatter / IRF"]

    result = compute_filters(
        total,
        [fast, slow],
        nuisance_decays=[afterpulse, scatter],
        nuisance_labels=labels,
        reject_nuisance=True,
    )
    unmixed = unmix_decay(
        total,
        [fast, slow],
        nuisance_decays=[afterpulse, scatter],
        nuisance_labels=labels,
    )

    assert result.n_species == 2
    assert result.n_filters == 4
    assert result.to_channel_filters().shape == (2, n_bins)
    assert result.nuisance_labels == labels
    assert np.allclose(unmixed.component_counts, [12_000, 8_000], rtol=1e-4)
    assert np.allclose(unmixed.nuisance_counts, [600, 900], rtol=1e-4)
    assert np.allclose(unmixed.reconstruction, total, rtol=1e-6)

    restored = FilterResult.from_dict(result.to_dict())
    assert restored.n_species == 2
    assert restored.n_filters == 4
    assert restored.nuisance_labels == labels


def test_compute_synthetic_filters_records_unmixing_diagnostics():
    from chisurf.plugins.fcs.fcs_filter_calculator.api import (
        compute_synthetic_filters,
        synthetic_decay,
    )

    fast = synthetic_decay(128, 1.2, bin_width=0.1)
    slow = synthetic_decay(128, 3.8, bin_width=0.1)
    total = 9000.0 * fast + 3000.0 * slow

    result = compute_synthetic_filters(
        total,
        lifetimes=[1.2, 3.8],
        bin_width=0.1,
    )

    assert result.n_species == 2
    assert np.allclose(result.metadata["unmixing"]["fractions"], [0.75, 0.25])
    assert result.metadata["synthetic_components"][0]["lifetime"] == 1.2


def test_filter_result_round_trips_synthetic_source_descriptors():
    from chisurf.plugins.fcs.fcs_filter_calculator.api import FilterResult, compute_filters

    total, species = _synthetic()
    source = {
        "type": "synthetic",
        "name": "fast",
        "lifetime": 1.0,
        "bin_width": 0.05,
        "start_bin": 0,
        "irf_path": None,
    }
    result = compute_filters(total, species, species_patterns=[source, ["slow.txt"]])
    restored = FilterResult.from_dict(result.to_dict())

    assert restored.species_patterns == [source, ["slow.txt"]]


def test_synthetic_filters_feed_existing_correlation_weights():
    from chisurf.core.fluorescence.fcs.filtered import photon_filter_weights
    from chisurf.plugins.fcs.fcs_filter_calculator.api import (
        compute_synthetic_filters,
        synthetic_decay,
    )

    fast = synthetic_decay(64, 1.0, bin_width=0.1)
    slow = synthetic_decay(64, 4.0, bin_width=0.1)
    result = compute_synthetic_filters(
        6000.0 * fast + 4000.0 * slow,
        [1.0, 4.0],
        bin_width=0.1,
    )
    photon_microtimes = np.array([0, 2, 8, 16, 32, 63])
    weights = photon_filter_weights(result.to_channel_filters(), photon_microtimes)

    assert weights.shape == (2, photon_microtimes.size)
    patterns = np.stack(result.species_decays)
    patterns /= patterns.sum(axis=1, keepdims=True)
    assert np.allclose(result.filters @ patterns.T, np.eye(2), atol=1e-10)


def test_gaussian_lifetime_component_is_normalized_and_broadened():
    from chisurf.plugins.fcs.fcs_filter_calculator.api import synthetic_component_decay

    mono = synthetic_component_decay(
        256,
        {"model": "lifetime", "lifetime": 3.0, "bin_width": 0.05},
    )
    distributed = synthetic_component_decay(
        256,
        {
            "model": "gaussian_lifetime",
            "mean_lifetime": 3.0,
            "sigma_lifetime": 0.8,
            "n_samples": 81,
            "bin_width": 0.05,
        },
    )

    assert np.isclose(distributed.sum(), 1.0)
    assert np.all(distributed >= 0.0)
    assert not np.allclose(distributed, mono)


def test_fret_distance_component_matches_single_distance_relation():
    from chisurf.plugins.fcs.fcs_filter_calculator.api import (
        synthetic_component_decay,
        synthetic_decay,
    )

    distance_decay = synthetic_component_decay(
        256,
        {
            "model": "gaussian_distance",
            "mean_distance": 50.0,
            "sigma_distance": 0.0,
            "forster_radius": 50.0,
            "donor_lifetime": 4.0,
            "kappa2": 2.0 / 3.0,
            "bin_width": 0.05,
        },
    )
    expected = synthetic_decay(256, 2.0, bin_width=0.05)

    assert np.allclose(distance_decay, expected)


def test_distributed_components_can_be_unmixed_and_filtered():
    from chisurf.plugins.fcs.fcs_filter_calculator.api import (
        compute_filters,
        synthetic_component_decay,
        unmix_decay,
    )

    lifetime_component = synthetic_component_decay(
        192,
        {
            "model": "gaussian_lifetime",
            "mean_lifetime": 1.5,
            "sigma_lifetime": 0.2,
            "bin_width": 0.05,
        },
    )
    distance_component = synthetic_component_decay(
        192,
        {
            "model": "gaussian_distance",
            "mean_distance": 58.0,
            "sigma_distance": 5.0,
            "forster_radius": 52.0,
            "donor_lifetime": 4.0,
            "bin_width": 0.05,
        },
    )
    total = 3000.0 * lifetime_component + 7000.0 * distance_component
    unmixed = unmix_decay(total, [lifetime_component, distance_component])
    filters = compute_filters(total, [lifetime_component, distance_component])

    assert np.allclose(unmixed.fractions, [0.3, 0.7], atol=1e-8)
    assert filters.n_species == 2


def test_central_decay_adapter_uses_all_fit_group_detector_models():
    from types import SimpleNamespace

    from chisurf.core.fluorescence.decay import compute_detector_patterns_from_fit

    class DetectorModel:
        lifetime_spectrum = np.array([1.0, 2.0])

        def __init__(self, scale):
            self.scale = scale
            self.y = np.array([99.0, 99.0, 99.0])

        def evaluate_lifetime_spectrum(self, lifetime_spectrum):
            spectrum = np.asarray(lifetime_spectrum, dtype=float)
            return self.scale * sum(
                amplitude * np.exp(-np.arange(3) / lifetime)
                for amplitude, lifetime in zip(spectrum[0::2], spectrum[1::2])
            )

    green_model = DetectorModel(1.0)
    red_model = DetectorModel(0.4)
    grouped_fit = SimpleNamespace(
        grouped_fits=[
            SimpleNamespace(model=green_model, data=SimpleNamespace(name="green data")),
            SimpleNamespace(model=red_model, data=SimpleNamespace(name="red data")),
        ]
    )

    patterns = compute_detector_patterns_from_fit(
        grouped_fit,
        [0.25, 1.0, 0.75, 4.0],
        detector_names=["green", "red"],
    )

    assert set(("green", "red", "__default__")) <= set(patterns)
    assert np.allclose(patterns["red"], 0.4 * patterns["green"])
    assert np.all(green_model.y == 99.0)
    assert np.all(red_model.y == 99.0)
