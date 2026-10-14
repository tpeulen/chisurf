"""The LLTF noise models: the Poisson deviance recovers lifetimes the data-weighted chi-square biases.

Decays come from the Synthetic Decay Generator with the plugin's example IRF
(6100 channels of 8 ps, 2e6 photons), as in the decay-tools guide.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.plugins.fluorescence_decay.lltf.core.fitter import fit_lifetime
from chisurf.plugins.fluorescence_decay.synthetic_decay.core.algorithms import compute_decay

_IRF = pathlib.Path(__file__).resolve().parents[1] / "example" / "IRF_D0.dat"


def _decay_file(tmp_path, lifetimes, seed):
    """Write a raw-count synthetic decay and return its path."""
    irf = np.loadtxt(_IRF)[:, 1]
    r = compute_decay(
        n_bins=irf.size,
        lifetimes=lifetimes,
        amplitudes=[1.0 / len(lifetimes)] * len(lifetimes),
        bin_width=0.008,
        irf=irf,
        normalize=False,
        photon_count=2e6,
        seed=seed,
    )
    path = tmp_path / f"decay_{seed}.dat"
    np.savetxt(path, np.column_stack([r["x"], r["y"]]))
    return str(path)


def _fit(tmp_path, decay_file, n, noise_model):
    """Fit *n* lifetimes with *noise_model*; return (lifetimes, amplitudes, result)."""
    res = fit_lifetime(
        decay_file,
        str(_IRF),
        n_lifetimes=n,
        config={
            "lifetime_fit_parameter": {
                "noise_model": noise_model,
                "plot_probabilities": False,
                "plot_weighted_residuals": False,
            },
            "plot_resulting_fit": False,
        },
        save_intermediate_results=False,
        output_file=str(tmp_path / f"fit_{noise_model}_{n}.json"),
    )
    spectrum = np.asarray(res["lifetime_spectrum"])
    order = np.argsort(spectrum[1::2])
    return spectrum[1::2][order], spectrum[::2][order], res


def test_single_exponential_poisson_is_unbiased_neyman_is_not(tmp_path):
    """4.0 ns: the deviance returns 4.00 ns, the data-weighted chi-square pulls it short."""
    f = _decay_file(tmp_path, [4.0], seed=1)
    tau_p, _, res_p = _fit(tmp_path, f, 1, "poisson")
    tau_n, _, res_n = _fit(tmp_path, f, 1, "neyman")
    assert res_p["noise_model"] == "poisson" and res_n["noise_model"] == "neyman"
    assert tau_p[0] == pytest.approx(4.0, abs=0.01)
    assert tau_n[0] < 3.99  # the low-count bias of weighting by the data
    assert res_p["reduced_chi_square"] < res_n["reduced_chi_square"]


def test_close_lifetimes_are_resolved_by_the_deviance(tmp_path):
    """3.0 + 4.5 ns, equal amplitudes: the data-weighted fit lands near 2.4 / 4.1 ns."""
    f = _decay_file(tmp_path, [3.0, 4.5], seed=3)
    taus, amps, _ = _fit(tmp_path, f, 2, "poisson")
    assert taus == pytest.approx([3.0, 4.5], abs=0.15)
    assert amps == pytest.approx([0.5, 0.5], abs=0.08)


def test_unknown_noise_model_is_refused(tmp_path):
    f = _decay_file(tmp_path, [4.0], seed=1)
    with pytest.raises(ValueError, match="noise_model"):
        _fit(tmp_path, f, 1, "gehrels")
