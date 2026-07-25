from __future__ import annotations

import numpy as np

from chisurf.core.math.functions.distributions import normal_distribution


def mask_zero_photon_bins(fit, xmin: int, wres: np.ndarray) -> np.ndarray:
    """Return residuals with 2D PDA bins with zero experimental photons masked.

    Parameters
    ----------
    fit : chisurf.core.fitting.fit.Fit
        Fit providing the experimental DataCurve.
    xmin : int
        Starting index of the residual window.
    wres : numpy.ndarray
        Weighted residuals over the selected window.
    """
    try:
        if wres is None:
            return wres
        data_obj = getattr(fit, "data", None)
        y_data = getattr(data_obj, "y", None)
        if y_data is None:
            return wres
        y_arr = np.asarray(y_data, dtype=float)

        # Cache the zero-photon mask on the data object so the expensive
        # comparison y_arr > 0.0 is only performed once per dataset/size.
        try:
            nonzero_full = getattr(data_obj, "_pda_nonzero_mask", None)
        except Exception:
            nonzero_full = None
        if nonzero_full is None or getattr(nonzero_full, "size", 0) != y_arr.size:
            nonzero_full = y_arr > 0.0
            try:
                data_obj._pda_nonzero_mask = nonzero_full
            except Exception:
                pass

        n_points = wres.size
        start = int(max(0, xmin))
        stop = start + n_points
        nonzero = nonzero_full[start:stop]
        if not nonzero.size or not n_points:
            return wres
        mlen = min(nonzero.size, n_points)
        out = np.array(wres, copy=True)
        out[:mlen][~nonzero[:mlen]] = 0.0
        return out
    except Exception:
        return wres


def get_pda_distance_distribution(fit) -> list:
    """Return the P(R) distance-distribution curves for a Gaussian-distance PDA fit.

    Qt-free accessor for the data-driven (AutoForm) ``distribution`` plot. The
    first curve is the summed distribution; one curve per Gaussian component
    follows (restoring the per-component overlay of the legacy widget).

    Parameters
    ----------
    fit : chisurf.core.fitting.fit.Fit
        Fit whose ``model.distances`` provides the Gaussian components.

    Returns
    -------
    list
        ``[[p_sum, r], [p_1, r], ...]`` (each ``[y, x]``); empty if unavailable.
    """
    model = getattr(fit, "model", None)
    distances = getattr(model, "distances", None)
    if distances is None:
        return []
    try:
        dist = np.asarray(distances.distribution, dtype=float)
        if dist.ndim != 2 or dist.shape[1] == 0:
            return []
        r, p_sum = dist[0], dist[1]
        curves = [[p_sum, r]]
        means = distances.means
        sigmas = distances.sigmas
        amplitudes = distances.amplitudes
        if getattr(distances, "limited_width", False) and means.size:
            sigmas = (sigmas / 100.0) * means
        for mean, sigma, amp in zip(means, sigmas, amplitudes):
            if sigma <= 0.0 or amp <= 0.0:
                continue
            y = amp * normal_distribution(x=r, loc=float(mean), scale=float(sigma), norm=False)
            curves.append([y, r])
        return curves
    except Exception:
        return []


def get_pda_residual_image(fit_group, weighted: bool = True):
    """Return a 2D S1S2 residual image ``(image, x_axis, y_axis)`` for a PDA fit.

    Qt-free accessor for the data-driven (AutoForm) ``residual2d`` plot. Compares
    the experimental S1S2 histogram (``fit.data.pda['s1s2']``) with the model
    S1S2 matrix (``fit.model.pda.s1s2``). With ``weighted=True`` the residual is
    counting-noise weighted, ``(data - model) / sqrt(max(data, 1))``.

    Parameters
    ----------
    fit_group : object
        A fit group (with ``selected_fit``) or a plain fit.
    weighted : bool
        Whether to weight the residual by counting shot noise.

    Returns
    -------
    tuple
        ``(image, x_axis, y_axis)`` or ``(None, None, None)`` if unavailable.
    """
    fit = getattr(fit_group, "selected_fit", fit_group)
    data_pda = getattr(getattr(fit, "data", None), "pda", None)
    model_obj = getattr(getattr(fit, "model", None), "pda", None)
    if data_pda is None or model_obj is None:
        return None, None, None
    try:
        data_2d = np.asarray(data_pda.get("s1s2"), dtype=float)
        model_2d = np.asarray(getattr(model_obj, "s1s2"), dtype=float)
    except Exception:
        return None, None, None
    if data_2d.ndim != 2 or model_2d.ndim != 2:
        return None, None, None

    n0 = min(data_2d.shape[0], model_2d.shape[0])
    n1 = min(data_2d.shape[1], model_2d.shape[1])
    d = data_2d[:n0, :n1]
    m = model_2d[:n0, :n1]
    if weighted:
        img = (d - m) / np.sqrt(np.maximum(d, 1.0))
    else:
        img = d - m
    return img, np.arange(n1, dtype=float), np.arange(n0, dtype=float)


