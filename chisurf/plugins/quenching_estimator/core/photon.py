"""Photon-trace and decay-curve kernels — IMP.bff's C++ (``simulate_photon_trace``, ``simulate_quenched_decay``).

The kernels moved upstream into IMP.bff's C++: they are general fluorescence machinery, not
application logic, and QuEst had the only copy. What is left here is the QuEst
spelling, so call sites read unchanged.

**Two numbers moved with the fixes upstream**, and both were bugs here:

* ``simulate_decay_quench`` raced. It accumulated into ``decay[bin_idx]`` from
  inside a ``prange`` with a data-dependent index, which numba cannot privatise
  into a reduction — on 8 threads it lost up to **2% of the emitted intensity**,
  at random, and worse the more curves were averaged.
* ``simulate_photon_trace_rate`` sampled waiting times as
  ``log(1 / (u + EPS)) * tau0``, which goes **negative** once ``u > 1 - EPS`` —
  2.4e-4 of all photons, emitted before they were excited, then silently dropped
  by any histogram starting at zero.

Imports are lazy: ``import quest.core`` must not pull ``IMP`` in
(okf/references/known-issues.md).
"""

from __future__ import annotations

from typing import Tuple

import numpy as np

from .av import cxx_seed

__all__ = ["simulate_photon_trace_rate", "simulate_decay_quench"]


def simulate_photon_trace_rate(
    n_ph: int,
    kQ: np.ndarray,
    t_step: float = 0.01,
    tau0: float = 0.25,
    random_seed: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Monte-Carlo photon trace against a per-frame quenching rate.

    Delegates to :func:`IMP.bff.simulate_photon_trace`. Passing ``random_seed``
    makes the trace reproducible, at the cost of running single-threaded.
    """
    from IMP.bff import simulate_photon_trace

    delays, emitted = simulate_photon_trace(
        int(n_ph),
        np.ascontiguousarray(kQ, dtype=np.float64).ravel(),
        float(t_step),
        float(tau0),
        cxx_seed(random_seed),
    )
    return np.asarray(delays), np.asarray(emitted)


def simulate_decay_quench(
    n_curves: int,
    decay: np.ndarray,
    dt_tac: float,
    k_quench: np.ndarray,
    t_step: float,
    tau0: float,
    random_seed: int | None = None,
) -> None:
    """Fill *decay* in place with a trajectory-driven fluorescence decay curve.

    Delegates to :func:`IMP.bff.simulate_quenched_decay`.

    :param n_curves: number of virtual decay curves to average over.
    :param decay: 1-D array filled in place.
    :param dt_tac: TAC bin width in ns.
    :param k_quench: quenching rate in 1/ns per trajectory frame.
    :param t_step: time step of the diffusion simulation in ns.
    :param tau0: intrinsic excited-state lifetime in ns.
    """
    from IMP.bff import simulate_quenched_decay

    simulate_quenched_decay(
        int(n_curves),
        decay,
        float(dt_tac),
        np.ascontiguousarray(k_quench, dtype=np.float64).ravel(),
        float(t_step),
        float(tau0),
        cxx_seed(random_seed),
    )
