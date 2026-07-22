"""Typed harness around tttrlib's ``fit2x`` maximum-likelihood estimators.

tttrlib ships the canonical single-molecule / burst lifetime estimators
``Fit23``/``Fit24``/``Fit25``/``Fit26``.  They minimise the Poisson maximum-
likelihood statistic ``2I*`` (Maus et al., *Anal. Chem.* 2001) rather than a
least-squares chi-square and are the correct estimators in the low-photon
regime of burst-wise and pixel-wise fluorescence analysis.

Historically every ChiSurf consumer (the burst-MLE wizard, its multiprocessing
worker, and the pixel/molecule image-MLE plugins) constructed and called the
raw tttrlib fitter itself, duplicating the same construction and result-parsing
boilerplate.  This module is the single, tested seam around ``fit2x``:

* :class:`Fit2xSettings` -- the acquisition/instrument description shared by a
  batch of fits (channel width, IRF, background, polarisation corrections).
* :class:`Fit2x` -- a reusable fitter that builds the underlying tttrlib object
  once and fits many decays through :meth:`Fit2x.fit`.
* :class:`Fit2xResult` -- a typed result with named parameter accessors.
* :func:`assemble_vv_vh` -- stack parallel/perpendicular histograms into the
  "VV/VH" layout every ``fit2x`` estimator expects.

The module imports tttrlib lazily so that importing ChiSurf without a working
tttrlib build does not fail; :data:`HAVE_TTTRLIB` reports availability.
"""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Sequence

import numpy as np

try:  # tttrlib is an optional-at-import compiled dependency
    import tttrlib

    HAVE_TTTRLIB = True
except Exception:  # pragma: no cover - exercised only without tttrlib
    tttrlib = None
    HAVE_TTTRLIB = False


class Fit2xModel(str, enum.Enum):
    """The ``fit2x`` estimator family.

    Attributes
    ----------
    FIT23
        Single fluorescence lifetime with anisotropy; free parameters
        ``[tau, gamma, r0, rho]``.
    FIT24
        Bi-exponential decay; free parameters
        ``[tau1, gamma, tau2, A2, offset]``.
    FIT25
        Lifetime selection out of four fixed candidates; parameters
        ``[tau1, tau2, tau3, tau4, gamma]`` (the best-describing lifetime is
        returned in ``x[0]``).
    """

    FIT23 = "fit23"
    FIT24 = "fit24"
    FIT25 = "fit25"


#: Ordered names of the *free* input parameters accepted by each estimator.
PARAMETER_NAMES: dict[Fit2xModel, tuple[str, ...]] = {
    Fit2xModel.FIT23: ("tau", "gamma", "r0", "rho"),
    Fit2xModel.FIT24: ("tau1", "gamma", "tau2", "A2", "offset"),
    Fit2xModel.FIT25: ("tau1", "tau2", "tau3", "tau4", "gamma"),
}

_TTTRLIB_CLASS: dict[Fit2xModel, str] = {
    Fit2xModel.FIT23: "Fit23",
    Fit2xModel.FIT24: "Fit24",
    Fit2xModel.FIT25: "Fit25",
}

#: Full packed start-vector layout for the batch ``DecayFitNN.fit_matrix`` of the
#: non-fit23 estimators. ``fit23`` keeps its own ``fit_matrix`` signature (the
#: BIFL/P+2S flags are separate arguments there); the others take the flags
#: inside the parameter vector, so ``fit_many`` packs them here.
#: value = (x_width, n_free_params, bifl_flag_index, {extra_input_index: default})
_BATCH_LAYOUT: dict[Fit2xModel, tuple[int, int, int, dict[int, float]]] = {
    # x = [tau1, gamma, tau2, A2, offset, bifl, r_scat, r_exp]
    Fit2xModel.FIT24: (8, 5, 5, {}),
    # x = [tau1, tau2, tau3, tau4, gamma, r0, bifl, r_scat, r_exp]
    Fit2xModel.FIT25: (9, 5, 6, {5: 0.38}),
}


