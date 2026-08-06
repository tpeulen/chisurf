from __future__ import annotations
from chisurf import typing
import chisurf as cs

import threading
import numpy as np
from typing import TYPE_CHECKING

import chisurf.core.decorators
import chisurf.core.parameter

from chisurf.core.curve import Curve
from chisurf.core.models import model

if TYPE_CHECKING:
    from chisurf.core.fitting.fit import Fit, FitGroup


class GlobalFitModel(model.Model, Curve):

    name = "Global fit"
    view_spec_file = "globalfit.view.json"

    @property
    def weighted_residuals(self) -> np.ndarray:
        """Concatenated weighted residuals from all local fits.

        Only the members whose model was actually recomputed are re-evaluated:
        the rest are served from the per-member cache that
        :meth:`update_model` invalidates. Without this the selective update was
        half an optimisation -- the models were skipped but their residuals were
        recomputed anyway, which is where the remaining per-evaluation cost sat.

        Returns
        -------
        np.ndarray
            1-D array of weighted residuals, or empty.
        """
        n = len(self.fits)
        if n == 0:
            return np.array([], dtype=np.float64)

        token = self._window_token()
        cache = self.__dict__.get("_residual_cache")
        if cache is None or cache[0] != token or len(cache[1]) != n:
            # A window changed (or the group did): nothing cached still applies.
            cache = (token, [None] * n)
            self._residual_dirty = set(range(n))
        dirty = getattr(self, "_residual_dirty", None)
        if dirty is None:
            dirty = set(range(n))

        pieces = cache[1]
        for i, f in enumerate(self.fits):
            if i in dirty or pieces[i] is None:
                pieces[i] = f.model.weighted_residuals.flatten()
        self.__dict__["_residual_cache"] = (token, pieces)
        self._residual_dirty = set()
        return np.concatenate(pieces)

    #: Name typed for the next global parameter. Bound by a ``value`` section, so
    #: the editor holds no state of its own -- the button below reads it from here.
    new_global_parameter_name: str = ""

    #: Row selected in the local-fit table, written by the table's ``selected_attr``.
    selected_local_fit: int = -1

    #: Fit chosen to be added next, written by the ``choice`` of candidates.
    selected_candidate_fit: str = ""

    @property
    def candidate_fit_names(self) -> typing.List[str]:
        """Names of fits that could be added to this global fit.

        Every fit except this one and those already included -- the list the
        hand-written editor filled a combo box with.
        """
        included = set(self.fit_names)
        out = []
        for f in getattr(cs, "fits", []) or []:
            name = str(getattr(f, "name", "") or "")
            if not name or name in included or f is self.fit:
                continue
            out.append(name)
        return out

    def add_selected_fit(self) -> None:
        """Add the fit named by :attr:`selected_candidate_fit` to the global fit."""
        name = str(self.selected_candidate_fit or "")
        for i, f in enumerate(getattr(cs, "fits", []) or []):
            if str(getattr(f, "name", "") or "") == name:
                self.fit.append_fit(i)
                return
        cs.logging.warning(f"GlobalFitModel: no fit named {name!r} to add")

    def remove_selected_local_fit(self) -> None:
        """Remove the row named by :attr:`selected_local_fit`."""
        row = int(self.selected_local_fit)
        if row < 0:
            cs.logging.warning("GlobalFitModel: no local fit selected to remove")
            return
        self.fit.remove_local_fit(row)

    def clear_local_fits(self) -> None:
        """Remove every local fit from the global fit."""
        self.fit.clear_local_fits()

    def add_global_parameter(self) -> None:
        """Create a global parameter named by :attr:`new_global_parameter_name`."""
        name = str(self.new_global_parameter_name or "").strip()
        if not name:
            cs.logging.warning("GlobalFitModel: type a name before adding a global parameter")
            return
        self.fit.append_global_parameter(name)
        self.new_global_parameter_name = ""

    @property
    def fit_names(self) -> typing.List[str]:
        """Names of all local fits in this global model."""
        return [f.name for f in self.fits]

    @property
    def n_points(self) -> int:
        """Total number of data points across all local fits.

        Cached against the fit windows, which are what it actually depends on.
        Every objective evaluation asks for the degrees of freedom, and summing
        this over the members re-derived each member's masked window length.
        """
        token = self._window_token()
        cache = self.__dict__.get("_n_points_cache")
        if cache is not None and cache[0] == token:
            return cache[1]
        nbr_points = 0
        for f in self.fits:
            nbr_points += f.model.n_points
        self.__dict__["_n_points_cache"] = (token, nbr_points)
        return nbr_points

    def _window_token(self) -> tuple:
        """Return a cheap token identifying every member's current fit window.

        Residual length and point count depend on each member's ``[xmin, xmax)``
        window and mask, which no structure-version bump covers. Rather than
        read those back per call -- this runs twice per objective evaluation --
        the window setters bump a counter, so the token is two integers.
        """
        from chisurf.core.fitting import factorgraph
        return (factorgraph.window_version(), len(self.fits))

    @property
    def global_parameters_all(self) -> typing.List[cs.core.fitting.parameter.FittingParameter]:
        """All global parameters (fixed and variable)."""
        return list(self._global_parameters.values())

    @property
    def global_parameters_all_names(self) -> typing.List[str]:
        """Names of all global parameters."""
        return [p.name for p in self.global_parameters_all]

    @property
    def global_parameters(self) -> typing.List[cs.core.fitting.parameter.FittingParameter]:
        """Non-fixed (variable) global parameters."""
        return [p for p in self.global_parameters_all if not p.fixed]

    @property
    def global_parameters_names(self) -> typing.List[str]:
        """Names of variable global parameters."""
        return [p.name for p in self.global_parameters]

    @property
    def global_parameters_bound_all(self) -> typing.List[typing.Tuple[float, float]]:
        """Bounds for all global parameters."""
        return [pi.bounds for pi in self.global_parameters_all]

    @property
    def parameters(self) -> typing.List[cs.core.fitting.parameter.FittingParameter]:
        """All fitting parameters (local variable + global variable).

        Cached against the structure version, like the per-model list it
        concatenates: this is consulted several times per objective evaluation
        and rebuilding it walked every local model's parameters each time. The
        cache is a tuple so that :func:`chisurf.core.base.find_objects` does not
        descend into it; a fresh list is returned.
        """
        frozen = self.__dict__.get("_frozen_structure")
        if frozen is not None:
            return frozen["parameters"]
        from chisurf.core.fitting import factorgraph
        version = factorgraph.structure_version()
        cache = self.__dict__.get("_free_parameter_cache")
        if cache is not None and cache[0] == version and cache[1] == len(self.fits):
            return list(cache[2])
        p = list()
        for f in self.fits:
            p += f.model.parameters
        p += self.global_parameters
        self.__dict__["_free_parameter_cache"] = (version, len(self.fits), tuple(p))
        return p

    @property
    def parameter_names(self) -> typing.List[str]:
        """Formatted names of variable parameters across all local fits.

        Each local parameter is prefixed with its fit index, e.g. ``1:N``.
        """
        frozen = self.__dict__.get("_frozen_structure")
        if frozen is not None:
            return frozen["parameter_names"]
        try:
            re = list()
            for i, f in enumerate(self.fits):
                if f.model is not None:
                    re += ["%i:%s" % (i + 1, p.name) for p in f.model.parameters]
            re += self.global_parameters_names
            return re
        except AttributeError:
            return list()

    @property
    def parameters_all(self) -> typing.List[cs.core.fitting.parameter.FittingParameter]:
        """All parameters (local + global), including fixed ones."""
        try:
            re = list()
            for f in self.fits:
                if f.model is not None:
                    re += [p for p in f.model.parameters_all]
            re += self.global_parameters_all
            return re
        except AttributeError:
            return []

    @property
    def global_parameters_values_all(self) -> typing.List[float]:
        """Current values of all global parameters."""
        return [g.value for g in self.global_parameters_all]

    @property
    def global_parameters_fixed_all(self) -> typing.List[bool]:
        """Fixed-state of all global parameters."""
        return [p.fixed for p in self.global_parameters_all]

    @property
    def parameter_names_all(self) -> typing.List[str]:
        """Formatted names of all parameters (local + global), including fixed."""
        try:
            re = list()
            for i, f in enumerate(self.fits):
                if f.model is not None:
                    re += ["%i:%s" % (i + 1, p.name) for p in f.model._parameters]
            re += self.global_parameters_all_names
            return re
        except AttributeError:
            return []

    @property
    def parameter_dict(self) -> typing.Dict[str, cs.core.fitting.parameter.FittingParameter]:
        """Dictionary mapping formatted parameter names to parameters."""
        re = dict()
        for i, f in enumerate(self.fits):
            d = f.model.parameter_dict
            k = [str(i+1)+":"+dk for dk in d.keys()]
            for j, di in enumerate(d.keys()):
                re[k[j]] = d[di]
        return re

    @property
    def data(self) -> typing.Tuple[np.array, np.array, np.array]:
        """Concatenated (x, y, weight) data from all local fits.

        Returns
        -------
        tuple of np.array
            ``(x, y, weights)`` where x is a running index.
        """
        d = list()
        w = list()
        for f in self.fits:
            x, di, wi = f.data[0:-1]
            d.append(di)
            w.append(wi)
        dn = np.hstack(d)
        wn = np.hstack(w)
        xn = np.arange(0, dn.shape[0], 1)
        return xn, dn, wn

    def __init__(
            self,
            fit: Fit,
            fits: typing.List[Fit] = None,
            *args,
            **kwargs
    ):
        """Initialize the global fit model.

        Parameters
        ----------
        fit : Fit
            The parent fit (FitGroup or similar).
        fits : list of Fit, optional
            Initial list of local fits.
        *args
            Positional arguments forwarded to the base class.
        **kwargs
            Keyword arguments forwarded to the base class.
        """
        if fits is None:
            fits = list()
        self.fits = fits
        self.fit = fit
        self._global_parameters = dict()
        self._factor_graph = None
        # Set by the ``parameter_values`` setter to the local fits a complete
        # vector assignment actually touched, and consumed by the next
        # ``update_model``. ``None`` means "recompute everything".
        self._pending_dirty_fits = None
        # Recomputing only what changed is valid only if everything *else* is
        # already up to date. A freshly built group, or one whose membership or
        # parameter structure just changed, has not been evaluated at all, so
        # skipping a local model there would leave stale residuals in the
        # objective. This records the structure version at which every local
        # model was last brought up to date; selective updating is admissible
        # exactly while it still matches the current one.
        self._current_at_version = None
        #: Members whose cached weighted residuals are stale. ``None`` means all.
        self._residual_dirty = None
        super().__init__(fit, *args, **kwargs)

    # -- posterior structure ----------------------------------------------

    @property
    def factor_graph(self) -> cs.core.fitting.factorgraph.FactorGraph:
        """Factor graph of this global fit, rebuilt when the structure changes.

        Variables are the free parameters of :attr:`parameters`, factors are the
        per-dataset likelihoods and the informative parameter priors. See
        :mod:`chisurf.core.fitting.factorgraph`; the graph is what lets
        :meth:`update_model` recompute only the local models a change actually
        reached, and what exposes the group's blocks, separators and treewidth.
        """
        from chisurf.core.fitting import factorgraph
        version = factorgraph.structure_version()
        graph = self._factor_graph
        if graph is None or graph.version != version:
            graph = factorgraph.build_factor_graph(self.fit, model=self)
            self._factor_graph = graph
        return graph

    @property
    def parameter_values(self) -> typing.List[float]:
        """Values of all free parameters (local variable + global variable)."""
        return [p.value for p in self.parameters]

    @parameter_values.setter
    def parameter_values(self, vs: typing.List[float]):
        """Assign the whole free-parameter vector and note what it moved.

        Assigning the complete vector is the one moment at which the model knows
        exactly which parameters changed, so it is also the only moment from
        which selective recomputation can be armed safely. The dirty set is
        derived from the factor graph and consumed by the very next
        :meth:`update_model`; anything else -- a GUI edit of a single value, a
        structure change, a second `update_model` -- falls back to recomputing
        every local model.

        Parameters
        ----------
        vs : list of float
            New parameter values, in the order of :attr:`parameters`.
        """
        ps = self.parameters
        changed = []
        for i, v in enumerate(vs):
            if i >= len(ps):
                break
            p = ps[i]
            try:
                before = float(p.value)
            except (TypeError, ValueError):
                before = None
            # Writing a value it already has costs two port round-trips and
            # tells us nothing, and most proposals move one parameter out of
            # many. Reading is unavoidable -- a value may have been set
            # elsewhere -- but writing and reading back are not.
            if before is not None and before == v:
                continue
            p.value = v
            # Compare the *readback*, not the requested value: a bound or a
            # transform can leave the effective value where it was, and a
            # parameter that did not move needs no work.
            try:
                after = float(p.value)
            except (TypeError, ValueError):
                after = None
            if before is None or after is None or before != after:
                changed.append(i)

        self._pending_dirty_fits = self._dirty_fits_for(changed)

    def _dirty_fits_for(self, changed_indices) -> typing.Optional[typing.List[int]]:
        """Map changed parameter positions onto the local fits to recompute.

        Parameters
        ----------
        changed_indices : sequence of int
            Positions in :attr:`parameter_values` whose value moved.

        Returns
        -------
        list of int or None
            Indices of the local fits to recompute, or ``None`` meaning "all of
            them" -- returned whenever selective updating is disabled, the graph
            cannot be built, or a changed parameter reaches no likelihood factor
            (see
            :meth:`~chisurf.core.fitting.factorgraph.FactorGraph.unexplained_variables`),
            which would otherwise be mistaken for "reaches nothing".
        """
        try:
            enabled = cs.core.settings.cs_settings['optimization'].get(
                'global_structure_aware_update', True
            )
        except (KeyError, TypeError, AttributeError):
            enabled = True
        if not enabled:
            return None
        try:
            from chisurf.core.fitting import factorgraph
            if self._current_at_version != factorgraph.structure_version():
                # Nothing may be skipped until every local model has been
                # evaluated at least once since the last structural change.
                return None
            graph = self.factor_graph
            keys = [graph.key_at(i) for i in changed_indices]
            keys = [k for k in keys if k is not None]
            if len(keys) != len(changed_indices):
                # A changed position is not in the graph: it is out of date.
                return None
            if set(keys) & graph.unexplained_variables():
                return None
            return graph.affected_fits(keys)
        except Exception as e:
            cs.logging.warning(
                f"GlobalFitModel: falling back to a full model update ({e})"
            )
            return None

    def _invalidate_structure(self) -> None:
        """Drop the cached factor graph after the group's membership changed.

        Adding or removing a local fit, or declaring a global parameter, changes
        which datasets and variables exist. The global counter is bumped as well
        so that any other holder of a graph over this fit rebuilds too.
        """
        from chisurf.core.fitting import factorgraph
        self._factor_graph = None
        self._pending_dirty_fits = None
        self._current_at_version = None
        self.__dict__.pop("_residual_cache", None)
        self.__dict__.pop("_n_points_cache", None)
        self.__dict__.pop("_free_parameter_cache", None)
        self._residual_dirty = None
        factorgraph.bump_structure_version()

    def structure_report(self) -> str:
        """Return a short report of how this global fit decomposes.

        Returns
        -------
        str
            The output of :meth:`~chisurf.core.fitting.factorgraph.FactorGraph.describe`
            — variable and dataset counts, treewidth, independent components and
            the shared (separator) parameters.
        """
        return self.factor_graph.describe()


    def get_wres(
            self,
            fit: Fit,
            xmin: int = None,
            xmax: int = None
    ) -> np.array:
        """Compute weighted residuals for a given fit within a range.

        Parameters
        ----------
        fit : Fit
            The local fit to evaluate.
        xmin, xmax : int, optional
            Index range for the residuals.

        Returns
        -------
        np.ndarray
            Weighted residuals array.
        """
        try:
            f = fit
            if xmin is None:
                xmin = f.xmin
            if xmax is None:
                xmax = f.xmax
            x, m = f.model[xmin:xmax]
            x, d, w = f.model.data[xmin:xmax]
            ml = min([len(m), len(d)])
            wr = np.array((d[:ml] - m[:ml]) * w[:ml], dtype=np.float64)
        except Exception as e:
            import logging
            logging.warning(f"Failed to calculate weighted residuals: {e}")
            wr = np.array([1.0])
        return wr

    def append_fit(self, fit: Fit) -> None:
        """Add a local fit to the global model.

        Parameters
        ----------
        fit : Fit
            The fit instance to append.
        """
        try:
            cs.logging.info(
                f"GlobalFitModel.append_fit: receiver={type(self).__name__}, incoming fit type={type(fit).__name__}, name={getattr(fit, 'name', None)}; already_present={fit in getattr(self, 'fits', [])}"
            )
        except Exception:
            pass
        if fit not in self.fits:
            self.fits.append(fit)
            self._invalidate_structure()
            try:
                cs.logging.info(
                    f"GlobalFitModel.append_fit: appended successfully; total_fits={len(self.fits)}; names={getattr(self, 'fit_names', [])}"
                )
            except Exception:
                pass
            # Notify any subscribers that a fit was appended (non-Qt callbacks)
            try:
                callbacks = getattr(self, "_on_fit_appended", None)
                if isinstance(callbacks, list):
                    for cb in list(callbacks):
                        try:
                            cb(fit)
                        except Exception:
                            # Keep notifications best-effort; ignore callback errors
                            pass
            except Exception:
                pass

    # --- Lightweight non-Qt subscription API for append notifications ---
    def on_fit_appended(self, fn) -> None:
        """Register a callback called with (fit) whenever a new fit is appended.

        This keeps the model free of Qt dependencies while allowing UI layers
        to react to changes triggered via macros/actions as well as the GUI.

        Parameters
        ----------
        fn : callable
            Callback accepting one argument (fit).
        """
        lst = getattr(self, "_on_fit_appended", None)
        if lst is None:
            lst = []
            setattr(self, "_on_fit_appended", lst)
        if callable(fn) and fn not in lst:
            lst.append(fn)

    def off_fit_appended(self, fn) -> None:
        """Unregister a callback previously registered with :meth:`on_fit_appended`.

        Parameters
        ----------
        fn : callable
            The callback to remove.
        """
        lst = getattr(self, "_on_fit_appended", None)
        if isinstance(lst, list) and fn in lst:
            lst.remove(fn)

    def append_global_parameter(self, parameter: cs.core.parameter.Parameter) -> None:
        """Add a global parameter to the model.

        Parameters
        ----------
        parameter : cs.core.parameter.Parameter
            The parameter instance to add.
        """
        variable_name = parameter.name
        if variable_name not in list(self._global_parameters.keys()):
            self._global_parameters[parameter.name] = parameter
            self._invalidate_structure()

    def autofitrange(self, fit: FitGroup):
        """Reset auto-fit range to cover all data.

        Parameters
        ----------
        fit : FitGroup
            Ignored (kept for API compatibility).

        Returns
        -------
        tuple of None
            ``(None, None)``.
        """
        self.xmin, self.xmax = None, None
        return self.xmin, self.xmax

    def clear_local_fits(self) -> None:
        """Remove all local fits from the global model."""
        self.fits = list()
        self._invalidate_structure()

    def remove_local_fit(self, fit_index: int):
        """Remove a local fit by index.

        Parameters
        ----------
        fit_index : int
            Index of the fit to remove.
        """
        del self.fits[fit_index]
        self._invalidate_structure()

    def __str__(self):
        """Return a string summary of the global model."""
        s = "\n"
        s += "Model: Global-fit\n"
        s += "Global-parameters:"
        p0 = list(zip(self.global_parameters_all_names, self.global_parameters_values_all,
                 self.global_parameters_bound_all, self.global_parameters_fixed_all))
        s += "Parameter \t Value \t Bounds \t Fixed\n"
        for p in p0:
            s += "%s \t %.4f \t %s \t %s\n" % p
        for fit in self.fits:
            s += "\n"
            s += fit.name + "\n"
            s += str(fit.model) + "\n"
        s += "\n"
        return s

    @property
    def x(self) -> np.array:
        """x-data from all local fits, one array per fit."""
        x = list()
        for f in self.fits:
            x.append(f.model.x)
        return np.array(x)

    @x.setter
    def x(self, v):
        """Set x-data (no-op, data come from local fits)."""
        pass

    @property
    def y(self) -> np.array:
        """y-data from all local fits, one array per fit."""
        y = list()
        for f in self.fits:
            y.append(f.model.y)
        return np.array(y)

    @y.setter
    def y(self, v):
        """Set y-data (no-op, data come from local fits)."""
        pass

    def __getitem__(self, key):
        """Slice data from all local fits.

        Parameters
        ----------
        key : slice
            Slice object with start/stop/step.

        Returns
        -------
        tuple
            ``(x_slice, y_slice)``.
        """
        start = key.start
        stop = key.stop
        step = 1 if key.step is None else key.step
        return self.x[start:stop:step], self.y[start:stop:step]

    def finalize(self):
        """Finalize all local-fit models."""
        for f in self.fits:
            f.model.finalize()

    def update(self) -> None:
        """Update all local-fit models."""
        super().update()
        for f in self.fits:
            f.model.update()
        # Every local model has just been rebuilt from its current parameters,
        # so selective updating is admissible again -- and every cached residual
        # is stale, because every model was recomputed.
        from chisurf.core.fitting import factorgraph
        self._current_at_version = factorgraph.structure_version()
        self._residual_dirty = set(range(len(self.fits)))

    def update_model(self, **kwargs) -> None:
        """Recompute the local-fit models, optionally in parallel threads.

        Only the models a parameter change actually reached are recomputed, as
        determined by the fit's :attr:`factor_graph`. The dirty set is armed by
        the :attr:`parameter_values` setter and consumed here, so an
        ``update_model`` that does not directly follow a complete vector
        assignment recomputes every local model. This is what makes a global
        objective cost what moved rather than the number of datasets: a proposal
        touching one dataset's local parameter used to cost N model evaluations.

        Parameters
        ----------
        **kwargs
            Forwarded to each local model's ``update_model``.
        """
        dirty = self._pending_dirty_fits
        # One-shot: whatever happens next must not inherit this dirty set.
        self._pending_dirty_fits = None

        if dirty is None:
            targets = list(self.fits)
            indices = range(len(self.fits))
            # A full pass re-establishes the invariant the selective path needs.
            from chisurf.core.fitting import factorgraph
            self._current_at_version = factorgraph.structure_version()
        else:
            indices = [i for i in dirty if 0 <= i < len(self.fits)]
            targets = [self.fits[i] for i in indices]
        # Whatever is recomputed here is what the residual cache must drop.
        stale = getattr(self, "_residual_dirty", None)
        if stale is None:
            stale = set()
        self._residual_dirty = stale | set(indices)
        if not targets:
            # Nothing moved, so every local model is already current.
            return

        if cs.core.settings.cs_settings['optimization']['global_threaded_model_update']:
            threads = [threading.Thread(target=f.model.update_model) for f in targets]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        else:
            for f in targets:
                f.model.update_model()
