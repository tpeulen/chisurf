from __future__ import annotations

import chisurf as cs
import chisurf.logging
from chisurf import typing
from collections import deque

import contextlib
import inspect
import os
import re
import numpy as np
import scipy.linalg

import chisurf.core.settings
import chisurf.core.base
import chisurf.core.fio
import chisurf.core.curve
import chisurf.core.experiments
import chisurf.core.data
import chisurf.core.fitting.diagnostics
import chisurf.core.fitting.engine
import chisurf.core.fitting.factorgraph
import chisurf.core.fitting.minimizer
import chisurf.core.fitting.parameter
import chisurf.core.fitting.priors
import chisurf.core.fitting.sample
import chisurf.core.fitting.support_plane
import chisurf.core.models
import chisurf.core.math.statistics
import chisurf.core.math.optimization
from chisurf.core.math.optimization import OptimizationCancelled
import chisurf.core.fitting.sampling_meta
import time
import json


#: Relative accuracy assumed for the model function when the settings leave it
#: unset. MINPACK derives its forward-difference step as ``sqrt(epsfcn) * |x|``,
#: and ``epsfcn = 0`` means "use machine epsilon" -- a step of ~1.5e-8 relative,
#: far below the noise floor of a decay model whose convolution is recursive over
#: ~1024 channels. The Jacobian columns are then dominated by rounding noise and
#: the optimiser can fail to move the lifetimes at all. Over 88 randomised fits
#: across four independent conditions, fits reaching chi2r < 1.1 went 60/88 at
#: ``epsfcn = 0`` to 83/88 at this value.
DEFAULT_EPSFCN = 1.0e-6


def _leastsq_options(options: dict) -> dict:
    """Return ``options`` with a usable ``epsfcn``.

    The bundled default lives in ``settings_chisurf.yaml``, but user settings are
    copied to ``~/.chisurf`` once and **never refreshed**, so an existing install
    keeps whatever it was first given. Every such install carries the old
    ``epsfcn: 0``, which is precisely the broken value, so honouring it verbatim
    would leave the fix inert for exactly the people who already have the
    problem. Treat 0 (MINPACK's "pick for me") as unset and substitute
    :data:`DEFAULT_EPSFCN`; any explicit non-zero value is passed through, so a
    genuinely machine-epsilon step is still reachable by asking for one.
    """
    options = dict(options)
    try:
        if not float(options.get("epsfcn", 0.0)):
            options["epsfcn"] = DEFAULT_EPSFCN
    except (TypeError, ValueError):
        options["epsfcn"] = DEFAULT_EPSFCN
    return options


def _raw_fit_name(f) -> str:
    """Compute the base (non-unique) name for a Fit/FitGroup instance."""
    try:
        model = getattr(f, "model", None)
        model_cls = getattr(model, "__class__", None)
        model_name = getattr(model_cls, "name", None)
        if model_name is None:
            model_name = getattr(model_cls, "__name__", "no model")
    except Exception:
        model_name = "no model"

    try:
        data = getattr(f, "_data", None)
        data_name = getattr(data, "name", None)
    except Exception:
        data_name = None

    if not data_name:
        data_name = "no data"

    return f"{model_name} - {data_name}"


class _StagedProgress:
    """One progress bar shared by several optimisations run back to back.

    A :class:`FitGroup` runs each member fit and then the global fit, and each
    of those counts its own evaluations from zero. Passed straight through, the
    bar would fill and reset once per member. This maps stage *k* of *n* onto
    the sub-range ``[k/n, (k+1)/n)``, and never reports a fraction below one it
    has already reported -- a bar going backwards reads as a bug, whereas one
    that pauses only reads as slow.

    Parameters
    ----------
    callback : callable or None
        Sink called as ``callback(done, total)``. ``None`` makes every method a
        no-op, so callers need not branch.
    n_stages : int
        How many optimisations share the bar.
    """

    def __init__(self, callback, n_stages: int):
        self._callback = callback
        self.n_stages = max(1, int(n_stages))
        self._stage = 0
        self._reported = 0.0

    def stage(self, index: int):
        """Return the callback to hand to the *index*-th optimisation."""
        self._stage = max(0, min(self.n_stages - 1, int(index)))
        return None if self._callback is None else self._report

    def _report(self, done, total, **kwargs) -> None:
        """Map one stage's ``(done, total)`` onto the shared bar.

        ``chi2`` / ``chi2r`` are forwarded to the sink unchanged: they describe
        the stage that is running, and a group has no single objective to
        replace them with.
        """
        try:
            within = float(done) / float(total) if total else 0.0
        except (TypeError, ValueError, ZeroDivisionError):
            within = 0.0
        within = min(1.0, max(0.0, within))
        self._reported = max(self._reported, (self._stage + within) / self.n_stages)
        # The reported pair is a *fraction* in permille, not an evaluation
        # count -- the stages have no common unit -- so the stage is passed
        # alongside for a caller that labels its bar.
        value = int(round(1000.0 * self._reported))
        # Cancellation travels out through this call, so it is deliberately not
        # wrapped: swallowing here would leave a pressed Cancel button inert.
        try:
            self._callback(
                value, 1000, stage=self._stage + 1, n_stages=self.n_stages, **kwargs
            )
        except TypeError:
            self._callback(value, 1000)


