"""Stochastic reaction simulation (Gillespie SSA).

The public surface for stochastic reaction kinetics. The implementation lives in
:mod:`chisurf.core.math.reaction._reaction` — a pure-Python/Numba replacement
for the legacy Cython extension — and is re-exported here so this module keeps
the name the package documents.

There used to be a **second** ``Model`` in this file: the original NumPy
implementation, with the same attributes, the same constructor signature and the
same ``run``/``GSSA``/``getStats``/``CR`` API as the replacement, kept side by
side with it. Two Gillespie samplers that answer the same question differently
is not a fallback, it is a coin toss — nothing imported this one, and the demo
below already reached past it into ``_reaction``. Removed in favour of the one
implementation.

See Also
--------
chisurf.core.math.reaction.continuous : deterministic (ODE) reaction systems.
chisurf.core.fluorescence.kinetics : the Markov-state kinetics used by the
    dynamic fluorescence models — generator, equilibrium populations and
    occupation-time law over a rate matrix.
chisurf.core.fitting.kinetics : the same rate matrix as fitting parameters.
"""

from __future__ import annotations

import numpy as np

from chisurf.core.math.reaction._reaction import Model, l1, l2

__all__ = ["Model", "l1", "l2"]


def main():
    """Run a small SIR system through the stochastic SSA as a demo."""
    import time

    variables = ["s", "i", "r"]
    initial = np.array([500, 1, 0], dtype=int)
    rates = np.array([0.001, 0.1], dtype=float)
    transitions = np.array(
        [
            [-1, 0],
            [1, -1],
            [0, 1],
        ]
    )

    model = Model(
        vnames=variables,
        rates=rates,
        inits=initial,
        tmat=transitions,
        propensity=[l1, l2],
    )
    started = time.time()
    model.run(tmax=80, reps=1000)
    print("total time:", (time.time() - started))