def assemble_vv_vh(parallel: np.ndarray, perpendicular: np.ndarray) -> np.ndarray:
    """Stack two detection channels into the ``fit2x`` "VV/VH" layout.

    Every ``fit2x`` estimator expects a single 1-D counting histogram in which
    the parallel (VV) channel is directly followed by the perpendicular (VH)
    channel.  Both channels must have the same number of micro-time bins.

    Parameters
    ----------
    parallel, perpendicular : numpy.ndarray
        Micro-time counting histograms of equal length ``n`` for the parallel
        and perpendicular detection channels.

    Returns
    -------
    numpy.ndarray
        A ``float64`` array of length ``2 * n`` (``[parallel, perpendicular]``).

    Raises
    ------
    ValueError
        If the two channels differ in length.
    """
    p = np.ascontiguousarray(parallel, dtype=np.float64)
    s = np.ascontiguousarray(perpendicular, dtype=np.float64)
    if p.shape != s.shape:
        raise ValueError(f"parallel/perpendicular length mismatch: {p.shape} vs {s.shape}")
    return np.concatenate((p, s))


@dataclasses.dataclass
class Fit2xSettings:
    """Instrument/acquisition description shared by a batch of ``fit2x`` fits.

    Parameters
    ----------
    dt : float
        Width of a single micro-time channel (nanoseconds).
    period : float
        Excitation period of the light source (nanoseconds).
    irf : numpy.ndarray
        Instrument-response counting histogram in VV/VH layout (length ``2*n``).
    background : numpy.ndarray, optional
        Background counting histogram in VV/VH layout (length ``2*n``).  If
        omitted a zero background of the correct length is used.
    g_factor : float, optional
        Polarisation ``G`` factor (detection-efficiency ratio VV/VH).
    l1, l2 : float, optional
        Polarisation mixing corrections of the objective.
    convolution_stop : int, optional
        Last micro-time channel included in the IRF convolution.  When omitted
        the tttrlib default (half the array length) is used.
    p2s_twoIstar : bool, optional
        Optimise ``P + 2S`` instead of ``P`` and ``S`` individually.
    soft_bifl_scatter : bool, optional
        Reduce ``Istar`` by the background contribution ("soft" BIFL scatter).
    """

    dt: float
    period: float
    irf: np.ndarray
    background: np.ndarray | None = None
    g_factor: float = 1.0
    l1: float = 0.0
    l2: float = 0.0
    convolution_stop: int | None = None
    p2s_twoIstar: bool = False
    soft_bifl_scatter: bool = False

    def __post_init__(self) -> None:
        """Coerce arrays to contiguous ``float64`` and validate their shapes."""
        self.irf = np.ascontiguousarray(self.irf, dtype=np.float64)
        if self.irf.ndim != 1 or self.irf.size % 2 != 0:
            raise ValueError(
                "irf must be a 1-D VV/VH histogram of even length (2*n); "
                f"got shape {self.irf.shape}"
            )
        if self.background is None:
            self.background = np.zeros_like(self.irf)
        else:
            self.background = np.ascontiguousarray(self.background, dtype=np.float64)
            if self.background.shape != self.irf.shape:
                raise ValueError(
                    f"background length must match irf: {self.background.shape} vs {self.irf.shape}"
                )
            # Area-normalise the background so gamma is a true 0..1 fraction.
            #
            # The fit2x models add the background as ``bg[i] * gamma`` — gamma is
            # the *fraction* of the model that is background, which only holds if
            # the background pattern has unit area. Callers hand us extracted
            # photon histograms summing to thousands of counts; a raw pattern
            # makes gamma an enormous multiplier, so any gamma > 0 blows the model
            # amplitude up by ~sum(bg) and a free-gamma fit diverges to gamma≈1.
            # Normalising here fixes every consumer of this facade at once (the
            # burst batch run and the pixel-/molecule-wise imaging fits); the
            # tttrlib model is left untouched because it is the cross-language
            # reference contract. See okf/subsystems/fluorescence-domain.md.
            bg_sum = float(self.background.sum())
            if bg_sum > 0.0:
                self.background = self.background / bg_sum

    @property
    def n_channels(self) -> int:
        """Number of micro-time channels per detection channel (``n``)."""
        return self.irf.size // 2


