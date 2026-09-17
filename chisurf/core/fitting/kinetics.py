"""A kinetic scheme whose transition rates are ordinary fitting parameters.

A rate scheme is not a property of any one experiment: dynamic PDA, three-colour
PDA, the photon-by-photon burst likelihood, lifetime-FCS and the acquisition
simulator all describe the same object — an ``n x n`` matrix of rates
:math:`k_{ij}` (state *i* to state *j*, in Hz) with a zero diagonal. This module
is the *fitting* layer over it: the rates as
:class:`~chisurf.core.fitting.parameter.FittingParameter` objects, so a model
can **recover** a scheme instead of only being told one.

The arithmetic lives one level down in
:mod:`chisurf.core.fluorescence.kinetics` — the generator, the equilibrium
populations, the occupation-time law, and the single flat-rate convention
(:func:`~chisurf.core.fluorescence.kinetics.rate_matrix_from_rates`) that this
module and the burst likelihood both order their rates by. There is deliberately
one convention and one implementation of it; a rate vector means the same thing
wherever it is handed over.

Nothing about the scheme is baked in
------------------------------------
Every off-diagonal entry is a parameter, so the *topology* is data rather than
code: a linear chain is the fully connected scheme with the long-range rates
fixed at zero, detailed balance is a link between two parameters, and a one-way
cycle is a set of zeros. There is no separate notion of "which scheme" for a
model to get out of step with, and no scheme a model cannot express.

Why the rates live in a list
----------------------------
:func:`chisurf.core.base.find_objects` — which is how ``find_parameters``
discovers what the optimiser may touch — recurses into **lists only**. Rates
kept in a dict or a tuple are invisible to it: they never appear in
``parameters_all``, so freeing one does nothing and the fit sits still while
reporting success. That is not hypothetical; the three-state PDA model shipped
that way. Anything holding fitting parameters here therefore holds them in a
list, and :meth:`RateMatrixMixin.rate_items` reconstructs the ``(i, j)`` labels
from the position rather than storing them alongside.

Usage
-----
Own a :class:`RateMatrixParameters` and bind the editable grid to it::

    self.kinetics = RateMatrixParameters(name="kinetics", n_states=3)

    rates = self.kinetics.rates_by_name()
    rates["k1_3"].value = 0.0        # a linear chain 1-2-3
    rates["k3_1"].value = 0.0
    rates["k1_2"].fixed = False      # fit the rest

Mix :class:`RateMatrixMixin` into an existing group instead when the states
carry other fitted quantities too (distances, efficiencies, brightnesses), so
they stay in one group with their rates — that is what the PDA models do.
"""

from __future__ import annotations

import logging

import numpy as np

from chisurf.core.fitting.parameter import FittingParameter, FittingParameterGroup
from chisurf.core.fluorescence.kinetics import (
    rate_matrix_from_rates,
    rates_from_rate_matrix,
    transitions_per_window,
)

__all__ = [
    "DEFAULT_RATE",
    "RateMatrixMixin",
    "RateMatrixParameters",
]

logger = logging.getLogger(__name__)

#: Rate a freshly created scheme starts every transition at, in Hz.
DEFAULT_RATE = 100.0


