"""Core / CLI / RPC tests for the synthetic decay generator plugin."""

from __future__ import annotations

import json

import numpy as np


def test_compute_decay_shape_and_normalization():
    from chisurf.plugins.fluorescence_decay.synthetic_decay.core.algorithms import compute_decay

    res = compute_decay(n_bins=128, lifetimes=[2.0], bin_width=0.05)
    assert res["n_bins"] == 128
    assert len(res["y"]) == 128 and len(res["x"]) == 128
    assert abs(sum(res["y"]) - 1.0) < 1e-9  # normalized
    y = np.asarray(res["y"])
    assert int(np.argmax(y)) == 0  # ideal decay peaks at t=0


def test_compute_decay_irf_shifts_prompt():
    from chisurf.plugins.fluorescence_decay.synthetic_decay.core.algorithms import compute_decay

    x = np.arange(256)
    irf = np.exp(-0.5 * ((x - 20) / 2.0) ** 2)
    res = compute_decay(n_bins=256, lifetimes=[3.0], bin_width=0.05, irf=irf.tolist())
    assert int(np.argmax(res["y"])) > 5  # convolution moves the peak off bin 0


def test_compute_decay_shot_noise_reproducible():
    from chisurf.plugins.fluorescence_decay.synthetic_decay.core.algorithms import compute_decay

    a = compute_decay(n_bins=128, lifetimes=[2.0], bin_width=0.05,
                      normalize=False, photon_count=50000, seed=7)
    b = compute_decay(n_bins=128, lifetimes=[2.0], bin_width=0.05,
                      normalize=False, photon_count=50000, seed=7)
    assert a["y"] == b["y"]
    assert abs(sum(a["y"]) - 50000) / 50000 < 0.05  # ~photon budget


def test_compute_component_decay_fret():
    from chisurf.plugins.fluorescence_decay.synthetic_decay.core.algorithms import (
        compute_component_decay,
    )

    comp = {"model": "gaussian_distance", "donor_lifetime": 4.0, "forster_radius": 52.0,
            "mean_distance": 50.0, "sigma_distance": 6.0, "bin_width": 0.05}
    res = compute_component_decay(n_bins=256, component=comp)
    assert len(res["y"]) == 256
    assert np.all(np.isfinite(res["y"]))


def test_uses_core_generator_not_a_duplicate():
    # The plugin core must delegate to the single canonical core generator.
    import chisurf.core.fluorescence.decay as core
    from chisurf.plugins.fluorescence_decay.synthetic_decay.core import algorithms

    assert algorithms.synthetic_decay is core.synthetic_decay


def test_cli_generate(tmp_path):
    from click.testing import CliRunner

    from chisurf.plugins.fluorescence_decay.synthetic_decay.cli.main import cli

    out = tmp_path / "d.csv"
    r = CliRunner().invoke(
        cli, ["generate", "--lifetimes", "1.2,4.0", "--amplitudes", "0.7,0.3",
              "--n-bins", "64", "--bin-width", "0.05", "-o", str(out)]
    )
    assert r.exit_code == 0, r.output
    assert out.is_file()
    data = np.loadtxt(out)
    assert data.shape == (64, 2)


def test_rpc_services_register_and_run():
    from chisurf.plugins.fluorescence_decay.synthetic_decay.backend.services import (
        register_services,
    )

    handlers = {}

    class _Dispatcher:
        def register(self, name, fn):
            handlers[name] = fn

    register_services(_Dispatcher())
    assert "synthetic_decay.compute" in handlers
    resp = handlers["synthetic_decay.compute"]({"n_bins": 32, "lifetimes": [2.0], "bin_width": 0.05})
    assert resp["ok"] is True
    assert len(resp["result"]["y"]) == 32
    # error path is reported, not raised
    bad = handlers["synthetic_decay.compute"]({"n_bins": -1, "lifetimes": [2.0]})
    assert bad["ok"] is False and "error" in bad
