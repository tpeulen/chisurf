"""The two MEM solver paths must return one result contract.

``solve_lifetime_mem`` has a fast path that hands the problem to the compiled
MEM engine and a pure-Python path. Both are supposed to be the same function,
but only the Python path used to attach the design matrix and the fitted
segment — so every consumer that plots or scores a result (the GUI, the
sampler, the saved JSON) raised ``KeyError: 'Fi'`` whenever the compiled engine
was present, which on a normal install is always.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.fluorescence_decay.maxent_decay.core.solver import (
    solve_lifetime_mem,
)

#: What a result has to carry for the plots and the sampler to work.
REQUIRED = ("p", "tau", "Fi", "H", "g0", "y", "sigma", "fitrange", "fit_additive")


def _problem(n: int = 256, dt: float = 0.0323, oversample: int = 32):
    """A reconvolved two-lifetime decay and the lamp it was built from.

    Built on a fine grid and averaged down per channel. A plain ``np.convolve``
    on the channel grid point-samples at each channel's left edge and lands half
    a channel early, which the solver -- whose forward model integrates over the
    bin, as a TCSPC channel does -- then cannot fit: it costs ~0.5 in chi2r and
    pushes the residual into the timeshift.
    """
    t_fine = (np.arange(n * oversample) + 0.5) * (dt / oversample)
    lamp_fine = np.exp(-0.5 * ((t_fine - 1.0) / 0.12) ** 2)
    lamp = lamp_fine.reshape(n, oversample).mean(1)
    lamp /= lamp.sum()
    pure_fine = 0.6 * np.exp(-t_fine / 1.1) + 0.4 * np.exp(-t_fine / 3.6)
    conv = np.convolve(pure_fine, lamp_fine / lamp_fine.sum())[: n * oversample]
    conv = conv.reshape(n, oversample).mean(1)
    rng = np.random.default_rng(0)
    decay = rng.poisson(2.0e4 * conv / conv.max() + 5.0).astype(float)
    return decay, lamp * 1.0e4, dt, np.arange(n) * dt


@pytest.mark.parametrize("optimize_nuisance", [False, True])
def test_both_paths_return_the_keys_the_consumers_read(optimize_nuisance):
    """Whichever path runs, the result carries the design matrix and segment."""
    decay, lamp, dt, _ = _problem()
    result = solve_lifetime_mem(
        decay,
        lamp,
        dt,
        tau=np.linspace(0.4, 7.0, 60),
        fitrange=(30, decay.size - 1),
        optimize_nuisance=optimize_nuisance,
        max_iter=40,
    )
    missing = [key for key in REQUIRED if key not in result]
    assert not missing, f"result is missing {missing}"


def test_the_fitted_curve_can_be_rebuilt_from_the_result():
    """``Fi @ p * sigma`` is what every plot draws, so it has to be consistent.

    A result whose ``Fi`` came from different arguments than the solve would
    still have the right *shape* — this checks the numbers agree with the data
    the solver was given, which shape assertions cannot.
    """
    decay, lamp, dt, _ = _problem()
    result = solve_lifetime_mem(
        decay, lamp, dt,
        tau=np.linspace(0.4, 7.0, 60),
        fitrange=(30, decay.size - 1),
        optimize_nuisance=False,
        max_iter=200,
    )
    Fi = np.asarray(result["Fi"], dtype=float)
    p = np.asarray(result["p"], dtype=float).ravel()
    y = np.asarray(result["y"], dtype=float).ravel()
    sigma = np.asarray(result["sigma"], dtype=float).ravel()
    fit = (Fi @ p) * sigma
    fit_additive = np.asarray(result["fit_additive"], dtype=float).ravel()
    if fit_additive.size == fit.size:
        fit = fit + fit_additive

    assert fit.shape == y.shape
    chi2r = float(np.mean(((y - fit) / sigma) ** 2))
    # With the fixture discretised the way the forward model is, MEM reaches
    # chi2r ~ 1. The bound was 5.0 while the fixture was half a channel out --
    # loose enough to pass either way, which is how that went unnoticed.
    assert chi2r < 1.5, chi2r


def test_the_reported_background_is_the_one_that_was_used():
    """The fast path used to report the median instead of its own argument.

    The GUI writes this number straight back into the background field, so a
    wrong value silently becomes the next run's input.
    """
    decay, lamp, dt, _ = _problem()
    background = 7.5
    result = solve_lifetime_mem(
        decay, lamp, dt,
        tau=np.linspace(0.4, 7.0, 40),
        fitrange=(30, decay.size - 1),
        background=background,
        optimize_nuisance=False,
        max_iter=20,
    )
    assert result["background"] == pytest.approx(background)
