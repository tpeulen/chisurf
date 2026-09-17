"""Shared fixtures for the 2D-FLC validation suite.

The data-driven tests run on a photon stream **simulated here**, with the ground
truth of the reference data set that shipped with the original MATLAB code
(T. Kondo, Schlau-Cohen lab; ``simulated_data.mat``): one immobile molecule,
two fluorescence-lifetime species (tau = 1 and 3 ns), equal brightness
(10 kcps each), interconversion rate matrix ``[[0, 30], [10, 0]]`` s^-1
(relaxation 40 s^-1, 25 ms), equilibrium populations 0.25 / 0.75, 1 us macro
ticks and 4 ps TCSPC channels, convolved with the reference instrument response.

The reference file itself was 69 MB and lived in a disposable checkout, so the
suite silently skipped wherever it was absent. Only its IRF is committed
(``test/data/flc_2d/reference_irf.npz``, 14 KB); the stream is regenerated from
a fixed seed. Two details make the simulated stream measure what the recorded
one did, and both were found by running every test against both:

* **The IRF is sampled the way the MATLAB simulator sampled it.** The reference
  IRF is background-subtracted and dips below zero; ``TK_MyMain_Simu_PhotonStream``
  draws the IRF offset as ``1 + #{cumsum(IRF) <= u}``, which on a non-monotone
  cumulative sum is the distribution of the *sorted* cumulative sum. Clipping
  the negative samples instead shifts the mean micro time by ~0.2 ns.
* **Photons past the TCSPC window stay past it.** The MATLAB stream let late
  photons run beyond channel 3126 (3.5% of them); the plugin simulator clips
  them into its last channel. Clipped at 3127 channels that is a spike in the
  last real channel, which merges the two lifetime peaks and wrecks the species
  filters (cross-correlation -0.03 instead of -0.34 at 1 ms). Moving the clipped
  photons out of the window afterwards is worse: the channel is then empty, the
  filters weight the photons clipped onto it arbitrarily, and the cross term
  came out +1.4. So the stream is simulated on twice the window (3.5% land
  beyond channel 3126, as in the reference) and handed over unmodified.

Reference numbers recorded on ``simulated_data.mat`` (10 M photons) before the
switch, for comparison with the simulated 60 s stream (0.6 M photons, ~17 s to
simulate): 1D peaks
0.76 / 2.91 ns; species relaxation 35.9 s^-1; rate matrix k12 26.9, k21 9.0;
species cross-correlation -0.34 at 1 ms, 1.00 at 200 ms; 2D marginal fraction in
0.7-3.5 ns 0.74.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

#: parents[5] is the repo root: test/ -> flc_2d/ -> fcs/ -> plugins/ ->
#: chisurf/ -> repo.
_IRF_FIXTURE = (
    pathlib.Path(__file__).resolve().parents[5] / "test" / "data" / "flc_2d" / "reference_irf.npz"
)

GROUND_TRUTH = {
    "lifetimes_ns": (1.0, 3.0),
    "intensities_cps": (1.0e4, 1.0e4),
    "rate_matrix_per_s": ((0.0, 30.0), (10.0, 0.0)),
    "relaxation_rate_per_s": 40.0,
    "relaxation_time_s": 0.025,
    "eq_populations": (0.25, 0.75),
    "micro_time_resolution_ns": 0.004,
}

#: TCSPC channels of the reference window (12.5 ns at 4 ps).
N_MICROTIME_BINS = 3127
#: Length of the simulated measurement. 60 s is ~0.6 M photons, ~1500
#: relaxations; every assertion below holds on seeds 1, 2, 3 and 7.
TOTAL_TIME_S = 60.0
SEED = 7


def reference_irf() -> tuple[np.ndarray, np.ndarray]:
    """Return the reference IRF and its ns axis from the committed fixture."""
    # Not a skip: the fixture is committed, so its absence is a lost file.
    assert _IRF_FIXTURE.is_file(), f"committed fixture is missing: {_IRF_FIXTURE}"
    with np.load(_IRF_FIXTURE) as data:
        return np.asarray(data["irf"], float), np.asarray(data["irf_time_ns"], float)


def matlab_sampled_irf(irf: np.ndarray) -> np.ndarray:
    """IRF weights equivalent to the MATLAB simulator's cumulative-sum draw."""
    cdf = np.sort(np.cumsum(irf / irf.sum()))
    return np.clip(np.diff(np.concatenate([[0.0], cdf])), 0.0, None)


@pytest.fixture(scope="session")
def reference_photons():
    """A seeded two-state stream with the reference data set's ground truth."""
    from chisurf.plugins.fcs.flc_2d.simulate import simulate_photon_stream

    irf, irf_time_ns = reference_irf()
    stream = simulate_photon_stream(
        np.asarray(GROUND_TRUTH["rate_matrix_per_s"], float),
        GROUND_TRUTH["lifetimes_ns"],
        GROUND_TRUTH["intensities_cps"],
        total_time_s=TOTAL_TIME_S,
        irf=matlab_sampled_irf(irf),
        irf_time_ns=irf_time_ns,
        macro_time_resolution_s=1e-6,
        tstep_ns=GROUND_TRUTH["micro_time_resolution_ns"],
        n_microtime_channels=2 * N_MICROTIME_BINS,
        seed=SEED,
    )
    return {
        "macro_ticks": stream.macro_times,
        "micro_ticks": stream.micro_times,
        "states": stream.states,
        "macro_resolution_s": 1e-6,
        "micro_resolution_ns": GROUND_TRUTH["micro_time_resolution_ns"],
        "irf": irf,
        "irf_time_ns": irf_time_ns,
        "n_microtime_bins": N_MICROTIME_BINS,
    }
