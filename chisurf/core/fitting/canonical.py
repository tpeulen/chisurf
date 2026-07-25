r"""Gaussians in canonical (information) form, where the queries are closed-form.

A Gaussian can be written in two equivalent ways. The **moment** form carries a
mean and a covariance, which is what one wants to *report*. The **canonical** or
information form carries

.. math::

    \phi(x) \;=\; \exp\!\left(g + h^{\mathsf T}x - \tfrac12 x^{\mathsf T}Kx\right),
    \qquad K = \Sigma^{-1},\quad h = K\mu ,

which is what one wants to *compute with*, because the two operations an
inference engine performs are linear in it:

- **Conditioning** on :math:`x_B = v` drops the rows and columns of :math:`B`
  and shifts :math:`h_A \mapsto h_A - K_{AB}v`. No matrix is inverted and no
  optimiser is run — for a Gaussian this is *exactly* the answer that fixing
  those parameters and re-optimising the rest would give.
- **Marginalising** :math:`x_B` out is a Schur complement,
  :math:`K_A - K_{AB}K_{BB}^{-1}K_{BA}`.

Multiplying two canonical forms is adding :math:`(K, h, g)` on the union of
their scopes, which is what makes a factorised posterior composable: a global
fit's canonical form is the *sum* of its per-dataset ones, and eliminating a
variable touches only the factors it appears in.

This is the representation mature probabilistic graphical-model toolkits use for
continuous linear-Gaussian networks, and it does transfer to a fluorescence
posterior: the quadratic approximation at an optimum *is* a Gaussian, and the
parameters that enter a model linearly -- amplitudes, offsets, scatter fractions
-- are exactly Gaussian conditionally.

Notes
-----
The approximation is the Gaussian, not the algebra. Everything here is exact
*given* a Gaussian; how well that describes the posterior is the same question
the `laplace` engine already answers, and a chain remains the way to find out.
"""
from __future__ import annotations

import collections
import dataclasses
import math

import numpy as np

from chisurf import typing

__all__ = [
    "CanonicalForm",
    "LOG_2PI",
]

#: ``ln(2 pi)``, which appears in every Gaussian normaliser.
LOG_2PI = math.log(2.0 * math.pi)