@dataclasses.dataclass
class Fit2xResult:
    """Typed result of a single ``fit2x`` maximum-likelihood fit.

    Attributes
    ----------
    model_kind : Fit2xModel
        Which estimator produced this result.
    x : numpy.ndarray
        Full optimised parameter vector as returned by tttrlib.  The leading
        entries follow :data:`PARAMETER_NAMES`; trailing entries hold derived
        quantities (for ``fit23``: ``x[6]`` = scatter anisotropy ``r_scatter``,
        ``x[7]`` = experimental anisotropy ``r_experimental``).
    twoIstar : float
        The ``2I*`` maximum-likelihood goodness-of-fit statistic (lower is
        better; ``~1`` per degree of freedom indicates a good fit).
    fixed : numpy.ndarray
        The fixed-parameter mask that was applied.
    model_curve : numpy.ndarray or None
        The realised model histogram when ``include_model=True`` was requested.
    """

    model_kind: Fit2xModel
    x: np.ndarray
    twoIstar: float
    fixed: np.ndarray
    model_curve: np.ndarray | None = None

    def as_dict(self) -> dict[str, float]:
        """Return the named free parameters as a ``{name: value}`` mapping."""
        names = PARAMETER_NAMES[self.model_kind]
        return {name: float(self.x[i]) for i, name in enumerate(names)}

    # -- convenience accessors shared across the family -----------------------
    @property
    def tau(self) -> float:
        """Best-describing fluorescence lifetime (ns).

        For ``fit23``/``fit25`` this is ``x[0]``; for ``fit24`` it is the first
        lifetime ``tau1`` (``x[0]``).
        """
        return float(self.x[0])

    @property
    def gamma(self) -> float:
        """Scattered/background fraction of the fit."""
        idx = 4 if self.model_kind is Fit2xModel.FIT25 else 1
        return float(self.x[idx])

    @property
    def r_scatter(self) -> float:
        """Scatter anisotropy (``fit23`` only; NaN otherwise)."""
        if self.model_kind is Fit2xModel.FIT23 and self.x.size > 6:
            return float(self.x[6])
        return float("nan")

    @property
    def r_experimental(self) -> float:
        """Experimental (steady-state) anisotropy (``fit23`` only; NaN otherwise)."""
        if self.model_kind is Fit2xModel.FIT23 and self.x.size > 7:
            return float(self.x[7])
        return float("nan")


