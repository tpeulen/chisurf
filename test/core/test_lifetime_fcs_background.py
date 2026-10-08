"""Physical background contracts for the native lifetime-FCS simulator."""

import copy

import numpy as np
import pytest

from chisurf.core.fluorescence.fcs import simulate


@pytest.mark.parametrize("channels, width_ns", [(64, 0.125), (512, 0.032), (2048, 0.016)])
def test_uncorrelated_background_spans_the_declared_laser_period(channels, width_ns, capfd):
    """Native background photons sample a flat TAC axis rather than prompt scatter."""
    stream = simulate.simulate_lifetime_fcs(
        (1.0,),
        (0.0,),
        population=(0.0,),
        brightness_cps=(0.0,),
        n_photons=20_000,
        seed=17,
        background_cps=1_000_000.0,
        n_microtime_channels=channels,
        micro_time_resolution_ns=width_ns,
    )
    assert "background_decay" not in capfd.readouterr().err
    assert stream.species.size >= 20_000
    assert np.all(stream.species == 1)  # Native background label follows real species.
    assert stream.micro_times.min() >= 0
    assert stream.micro_times.max() < channels
    phase_ns = stream.micro_times * width_ns
    period_ns = channels * width_ns
    assert phase_ns.min() < period_ns / 16
    assert phase_ns.max() > period_ns * 15 / 16
    # Eight broad bins keep this statistical check independent of native bin rounding.
    phase_histogram, _ = np.histogram(phase_ns, bins=8, range=(0.0, period_ns))
    expected = stream.micro_times.size / 8
    assert np.all(np.abs(phase_histogram - expected) < 0.10 * expected)


def test_background_configuration_matches_the_tac_axis_and_rate(monkeypatch):
    """The caller declares counts/ms and a calibrated flat decay to the actual engine."""
    configs = []
    native_build = simulate.build_engine

    def record_config(config):
        """Observe configuration while preserving the native construction and run."""
        configs.append(copy.deepcopy(config))
        return native_build(config)

    monkeypatch.setattr(simulate, "build_engine", record_config)
    simulate.simulate_lifetime_fcs(
        (1.0,),
        (0.0,),
        n_photons=200,
        background_cps=2.0,
        n_microtime_channels=128,
        micro_time_resolution_ns=0.25,
    )
    config = configs[0]
    assert config["background"] == [0.002]
    assert config["background_decay"] == {"pattern": [1.0] * 128, "dt": 0.25}
    assert config["settings"]["laser_period"] == 32.0


def test_zero_background_retains_the_original_native_signal_configuration(monkeypatch, capfd):
    """No background decay is introduced when only fluorescent species emit."""
    configs = []
    native_build = simulate.build_engine

    def record_config(config):
        """Observe configuration while preserving the native construction and run."""
        configs.append(copy.deepcopy(config))
        return native_build(config)

    monkeypatch.setattr(simulate, "build_engine", record_config)
    stream = simulate.simulate_lifetime_fcs(
        (1.0, 4.0),
        (8.0, 0.5),
        n_photons=2_000,
        seed=3,
        background_cps=0.0,
    )
    assert configs[0]["background"] == [0.0]
    assert "background_decay" not in configs[0]
    assert "background_decay" not in capfd.readouterr().err
    assert set(np.unique(stream.species)) == {0, 1}
    assert stream.reference_decays[0].sum() + stream.reference_decays[1].sum() == len(
        stream.species
    )

    # Preserve the complete signal-only native configuration, not a hardcoded
    # random-stream hash tied to one engine build.
    from chisurf.core.fluorescence.simulation import seeds

    expected_config = {
        "settings": {
            "dt": 0.005,
            "n_ph_max": 2_000,
            "n_channels": 1,
            "n_microtime_channels": 2048,
            "microtime_resolution": 0.016,
            "laser_period": 32.768,
            "fast_grid_bbox": True,
            "active_margin": 1.0,
            **seeds(3),
        },
        "box": {"xy": 1.5, "z": 3.0},
        "species": [
            {"D": 8.0, "q": [120.0], "decay": {"lifetimes": [1.0]}},
            {"D": 0.5, "q": [120.0], "decay": {"lifetimes": [4.0]}},
        ],
        "k_rad": [0.0] * 4,
        "k_nrad": [0.0] * 4,
        "background": [0.0],
        "population": [1.5, 1.5],
        "excitation": {
            "type": "gaussian3d",
            "w0": 0.3,
            "z0": 2.0,
            "extent_xy": 1.5,
            "extent_z": 3.0,
            "spacing": 0.1,
        },
    }
    assert configs[0] == expected_config
    reference = native_build(expected_config)
    reference.run()
    expected_macro_ms = np.asarray(reference.macro_window()) * 0.005 + np.asarray(
        reference.arrival_time()
    )
    expected_ticks = np.maximum.accumulate(
        np.round(expected_macro_ms * 1e-3 / 1e-7).astype(np.uint64)
    )
    np.testing.assert_array_equal(stream.macro_times, expected_ticks)
    np.testing.assert_array_equal(stream.micro_times, reference.micro_time())
    np.testing.assert_array_equal(stream.species, reference.emitting_species())