@dataclasses.dataclass(frozen=True)
class CanonicalForm:
    """A Gaussian held as ``(K, h, g)`` over a named scope.

    Attributes
    ----------
    names : tuple of str
        Variable names, in the order of :attr:`K` and :attr:`h`.
    K : numpy.ndarray
        Precision matrix, ``inv(covariance)``. Symmetric.
    h : numpy.ndarray
        Information vector, ``K @ mean``.
    g : float
        Log normalising constant, chosen so that the integral of the form is the
        total mass it represents (see :meth:`from_moments`).
    """

    names: typing.Tuple[str, ...]
    K: np.ndarray
    h: np.ndarray
    g: float = 0.0

    def __post_init__(self) -> None:
        """Reject a scope that names the same variable twice.

        Every operation here addresses the scope by name -- :meth:`marginal`,
        :meth:`condition` and :meth:`__mul__` all build ``{name: index}`` -- so
        a repeated name would silently resolve to its *last* occurrence and
        return another variable's moments without ever raising. Uniqueness is
        the contract that makes the name the identity of the variable.

        Raises
        ------
        ValueError
            If a name appears more than once.
        """
        if len(set(self.names)) != len(self.names):
            counts = collections.Counter(self.names)
            repeated = sorted(n for n, c in counts.items() if c > 1)
            raise ValueError(
                f"a canonical form needs a unique name per variable; repeated: {repeated}"
            )

    # -- construction -----------------------------------------------------

    @classmethod
    def from_moments(
            cls,
            names: typing.Sequence[str],
            mean: np.ndarray,
            covariance: np.ndarray,
            log_mass: float = 0.0,
    ) -> CanonicalForm:
        """Build a canonical form from a mean and a covariance.

        Parameters
        ----------
        names : sequence of str
            Variable names.
        mean : array_like
            Mean vector.
        covariance : array_like
            Covariance matrix; must be positive definite.
        log_mass : float, optional
            Log of the total mass the form should integrate to. Zero gives a
            normalised density; pass a log-evidence to have marginalisation
            carry it correctly.

        Returns
        -------
        CanonicalForm
            The form.

        Raises
        ------
        ValueError
            If ``names`` repeats a name.
        numpy.linalg.LinAlgError
            If ``covariance`` is not positive definite.
        """
        names = tuple(str(n) for n in names)
        mean = np.atleast_1d(np.asarray(mean, dtype=np.float64))
        cov = np.atleast_2d(np.asarray(covariance, dtype=np.float64))
        cov = 0.5 * (cov + cov.T)
        chol = np.linalg.cholesky(cov)
        identity = np.eye(cov.shape[0])
        inv_chol = np.linalg.solve(chol, identity)
        K = inv_chol.T @ inv_chol
        h = K @ mean
        log_det_cov = 2.0 * float(np.log(np.diag(chol)).sum())
        g = float(
            log_mass
            - 0.5 * (cov.shape[0] * LOG_2PI + log_det_cov)
            - 0.5 * float(mean @ h)
        )
        return cls(names=names, K=K, h=h, g=g)

    # -- moments ----------------------------------------------------------

    @property
    def covariance(self) -> np.ndarray:
        """Return ``inv(K)``."""
        return np.linalg.inv(self.K)

    @property
    def mean(self) -> np.ndarray:
        """Return ``inv(K) @ h``, solved rather than inverted."""
        return np.linalg.solve(self.K, self.h)

    @property
    def log_mass(self) -> float:
        r"""Return :math:`\ln\int\phi`, the total mass this form carries.

        For a posterior built with the evidence as ``log_mass`` this is the log
        evidence, and marginalising variables out leaves it unchanged -- which
        is the point of tracking ``g`` at all.
        """
        d = self.K.shape[0]
        sign, log_det_k = np.linalg.slogdet(self.K)
        if sign <= 0:
            return float("nan")
        return float(
            self.g + 0.5 * (d * LOG_2PI - log_det_k + float(self.h @ self.mean))
        )

    def log_density(self, x: np.ndarray) -> float:
        """Return ``g + h.x - x.K.x/2`` at a point."""
        x = np.atleast_1d(np.asarray(x, dtype=np.float64))
        return float(self.g + self.h @ x - 0.5 * x @ self.K @ x)

    # -- the two operations -----------------------------------------------

    def marginal(self, keep: typing.Sequence[str]) -> CanonicalForm:
        r"""Integrate out every variable not in ``keep``.

        The Schur complement
        :math:`K_A - K_{AB}K_{BB}^{-1}K_{BA}`, with the matching update to
        :math:`h` and :math:`g`. The mass is preserved, so
        :attr:`log_mass` is unchanged by marginalisation.

        Parameters
        ----------
        keep : sequence of str
            Variables to keep. Order of the result follows ``keep``.

        Returns
        -------
        CanonicalForm
            The marginal.

        Raises
        ------
        KeyError
            If a requested name is not in this form's scope.
        ValueError
            If ``keep`` repeats a name.
        """
        keep = tuple(str(n) for n in keep)
        index = {n: i for i, n in enumerate(self.names)}
        missing = [n for n in keep if n not in index]
        if missing:
            raise KeyError(f"not in scope: {missing}")
        a = [index[n] for n in keep]
        b = [i for i in range(len(self.names)) if i not in set(a)]
        if not b:
            return CanonicalForm(
                names=keep,
                K=self.K[np.ix_(a, a)],
                h=self.h[a],
                g=self.g,
            )

        k_aa = self.K[np.ix_(a, a)]
        k_ab = self.K[np.ix_(a, b)]
        k_bb = self.K[np.ix_(b, b)]
        h_a, h_b = self.h[a], self.h[b]

        solved_kba = np.linalg.solve(k_bb, k_ab.T)   # K_bb^-1 K_ba
        solved_hb = np.linalg.solve(k_bb, h_b)       # K_bb^-1 h_b
        sign, log_det_kbb = np.linalg.slogdet(k_bb)
        if sign <= 0:
            raise np.linalg.LinAlgError(
                "the eliminated block is not positive definite"
            )
        return CanonicalForm(
            names=keep,
            K=k_aa - k_ab @ solved_kba,
            h=h_a - k_ab @ solved_hb,
            g=float(
                self.g
                + 0.5 * (len(b) * LOG_2PI - log_det_kbb + float(h_b @ solved_hb))
            ),
        )

    def condition(
            self,
            assignments: typing.Dict[str, float]
    ) -> CanonicalForm:
        r"""Hold variables at given values.

        :math:`K` loses the conditioned rows and columns and
        :math:`h_A \mapsto h_A - K_{AB}v`. Nothing is inverted and nothing is
        re-optimised: for a Gaussian this *is* the result of fixing those
        parameters and re-minimising over the rest, because the constrained
        minimum of a quadratic is exactly its conditional mode.

        Parameters
        ----------
        assignments : dict
            Variable name to held value.

        Returns
        -------
        CanonicalForm
            The conditional, over the remaining variables.

        Raises
        ------
        KeyError
            If a name is not in this form's scope.
        """
        assignments = {str(k): float(v) for k, v in assignments.items()}
        index = {n: i for i, n in enumerate(self.names)}
        missing = [n for n in assignments if n not in index]
        if missing:
            raise KeyError(f"not in scope: {missing}")
        if not assignments:
            return self

        b = [index[n] for n in assignments]
        a = [i for i in range(len(self.names)) if i not in set(b)]
        v = np.array([assignments[self.names[i]] for i in b], dtype=np.float64)

        k_bb = self.K[np.ix_(b, b)]
        h_b = self.h[b]
        g = float(self.g + h_b @ v - 0.5 * v @ k_bb @ v)
        if not a:
            return CanonicalForm(
                names=(), K=np.zeros((0, 0)), h=np.zeros(0), g=g
            )
        return CanonicalForm(
            names=tuple(self.names[i] for i in a),
            K=self.K[np.ix_(a, a)],
            h=self.h[a] - self.K[np.ix_(a, b)] @ v,
            g=g,
        )

    # -- composition ------------------------------------------------------

    def __mul__(self, other: CanonicalForm) -> CanonicalForm:
        """Return the product of two forms, on the union of their scopes.

        A product of Gaussians is a Gaussian whose ``(K, h, g)`` are the *sums*
        of the factors', extended to the union scope with zeros. This is why a
        factorised posterior composes: a global fit's form is the sum of its
        per-dataset ones, and eliminating a variable touches only the factors it
        appears in.
        """
        names = list(self.names) + [n for n in other.names if n not in self.names]
        index = {n: i for i, n in enumerate(names)}
        size = len(names)
        K = np.zeros((size, size), dtype=np.float64)
        h = np.zeros(size, dtype=np.float64)
        for form in (self, other):
            idx = [index[n] for n in form.names]
            K[np.ix_(idx, idx)] += form.K
            h[idx] += form.h
        return CanonicalForm(
            names=tuple(names), K=K, h=h, g=float(self.g + other.g)
        )

    def __len__(self) -> int:
        """Return the number of variables in scope."""
        return len(self.names)

    def __repr__(self) -> str:
        """Return a compact ``CanonicalForm(names)`` representation."""
        return f"CanonicalForm({', '.join(self.names)})"