class RateMatrixMixin:
    """Off-diagonal rate parameters of an ``n``-state scheme.

    Expects the host to be a
    :class:`~chisurf.core.fitting.parameter.FittingParameterGroup` and to keep
    two attributes this mixin owns: ``_rates`` (a list of
    :class:`~chisurf.core.fitting.parameter.FittingParameter`, ordered by
    :func:`~chisurf.core.fluorescence.kinetics.rate_matrix_from_rates`) and
    ``_n_states``.

    The host decides *when* the scheme is resized — from a spin box, from a
    species count, from a loaded file — and calls :meth:`_rebuild_rates` to do
    it. Use :class:`RateMatrixParameters` when the scheme is all the group
    holds.
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
        for i, j in self._rate_pairs(target):
            rates.append(
                FittingParameter(
                    value=float(old.get((i, j), self.default_rate)),
                    name=f"{self.rate_prefix}{i}_{j}",
                    lb=0.0,
                    ub=1e9,
                    bounds_on=True,
                    fixed=old_fixed.get((i, j), True),
                    label_text=f"{self.rate_prefix}<sub>{i}{j}</sub>",
                )
            )
        self._rates = rates
        self._n_states = target
        self._invalidate_parameters()

    def _invalidate_parameters(self) -> None:
        """Forget the discovered parameter list after the scheme changed.

        ``find_parameters`` snapshots the rate objects into ``_parameters``, and
        a resize replaces every one of them. Left alone, the group would keep
        reporting the *old* rates: an optimiser handed them would move
        parameters that no longer belong to the scheme, and the rates that do
        would sit untouched while the fit reported success.

        ``None`` is what
        :attr:`~chisurf.core.fitting.parameter.FittingParameterGroup.parameters_all`
        reads as "never walked", so the next read rediscovers.
        """
        self._parameters = None
        try:
            from chisurf.core.fitting import factorgraph

            factorgraph.bump_structure_version()
        except Exception:  # pragma: no cover - the graph is optional here
            logger.debug("could not bump the structure version", exc_info=True)

    @staticmethod
    def _rate_pairs(n_states: int) -> list:
        """Return the ``(source, target)`` labels, 1-based, in the flat order.

        The order of
        :func:`~chisurf.core.fluorescence.kinetics.rate_matrix_from_rates`, so
        the parameter list and any flat rate vector line up element for element.
        """
        return [(i, j) for i in range(1, n_states + 1) for j in range(1, n_states + 1) if i != j]

    # -- access -------------------------------------------------------------

    def rate_items(self) -> list:
        """Return ``((i, j), parameter)`` for every off-diagonal rate, 1-based."""
        return list(
            zip(self._rate_pairs(getattr(self, "_n_states", 0)), getattr(self, "_rates", []))
        )

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

    @property
    def flat_rates(self) -> np.ndarray:
        """The ``n(n-1)`` off-diagonal rates, in the shared flat order."""
        return np.array(
            [max(0.0, float(p.value)) for p in getattr(self, "_rates", [])], dtype=float
        )

    def rate_matrix(self) -> np.ndarray:
        """Return the ``n x n`` rate matrix ``K[target, source]`` (Hz)."""
        return rate_matrix_from_rates(self.flat_rates, getattr(self, "_n_states", 0))

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
        for p, value in zip(self._rates, rates_from_rate_matrix(K)):
            p.value = max(0.0, float(value))

    @property
    def rate_values(self) -> list:
        """Return the flat row-major ``n*n`` rates, diagonal zeroed.

        The view the editable rate-matrix grid binds to — a *full* ``n x n``
        row-major read, not the off-diagonal-only flat order of
        :attr:`flat_rates`. Row ``i``, column ``j`` is ``k_ij``, the rate from
        state ``i`` to state ``j``, so entry ``i*n + j``.

        It is the only such view. A second property, ``matrix``, returned the
        same numbers untransposed (``K[target, source]``); the one grid widget
        cannot be right for both, and flipping it to suit one made the other
        show every rate mirrored. The entries are the fitting parameters themselves,
        so editing the grid moves the parameters and their fixed/free state is
        still controlled from the table.
        """
        return [float(v) for v in self.rate_matrix().T.ravel()]

    @rate_values.setter
    def rate_values(self, values) -> None:
        """Write a flat row-major ``n*n`` grid back onto the rate parameters."""
        n = getattr(self, "_n_states", 0)
        flat = list(values)
        if len(flat) != n * n:
            return
        self.set_rate_matrix(np.asarray(flat, dtype=float).reshape(n, n).T)

    @property
    def state_names(self) -> list:
        """Row/column labels for the rate-matrix grid."""
        return [str(i) for i in range(1, getattr(self, "_n_states", 0) + 1)]

    def transitions_per_window(self, window: float) -> float:
        """Return the largest expected number of transitions in ``window``."""
        return transitions_per_window(self.rate_matrix(), window)


class RateMatrixParameters(RateMatrixMixin, FittingParameterGroup):
    """A standalone fittable rate scheme with a settable ``n_states``.

    Own one of these when the scheme is all the group holds; mix
    :class:`RateMatrixMixin` into an existing group when the states carry other
    fitted quantities that belong beside their rates.
    """

    def __init__(
        self, name: str = "kinetics", n_states: int = 2, default_rate: float | None = None, **kwargs
    ):
        """Initialize an ``n_states`` scheme.

        Parameters
        ----------
        name : str
            Group name.
        n_states : int
            Number of states; at least two.
        default_rate : float, optional
            Value each transition starts at. Pass ``0.0`` for a model whose
            dynamics are optional, so an untouched scheme reads as "no
            kinetics" and the static route stays the default.
        **kwargs
            Forwarded to the parent constructor.
        """
        super().__init__(name=name, **kwargs)
        if default_rate is not None:
            self.default_rate = float(default_rate)
        self._rates: list = []
        self._n_states = 0
        self._rebuild_rates(n_states)

    @property
    def n_states(self) -> int:
        """Number of states in the scheme."""
        return self._n_states

    @n_states.setter
    def n_states(self, value: int) -> None:
        """Resize the scheme, keeping the rates that survive."""
        if max(2, int(value)) != self._n_states:
            self._rebuild_rates(value)

    @property
    def any_rate(self) -> bool:
        """True when at least one transition has a non-zero rate."""
        return any(float(p.value) > 0.0 for p in self._rates)
