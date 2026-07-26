r"""Uncertainty for the numbers a fit *reports* but does not fit.

A fit optimises amplitudes and lifetimes. Nobody publishes those. What goes in
the paper is a FRET efficiency, a species-averaged lifetime, a distance -- each
a function of the fitted parameters, each printed by ChiSurf to six digits with
no error bar at all. The uncertainty was never absent; it was never carried
across the function.

Two ways to carry it, and the difference between them is the point:

``draws``
    Evaluate the derived quantity at every posterior draw. This is exact for any
    function, however non-linear, and it produces the *actual* distribution --
    which for a ratio such as :math:`E = 1 - \langle\tau\rangle_{DA} /
    \langle\tau\rangle_{D}` is skewed and bounded even when both lifetimes are
    beautifully Gaussian. No approximation is made and none can break.

``delta``
    The classical linear propagation
    :math:`\sigma_g^2 = \nabla g^{\mathsf{T}} \Sigma \nabla g`, from a numerical
    gradient and the covariance at the optimum. Available without sampling, and
    symmetric by construction: it *cannot* express the skew above, so it is
    reported with that limitation attached rather than silently.

Which one was used is on every row, because a symmetric error bar on a bounded
ratio is not a rounding difference -- it is an interval whose ends are both
wrong, and the row has to say so.

A model advertises what it can report by listing attribute names in a class-level
:attr:`derived_quantities` tuple; anything reachable by :func:`getattr` and
returning a float qualifies. Nothing here is TCSPC-specific.
"""
from __future__ import annotations

import numpy as np

from chisurf import typing

__all__ = [
    "derived_quantity_names",
    "evaluate_derived",
    "derived_posterior",
    "MAX_DRAWS",
]

#: How many posterior draws a derived quantity is evaluated at. Each evaluation
#: sets every parameter and reads a property, which for a distance-distribution
#: model is not free; a few thousand draws already pin a 68% interval to well
#: under a percent, and the chain is thinned rather than truncated so the whole
#: posterior is still represented.
MAX_DRAWS = 4000


def derived_quantity_names(model) -> typing.List[str]:
    """Return the derived quantities a model says it can report.

    Parameters
    ----------
    model : chisurf.core.models.model.Model
        Model to interrogate.

    The class attribute is collected up the whole MRO rather than read off the
    most-derived class, so a subclass that adds a quantity keeps the ones it
    inherited instead of shadowing them. An instance may add its own on top,
    which is how a script or a plugin asks about a quantity the model class never
    anticipated.

    Returns
    -------
    list of str
        Attribute names, in declaration order, with duplicates from inheritance
        removed. Empty when the model declares none.
    """
    names: typing.List[str] = []
    for klass in reversed(type(model).__mro__):
        for name in klass.__dict__.get("derived_quantities", ()) or ():
            name = str(name)
            if name not in names:
                names.append(name)
    for name in getattr(model, "__dict__", {}).get("derived_quantities", ()) or ():
        name = str(name)
        if name not in names:
            names.append(name)
    return names


def evaluate_derived(
        model,
        names: typing.Sequence[str],
) -> np.ndarray:
    """Read each named quantity off a model, as a float array.

    Parameters
    ----------
    model : chisurf.core.models.model.Model
        Model in whatever parameter state the caller has put it in.
    names : sequence of str
        Attribute names to read.

    Returns
    -------
    numpy.ndarray
        One value per name. A quantity that raises, or that is not a finite
        scalar, reads ``nan`` -- a draw in a corner of the posterior where a
        distance distribution collapses is a real event, and it should cost that
        one draw rather than the whole calculation.
    """
    out = np.full(len(names), np.nan, dtype=np.float64)
    for i, name in enumerate(names):
        try:
            value = float(getattr(model, name))
        except Exception:
            continue
        out[i] = value
    return out


def _thin(n: int, limit: int) -> np.ndarray:
    """Return indices selecting at most ``limit`` draws, evenly spaced."""
    if n <= limit:
        return np.arange(n)
    return np.linspace(0, n - 1, limit).astype(np.int64)


