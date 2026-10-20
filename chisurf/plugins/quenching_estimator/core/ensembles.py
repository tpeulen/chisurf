"""Where the dye sits during the excited state: three ensembles of one diffusion problem.

The dye diffuses in its accessible volume with a local mobility ``m(x) = prod_r s_r``
(every residue within the slowing radius multiplies its slow factor in) and is quenched
at a rate ``k(x)``. Its equilibrium occupancy is ``w(x) = 1/m(x) = prod s^-n``: a sticky
residue slows the dye *and* holds it. QuEst solves that problem three ways, chosen by the
project's ``ensemble``:

``"equilibrium"``
    The static limit. Each voxel decays on its own at ``1/tau0 + k``, weighted by ``w``:
    ``tau_x = sum_x p(x) / (1/tau0 + k(x))``. Deterministic and fast, and what the inverse
    fit uses (:func:`..inference.site_table.equilibrium_lifetime` is the one copy of that sum).
``"walk"``
    Brownian walkers started from ``p(x)`` and a photon race along each
    (:func:`.av.simulate_walkers`). The straightforward path for FRET, where the donor and
    the acceptor move. Unbiased at any slow factor because it starts at equilibrium; its
    remaining error is Monte-Carlo noise plus a time-step bias at sticky boundaries.
``"pde"``
    The Smoluchowski equation with the stickiness as a potential and quenching as a sink,
    solved on the AV grid by IMP.bff's ``GridDiffusionSolver`` (``flux_form=
    "detailed_balance"``, weight ``w``, mobility ``D0 m``). Its stationary state without the
    sink is exactly ``w``; with the sink it is the decay *with* transport during the
    excited state, with no sampling noise. The walk is its stochastic realisation.

Theory: ``docs/concepts/quenching_inference.md`` ("Where the dye sits: three ensembles").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

__all__ = [
    "DEFAULT_ENSEMBLE",
    "ENSEMBLES",
    "WALK_SEGMENT_TAU0",
    "WALK_TARGET_WALKERS",
    "EnsembleFields",
    "EnsembleLifetimes",
    "decay_photons",
    "ensemble_fields",
    "equilibrium_lifetimes",
    "normalize_ensemble",
    "pde_decay",
    "pde_lifetimes",
    "pde_solver",
    "static_photons",
    "walk_segment",
]

#: The three ensembles a project can ask for.
ENSEMBLES = ("equilibrium", "walk", "pde")

#: The walk: what QuEst always ran, and the only one that simulates FRET.
DEFAULT_ENSEMBLE = "walk"

#: Length of one walker, in units of tau0, between these bounds. Each photon starts on a
#: random frame of the concatenated walkers, so a photon whose excited state outlives its
#: walker continues on the next one -- another equilibrium sample, but not the same path:
#: ~tau/T of the photons, 5 % at 20 tau0. Shorter walkers are more independent starts,
#: which is what a sticky (nearly immobile) dye needs; 20 tau0 also keeps the 10 tau0
#: position-autocorrelation window inside one walker.
WALK_SEGMENT_TAU0 = (20.0, 50.0)

#: Walkers the run aims for, within the bounds above.
WALK_TARGET_WALKERS = 1000


def walk_segment(tau0: float, t_max: float, n_blocks: int = 1) -> float:
    """Length of one walker, ns: the total time over :data:`WALK_TARGET_WALKERS`, clamped
    to :data:`WALK_SEGMENT_TAU0` x tau0 and to ``t_max``.

    The default run (8 x 16 000 ns, tau0 4.2) is 1000 walkers of 128 ns; a 400 ns run is
    5 walkers of 84 ns, and its noise is the user's to lengthen away.
    """
    lo, hi = (float(v) * float(tau0) for v in WALK_SEGMENT_TAU0)
    total = float(t_max) * max(1, int(n_blocks))
    return min(float(t_max), max(lo, min(hi, total / WALK_TARGET_WALKERS)))

#: Report spacing (ns) and span (in tau0) of the PDE decay the photons are drawn from.
PDE_DECAY_DT = 0.004
PDE_DECAY_SPAN_TAU0 = 15.0
PDE_KRYLOV_DIM = 128


def normalize_ensemble(value: Any) -> str:
    """The ensemble name, lower-case; ``None`` is the default.

    Raises
    ------
    ValueError
        For a name not in :data:`ENSEMBLES`.
    """
    name = DEFAULT_ENSEMBLE if value is None else str(value).strip().lower()
    if name not in ENSEMBLES:
        raise ValueError(f"ensemble must be one of {ENSEMBLES}, got {value!r}")
    return name


@dataclass
class EnsembleFields:
    """The maps of one dye on a grid every IMP.bff solver accepts (flat, C order).

    Attributes
    ----------
    ng : int
        Edge of the (possibly padded) grid.
    pad : int
        Empty voxels added on every side; the solvers refuse a domain on the outer shell.
    dg : float
        Voxel edge, Angstrom.
    bounds, mobility, weight, rate, diffusion : numpy.ndarray
        Occupancy (0/1), ``m``, ``w = 1/m`` (1 outside), ``k`` (1/ns, 0 outside) and
        ``D0 m`` (Angstrom^2/ns, 0 outside).
    """

    ng: int
    pad: int
    dg: float
    bounds: np.ndarray
    mobility: np.ndarray
    weight: np.ndarray
    rate: np.ndarray
    diffusion: np.ndarray

    @property
    def occupancy(self) -> np.ndarray:
        """The equilibrium occupancy ``w b / sum(w b)``."""
        p = self.weight * self.bounds
        return p / p.sum()

    def unpad(self, flat: np.ndarray) -> np.ndarray:
        """A flat padded map back on the AV's own ``(ng0, ng0, ng0)`` grid."""
        cube = np.asarray(flat).reshape((self.ng,) * 3)
        if self.pad == 0:
            return cube
        p = self.pad
        return cube[p:-p, p:-p, p:-p]


