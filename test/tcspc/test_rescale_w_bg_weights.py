"""Pin the weighting convention of :func:`rescale_w_bg` (RF-610).

The autoscale kernel used to invert the weights it was handed
(``iwsq = 1 / (w * w + 1e-12)``), while its only caller passes ``w = 1 / ey``
-- the inverse errors fixed by :meth:`chisurf.core.data.DataCurve.set_weights`.
Each channel therefore entered the least-squares sums with its *variance*
instead of its inverse variance, so the scale ``n0`` that autoscale wrote back
did not minimise chi2. At the optimum the two agree, but away from it (i.e. on
every fit iteration) the reported chi2 was tens of percent above the value the
same model reaches at its own optimal scale, distorting the surface the
optimizer walks on.

The tests below pin the scale to the closed-form inverse-variance solution and,
independently, to stationarity of chi2 -- either alone would catch a return to
the inverted weighting.
"""

import numpy as np
import pytest

from chisurf.core.fluorescence.tcspc.tcspc import rescale_w_bg
from chisurf.plugins.fluorescence_decay.lltf.core.scaling import (
    rescale_w_bg as rescale_w_bg_lltf,
)

BACKGROUND = 5.0
N_CHANNELS = 512


def _decay(tau: float, n_channels: int = N_CHANNELS) -> np.ndarray:
    """Build a normalized single-exponential decay.

    Parameters
    ----------
    tau : float
        Fluorescence lifetime in nanoseconds.
    n_channels : int
        Number of TCSPC channels.

    Returns
    -------
    numpy-array
        The decay, scaled to a maximum of one.
    """
    t = np.arange(n_channels) * 0.032
    y = np.exp(-t / tau)
    return y / y.max()


def _noisy_data(tau: float = 3.5, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Draw a Poisson TCSPC decay and its counting weights.

    Parameters
    ----------
    tau : float
        Lifetime of the decay that is sampled.
    seed : int
        Seed of the random number generator.

    Returns
    -------
    tuple
        The counts and the weights ``w = 1 / ey``.
    """
    rng = np.random.default_rng(seed)
    y = rng.poisson(_decay(tau) * 20000.0 + BACKGROUND).astype(np.float64)
    ey = np.sqrt(np.maximum(y, 1.0))
    return y, 1.0 / ey


def _chi2(y: np.ndarray, model: np.ndarray, ey: np.ndarray, scale: float) -> float:
    """Compute the weighted sum of squared residuals for a given scale.

    Parameters
    ----------
    y : numpy-array
        Experimental counts.
    model : numpy-array
        Unscaled model decay.
    ey : numpy-array
        Errors of the experimental counts.
    scale : float
        Scaling factor applied to `model`.

    Returns
    -------
    float
        The weighted sum of squared residuals.
    """
    return float(np.sum(((y - (scale * model + BACKGROUND)) / ey) ** 2))


@pytest.mark.parametrize("tau_model", [3.5, 3.8, 4.2])
def test_scale_is_the_inverse_variance_solution(tau_model: float):
    """The kernel must weight each channel by ``w**2 = 1 / sigma**2``."""
    y, w = _noisy_data()
    m = _decay(tau_model)

    scale = rescale_w_bg(m, y, w, BACKGROUND, 0, N_CHANNELS)

    sel = y > 0.0
    expected = np.sum(m[sel] * (y[sel] - BACKGROUND) * w[sel] ** 2) / np.sum(
        m[sel] * m[sel] * w[sel] ** 2
    )
    assert scale == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize("tau_model", [3.5, 3.8, 4.2])
def test_scale_minimizes_chi2_away_from_the_optimum(tau_model: float):
    """chi2 is stationary in the returned scale, not only for a perfect model."""
    y, w = _noisy_data()
    ey = 1.0 / w
    m = _decay(tau_model)

    scale = rescale_w_bg(m, y, w, BACKGROUND, 0, N_CHANNELS)

    chi2 = _chi2(y, m, ey, scale)
    for factor in (0.99, 1.01):
        assert _chi2(y, m, ey, scale * factor) > chi2


def test_zero_error_channels_are_skipped():
    """An infinite weight (``ey == 0``) must not poison the sums."""
    y, w = _noisy_data()
    m = _decay(3.8)
    reference = rescale_w_bg(m, y, w, BACKGROUND, 0, N_CHANNELS)

    w_inf = w.copy()
    w_inf[N_CHANNELS // 2] = np.inf
    scale = rescale_w_bg(m, y, w_inf, BACKGROUND, 0, N_CHANNELS)

    assert np.isfinite(scale)
    assert scale == pytest.approx(reference, rel=1e-3)


def test_lltf_kernel_is_the_same_kernel():
    """The lifetime tool uses the shared kernel, not a copy of it.

    It used to be a copy, and the copy indexed its weights as ``w[i - start]``
    -- a *pre-sliced* array -- while this one indexes ``w[i]`` like every other
    array it is handed. The two therefore agreed only at ``start == 0``, which
    is the only way this test used to call them, so a genuine divergence in
    convention sat behind a passing assertion.

    Hence the offset window below: it is the case that can tell the two apart,
    and it is the reason to check identity rather than equality now.
    """
    assert rescale_w_bg_lltf is rescale_w_bg

    y, w = _noisy_data()
    m = _decay(3.8)
    start, stop = 64, N_CHANNELS - 32

    scale = rescale_w_bg_lltf(m, y, w, BACKGROUND, start, stop)
    assert scale == pytest.approx(
        rescale_w_bg(m, y, w, BACKGROUND, start, stop), rel=1e-12
    )

    # And the offset window is not a no-op: it must disagree with a call that
    # ignores it, or the test above would pass for the wrong reason.
    assert scale != pytest.approx(
        rescale_w_bg(m, y, w, BACKGROUND, 0, N_CHANNELS), rel=1e-9
    )
