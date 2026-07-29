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

#: Fundamental anisotropy used for ``fit25``, which takes ``r0`` as a fixed input
#: rather than a fitted parameter.
_FIT25_R0 = 0.38

# There is deliberately no model-to-class table and no packed-vector layout here
# any more. Both used to be necessary because each estimator was its own class
# with its own arrangement of parameters, setup flags and outputs inside one
# array; tttrlib now describes all of that in its registry, so this module asks
# for a fit by name and lets ``setup_vector``/``result_names`` say what the slots
# mean. Re-introducing a table here would re-introduce the drift it caused.


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
        The optimised parameters, and only those, ordered as
        :data:`PARAMETER_NAMES`.  Derived quantities used to share this array —
        ``x[6]`` and ``x[7]`` held anisotropies for ``fit23`` — which meant every
        caller had to know a per-estimator layout.  They now live in
        :attr:`results` under the names tttrlib publishes.
    results : numpy.ndarray
        The fit's result columns, named by :attr:`result_names`.  Every
        estimator reports at least ``twoIstar``, ``converged`` and
        ``iterations``.
    result_names : tuple of str
        Column names of :attr:`results`, taken from the tttrlib registry.
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
    results: np.ndarray = dataclasses.field(default_factory=lambda: np.empty(0))
    result_names: tuple[str, ...] = ()
    model_curve: np.ndarray | None = None

    def result(self, name: str, default: float = float("nan")) -> float:
        """Return a named result column, or ``default`` when absent.

        Estimators publish different columns — only ``fit25`` reports
        ``selected_index``, only the polarisation-resolved ones report
        anisotropies — so asking by name keeps a caller working across models.
        """
        try:
            return float(self.results[self.result_names.index(name)])
        except (ValueError, IndexError):
            return default

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
        """Scatter-corrected steady-state anisotropy (NaN when not reported)."""
        return self.result("r_scatter")

    @property
    def r_experimental(self) -> float:
        """Experimental (steady-state) anisotropy (NaN when not reported)."""
        return self.result("r_experimental")

    @property
    def converged(self) -> bool:
        """Whether the optimiser met its tolerance rather than hitting a limit.

        Note this does *not* mean the answer is meaningful: a lifetime pushed
        against the excitation period converges onto that bound and still reports
        ``True``, so compare :attr:`tau` against the period when it looks large.
        """
        return bool(self.result("converged", 0.0))


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

        name = self.model.value
        setup_kwargs = dict(
            dt=settings.dt,
            period=settings.period,
            g_factor=settings.g_factor,
            l1=settings.l1,
            l2=settings.l2,
            soft_bifl_scatter_flag=settings.soft_bifl_scatter,
            objective="p2s_mle" if settings.p2s_twoIstar else "poisson_mle",
        )
        if settings.convolution_stop is not None:
            setup_kwargs["convolution_stop"] = int(settings.convolution_stop)

        irf = np.ascontiguousarray(settings.irf, dtype=np.float64)
        background = np.ascontiguousarray(settings.background, dtype=np.float64)

        # The model is immutable and caches what it derives from the IRF, so it
        # is built once here and shared by every fit; only the problem carries
        # per-fit state.
        self._fit = tttrlib.DecayFit2(
            name, tttrlib.setup_vector(name, **setup_kwargs), irf.tolist())
        self._problem = tttrlib.DecayFitProblem(2, settings.n_channels, settings.dt)
        self._problem.irf = tttrlib.VectorDouble(irf.tolist())
        self._problem.background = tttrlib.VectorDouble(background.tolist())
        self._n_parameters = self._fit.n_parameters(self._problem)
        self._result_names = tuple(tttrlib.result_names(name))

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
        fixed_arr = (
            np.zeros(x0.size, dtype=np.int16)
            if fixed is None
            else np.ascontiguousarray(fixed, dtype=np.int16)
        )
        data_arr = np.ascontiguousarray(data, dtype=np.float64)
        self._problem.data = tttrlib.VectorDouble(data_arr.ravel().tolist())

        out = self._fit.fit(
            self._parameters(x0), self._constraints(fixed_arr), self._problem)

        return Fit2xResult(
            model_kind=self.model,
            x=np.asarray(out.parameters, dtype=np.float64),
            results=np.asarray(out.results, dtype=np.float64),
            result_names=self._result_names,
            twoIstar=float(out.objective),
            fixed=fixed_arr,
            model_curve=(
                np.asarray(self._problem.model, dtype=np.float64)
                if include_model
                else None
            ),
        )

    def _parameters(self, x0: np.ndarray) -> list[float]:
        """Pad the caller's free parameters out to the model's full vector.

        ``fit25`` is the only asymmetry: it takes ``r0`` as a fixed instrument
        constant rather than something a caller tunes, so it is supplied here
        rather than being demanded of every caller.
        """
        values = [float(v) for v in x0[: self._n_parameters]]
        while len(values) < self._n_parameters:
            values.append(
                _FIT25_R0 if self.model is Fit2xModel.FIT25 else 0.0)
        return values

    def _constraints(self, fixed_arr: np.ndarray):
        """Translate the fix mask into tttrlib's link vector.

        A parameter the caller did not mention is held: the vector may be longer
        than the mask (see :meth:`_parameters`), and inventing freedom for a slot
        nobody asked about is how ``r0`` would silently start being fitted.
        """
        codes = [
            -1 if (i >= fixed_arr.size or int(fixed_arr[i])) else 0
            for i in range(self._n_parameters)
        ]
        return tttrlib.DecayFitConstraints(tttrlib.VectorInt32(codes))

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

        Every estimator supports this: the batch loop is part of the fit
        interface rather than something each model had to provide, so there is no
        longer a set of "estimators with a native batch kernel" and a set without.

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
            ``(n_rows, n_parameters + 1)`` array of the fitted parameters
            followed by the ``2I*`` fit quality per row.
        """
        data_arr = np.ascontiguousarray(data, dtype=np.float64)
        if data_arr.ndim != 2:
            raise ValueError("data must be a 2-D (n_rows, 2*n_channels) matrix")
        x0_free = np.ascontiguousarray(initial_values, dtype=np.float64)
        fixed_arr = (
            np.zeros(x0_free.size, dtype=np.int16)
            if fixed is None
            else np.ascontiguousarray(fixed, dtype=np.int16)
        )

        batch = self._fit.fit_many(
            self._problem, data_arr.ravel().tolist(),
            int(data_arr.shape[0]), int(data_arr.shape[1]),
            self._parameters(x0_free), self._constraints(fixed_arr))

        n_rows = data_arr.shape[0]
        parameters = np.asarray(batch.parameters, dtype=np.float64).reshape(
            n_rows, self._n_parameters)
        # Report the parameters this facade *names*, which is not always all of
        # them: fit25's r0 is an instrument constant supplied by
        # :meth:`_parameters`, not something a caller passed in or can read back
        # by position. Returning it would shift every column a caller indexes by
        # :data:`PARAMETER_NAMES`.
        n_named = len(PARAMETER_NAMES[self.model])
        out = np.empty((n_rows, n_named + 1), dtype=np.float64)
        out[:, :n_named] = parameters[:, :n_named]
        out[:, n_named] = np.asarray(batch.objective, dtype=np.float64)
        return out
