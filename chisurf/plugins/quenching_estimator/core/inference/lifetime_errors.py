"""Lifetimes on the labelled protein: water quenching, measurement error, free-dye references.

Every (dye, apo/holo, site) is measured at several heavy-water fractions. With
:math:`x` the fraction of normal water, the decay rate is linear,

.. math:: 1/\\tau = a + b\\,x,

so :math:`b` is the water quenching rate :math:`k_{q,w}` of that site (:func:`water_quenching`)
and the scatter of the points around their line *is* the measurement error (:func:`series_fits`).

**Scatter per dye** (:func:`measurement_scatter`), in units of the lifetime:

* ``regression``: pooled residual scatter, :math:`\\sqrt{\\sum r^2/\\sum(n-2)}`;
* ``leave_one_out``: the exact leave-one-out residual of a line,
  :math:`r_i/(1-h_i)`, rescaled by :math:`\\sqrt{1-h_i}` to the same scale;
* ``typical``: :math:`1.4826\\,\\mathrm{median}|\\cdot|` of the same, not moved by one bad series.

**Error per site** (:func:`site_lifetimes`). A site's own scatter is mixed with the dye's typical
scatter, counted as ``prior_points`` extra points,
:math:`\\sigma_{rel} = \\sqrt{(\\sum r^2 + p\\,t^2)/(n-2+p)}`, and the line's value at
:math:`x_0` (1 = normal water; 0 = heavy water for the dyes in ``d2o_dyes``) gets the regression
error :math:`\\sigma_{rel}\\sqrt{1/n + (x_0-\\bar x)^2/S_{xx}}`, converted to a lifetime error.

**Coverage** (:func:`loo_coverage`): the fraction of left-out points inside their 1-sigma error
bar; about 68 % for honest error bars.

**Free dye** (:func:`free_dye_lifetimes`): :math:`\\tau_0` in water from the titration summary,
:math:`\\tau_0` in heavy water from the free-dye rows at 100 % D2O, and
:math:`k_{q,w,free} = 1/\\tau_0(H_2O) - 1/\\tau_0(D_2O)` (:func:`free_water_quenching`).

**Water access** (:func:`water_access`): :math:`(1/\\tau_H - 1/\\tau_D)/k_{q,w,free}` per site
from the measured lifetimes alone; 1 means as exposed as the free dye.

Theory: ``docs/concepts/quenching_inference.md``. The table layouts are declared in
``settings/analysis/measurement_columns.yaml``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import columns as _columns
from .titration import _groups


def _settings():
    """The lifetime-error selections declared in the measurement-columns file.

    Returns
    -------
    dict
        The ``settings`` mapping.
    """
    return _columns.settings()


def _labelled(lifetimes, settings, complete=True):
    """Rows of labelled protein (apo/holo) with a site, optionally with D2O % and tau known.

    Parameters
    ----------
    lifetimes : numpy.ndarray
        Lifetime table from :func:`~.measurements.load_measurements`.
    settings : dict
        Declared settings (``labelled_conditions``).
    complete : bool, optional
        Also drop rows without a heavy-water fraction or a lifetime.

    Returns
    -------
    numpy.ndarray
        The selected rows, in table order.
    """
    keep = np.isin(lifetimes["condition"], settings["labelled_conditions"]) & np.isfinite(
        lifetimes["site"]
    )
    if complete:
        keep &= np.isfinite(lifetimes["d2o_percent"]) & np.isfinite(lifetimes["tau_x"])
    return lifetimes[keep]


def water_quenching(lifetimes, settings=None):
    """Water quenching rate per (dye, apo/holo, site): the slope of 1/tau vs the H2O fraction.

    Parameters
    ----------
    lifetimes : numpy.ndarray
        Lifetime table.
    settings : dict, optional
        Declared settings; the measurement-columns file by default.

    Returns
    -------
    numpy.ndarray
        Declared table ``water_quenching`` (``kq_w`` in 1/ns), one row per series with at least
        two distinct heavy-water fractions, sorted by dye, state and site.
    """
    settings = settings or _settings()
    labelled = _labelled(lifetimes, settings, complete=False)
    rows = []
    for (dye, state, site), idx in _groups(labelled, ("dye", "condition", "site")):
        g = labelled[idx]
        g = g[np.isfinite(g["d2o_percent"]) & np.isfinite(g["tau_x"])]
        if len(np.unique(g["d2o_percent"])) < 2:
            continue
        x = g["d2o_percent"] / 100.0
        slope, _ = np.polyfit(1 - x, 1.0 / g["tau_x"], 1)
        rows.append(dict(dye=dye, state=state, site=int(site), kq_w=slope))
    return _columns.make_table("water_quenching", rows)


def water_quenching_summary(water):
    """Median, minimum and maximum water quenching rate per dye.

    Parameters
    ----------
    water : numpy.ndarray
        Table ``water_quenching``.

    Returns
    -------
    dict
        ``{dye: {"median", "min", "max"}}`` in 1/ns.
    """
    out = {}
    for dye in sorted(set(water["dye"].tolist())):
        k = water["kq_w"][water["dye"] == dye]
        out[dye] = {"median": float(np.median(k)), "min": float(k.min()), "max": float(k.max())}
    return out


@dataclass(frozen=True)
class SeriesFit:
    """One heavy-water series of a (dye, apo/holo, site): the line 1/tau = a + b x.

    Attributes
    ----------
    dye, state : str
        Dye and apo/holo state.
    site : int
        Labelled residue.
    x : numpy.ndarray
        Fraction of normal water of each point.
    y : numpy.ndarray
        Decay rate 1/tau (1/ns) of each point.
    a, b : float
        Intercept (rate in heavy water) and slope (water quenching rate).
    n : int
        Number of points.
    relative_residual : numpy.ndarray
        ``(y - fit) / fit``.
    relative_leave_out : numpy.ndarray
        Leave-one-out residual ``(y - fit) / (1 - h) / fit``.
    leverage : numpy.ndarray
        Leverage ``h`` of each point.
    """

    dye: str
    state: str
    site: int
    x: np.ndarray
    y: np.ndarray
    a: float
    b: float
    n: int
    relative_residual: np.ndarray
    relative_leave_out: np.ndarray
    leverage: np.ndarray


def series_fits(lifetimes, settings=None):
    """The straight line of every heavy-water series.

    Parameters
    ----------
    lifetimes : numpy.ndarray
        Lifetime table.
    settings : dict, optional
        Declared settings (``min_series_points``); the measurement-columns file by default.

    Returns
    -------
    list of SeriesFit
        Series with at least ``min_series_points`` points and two distinct fractions, sorted by
        dye, state and site.
    """
    settings = settings or _settings()
    labelled = _labelled(lifetimes, settings)
    out = []
    for (dye, state, site), idx in _groups(labelled, ("dye", "condition", "site")):
        g = labelled[idx]
        x = 1 - g["d2o_percent"] / 100.0
        y = 1 / g["tau_x"]
        if len(x) < settings["min_series_points"] or len(np.unique(x)) < 2:
            continue
        b, a = np.polyfit(x, y, 1)
        fitted = a + b * x
        leverage = 1 / len(x) + (x - x.mean()) ** 2 / ((x - x.mean()) ** 2).sum()
        out.append(
            SeriesFit(
                dye=dye,
                state=state,
                site=int(site),
                x=x,
                y=y,
                a=a,
                b=b,
                n=len(x),
                relative_residual=(y - fitted) / fitted,
                relative_leave_out=(y - fitted) / (1 - leverage) / fitted,
                leverage=leverage,
            )
        )
    return out


def measurement_scatter(series, dyes=None, settings=None):
    """Scatter of a single lifetime measurement around its line, per dye, relative to tau.

    Parameters
    ----------
    series : list of SeriesFit
        From :func:`series_fits`.
    dyes : sequence of str, optional
        Dyes in output order; the declared ``dyes`` by default.
    settings : dict, optional
        Declared settings (``robust_scale``); the measurement-columns file by default.

    Returns
    -------
    numpy.ndarray
        Declared table ``measurement_scatter`` without coverage filled (NaN); see
        :func:`loo_coverage`.
    """
    settings = settings or _settings()
    rows = []
    for dye in dyes or settings["dyes"]:
        s = [r for r in series if r.dye == dye]
        residual = np.concatenate([r.relative_residual for r in s])
        leave_out = np.concatenate([r.relative_leave_out * np.sqrt(1 - r.leverage) for r in s])
        dof = sum(r.n - 2 for r in s)
        rows.append(
            dict(
                dye=dye,
                series=len(s),
                points=len(residual),
                regression=np.sqrt((residual**2).sum() / dof),
                leave_one_out=np.sqrt((leave_out**2).mean()),
                typical=settings["robust_scale"] * np.median(np.abs(leave_out)),
                coverage=np.nan,
            )
        )
    return _columns.make_table("measurement_scatter", rows)


def _scatter_of(scatter, dye, field):
    """One field of the scatter table for one dye.

    Parameters
    ----------
    scatter : numpy.ndarray
        Table ``measurement_scatter``.
    dye : str
        Dye name.
    field : str
        Column.

    Returns
    -------
    float
        The value.
    """
    return float(scatter[field][scatter["dye"] == dye][0])


def site_lifetimes(series, scatter, settings=None):
    """Lifetime and measurement error of every site, read from its line.

    Parameters
    ----------
    series : list of SeriesFit
        From :func:`series_fits`.
    scatter : numpy.ndarray
        Table ``measurement_scatter`` (its ``typical`` column).
    settings : dict, optional
        Declared settings (``prior_points``, ``d2o_dyes``); the measurement-columns file by
        default.

    Returns
    -------
    numpy.ndarray
        Declared table ``site_lifetimes``: one row per series and solvent (H2O for every dye,
        also D2O for ``d2o_dyes``), sorted by dye, solvent, state and site.
    """
    settings = settings or _settings()
    prior = settings["prior_points"]
    rows = []
    for r in series:
        own = (r.relative_residual**2).sum()
        typical = _scatter_of(scatter, r.dye, "typical")
        relative = np.sqrt((own + prior * typical**2) / (r.n - 2 + prior))
        x = r.x
        sxx = ((x - x.mean()) ** 2).sum()
        targets = [("H2O", 1.0)] + ([("D2O", 0.0)] if r.dye in settings["d2o_dyes"] else [])
        for solvent, x0 in targets:
            rate = r.a + r.b * x0
            factor = np.sqrt(1 / r.n + (x0 - x.mean()) ** 2 / sxx)
            rows.append(
                dict(
                    dye=r.dye,
                    solvent=solvent,
                    state=r.state,
                    site=r.site,
                    n=r.n,
                    tau_x=1 / rate,
                    sigma_meas=relative * factor / rate,
                    point_error_pct=100 * relative,
                    water_slope=r.b,
                    water_slope_err=relative * rate * np.sqrt(1 / sxx),
                )
            )
    rows.sort(key=lambda d: (d["dye"], d["solvent"], d["state"], d["site"]))
    return _columns.make_table("site_lifetimes", rows)


def loo_coverage(series, data):
    """Fraction of left-out points inside their 1-sigma error bar, per dye.

    Parameters
    ----------
    series : list of SeriesFit
        From :func:`series_fits`.
    data : numpy.ndarray
        Table ``site_lifetimes`` (its ``point_error_pct``).

    Returns
    -------
    dict
        ``{dye: fraction}``, dyes sorted.
    """
    inside = {}
    for r in series:
        match = (data["dye"] == r.dye) & (data["state"] == r.state) & (data["site"] == r.site)
        relative = data["point_error_pct"][match][0] / 100
        z = r.relative_leave_out / (relative / np.sqrt(1 - r.leverage))
        inside.setdefault(r.dye, []).extend(bool(abs(v) <= 1) for v in z)
    return {dye: float(np.mean(inside[dye])) for dye in sorted(inside)}


def _compensated_mean(values):
    """Mean by compensated (Kahan) summation, as a grouped mean of the reference analysis.

    Parameters
    ----------
    values : array_like
        Finite numbers.

    Returns
    -------
    float
        The mean.
    """
    total = comp = 0.0
    for v in np.asarray(values, float):
        y = v - comp
        t = total + y
        comp = t - total - y
        total = t
    return total / len(values)


def free_dye_lifetimes(titration_summary, lifetimes, settings=None):
    """Free-dye lifetimes tau0 in normal water and, for the water-quenched dye, heavy water.

    Parameters
    ----------
    titration_summary : numpy.ndarray
        Titration summary (``dye``, ``tau0_ns``): the mean over its rows is tau0 in H2O.
    lifetimes : numpy.ndarray
        Lifetime table: free-dye rows (``free_dye_condition``) at 100 % D2O give tau0 in D2O.
    settings : dict, optional
        Declared settings (``dyes``, ``d2o_dyes``, ``free_dye_condition``); the
        measurement-columns file by default.

    Returns
    -------
    dict
        ``{(dye, solvent): tau0 in ns}``.
    """
    settings = settings or _settings()
    out = {}
    for dye in settings["dyes"]:
        out[(dye, "H2O")] = _compensated_mean(
            titration_summary["tau0_ns"][titration_summary["dye"] == dye]
        )
        if dye in settings["d2o_dyes"]:
            free = (
                (lifetimes["dye"] == dye)
                & (lifetimes["condition"] == settings["free_dye_condition"])
                & (lifetimes["d2o_percent"] == 100)
            )
            out[(dye, "D2O")] = float(lifetimes["tau_x"][free].mean())
    return out


def free_dye_table(tau0):
    """The free-dye lifetimes as the declared table.

    Parameters
    ----------
    tau0 : dict
        ``{(dye, solvent): tau0}`` from :func:`free_dye_lifetimes`.

    Returns
    -------
    numpy.ndarray
        Declared table ``free_dye_lifetimes``.
    """
    rows = [dict(dye=d, solvent=s, tau0=v) for (d, s), v in tau0.items()]
    return _columns.make_table("free_dye_lifetimes", rows)


def free_water_quenching(tau0, dye=None, settings=None):
    """Water quenching rate of the free dye, 1/tau0(H2O) - 1/tau0(D2O).

    Parameters
    ----------
    tau0 : dict
        From :func:`free_dye_lifetimes`.
    dye : str, optional
        The dye; the declared ``water_reference_dye`` by default.
    settings : dict, optional
        Declared settings; the measurement-columns file by default.

    Returns
    -------
    float
        kq_w,free in 1/ns.
    """
    dye = dye or (settings or _settings())["water_reference_dye"]
    return 1 / tau0[(dye, "H2O")] - 1 / tau0[(dye, "D2O")]


def water_access(data, kqw_free, dye=None, settings=None):
    """Measured water access per site: (1/tau_H2O - 1/tau_D2O) / kq_w,free.

    Parameters
    ----------
    data : numpy.ndarray
        Table ``site_lifetimes``.
    kqw_free : float
        Water quenching rate of the free dye (1/ns).
    dye : str, optional
        The dye; the declared ``water_reference_dye`` by default.
    settings : dict, optional
        Declared settings; the measurement-columns file by default.

    Returns
    -------
    numpy.ndarray
        Declared table ``water_access``; one row per H2O row with a matching D2O row, in the
        order of the H2O rows (state, then site). ``measured_err`` is the line slope's error
        over kq_w,free.
    """
    dye = dye or (settings or _settings())["water_reference_dye"]
    h2o = data[(data["dye"] == dye) & (data["solvent"] == "H2O")]
    d2o = data[(data["dye"] == dye) & (data["solvent"] == "D2O")]
    rows = []
    for r_h in h2o:
        match = d2o[(d2o["site"] == r_h["site"]) & (d2o["state"] == r_h["state"])]
        if not len(match):
            continue
        rows.append(
            dict(
                site=int(r_h["site"]),
                state=str(r_h["state"]),
                measured=(1 / r_h["tau_x"] - 1 / match["tau_x"][0]) / kqw_free,
                measured_err=r_h["water_slope_err"] / kqw_free,
            )
        )
    return _columns.make_table("water_access", rows)


@dataclass(frozen=True)
class LifetimeErrors:
    """Everything chapter 2 derives from the lifetimes on the labelled protein.

    Attributes
    ----------
    water : numpy.ndarray
        Table ``water_quenching``.
    series : list of SeriesFit
        The heavy-water lines.
    scatter : numpy.ndarray
        Table ``measurement_scatter`` with its ``coverage`` column filled.
    data : numpy.ndarray
        Table ``site_lifetimes``.
    coverage : dict
        ``{dye: fraction of left-out points inside 1 sigma}``.
    tau0 : dict
        ``{(dye, solvent): free-dye tau0}``.
    kqw_free : float
        Water quenching rate of the free reference dye (1/ns).
    access : numpy.ndarray
        Table ``water_access``.
    """

    water: np.ndarray
    series: list
    scatter: np.ndarray
    data: np.ndarray
    coverage: dict
    tau0: dict
    kqw_free: float
    access: np.ndarray

    def median_sigma(self):
        """Median measurement error of a site lifetime per dye and solvent.

        Returns
        -------
        dict
            ``{"<dye> <solvent>": median sigma_meas in ns}``.
        """
        out = {}
        for key, idx in _groups(self.data, ("dye", "solvent")):
            out[f"{key[0]} {key[1]}"] = float(np.median(self.data["sigma_meas"][idx]))
        return out


def analyse_lifetimes(lifetimes, titration_summary, settings=None):
    """Chapter 2 in one call: water quenching, scatter, site errors, coverage, free dye.

    Parameters
    ----------
    lifetimes : numpy.ndarray
        Lifetime table (sites corrected).
    titration_summary : numpy.ndarray
        Titration summary (free-dye tau0 in water).
    settings : dict, optional
        Declared settings; the measurement-columns file by default.

    Returns
    -------
    LifetimeErrors
        All derived tables.
    """
    settings = settings or _settings()
    series = series_fits(lifetimes, settings)
    scatter = measurement_scatter(series, settings=settings)
    data = site_lifetimes(series, scatter, settings)
    coverage = loo_coverage(series, data)
    for i, dye in enumerate(scatter["dye"]):
        scatter["coverage"][i] = coverage.get(str(dye), np.nan)
    tau0 = free_dye_lifetimes(titration_summary, lifetimes, settings)
    kqw_free = free_water_quenching(tau0, settings=settings)
    return LifetimeErrors(
        water=water_quenching(lifetimes, settings),
        series=series,
        scatter=scatter,
        data=data,
        coverage=coverage,
        tau0=tau0,
        kqw_free=kqw_free,
        access=water_access(data, kqw_free, settings=settings),
    )