def apply_lightpath_to_nuisance(
    nuisance,
    lightpath_result: dict,
    donor: str,
    acceptor: str,
    green_detector: str,
    red_detector: str,
    green_laser: str | None = None,
) -> None:
    """Feed a light-path simulation result into a PDA FRET nuisance group.

    Bridge between the light-path simulator plugin and PDA models. Accepts
    either the full result of
    ``chisurf.plugins.core.lightpath_simulator.core.workflow.simulate_lightpath``
    (which nests the matrices under ``"crosstalk_matrices"``) or a bare
    ``crosstalk_matrices`` dict, and delegates to
    :meth:`PdaFretNuisance.apply_lightpath_matrices`.

    Parameters
    ----------
    nuisance : PdaFretNuisance
        Target nuisance group (updated in place).
    lightpath_result : dict
        Light-path simulation output or its ``crosstalk_matrices`` sub-dict.
    donor, acceptor : str
        Dye labels.
    green_detector, red_detector : str
        Detector labels for the green/red channels.
    green_laser : str, optional
        Donor-excitation laser label.
    """
    matrices = lightpath_result
    if isinstance(lightpath_result, dict) and "crosstalk_matrices" in lightpath_result:
        matrices = lightpath_result["crosstalk_matrices"]
    nuisance.apply_lightpath_matrices(
        matrices,
        donor=donor,
        acceptor=acceptor,
        green_detector=green_detector,
        red_detector=red_detector,
        green_laser=green_laser,
    )


def green_probability_from_efficiency(E, nuisance) -> np.ndarray:
    """Return the per-photon green (channel-1) probability for FRET efficiency ``E``.

    Uses the same excitation/emission/crosstalk description as
    :class:`~chisurf.core.models.pda.pdagauss.PdaGaussianDistanceModel`: absolute
    excitation probabilities (ExDG/ExAG), per-channel detector efficiencies
    (gG/gR), the 2x2 emission-detection crosstalk matrix (cGD/cGA/cRD/cRA) and
    the donor/acceptor quantum yields (QYD/QYA).

    Parameters
    ----------
    E : array_like
        FRET efficiency (or grid of efficiencies).
    nuisance : PdaFretNuisance
        Nuisance group supplying the correction parameters.

    Returns
    -------
    numpy.ndarray
        Probability that a photon is detected in the green channel.
    """
    eps = 1e-12
    E = np.clip(np.asarray(E, dtype=float), eps, 1.0 - eps)
    n = nuisance
    ExDG = float(getattr(n, "ExDG", 1.0))
    ExAG = float(getattr(n, "ExAG", 0.0))
    gG = float(getattr(n, "gG", 1.0))
    gR = float(getattr(n, "gR", 1.0))
    cGD = float(getattr(n, "cGD", 1.0))
    cGA = float(getattr(n, "cGA", 0.0))
    cRD = float(getattr(n, "cRD", 0.0))
    cRA = float(getattr(n, "cRA", 1.0))
    QYD = float(getattr(n, "QYD", 1.0))
    QYA = float(getattr(n, "QYA", 1.0))
    S_DQ = QYD * ExDG * (1.0 - E)
    S_AQ = QYA * (ExDG * E + ExAG)
    G = gG * (cGD * S_DQ + cGA * S_AQ)
    R = gR * (cRD * S_DQ + cRA * S_AQ)
    denom = G + R
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(denom > 0.0, G / denom, 0.5)