def ensemble_fields(density, mobility, rate_map, dg, diffusion_coefficient) -> EnsembleFields:
    """Flatten the AV's maps, padding by one voxel when the volume touches the grid edge.

    Parameters
    ----------
    density : numpy.ndarray
        ``(ng, ng, ng)``, nonzero where the dye may be.
    mobility : numpy.ndarray
        ``(ng, ng, ng)`` walk mobility ``m`` (:func:`.av.walk_mobility`).
    rate_map : numpy.ndarray or None
        ``(ng, ng, ng)`` quenching rate, 1/ns; ``None`` is no quenching.
    dg : float
    diffusion_coefficient : float
        ``D0``, Angstrom^2/ns.

    Returns
    -------
    EnsembleFields
    """
    b = (np.asarray(density) > 0).astype(np.float64)
    m = np.asarray(mobility, dtype=np.float64).reshape(b.shape)
    k = np.zeros_like(b) if rate_map is None else np.asarray(rate_map, np.float64).reshape(b.shape)
    shell = (
        b[0].any() or b[-1].any() or b[:, 0].any() or b[:, -1].any()
        or b[:, :, 0].any() or b[:, :, -1].any()
    )
    pad = 1 if shell else 0
    if pad:
        b = np.pad(b, pad)
        m = np.pad(m, pad, constant_values=1.0)
        k = np.pad(k, pad)
    inside = b > 0
    if np.any(m[inside] <= 0.0):
        raise ValueError("the mobility must be positive inside the volume")
    w = np.where(inside, 1.0 / np.where(inside, m, 1.0), 1.0)
    return EnsembleFields(
        ng=int(b.shape[0]),
        pad=pad,
        dg=float(dg),
        bounds=b.ravel(),
        mobility=m.ravel(),
        weight=w.ravel(),
        rate=(k * b).ravel(),
        diffusion=(float(diffusion_coefficient) * m * b).ravel(),
    )


@dataclass
class EnsembleLifetimes:
    """What an ensemble says about the donor, before any photon is drawn.

    Attributes
    ----------
    ensemble : str
    tau_x : float
        Species-averaged lifetime ``int F dt`` (ns) = QY x tau0.
    tau_f : float
        Intensity-averaged lifetime ``int t F / int F`` (ns).
    quantum_yield : float
        ``tau_x / tau0`` (Phi / Phi0).
    contact_fraction : float
        Equilibrium share of the ensemble where ``k > 0``.
    limits : dict
        ``static`` and ``fast_exchange`` tau_x (ns): the D -> 0 and D -> inf bounds.
    """

    ensemble: str
    tau_x: float
    tau_f: float
    quantum_yield: float
    contact_fraction: float
    limits: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        """Plain JSON-able copy."""
        return {
            "ensemble": self.ensemble,
            "tau_x": float(self.tau_x),
            "tau_f": float(self.tau_f),
            "quantum_yield": float(self.quantum_yield),
            "contact_fraction": float(self.contact_fraction),
            **{f"tau_x_{k}": float(v) for k, v in self.limits.items()},
        }


def _contact_fraction(f: EnsembleFields) -> float:
    return float((f.occupancy * (f.rate > 0)).sum())


def equilibrium_lifetimes(f: EnsembleFields, tau0: float) -> EnsembleLifetimes:
    """The static ensemble: every voxel decays on its own, weighted by ``w``.

    ``tau_x`` is :func:`..inference.site_table.equilibrium_lifetime` on these maps (the
    inverse fit's closed form); ``tau_f = sum p tau^2 / sum p tau``.
    """
    from chisurf.plugins.quenching_estimator.core.inference.site_table import (
        equilibrium_lifetime,
    )

    tau0 = float(tau0)
    tau_x = equilibrium_lifetime(f.bounds, f.mobility, f.rate, tau0)
    inside = f.bounds > 0
    p = f.occupancy[inside]
    tau = 1.0 / (1.0 / tau0 + f.rate[inside])
    tau_f = float((p * tau * tau).sum() / (p * tau).sum())
    return EnsembleLifetimes(
        "equilibrium", tau_x, tau_f, tau_x / tau0, _contact_fraction(f), {"static": tau_x}
    )