class Fit(cs.core.base.Base):
    """Fit of a single data set with a single model.

    The :class:`Fit` object owns a :class:`cs.core.data.DataCurve` instance
    (accessible via :attr:`data`) and a :class:`cs.core.models.ModelCurve`
    instance (via :attr:`model`). It provides convenience properties for
    weighted residuals, chi² statistics, and running a local least-squares
    optimization.
    """

    #: Process-local progress sink, installed by :meth:`reporting_progress`.
    #:
    #: A caller that wants progress cannot simply pass a callback to
    #: :meth:`run`: the GUI reaches its fits through the JSON-RPC facade, and a
    #: Python callable does not cross that boundary -- the service calls
    #: ``fit.run()`` with no arguments. So the callback is attached to the *fit*
    #: rather than threaded through the call, which works whenever the caller
    #: and the fit are the same object (local and hybrid modes, i.e. the GUI)
    #: and is simply absent when they are not (a genuinely remote fit reports no
    #: progress rather than failing).
    #:
    #: It is a class attribute, so it never enters ``__dict__`` and never
    #: reaches :meth:`__getstate__` -- a live Qt closure must not be pickled
    #: into a saved fit.
    _progress_callback = None

    #: Whether the last :meth:`run` was stopped by the user. Cancellation
    #: travels *out* the same way progress travels in: raising through the RPC
    #: service turns it into a generic error result, indistinguishable from a
    #: real failure, so the fit records it and the caller reads it back.
    _last_run_cancelled = False

    @contextlib.contextmanager
    def reporting_progress(self, callback):
        """Report optimiser progress to *callback* for the duration of the block.

        Parameters
        ----------
        callback : callable or None
            Called as ``callback(evaluated, total)`` from inside the residual
            evaluations. ``None`` installs nothing, so a caller does not have to
            branch on whether it has a sink.

        Examples
        --------
        ::

            with fit.reporting_progress(on_progress):
                api.run_fit(fit_uid=fit.unique_identifier)
        """
        previous = self.__dict__.get("_progress_callback")
        self._progress_callback = callback
        try:
            yield self
        finally:
            if previous is None:
                self.__dict__.pop("_progress_callback", None)
            else:
                self._progress_callback = previous

    @property
    def last_run_cancelled(self) -> bool:
        """Whether the most recent :meth:`run` was cancelled by the user."""
        return bool(self._last_run_cancelled)

    @property
    def fit_idx(self) -> int | None:
        """Index of this fit in ``cs.fits``.

        A member of a :class:`FitGroup` is not listed in ``cs.fits`` itself and
        resolves to the index of its group, so a member fit can be addressed by
        index like any other fit.

        Returns
        -------
        int or None
            Position of the fit -- or of the group containing it -- in the
            global fit list, or ``None`` if the fit is not part of it.
        """
        return cs.core.fitting.find_fit_idx(self)

    @property
    def xmin(self) -> int:
        """Minimum index of the fitting range.

        Returns
        -------
        int
            Lower bound of the fitting range.
        """
        return self._xmin

    @xmin.setter
    def xmin(self, v: int):
        """Set the minimum index of the fitting range.

        Parameters
        ----------
        v : int
            Lower bound. Clamped to zero if negative.
        """
        self._xmin = max(0, v)
        cs.core.fitting.factorgraph.bump_window_version()

    @property
    def xmax(self) -> int:
        """Maximum index of the fitting range.

        Returns
        -------
        int
            Upper bound of the fitting range.
        """
        return self._xmax

    @xmax.setter
    def xmax(self, v: int):
        """Set the maximum index of the fitting range.

        Parameters
        ----------
        v : int
            Upper bound. Clamped to the data length minus one.
        """
        try:
            self._xmax = min(len(self.data.y) - 1, v)
        except AttributeError:
            self._xmax = v
        cs.core.fitting.factorgraph.bump_window_version()

    @property
    def data(self) -> cs.core.data.DataCurve:
        """Data curve being fitted.

        Returns
        -------
        cs.core.data.DataCurve
            The experimental data attached to this fit.
        """
        return self._data

    @data.setter
    def data(self, v: cs.core.data.DataCurve):
        """Set the data curve for this fit.

        Parameters
        ----------
        v : cs.core.data.DataCurve
            New data curve.
        """
        self._data = v

    @property
    def model(self) -> cs.core.models.ModelCurve:
        """Model curve used for fitting.

        Returns
        -------
        cs.core.models.ModelCurve
            The model instance associated with this fit.
        """
        return self._model

    @model.setter
    def model(
            self,
            model: typing.Union[
                cs.core.models.model.Model,
                typing.Type[cs.core.models.model.Model]
            ]
    ):
        """Attach a model, given either the class to build or a built instance.

        The getter returns an *instance*, so the setter has to accept one:
        ``fit.model = fit.model`` used to raise ``TypeError: issubclass() arg 1
        must be a class``, and so did every caller that built its model first
        (a global fit wiring two models to two fits, for example). A class is
        still accepted and instantiated on this fit, because that is how
        :meth:`__init__` and the model-selection GUI attach a model.

        An adopted instance is re-pointed at this fit: a model reads its data,
        range and weights through ``self.fit``, so one that still referenced
        another fit would silently compute the wrong curve.

        Parameters
        ----------
        model : Model or type
            A :class:`cs.core.models.Model` subclass to instantiate on this
            fit, or an already-built model instance to adopt. The bare class
            :class:`type` is :meth:`__init__`'s "no model asked for" default and
            leaves the current model alone -- :class:`FitGroup` relies on that,
            because its ``model`` property writes through to the selected member
            fit and its own ``__init__`` passes the default on. ``None``
            detaches the model.

        Raises
        ------
        TypeError
            If *model* is neither a model, a model class, nor a way of saying
            "no model".
        """
        if model is type:
            return
        if isinstance(model, cs.core.models.Model):
            model.fit = self
            self._model = model
        elif isinstance(model, type) and issubclass(model, cs.core.models.Model):
            self._model = model(self, **self._model_kw)
        elif model is None:
            self._model = None
        else:
            raise TypeError(
                f"a fit's model must be a Model or a Model subclass, "
                f"got {model!r}"
            )

    @property
    def weighted_residuals(self) -> cs.core.curve.Curve:
        """Weighted residuals within the current fit range.

        Returns
        -------
        cs.core.curve.Curve
            Curve whose y-values are ``(data - model) / weights``.
        """
        wres_x, _ = self.model[self.xmin:self.xmax]
        wres_y = self.model.weighted_residuals
        return cs.core.curve.Curve(
            x=wres_x,
            y=wres_y,
            copy_array=False
        )

    @property
    def autocorrelation(self):
        """Autocorrelation of the weighted residuals.

        Returns
        -------
        cs.core.curve.Curve
            Autocorrelation curve (excluding the zero-lag point).
        """
        wres = self.weighted_residuals
        return cs.core.curve.Curve(
            x=wres.x[1:],
            y=cs.core.math.signal.autocorr(wres.y)[1:],
            copy_array=False
        )

    @property
    def chi2(self) -> float:
        """Chi-squared statistic (non-reduced).

        Returns
        -------
        float
            Sum of squared weighted residuals.
        """
        return get_chi2(
            self.model.parameter_values,
            model=self.model,
            reduced=False
        )

    @property
    def chi2r(self) -> float:
        """Reduced chi-squared statistic.

        Returns
        -------
        float
            Chi-squared divided by degrees of freedom.
        """
        return get_chi2(list(), model=self.model)

    @property
    def durbin_watson(self) -> float:
        """Durbin-Watson statistic of the weighted residuals.

        Returns
        -------
        float
            Test statistic for autocorrelation in residuals.
        """
        return cs.core.math.statistics.durbin_watson(
            self.weighted_residuals.y
        )

    @property
    def name(self) -> str:
        """Return a human-readable, *globally unique* fit name.

        The base name is derived from the model class and attached data
        ("ModelName - DataName"). If multiple active fits share the same
        base name, a numeric suffix " (1)", " (2)", ... is appended based
        on the order of appearance in ``cs.fits``.
        """

        try:
            base_name = _raw_fit_name(self)
        except Exception:
            return "no name"

        # Try to enforce uniqueness across active fits tracked in cs.fits.
        # On any error we simply fall back to the base name.
        try:
            all_fits = []
            for fg in getattr(cs, "fits", []):
                if isinstance(fg, Fit):
                    grouped = getattr(fg, "grouped_fits", None)
                    if isinstance(grouped, (list, tuple)) and grouped:
                        # FitGroup: only add grouped_fits, not the FitGroup itself
                        for lf in grouped:
                            if isinstance(lf, Fit):
                                all_fits.append(lf)
                    else:
                        # Plain Fit: add directly
                        all_fits.append(fg)

            if not all_fits:
                return base_name

            # Collect all fits that share the same base name, using the
            # raw-name helper to avoid recursion via the name property.
            same_base = [f for f in all_fits if _raw_fit_name(f) == base_name]
            if not same_base:
                return base_name

            try:
                idx = same_base.index(self)
            except ValueError:
                # This fit is not registered in cs.fits; treat it as
                # a standalone instance without suffix.
                return base_name

            if idx == 0:
                # First fit with this base name keeps the plain name.
                return base_name

            # Subsequent fits with the same base name receive a numeric
            # suffix reflecting their order of appearance.
            return f"{base_name} ({idx})"
        except Exception:
            return base_name

    @property
    def fit_range(self) -> typing.Tuple[int, int]:
        """Current fitting range as ``(xmin, xmax)``.

        Returns
        -------
        tuple of int
            Lower and upper index of the fitting range.
        """
        return self.xmin, self.xmax

    @fit_range.setter
    def fit_range(self, v):
        """Set the fitting range and optionally a residual mask.

        Parameters
        ----------
        v : tuple of int
            Either a 2-tuple ``(xmin, xmax)`` for a simple range, or a
            4-tuple ``(xmin1, xmax1, xmin2, xmax2)`` for a two-region mask.
        """
        vals = tuple(int(x) for x in v)
        if len(vals) == 2:
            # Backwards-compatible 1D range: do not touch any existing mask.
            xmin1, xmax1 = vals
            self.xmin, self.xmax = xmin1, xmax1

            # Rebuild a simple 1D mask matching the fit range so that APIs
            # like ``cs.current_fit.fit_range = i, j`` also update the mask
            # used by residual-based tools and the Data table.
            try:
                y = getattr(self.data, "y", None)
                n = int(len(y)) if y is not None else 0
            except Exception:
                n = 0
            if n <= 0:
                self.mask = None
                return

            lb1 = max(0, int(xmin1))
            ub1 = max(lb1, min(int(xmax1), n))
            mask = np.zeros(n, dtype=float)
            if ub1 > lb1:
                mask[lb1:ub1] = 1.0
            self.mask = mask
            return
        if len(vals) != 4:
            raise ValueError("fit_range must be a 2- or 4-tuple of integers")

        xmin1, xmax1, xmin2, xmax2 = vals
        # Primary 1D range still defined by the first interval
        self.xmin, self.xmax = xmin1, xmax1

        # Build a 1D mask as the union of [xmin1, xmax1) and [xmin2, xmax2)
        # over the current data length.
        try:
            y = getattr(self.data, "y", None)
            n = int(len(y)) if y is not None else 0
        except Exception:
            n = 0
        if n <= 0:
            # No data: clear mask but keep the primary range assignment.
            self.mask = None
            return

        lb1 = max(0, int(xmin1))
        ub1 = max(lb1, min(int(xmax1), n))
        lb2 = max(0, int(xmin2))
        ub2 = max(lb2, min(int(xmax2), n))
        mask = np.zeros(n, dtype=float)
        if ub1 > lb1:
            mask[lb1:ub1] = 1.0
        if ub2 > lb2:
            mask[lb2:ub2] = 1.0
        self.mask = mask

    @property
    def mask(self):
        """Optional 1D mask or weights applied to weighted residuals.

        If *mask* is boolean, False entries are excluded (residuals set to 0
        effectively via a multiplicative 0/1 weight). If numeric, values are
        treated as multiplicative weights on the residuals.
        """

        return getattr(self, "_mask", None)

    @mask.setter
    def mask(self, v):
        """Set the mask or weights applied to weighted residuals.

        Parameters
        ----------
        v : array_like or None
            1D array of weights or boolean inclusion flags. ``None``
            clears the mask.
        """
        cs.core.fitting.factorgraph.bump_window_version()
        if v is None:
            self._mask = None
            return
        arr = np.asarray(v)
        if arr.ndim != 1:
            raise ValueError("fit.mask must be a 1D array or sequence")
        self._mask = arr

    @property
    def grad(self) -> np.array:
        """Approximate gradient of the residuals at current parameters.

        The step scales with each parameter and is floored at 1.0 --
        ``epsilon * max(|x_k|, 1)``. Passing the machine epsilon here, as
        this used to, made every step a no-op and the whole gradient zero.

        Taken over the graph in C++ when the model builds one, and by
        :func:`approx_grad` when it does not. The two are the same
        differences at the same step; only the side of the SWIG boundary
        differs.
        """
        over_the_graph = cs.core.fitting.minimizer.curvature_over_the_graph(
            self, self.model, what="jacobian")
        if over_the_graph is not None:
            return over_the_graph
        _, grad = approx_grad(
            self.model.parameter_values,
            self
        )
        return grad

    @property
    def covariance_matrix(self) -> typing.Tuple[np.array, typing.typing.List[int]]:
        """Approximate covariance matrix and indices of relevant parameters.

        The matrix is computed from numerical partial derivatives obtained
        via :func:`covariance_matrix`.
        """
        return covariance_matrix(self)

    @property
    def n_free(self) -> int:
        """Number of free (non-fixed, non-linked) parameters in the model."""
        return self.model.n_free


    def __init__(
            self,
            model_class: typing.Type[cs.core.models.Model] = type,
            data: cs.core.data.DataCurve = None,
            xmin: int = 0,
            xmax: int = 0,
            model_kw: typing.Dict = None,
            group: list = None,
            noise_model: str = "default",
            **kwargs
    ):
        """Create a :class:`Fit` with a given model class and data.

        Parameters
        ----------
        model_class : type
            Model class to instantiate, typically a subclass of
            :class:`cs.core.models.ModelCurve`.
        data : cs.core.data.DataCurve, optional
            Data to be fitted. If omitted, a dummy ramp is used.
        xmin, xmax : int, optional
            Initial fitting range indices.
        model_kw : dict, optional
            Keyword arguments forwarded to the model constructor.
        group : list, optional
            Optional list used to collect multiple :class:`Fit` instances
            into a :class:`FitGroup`.
        noise_model : {"default", "poisson"}, optional
            Objective/estimator used by the fit. ``"default"`` uses weighted
            least squares (Neyman chi-square from the data error column);
            ``"poisson"`` uses the ``2I*`` maximum-likelihood deviance, the
            correct estimator for low photon counts.
        """
        super().__init__(**kwargs)
        self.noise_model = cs.core.fitting.normalize_noise_model(noise_model)
        self._model: cs.core.models.Model = None
        self._result_current = 0
        self.results = deque(maxlen=500)
        self._mask = None
        if data is None:
            data = cs.core.data.DataCurve(
                x=np.arange(10),
                y=np.arange(10)
            )
        self._data = data
        self.plots = list()
        self._xmin, self._xmax = xmin, xmax
        cs.core.fitting.factorgraph.bump_window_version()
        if model_kw is None:
            model_kw = {}
        self._model_kw = model_kw
        # Store the group reference before creating the model
        if isinstance(group, list):
            self.group = group
            self.group.append(self)
        self.model = model_class

    def __getstate__(self):
        """Custom pickling state with removable unpickleable attributes.

        Returns
        -------
        dict
            Serialized state including data and sanitized model state.
        """
        d = super().__getstate__()

        # Try to pickle model; remove unpickleable attributes
        model_state = self.model.__getstate__()
        import pickle
        # Attempt to pickle each attribute
        for key in list(model_state.keys()):  # Use list to avoid modifying dict while iterating
            try:
                pickle.dumps(model_state[key])  # Try pickling the attribute
            except (pickle.PicklingError, TypeError):
                # Remove unpickleable attributes
                del model_state[key]

        d['data'] = self.data.__getstate__()
        d['model'] = model_state
        return d

    def __setstate__(self, state):
        """Restore fit state from a pickled representation.

        Parameters
        ----------
        state : dict
            State dictionary produced by :meth:`__getstate__`.
        """
        m = state.pop('model')
        d = state.pop('data')
        self.model.__setstate__(m)
        self.data.__setstate__(d)
        super().__init__(**state)
        self.model.finalize()
        self.update()

    def get_state(self) -> dict:
        """Return a JSON-serializable snapshot of this fit's model state.

        By default this delegates to :meth:`model.get_state` so that the
        underlying model (and any nested parameter groups) control how their
        state is serialized.
        """

        model = getattr(self, "model", None)
        get_state = getattr(model, "get_state", None)
        if callable(get_state):
            try:
                return get_state()
            except Exception:
                return {}
        return {}

    def set_state(self, state: dict) -> None:
        """Restore model state from :meth:`get_state` output.

        The provided ``state`` must be a dictionary produced by
        :meth:`get_state` above. This updates parameter values, bounds,
        fixed flags, links and any registered model-specific extras (e.g.
        TCSPC IRF/linearization) but does not change the data object.
        """

        if not isinstance(state, dict):
            return
        model = getattr(self, "model", None)
        set_state = getattr(model, "set_state", None)
        if callable(set_state):
            try:
                set_state(state)
            except Exception:
                return
        # After restoring the internal model/parameter state, trigger a
        # standard fit update so that derived quantities, plots and any
        # GUI widgets stay in sync.
        try:
            self.update()
        except Exception:
            pass
        # Ask the model to finalize its parameter controllers so that all
        # FittingParameter widgets refresh from the restored values.
        try:
            model = getattr(self, "model", None)
            finalize = getattr(model, "finalize", None)
            if callable(finalize):
                finalize()
        except Exception:
            pass

    def __str__(self):
        """Human-readable summary of the fit.

        Returns
        -------
        str
            String containing chi²r, range, and a parameter table.
        """
        s = f"chi2r={self.chi2r:.4f}  range={self.xmin}..{self.xmax}\n\n"
        s += f"  {'Name':<12s}  {'Value':<11s}  {'Error':<13s}  {'Source'}  {'Link'}\n"
        pd = self.model.parameters_all_dict
        for k in sorted(pd.keys()):
            p = pd[k]
            if not isinstance(p, cs.core.fitting.parameter.FittingParameter):
                continue
            if getattr(p, 'is_output', False):
                continue
            val = f"{p.value:.5g}"
            if p.fixed:
                s += f"  {p.name:<12s}  {val:<11s}  fixed"
            else:
                try:
                    ee = p.error_estimate
                    if isinstance(ee, float):
                        rel = abs(ee / (p.value + 1e-12) * 100.0)
                        err = f"±{ee:.3g}({rel:.1f}%)"
                        src = "sp" if p.scan_result is not None else "cov"
                    else:
                        err = "±N/A"
                        src = ""
                except Exception:
                    err = "±N/A"
                    src = ""
                s += f"  {p.name:<12s}  {val:<11s}  {err:<13s}  {src:<6s}"
            if p.is_linked and p.link is not None:
                s += f"  →{p.link.name}"
            s += "\n"
        s += self._prior_posterior_report()
        return s

    def _prior_posterior_report(self) -> str:
        """Render the prior and posterior sections appended to :meth:`__str__`."""
        lines = []

        priors = self.prior_summary()
        informative = [e for e in priors if e['informative']]
        box_only = [e['name'] for e in priors if not e['informative']]
        lines.append("\n  Priors")
        for e in informative:
            lines.append(f"    {e['name']:<12s}  {e['description']}")
        if box_only:
            # These only restate the bounds and contribute nothing to the
            # objective, so they are named rather than listed one per line.
            lines.append(f"    bounds only (not in objective): {', '.join(box_only)}")
        if not priors:
            lines.append("    (none set — flat prior, so the fit is plain least squares)")
        elif not informative:
            lines.append("    (no informative prior — the fit is plain least squares)")

        post = self.posterior_summary()
        # Only an informative prior makes the optimum a posterior mode; with
        # bounds alone the interval is an ordinary confidence interval.
        kind = "posterior (MAP)" if informative else "likelihood"
        lines.append(f"\n  Parameter {kind} intervals")
        if not post:
            lines.append("    (no free parameters)")
        else:
            lines.append(f"    {'Name':<12s}  {'Value':<11s}  {'Interval':<25s}  Method")
            for e in post:
                if e['method'] == 'none':
                    interval, method = "n/a", "no estimate"
                else:
                    interval = f"[{e['low']:.5g}, {e['high']:.5g}]"
                    method = {
                        'mcmc': f"MCMC quantiles, p={e['p_value']:g}",
                        'profile': f"chi2 scan, p={e['p_value']:g}",
                    }.get(e['method'], f"covariance ±1σ, p≈{e['p_value']:g}")
                lines.append(f"    {e['name']:<12s}  {e['value']:<11.5g}  {interval:<25s}  {method}")

        lines.extend(self._derived_report())

        warnings = ((getattr(self, 'sampling_diagnostics', None) or {})
                    .get('warnings') or [])
        if warnings:
            lines.append("\n  Sampling did not converge")
            for w in warnings:
                lines.append(f"    {w}")
        return "\n".join(lines) + "\n"

    def _derived_report(self) -> typing.List[str]:
        """Render the derived-quantity section of :meth:`__str__`.

        These are the numbers that leave the program -- the efficiency in the
        figure, the lifetime in the table -- and until now the report printed
        them, when it printed them at all, without any indication of how well
        they were known.
        """
        try:
            rows = self.derived_summary()
        except Exception as e:
            return ["\n  Derived quantities", f"    (unavailable: {e})"]
        if not rows:
            return []

        lines = ["\n  Derived quantities"]
        lines.append(f"    {'Name':<32s}  {'Value':<11s}  {'Interval':<27s}  Method")
        method_text = {
            'draws': 'posterior draws',
            'delta': 'linear propagation',
            'none': 'no estimate',
        }
        skewed = []
        for e in rows:
            if e['method'] == 'none' or not np.isfinite(e.get('low', np.nan)):
                interval = e.get('warning') or "n/a"
            else:
                interval = f"[{e['low']:.5g}, {e['high']:.5g}]"
            method = method_text.get(e['method'], e['method'])
            lines.append(
                f"    {e['name']:<32s}  {e['value']:<11.5g}  {interval:<27s}  {method}")
            if 'skewed' in (e.get('warning') or ''):
                skewed.append(e['name'])
        if skewed:
            lines.append(f"    (skewed, so the interval is not value ± σ: "
                         f"{', '.join(skewed)})")
        elif rows and rows[0]['method'] == 'delta':
            if rows[0].get('converged') is False:
                lines.append("    (the chain on this fit did not converge and was "
                             "not used; these are linear propagation)")
            else:
                lines.append("    (linear propagation: symmetric by construction — "
                             "sample the fit for the true shape)")
        return lines

    def prior_summary(self) -> typing.List[typing.Dict[str, typing.Any]]:
        """Describe the prior attached to each parameter of the model.

        Returns
        -------
        list of dict
            One entry per parameter carrying a prior, with ``name``,
            ``description`` (a compact ``kind(params)`` string) and
            ``informative`` — False for a uniform/box prior, which only restates
            the parameter's bounds and contributes nothing to the objective.
        """
        out = []
        for name in sorted(self.model.parameters_all_dict.keys()):
            p = self.model.parameters_all_dict[name]
            if not isinstance(p, cs.core.fitting.parameter.FittingParameter):
                continue
            if getattr(p, 'is_output', False):
                continue
            try:
                prior = getattr(p, 'prior', None)
            except Exception:
                prior = None
            if prior is None:
                continue
            informative = not isinstance(prior, cs.core.fitting.priors.UniformPrior)
            out.append({
                'name': str(p.name),
                'description': repr(prior),
                'informative': bool(informative),
            })
        return out

    def posterior_summary(
            self,
            p_value: float = 0.68
    ) -> typing.List[typing.Dict[str, typing.Any]]:
        """Summarise each free parameter's marginal uncertainty about the optimum.

        Two very different estimates are reported under one roof, and the
        ``method`` key says which one a row carries. ``profile`` intervals come
        from an actual chi² scan and may be asymmetric; ``laplace`` intervals are
        the quadratic approximation ``value ± error_estimate`` implied by the
        covariance matrix. Whether these are *credible* or merely *confidence*
        intervals depends on the priors in play: with only uniform/box priors the
        posterior is proportional to the likelihood inside the bounds and the two
        coincide, which is why :meth:`prior_summary` reports informativeness.

        Parameters
        ----------
        p_value : float, optional
            Coverage requested from a scan-derived interval.

        Returns
        -------
        list of dict
            One entry per free parameter with ``name``, ``value``, ``low``,
            ``high``, ``method`` and ``p_value``. ``low``/``high`` are NaN when
            no estimate is available.

        Notes
        -----
        Three estimates are possible and the ``method`` key says which a row
        carries, in decreasing order of fidelity: ``mcmc`` (posterior quantiles
        from a chain left by :func:`sample_fit`, the only one that needs no
        Gaussian or single-parameter assumption), ``profile`` and ``laplace``.

        A ``laplace`` row is symmetric by construction, and the posterior it
        approximates often is not -- bounded parameters and weak components are
        routinely skewed. Where a stored chain shows this, the row carries a
        ``warning`` and the measured ``asymmetry`` so a reader is not left to
        assume the interval means what it looks like.
        """
        engine = cs.core.fitting.engine.StoredEngine(self, model=self.model)
        names = []
        for name in sorted(self.model.parameters_all_dict.keys()):
            p = self.model.parameters_all_dict[name]
            if not isinstance(p, cs.core.fitting.parameter.FittingParameter):
                continue
            if getattr(p, 'is_output', False) or p.fixed:
                continue
            names.append(str(p.name))
            engine.add_target(str(p.name))
        engine.run(p_value=p_value)

        out = []
        for name in names:
            m = engine.marginal(name)
            entry = {
                'name': m.name,
                'value': m.value,
                'low': m.low,
                'high': m.high,
                'method': m.method,
                'p_value': float(p_value),
            }
            # A ``laplace`` row is symmetric by construction. When a chain shows
            # the posterior is not, the row says so rather than leaving the
            # reader to assume the interval means what it looks like.
            warning = (m.diagnostics or {}).get('warning')
            if warning:
                entry['warning'] = warning
                entry['asymmetry'] = m.diagnostics['asymmetry']['asymmetry']
            out.append(entry)
        return out

    def derived_summary(
            self,
            p_value: float = 0.68,
            max_draws: int = 2048
    ) -> typing.List[typing.Dict[str, typing.Any]]:
        r"""Attach an interval to the quantities the model reports but never fits.

        A FRET efficiency or a mean lifetime is a function of the fitted
        parameters and has always been printed as a bare number, as if it were
        exact. It is not: it inherits the parameters' uncertainty, and because
        the function is non-linear it inherits a *shape* as well. See
        :mod:`chisurf.core.fitting.derived`.

        Parameters
        ----------
        p_value : float, optional
            Central coverage of the reported interval.
        max_draws : int, optional
            Cap on posterior draws evaluated. Lower than the module default
            because this feeds a printed report: a derived quantity of a
            distance-distribution model costs a distribution-to-rates conversion
            per draw, and nobody wants that on the path that renders text.
            Measured on a two-component TCSPC fit, the whole section costs 0.28 s
            here against 12.7 s for the full chain, and the interval ends land
            within ~1% of the arm they converge to. Halving it again does not:
            a quantile in the long tail of a skewed quantity was still moving by
            several percent at 512 draws, which is visible in the printed digits.

        Returns
        -------
        list of dict
            As :func:`chisurf.core.fitting.derived.derived_posterior`; empty when
            the model declares no derived quantities.
        """
        from chisurf.core.fitting import derived as _derived
        return _derived.derived_posterior(
            self, p_value=p_value, max_draws=max_draws)

    def get_curves(
            self,
            copy_curves: bool = False,
            *,
            full_length: bool = False
    ) -> typing.OrderedDict[str, cs.core.curve.Curve]:
        """Return a mapping of named curves associated with this fit.

        The dictionary typically contains entries for ``"model"``,
        ``"data"``, ``"weighted residuals"`` and ``"autocorrelation"``.
        """
        d = self.model.get_curves(
            copy_curves=copy_curves
        )
        d['data'] = self.data
        if full_length:
            try:
                x_full = np.asarray(getattr(self.data, 'x', []), dtype=float)
            except Exception:
                x_full = np.asarray([], dtype=float)
            n = int(x_full.size)

            try:
                xmin = int(getattr(self, 'xmin', 0))
            except Exception:
                xmin = 0
            if n <= 0:
                xmin = 0
            else:
                xmin = int(np.clip(xmin, 0, n))

            try:
                wres_seg = self.get_wres(model=self.model, xmin=self.xmin, xmax=self.xmax)
                wres_seg = np.asarray(wres_seg, dtype=float)
            except Exception:
                try:
                    wres_seg = np.asarray(getattr(self.model, 'weighted_residuals', []), dtype=float)
                except Exception:
                    wres_seg = np.asarray([], dtype=float)

            try:
                _, mdl_seg = self.model[self.xmin:self.xmax]
                mdl_seg = np.asarray(mdl_seg, dtype=float)
            except Exception:
                mdl_seg = np.asarray([], dtype=float)

            window_len = int(min(wres_seg.size, mdl_seg.size))
            if n > 0:
                window_len = int(min(window_len, n - xmin))
            else:
                window_len = 0

            y_wres = np.full(n, np.nan, dtype=float)
            y_mdl = np.full(n, np.nan, dtype=float)
            if window_len > 0:
                y_wres[xmin:xmin + window_len] = wres_seg[:window_len]
                y_mdl[xmin:xmin + window_len] = mdl_seg[:window_len]

            d['weighted residuals'] = cs.core.curve.Curve(x=x_full, y=y_wres, copy_array=False)
            d['model'] = cs.core.curve.Curve(x=x_full, y=y_mdl, copy_array=False)
        else:
            d['weighted residuals'] = self.weighted_residuals
        d['autocorrelation'] = self.autocorrelation
        return d

    def get_score(self, score_type: str = 'chi2'):
        """Return a scalar goodness-of-fit score.

        Parameters
        ----------
        score_type : {"chi2", "chi2r"}
            Select unreduced or reduced chi².
        """
        if score_type == 'chi2':
            return self.chi2
        elif score_type == 'chi2r':
            return self.chi2r

    def get_chi2(
            self,
            parameter=None,
            model: cs.core.models.Model = None,
            reduced: bool = True
    ) -> float:
        """Convenience wrapper around :func:`get_chi2` using this fit."""
        if model is None:
            model = self.model
        return get_chi2(
            parameter,
            model,
            reduced
        )

    def get_wres(
            self,
            parameter=None,
            model=None,
            **kwargs
    ) -> np.ndarray:
        """Return weighted residuals for a model attached to this fit."""
        if model is None:
            model = self.model
        if parameter is not None:
            model.parameter_values = parameter
            model.update_model()
        wres = model.get_wres(self, **kwargs)
        return _apply_fit_mask(model, wres)

    def save(
            self,
            filename: str,
            file_type: str = 'csv',
            save_curves: bool = False,
            verbose: bool = False,
            **kwargs
    ) -> None:
        """Save fit metadata and, optionally, all associated curves."""
        super().save(
            filename=filename,
            file_type=file_type,
            verbose=verbose
        )
        if save_curves:
            curve_dict = self.get_curves(full_length=True)
            with open(filename+'_info.txt', mode='w') as fp:
                fp.write(str(self))
            for curve_key in curve_dict:
                curve = curve_dict[curve_key]
                curve_file_root = filename + "_%s" % curve_key
                curve.save(
                    filename=curve_file_root + '.' + file_type,
                    file_type=file_type
                )

    def run(self, *args, **kwargs) -> None:
        """Run a local least-squares optimization on this fit."""
        fitting_options = _leastsq_options(cs.core.settings.cs_settings['optimization']['leastsq'])
        self.model.find_parameters(
            parameter_type=cs.core.fitting.parameter.FittingParameter
        )
        progress_callback = kwargs.get("progress_callback") or self._progress_callback
        cancelled = False
        # A covariance from an earlier run describes earlier parameters, and
        # a graph cached for one describes earlier data.
        self.__dict__.pop("_cpp_covariance", None)
        self.__dict__.pop("_graph_cache", None)
        try:
            # The structure is fixed for the whole optimisation -- parameters
            # are not linked, freed or rediscovered between two evaluations --
            # so resolve the free-parameter list and the bounds once.
            with cs.core.fitting.factorgraph.frozen_structure(self):
                # The optimiser runs in C++, on the same side of the
                # boundary as the residual: one crossing per evaluation
                # instead of one per parameter plus one per part. Same
                # MINPACK lmdif, same bounds transform, same tolerances --
                # pinned against this module's own leastsqbound in
                # IMP.bff's test/minimizer.
                cs.core.fitting.minimizer.minimize(
                    get_wres,
                    self.model.parameter_values,
                    args=(self.model, True),
                    bounds=self.model.parameter_bounds,
                    progress_callback=progress_callback,
                    n_free=self.model.n_free,
                    fit=self,
                    model=self.model,
                    **fitting_options
                )
        except OptimizationCancelled:
            cancelled = True
        self._last_run_cancelled = cancelled
        if self.__dict__.pop("_model_holds_the_fit", False):
            # The graph path's write-back already ran the one model
            # evaluation, so the curve and residuals are the fitted ones;
            # re-evaluating here recomputed the same curve (10% of a TCSPC
            # fit, T-20260901-11). The bookkeeping half of update() still
            # runs, and finalize() below refreshes the controllers.
            self.model.find_parameters()
        else:
            self.update()
        if not cancelled:
            self.update_error_estimates()
            self.results.append(self.model.__getstate__())
        self.model.finalize()
        if cancelled:
            raise OptimizationCancelled()

    def set_parameter_value(self, name: str, value: float):
        """Update a parameter value and notify dependents."""
        try:
            p = self.model.parameters_all_dict[name]
            p.value = value
            self.model.update_model()
            self.model.finalize()
        except KeyError:
            cs.logging.error(f"Parameter '{name}' not found in model.")

    def set_parameter_fixed(self, name: str, fixed: bool):
        """Fix/release a parameter and notify dependents."""
        try:
            p = self.model.parameters_all_dict[name]
            p.fixed = bool(fixed)
            self.model.finalize()
        except KeyError:
            cs.logging.error(f"Parameter '{name}' not found in model.")

    def set_parameter_bounds(self, name: str, bounds: typing.Tuple[float, float]):
        """Set parameter bounds and notify dependents."""
        try:
            p = self.model.parameters_all_dict[name]
            p.bounds = bounds
            self.model.finalize()
        except KeyError:
            cs.logging.error(f"Parameter '{name}' not found in model.")

    def set_parameter_bounds_on(self, name: str, on: bool):
        """Enable/disable parameter bounds and notify dependents."""
        try:
            p = self.model.parameters_all_dict[name]
            p.bounds_on = bool(on)
            self.model.finalize()
        except KeyError:
            cs.logging.error(f"Parameter '{name}' not found in model.")

    def set_parameter_prior(self, name: str, prior):
        """Set or clear a parameter's prior and notify dependents.

        ``prior`` may be a :class:`~chisurf.core.fitting.priors.Prior`, a prior
        state dict, a callable ``logpdf(x)``, or ``None`` to clear it. Bounds are
        the uniform-prior special case (handled by the ``Parameter.prior``
        setter).
        """
        try:
            p = self.model.parameters_all_dict[name]
            p.prior = prior
            self.model.finalize()
        except KeyError:
            cs.logging.error(f"Parameter '{name}' not found in model.")

    def link_parameter(self, target_name: str, source_name: str, source_fit: Fit):
        """Link a parameter to another and notify dependents."""
        try:
            tp = self.model.parameters_all_dict[target_name]
            sp = source_fit.model.parameters_all_dict[source_name]
            tp.link = sp
            self.model.finalize()
        except KeyError:
            import chisurf.logging
            # Provide detailed diagnostics including requested keys and available ones.
            try:
                tgt_keys = ', '.join(self.model.parameters_all_dict.keys())
            except Exception:
                tgt_keys = '<unavailable>'
            try:
                src_keys = ', '.join(source_fit.model.parameters_all_dict.keys())
            except Exception:
                src_keys = '<unavailable>'
            cs.logging.error(
                "Parameter link failed: name not found. target='%s' in target_fit(keys=[%s]); "
                "source='%s' in source_fit(keys=[%s])" % (target_name, tgt_keys, source_name, src_keys)
            )

    def unlink_parameter(self, name: str):
        """Unlink a parameter and notify dependents."""
        try:
            p = self.model.parameters_all_dict[name]
            p.link = None
            self.model.finalize()
        except KeyError:
            cs.logging.error(f"Parameter '{name}' not found in model.")

    def set_result_idx(self, idx: int):
        """Restore model state from a stored result by index.

        Parameters
        ----------
        idx : int
            Index in the results deque. Clipped to the valid range.

        Raises
        ------
        ValueError
            When the fit has no stored results. There is no valid range to
            clip to in that case: ``np.clip(idx, 0, -1)`` returns ``-1`` and
            indexing an empty deque with it raised ``IndexError: deque index
            out of range`` — an internal leak where "this fit has not been run
            yet" is the thing the caller needs to hear.
        """
        if not self.results:
            raise ValueError(
                f"fit {getattr(self, 'name', '')!r} has no results to restore; run it first"
            )
        idx = np.clip(idx, 0, len(self.results) - 1)
        self._result_current = idx
        self.model.__setstate__(self.results[idx])
        self.update()
        self.model.finalize()

    def next_result(self):
        """Advance to the next stored result."""
        self.set_result_idx(self._result_current + 1)

    def previous_result(self):
        """Go back to the previous stored result."""
        self.set_result_idx(self._result_current - 1)

    def update_error_estimates(self):
        """Update parameter error estimates from the covariance matrix."""
        # Estimate errors based on gradient
        fit = self
        # Both callers of this method run `self.update()` immediately before
        # it, so the model curve belongs to the parameter values the
        # covariance is taken around, and its residuals are exactly the `f0`
        # that would otherwise be recomputed. That is one model evaluation of
        # the five this used to cost for three free parameters -- a fifth of
        # the error estimate, which is itself a third of every fit.
        cov_m, used_parameters = self._optimiser_covariance()
        if cov_m is None:
            f0 = None
            try:
                residuals = np.asarray(fit.model.weighted_residuals, dtype=float)
                if residuals.ndim == 1 and residuals.size:
                    f0 = residuals
            except Exception:
                f0 = None
            cov_m, used_parameters = covariance_matrix(fit, f0=f0)
        err = np.sqrt(np.diag(cov_m)) * _error_scale(fit)
        free = fit.model.parameters
        for p, e in zip(used_parameters, err):
            free[p].error_estimate = e
        self._propagate_redundant_error_estimates(cov_m, used_parameters, free)

    def _optimiser_covariance(self):
        """The covariance the optimiser already built, or ``(None, None)``.

        Rebuilding the Jacobian by finite differences over the *Python*
        model costs ``p + 1`` calls to :meth:`Model.update_model` and was
        **32% of every TCSPC fit** -- for a matrix that can be built where
        the model and the data already are.

        :func:`chisurf.core.fitting.minimizer._covariance_at_the_solution`
        builds it: the optimiser's own QR matrix when its step resolved, and
        otherwise the same finite differences taken over the *graph*, in C++.
        Either way nothing crosses the boundary here. Only a model that never
        built a graph returns ``(None, None)`` and sends the caller to
        :func:`covariance_matrix`.

        The stash is checked against the *identity* of the current free
        parameters rather than their number, because a re-parse rebuilds the
        parameter objects and a covariance for the previous set would line up
        by length and mean nothing.
        """
        stash = self.__dict__.pop("_cpp_covariance", None)
        if stash is None:
            return None, None
        cov_m, used_parameters, parameter_ids = stash
        free = self.model.parameters
        if tuple(id(p) for p in free) != parameter_ids:
            return None, None
        return cov_m, list(used_parameters)

    def _propagate_redundant_error_estimates(self, cov_m, used_parameters, free):
        """Give redundant parameters the uncertainty implied by their constraint.

        A redundant amplitude carries no column in the covariance matrix, so it
        would otherwise keep a stale estimate from an earlier fit -- worse than
        having none. Amplitudes are normalised to sum to one, so the held-out one
        is ``1 - sum(siblings)`` and its variance is the sum of that block of the
        covariance matrix (including the off-diagonal terms, which are large
        here precisely because the fractions are anti-correlated).
        """
        groups = getattr(self.model, "_aggregated_parameters", None) or []
        index_of = {id(free[p]): k for k, p in enumerate(used_parameters)}
        for group in groups:
            amplitudes = getattr(group, "_amplitudes", None)
            if not amplitudes:
                continue
            for a in amplitudes:
                if not getattr(a, "redundant", False):
                    continue
                cols = [index_of[id(s)] for s in amplitudes
                        if s is not a and id(s) in index_of]
                if not cols:
                    a.error_estimate = None
                    continue
                block = cov_m[np.ix_(cols, cols)]
                a.error_estimate = float(np.sqrt(max(block.sum(), 0.0)))

    def update(self) -> None:
        """Update the model and notify observers."""
        self.model.update()

    def grid_scan(
            self,
            parameters: typing.Sequence = None,
            budget: int = None,
            points: int = None,
            apply_best: bool = True,
            progress_callback: typing.Callable = None,
    ):
        """Scan a coarse grid over free parameters and jump to the best point.

        A least-squares run is local: it goes downhill from where it starts, so
        a degenerate pair or a rough objective leaves it in the first dip it
        finds. This evaluates chi2 on a coarse grid first — a fixed number of
        model evaluations, whatever the number of parameters — and (by default)
        leaves the parameters at the best point, from which :meth:`run` then
        descends.

        Different in kind from :meth:`chi2_scan`, which profiles *one*
        parameter for its confidence interval.

        Parameters
        ----------
        parameters : sequence of FittingParameter, optional
            What to scan. Defaults to the model's free parameters.
        budget : int, optional
            Roughly how many grid points to evaluate.
        points : int, optional
            Fixed number of values per parameter, overriding ``budget``.
        apply_best : bool, optional
            Leave the parameters at the best point (default). ``False`` restores
            them and only reports.
        progress_callback : callable, optional
            Called as ``progress_callback(evaluated, total)``.

        Returns
        -------
        GridScanResult
            Falsy when no grid was run (too many parameters).
        """
        from chisurf.core.fitting import grid_scan as _grid_scan

        if parameters is None:
            self.model.find_parameters(
                parameter_type=cs.core.fitting.parameter.FittingParameter
            )
            parameters = list(self.model.parameters)
        parameters = list(parameters)
        state = {"n": 0}

        def cost(values) -> float:
            for parameter, value in zip(parameters, values):
                parameter.value = float(value)
            self.model.update_model()
            state["n"] += 1
            if progress_callback is not None:
                progress_callback(state["n"], None)
            return float(self.chi2r)

        kwargs = {"apply_best": apply_best}
        if budget is not None:
            kwargs["budget"] = int(budget)
        if points is not None:
            kwargs["points"] = int(points)
        result = _grid_scan.grid_scan(parameters, cost, **kwargs)
        self.update()
        return result

    def chi2_scan(
            self,
            parameter_name: str,
            rel_range: float = None,
            scan_range: typing.Tuple[float, float] = (None, None),
            n_steps: int = 30
    ) -> typing.Tuple[np.array, np.array]:
        """Perform a chi2-scan on a parameter of the fit.

        :param parameter_name: the parameter name
        :param rel_range: defines the scanning range as a fraction of the
        current value, e.g., for a value of 2.0 a rel_range of 0.5 scans
        from (2.0 - 2.0*0.5) to (2.0 + 2.0*0.5)
        :param kwargs:
        :return: a list containing arrays of the chi2 and the parameter-values
        """
        parameter = self.model.parameters_all_dict[parameter_name]
        if rel_range is None:
            rel_range = max(
                parameter.error_estimate * 3.0 / parameter.value,
                0.25
            )
        r = cs.core.fitting.support_plane.scan_parameter(
            fit=self,
            parameter_name=parameter_name,
            rel_range=rel_range,
            scan_range=scan_range,
            n_steps=n_steps
        )
        parameter.parameter_scan = r['parameter_values'], r['chi2r']
        return parameter.parameter_scan

    def adaptive_chi2_scan(
            self,
            parameter_name: str,
            scan_range: typing.Tuple[float, float] = (None, None),
            p_value: float = 0.99,
            max_points_per_side: int = 50,
            **kwargs
    ) -> typing.Dict:
        """Adaptive F-test-driven chi² scan for a parameter.

        See :func:`cs.core.fitting.support_plane.adaptive_scan_parameter`
        for details.
        """
        r = cs.core.fitting.support_plane.adaptive_scan_parameter(
            fit=self,
            parameter_name=parameter_name,
            scan_range=scan_range,
            p_value=p_value,
            max_points_per_side=max_points_per_side,
        )
        parameter = self.model.parameters_all_dict[parameter_name]
        parameter.parameter_scan = r['parameter_values'], r['chi2r']
        parameter.scan_result = r
        crossings = r.get('crossings', (None, None))
        errors = []
        for crossing in crossings:
            try:
                if crossing is not None and np.isfinite(float(crossing)):
                    errors.append(abs(float(crossing) - float(parameter.value)))
            except Exception:
                pass
        if errors:
            parameter.error_estimate = float(max(errors))
        return r


