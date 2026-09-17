"""Starting values read off the measurement, instead of guessed.

A two-state MFD fit has six free numbers and a strongly multi-modal objective, so
where it starts decides where it ends. The generic defaults were about as bad as a
starting point can be:

* every state began at the **same** distance, which makes two states literally the
  same species -- identical patterns, identical Jacobian columns, a rank-deficient
  first step;
* ``alpha`` began at ``0.0``, which is *on its lower bound*, where a
  forward-difference gradient can only see one side;
* ``tauD0`` began at a generic 4 ns with no reference to the measured decay.

From there a real measurement converged to a crosstalk of 0.31 -- putting the
model's donor-only population at a proximity ratio of 0.24 while the data's sits
at 0.012 -- and stayed there, because nothing in the neighbourhood pointed
downhill.

Everything here is a *starting value*: each estimate is deliberately crude and
robust rather than precise, and the fit refines it. The point is only to start in
the right basin.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = ["StartingValues", "estimate_starting_values"]


@dataclass
class StartingValues:
    """Starting values estimated from a measurement.

    Attributes
    ----------
    alpha : float
        Spectral crosstalk, from where the donor-only population sits.
    tau_d0 : float
        Donor lifetime with no acceptor, ns.
    donor_only : float
        Fraction of bursts with no active acceptor.
    distances : list of float
        One mean donor-acceptor distance per state, Angstrom.
    populations : list of float
        Relative population of each state.
    diagnostics : dict
        What the estimate was read off, for a caller that wants to explain it.
    """

    alpha: float
    tau_d0: float
    donor_only: float
    distances: list[float]
    populations: list[float]
    diagnostics: dict


def _response_mean(response) -> float:
    """Return the mean arrival time of an instrument response, ns.

    Means add under convolution -- the identity the whole forward model rests on --
    so a measured mean micro time is the response's mean plus the decay's. That is
    what makes the donor lifetime readable off the donor-only population without
    fitting anything.
    """
    irf = np.asarray(response.irf, dtype=float)
    times = np.arange(irf.size, dtype=float) * float(response.dt)
    total = irf.sum()
    return float((times * irf).sum() / total) if total > 0 else 0.0


def _valley(counts: np.ndarray, start: int, stop: int) -> int:
    """Return the index of the emptiest bin between two peaks."""
    if stop <= start + 1:
        return int(start)
    return int(start + 1 + np.argmin(counts[start + 1 : stop]))


def _donor_only_split(ratio_marginal: np.ndarray) -> tuple[int, int]:
    """Return ``(donor-only mode, split index)`` of the proximity-ratio marginal.

    The donor-only population is the leftmost one: with no acceptor, a burst's red
    counts are crosstalk and background only. It is found as the mode of the lower
    part of the axis, and separated from the FRET population at the emptiest bin
    between the two modes -- a valley, not a fixed threshold, because where the
    populations meet depends on the sample.
    """
    n = ratio_marginal.size
    lower = max(1, n // 4)
    donor_mode = int(np.argmax(ratio_marginal[:lower]))
    upper = ratio_marginal.copy()
    # Everything up to and including the donor-only mode's own shoulder is off the
    # table when looking for the *other* population.
    upper[: donor_mode + 1] = 0.0
    fret_mode = int(np.argmax(upper))
    if fret_mode <= donor_mode:
        return donor_mode, min(n - 1, donor_mode + 1)
    return donor_mode, _valley(ratio_marginal, donor_mode, fret_mode)


def _distance_from_efficiency(efficiency: float, r0: float) -> float:
    """Return the distance giving a FRET efficiency, Angstrom."""
    e = float(np.clip(efficiency, 1e-3, 1.0 - 1e-3))
    return float(r0 * ((1.0 - e) / e) ** (1.0 / 6.0))


def estimate_starting_values(
    data,
    n_states: int = 2,
    r0: float = 52.0,
    gamma: float = 1.0,
) -> StartingValues:
    """Read starting values off an MFD measurement.

    Parameters
    ----------
    data : MfdData
        The measurement, from :func:`chisurf.core.fluorescence.mfd.fit.load_mfd_data`.
    n_states : int
        How many FRET states the model has.
    r0 : float
        Forster radius, Angstrom -- used to turn an efficiency into a distance.
    gamma : float
        Detection-efficiency ratio, used in the raw-to-efficiency conversion.

    Returns
    -------
    StartingValues

    Notes
    -----
    The estimates are crude by design:

    * **alpha** from the donor-only mode. A burst with no acceptor has
      ``PR = alpha / (1 + alpha)`` up to background, so ``alpha = PR / (1 - PR)``.
    * **tauD0** from the donor-only population's mean micro time minus the green
      response's mean -- means add under convolution.
    * **donorOnly** from the share of bursts left of the valley between the two
      populations.
    * **distances** from quantiles of the FRET population's proximity ratio, so two
      states start *apart*; equal distances would make them the same species.
    """
    counts = np.asarray(data.observed.counts, dtype=float)
    axes = data.axes
    ratio = 0.5 * (axes.ratio_edges[:-1] + axes.ratio_edges[1:])
    micro = 0.5 * (axes.micro_time_edges[:-1] + axes.micro_time_edges[1:])

    ratio_marginal = counts.sum(axis=1)
    total = ratio_marginal.sum()
    if total <= 0:
        raise ValueError("the observed histogram is empty")

    donor_mode, split = _donor_only_split(ratio_marginal)

    # --- crosstalk, from where the donor-only population sits ------------------
    pr_donor = float(ratio[donor_mode])
    alpha = float(np.clip(pr_donor / max(1.0 - pr_donor, 1e-6), 0.0, 0.5))
    # Never start exactly on a bound: a forward-difference gradient there sees one
    # side only, and the optimiser's first step is uninformed.
    alpha = max(alpha, 1e-3)

    # --- donor lifetime, from the donor-only population's mean micro time ------
    donor_block = counts[: split + 1, :].sum(axis=0)
    green = data.responses[data.channels[0]]
    offset = _response_mean(green)
    if donor_block.sum() > 0:
        mean_micro = float((micro * donor_block).sum() / donor_block.sum())
    else:
        mean_micro = offset
    tau_d0 = float(np.clip(mean_micro - offset, 0.05, 30.0))

    # --- how many have no acceptor at all --------------------------------------
    donor_only = float(np.clip(ratio_marginal[: split + 1].sum() / total, 0.01, 0.95))

    # --- the FRET states, spread over the population that is left ---------------
    fret = ratio_marginal.copy()
    fret[: split + 1] = 0.0
    distances: list[float] = []
    populations: list[float] = []
    if fret.sum() > 0:
        cumulative = np.cumsum(fret) / fret.sum()
        # One quantile per state, evenly spaced inside the population, so the
        # states start apart and in the order the editor lists them.
        quantiles = (np.arange(n_states) + 0.5) / n_states
        for q in quantiles:
            pr = float(ratio[int(np.searchsorted(cumulative, q))])
            # Raw ratio to efficiency, with the crosstalk taken back out. This
            # ignores direct excitation, which is a seed's privilege.
            efficiency = (pr - alpha * (1.0 - pr)) / max(
                pr + gamma * (1.0 - pr) - alpha * (1.0 - pr), 1e-6
            )
            distances.append(_distance_from_efficiency(efficiency, r0))
            populations.append(1.0 / n_states)
    else:
        distances = [r0 * (1.0 + 0.2 * (i - 0.5 * (n_states - 1))) for i in range(n_states)]
        populations = [1.0 / n_states] * n_states

    # Two states at the same distance are one state twice over: the patterns are
    # identical, the Jacobian columns are identical, and the optimiser starts
    # rank-deficient. Force them apart if the data did not.
    distances = sorted(distances)
    for i in range(1, len(distances)):
        if distances[i] - distances[i - 1] < 1.0:
            distances[i] = distances[i - 1] + 1.0

    return StartingValues(
        alpha=alpha,
        tau_d0=tau_d0,
        donor_only=donor_only,
        distances=[float(d) for d in distances],
        populations=[float(p) for p in populations],
        diagnostics={
            "donor_only_ratio": pr_donor,
            "split_ratio": float(ratio[split]),
            "response_mean_ns": offset,
            "donor_only_mean_micro_ns": mean_micro,
        },
    )