def pde_solver(f: EnsembleFields, t_step: float = PDE_DECAY_DT):
    """IMP.bff's grid solver for these maps, started from the equilibrium occupancy."""
    import IMP.bff as bff

    return bff.GridDiffusionSolver(
        f.diffusion, f.bounds, f.occupancy, f.rate, f.dg, float(t_step),
        "detailed_balance", False, f.weight,
    )


def pde_lifetimes(f: EnsembleFields, tau0: float, solver=None) -> EnsembleLifetimes:
    """The PDE ensemble: transport resolved by two linear solves (no time step, no noise)."""
    s = pde_solver(f) if solver is None else solver
    life = s.lifetime(float(tau0))
    return EnsembleLifetimes(
        "pde",
        float(life.get_tau_x()),
        float(life.get_tau_f()),
        float(life.get_quantum_yield()),
        _contact_fraction(f),
        {
            "static": float(s.lifetime_static(float(tau0)).get_tau_x()),
            "fast_exchange": float(s.lifetime_fast_exchange(float(tau0)).get_tau_x()),
        },
    )


def pde_decay(f: EnsembleFields, tau0: float, solver=None, dt: float = PDE_DECAY_DT):
    """The donor decay ``I(t)/I(0) = e^(-t/tau0) sum p(t)`` by Lanczos.

    Returns
    -------
    t, intensity : numpy.ndarray
        Report grid every ``dt`` ns up to ``PDE_DECAY_SPAN_TAU0 * tau0``.
    """
    s = pde_solver(f, dt) if solver is None else solver
    n_steps = int(np.ceil(PDE_DECAY_SPAN_TAU0 * float(tau0) / float(dt)))
    r = s.donor_decay(float(tau0), n_steps, 1, PDE_KRYLOV_DIM)
    return np.asarray(r.get_time(), dtype=float), np.asarray(r.get_fluorescence(), dtype=float)


def _rng(seed: Optional[int]) -> np.random.Generator:
    return np.random.default_rng(None if seed is None else int(seed) & 0x7FFFFFFF)


def static_photons(f: EnsembleFields, tau0: float, n_photons: int, seed: Optional[int] = None):
    """A photon trace of the static ensemble: a voxel from ``p``, then a race at its rate.

    Returns
    -------
    delays, emitted : numpy.ndarray
        The shape :func:`.photon.simulate_photon_trace_rate` returns: delay (ns, 0 when
        quenched) and 1/0 per excitation.
    """
    n = max(0, int(n_photons))
    rng = _rng(seed)
    inside = np.flatnonzero(f.bounds > 0)
    p = f.occupancy[inside]
    voxel = inside[rng.choice(inside.size, size=n, p=p / p.sum())] if n else inside[:0]
    total = 1.0 / float(tau0) + f.rate[voxel]
    delay = rng.exponential(1.0, n) / total
    emitted = rng.random(n) < (1.0 / float(tau0)) / total
    return np.where(emitted, delay, 0.0), emitted.astype(np.uint8)


def decay_photons(t, intensity, quantum_yield, n_photons, seed: Optional[int] = None):
    """A photon trace drawn from a decay curve: Binomial(n, QY) emitted, times from ``I(t)``.

    The emission density is ``I(t)/tau0``; its integral is the quantum yield, which is
    passed in (the PDE's exact one) rather than read back from the truncated curve.
    """
    n = max(0, int(n_photons))
    rng = _rng(seed)
    t = np.asarray(t, dtype=float)
    y = np.clip(np.asarray(intensity, dtype=float), 0.0, None)
    n_emit = int(rng.binomial(n, min(1.0, max(0.0, float(quantum_yield))))) if n else 0
    cdf = np.concatenate([[0.0], np.cumsum(0.5 * (y[1:] + y[:-1]) * np.diff(t))])
    cdf /= cdf[-1]
    u = rng.random(n_emit)
    i = np.clip(np.searchsorted(cdf, u, side="right") - 1, 0, t.size - 2)
    frac = (u - cdf[i]) / np.maximum(cdf[i + 1] - cdf[i], 1e-300)
    times = t[i] + frac * (t[i + 1] - t[i])
    delays = np.zeros(n)
    emitted = np.zeros(n, dtype=np.uint8)
    slots = rng.permutation(n)[:n_emit]
    delays[slots] = times
    emitted[slots] = 1
    return delays, emitted