def _from_draws(
        fit,
        model,
        names: typing.Sequence[str],
        chain: dict,
        p_value: float,
        max_draws: int,
) -> typing.Optional[typing.List[typing.Dict[str, typing.Any]]]:
    """Evaluate the derived quantities at posterior draws. See module docstring."""
    from chisurf.core.fitting import engine as _engine

    draws = np.atleast_2d(np.asarray(chain["parameter_values"], dtype=np.float64))
    chain_names = [str(n) for n in chain.get("parameter_names", [])]
    if draws.shape[0] < 32 or len(chain_names) != draws.shape[1]:
        return None

    # The chain was written for the model's free parameters in *its* order. If
    # the model has since been re-parameterised the two no longer describe the
    # same thing, and quietly zipping them would evaluate a lifetime at an
    # amplitude's draws.
    if [str(n) for n in model.parameter_names] != chain_names:
        return None

    keep = _thin(draws.shape[0], max(32, int(max_draws)))
    snapshot = list(model.parameter_values)
    values = np.full((keep.size, len(names)), np.nan, dtype=np.float64)
    try:
        for row, index in enumerate(keep):
            model.parameter_values = draws[index]
            values[row] = evaluate_derived(model, names)
    finally:
        model.parameter_values = snapshot

    # The effective sample size is a property of the chain, and thinning does not
    # create information: whichever is smaller is the honest count.
    effective = _effective_draws(chain)
    if effective is not None:
        effective = min(effective, float(keep.size))

    at_optimum = evaluate_derived(model, names)
    rows = []
    for i, name in enumerate(names):
        column = values[:, i]
        finite = column[np.isfinite(column)]
        summary = _engine.sample_asymmetry(column, effective, p_value=p_value)
        row = {
            "name": str(name),
            "value": float(at_optimum[i]),
            "method": "draws",
            "p_value": float(p_value),
            "n_draws": int(finite.size),
        }
        if summary is None:
            if finite.size < 32:
                note = "too few usable draws"
            else:
                # It varied not at all across the posterior. Usually a quantity
                # of parameters that are all fixed -- worth saying, because a
                # bare "n/a" reads as a failure to compute rather than as an
                # answer of zero width.
                note = "constant over the posterior"
            row.update({
                "median": float(np.median(finite)) if finite.size else float("nan"),
                "low": float("nan"),
                "high": float("nan"),
                "asymmetry": float("nan"),
                "warning": note,
            })
        else:
            median = summary["median"]
            row.update({
                "median": median,
                "low": median - summary["lower"],
                "high": median + summary["upper"],
                "sd": float(finite.std()) if finite.size else float("nan"),
                "asymmetry": summary["asymmetry"],
                "skew": summary["skew"],
                "gaussian_ok": summary["gaussian_ok"],
                "warning": summary["note"],
            })
        rows.append(row)
    return rows


def chain_verdict(fit) -> typing.Optional[bool]:
    """Say whether a convergence report exists and whether the chain passed it.

    A derived quantity mixes *every* parameter, so it is only as trustworthy as
    the worst-converged one: a chain that R-hat or the effective sample size
    rejected must not become the quoted interval merely because it went through
    a function on the way out. The same rule
    :class:`~chisurf.core.fitting.engine.StoredEngine` applies to a parameter,
    applied to what is computed from parameters.

    Parameters
    ----------
    fit : chisurf.core.fitting.fit.Fit
        Fit whose ``sampling_diagnostics`` is consulted.

    Returns
    -------
    bool or None
        ``True`` when every parameter passed, ``False`` when at least one did
        not, and ``None`` when no report exists at all -- which is not a pass,
        and is reported as unverified rather than silently promoted to one.
    """
    report = getattr(fit, "sampling_diagnostics", None)
    if not isinstance(report, dict):
        return None
    entries = report.get("parameters") or []
    if not entries:
        return None
    from chisurf.core.fitting import diagnostics as _dg
    for e in entries:
        rhat = e.get("rhat", float("nan"))
        ess = e.get("ess", 0.0)
        if not (np.isfinite(rhat) and rhat <= _dg.RHAT_THRESHOLD):
            return False
        if not (np.isfinite(ess) and ess >= _dg.ESS_THRESHOLD):
            return False
    return True


def _effective_draws(chain: dict) -> typing.Optional[float]:
    """Return the chain's smallest per-parameter effective sample size.

    A derived quantity mixes every parameter, so it inherits the worst-mixed
    one's autocorrelation rather than the average.
    """
    chains = chain.get("chains")
    if chains is None:
        return None
    from chisurf.core.fitting import diagnostics as _dg
    try:
        ess = np.asarray(_dg.effective_sample_size(
            np.asarray(chains, dtype=np.float64)), dtype=np.float64)
    except Exception:
        return None
    ess = ess[np.isfinite(ess)]
    if ess.size == 0:
        return None
    return float(ess.min())