#: Named 1D PDA histogram axes. Each callback receives the tttrlib S1S2
#: counts as (ch1, ch2) = (red, green) and returns the scalar plotted on the
#: x-axis. Keeping these as named strings (not lambdas) lets the distribution
#: plot be authored declaratively in ``*.view.json`` (PRD-38).
_PDA_HISTOGRAM_AXES = {
    # Red fraction S1/(S0+S1) with S0=green, S1=red.
    "S1/(S0+S1)": lambda ch1, ch2: ch1 / max(1, ch1 + ch2),
    # Green/red ratio S0/S1.
    "S0/S1": lambda ch1, ch2: ch2 / max(1, ch1),
}

#: Axis names selectable for the fitted 1D histogram, in menu order. The first
#: two are raw (uncorrected) count ratios computed by ``_PDA_HISTOGRAM_AXES``;
#: ``E``/``R`` are gamma-corrected and need the model, so they are built by
#: :func:`build_pda_histogram_function`.
PDA_AXES = ("S1/(S0+S1)", "E", "S0/S1", "R")

#: Per-axis default binning ``(x_min, x_max, log_x)``. Selecting an axis on
#: :class:`PdaFitSettings` resets the range to these, because a range that is
#: sensible for a proximity ratio (0–1, linear) is meaningless for a distance
#: (Angstrom) or an intensity ratio (decades).
PDA_AXIS_RANGES = {
    "S1/(S0+S1)": (0.0, 1.0, False),
    "E": (0.0, 1.0, False),
    "S0/S1": (0.01, 500.0, True),
    "R": (20.0, 100.0, False),
}

#: Statistics available for the 1D residual, in menu order. See
#: :func:`pda_weighted_residuals` for what each one weights by.
PDA_STATISTICS = ("poisson", "neyman", "pearson")


def build_pda_histogram_function(model, axis: str):
    """Return the ``tttrlib.Pda.histogram_function`` for a named PDA axis.

    One place decides how an (S1, S2) count pair maps onto the plotted /
    fitted x-axis, so the distribution plot and the residual cannot drift
    apart. ``E`` and ``R`` are **corrected** axes: the raw red fraction
    ``PR = S1/(S0+S1)`` is turned into an efficiency with the model's detection
    correction factor gamma, ``E = PR / (PR + gamma(1-PR))``, and ``R`` inverts
    Foerster's relation with the model's ``forster_radius``. The two ratio axes
    need no model at all.

    Parameters
    ----------
    model : object
        PDA model supplying ``nuisance.gamma`` and
        ``fret_parameters.forster_radius`` for the corrected axes. Only read
        for ``E`` / ``R``; may be ``None`` otherwise.
    axis : str
        One of :data:`PDA_AXES`. Unknown names fall back to ``S1/(S0+S1)``.

    Returns
    -------
    callable
        ``f(ch1, ch2) -> float`` with ``(ch1, ch2) = (red, green)`` counts,
        as ``tttrlib.Pda`` calls it.
    """
    if axis in ("E", "R"):
        gamma = float(getattr(getattr(model, "nuisance", None), "gamma", 1.0) or 1.0)
        if not np.isfinite(gamma) or gamma <= 0.0:
            gamma = 1.0
        R0 = float(
            getattr(getattr(model, "fret_parameters", None), "forster_radius", 52.0) or 52.0
        )

        def histogram_function(ch1, ch2, _g=gamma, _r0=R0, _axis=axis):
            """Return the corrected FRET efficiency (or distance) for S1S2 counts."""
            total = ch1 + ch2
            pr = ch1 / total if total > 0 else 0.0
            denom = pr + _g * (1.0 - pr)
            e = pr / denom if denom > 0 else 0.0
            if _axis == "E":
                return e
            e = min(max(e, 1e-6), 1.0 - 1e-6)
            return _r0 * (1.0 / e - 1.0) ** (1.0 / 6.0)

        return histogram_function

    inner = _PDA_HISTOGRAM_AXES.get(axis, _PDA_HISTOGRAM_AXES["S1/(S0+S1)"])

    def histogram_function(ch1, ch2, _cb=inner):
        """Return the selected raw ratio axis for tttrlib.Pda S1S2 counts."""
        return _cb(ch1, ch2)

    return histogram_function


