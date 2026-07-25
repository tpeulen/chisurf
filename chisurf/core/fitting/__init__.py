from __future__ import annotations

import numpy as np

import chisurf.core.curve
import chisurf.logging


#: Selectable noise models for the fit objective.  ``"default"`` keeps the
#: historical behaviour (Gaussian/weighted-least-squares residuals divided by
#: the data error column, i.e. Neyman chi-square for ``sqrt(counts)`` errors).
#: ``"poisson"`` switches to the Poisson maximum-likelihood ``2I*`` objective.
NOISE_MODELS = ("default", "poisson")

#: Aliases accepted for :data:`NOISE_MODELS` on the ``Fit``/model level.
_NOISE_MODEL_ALIASES = {
    "": "default",
    "lsq": "default",
    "wls": "default",
    "neyman": "default",
    "gaussian": "default",
    "default": "default",
    "mle": "poisson",
    "2istar": "poisson",
    "poisson": "poisson",
}


def normalize_noise_model(noise_model: str) -> str:
    """Map a user-facing noise-model name onto a canonical :data:`NOISE_MODELS` value."""
    if noise_model is None:
        return "default"
    return _NOISE_MODEL_ALIASES.get(str(noise_model).strip().lower(), "default")


def deviance_residuals(
        data_y: np.ndarray,
        model_y: np.ndarray,
) -> np.ndarray:
    r"""Signed Poisson deviance residuals for a maximum-likelihood fit.

    Returns the per-bin signed square roots of the Baker & Cousins / ``2I*``
    likelihood-ratio deviance,

    .. math::

        r_i = \\operatorname{sign}(\\mu_i - y_i)\\,
              \\sqrt{2\\left[\\mu_i - y_i + y_i \\ln(y_i/\\mu_i)\\right]},

    with the convention :math:`y_i \\ln(y_i/\\mu_i) \\to 0` for :math:`y_i = 0`.
    Because :math:`\\sum_i r_i^2 = 2I^*`, feeding these residuals to the existing
    least-squares (Levenberg-Marquardt) engine minimises the Poisson maximum-
    likelihood objective without any change to the optimiser (Laurence & Chromy,
    *Nat. Methods* 2010).  This is the correct estimator for low photon counts,
    where the Neyman ``1/sqrt(counts)`` weighting is biased.

    Parameters
    ----------
    data_y : numpy.ndarray
        Measured counts :math:`y_i` (non-negative).
    model_y : numpy.ndarray
        Model-predicted expected counts :math:`\\mu_i` (should be positive).

    Returns
    -------
    numpy.ndarray
        Signed deviance residuals of the same length as the inputs.
    """
    y = np.asarray(data_y, dtype=np.float64)
    mu = np.asarray(model_y, dtype=np.float64)
    # The likelihood is only defined for mu > 0; floor to a tiny positive value
    # so that ln(mu) stays finite for empty model bins (a positive count against
    # a vanishing model then correctly incurs a large penalty).
    tiny = np.finfo(np.float64).tiny
    mu = np.clip(mu, tiny, None)
    # y * ln(y / mu), computed as y * (ln y - ln mu) to avoid overflow of the
    # ratio y/mu when mu is floored to ``tiny``; the y -> 0 limit (0 * -inf) is
    # handled explicitly by only taking the log where y > 0.
    pos = y > 0.0
    log_y = np.zeros_like(y)
    log_y[pos] = np.log(y[pos])
    ylog = np.where(pos, y * (log_y - np.log(mu)), 0.0)
    dev = 2.0 * (mu - y + ylog)
    # Guard tiny negatives from floating-point cancellation before the sqrt.
    dev = np.clip(dev, 0.0, None)
    return np.sign(mu - y) * np.sqrt(dev)


