"""Simulated smFRET bursts with exchange on three timescales, fitted back.

Exchange between two conformations is only visible in an MFD histogram when it is
*comparable to how long a molecule spends in the focus*. Much slower and you see two
static populations; much faster and you see one averaged population. In between,
bursts caught mid-exchange fill the space between the states and pull the cloud off
the static FRET line — and that displacement is the entire signal.

This example simulates the same molecule in all three regimes, writes each one as a
real burst-analysis folder, loads it back through the ordinary reader, and fits the
exchange rate. Run it with::

    python examples/mfd_dynamics_timescales.py

A word on what this proves. The simulator and the model share the physics being
asserted, so this is a **code test, never a physics test** — it shows the
implementation computes what it claims to, not that the claim describes a molecule.
It is still worth running, because the two reach the same numbers by different
routes: the simulator samples an explicit Markov path per burst and draws each
photon's micro time as an instrument-response sample plus an exponential delay,
where the model evaluates the occupation-time law and the wrapped moments in closed
form.
"""

import pathlib
import tempfile

import numpy as np
from scipy.optimize import least_squares

from chisurf.core.fluorescence.mfd.fit import MfdKineticModel, load_mfd_data
from chisurf.core.fluorescence.mfd.histogram import HistogramAxes
from chisurf.core.fluorescence.burst.simulate import (
    rate_matrix_for,
    simulate_smfret,
)

# Two conformations, 40 Å and 70 Å apart, seen through an ordinary confocal setup.
MEAN_DURATION = 2.0e-3  # seconds a molecule spends in the focus
AXES = HistogramAxes.default(n_ratio=40, n_micro_time=40, micro_time_range=(0.5, 6.0))


#: The declared measurement, shared by the simulation and the model below so the
#: example fits the rate against the molecule it actually made.
EFFICIENCIES = (0.786, 0.152)
DONOR_ONLY = 0.15
OPTICS = dict(r0=52.0, tau_d0=4.0, tau_a=3.0, sigma=6.0, alpha=0.02,
              delta=0.0, gamma=1.0)


def truth_model():
    """Return the optics and states the simulated measurement declares."""
    from chisurf.core.fluorescence.fret.lines import distance_for_efficiency
    from chisurf.core.fluorescence.mfd.patterns import FretState, Optics

    optics = Optics(**OPTICS)
    states = [
        FretState(distance=float(distance_for_efficiency(
            e, donor=OPTICS["tau_d0"], r0=OPTICS["r0"], sigma=OPTICS["sigma"])))
        for e in EFFICIENCIES
    ]
    return optics, states


def fit_exchange_rate(data, start=400.0):
    """Fit the single exchange rate of a symmetric two-state scheme.

    Everything except the rate is treated as known, so the example is about the
    *rate* and nothing else can absorb the error.

    Parameters
    ----------
    data : chisurf.core.fluorescence.mfd.fit.MfdData
        The loaded measurement.
    start : float
        Starting rate, per second.

    Returns
    -------
    float
        The fitted total exchange rate, per second.
    """

    def residuals(values):
        rate = float(np.exp(values[0]))
        optics, states = truth_model()
        model = MfdKineticModel(
            optics=optics,
            states=states,
            populations=[0.5, 0.5],
            donor_only=DONOR_ONLY,
            rate_matrix=np.array([[0.0, rate / 2.0], [rate / 2.0, 0.0]]),
        )
        # Score every bin, so the residual vector keeps a fixed length as the rate
        # moves — masking empty-model bins makes it change, and least_squares
        # cannot difference a vector whose length moves.
        return model.score(data, mask_empty_model=False).residuals

    result = least_squares(residuals, [np.log(start)], diff_step=0.05, xtol=1e-8)
    return float(np.exp(result.x[0]))


def main():
    """Simulate, write, load and fit each regime, then report."""
    workspace = pathlib.Path(tempfile.mkdtemp(prefix="mfd-timescales-"))
    print(f"writing simulated burst folders under {workspace}\n")

    centres = 0.5 * (AXES.ratio_edges[:-1] + AXES.ratio_edges[1:])
    between = (centres > 0.30) & (centres < 0.60)

    header = f"{'regime':<14}{'true rate':>12}{'fitted':>12}{'in the gap':>13}"
    print(header)
    print("-" * len(header))

    for regime, start in (
        ("static", 400.0),
        ("slow", 400.0),
        ("intermediate", 400.0),
        ("fast", 5000.0),
    ):
        simulated = simulate_smfret(
            alex=False, polarized=True,
            efficiencies=EFFICIENCIES, donor_only=DONOR_ONLY, acceptor_only=0.0,
            gamma=OPTICS["gamma"], alpha=OPTICS["alpha"], beta=1.0,
            delta=OPTICS["delta"], tau_d0=OPTICS["tau_d0"], tau_a=OPTICS["tau_a"],
            linker_sigma=OPTICS["sigma"], r0=OPTICS["r0"],
            concentration=1.0, brightness=400.0, background=0.02,
            laser_period=13.6, irf_centre=1.2, irf_width=0.09,
            n_photons=360_000, seed=17,
            rate_matrix=rate_matrix_for(regime, mean_duration=MEAN_DURATION),
        )
        folder = simulated.write_folder(workspace / regime, stem=regime)

        # The declared instrument response is used rather than the one estimated
        # from the non-burst photons. Both work, but the estimate is contaminated
        # by bursts below the search threshold — see the concept page — and this
        # example is about the exchange rate, not about that.
        data = load_mfd_data(
            folder,
            axes=AXES,
            min_green_photons=20,
            responses=simulated.true_responses(),
            n_signal_bins=16,
            n_span_bins=4,
        )

        marginal = data.observed.counts.sum(axis=1)
        marginal = marginal / marginal.sum()
        gap = float(marginal[between].sum())

        rates = rate_matrix_for(regime, mean_duration=MEAN_DURATION)
        truth = 0.0 if rates is None else float(np.asarray(rates).sum())
        fitted = fit_exchange_rate(data, start=start)
        print(
            f"{regime:<14}{truth:>10.0f} /s{fitted:>10.0f} /s{gap:>12.1%}"
        )

    print(
        "\n'in the gap' is the fraction of bursts landing between the two states."
        "\nIt is the signal: slow exchange leaves it empty, fast exchange puts"
        "\neverything there, and only in between does it tell you a rate."
        "\n\nThe rate is accurate near one transition per burst and only an order of"
        "\nmagnitude elsewhere — far below it almost no burst ever switches, and far"
        "\nabove it every burst reports the same average. That is the physics, not a"
        "\nshortcoming of the fit."
    )


if __name__ == "__main__":
    main()