def pda_weighted_residuals(
        data_y,
        model_y,
        statistic: str = "poisson",
) -> np.ndarray:
    """Weighted residuals of a modelled counting histogram.

    The model is first rescaled to the total counts of the data — the PDA
    engine returns a normalised probability distribution (sum ~ 1) while the
    data is in counts — and then compared under one of three statistics whose
    sum of squares is the quantity the fit minimises:

    ``poisson``
        Poisson **deviance** (the likelihood-ratio / Cash statistic),
        ``r = sign(d-m) sqrt(2[m - d + d ln(d/m)])``. This is the residual form
        of the Poisson maximum likelihood and is the correct choice for PDA:
        the histogram is sparse (many bins hold a handful of bursts), which is
        exactly where the Gaussian approximations below break down. Empty bins
        contribute ``2m``, so they still constrain the fit.
    ``neyman``
        ``(d - m)/sqrt(max(d,1))``, the "data-weighted" chi-square. Cheap and
        familiar, but it *systematically underestimates* amplitudes at low
        counts, because a bin that fluctuated low is given a small sigma and
        therefore a large weight.
    ``pearson``
        ``(d - m)/sqrt(max(m,1))``, weighting by the model instead. Unbiased
        where ``neyman`` is biased low, and biased the other way.

    All three converge in the high-count limit; they differ where PDA works.

    Parameters
    ----------
    data_y : array_like
        Measured bin counts.
    model_y : array_like
        Modelled bin contents, in arbitrary normalisation.
    statistic : str
        One of :data:`PDA_STATISTICS`.

    Returns
    -------
    numpy.ndarray
        Weighted residuals, or an empty array if the shapes disagree.
    """
    d = np.asarray(data_y, dtype=float)
    m = np.asarray(model_y, dtype=float)
    if d.shape != m.shape:
        return np.zeros(0, dtype=np.float64)

    total_model = float(m.sum())
    if total_model > 0.0:
        m = m * (float(d.sum()) / total_model)

    if statistic == "neyman":
        return (d - m) / np.sqrt(np.maximum(d, 1.0))
    if statistic == "pearson":
        return (d - m) / np.sqrt(np.maximum(m, 1.0))

    # Poisson deviance. The d*ln(d/m) term is defined as 0 at d = 0 (its
    # limit), and m is floored so an empty model bin with data in it gives a
    # large-but-finite residual instead of an inf that poisons the fit.
    m_safe = np.maximum(m, 1e-12)
    terms = m_safe - d
    nz = d > 0.0
    terms[nz] += d[nz] * np.log(d[nz] / m_safe[nz])
    deviance = 2.0 * np.maximum(terms, 0.0)
    return np.sign(d - m) * np.sqrt(deviance)


class PdaFitSettings:
    """Which 1D histogram a PDA model is fitted against, and with what statistic.

    PDA compares a modelled and a measured **S1S2 count matrix**, but the fit
    itself runs on a 1D projection of it. Which projection is a real modelling
    choice, not a display preference: the raw proximity ratio needs no
    correction factors but smears the low-FRET species, the corrected ``E``
    axis is linear in the quantity of interest, and ``S0/S1`` on a log axis
    spreads out exactly the region where donor-only and low-FRET states
    overlap. This group carries that choice (plus the binning and the
    statistic) so it is visible and editable in the model editor rather than
    hard-coded in the residual.

    Attributes are plain scalars, so an AutoForm ``scalar_table`` / ``choice``
    section binds to them directly.
    """

    def __init__(
            self,
            axis: str = "S1/(S0+S1)",
            n_bins: int = 81,
            n_min: int = 10,
            statistic: str = "poisson",
            x_min: float | None = None,
            x_max: float | None = None,
            log_x: bool | None = None,
    ):
        """Initialize the fit-histogram settings.

        Parameters
        ----------
        axis : str
            Name of the fitted axis, one of :data:`PDA_AXES`.
        n_bins : int
            Number of histogram bins.
        n_min : int
            Minimum number of photons a burst must have to enter the histogram.
        statistic : str
            One of :data:`PDA_STATISTICS`.
        x_min, x_max, log_x : optional
            Explicit binning range; defaults to the axis' entry in
            :data:`PDA_AXIS_RANGES`.
        """
        lo, hi, log = PDA_AXIS_RANGES.get(axis, PDA_AXIS_RANGES["S1/(S0+S1)"])
        self._axis = axis if axis in PDA_AXIS_RANGES else "S1/(S0+S1)"
        self.x_min = lo if x_min is None else float(x_min)
        self.x_max = hi if x_max is None else float(x_max)
        self.log_x = log if log_x is None else bool(log_x)
        self.n_bins = int(n_bins)
        self.n_min = int(n_min)
        self.statistic = statistic if statistic in PDA_STATISTICS else "poisson"

    @property
    def axis(self) -> str:
        """Name of the fitted 1D histogram axis."""
        return self._axis

    @axis.setter
    def axis(self, value: str) -> None:
        """Select an axis, resetting the range to that axis' defaults."""
        value = value if value in PDA_AXIS_RANGES else "S1/(S0+S1)"
        if value == self._axis:
            return
        self._axis = value
        self.x_min, self.x_max, self.log_x = PDA_AXIS_RANGES[value]

    @property
    def kw_hist(self) -> dict:
        """Return the ``tttrlib.Pda.get_1dhistogram`` keyword arguments."""
        return {
            "x_min": float(self.x_min),
            "x_max": float(self.x_max),
            "log_x": bool(self.log_x),
            "n_bins": int(self.n_bins),
            "n_min": int(self.n_min),
        }

    def to_dict(self) -> dict:
        """Return the settings as a plain dict (for saving / round-tripping)."""
        d = self.kw_hist
        d["axis"] = self.axis
        d["statistic"] = self.statistic
        return d