class FitGroup(Fit):
    """Group of :class:`Fit` objects that share a global model.

    A :class:`FitGroup` manages multiple single-curve fits while exposing
    an aggregate model for global optimization.
    """

    @property
    def selected_fit(self) -> Fit:
        """Currently selected grouped fit.

        Returns
        -------
        Fit
            The fit at the current selection index.
        """
        return self.grouped_fits[self.selected_fit_index]

    @property
    def selected_fit_index(self) -> int:
        """Index of the currently selected grouped fit.

        Returns
        -------
        int
            Selection index.
        """
        return self._selected_fit_index

    @selected_fit.setter
    def selected_fit(self, v: int):
        """Set the selected fit index.

        Parameters
        ----------
        v : int or Fit
            New selection index. A :class:`Fit` member is accepted for
            convenience and converted to its index; passing one used to corrupt
            ``_selected_fit_index`` and break later ``grouped_fits[index]``
            lookups.
        """
        if isinstance(v, Fit):
            try:
                v = self.grouped_fits.index(v)
            except ValueError:
                raise ValueError("selected_fit: Fit is not a member of this group")
        self._selected_fit_index = int(v)

    @property
    def data(self) -> cs.core.data.DataCurve:
        """Data of the currently selected grouped fit.

        Returns
        -------
        cs.core.data.DataCurve
            Data curve of the selected fit.
        """
        return self.selected_fit.data

    @data.setter
    def data(self, v: cs.core.base.Data):
        """Set the data on the currently selected grouped fit.

        Parameters
        ----------
        v : cs.core.data.DataCurve
            New data curve.
        """
        self.selected_fit.data = v

    @property
    def model(self) -> cs.core.models.Model:
        """Model of the currently selected grouped fit.

        Returns
        -------
        cs.core.models.Model
            Model of the selected fit.
        """
        return self.selected_fit.model

    @model.setter
    def model(self, v: typing.Type[cs.core.models.Model]):
        """Set the model on the currently selected grouped fit.

        Parameters
        ----------
        v : type
            Model class to instantiate on the selected fit.
        """
        self.selected_fit.model = v

    @property
    def weighted_residuals(self) -> cs.core.curve.Curve:
        """Weighted residuals of the currently selected grouped fit.

        Returns
        -------
        cs.core.curve.Curve
            Weighted residuals curve.
        """
        return self.selected_fit.weighted_residuals

    @property
    def chi2r(self) -> float:
        """Reduced chi-squared of the currently selected grouped fit.

        Returns
        -------
        float
            Reduced chi-squared value.
        """
        return self.selected_fit.chi2r

    @property
    def durbin_watson(self) -> float:
        """Durbin-Watson statistic of the selected fit's residuals.

        Returns
        -------
        float
            Test statistic for autocorrelation.
        """
        return cs.core.math.statistics.durbin_watson(
            self.weighted_residuals.y
        )

    @property
    def mask(self):
        """Optional global mask shared across all grouped fits.

        This forwards to the currently selected fit's mask for reading and
        propagates any assignment to all member fits, so that both the global
        model and individual fits see the same residual weights.
        """

        return getattr(self.selected_fit, "mask", None)

    @mask.setter
    def mask(self, v):
        """Set the mask on all grouped fits.

        Parameters
        ----------
        v : array_like or None
            Mask or weights array forwarded to each member fit.
        """
        for f in self:
            setattr(f, "mask", v)

    @property
    def fit_range(self) -> typing.Tuple[int, int]:
        """Fitting range of the FitGroup (from the selected fit).

        Returns
        -------
        tuple of int
            ``(xmin, xmax)`` of the selected fit.
        """
        return self.xmin, self.xmax

    @fit_range.setter
    def fit_range(self, v):
        """Set the fitting range on all grouped fits.

        Parameters
        ----------
        v : tuple of int
            Either a 2-tuple ``(xmin, xmax)`` or a 4-tuple defining two
            mask intervals.
        """
        vals = tuple(int(x) for x in v)
        if len(vals) == 2:
            # Backwards-compatible 1D range: propagate to all member fits.
            xmin, xmax = vals
            for f in self:
                f.xmin, f.xmax = xmin, xmax
            self.xmin, self.xmax = xmin, xmax

            # Initialize or rebuild simple 1D masks per fit matching the
            # common [xmin, xmax) range, clipped to each dataset length.
            for f in self:
                try:
                    y = getattr(f.data, "y", None)
                    n = int(len(y)) if y is not None else 0
                except Exception:
                    n = 0
                if n <= 0:
                    try:
                        f.mask = None
                    except Exception:
                        pass
                    continue
                lb1 = max(0, int(xmin))
                ub1 = max(lb1, min(int(xmax), n))
                mask = np.zeros(n, dtype=float)
                if ub1 > lb1:
                    mask[lb1:ub1] = 1.0
                try:
                    f.mask = mask
                except Exception:
                    pass
            return
        if len(vals) != 4:
            raise ValueError("FitGroup.fit_range must be a 2- or 4-tuple of integers")

        xmin1, xmax1, xmin2, xmax2 = vals

        # Primary 1D range still defined by the first interval; propagate to
        # all member fits and to the group itself.
        for f in self:
            f.xmin, f.xmax = xmin1, xmax1
        self.xmin, self.xmax = xmin1, xmax1

        # Build per-fit masks as the union of the two index intervals on
        # each fit's data length so that all residuals see consistent
        # weighting regardless of individual data sizes.
        for f in self:
            try:
                y = getattr(f.data, "y", None)
                n = int(len(y)) if y is not None else 0
            except Exception:
                n = 0
            if n <= 0:
                try:
                    f.mask = None
                except Exception:
                    pass
                continue
            lb1 = max(0, int(xmin1))
            ub1 = max(lb1, min(int(xmax1), n))
            lb2 = max(0, int(xmin2))
            ub2 = max(lb2, min(int(xmax2), n))
            mask = np.zeros(n, dtype=float)
            if ub1 > lb1:
                mask[lb1:ub1] = 1.0
            if ub2 > lb2:
                mask[lb2:ub2] = 1.0
            try:
                f.mask = mask
            except Exception:
                pass

    @property
    def xmin(self) -> int:
        """Minimum fit index of the selected grouped fit.

        Returns
        -------
        int
            Lower bound of the fitting range.
        """
        return self.selected_fit.xmin

    @xmin.setter
    def xmin(self, v: int):
        """Set the minimum fit index on all grouped fits.

        Parameters
        ----------
        v : int
            Lower bound.
        """
        for f in self:
            f.xmin = v

    @property
    def xmax(self) -> int:
        """Maximum fit index of the selected grouped fit.

        Returns
        -------
        int
            Upper bound of the fitting range.
        """
        return self.selected_fit.xmax

    @xmax.setter
    def xmax(self, v: int):
        """Set the maximum fit index on all grouped fits.

        Parameters
        ----------
        v : int
            Upper bound.
        """
        for f in self:
            f.xmax = v

    def get_curves(
            self,
            copy_curves: bool = False,
            idx: int = None,
            *,
            full_length: bool = False
    ) -> typing.OrderedDict[str, cs.core.curve.Curve]:
        """Return curves for one or all grouped fits.

        If ``idx`` is ``None``, curves from :meth:`super().get_curves` are
        returned. Otherwise curves are collected from the selected or all
        grouped fits, with keys suffixed by ``"_%02d"``.
        """
        curves = {}
        if idx is None:
            curves = super().get_curves(copy_curves=copy_curves, full_length=full_length)
        else:
            if idx >= 0:
                fit = self.grouped_fits[idx]
                curves = fit.get_curves(copy_curves=copy_curves, full_length=full_length)
            else:
                for i, f in enumerate(self.grouped_fits):
                    fit_curves = f.get_curves(copy_curves=copy_curves, full_length=full_length)
                    for curve_key in fit_curves:
                        new_curve_key = curve_key + "_%02d" % i
                        curves[new_curve_key] = fit_curves[curve_key]
        return curves

    def save(
            self,
            filename: str,
            file_type: str = 'txt',
            verbose: bool = False,
            **kwargs
    ) -> None:
        """Save all grouped fits with derived per-fit filenames.

        Parameters
        ----------
        filename : str
            Base filename. Per-fit suffixes are derived from data names.
        file_type : str, optional
            Output file format (default ``'txt'``).
        verbose : bool, optional
            If True, print additional information during save.
        """
        root, ext = os.path.splitext(filename)
        member_bases = []
        for fit in self:
            data_name = str(getattr(getattr(fit, "data", None), "name", ""))
            base = os.path.splitext(os.path.basename(data_name))[0].strip()
            member_bases.append(base)

        token_lists = [
            [t for t in re.split(r"[\s_\-]+", b) if t]
            for b in member_bases
        ]

        # Token-aware common prefix/suffix to avoid character-level artifacts
        # like VV/VH collapsing to V/H.
        prefix_len = 0
        if token_lists:
            min_len = min(len(toks) for toks in token_lists)
            for i in range(min_len):
                tok = token_lists[0][i]
                if all(len(toks) > i and toks[i] == tok for toks in token_lists[1:]):
                    prefix_len += 1
                else:
                    break

        suffix_len = 0
        if token_lists:
            min_len = min(max(0, len(toks) - prefix_len) for toks in token_lists)
            for i in range(1, min_len + 1):
                tok = token_lists[0][-i]
                if all(len(toks) - i >= prefix_len and toks[-i] == tok for toks in token_lists[1:]):
                    suffix_len += 1
                else:
                    break

        pol_re = re.compile(r"^(VV|VH|HV|HH)$", re.IGNORECASE)
        used_suffixes = set()
        for i, fit in enumerate(self):
            suffix = ""
            try:
                base = member_bases[i]
                tokens = token_lists[i]
            except Exception:
                base = ""
                tokens = []

            if base:
                # Prefer explicit polarization/channel tokens where available.
                pol_tokens = [t for t in tokens if pol_re.match(t)]
                if pol_tokens:
                    suffix = pol_tokens[-1].upper()

                # Otherwise use the token-difference core.
                if not suffix:
                    start = min(prefix_len, len(tokens))
                    end = len(tokens) - suffix_len if suffix_len > 0 else len(tokens)
                    if end < start:
                        end = start
                    core_tokens = tokens[start:end]
                    if core_tokens:
                        suffix = "_".join(core_tokens)

            # If no meaningful per-fit suffix is available, fall back to index.
            if not suffix:
                suffix = f"{i:02d}"

            # Keep filesystem-friendly suffixes.
            suffix = re.sub(r'[\\/:*?"<>|]+', '_', suffix)
            suffix = re.sub(r'\s+', ' ', suffix).strip()

            # Ensure uniqueness even for duplicate labels.
            if suffix in used_suffixes:
                suffix = f"{suffix}_{i:02d}"
            used_suffixes.add(suffix)

            fit_root = f"{root}_{suffix}"
            fit_filename = fit_root + ext if ext else fit_root
            fit.save(
                filename=fit_filename,
                file_type=file_type,
                verbose=verbose,
                **kwargs
            )

    def finalize(self):
        """Finalize the global model and all grouped fits."""
        self.update()
        self._model.finalize()

    def update(self) -> None:
        """Update all grouped fits."""
        for f in self.grouped_fits:
            f.update()

    def run(self, local_first: bool = None, **kwargs):
        """Run local fits followed by a global least-squares optimization."""
        fit: FitGroup = self
        if local_first is None:
            local_first = cs.core.settings.optimization['global_optimize_local_first']
        cancelled = False
        # A covariance from an earlier run describes earlier parameters.
        self.__dict__.pop("_cpp_covariance", None)
        sink = kwargs.pop("progress_callback", None) or self._progress_callback
        # A group runs each member and then the global fit, and every one of
        # those restarts its own evaluation count from zero. Reported raw, the
        # bar would sweep to full and drop back once per member; staged, the
        # members share the bar in order.
        staged = _StagedProgress(sink, (len(fit) if local_first else 0) + 1)
        try:
            if local_first:
                for i, f in enumerate(fit):
                    f.run(progress_callback=staged.stage(i), **kwargs)
            for f in fit:
                f.model.find_parameters()
            fit._model.find_parameters()
            fitting_options = _leastsq_options(cs.core.settings.optimization['leastsq'])
            bounds = [pi.bounds for pi in fit._model.parameters]
            progress_callback = staged.stage(staged.n_stages - 1)
            # Nothing about the structure changes while the optimiser runs, so
            # the free-parameter lists are resolved once instead of per call.
            with cs.core.fitting.factorgraph.frozen_structure(fit):
                # The same C++ optimiser as a member fit, and -- when every
                # member is a model bff can compile -- the same whole-graph
                # arrangement: one `Expression -> ChiSquared` per member under
                # one `JointChiSquared`, with the shared parameters as port
                # links. The group's residual is its members' end to end,
                # which is what `GlobalFitModel.weighted_residuals`
                # concatenates, so the objective is the same one and nothing
                # crosses the boundary per iteration. A group with a member
                # the graph cannot represent is refused *whole* and falls back
                # to scipy: half a group in C++ still pays the crossing.
                cs.core.fitting.minimizer.minimize(
                    func=get_wres,
                    x0=fit._model.parameter_values,
                    args=(fit._model, True),
                    bounds=bounds,
                    progress_callback=progress_callback,
                    n_free=fit._model.n_free,
                    fit=fit,
                    model=fit._model,
                    **fitting_options
                )
        except OptimizationCancelled:
            cancelled = True
        self._last_run_cancelled = cancelled
        if self.__dict__.pop("_model_holds_the_fit", False):
            # Same as Fit.run: the joint graph's write-back already
            # evaluated the global model once (T-20260901-11).
            self.model.find_parameters()
        else:
            self.update()
        if not cancelled:
            self.update_error_estimates()
            self.results.append(self.model.__getstate__())
        if cancelled:
            raise OptimizationCancelled()

    def __init__(
            self,
            data: cs.core.data.DataGroup,
            model_class: typing.Type[cs.core.models.Model] = type,
            model_kw: typing.Dict = None
    ):
        """Create a :class:`FitGroup` over a :class:`DataGroup`.

        One :class:`Fit` instance is created per entry in ``data`` and
        collected into ``grouped_fits``. A global model is then constructed
        from these.
        """
        self._selected_fit_index = 0
        self.grouped_fits = list()

        for d in data:
            if model_kw is None:
                model_kw = dict()
            fit = Fit(
                model_class=model_class,
                data=d,
                model_kw=model_kw,
                group=self.grouped_fits
            )

        super().__init__(
            data=data
        )
        self._model = cs.core.models.global_model.GlobalFitModel(
            fit=self,
            fits=self.grouped_fits
        )

    def to_dict(
            self,
            remove_protected: bool = False,
            copy_values: bool = True,
            convert_values_to_elementary: bool = False,
        skip_qt_widgets: bool = False
    ) -> typing.Dict:
        """Serialize the FitGroup and its grouped fits to a dictionary.

        Parameters
        ----------
        remove_protected : bool, optional
            If True, omit keys starting with ``'_'``.
        copy_values : bool, optional
            If True, copy values to avoid aliasing.
        convert_values_to_elementary : bool, optional
            If True, convert numpy types to Python builtins.

        Returns
        -------
        dict
            Serialized representation.
        """
        d = super().to_dict(
            remove_protected=remove_protected,
            copy_values=copy_values,
            convert_values_to_elementary=convert_values_to_elementary,
            skip_qt_widgets=skip_qt_widgets
        )
        d['grouped_fits'] = [
            f.to_dict(
                remove_protected=remove_protected,
                copy_values=copy_values,
                convert_values_to_elementary=convert_values_to_elementary
            ) for f in self.grouped_fits
        ]
        return d

    def __str__(self):
        """String representation of all grouped fits.

        Returns
        -------
        str
            Joined string representations of each member fit.
        """
        parts = []
        for f in self:
            parts.append(str(f))
        return "\n".join(parts)

    def next(self):
        """Advance the iterator and return the next grouped fit.

        Returns
        -------
        Fit
            The next grouped fit.

        Raises
        ------
        StopIteration
            If the end of the grouped fits list is reached.
        """
        if self._selected_fit_index > len(self.grouped_fits):
            raise StopIteration
        else:
            self._selected_fit_index += 1
            return self.grouped_fits[self._selected_fit_index - 1]

    def __len__(self):
        """Number of grouped fits.

        Returns
        -------
        int
            Length of ``grouped_fits``.
        """
        return len(self.grouped_fits)

    def __getitem__(self, key) -> typing.List[Fit]:
        """Access grouped fits by index or slice.

        Parameters
        ----------
        key : int or slice
            Index or slice object.

        Returns
        -------
        Fit or list of Fit
            The fit(s) at the given index/slice.
        """
        if isinstance(key, int):
            return self.grouped_fits.__getitem__(key)
        else:
            start = 0 if key.start is None else key.start
            stop = len(self.grouped_fits) if key.stop is None else key.stop
            step = 1 if key.step is None else key.step
            key = slice(start, stop, step)
            return self.grouped_fits.__getitem__(key)


