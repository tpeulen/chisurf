"""Which 2D-MFD forward model recovers a known exchange rate, and what it costs.

The arbiter is neither implementation. Photons come from tttrlib's confocal
simulator — molecules diffusing through a focus, switching conformation on the
simulated clock — and go through the *same* burst tables, reader and response
estimation a measurement does. The exchange rate that generated them is known, so
each setting can be scored on what it gets back rather than on whether it agrees
with the other setting.

Settings compared (see the modules for what each means):

Both the accuracy and the time are reported, because a forward model that is
right and unaffordable has not won anything.

This measured four settings while there were four to measure: donor weighting by
green photons or by occupancy, the averaging window from the photons or from the
burst span, and the closed-form engine against a transcribed Sim2D Monte Carlo.
Three of those lost and have been removed from the tree; the outcome and the
numbers are in ``okf/references/mfd-forward-model-alternatives.md``. What remains
is a recovery benchmark for the one configuration that is left.

Two axes of the intended design are **not** covered yet, and a number from here
should not be read as if they were:

* bursts are always the truth-defined transits, never the searched ones, so this
  measures the model and not the burst search;
* the instrument response and background are always the pipeline's own estimates
  from non-burst photons, never the declared truth, so a bias in that estimation
  is charged to whichever setting is being scored.

Both are single arguments away — :meth:`SimulatedSmfret.searched_bursts` exists
and ``load_mfd_data`` takes ``responses=`` — but the cells have not been run.

Run::

    pixi run python test/benchmarks/benchmark_mfd_engines.py

and paste the table into ``docs/development/benchmarks.md``.
"""

from __future__ import annotations

import pathlib
import tempfile
import time

import numpy as np

#: Exchange rates to recover, in Hz. The middle of this range is where a rate is
#: identifiable at all: at both extremes a burst either never switches or has
#: already averaged, and every model is reduced to an order of magnitude.
RATES = (200.0, 1_000.0, 5_000.0)

#: Independent measurements per cell. Recovery scatter is the thing being
#: measured, so a single seed would report noise as a difference.
SEEDS = (11, 12, 13)

#: The simulated measurement. Brightness over background matters more than photon
#: count here: a flat background spread over the laser period drags every mean
#: micro time toward the middle of the window and dilutes the lifetime axis.
MEASUREMENT = dict(
    n_photons=300_000,
    alex=False,
    polarized=True,
    efficiencies=(0.2, 0.8),
    donor_only=0.05,
    acceptor_only=0.0,
    gamma=1.0,
    alpha=0.0,
    beta=1.0,
    delta=0.0,
    concentration=1.0,
    brightness=400.0,
    background=0.02,
    rho=1.0,
    irf_centre=1.0,
    irf_width=0.1,
)

#: Distances giving E = 0.2 and E = 0.8 at the optics below. Solved from
#: R = R0 (1/E - 1)^(1/6) rather than read off a plot: the earlier pair (66.2,
#: 39.3) gives 0.190 and 0.843, and a benchmark whose model sits at different
#: efficiencies than its data charges that mismatch to whichever setting is
#: being scored.
DISTANCES = tuple(52.0 * (1.0 / e - 1.0) ** (1.0 / 6.0) for e in (0.2, 0.8))

#: Linker width in the model. The simulator places both states at a fixed
#: efficiency, so a benchmark that gives the model a distance *distribution* the
#: data does not have lets the free rate absorb the difference. A real
#: measurement has one; a recovery test must not.
SIGMA = 0.5


def _model(rate):
    """Build the kinetic model at a given exchange rate."""
    from chisurf.core.fluorescence.mfd.fit import MfdKineticModel
    from chisurf.core.fluorescence.mfd.patterns import FretState, Optics

    optics = Optics(r0=52.0, tau_d0=4.0, sigma=SIGMA, gamma=1.0, alpha=0.0, delta=0.0)
    states = [FretState(distance=d, name=n) for d, n in zip(DISTANCES, ("low", "high"))]
    matrix = np.array([[0.0, rate / 2.0], [rate / 2.0, 0.0]])
    return MfdKineticModel(
        optics=optics,
        states=states,
        populations=[0.5, 0.5],
        donor_only=0.05,
        rate_matrix=matrix,
    )


def _measure(rate, seed, directory):
    """Simulate one measurement at *rate* and load it through the real pipeline."""
    from chisurf.core.fluorescence.burst.simulate import simulate_smfret
    from chisurf.core.fluorescence.mfd.fit import load_mfd_data

    matrix = np.array([[0.0, rate / 2.0], [rate / 2.0, 0.0]])
    sim = simulate_smfret(**MEASUREMENT, seed=seed, rate_matrix=matrix)
    folder = sim.write_folder(directory, bursts="truth", stem=f"r{int(rate)}s{seed}")
    return load_mfd_data(folder, min_green_photons=20, responses=None), sim


def fit_rate(data, *, start=800.0):
    """Recover the exchange rate, everything else pinned at truth.

    Rates only free: with the optics, distances and populations known, whatever
    the model gets wrong has nowhere to hide but the one free parameter. Fitting
    the distances too would let them absorb a lifetime-axis bias and report a rate
    that looks fine.

    Parameters
    ----------
    data : MfdData
        The measurement.
    start : float
        Starting rate (Hz). Deliberately not the truth, so the comparison sees
        basin-of-attraction differences rather than only curvature at the optimum.

    Returns
    -------
    rate, seconds : float
    """
    from scipy.optimize import minimize_scalar

    def objective(log_rate):
        model = _model(float(np.exp(log_rate)))
        return float(model.score(data, mask_empty_model=False).score)

    # A bounded scalar search rather than Levenberg-Marquardt, for both engines so
    # the comparison is not an optimiser artefact. The Monte-Carlo objective is
    # deterministic under common random numbers but *not smooth*: a small change in
    # the rate reshuffles which transitions a burst makes, so a finite-difference
    # gradient measures the reshuffle rather than the trend. Golden-section needs
    # no gradient and only assumes the objective is unimodal in the bracket.
    started = time.perf_counter()
    result = minimize_scalar(
        objective,
        bounds=(np.log(start / 40.0), np.log(start * 40.0)),
        method="bounded",
        options={"xatol": 2e-3},
    )
    return float(np.exp(result.x)), time.perf_counter() - started


def main():
    """Run the sweep and print the table."""
    rows = {}
    for rate in RATES:
        for seed in SEEDS:
            with tempfile.TemporaryDirectory() as tmp:
                data, _ = _measure(rate, seed, pathlib.Path(tmp) / "m")
                fitted, seconds = fit_rate(data)
                rows.setdefault(rate, []).append((fitted, seconds))

    print("\n| rate (Hz) | median fitted | bias | RMSE | s/fit |")
    print("|---|---|---|---|---|")
    for rate, values in rows.items():
        fitted = np.array([v[0] for v in values])
        seconds = np.array([v[1] for v in values])
        bias = float(np.median(fitted) / rate - 1.0)
        rmse = float(np.sqrt(np.mean((fitted / rate - 1.0) ** 2)))
        print(
            f"| {rate:g} | {np.median(fitted):.0f} | {bias:+.1%} | "
            f"{rmse:.1%} | {np.mean(seconds):.1f} |"
        )


if __name__ == "__main__":
    main()
