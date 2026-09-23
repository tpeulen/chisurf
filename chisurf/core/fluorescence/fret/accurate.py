"""Accurate FRET in ChiSurf: the calibration-parameter side of tttrlib's calibration.

The algorithms -- corrected E/S, the population gating, the alpha/delta/gamma/
beta estimators, the self-consistent iteration, the bootstrap, the propagated
uncertainties, the distance conversion and the species-specific gamma -- live
in tttrlib (``tttrlib.auto_calibrate``, ``tttrlib.accurate_fret``,
``tttrlib.corrected_es``, ...), one implementation shared with ndXplorer.

What stays here is what only ChiSurf has: the correction factors as
:class:`~chisurf.core.fluorescence.fret.calibration.CalibrationParameters`
(fitting parameters that carry the light-path priors), the light-path payload
that seeds those priors, the static FRET line built by
:mod:`chisurf.core.fluorescence.fret.lines`, and the printable report.
:func:`auto_calibrate` reads the parameters and priors, hands the arrays to
tttrlib, and writes the calibrated factors back into the parameters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

import numpy as np
import tttrlib

from chisurf.core.fluorescence.fret.calibration import CalibrationParameters
from chisurf.core.fluorescence.fret.lines import FretLine, static_fret_line

__all__ = ["AutoCalibration", "auto_calibrate", "calibration_constants"]

#: The factors tttrlib calibrates, as named on :class:`CalibrationParameters`.
_FACTORS = ("gamma", "alpha", "beta", "delta")


@dataclass
class AutoCalibration:
    """Result of :func:`auto_calibrate`.

    Attributes
    ----------
    calibration : CalibrationParameters
        The calibrated group (updated in place when one was passed in).
    factors : dict
        ``gamma``/``alpha``/``beta``/``delta``, the three backgrounds and ``r0``.
    uncertainties : dict
        Standard uncertainty per factor (``NaN`` when not estimated).
    split : types.SimpleNamespace or None
        The final population assignment as tttrlib returns it
        (``donor_only``, ``acceptor_only``, ``fret``, ``fret_labels``,
        ``thresholds``, ``method``, ``counts``, ``fret_probabilities``).
    gamma_estimates : dict
        ``"es"``, ``"lifetime"``, ``"prior"``, ``"data"`` and ``"posterior"``.
    populations : list of dict
        Per-FRET-population summary (mean E/S/lifetime/distance and errors).
    iterations : int
        Self-consistency passes run.
    converged : bool
        Whether the factors stopped changing within the tolerance.
    messages : list of str
        What the procedure did and what it could not do.
    species : dict or None
        Global and per-population factors with the shared-versus-species model
        choice (``tttrlib.auto_calibrate``'s ``"species"``).
    tau_d0 : float
        Donor-only lifetime the lifetime route used (``NaN`` without lifetimes).
    """

    calibration: CalibrationParameters
    factors: dict
    uncertainties: dict = field(default_factory=dict)
    split: SimpleNamespace | None = None
    gamma_estimates: dict = field(default_factory=dict)
    populations: list = field(default_factory=list)
    iterations: int = 0
    converged: bool = False
    messages: list = field(default_factory=list)
    species: dict | None = None
    tau_d0: float = float("nan")

    def report(self) -> str:
        """Human-readable summary of the calibration and how it was obtained."""
        lines = ["Automatic FRET calibration", "=========================="]
        for key in ("alpha", "delta", "gamma", "beta"):
            u = self.uncertainties.get(key, float("nan"))
            unc = "" if not np.isfinite(u) else f" ± {u:.4f}"
            lines.append(f"  {key:<6s} = {self.factors.get(key, float('nan')):.4f}{unc}")
        if self.split is not None:
            c = self.split.counts
            lines.append(
                f"  bursts: {c['donor_only']} donor-only, {c['acceptor_only']} "
                f"acceptor-only, {c['fret']} FRET in {c['fret_populations']} population(s)"
            )
            lines.append(
                f"  stoichiometry cuts ({self.split.method}): "
                f"{self.split.thresholds[0]:.3f} / {self.split.thresholds[1]:.3f}"
            )
        labels = {
            "prior": "light path",
            "es": "E-S population fit",
            "lifetime": "static FRET line",
            "data": "data (adopted)",
            "posterior": "posterior",
        }
        for key, label in labels.items():
            value = self.gamma_estimates.get(key)
            if value is not None and np.isfinite(value):
                lines.append(f"  gamma [{label}] = {value:.4f}")
        if self.species and self.species["model_selection"]["selected"] == "species":
            values = ", ".join(f"{v:.4f}" for v in self.species["factors"]["gamma"]["values"])
            lines.append(f"  gamma per FRET population (species model, lower BIC) = {values}")
        for p in self.populations:
            tau = f", tau_f = {p['tau_f']:.3f} ns" if "tau_f" in p else ""
            dev = f", off-line by {p['deviation']:+.3f}" if "deviation" in p else ""
            lines.append(
                f"  population {p['label']}: n = {p['n']}, E = {p['E']:.3f} "
                f"± {p['sigma_E']:.3f}, R = {p['distance']:.1f} Å{tau}{dev}"
            )
        lines.extend(f"  ! {m}" for m in self.messages)
        lines.append(
            f"  {'converged' if self.converged else 'not converged'} "
            f"after {self.iterations} iteration(s)"
        )
        return "\n".join(lines)


def calibration_constants(calibration) -> dict:
    """The ``constants`` argument of ``tttrlib.auto_calibrate`` for a parameter group.

    Parameters
    ----------
    calibration : CalibrationParameters
        Factors, backgrounds and R0; Gaussian priors attached to ``gamma``,
        ``alpha`` and ``delta`` (e.g. by
        :func:`~chisurf.core.fluorescence.fret.calibration.set_priors_from_lightpath`)
        become ``(mu, sigma)`` priors.

    Returns
    -------
    dict
        ``{gamma, alpha, beta, delta, bg_dd, bg_da, bg_aa, r0, "priors": {...}}``.
    """
    from chisurf.core.fitting.priors import as_prior

    constants = {
        "gamma": calibration.gamma,
        "alpha": calibration.alpha,
        "beta": calibration.beta,
        "delta": calibration.delta,
        "bg_dd": calibration.bg_dd,
        "bg_da": calibration.bg_da,
        "bg_aa": calibration.bg_aa,
        "r0": calibration.r0,
    }
    priors = {}
    for name in ("gamma", "alpha", "delta"):
        prior = as_prior(getattr(getattr(calibration, "_" + name), "prior", None))
        if prior is not None and hasattr(prior, "mu") and hasattr(prior, "sigma"):
            priors[name] = (float(prior.mu), float(prior.sigma))
    constants["priors"] = priors
    return constants


def auto_calibrate(
    i_dd,
    i_da,
    i_aa=None,
    *,
    calibration=None,
    lightpath: dict | None = None,
    tau_f=None,
    line: FretLine | None = None,
    donor_lifetime: float | None = None,
    linker_sigma: float = 6.0,
    progress=None,
    columns: dict | None = None,
    **options,
) -> AutoCalibration:
    """Calibrate a :class:`CalibrationParameters` group from one measurement with tttrlib.

    The procedure is ``tttrlib.auto_calibrate`` (see its documentation). This
    adds the ChiSurf side: light-path priors on the parameters, the static
    FRET line built from ``donor_lifetime`` (the longest observed lifetime
    when omitted), and the write-back of the calibrated factors.

    Parameters
    ----------
    i_dd, i_da, i_aa : array_like
        Per-burst counts; ``i_aa`` (acceptor excitation) is optional.
    calibration : CalibrationParameters, optional
        Group to refine in place; a fresh one when omitted.
    lightpath : dict, optional
        Keyword arguments of
        :func:`~chisurf.core.fluorescence.fret.calibration.set_priors_from_lightpath`.
    tau_f : array_like, optional
        Per-burst donor lifetime (ns).
    line : FretLine, optional
        Static FRET line; built from ``donor_lifetime``, ``r0`` and
        ``linker_sigma`` when lifetimes are given without one.
    progress : callable, optional
        ``progress(step, total, message)``; returning ``False`` stops early.
    columns : dict, optional
        Extra per-burst columns for ``dimensions`` (``tau_a``, ``r_d``, ...).
    **options
        Any ``tttrlib.auto_calibrate`` option (``gamma_source``,
        ``n_bootstrap``, ``seed``, ``use_priors``, ``dimensions``, ...). The
        bootstrap draws ``numpy.random.default_rng(seed)``, as it always has.

    Returns
    -------
    AutoCalibration
    """
    from chisurf.core.fluorescence.fret.calibration import set_priors_from_lightpath

    calib = calibration if calibration is not None else CalibrationParameters()
    messages: list[str] = []
    if lightpath:
        optics = set_priors_from_lightpath(calib, **lightpath)
        messages.append(
            "light path: gamma {gamma:.4f}, alpha {alpha:.4f}, delta {delta:.4f} "
            "(prior means)".format(**optics)
        )
    tau = None if tau_f is None else np.asarray(tau_f, dtype=float)
    if line is None and tau is not None:
        base = donor_lifetime if donor_lifetime is not None else float(np.nanmax(tau))
        line = static_fret_line(float(base), r0=float(calib.r0), sigma=float(linker_sigma))
        if donor_lifetime is None:
            messages.append(
                f"donor-only lifetime not given; the static line uses the longest "
                f"observed lifetime ({base:.2f} ns) as tau_D(0)"
            )
    rng = np.random.default_rng(int(options.get("seed", 0)))
    options = dict(options, line=line)
    options.setdefault("bootstrap_indices", lambda size: rng.integers(0, size, size))
    data = dict(columns or {}, i_dd=i_dd, i_da=i_da, i_aa=i_aa, tau_f=tau)
    result = tttrlib.auto_calibrate(data, calibration_constants(calib), options, progress)
    for name in _FACTORS:
        setattr(calib, name, result["factors"][name])
    split = result["split"]
    return AutoCalibration(
        calibration=calib,
        factors=dict(result["factors"]),
        uncertainties=dict(result["uncertainties"]),
        split=None if split is None else SimpleNamespace(**split),
        gamma_estimates=dict(result["gamma_estimates"]),
        populations=list(result["populations"]),
        iterations=int(result["iterations"]),
        converged=bool(result["converged"]),
        messages=messages + list(result["messages"]),
        species=result.get("species"),
        tau_d0=float(result.get("tau_d0", float("nan"))),
    )