#: Chain file formats ``sample_fit`` can write, and the suffix each uses.
#: ``er4`` is tab-separated text -- readable by anything, and the reason a long
#: run fills a disk, since a float64 costs ~25 characters there and 8 in
#: ``hdf5``. Both open in nDXplorer.
CHAIN_FORMATS = {
    'er4': '.er4',
    'hdf5': '.h5',
}


def sample_fit(
        fit: Fit,
        target_directory: str,
        method: str = 'ensemble',
        global_posterior: bool = False,
        steps: int = 1000,
        thin: int = 1,
        chi2max: float = float("inf"),
        n_runs: int = 10,
        step_size: float = 0.1,
        temp: float = 1.0,
        check_cancel: typing.Callable = None,
        progress_callback: typing.Callable = None,
        chain_format: str = None,
        **kwargs
):
    """Sample free parameters of a fit and save the chain to disk.

    Parameters
    ----------
    fit : Fit
        Fit whose parameters should be sampled.
    target_directory : str
        Target directory for the sampling results. A timestamped
        subdirectory will be created within this directory.
    method : {"ensemble", "slice", "blocked", "de", "collapsed", "mcmc"}, optional
        Sampling backend; ``emcee`` is accepted as the historical name of
        ``ensemble``. ``de``
        (:func:`chisurf.core.fitting.sample.sample_differential_evolution`)
        proposes from the differences between a population of chains, so it
        needs neither a gradient nor a covariance and cannot be misled by one
        taken at the wrong point: on a curved posterior started away from the
        optimum it delivered ~36x the effective samples per model evaluation of
        ``blocked``. ``collapsed``
        (:func:`chisurf.core.fitting.sample.sample_marginal_shared`) integrates
        each dataset's private parameters out analytically and samples only the
        parameters shared between datasets -- the right choice for a *linked*
        global fit, where linking lowers the dimension but makes the posterior
        harder to sample. With three private parameters per dataset it beat
        ``blocked`` 26-fold in effective samples per model evaluation, and
        ``blocked`` there reported an error bar 5.6x too small. ``blocked``
        (:func:`chisurf.core.fitting.sample.walk_mcmc_blocked`) proposes from a
        per-block *covariance* seeded by the curvature at the optimum, and is
        the one to reach for on a correlated posterior: on a deliberately
        collinear three-parameter fit it delivered ~64 effective samples per
        1000 model evaluations against ~26 for ``ensemble`` and ~0.4 for
        ``mcmc``, whose diagonal proposal produced 4 effective samples out of
        8000 draws. ``ensemble``
        (:func:`chisurf.core.fitting.sample.sample_ensemble`) needs no
        covariance at all -- its walkers take their scale from each other --
        which makes it the fallback when nothing is known about the posterior.
        ``slice`` (:func:`chisurf.core.fitting.sample.sample_ensemble_slice`) is
        the same ensemble idea without an accept/reject step: every walker moves
        every step, at the price of several model evaluations per step.
        ``mcmc`` is the historical diagonal random walk.
    global_posterior : bool, optional
        Sample the *joint* posterior of a :class:`FitGroup` rather than the
        selected member's. ``fit.model`` is that member's model, so the default
        (*False*) samples one dataset. Requires ``method='blocked'``, and the
        reported parameter names are then the group's prefixed ones (``1:c``),
        which :meth:`Fit.posterior_summary` does not map back onto members.
    steps, thin, chi2max, n_runs, step_size, temp : float or int, optional
        Sampling configuration passed through to
        :mod:`cs.core.fitting.sample`.
    chain_format : {"er4", "hdf5"}, optional
        Format of the stored chains, see :data:`CHAIN_FORMATS`. Defaults to the
        ``optimization.sampling.chain_format`` setting. ``er4`` is tab-separated
        text that any tool reads; ``hdf5`` is a compressed table roughly a
        quarter of the size, which is what a long run needs. Both open in
        nDXplorer.

    Returns
    -------
    dict or None
        The convergence report also written to ``diagnostics.json``: pooled
        per-parameter statistics over the ``n_runs`` *independent* runs (mean,
        sd, quantiles, effective sample size, split R-hat, autocorrelation time,
        Monte-Carlo error) plus the list of ``warnings``. ``None`` when no run
        produced a chain. See :mod:`chisurf.core.fitting.diagnostics`.

    Raises
    ------
    ValueError
        If ``fit.model`` is not a curve-based model (e.g. ProteinMC) and
        therefore cannot be sampled with the generic ensemble backend.

    Notes
    -----
    The stored chain files are never truncated. The recommended burn-in is
    reported in ``diagnostics.json`` and applied to the summary statistics only,
    so a reader who disagrees still has every draw.
    """
    model = getattr(fit, "model", None)
    if model is None or not hasattr(model, "__getitem__") or not hasattr(model, "n_points"):
        raise ValueError(
            "Generic sampling requires a curve-based model. "
            "Use the model-specific sampling workflow (e.g. ProteinMC's own sampling button)."
        )

    # ``fit.model`` is the *selected member's* model for a group, so sampling a
    # FitGroup samples that one dataset unless the joint posterior is asked for
    # explicitly. The default keeps the historical behaviour.
    sample_model = fit.model
    if global_posterior:
        sample_model = cs.core.fitting.factorgraph.posterior_model(fit)
        if method not in ('blocked', 'collapsed', 'de'):
            raise ValueError(
                "global_posterior=True requires method='blocked', 'collapsed' or 'de'; "
                "the ensemble, slice and mcmc backends sample fit.model only."
            )
        sample_model.update_model()

    # Settings carry every sampler's knobs -- the dialog keeps them per sampler
    # so switching back and forth does not lose them -- and a sampler must not
    # be handed another one's. Anything it does not accept is dropped here, with
    # the per-sampler block for the chosen one merged in.
    sampler_settings = kwargs.pop('samplers', None) or {}
    # One canonical name from here on: the raw string is a hand-editable YAML
    # value, and 'Blocked' or 'mcmC' used to fall through to the ensemble
    # sampler in silence (RF-782).
    method = cs.core.fitting.sample.resolve_sampler(method)
    if isinstance(sampler_settings, dict):
        kwargs.update(sampler_settings.get(method, {}) or {})
    accepted = set(
        inspect.signature(cs.core.fitting.sample.sampler_function(method)).parameters
    )
    # Arguments this function supplies itself. A setting of the same name would
    # arrive twice at the call below ("got multiple values for keyword argument
    # 'nwalkers'"), so the run keeps ownership of them -- except the ensemble
    # size, which is genuinely worth overriding and is read back below.
    owned = {
        'fit', 'model', 'steps', 'thin', 'chi2max', 'step_size', 'temp',
        'callback', 'check_cancel', 'progress_bar',
    }
    requested_walkers = kwargs.pop('nwalkers', None)
    dropped = sorted(set(kwargs) - accepted)
    if dropped:
        cs.logging.info(
            "%s does not take %s; ignoring", method, ", ".join(dropped)
        )
    kwargs = {k: v for k, v in kwargs.items() if k in accepted and k not in owned}

    # save initial parameter values
    pv = sample_model.parameter_values
    
    # Create timestamped directory
    timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    sampling_dir = os.path.join(target_directory, timestamp)
    os.makedirs(sampling_dir, exist_ok=True)
    
    # Save project state (full save)
    from chisurf.macros.core_fit import save_project
    save_project(target_path=sampling_dir, project_name="project")
    
    # Save parameters metadata
    params_meta = cs.core.fitting.sampling_meta.get_sampling_metadata(fit)
    params_path = os.path.join(sampling_dir, "parameters.json")
    with open(params_path, "w") as f:
        json.dump(params_meta, f, indent=4)
        
    chains_dir = os.path.join(sampling_dir, "chains")
    os.makedirs(chains_dir, exist_ok=True)

    if chain_format is None:
        try:
            chain_format = cs.core.settings.cs_settings['optimization']['sampling'].get(
                'chain_format', 'er4'
            )
        except (KeyError, TypeError):
            chain_format = 'er4'
    chain_format = str(chain_format or 'er4').strip().lower()
    if chain_format not in CHAIN_FORMATS:
        cs.logging.warning(
            "unknown chain format %r; writing %s", chain_format, 'er4'
        )
        chain_format = 'er4'
    chain_suffix = CHAIN_FORMATS[chain_format]

    def chain_frame(r):
        """Return a sampling result as one row per draw.

        Parameters
        ----------
        r : dict
            Result dict with ``'chi2r'``, ``'parameter_values'``,
            ``'parameter_names'`` and optionally ``'lnprior'``.

        Returns
        -------
        names : list of str
            Column names: ``chi2r``, ``lnprior``, then the parameters.
        rows : numpy.ndarray
            Finite draws, shape ``(n_draws, 2 + n_parameters)``.
        """
        chi2 = np.asarray(r['chi2r'], dtype=np.float64)
        parameter_values = np.asarray(r['parameter_values'], dtype=np.float64)
        lnprior = r.get('lnprior')
        if lnprior is None:
            lnprior = np.zeros_like(chi2)
        lnprior = np.asarray(lnprior, dtype=np.float64)

        keep = np.isfinite(chi2)
        rows = np.column_stack([chi2[keep], lnprior[keep], parameter_values[keep]])
        return ['chi2r', 'lnprior'] + list(r['parameter_names']), rows

    def save_chain_to_hdf5(r, fn_target):
        """Save a sampling result to an HDF5 table, one dataset per column.

        Text chains are the default because they need nothing to read, but they
        are also the reason a long run fills a disk: every number costs ~25
        characters where a float64 costs 8, before compression. A chain worth
        keeping is usually one that ran long enough for that to matter.

        Written at the file root, which is where the readers that matter --
        nDXplorer's among them -- look first.

        Parameters
        ----------
        r : dict
            Result dict, see :func:`chain_frame`.
        fn_target : str
            Target file path.
        """
        from chisurf.core.datastore import write_table

        names, rows = chain_frame(r)
        write_table(fn_target, {name: rows[:, i] for i, name in enumerate(names)})

    def save_chain_to_file(r, fn_target):
        """Save a sampling result dict to a tab-separated text file.

        The data misfit and the prior are written as separate columns: mixing
        them would make ``chi2r`` unusable as a goodness-of-fit number whenever
        an informative prior is attached, and keeping ``lnprior`` lets the
        stored posterior be reweighted under a different prior afterwards
        without resampling.

        Parameters
        ----------
        r : dict
            Result dict with keys ``'chi2r'``, ``'parameter_values'``,
            ``'parameter_names'`` and optionally ``'lnprior'``.
        fn_target : str
            Target file path.
        """
        names, rows = chain_frame(r)
        cs.core.fio.ascii.Csv().save(
            rows.T,
            fn_target,
            delimiter='\t',
            file_type='txt',
            header="\t".join(names)
        )

    def save_chain(r, fn_target):
        """Write a chain in the configured format.

        Parameters
        ----------
        r : dict
            Result dict, see :func:`chain_frame`.
        fn_target : str
            Target file path; its suffix already matches the format.
        """
        if chain_format == 'hdf5':
            save_chain_to_hdf5(r, fn_target)
        else:
            save_chain_to_file(r, fn_target)

    total_steps = int(n_runs * steps)
    done_steps = 0
    run_results: typing.List[dict] = []

    success = True
    # Sanitize fit name for use in filenames
    safe_fit_name = "".join([c if c.isalnum() or c in (' ', '_', '-') else '_' for c in fit.name]).strip().replace(' ', '_')
    for i_run in range(n_runs):
        if check_cancel and check_cancel():
            success = False
            break
            
        base_fn = f"{safe_fit_name}_{i_run}"
        fn_final = os.path.join(chains_dir, base_fn + chain_suffix)
        fn_partial = os.path.join(chains_dir, base_fn + '.partial' + chain_suffix)

        def sampler_callback(done, run_total, sampler=None, result=None,
                             **cb_kwargs):
            """Callback invoked during sampling for intermediate saves.

            Parameters
            ----------
            done : int
                Number of completed steps in the current run.
            run_total : int
                Total steps in the current run.
            sampler : chisurf.core.fitting.ensemble.EnsembleSampler, optional
                The ensemble sampler instance, used to extract intermediate
                chains when not None (the Python samplers' route).
            result : dict, optional
                A partial result dict, already in the samplers' return shape
                (the C++ graph route delivers one per segment).
            """
            if result is not None:
                # Partial save of the C++ sampler's chain so far.
                try:
                    save_chain(result, fn_partial)
                except Exception:
                    pass
            elif sampler is not None:
                # Partial save of an unfinished ensemble chain.
                try:
                    r_partial = cs.core.fitting.sample.ensemble_result(sampler, fit)
                    save_chain(r_partial, fn_partial)
                except Exception:
                    pass

            if progress_callback is not None:
                current_total_done = done_steps + done
                progress_callback(current_total_done, total_steps)

        if method == 'de':
            r = cs.core.fitting.sample.sample_differential_evolution(
                fit=fit,
                steps=steps,
                thin=thin,
                chi2max=chi2max,
                temp=temp,
                callback=sampler_callback,
                check_cancel=check_cancel,
                model=sample_model,
                **kwargs
            )
        elif method == 'collapsed':
            r = cs.core.fitting.sample.sample_marginal_shared(
                fit=fit,
                steps=steps,
                thin=thin,
                step_size=step_size,
                temp=temp,
                check_cancel=check_cancel,
                model=sample_model,
                **kwargs
            )
        elif method == 'blocked':
            # Independent sub-problems are sampled apart and merged exactly;
            # with a single component this is the plain blocked walk.
            r = cs.core.fitting.sample.sample_independent_components(
                fit=fit,
                steps=steps,
                thin=thin,
                chi2max=chi2max,
                step_size=step_size,
                temp=temp,
                callback=sampler_callback,
                check_cancel=check_cancel,
                model=sample_model,
                **kwargs
            )
        elif method == 'mcmc':
            r = cs.core.fitting.sample.walk_mcmc(
                fit=fit,
                steps=steps,
                thin=thin,
                chi2max=chi2max,
                step_size=step_size,
                temp=temp,
                callback=sampler_callback,
                check_cancel=check_cancel,
                **kwargs
            )
        elif method == 'slice':
            r = cs.core.fitting.sample.sample_ensemble_slice(
                fit,
                steps=steps,
                nwalkers=int(requested_walkers or max(int(fit.n_free * 2) + 2, 10)),
                thin=thin,
                chi2max=chi2max,
                callback=sampler_callback,
                check_cancel=check_cancel,
                **kwargs
            )
        else:  # 'ensemble' (and the legacy name 'emcee')
            # Ensure at least 10 walkers and at least 2*ndim+2 for robustness,
            # unless the settings ask for a specific ensemble size.
            n_walkers = int(requested_walkers or max(int(fit.n_free * 2) + 2, 10))
            r = cs.core.fitting.sample.sample_ensemble(
                fit,
                steps=steps,
                nwalkers=n_walkers,
                thin=thin,
                chi2max=chi2max,
                callback=sampler_callback,
                check_cancel=check_cancel,
                **kwargs
            )

        if success:
            save_chain(r, fn_final)
            run_results.append(r)

            if os.path.exists(fn_partial):
                try:
                    os.remove(fn_partial)
                except Exception:
                    pass

        done_steps += steps
        if progress_callback:
            progress_callback(done_steps, total_steps)

    diagnostics = _write_sampling_diagnostics(
        run_results, sample_model, os.path.join(sampling_dir, "diagnostics.json")
    )
    # Leave the report on the fit so ``posterior_summary`` can quote credible
    # intervals from the chain instead of only the covariance or a profile scan.
    # What was sampled is ``fit.model``, which for a group is the *selected*
    # member's model -- so that member owns the report too, and shows it in the
    # per-member text a group's ``__str__`` is assembled from.
    fit.sampling_diagnostics = diagnostics
    # Keep the draws themselves, not only their summary. Asking what the
    # posterior would be under a different prior is a reweighting of these exact
    # points and costs no model evaluation at all
    # (:mod:`chisurf.core.fitting.reweight`) -- but only while the draws are in
    # hand. Recovering them from the chain files afterwards is possible and
    # tedious, and the summary alone cannot answer it at any price.
    chain = pool_chains(run_results)
    sampling_chain = None
    if chain is not None:
        burn_in = int((diagnostics or {}).get('burn_in', 0) or 0)
        burn_in = max(0, min(burn_in, chain.shape[1] - 1))
        kept = chain[:, burn_in:, :]
        sampling_chain = {
            'parameter_names': list(sample_model.parameter_names),
            'parameter_values': kept.reshape(-1, kept.shape[2]),
            'chains': kept,
            'burn_in': burn_in,
        }
    fit.sampling_chain = sampling_chain

    selected = getattr(fit, 'selected_fit', None)
    if selected is not None and selected is not fit:
        selected.sampling_diagnostics = diagnostics
        selected.sampling_chain = sampling_chain

    # restore initial parameter values
    sample_model.parameter_values = pv
    sample_model.update()
    return diagnostics