def resolve_fit_settings(model, kw_hist: dict | None = None) -> PdaFitSettings:
    """Return the :class:`PdaFitSettings` a PDA model should be fitted with.

    Models constructed before this group existed took a bare ``kw_hist`` dict;
    that form is still accepted and folded into the settings object so old
    call sites and saved sessions keep working.

    Parameters
    ----------
    model : object
        PDA model, possibly carrying ``fit_settings``.
    kw_hist : dict, optional
        Legacy histogram-settings dict, may carry a ``histogram`` axis key.

    Returns
    -------
    PdaFitSettings
    """
    settings = getattr(model, "fit_settings", None)
    if isinstance(settings, PdaFitSettings):
        return settings
    kw = dict(kw_hist or {})
    axis = kw.pop("histogram", "S1/(S0+S1)")
    return PdaFitSettings(axis=axis, **{k: v for k, v in kw.items() if k in
                                        ("n_bins", "n_min", "x_min", "x_max", "log_x")})


def get_pda_distribution(fit, kw_hist: dict | None = None) -> list:
    """Return data/model/residual 1D-histogram curves for a PDA fit.

    Qt-free accessor used by the data-driven (AutoForm) ``distribution`` plot.
    ``kw_hist`` carries the usual ``tttrlib`` histogram settings plus a
    ``histogram`` key naming the x-axis (see :data:`_PDA_HISTOGRAM_AXES`), so
    the whole plot stays authorable in JSON (no GUI lambdas).

    Parameters
    ----------
    fit : chisurf.core.fitting.fit.Fit
        Fit whose ``model.pda`` and ``data.pda`` provide model/experimental
        S1S2 matrices.
    kw_hist : dict, optional
        Histogram settings; ``histogram`` selects the axis
        (default ``"S1/(S0+S1)"``).

    Returns
    -------
    list
        ``[[data_y, data_x], [model_y, model_x], [wres, data_x]]`` (residual
        curve omitted if shapes disagree).
    """
    model = getattr(fit, "model", None)
    pda = getattr(model, "pda", None)
    if pda is None:
        return []

    kw = dict(kw_hist or {})
    axis = kw.pop("histogram", "S1/(S0+S1)")
    pda.histogram_function = build_pda_histogram_function(model, axis)

    pda_meta = getattr(getattr(fit, "data", None), "pda", None)
    if not isinstance(pda_meta, dict):
        return []
    s1s2_experimental = pda_meta.get("s1s2")
    if s1s2_experimental is None:
        return []

    try:
        s1s2_model = np.asarray(pda.get_S1S2_matrix(), dtype=float)
        s1s2_data = np.asarray(s1s2_experimental, dtype=float)
        shp = pda_meta.get("shape")
        if shp is not None and len(shp) == 2:
            ny, nx = int(shp[0]), int(shp[1])
            s1s2_model = s1s2_model[:ny, :nx]
            s1s2_data = s1s2_data[:ny, :nx]

        model_x, model_y = pda.get_1dhistogram(s1s2=s1s2_model.flatten(), **kw)
        data_x, data_y = pda.get_1dhistogram(s1s2=s1s2_data.flatten(), **kw)
    except Exception:
        return []

    curves = [[data_y, data_x], [model_y, model_x]]
    try:
        # Same statistic the fit minimises, so the plotted residual panel and
        # the reported chi2r cannot disagree about what "poor" looks like.
        statistic = resolve_fit_settings(model).statistic
        wres = pda_weighted_residuals(data_y, model_y, statistic=statistic)
        if wres.size:
            curves.append([wres, data_x])
    except Exception:
        pass
    return curves