def _from_covariance(
        fit,
        model,
        names: typing.Sequence[str],
        p_value: float,
) -> typing.Optional[typing.List[typing.Dict[str, typing.Any]]]:
    """Linear (delta-method) propagation through the covariance at the optimum."""
    import chisurf.core.fitting.fit as fit_module
    from chisurf.core.fitting import engine as _engine

    try:
        cov, used = fit_module.covariance_matrix(fit, model=model)
    except Exception:
        return None
    cov = np.atleast_2d(np.asarray(cov, dtype=np.float64))
    used = list(used)
    if cov.size == 0 or cov.shape[0] != len(used) or not np.all(np.isfinite(cov)):
        return None

    snapshot = np.asarray(model.parameter_values, dtype=np.float64)
    at_optimum = evaluate_derived(model, names)

    # Step each parameter by a fraction of its own marginal width, so the
    # gradient is measured on the scale the posterior actually occupies rather
    # than on an absolute step that is huge for one parameter and noise for the
    # next.
    sd = np.sqrt(np.maximum(np.diag(cov), 0.0))
    jacobian = np.zeros((len(names), len(used)), dtype=np.float64)
    try:
        for column, index in enumerate(used):
            if index >= snapshot.size:
                continue
            step = 0.05 * sd[column]
            if not np.isfinite(step) or step <= 0.0:
                step = 1e-4 * max(abs(float(snapshot[index])), 1.0)
            shifted = snapshot.copy()
            shifted[index] = snapshot[index] + step
            model.parameter_values = shifted
            plus = evaluate_derived(model, names)
            shifted[index] = snapshot[index] - step
            model.parameter_values = shifted
            minus = evaluate_derived(model, names)
            jacobian[:, column] = (plus - minus) / (2.0 * step)
    finally:
        model.parameter_values = list(snapshot)

    z = _engine._normal_quantile(0.5 + 0.5 * float(p_value))

    rows = []
    for i, name in enumerate(names):
        g = jacobian[i]
        if not np.all(np.isfinite(g)):
            variance = float("nan")
        else:
            variance = float(g @ cov @ g)
        sd_i = _sqrt(variance)
        value = float(at_optimum[i])
        rows.append({
            "name": str(name),
            "value": value,
            "median": value,
            "low": value - z * sd_i,
            "high": value + z * sd_i,
            "sd": sd_i,
            "method": "delta",
            "p_value": float(p_value),
            "asymmetry": float("nan"),
            "warning": (
                "linear propagation: symmetric by construction, so a bounded "
                "or ratio-valued quantity is misstated at both ends"
            ),
        })
    return rows


def _sqrt(x: float) -> float:
    """Square root that answers ``nan`` instead of raising on a negative input."""
    if not np.isfinite(x) or x < 0.0:
        return float("nan")
    return float(np.sqrt(x))


def derived_posterior(
        fit,
        names: typing.Optional[typing.Sequence[str]] = None,
        p_value: float = 0.68,
        model=None,
        max_draws: int = MAX_DRAWS,
) -> typing.List[typing.Dict[str, typing.Any]]:
    r"""Report each derived quantity with an interval, not just a number.

    Prefers posterior draws and falls back to linear propagation; see the module
    docstring for why the distinction is worth carrying on every row.

    Parameters
    ----------
    fit : chisurf.core.fitting.fit.Fit
        Fit to report on. Its stored chain is used when there is one.
    names : sequence of str, optional
        Quantities to report. Defaults to what the model declares in its
        ``derived_quantities``.
    p_value : float, optional
        Central coverage of the reported interval.
    model : chisurf.core.models.model.Model, optional
        Model whose quantities are meant. Defaults to ``fit.model``.
    max_draws : int, optional
        Cap on the number of draws evaluated; the chain is thinned to fit.

    Returns
    -------
    list of dict
        One row per quantity with ``name``, ``value`` (at the optimum),
        ``median``, ``low``, ``high``, ``method``, ``p_value`` and ``warning``.
        Empty when the model declares no derived quantities.

    Examples
    --------
    >>> rows = derived_posterior(fit)                        # doctest: +SKIP
    >>> for r in rows:                                       # doctest: +SKIP
    ...     print(f"{r['name']}: {r['median']:.4g} "
    ...           f"[{r['low']:.4g}, {r['high']:.4g}] ({r['method']})")
    """
    if model is None:
        model = getattr(fit, "model", None)
    if model is None:
        return []
    if names is None:
        names = derived_quantity_names(model)
    names = [str(n) for n in names]
    if not names:
        return []

    chain = getattr(fit, "sampling_chain", None)
    verdict = chain_verdict(fit)
    if (verdict is not False
            and isinstance(chain, dict)
            and chain.get("parameter_values") is not None):
        rows = _from_draws(fit, model, names, chain, p_value, max_draws)
        if rows is not None:
            for row in rows:
                row["converged"] = verdict
            return rows

    rows = _from_covariance(fit, model, names, p_value)
    if rows is not None:
        if verdict is False:
            # There *are* draws; they were refused. Saying only "linear
            # propagation" would leave the reader wondering why the chain they
            # can see on the fit was not used.
            for row in rows:
                row["converged"] = False
                row["warning"] = (
                    "chain did not converge, so it was not used; "
                    + row["warning"]
                )
        return rows

    value = evaluate_derived(model, names)
    return [{
        "name": str(name),
        "value": float(value[i]),
        "median": float(value[i]),
        "low": float("nan"),
        "high": float("nan"),
        "method": "none",
        "p_value": float(p_value),
        "asymmetry": float("nan"),
        "warning": "no uncertainty available: fit the model or sample it first",
    } for i, name in enumerate(names)]