def calculate_weighted_residuals(
        data: chisurf.core.data.DataCurve,
        model: chisurf.core.curve.Curve,
        xmin: int,
        xmax: int,
        noise_model: str = "default",
) -> np.ndarray:
    """Calculate weighted residuals for a data curve and a model curve.

    Residuals are evaluated over the index range ``[xmin, xmax)``.
    For the ``"default"`` noise model the weighted residuals are
    ``(data - model) / weights`` where the weights are the data errors
    (weighted least squares / Neyman chi-square).  For the ``"poisson"``
    noise model the signed Poisson deviance residuals are returned instead
    (see :func:`deviance_residuals`), so that the fit minimises the ``2I*``
    maximum-likelihood objective -- the correct estimator for low counts.

    :param data: the experimental data
    :param model: the model
    :param xmin: minimum index
    :param xmax: maximum index
    :param noise_model: ``"default"`` (weighted least squares) or ``"poisson"``
        (maximum likelihood); aliases are resolved via
        :func:`normalize_noise_model`.
    :return: a numpy array containing the weighted residuals
    """
    model_x, model_y = model[xmin:xmax]
    data_sliced = data[xmin:xmax]
    data_x, data_y, _, data_y_error = data_sliced[:4]
    ml = min([len(model_y), len(data_y)])
    if normalize_noise_model(noise_model) == "poisson":
        return deviance_residuals(data_y[:ml], model_y[:ml])
    wr = np.array(
        (data_y[:ml] - model_y[:ml]) / data_y_error[:ml],
        dtype=np.float64
    )
    return wr


def find_fit_idx(
        fit: 'chisurf.core.fitting.fit.Fit',
        fits: list['chisurf.core.fitting.fit.Fit'] = None
) -> int | None:
    """Find the position of a fit in the global fit list.

    Only :class:`~chisurf.core.fitting.fit.FitGroup` instances are listed in
    ``chisurf.fits``; the member fits they contain are not. A member therefore
    resolves to the index of the **group holding it**, which is the index the
    action layer and the server RPC address a fit by -- a member that resolved
    to nothing would silently target no fit at all.

    Parameters
    ----------
    fit : Fit
        The fit to locate. May be a member of a grouped fit.
    fits : list of Fit, optional
        List of fits to search. Defaults to ``chisurf.fits``.

    Returns
    -------
    int or None
        Position of the fit -- or of the group containing it -- in ``fits``,
        or ``None`` if the fit is not part of the list at all.
    """
    if fits is None:
        fits = chisurf.fits
    for idx, f in enumerate(fits):
        if f is fit:
            return idx
    for idx, f in enumerate(fits):
        members = getattr(f, "grouped_fits", None)
        if not isinstance(members, (list, tuple)):
            continue
        for member in members:
            if member is fit:
                return idx
    return None


def find_fit_idx_of_parameter(
        parameter: 'chisurf.core.fitting.parameter.FittingParameter',
        fit_list: list['chisurf.core.fitting.fit.Fit'] = None
) -> list[int]:
    """Find indices of fits that contain a specific parameter.

    Parameters
    ----------
    parameter : FittingParameter
        The parameter to search for.
    fit_list : list of Fit, optional
        List of fits to search. Defaults to ``chisurf.fits``.

    Returns
    -------
    list of int
        Indices of fits whose model contains the parameter.
    """
    if fit_list is None:
        fit_list = chisurf.fits
    fit_idx = list()
    for idx, fit in enumerate(fit_list):
        models = []
        model = getattr(fit, "model", None)
        if model is not None:
            models.append(model)

        grouped_fits = getattr(fit, "grouped_fits", None)
        if isinstance(grouped_fits, (list, tuple)):
            for f_local in grouped_fits:
                m_local = getattr(f_local, "model", None)
                if m_local is not None and m_local not in models:
                    models.append(m_local)

        global_model = getattr(fit, "_model", None)
        if global_model is not None and global_model not in models:
            models.append(global_model)

        found = False
        for m in models:
            try:
                params = getattr(m, "parameters_all", [])
            except Exception:
                continue
            for p in params:
                # Primary: object identity
                if id(p) == id(parameter):
                    fit_idx.append(idx)
                    found = True
                    break
                # Secondary: port-object identity (stable across list rebuilds,
                # safe against cross-fit confusion unlike the old name match)
                try:
                    if id(p._port) == id(parameter._port):
                        fit_idx.append(idx)
                        found = True
                        break
                except AttributeError:
                    continue
            if found:
                break
    return fit_idx


def find_fit_idx_of_model(
        model: 'chisurf.core.models.Model',
        fits: list['chisurf.core.fitting.fit.Fit'] = None
) -> int:
    """Returns index of the fit of a model in chisurf.fits array

    :param model:
    :param fits:
    :return:
    """
    if fits is None:
        fits = chisurf.fits
    for idx, f in enumerate(fits):
        if f.model is model:
            return idx
