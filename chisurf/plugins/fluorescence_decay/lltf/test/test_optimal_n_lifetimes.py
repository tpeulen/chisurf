"""Tests for the optimal-lifetime-count selection of the LLTF fitter (RF-878)."""

from __future__ import annotations

import random

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

from chisurf.plugins.fluorescence_decay.lltf.core import fitter as lltf_fitter
from chisurf.plugins.fluorescence_decay.lltf.core.convolve import (
    convolve_lifetime_spectrum,
)
from chisurf.plugins.fluorescence_decay.lltf.core.fitter import (
    Decay,
    select_number_of_lifetimes,
)


def _bi_exponential_decay(
    n_channels: int = 1024, channel_width: float = 0.032
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Build a synthetic bi-exponential decay with Poisson noise.

    Parameters
    ----------
    n_channels : int
        Number of channels of the decay and of the IRF.
    channel_width : float
        Time between two channels in nanoseconds.

    Returns
    -------
    tuple of numpy.ndarray
        The decay counts, the IRF and the time axis in nanoseconds.
    """
    time_axis = np.arange(n_channels) * channel_width
    channels = np.arange(n_channels, dtype=np.float64)
    irf = np.exp(-0.5 * ((channels - 60.0) / 4.0) ** 2)
    irf /= irf.sum()

    model = np.zeros(n_channels)
    convolve_lifetime_spectrum(model, np.array([0.6, 0.5, 0.4, 4.0]), irf, time_axis=time_axis)
    model = model / model.max() * 20000.0
    decay = np.random.default_rng(0).poisson(model).astype(np.float64)
    return decay, irf * 5000.0, time_axis


def test_lower_mode_keeps_the_last_significant_model():
    """A series that keeps improving must not fall through to a single lifetime."""
    # The scores measured on the plugin's shipped example for n = 1..4.
    scores = [7.97, 3.95, 12.88, 68.78]
    probs = [1.0, 1.0, 0.31, 0.0]
    assert select_number_of_lifetimes(scores, probs, 0.95, "lower") == 1

    # Every added component still helps significantly: the largest model wins,
    # including the last one tried.
    scores = [40.0, 12.0, 4.0, 1.1]
    probs = [1.0, 1.0, 1.0, 0.999]
    assert select_number_of_lifetimes(scores, probs, 0.95, "lower") == 3


def test_lower_mode_stops_at_the_first_insignificant_component():
    """Parsimony: an insignificant improvement ends the search where it is."""
    scores = [5.0, 4.9, 1.0]
    probs = [1.0, 0.4, 1.0]
    assert select_number_of_lifetimes(scores, probs, 0.95, "lower") == 0


def test_upper_mode_returns_the_largest_significant_model():
    """'upper' searches downwards and accepts the largest supported model."""
    scores = [7.97, 3.95, 12.88, 3.90]
    probs = [1.0, 1.0, 0.31, 0.99]
    assert select_number_of_lifetimes(scores, probs, 0.95, "upper") == 3

    scores = [7.97, 3.95, 12.88, 68.78]
    probs = [1.0, 1.0, 0.31, 0.0]
    assert select_number_of_lifetimes(scores, probs, 0.95, "upper") == 1


@pytest.mark.parametrize("selection_mode", ["lower", "upper"])
def test_scan_recovers_two_lifetimes(monkeypatch, selection_mode):
    """The scan over a bi-exponential decay must return two lifetimes."""
    monkeypatch.setattr(lltf_fitter.plt, "show", lambda *args, **kwargs: None)

    decay_counts, irf, time_axis = _bi_exponential_decay()
    decay = Decay(decay=decay_counts, irf=irf, time_axis=time_axis)
    decay.set_analysis_range(20, 900)

    random.seed(0)
    result = decay.find_optimal_lifetime_spectrum(
        maximum_number_of_lifetimes=3,
        plot_probabilities=False,
        plot_weighted_residuals=False,
        save_intermediate_results=False,
        min_lifetime=0.2,
        max_lifetime=6.0,
        selection_mode=selection_mode,
    )
    lltf_fitter.plt.close("all")

    scores = result["scores"]
    assert scores[1] < scores[0], "the two-lifetime fit must beat the mono-exponential one"
    assert result["best_number_of_lifetimes"] == 2
    assert result["best_idx"] == 1
