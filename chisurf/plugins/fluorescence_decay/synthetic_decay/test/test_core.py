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


def test_synthetic_decay_allow_rise_terms_matches_low_level_builder():
    """allow_rise_terms lets the generator reproduce the acquisition-simulator path.

    With a rise term (negative amplitude) and a zero-lifetime component, the
    canonical generator (normalize=False, ÷Σamp) matches the low-level
    ``calculate_fluorescence_decay`` (normalize=True) exactly, and the strict
    default still rejects the negative amplitude.
    """
    import numpy as np
    import pytest

    from chisurf.core.fluorescence.decay import synthetic_decay
    from chisurf.core.fluorescence.general import calculate_fluorescence_decay

    n, dt = 512, 0.02
    spectrum = np.array([-0.3, 0.4, 0.2, 0.0, 1.0, 2.5])  # rise term + zero-lifetime
    amps, taus = spectrum[0::2].copy(), spectrum[1::2].copy()

    y_new = synthetic_decay(n_bins=n, lifetimes=taus, amplitudes=amps, bin_width=dt,
                            start_bin=0, normalize=False, allow_rise_terms=True)
    y_new = y_new / amps.sum()
    _, y_old = calculate_fluorescence_decay(spectrum.copy(), np.arange(n) * dt)
    assert np.max(np.abs(y_new - y_old)) < 1e-12

    with pytest.raises(ValueError):
        synthetic_decay(n_bins=n, lifetimes=[2.5], amplitudes=[-0.3], bin_width=dt)


def test_tcspc_simulator_reader_uses_canonical_generator():
    """The TCSPC simulator experiment reader produces the canonical decay.

    The reader convolves with the instrument response and scales to the peak
    count, so the reference is the canonical generator driven with the same
    response — not a bare multi-exponential.
    """
    import numpy as np

    from chisurf.core.experiments.tcspc.simulator import (
        TCSPCSimulatorSetup,
        gaussian_irf,
    )
    from chisurf.core.fluorescence.decay import synthetic_decay

    spectrum = [1.0, 1.2, 0.5, 4.0]
    # Construct without a spectrum (avoids the GUI controller coupling in __init__),
    # then set it directly — read() is the code path under test.
    reader = TCSPCSimulatorSetup(n_tac=1024, dt=0.0141, p0=5000.0, add_noise=False)
    reader.lifetime_spectrum = np.asarray(spectrum, dtype=np.float64)
    group = reader.read()
    y = np.asarray(group[0].y, dtype=float)

    time_axis = np.arange(1024) * 0.0141
    y_ref = synthetic_decay(
        n_bins=1024,
        lifetimes=np.asarray(spectrum, float)[1::2],
        amplitudes=np.asarray(spectrum, float)[0::2],
        bin_width=0.0141,
        start_bin=0,
        irf=gaussian_irf(time_axis, mean=reader.irf_mean, sigma=reader.irf_sigma),
        normalize=False,
        allow_rise_terms=True,
    )
    y_ref = y_ref * (5000.0 / y_ref.max())
    assert np.max(np.abs(y - y_ref)) < 1e-9


def test_view_model_load_spectrum(tmp_path):
    """load_spectrum accepts interleaved and 2-column files and fills the table."""
    import numpy as np
    from qtpy import QtWidgets

    from chisurf.plugins.fluorescence_decay.synthetic_decay.gui.view_model import (
        SyntheticDecayViewModel,
    )

    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    inter = tmp_path / "inter.txt"
    twocol = tmp_path / "twocol.txt"
    np.savetxt(inter, np.array([0.3, 1.2, 0.7, 4.0]))
    np.savetxt(twocol, np.array([[0.3, 1.2], [0.7, 4.0]]))
    expected = [{"amp": 0.3, "tau": 1.2}, {"amp": 0.7, "tau": 4.0}]

    for f in (inter, twocol):
        vm = SyntheticDecayViewModel()
        QtWidgets.QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(f), ""))
        vm.load_spectrum()
        assert vm.spectrum_rows == expected