def pool_chains(
        run_results: typing.Sequence[dict]
) -> typing.Optional[np.ndarray]:
    """Stack the chains of several independent sampling runs.

    ``sample_fit`` performs ``n_runs`` independent runs and used to write each to
    its own file and forget about them. Independent runs are exactly what a
    cross-chain R-hat is computed from, so pooling them is what turns them from
    redundant work into evidence.

    Runs of unequal length (one was cancelled) are truncated to the shortest, so
    every pooled chain covers the same number of draws.

    Parameters
    ----------
    run_results : sequence of dict
        Result dicts carrying a ``chains`` entry of shape
        ``(n_chains, n_draws, n_parameters)``.

    Returns
    -------
    numpy.ndarray or None
        ``(total_chains, n_draws, n_parameters)``, or ``None`` when no run
        provided usable chains.
    """
    blocks = []
    for r in run_results:
        c = r.get('chains') if isinstance(r, dict) else None
        if c is None:
            continue
        c = np.asarray(c, dtype=np.float64)
        if c.ndim == 3 and c.shape[0] and c.shape[1]:
            blocks.append(c)
    if not blocks:
        return None
    n_draws = min(b.shape[1] for b in blocks)
    n_par = min(b.shape[2] for b in blocks)
    return np.concatenate(
        [b[:, :n_draws, :n_par] for b in blocks], axis=0
    )


