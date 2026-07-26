"""A transition-rate matrix whose entries are ordinary fitting parameters.

Shared by the two-colour N-state PDA model
(:class:`~chisurf.core.models.pda.dynamic_mc.PdaDynamicNStates`) and the
three-colour one (:class:`~chisurf.core.models.pda3c.tcpda.TcPdaKinetics`),
because a kinetic scheme is the same object in both: an ``n x n`` matrix of
rates ``k_ij`` (state *i* to state *j*, in Hz) with a zero diagonal.

Why the rates live in a list
----------------------------
:func:`chisurf.core.base.find_objects` — which is how ``find_parameters``
discovers what the optimiser may touch — recurses into **lists only**. Rates
kept in a dict or a tuple are invisible to it: they never appear in
``parameters_all``, so freeing one does nothing and the fit sits still while
reporting success. That is not hypothetical; the three-state model shipped that
way. Anything holding fitting parameters here therefore holds them in a list,
and :meth:`RateMatrixMixin.rate_items` reconstructs the ``(i, j)`` labels from
the position rather than storing them alongside.

Nothing about the scheme is baked in
------------------------------------
Every off-diagonal entry is a parameter, so the *topology* is data rather than
code: a linear chain is the fully connected scheme with the long-range rates
fixed at zero, detailed balance is a link between two parameters, and a
one-way cycle is a set of zeros. There is no separate notion of "which scheme"
for the model to get out of step with.
"""

from __future__ import annotations

import numpy as np

from chisurf.core.fitting.parameter import FittingParameter

#: Rate a freshly created scheme starts every transition at, in Hz.
DEFAULT_RATE = 100.0


