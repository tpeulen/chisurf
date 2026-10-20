"""Free-dye titrations: Stern-Volmer slopes and their hierarchical day-to-day error.

The free dye is titrated with a free amino acid and its lifetime is measured at each
concentration. Collisional quenching gives the Stern-Volmer line

.. math:: \\tau_0/\\tau = 1 + K_{SV}\\,[Q],

and the bimolecular quenching constant :math:`k_q = K_{SV}/\\tau_0`.

**Per day.** One straight line per (dye, amino acid, day) gives a slope :math:`y_d` and its
regression error :math:`s_d` (:func:`per_day_slopes`).

**All days together.** The slopes of different days scatter more than one day's regression
error says. Each day's slope is modelled as the true :math:`K_{SV}` plus the regression error
plus a day-to-day error with an absolute and a relative part,

.. math:: v_d = s_d^2 + a^2 + (r\\,|\\bar y|)^2,

where :math:`a` and :math:`r` are shared by every titration and :math:`|\\bar y|` is the
titration's precision-weighted mean slope. With a flat prior on :math:`K_{SV}` the posterior of
each titration is Gaussian for fixed :math:`(a, r)`, and its evidence is closed form. The
evidence summed over titrations, on a log grid of :math:`(a, r)`, is the hyper-posterior
(flat per decade); the :math:`K_{SV}` posterior is the mixture of the Gaussians over that grid
(:func:`titration_posterior`). No sampler is needed.

Negative slopes are kept as they are measured. Only their positive part counts as quenching,
and that cut is applied where kQ is formed (:mod:`.kq_scaling`).

Theory: ``docs/concepts/quenching_inference.md``. The table layouts are declared in
``settings/analysis/measurement_columns.yaml``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import columns as _columns


def _settings():
    """The titration selections declared in the measurement-columns file.

    Returns
    -------
    dict
        The ``settings`` mapping.
    """
    return _columns.settings()


def day_error_grids(settings=None):
    """The log grids of the absolute and relative day-to-day error.

    Parameters
    ----------
    settings : dict, optional
        Declared settings (``day_abs_grid``, ``day_rel_grid`` with ``low``, ``high``, ``n``);
        the measurement-columns file by default.

    Returns
    -------
    tuple of numpy.ndarray
        ``(day_abs, day_rel)``: absolute part in 1/M, relative part as a fraction.
    """
    settings = settings or _settings()
    grids = []
    for key in ("day_abs_grid", "day_rel_grid"):
        g = settings[key]
        grids.append(np.logspace(np.log10(g["low"]), np.log10(g["high"]), int(g["n"])))
    return grids[0], grids[1]


def line_fit(x, y):
    """Straight line ``y = intercept + slope * x``: the slope and its regression error.

    Parameters
    ----------
    x, y : array_like
        Points of the line.

    Returns
    -------
    tuple of float
        ``(slope, slope_error)``; the error is 0 when the line has no degree of freedom left.
    """
    x, y = np.asarray(x, float), np.asarray(y, float)
    slope, intercept = np.polyfit(x, y, 1)
    residual = y - (intercept + slope * x)
    dof = len(x) - 2
    if dof < 1:
        return slope, 0.0
    return slope, np.sqrt((residual**2).sum() / dof / ((x - x.mean()) ** 2).sum())


def _groups(table, keys):
    """Row indices of a structured array grouped by key fields, groups in sorted key order.

    Parameters
    ----------
    table : numpy.ndarray
        Structured array.
    keys : sequence of str
        Field names to group by.

    Returns
    -------
    list of tuple
        ``(key tuple, row indices)`` with the rows of each group in table order.
    """
    groups = {}
    for i, row in enumerate(table):
        key = tuple(row[k].item() if hasattr(row[k], "item") else row[k] for k in keys)
        groups.setdefault(key, []).append(i)
    return [(key, np.asarray(groups[key])) for key in sorted(groups)]


def per_day_slopes(points, settings=None):
    """One Stern-Volmer line per (dye, amino acid, day).

    Parameters
    ----------
    points : numpy.ndarray
        Titration points (:data:`~.measurements.TITRATION_POINT_FIELDS`): ``dye``,
        ``amino_acid``, ``date``, ``concentration_mM``, ``tau0_ns``, ``tau_x``.
    settings : dict, optional
        Declared settings (``min_concentrations``); the measurement-columns file by default.

    Returns
    -------
    numpy.ndarray
        Declared table ``titration_days``: ``ksv`` and ``ksv_sd`` in 1/M, ``tau0`` the day's
        mean unquenched lifetime (ns). Days with fewer distinct concentrations than
        ``min_concentrations`` are skipped.
    """
    settings = settings or _settings()
    ratio = points["tau0_ns"] / points["tau_x"]
    rows = []
    for (dye, aa, day), idx in _groups(points, ("dye", "amino_acid", "date")):
        conc = points["concentration_mM"][idx]
        if len(np.unique(conc)) < settings["min_concentrations"]:
            continue
        k, k_err = line_fit(conc, ratio[idx] - 1)
        rows.append(
            dict(
                dye=dye,
                amino_acid=aa,
                day=int(day),
                ksv=k * 1000,
                ksv_sd=k_err * 1000,
                tau0=points["tau0_ns"][idx].mean(),
            )
        )
    return _columns.make_table("titration_days", rows)


@dataclass(frozen=True)
class TitrationPosterior:
    """The K_SV posterior of every titration and the day-to-day error hyper-posterior.

    Attributes
    ----------
    table : numpy.ndarray
        Declared table ``k_posterior``: one row per (dye, amino acid) with ``days``, ``tau0``,
        ``ksv``, ``ksv_sd`` (1/M) and ``kq``, ``kq_sd`` (1/(M ns) = 1e9/(M s)).
    weight : numpy.ndarray
        Normalised hyper-posterior on the grid, shape ``(len(day_abs), len(day_rel))``.
    day_abs, day_rel : numpy.ndarray
        The grids: absolute day-to-day error (1/M) and relative part (fraction).
    """

    table: np.ndarray
    weight: np.ndarray
    day_abs: np.ndarray
    day_rel: np.ndarray

    @property
    def abs_marginal(self):
        """Marginal weight of the absolute day-to-day error.

        Returns
        -------
        numpy.ndarray
            One weight per ``day_abs`` grid point.
        """
        return self.weight.sum(1)

    @property
    def rel_marginal(self):
        """Marginal weight of the relative day-to-day error.

        Returns
        -------
        numpy.ndarray
            One weight per ``day_rel`` grid point.
        """
        return self.weight.sum(0)

    def quantile(self, which, q):
        """A quantile of a day-to-day error marginal, linear in the cumulative weight.

        Parameters
        ----------
        which : {"abs", "rel"}
            The absolute or the relative part.
        q : float
            Probability, 0..1.

        Returns
        -------
        float
            The grid value where the cumulative marginal reaches ``q``.
        """
        grid, w = (
            (self.day_abs, self.abs_marginal)
            if which == "abs"
            else (self.day_rel, self.rel_marginal)
        )
        return float(np.interp(q, np.cumsum(w), grid))

    @property
    def edge_mass(self):
        """Hyper-posterior weight on the grid's border rows and columns.

        Returns
        -------
        float
            Weight on the first/last row plus the first/last column (corners count twice, as
            in the analysis it reproduces). Above 0.05 the grid is too narrow.
        """
        w = self.weight
        return float(w[[0, -1], :].sum() + w[:, [0, -1]].sum())

    def _by_key(self, field):
        """Map ``(dye, amino acid)`` to one field of the table.

        Parameters
        ----------
        field : str
            Column of :attr:`table`.

        Returns
        -------
        dict
            ``{(dye, amino_acid): value}``.
        """
        return {(str(r["dye"]), str(r["amino_acid"])): float(r[field]) for r in self.table}

    def k_mean(self):
        """Posterior mean K_SV per titration.

        Returns
        -------
        dict
            ``{(dye, amino_acid): K_SV in 1/M}``.
        """
        return self._by_key("ksv")

    def k_sd(self):
        """Posterior standard deviation of K_SV per titration.

        Returns
        -------
        dict
            ``{(dye, amino_acid): sd in 1/M}``.
        """
        return self._by_key("ksv_sd")

    def tau0(self):
        """Mean unquenched lifetime of each titration's days.

        Returns
        -------
        dict
            ``{(dye, amino_acid): tau0 in ns}``.
        """
        return self._by_key("tau0")


def titration_posterior(per_day, day_abs=None, day_rel=None, settings=None):
    """The hierarchical posterior of all titrations, solved on the day-to-day error grid.

    Parameters
    ----------
    per_day : numpy.ndarray
        Table ``titration_days`` from :func:`per_day_slopes`.
    day_abs, day_rel : numpy.ndarray, optional
        Hyper-parameter grids; :func:`day_error_grids` by default.
    settings : dict, optional
        Declared settings (``slope_weight_floor``, the grids); the measurement-columns file by
        default.

    Returns
    -------
    TitrationPosterior
        Per-titration K_SV mixture mean and sd, kq = K_SV/tau0, and the hyper-posterior.
    """
    settings = settings or _settings()
    if day_abs is None or day_rel is None:
        grid_abs, grid_rel = day_error_grids(settings)
        day_abs = grid_abs if day_abs is None else np.asarray(day_abs, float)
        day_rel = grid_rel if day_rel is None else np.asarray(day_rel, float)
    floor = settings["slope_weight_floor"]
    log_evidence = np.zeros((len(day_abs), len(day_rel)))
    gaussians = []
    for (dye, aa), idx in _groups(per_day, ("dye", "amino_acid")):
        y, se = per_day["ksv"][idx], per_day["ksv_sd"][idx]
        size = abs(np.average(y, weights=1 / (se**2 + floor)))
        v = se**2 + day_abs[:, None, None] ** 2 + (day_rel[None, :, None] * size) ** 2
        V = 1 / (1 / v).sum(-1)
        m = V * (y / v).sum(-1)
        quad = (y * y / v).sum(-1) - m * m / V
        log_evidence += (
            -0.5 * np.log(v).sum(-1)
            + 0.5 * np.log(V)
            - 0.5 * quad
            - 0.5 * (len(y) - 1) * np.log(2 * np.pi)
        )
        gaussians.append((dye, aa, m, V, len(y), per_day["tau0"][idx].mean()))
    weight = np.exp(log_evidence - log_evidence.max())
    weight /= weight.sum()
    rows = []
    for dye, aa, m, V, n, tau0 in gaussians:
        K = (weight * m).sum()
        K_sd = np.sqrt(max((weight * (V + m**2)).sum() - K**2, 0.0))
        rows.append(
            dict(
                dye=dye,
                amino_acid=aa,
                days=n,
                tau0=tau0,
                ksv=K,
                ksv_sd=K_sd,
                kq=K / tau0,
                kq_sd=K_sd / tau0,
            )
        )
    return TitrationPosterior(
        table=_columns.make_table("k_posterior", rows),
        weight=weight,
        day_abs=day_abs,
        day_rel=day_rel,
    )


def analyse_titrations(points, settings=None):
    """Per-day slopes and the hierarchical posterior in one call.

    Parameters
    ----------
    points : numpy.ndarray
        Titration points, as read by :func:`~.measurements.load_measurements`.
    settings : dict, optional
        Declared settings; the measurement-columns file by default.

    Returns
    -------
    tuple
        ``(per_day, posterior)``: the ``titration_days`` table and the
        :class:`TitrationPosterior`.
    """
    per_day = per_day_slopes(points, settings)
    return per_day, titration_posterior(per_day, settings=settings)