def _write_sampling_diagnostics(
        run_results: typing.Sequence[dict],
        model: cs.core.models.Model,
        path: str
) -> typing.Optional[dict]:
    """Summarise the pooled runs, write ``diagnostics.json`` and log the warnings.

    Parameters
    ----------
    run_results : sequence of dict
        The per-run result dicts.
    model : chisurf.core.models.Model
        Model that was sampled; supplies the parameter names.
    path : str
        Where to write the JSON report.

    Returns
    -------
    dict or None
        The report, or ``None`` when there were no chains to summarise.
    """
    chains = pool_chains(run_results)
    if chains is None:
        return None

    names = list(model.parameter_names)
    summary = cs.core.fitting.diagnostics.summarize(chains, names=names)
    warnings = cs.core.fitting.diagnostics.convergence_warnings(summary)
    acceptance = [
        float(r['acceptance_rate']) for r in run_results
        if isinstance(r, dict) and np.isfinite(r.get('acceptance_rate', np.nan))
    ]
    report = {
        'n_runs': len(run_results),
        'n_chains': int(chains.shape[0]),
        'n_draws': int(chains.shape[1]),
        'burn_in': summary[0]['burn_in'] if summary else 0,
        'acceptance_rate': float(np.mean(acceptance)) if acceptance else None,
        'parameters': summary,
        'warnings': warnings,
    }
    try:
        with open(path, "w") as f:
            json.dump(report, f, indent=4)
    except OSError as e:
        cs.logging.warning(f"could not write sampling diagnostics: {e}")

    for message in warnings:
        cs.logging.warning(f"sampling: {message}")
    if not warnings:
        cs.logging.info(
            "sampling: no convergence problems detected "
            f"({report['n_chains']} chains x {report['n_draws']} draws)"
        )
    return report