class Fit2x:
    """A reusable ``fit2x`` maximum-likelihood lifetime estimator.

    The underlying tttrlib fitter is built once from :class:`Fit2xSettings`
    and reused for every :meth:`fit` call, which is the performance-critical
    path when fitting thousands of bursts or image pixels.

    Parameters
    ----------
    settings : Fit2xSettings
        Instrument/acquisition description.
    model : Fit2xModel, optional
        Estimator to use (default :attr:`Fit2xModel.FIT23`).

    Raises
    ------
    RuntimeError
        If tttrlib is not importable in this environment.
    """

    def __init__(
        self,
        settings: Fit2xSettings,
        model: Fit2xModel = Fit2xModel.FIT23,
    ) -> None:
        if not HAVE_TTTRLIB:
            raise RuntimeError(
                "tttrlib is required for maximum-likelihood (fit2x) fitting but "
                "could not be imported."
            )
        self.settings = settings
        self.model = Fit2xModel(model)
        cls = getattr(tttrlib, _TTTRLIB_CLASS[self.model])
        kwargs = dict(
            dt=settings.dt,
            irf=settings.irf,
            background=settings.background,
            period=settings.period,
            g_factor=settings.g_factor,
            l1=settings.l1,
            l2=settings.l2,
            p2s_twoIstar_flag=settings.p2s_twoIstar,
            soft_bifl_scatter_flag=settings.soft_bifl_scatter,
        )
        if settings.convolution_stop is not None:
            kwargs["convolution_stop"] = int(settings.convolution_stop)
        self._fitter = cls(**kwargs)

    @property
    def n_channels(self) -> int:
        """Number of micro-time channels per detection channel."""
        return self.settings.n_channels

    @property
    def parameter_names(self) -> tuple[str, ...]:
        """Ordered names of the free input parameters for this estimator."""
        return PARAMETER_NAMES[self.model]

    def fit(
        self,
        data: np.ndarray,
        initial_values: Sequence[float],
        fixed: Sequence[int] | None = None,
        include_model: bool = False,
    ) -> Fit2xResult:
        """Fit one VV/VH-format decay histogram by maximum likelihood.

        Parameters
        ----------
        data : numpy.ndarray
            Experimental counting histogram in VV/VH layout (length ``2*n``).
            Use :func:`assemble_vv_vh` to build it from two channels.
        initial_values : sequence of float
            Initial values of the free parameters, ordered as
            :attr:`parameter_names`.
        fixed : sequence of int, optional
            Per-parameter fix mask (``1`` = fixed, ``0`` = optimised), same
            length as ``initial_values``.  Defaults to all-free.
        include_model : bool, optional
            When *True*, the realised model histogram is returned in
            :attr:`Fit2xResult.model_curve`.

        Returns
        -------
        Fit2xResult
            The optimised parameters and ``2I*`` goodness of fit.
        """
        x0 = np.ascontiguousarray(initial_values, dtype=np.float64)
        if fixed is None:
            fixed_arr = np.zeros(x0.size, dtype=np.int16)
        else:
            fixed_arr = np.ascontiguousarray(fixed, dtype=np.int16)
        data_arr = np.ascontiguousarray(data, dtype=np.float64)
        res = self._fitter(
            data=data_arr,
            initial_values=x0,
            fixed=fixed_arr,
            include_model=include_model,
        )
        return Fit2xResult(
            model_kind=self.model,
            x=np.asarray(res["x"], dtype=np.float64),
            twoIstar=float(res.get("twoIstar", float("nan"))),
            fixed=np.asarray(res.get("fixed", fixed_arr), dtype=np.int16),
            model_curve=(
                np.asarray(res["model"], dtype=np.float64)
                if include_model and "model" in res
                else None
            ),
        )

    __call__ = fit

    def fit_many(
        self,
        data: np.ndarray,
        initial_values: Sequence[float],
        fixed: Sequence[int] | None = None,
    ) -> np.ndarray:
        """Fit a whole matrix of decays in one GIL-released C++ call.

        Every row of ``data`` is fitted from the same start values, looping in
        C++ with the Python GIL released for the *whole* batch — so several
        threads each calling ``fit_many`` on a chunk run in true parallel
        (unlike per-row :meth:`fit`, whose per-call GIL handoff does not scale).

        Supported for ``fit23``, ``fit24`` and ``fit25`` (every estimator that
        exposes a native ``fit_matrix`` batch kernel).

        Parameters
        ----------
        data : numpy.ndarray
            ``(n_rows, 2*n_channels)`` matrix of VV/VH-format histograms.
        initial_values : sequence of float
            Shared start values for every row — the free parameters named in
            :data:`PARAMETER_NAMES` for this estimator (``[tau, gamma, r0, rho]``
            for fit23; ``[tau1, gamma, tau2, A2, offset]`` for fit24;
            ``[tau1, tau2, tau3, tau4, gamma]`` for fit25).
        fixed : sequence of int, optional
            Per-parameter fix mask applied to every row (default all-free).

        Returns
        -------
        numpy.ndarray
            ``(n_rows, n_free + 1)`` array of the fitted free parameters followed
            by the ``2I*`` fit quality per row.

        Raises
        ------
        NotImplementedError
            If the estimator has no native batch kernel.
        """
        data_arr = np.ascontiguousarray(data, dtype=np.float64)
        if data_arr.ndim != 2:
            raise ValueError("data must be a 2-D (n_rows, 2*n_channels) matrix")
        x0_free = np.ascontiguousarray(initial_values, dtype=np.float64)

        # fit23 keeps its dedicated fit_matrix (BIFL/P+2S flags are separate
        # arguments, and it has the tau-only fast path).
        if self.model is Fit2xModel.FIT23:
            fixed_arr = (
                np.zeros(x0_free.size, dtype=np.int16)
                if fixed is None
                else np.ascontiguousarray(fixed, dtype=np.int16)
            )
            out = np.empty((data_arr.shape[0], 5), dtype=np.float64)
            tttrlib.DecayFit23.fit_matrix(
                data_arr, x0_free, fixed_arr,
                float(self._fitter._bifl_scatter),
                float(self._fitter._p_2s_flag),
                self._fitter._m_param, out,
            )
            return out

        layout = _BATCH_LAYOUT.get(self.model)
        if layout is None:
            raise NotImplementedError(
                f"batch fit_many has no native kernel for {self.model.value}"
            )
        x_width, n_free, bifl_index, extras = layout
        # Pack the shared start vector: free params, estimator-specific input
        # slots (e.g. fit25's r0), then the BIFL-scatter flag the fitter carries.
        x0 = np.zeros(x_width, dtype=np.float64)
        x0[:n_free] = x0_free[:n_free]
        for index, value in extras.items():
            x0[index] = value
        x0[bifl_index] = float(self._fitter._bifl_scatter)
        fixed_arr = (
            np.zeros(n_free, dtype=np.int16)
            if fixed is None
            else np.ascontiguousarray(fixed, dtype=np.int16)
        )
        out = np.empty((data_arr.shape[0], n_free + 1), dtype=np.float64)
        decay_cls = getattr(tttrlib, "Decay" + _TTTRLIB_CLASS[self.model])
        decay_cls.fit_matrix(data_arr, x0, fixed_arr, self._fitter._m_param, out)
        return out