class RateMatrixMixin:
    """Off-diagonal rate parameters of an ``n``-state scheme.

    Expects the host to be a
    :class:`~chisurf.core.fitting.parameter.FittingParameterGroup` and to keep
    two attributes this mixin owns: ``_rates`` (a list of
    :class:`~chisurf.core.fitting.parameter.FittingParameter`, row-major over
    ``(i, j), i != j`` with 1-based labels) and ``_n_states``.

    The host decides *when* the scheme is resized — the two-colour model from a
    spin box, the three-colour one from its species count — and calls
    :meth:`_rebuild_rates` to do it.
    """

    #: Prefix of the generated parameter names, ``<prefix><i>_<j>``.
    rate_prefix = "k"

    #: Value a transition starts at when the scheme first grows to include it.
    #: Zero means "no kinetics until asked for", which is how a model whose
    #: dynamics are optional keeps the static route as its default.
    default_rate = DEFAULT_RATE

    def _rebuild_rates(self, n_states: int) -> None:
        """Resize the scheme to ``n_states``, keeping the rates that survive.

        Parameters
        ----------
        n_states : int
            Number of states; at least two.

        Notes
        -----
        Values are carried over by their ``(i, j)`` label, not by position, so
        growing a scheme leaves the existing rates where they were and only the
        new transitions start at :attr:`default_rate`. Shrinking drops the
        vanished state's row and column. Whether a rate is fixed survives a
        resize too, so a scheme built by zeroing the transitions it does not
        have is not silently reconnected by adding a state.
        """
        target = max(2, int(n_states))
        old = {(i, j): p.value for (i, j), p in self.rate_items()}
        old_fixed = {(i, j): p.fixed for (i, j), p in self.rate_items()}
        rates = []
        for i in range(1, target + 1):
            for j in range(1, target + 1):
                if i == j:
                    continue
                rates.append(FittingParameter(
                    value=float(old.get((i, j), self.default_rate)),
                    name=f"{self.rate_prefix}{i}_{j}",
                    lb=0.0, ub=1e9, bounds_on=True,
                    fixed=old_fixed.get((i, j), True),
                    label_text=f"{self.rate_prefix}<sub>{i}{j}</sub>"))
        self._rates = rates
        self._n_states = target

    # -- access -------------------------------------------------------------

    def rate_items(self) -> list:
        """Return ``((i, j), parameter)`` for every off-diagonal rate, 1-based."""
        n = getattr(self, "_n_states", 0)
        pairs = [(i, j)
                 for i in range(1, n + 1)
                 for j in range(1, n + 1) if i != j]
        return list(zip(pairs, getattr(self, "_rates", [])))

    def rates_by_name(self) -> dict:
        """Return ``{"k<i>_<j>": parameter}`` for every off-diagonal rate.

        The handle for scripting a scheme: free the rates it has, fix the ones
        it does not, and link a pair to impose detailed balance::

            rates = model.states.rates_by_name()
            rates["k1_3"].value = 0.0        # no direct 1 <-> 3
            rates["k3_1"].value = 0.0
            rates["k1_2"].fixed = False      # fit the rest
        """
        return {p.name: p for p in getattr(self, "_rates", [])}

    def rate_matrix(self) -> np.ndarray:
        """Return the ``n x n`` rate matrix ``K[target, source]`` (Hz)."""
        n = getattr(self, "_n_states", 0)
        K = np.zeros((n, n), dtype=float)
        for (i, j), p in self.rate_items():
            # k_ij is the rate i -> j, so target = j, source = i (0-based).
            K[j - 1, i - 1] = max(0.0, float(p.value))
        return K

    def set_rate_matrix(self, matrix) -> None:
        """Write an ``n x n`` ``K[target, source]`` matrix onto the parameters.

        Parameters
        ----------
        matrix : array_like or None
            Rates in Hz. ``None`` zeroes the scheme, which is how a model says
            "no kinetics" without the matrix having to be absent. Resizes the
            scheme when the matrix is a different size.
        """
        if matrix is None:
            for p in getattr(self, "_rates", []):
                p.value = 0.0
            return
        K = np.asarray(matrix, dtype=float)
        if K.ndim != 2 or K.shape[0] != K.shape[1]:
            raise ValueError(f"rate matrix must be square, got {K.shape}")
        if K.shape[0] != getattr(self, "_n_states", 0):
            self._rebuild_rates(K.shape[0])
        for (i, j), p in self.rate_items():
            p.value = max(0.0, float(K[j - 1, i - 1]))

    @property
    def rate_values(self) -> list:
        """Return the flat row-major ``n*n`` rates, diagonal zeroed.

        The view the editable rate-matrix grid binds to; the entries are the
        fitting parameters themselves, so editing the grid moves the parameters
        and their fixed/free state is still controlled from the table.
        """
        n = getattr(self, "_n_states", 0)
        flat = [0.0] * (n * n)
        for (i, j), p in self.rate_items():
            flat[(i - 1) * n + (j - 1)] = float(p.value)
        return flat

    @rate_values.setter
    def rate_values(self, values) -> None:
        """Write a flat row-major ``n*n`` grid back onto the rate parameters."""
        n = getattr(self, "_n_states", 0)
        flat = list(values)
        if len(flat) != n * n:
            return
        for (i, j), p in self.rate_items():
            p.value = max(0.0, float(flat[(i - 1) * n + (j - 1)]))

    @property
    def state_names(self) -> list:
        """Row/column labels for the rate-matrix grid."""
        return [str(i) for i in range(1, getattr(self, "_n_states", 0) + 1)]

    def transitions_per_window(self, window: float) -> float:
        """Return the largest expected number of transitions in ``window``."""
        return transitions_per_window(self.rate_matrix(), window)


def transitions_per_window(rate_matrix, window: float) -> float:
    """Return the largest expected number of transitions in ``window``.

    Taken from the generator's diagonal — the escape rate out of each state —
    rather than from the raw matrix. Summing ``|K|`` down a column double-counts
    when the caller passes a matrix that already carries its generator diagonal,
    so one physical system would measure two different exchange speeds depending
    on how it was spelled, and could take different code paths for it.

    Parameters
    ----------
    rate_matrix : array_like
        ``(n, n)`` with ``K[target, source]`` in Hz; the diagonal is ignored,
        as everywhere else the matrix is consumed.
    window : float
        Observation time in seconds.

    Returns
    -------
    float
    """
    from chisurf.core.fluorescence.kinetics import generator_from_rate_matrix

    generator = generator_from_rate_matrix(rate_matrix)
    return float(np.max(-np.diag(generator))) * float(window)