#@nb.jit#(nopython=True)
#: Relative finite-difference step for :func:`approx_grad`. The square root of
#: the machine epsilon is the standard optimum for a forward difference: it
#: balances the truncation error (linear in the step) against the cancellation
#: error (inversely proportional to it).
FINITE_DIFFERENCE_STEP = float(np.sqrt(np.finfo(float).eps))


def approx_grad(
        xk: np.array,
        fit: cs.core.fitting.fit.Fit,
        epsilon: float = None,
        args=(),
        f0=None,
        model: cs.core.models.Model = None
) -> typing.Tuple[float, np.array]:
    """Approximate gradient of the weighted residuals with respect to ``xk``.

    Parameters
    ----------
    xk : array_like
        Parameter values around which the gradient is estimated.
    fit : Fit
        Fit providing :meth:`Fit.get_wres` and a model.
    epsilon : float, optional
        **Relative** finite-difference step. The step taken for parameter ``k``
        is ``epsilon * max(|xk[k]|, 1)``. Defaults to
        :data:`FINITE_DIFFERENCE_STEP`.
    args : tuple, optional
        Unused; kept so existing call sites keep working.
    f0 : array_like, optional
        Pre-computed weighted residuals at ``xk``.
    model : chisurf.core.models.Model, optional
        Model to differentiate; defaults to ``fit.model``, which for a
        :class:`FitGroup` is the *selected member's* model rather than the
        global one.

    Returns
    -------
    (numpy.ndarray, numpy.ndarray)
        Tuple ``(f0, grad)`` where ``grad`` has shape
        ``(len(xk), len(f0))``.

    Notes
    -----
    The step must scale with the parameter: an absolute step is meaningless
    across the range of magnitudes fluorescence models use. A fixed step of
    ``1e-12`` added to an amplitude of order ``1e6`` is lost entirely to
    rounding, the difference evaluates to exactly zero, and the parameter then
    looks as though it has no influence on the model at all.
    """
    if epsilon is None:
        epsilon = FINITE_DIFFERENCE_STEP
    if model is None:
        model = fit.model
    p0 = model.parameter_values

    def f(values):
        """Weighted residuals of ``model`` at a parameter vector."""
        return get_wres(values, model)
    xk = np.asarray(xk, dtype=float)
    n_xk = len(xk)
    if f0 is None:
        f0 = f(xk)
    i = len(f0)
    grad = np.zeros((n_xk, i, ), float)
    ei = np.zeros((n_xk, ), float)

    for k in range(n_xk):
        step = epsilon * max(abs(float(xk[k])), 1.0)
        # Round the step to an exactly representable difference so that the
        # divisor below is the step the model actually saw.
        step = (xk[k] + step) - xk[k]
        ei[k] = 1.0
        d = step * ei
        grad[k] = (f(xk + d) - f0) / step
        ei[k] = 0.0

    # Restore *and* recompute. Assigning the values alone leaves the model's
    # arrays holding the last perturbation, and a later evaluation at these same
    # values then correctly concludes that nothing changed and skips the update
    # -- serving residuals that belong to a different parameter vector. That is
    # latent whenever anything caches on "did a value change", which the
    # selective global update and the residual cache both do.
    model.parameter_values = p0
    model.update_model()
    return f0, grad


def _error_scale(fit) -> float:
    """Correction for data that carries no uncertainties of its own.

    `covariance_matrix` returns ``(J'J)^-1`` for ``J = d(weighted residuals)/dp``.
    That is the parameter covariance **only when the weights are real standard
    deviations** -- weighted least squares, the assumption
    :func:`calculate_weighted_residuals` documents for its ``"default"`` noise
    model, and what ``scipy.optimize.curve_fit(absolute_sigma=True)`` computes.

    `DataCurve` sets ``ey`` to **ones** whenever none is supplied, which
    includes the ordinary case of a two-column ``x, y`` file
    (``chisurf/core/data.py``, five sites). The residuals are then not weighted
    by anything and the covariance comes out in units of "a residual of 1", so
    the reported errors are wrong by a factor ``1/sqrt(chi2r)``. Measured on a
    400-point exponential with sigma = 0.05 and no ``ey``: 0.078 / 0.291 /
    0.375 reported against 0.0036 / 0.0133 / 0.0171 correct -- **22x too
    large**.

    When sigma is unknown the standard treatment is to estimate it from the
    residuals, which scales the covariance by ``chi2r``; that is what
    ``curve_fit`` does by default and what gnuplot and Origin report. So the
    scale is applied *only* when the data supplies no uncertainties, detected
    as ``ey`` being exactly one everywhere. A dataset with genuine errors is
    untouched, and its error bars do not move.

    The narrow risk is a dataset whose true sigma really is exactly 1.0 at
    every point; its errors would now be scaled. That is both vanishingly
    unlikely and self-diagnosing -- if sigma were truly 1 the scale would be
    sqrt(chi2r) ~= 1 and the correction would do nothing. It only bites when
    the data already contradicts the sigma = 1 claim.
    """
    try:
        ey = np.asarray(fit.data.ey, dtype=float)
    except Exception:
        return 1.0
    if ey.size == 0 or not np.all(ey == 1.0):
        return 1.0          # real uncertainties: the covariance is already right
    try:
        chi2r = float(fit.chi2r)
    except Exception:
        return 1.0
    if not np.isfinite(chi2r) or chi2r <= 0.0:
        return 1.0
    return float(np.sqrt(chi2r))


def covariance_matrix(
        fit: cs.core.fitting.fit.Fit,
        epsilon: float = None,
        model: cs.core.models.Model = None,
        f0: np.ndarray = None,
        **kwargs
) -> typing.Tuple[np.array, typing.List[int]]:
    """Estimate the covariance matrix of the fit parameters.

    With ``J = d(weighted residuals)/dp``, the curvature matrix of
    ``chi2 = sum(wres**2)`` is ``alpha = J'J`` and the parameter covariance is
    its inverse. (The factor of one half that appears in textbook definitions
    belongs to ``alpha`` relative to the chi² Hessian, which is ``2*alpha`` --
    it must not be applied a second time here.)

    Parameters
    ----------
    fit : Fit
        The fit whose model and residuals are used.
    epsilon : float, optional
        Relative step size for the numerical gradient, see :func:`approx_grad`.
    model : chisurf.core.models.Model, optional
        Model whose parameters the covariance is over; defaults to ``fit.model``,
        which for a :class:`FitGroup` is the *selected member's* model.
    **kwargs
        Ignored; accepted so callers may pass through unrelated options.

    Returns
    -------
    cov_m : numpy.ndarray
        Approximate covariance matrix of important parameters.
    important_parameters : list of int
        Indices of parameters whose partial derivatives are non-zero.
    """
    if model is None:
        model = fit.model
    # The graph first, when the model builds one: the same arithmetic at the
    # same step rule, but in C++ with the data already in the node, instead
    # of `p + 1` trips through `Model.update_model()`. Every caller of this
    # function gets that -- the error estimate, the posterior view, the
    # derived-quantity propagation, the sampler preconditioners -- because
    # the choice is made here rather than at six call sites. A model the
    # graph cannot represent falls through to the numpy path below, which is
    # the definition of the answer and stays the reference the C++ routine is
    # pinned against.
    over_the_graph = cs.core.fitting.minimizer.curvature_over_the_graph(
        fit, model, epsilon)
    if over_the_graph is not None:
        return over_the_graph
    xk = np.array(model.parameter_values)
    # `f0` is the residuals at `xk`. Supplied by a caller that has just
    # evaluated the model there, it saves the first of the p+2 evaluations
    # this function costs -- and it is the *same* number, not an
    # approximation of it: the gradient comes out bit-identical (verified at
    # rtol=0, atol=0). Only a caller that can guarantee the model is current
    # for `xk` may pass it; everyone else leaves it None and pays for the
    # evaluation, which is why this is not simply read from the model here.
    fi_v, partial_derivatives = approx_grad(
        xk, fit, epsilon, model=model, f0=f0)

    # find parameters which do not change the models
    # use only parameters which change the models
    important_parameters = list()
    for k, pd_k in enumerate(partial_derivatives):
        if (pd_k**2).sum() > 0.0:
            important_parameters.append(k)

    pdi = partial_derivatives[important_parameters]
    n_important_parameters = len(important_parameters)
    m = np.zeros((n_important_parameters, n_important_parameters), float)

    for i_alpha in range(n_important_parameters):
        da_alpha = pdi[i_alpha]
        for i_beta in range(n_important_parameters):
            da_beta = pdi[i_beta]
            m[i_alpha, i_beta] = ((da_alpha * da_beta)).sum()
    try:
        cov_m = scipy.linalg.pinvh(m)
    except (scipy.linalg.LinAlgError, np.linalg.LinAlgError) as e:
        cs.logging.debug(f"Failed to compute covariance matrix: {e}")
        # np.zeros_like((n, n)) would build a length-2 vector from the shape
        # tuple rather than an n x n matrix.
        cov_m = np.zeros(
            (n_important_parameters, n_important_parameters),
            dtype=float
        )
    return cov_m, important_parameters