def pda_1d_residuals_from_s1s2(
        fit,
        pda_obj,
        nuisance=None,
        kw_hist: dict | None = None,
        settings: PdaFitSettings | None = None,
) -> np.ndarray:
    """Compute 1D PDA histogram residuals from S1S2 data.

    This is a shared implementation used by every PDA model to build 1D
    residuals from the experimental S1S2 histogram and the ``tttrlib.Pda``
    model S1S2 matrix. Which projection of the S1S2 matrix is fitted, its
    binning, and the counting statistic all come from ``settings``.

    Parameters
    ----------
    fit : chisurf.core.fitting.fit.Fit
        Fit carrying the experimental ``data.pda`` metadata.
    pda_obj : tttrlib.Pda
        Engine holding the current model S1S2 matrix.
    nuisance : optional
        Group supplying the ``nPh_min`` / ``nPh_max`` photon-number gating.
    kw_hist : dict, optional
        Legacy histogram-settings dict, used when ``settings`` is ``None``
        and the model carries no ``fit_settings``.
    settings : PdaFitSettings, optional
        Axis / binning / statistic to fit with. Defaults to the model's
        ``fit_settings``.

    Returns
    -------
    numpy.ndarray
        Weighted residuals over the 1D histogram bins.
    """
    pda_meta = getattr(fit.data, "pda", None)
    if not isinstance(pda_meta, dict):
        return np.zeros(0, dtype=np.float64)
    s1s2_experimental = pda_meta.get("s1s2")
    if s1s2_experimental is None:
        return np.zeros(0, dtype=np.float64)

    if settings is None:
        settings = resolve_fit_settings(getattr(fit, "model", None), kw_hist)
    kw_hist = settings.kw_hist
    pda_obj.histogram_function = build_pda_histogram_function(
        getattr(fit, "model", None), settings.axis
    )

    try:
        s1s2_model = np.asarray(pda_obj.get_S1S2_matrix(), dtype=float)
        s1s2_data = np.asarray(s1s2_experimental, dtype=float)

        try:
            shp = pda_meta.get("shape")
            if shp is not None and len(shp) == 2:
                ny, nx = int(shp[0]), int(shp[1])
                s1s2_model = s1s2_model[:ny, :nx]
                s1s2_data = s1s2_data[:ny, :nx]
        except Exception:
            pass

        # Effective photon-number bounds used for gating (0, 0 => disabled).
        gating_nmin = 0
        gating_nmax = 0

        # Apply photon-number gating (nPh_min/nPh_max) if a nuisance group is
        # provided. This mirrors the logic used in the PDA distance model so
        # that 1D projections respect the same N-range as the 2D residuals.
        try:
            if nuisance is not None:
                row_indices = np.asarray(pda_meta.get("row_indices"), dtype=np.int64)
                col_indices = np.asarray(pda_meta.get("col_indices"), dtype=np.int64)
                if row_indices.size and col_indices.size and row_indices.size == col_indices.size:
                    pda_nmin = int(pda_meta.get("minimum_number_of_photons", 0) or 0)
                    pda_nmax = int(pda_meta.get("maximum_number_of_photons", 0) or 0)
                    try:
                        nmin_param = int(round(float(nuisance.nPh_min)))
                    except Exception:
                        nmin_param = 0
                    try:
                        nmax_param = int(round(float(nuisance.nPh_max)))
                    except Exception:
                        nmax_param = 0
                    if nmin_param != 0 or nmax_param != 0:
                        nmin = nmin_param if nmin_param > 0 else pda_nmin
                        nmax = nmax_param if nmax_param > 0 else pda_nmax
                        if nmax >= nmin:
                            gating_nmin = nmin
                            gating_nmax = nmax
                            shp2 = getattr(s1s2_data, "shape", None)
                            if shp2 is not None and len(shp2) == 2:
                                ny2, nx2 = int(shp2[0]), int(shp2[1])
                                data_obj = getattr(fit, "data", None)
                                key = (
                                    id(pda_meta),
                                    int(ny2),
                                    int(nx2),
                                    int(nmin),
                                    int(nmax),
                                )
                                mask2d = None
                                try:
                                    cache_key = getattr(data_obj, "_pda_1d_mask2d_key", None)
                                    cache_mask = getattr(data_obj, "_pda_1d_mask2d", None)
                                except Exception:
                                    cache_key = None
                                    cache_mask = None
                                if cache_mask is not None and cache_key == key:
                                    mask2d = cache_mask
                                else:
                                    mask2d = np.zeros((ny2, nx2), dtype=bool)
                                    N = row_indices + col_indices
                                    sel = (N >= nmin) & (N <= nmax)
                                    if np.any(sel):
                                        mask2d[row_indices[sel], col_indices[sel]] = True
                                    try:
                                        data_obj._pda_1d_mask2d = mask2d
                                        data_obj._pda_1d_mask2d_key = key
                                    except Exception:
                                        pass
                                if mask2d is not None:
                                    s1s2_model = np.where(mask2d, s1s2_model, 0.0)
                                    s1s2_data = np.where(mask2d, s1s2_data, 0.0)
        except Exception:
            pass

        s1s2_model = s1s2_model.flatten()
        s1s2_data = s1s2_data.flatten()

        # Experimental 1D histogram depends only on the experimental S1S2
        # matrix, histogram settings, and photon-number gating. Cache it on the
        # data object so it is not recomputed on every model evaluation.
        data_obj = getattr(fit, "data", None)
        try:
            hist_cache_key = getattr(data_obj, "_pda_1d_hist_key", None)
            hist_cache_val = getattr(data_obj, "_pda_1d_hist", None)
        except Exception:
            hist_cache_key = None
            hist_cache_val = None

        eff_nmin = int(gating_nmin)
        eff_nmax = int(gating_nmax)
        # The corrected axes bin through gamma and R0, so a change in either
        # re-bins the *data* histogram too and has to invalidate the cache.
        model_obj = getattr(fit, "model", None)
        axis_signature = (settings.axis,)
        if settings.axis in ("E", "R"):
            axis_signature = (
                settings.axis,
                float(getattr(getattr(model_obj, "nuisance", None), "gamma", 1.0) or 1.0),
                float(
                    getattr(
                        getattr(model_obj, "fret_parameters", None), "forster_radius", 52.0
                    )
                    or 52.0
                ),
            )
        hist_key = (
            id(pda_meta),
            int(s1s2_data.size),
            # Content signature so the cached data histogram invalidates when the
            # experimental S1S2 is replaced in place (id + size alone are stable
            # across an in-place edit / a new dataset loaded into the same object).
            hash(s1s2_data.tobytes()),
            eff_nmin,
            eff_nmax,
            axis_signature,
            int(kw_hist.get("n_bins", 81)),
            float(kw_hist.get("x_min", 0.0)),
            float(kw_hist.get("x_max", 1.0)),
            bool(kw_hist.get("log_x", False)),
            int(kw_hist.get("n_min", 10)),
        )

        if hist_cache_val is not None and hist_cache_key == hist_key:
            data_x, data_y = hist_cache_val
        else:
            data_x, data_y = pda_obj.get_1dhistogram(
                s1s2=s1s2_data,
                **kw_hist,
            )
            try:
                data_obj._pda_1d_hist_key = hist_key
                data_obj._pda_1d_hist = (
                    np.asarray(data_x, dtype=float),
                    np.asarray(data_y, dtype=float),
                )
            except Exception:
                pass

        # Model histogram is recomputed for each evaluation since the PDA
        # probability spectrum changes during fitting.
        model_x, model_y = pda_obj.get_1dhistogram(
            s1s2=s1s2_model,
            **kw_hist,
        )
    except Exception:
        return np.zeros(0, dtype=np.float64)

    try:
        # The model S1S2 matrix is a normalised probability distribution (sum ~1)
        # while the experimental data is in counts, so the model 1D histogram must
        # be scaled to the data's total counts before forming the residual —
        # otherwise the model term is ~0 and chi2 collapses to a mean-independent
        # sum(data) offset (flat, mis-scaled surface). `pda_weighted_residuals`
        # does that rescaling; it mirrors the count-normalisation `update_model`
        # applies to the display curve.
        return pda_weighted_residuals(data_y, model_y, statistic=settings.statistic)
    except Exception:
        return np.zeros(0, dtype=np.float64)