def _apply_fit_mask(
        model: cs.core.models.Model,
        wres: np.array
) -> np.array:
    """Apply an optional Fit-level mask to a residual vector.

    The mask is taken from ``model.fit.mask`` if available. Boolean masks are
    interpreted as 0/1 inclusion weights; numeric masks are used as
    multiplicative weights. The mask is truncated to the residual length.
    """

    if wres is None:
        return wres

    fit = getattr(model, "fit", None)
    if fit is None:
        return wres

    mask = getattr(fit, "mask", None)
    if mask is None:
        return wres

    try:
        m = np.asarray(mask, dtype=float).ravel()
    except Exception:
        return wres
    if m.ndim != 1 or m.size == 0:
        return wres

    try:
        xmin = int(getattr(fit, "xmin", 0))
        xmax = int(getattr(fit, "xmax", xmin + int(len(wres))))
    except Exception:
        return wres

    if xmax < xmin:
        xmin, xmax = xmax, xmin

    xmin = max(0, xmin)
    xmax = min(m.size, max(xmin, xmax))
    window_len = max(0, xmax - xmin)
    if window_len == 0 or len(wres) == 0:
        return wres

    n = len(wres)
    if window_len != n:
        return wres

    wres = np.array(wres, copy=True)
    w_slice = m[xmin:xmax]
    wres *= w_slice
    return wres


def _closest_quantile(
        quantiles: typing.Dict[str, float],
        target: float,
        tolerance: float = 0.02
) -> typing.Optional[float]:
    """Return the stored quantile nearest ``target``, or ``None`` if none is close.

    A summary carries a fixed ladder of quantiles (2.5/16/50/84/97.5 %), so a
    request for a 68 % interval matches the 16/84 pair exactly while an unusual
    coverage has no honest answer and returns ``None`` rather than an
    interpolation the sample may not support.

    Parameters
    ----------
    quantiles : dict
        Mapping of probability (as a string) to value.
    target : float
        Requested probability.
    tolerance : float, optional
        Largest acceptable difference in probability.

    Returns
    -------
    float or None
        The value at the closest stored probability.
    """
    best, best_gap = None, tolerance
    for key, value in quantiles.items():
        try:
            gap = abs(float(key) - target)
        except (TypeError, ValueError):
            continue
        if gap <= best_gap:
            best, best_gap = value, gap
    return None if best is None else float(best)


def _smooth_prior(parameter) -> typing.Optional[cs.core.fitting.priors.Prior]:
    """Return a parameter's prior, but only when it is more than its bounds.

    A *bounded* parameter reports a
    :class:`~chisurf.core.fitting.priors.UniformPrior` synthesised from its
    bounds, which contributes nothing beyond the hard box that the optimiser
    (and the sampler's cheap bound check) already enforces. Building that object
    for every bounded parameter on every objective evaluation is pure overhead,
    so this helper returns ``None`` unless a genuine prior is stored.

    Both stores must be consulted: a distribution prior mirrors a serialisable
    spec onto the chinet port, but a *callback* prior is runtime-only and
    deliberately leaves ``port.prior`` as ``None`` while keeping the live object
    on the parameter. Checking only the port silently drops callback priors.

    Parameters
    ----------
    parameter : chisurf.core.fitting.parameter.FittingParameter
        Parameter to inspect.

    Returns
    -------
    chisurf.core.fitting.priors.Prior or None
        The stored prior, or ``None`` when the parameter only carries bounds.
    """
    live = getattr(parameter, "_prior", None)
    port = getattr(parameter, "_port", None)
    spec = getattr(port, "prior", None) if port is not None else None
    if live is None and spec is None:
        return None
    return getattr(parameter, "prior", None)


def _prior_residuals(
        model: cs.core.models.Model
) -> np.array:
    """Return the concatenated prior-residual contributions of a model.

    Each free parameter that carries a prior contributes its
    :meth:`~chisurf.core.fitting.priors.Prior.residuals` at the parameter's
    current value. Appending these to the data residuals makes a least-squares
    (Levenberg-Marquardt) fit minimise the negative log-posterior, i.e. it
    performs maximum-a-posteriori estimation. Uniform (box) priors contribute
    nothing here because they are enforced as hard optimiser bounds.

    Parameters
    ----------
    model : cs.core.models.Model
        Model whose free :attr:`parameters` are inspected for priors.

    Returns
    -------
    numpy.ndarray
        A 1-D array of prior residuals (possibly empty).
    """
    pieces = []
    for p in getattr(model, "parameters", []):
        prior = _smooth_prior(p)
        if prior is None:
            continue
        try:
            r = np.asarray(prior.residuals(float(p.value)), dtype=np.float64).ravel()
        except Exception:
            continue
        if r.size:
            pieces.append(r)
    if not pieces:
        return np.empty(0, dtype=np.float64)
    return np.concatenate(pieces)


def get_wres(
        parameter_values: typing.List[float],
        model: cs.core.models.Model,
        include_priors: bool = False
) -> np.array:
    """Return weighted residuals for a list of model parameters.

    Parameters
    ----------
    parameter_values : list of float
        Parameter values to assign before computing residuals. If the list
        is empty, the model is not updated.
    model : cs.core.models.Model
        Model providing :attr:`weighted_residuals`.
    include_priors : bool, optional
        If *True*, append per-parameter prior residuals (see
        :func:`_prior_residuals`) so the optimiser performs maximum-a-posteriori
        estimation. Goodness-of-fit reporting (:func:`get_chi2`) leaves this
        *False* so the reported chi² reflects the data misfit only.
    """
    if len(parameter_values) > 0:
        model.parameter_values = parameter_values
        model.update_model()
    wres = model.weighted_residuals
    wres = _apply_fit_mask(model, wres)
    if include_priors:
        pr = _prior_residuals(model)
        if pr.size:
            wres = np.concatenate(
                [np.asarray(wres, dtype=np.float64).ravel(), pr]
            )
    return wres


def get_chi2(
        parameter_values: typing.List[float],
        model: cs.core.models.model.ModelCurve,
        reduced: bool = True
) -> float:
    """Return either the reduced chi² or the sum of squares (chi²).

    Parameters
    ----------
    parameter_values : list of float
        Parameter values to apply before computing residuals. If the list
        is empty, the model is not updated.
    model : cs.core.models.ModelCurve
        Model providing :attr:`weighted_residuals`, :attr:`n_points` and
        :attr:`n_free`.
    reduced : bool, optional
        If *True*, return the reduced chi², i.e. chi² divided by
        ``(n_points - n_free - 1)``.

    Examples
    --------
    Use a tiny dummy model with three residuals:

    >>> import numpy as np
    >>> class _DummyModel:
    ...     def __init__(self):
    ...         self._wres = np.array([1.0, -1.0, 0.0])
    ...         self.n_points = self._wres.size
    ...         self.n_free = 1
    ...     @property
    ...     def weighted_residuals(self):
    ...         return self._wres
    ...     @property
    ...     def parameter_values(self):
    ...         return []
    ...     @parameter_values.setter
    ...     def parameter_values(self, v):
    ...         pass
    ...     def update_model(self):
    ...         pass
    >>> m = _DummyModel()
    >>> float(round(get_chi2([], m, reduced=False), 1))
    2.0
    >>> float(round(get_chi2([], m, reduced=True), 1))
    2.0
    """
    chi2 = (get_wres(parameter_values, model)**2.0).sum()
    chi2 = np.inf if np.isnan(chi2) else chi2
    chi2r = chi2 / float(model.n_points - model.n_free - 1.0)
    if reduced:
        return chi2r
    else:
        return chi2


def lnprior(
        parameter_values: typing.List[float],
        fit: cs.core.fitting.fit.Fit,
        bounds: typing.List[
            typing.Tuple[float, float]
        ] = None,
        model: cs.core.models.Model = None
) -> float:
    """Log-prior probability of a set of parameter values.

    The prior is the sum of the per-parameter log densities
    :meth:`chisurf.core.fitting.priors.Prior.lnpdf` over the fit's free
    parameters. Bounds are the
    :class:`~chisurf.core.fitting.priors.UniformPrior` special case of a prior,
    so ``bounds`` is an *additional*, cheap box rejection rather than a
    replacement: it is checked first and short-circuits to ``-inf`` before any
    parameter prior (or, via :func:`lnprob`, any model evaluation) is touched.
    Parameters whose only prior is that box are then skipped, because the box
    has already been enforced.

    ``bounds`` used to suppress the parameter priors entirely, which silently
    dropped every informative prior from the sampled posterior while
    maximum-a-posteriori estimation (:func:`_prior_residuals`) still honoured
    them -- optimiser and sampler targeted different distributions.

    Parameters
    ----------
    parameter_values : list of float
        Parameter values to be tested, in the order of the fit's free
        parameters.
    fit : Fit
        Fit providing the free parameters and their priors. May be *None*, in
        which case only ``bounds`` contributes.
    bounds : list of (float, float), optional
        Explicit box bounds, checked before the priors. When omitted, the box
        arrives through each parameter's own uniform prior instead.
    model : chisurf.core.models.Model, optional
        Model whose free parameters ``parameter_values`` refers to. Defaults to
        ``fit.model`` -- which for a
        :class:`~chisurf.core.fitting.fit.FitGroup` is the *selected member's*
        model, not the global one. Pass
        :func:`chisurf.core.fitting.factorgraph.posterior_model` to evaluate the
        joint posterior of a group instead.

    Examples
    --------
    >>> bounds = [(0.0, 2.0), (None, 1.0)]
    >>> round(lnprior([1.0, 0.5], fit=None, bounds=bounds), 1)
    0.0
    >>> lnprior([3.0, 0.5], fit=None, bounds=bounds)
    -inf
    """
    if bounds is not None:
        for (bound, value) in zip(bounds, parameter_values):
            lb, ub = bound
            if lb is not None and value < lb:
                return -np.inf
            if ub is not None and value > ub:
                return -np.inf

    if model is None:
        model = getattr(fit, "model", None)
    if model is None:
        return 0.0

    params = list(getattr(model, "parameters", []))
    if bounds is None:
        # No box was applied above, so every prior -- including the uniform ones
        # standing in for bounds -- has to contribute.
        priors = [getattr(p, "prior", None) for p in params]
    else:
        priors = [_smooth_prior(p) for p in params]

    lp = 0.0
    for pr, value in zip(priors, parameter_values):
        if pr is None:
            continue
        lp += pr.lnpdf(float(value))
        if not np.isfinite(lp):
            return -np.inf
    return lp


def lnprob_parts(
        parameter_values: typing.List[float],
        fit: Fit,
        chi2max: float = float("inf"),
        bounds: typing.List[
            typing.Tuple[float, float]
        ] = None,
        model: cs.core.models.Model = None
) -> typing.Tuple[float, float, float]:
    """Return the log-likelihood, log-prior and chi² of a parameter vector.

    The three terms that :func:`lnprob` adds up, kept apart. Samplers record
    them separately so that a chain carries the *data* misfit (``chi2``) rather
    than a mixture of misfit and prior, and so that the posterior can afterwards
    be reweighted under a different prior without resampling.

    Parameters
    ----------
    parameter_values : list of float
        Parameter values at which to evaluate the posterior.
    fit : Fit
        Fit providing the model, the parameter priors and the default bounds.
    chi2max : float, optional
        Hard cutoff on chi²; above it the log-likelihood is ``-inf``.
    bounds : list of (float, float), optional
        Explicit box bounds, checked before the model is evaluated.
    model : chisurf.core.models.Model, optional
        Model to evaluate; defaults to ``fit.model``. See :func:`lnprior`.

    Returns
    -------
    tuple of float
        ``(lnlike, lnprior, chi2)``. When the prior rejects the vector the
        model is never evaluated and ``(-inf, -inf, inf)`` is returned.
    """
    if model is None:
        model = fit.model
    lp = lnprior(parameter_values, fit, bounds=bounds, model=model)
    if not np.isfinite(lp):
        return float("-inf"), float("-inf"), float("inf")
    chi2 = get_chi2(parameter_values, model=model, reduced=False)
    lnlike = -0.5 * chi2 if chi2 < chi2max else -np.inf
    return float(lnlike), float(lp), float(chi2)


def lnprob(
        parameter_values: typing.List[float],
        fit: Fit,
        chi2max: float = float("inf"),
        bounds: typing.List[
            typing.Tuple[float, float]
        ] = None,
        model: cs.core.models.Model = None
) -> float:
    """Log-posterior probability for use in MCMC sampling.

    The posterior is given by ``lnprior + lnlikelihood`` where the
    likelihood is assumed to be Gaussian in the residuals, i.e.

    ``lnlikelihood = -0.5 * chi2``

    and ``chi2`` is obtained from :func:`get_chi2`. Use :func:`lnprob_parts`
    when the two terms are needed separately.

    Parameters
    ----------
    parameter_values : list of float
        Parameter values at which to evaluate the posterior.
    fit : Fit
        Fit providing the model, the parameter priors and default bounds.
    chi2max : float, optional
        Hard cutoff on chi²; values above this threshold return ``-inf``.
    bounds : list of (float, float), optional
        Explicit box bounds, checked before the model is evaluated. This does
        *not* replace the parameter priors -- see :func:`lnprior`.
    model : chisurf.core.models.Model, optional
        Model to evaluate; defaults to ``fit.model``. See :func:`lnprior`.

    Examples
    --------
    >>> import numpy as np
    >>> class _DummyModel:
    ...     def __init__(self):
    ...         self._wres = np.array([1.0, -1.0, 0.0])
    ...         self.n_points = self._wres.size
    ...         self.n_free = 1
    ...     @property
    ...     def weighted_residuals(self):
    ...         return self._wres
    ...     @property
    ...     def parameter_values(self):
    ...         return []
    ...     @parameter_values.setter
    ...     def parameter_values(self, v):
    ...         pass
    ...     def update_model(self):
    ...         pass
    >>> class _DummyFit:
    ...     def __init__(self):
    ...         self.model = _DummyModel()
    >>> fit = _DummyFit()
    >>> bounds = [(0.0, 2.0)]
    >>> val = lnprob([1.0], fit, chi2max=10.0, bounds=bounds)
    >>> bool(isinstance(val, float) and np.isfinite(val))
    True
    >>> lnprob([10.0], fit, chi2max=10.0, bounds=bounds)
    -inf
    """
    lnlike, lp, _ = lnprob_parts(
        parameter_values,
        fit,
        chi2max=chi2max,
        bounds=bounds,
        model=model
    )
    if not np.isfinite(lp):
        return float("-inf")
    return lnlike + lp

