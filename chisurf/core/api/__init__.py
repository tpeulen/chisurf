from __future__ import annotations
import chisurf as cs

from typing import Any, Callable, Dict, List, Optional

import numpy as np

from chisurf.core.api.context import PluginContext
from chisurf.server.session import SessionState


def _extract_curve_data(dataset: Any) -> Optional[Dict[str, List[float]]]:
    """Extract serializable x/y/ex/ey arrays from a DataCurve or container.

    Returns ``None`` if the dataset does not have curve-like data.
    """
    try:
        x = getattr(dataset, "x", None)
        y = getattr(dataset, "y", None)
        if x is None or y is None:
            return None
        result: Dict[str, List[float]] = {
            "x": np.asarray(x, dtype=float).tolist(),
            "y": np.asarray(y, dtype=float).tolist(),
        }
        ex = getattr(dataset, "ex", None)
        if ex is not None:
            result["ex"] = np.asarray(ex, dtype=float).tolist()
        ey = getattr(dataset, "ey", None)
        if ey is not None:
            result["ey"] = np.asarray(ey, dtype=float).tolist()
        return result
    except Exception:
        return None


def _global_datasets() -> list[Any]:
    """Return the process-global imported-dataset list *object*.

    The identity matters: :class:`ChiSurfAPI` binds this list into its
    :class:`SessionState`, so the state and ``cs.imported_datasets`` must stay
    the same object even when the global is currently empty.  The list is
    created and installed on the ``chisurf`` module if it is genuinely absent.

    Returns
    -------
    list
        The ``chisurf.imported_datasets`` list itself, never a copy.
    """
    datasets = getattr(cs, "imported_datasets", None)
    if datasets is None:
        datasets = []
        cs.imported_datasets = datasets
    return datasets


def _global_fits() -> list[Any]:
    """Return the process-global fit list *object*.

    See :func:`_global_datasets` — the same identity requirement applies to
    ``cs.fits``.

    Returns
    -------
    list
        The ``chisurf.fits`` list itself, never a copy.
    """
    fits = getattr(cs, "fits", None)
    if fits is None:
        fits = []
        cs.fits = fits
    return fits


def _local_datasets() -> list[Any]:
    return list(_global_datasets())


def _local_fits() -> list[Any]:
    return list(_global_fits())


def _resolve_indexed(items: list[Any], index: Optional[int] = None, uid: Optional[str] = None) -> tuple[Any, int]:
    """Look up an item by uid or position. Returns ``(item, index)`` or ``(None, -1)``.

    A **non-empty** ``uid`` that matches nothing resolves to ``(None, -1)``
    rather than falling back to ``index``: the caller named a specific item, so
    silently retargeting the operation at another one would apply it to the
    wrong fit or dataset.  An empty or absent uid means "unspecified" and uses
    the index.  This mirrors the server-side
    :func:`~chisurf.server.services._resolve_fit`, so local, hybrid, and server
    modes address the same object.

    Parameters
    ----------
    items : list
        The fits or datasets to search.
    index : int, optional
        Positional index, used only when no uid is given.
    uid : str, optional
        Unique identifier of the wanted item.

    Returns
    -------
    tuple
        ``(item, index)``, or ``(None, -1)`` if nothing matches.
    """
    if uid:
        for i, item in enumerate(items):
            if str(getattr(item, "unique_identifier", "")) == uid:
                return item, i
        return None, -1
    if index is not None and 0 <= index < len(items):
        return items[index], index
    return None, -1


def _local_dataset(dataset_index: Optional[int] = None, dataset_uid: Optional[str] = None) -> tuple[Any, int]:
    return _resolve_indexed(_local_datasets(), dataset_index, dataset_uid)


def _local_fit(fit_index: Optional[int] = None, fit_uid: Optional[str] = None) -> tuple[Any, int]:
    return _resolve_indexed(_local_fits(), fit_index, fit_uid)


def _local_parameter(
    parameter_name: str,
    fit_index: int = 0,
    fit_uid: Optional[str] = None,
    require_parameters: bool = False,
) -> tuple[Any, Any, Optional[Dict[str, Any]]]:
    fit, _ = _local_fit(fit_index, fit_uid)
    if fit is None:
        return None, None, {"ok": False, "error": "fit not found"}
    try:
        parameters = getattr(fit.model, "parameters_all_dict", {}) or {}
    except Exception:
        if require_parameters:
            return fit, None, {"ok": False, "error": "cannot access model parameters"}
        parameters = {}
    parameter = parameters.get(parameter_name)
    if parameter is None:
        return fit, None, {"ok": False, "error": f"parameter '{parameter_name}' not found"}
    return fit, parameter, None


class ChiSurfAPI:
    """Single stable API facade for GUI, macros, plugins, and QtConsole.

    Routes to local in-process objects in ``local`` mode, server RPC in
    ``server`` mode, and a mix in ``hybrid`` mode.

    The API owns a :class:`SessionState <chisurf.server.session.SessionState>`
    that aliases the ``cs.fits`` / ``cs.imported_datasets`` globals (same
    list objects).  All mutations go through the state; the globals are a
    backward-compatible read-shim.

    Parameters
    ----------
    client : object, optional
        A ``ChisurfClient`` instance for server-mode routing.
    mode : str
        ``"local"``, ``"hybrid"``, or ``"server"``.
    state : SessionState, optional
        Pre-existing state to adopt.  When *None* (default) a new state is
        built that aliases the current ``cs.fits`` / ``cs.imported_datasets``
        globals.
    """

    def __init__(
        self,
        client: Any = None,
        mode: str = "hybrid",
        state: SessionState | None = None,
    ):
        self.client = client
        self.mode = mode
        if state is not None:
            self._state = state
        else:
            self._state = SessionState(
                datasets=_global_datasets(),
                fits=_global_fits(),
            )

    # ── datasets ─────────────────────────────────────────────────

    def list_datasets(self) -> List[Dict[str, Any]]:
        if self.mode == "server" and self.client is not None:
            return self.client.dataset__list()
        result: List[Dict[str, Any]] = []
        for idx, d in enumerate(self._state.datasets):
            result.append({
                "index": idx,
                "uid": str(getattr(d, "unique_identifier", "") or ""),
                "name": str(getattr(d, "name", "") or ""),
                "type": type(d).__name__,
                "experiment": str(getattr(getattr(d, "experiment", None), "name", "") or ""),
                "filename": str(getattr(d, "filename", "") or ""),
            })
        return result

    def get_dataset_info(self, dataset_index: Optional[int] = None, dataset_uid: Optional[str] = None) -> Dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            return self.client.dataset__get(dataset_index=dataset_index, dataset_uid=dataset_uid)
        d, idx = _local_dataset(dataset_index, dataset_uid)
        if d is None:
            return {"ok": False, "error": "dataset not found"}
        return {
            "ok": True,
            "dataset": {
                "index": idx,
                "uid": str(getattr(d, "unique_identifier", "") or ""),
                "name": str(getattr(d, "name", "") or ""),
                "type": type(d).__name__,
                "experiment": str(getattr(getattr(d, "experiment", None), "name", "") or ""),
                "filename": str(getattr(d, "filename", "") or ""),
                "length": int(len(getattr(d, "y", []))) if hasattr(d, "y") else None,
            },
        }

    def get_dataset_curve_data(self, dataset_index: Optional[int] = None, dataset_uid: Optional[str] = None) -> Dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            return self.client.dataset__curve_data(dataset_index=dataset_index, dataset_uid=dataset_uid)
        d, _ = _local_dataset(dataset_index, dataset_uid)
        if d is None:
            return {"ok": False, "error": "dataset not found"}
        try:
            result: Dict[str, Any] = {"ok": True}
            x = getattr(d, "x", None)
            if x is not None:
                result["x"] = np.asarray(x, dtype=float).tolist()
            y = getattr(d, "y", None)
            if y is not None:
                result["y"] = np.asarray(y, dtype=float).tolist()
            ex = getattr(d, "ex", None)
            if ex is not None:
                result["ex"] = np.asarray(ex, dtype=float).tolist()
            ey = getattr(d, "ey", None)
            if ey is not None:
                result["ey"] = np.asarray(ey, dtype=float).tolist()
            return result
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def load_dataset(
        self,
        experiment_reader: Any = None,
        dataset: Any = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            params: Dict[str, Any] = dict(kwargs)
            if experiment_reader is not None:
                rname = getattr(type(experiment_reader), "__name__", None)
                if rname:
                    params["reader_name"] = rname
                fname = getattr(experiment_reader, "filename", None) or kwargs.get("filename")
                if fname:
                    params["filename"] = str(fname)
                name = getattr(experiment_reader, "name", None) or kwargs.get("name")
                if name:
                    params["name"] = str(name)
                # Extract data arrays from the dataset if available; else
                # try to read them locally so the server has real x/y data.
                if dataset is not None:
                    curve_data = _extract_curve_data(dataset)
                    if curve_data:
                        params["curve_data"] = curve_data
                else:
                    try:
                        local_data = experiment_reader.get_data(**kwargs)
                        curve_data = _extract_curve_data(local_data)
                        if curve_data:
                            params["curve_data"] = curve_data
                    except Exception:
                        pass
            return self.client.call("dataset.load", params)
        from chisurf.macros import core_data
        core_data.add_dataset(
            experiment_reader=experiment_reader,
            dataset=dataset,
            _from_controller=True,
            **kwargs,
        )
        return {"ok": True}

    def remove_datasets(
        self,
        dataset_indices: Optional[List[int]] = None,
        dataset_uids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            return self.client.dataset__remove(dataset_indices=dataset_indices, dataset_uids=dataset_uids)
        from chisurf.macros import core_data
        indices = list(dataset_indices or [])
        if dataset_uids:
            for i, d in enumerate(self._state.datasets):
                if str(getattr(d, "unique_identifier", "")) in dataset_uids:
                    indices.append(i)
        if indices:
            core_data.remove_datasets(dataset_indices=list(set(indices)), _from_controller=True)
        return {"ok": True}

    def clear_datasets(self) -> Dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            return self.client.dataset__clear()
        self._state.datasets.clear()
        return {"ok": True}

    def group_datasets(
        self,
        dataset_indices: List[int],
        group_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            return self.client.dataset__group(
                dataset_indices=dataset_indices,
                group_name=group_name,
            )
        from chisurf.macros import core_data
        core_data.group_datasets(
            dataset_indices=dataset_indices,
            _from_controller=True,
        )
        return {"ok": True}

    def ungroup_datasets(
        self,
        dataset_indices: List[int],
    ) -> Dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            return self.client.dataset__ungroup(dataset_indices=dataset_indices)
        from chisurf.macros import core_data
        core_data.ungroup_datasets(
            dataset_indices=dataset_indices,
            _from_controller=True,
        )
        return {"ok": True}

    # ── fits ──────────────────────────────────────────────────────

    def list_fits(self) -> List[Dict[str, Any]]:
        if self.mode == "server" and self.client is not None:
            return self.client.fit__list()
        result: List[Dict[str, Any]] = []
        fits = list(self._state.fits)
        for idx, f in enumerate(fits):
            chi2 = None
            try:
                chi2 = float(getattr(f, "chi2", float("nan")))
            except Exception:
                pass
            data_name = ""
            try:
                data_name = str(getattr(getattr(f, "data", None), "name", "") or "")
            except Exception:
                pass
            param_count = 0
            try:
                param_count = len(getattr(getattr(f, "model", None), "parameters_all_dict", {}) or {})
            except Exception:
                pass
            result.append({
                "index": idx,
                "uid": str(getattr(f, "unique_identifier", "") or ""),
                "name": str(getattr(f, "name", "") or ""),
                "type": type(f).__name__,
                "chi2": chi2,
                "dataset_uid": str(getattr(getattr(f, "data", None), "unique_identifier", "") or ""),
                "dataset_name": data_name,
                "model_name": str(getattr(getattr(f, "model", None), "name", "") or ""),
                "parameter_count": param_count,
                "data": {
                    "name": str(getattr(getattr(f, "data", None), "name", "") or ""),
                    "uid": str(getattr(getattr(f, "data", None), "unique_identifier", "") or ""),
                    "filename": str(getattr(getattr(f, "data", None), "filename", "") or ""),
                    "experiment": str(getattr(getattr(f, "data", None), "experiment", "") or getattr(getattr(getattr(f, "data", None), "experiment", None), "name", "") or ""),
                } if hasattr(f, "data") and f.data is not None else {},
                "model": {
                    "name": str(getattr(getattr(f, "model", None), "name", "") or ""),
                    "n_points": _safe_n_points(f),
                    "n_free": _safe_n_free(f),
                    "chi2r": _safe_chi2r(f),
                    "parameters_all": _collect_param_list(f, fit_uid=str(getattr(f, "unique_identifier", "") or "")),
                } if hasattr(f, "model") and f.model is not None else {},
            })
        return result

    def get_fit_info(self, fit_index: Optional[int] = None, fit_uid: Optional[str] = None) -> Dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            return self.client.fit__get(fit_index=fit_index, fit_uid=fit_uid)
        fit, idx = _local_fit(fit_index, fit_uid)
        if fit is None:
            return {"ok": False, "error": "fit not found"}
        params = {}
        try:
            pdict = getattr(fit.model, "parameters_all_dict", {}) if hasattr(fit, "model") else {}
            for name, p in pdict.items():
                params[name] = {
                    "value": getattr(p, "value", None),
                    "fixed": bool(getattr(p, "fixed", False)),
                    "bounds": getattr(p, "bounds", None),
                    "bounds_on": bool(getattr(p, "bounds_on", False)),
                    "linked_to": str(getattr(getattr(p, "link", None), "name", "") or ""),
                    "error_estimate": getattr(p, "error_estimate", None),
                }
        except Exception:
            pass
        return {
            "ok": True,
            "fit": {
                "index": idx,
                "uid": str(getattr(fit, "unique_identifier", "") or ""),
                "name": str(getattr(fit, "name", "") or ""),
                "type": type(fit).__name__,
                "chi2": _safe_chi2(fit),
                "chi2r": _safe_chi2r(fit),
                "n_points": _safe_n_points(fit),
                "n_free": _safe_n_free(fit),
                "dataset_uid": str(getattr(getattr(fit, "data", None), "unique_identifier", "") or ""),
                "dataset_name": str(getattr(getattr(fit, "data", None), "name", "") or ""),
                "model_name": str(getattr(getattr(fit, "model", None), "name", "") or ""),
                "parameter_count": len(params),
                "parameters": params,
                "members": _collect_member_list(fit),
                "data": {
                    "name": str(getattr(getattr(fit, "data", None), "name", "") or ""),
                    "uid": str(getattr(getattr(fit, "data", None), "unique_identifier", "") or ""),
                    "filename": str(getattr(getattr(fit, "data", None), "filename", "") or ""),
                    "experiment": str(getattr(getattr(fit, "data", None), "experiment", "") or getattr(getattr(getattr(fit, "data", None), "experiment", None), "name", "") or ""),
                } if hasattr(fit, "data") and fit.data is not None else {},
                "model": {
                    "name": str(getattr(getattr(fit, "model", None), "name", "") or ""),
                    "n_points": _safe_n_points(fit),
                    "n_free": _safe_n_free(fit),
                    "chi2r": _safe_chi2r(fit),
                    "parameters_all": _collect_param_list(fit, fit_uid=str(getattr(fit, "unique_identifier", "") or "")),
                } if hasattr(fit, "model") and fit.model is not None else {},
            },
        }

    def posterior(
        self,
        fit_index: int | None = None,
        fit_uid: str | None = None,
        engine: str = "stored",
        targets: list[str] | None = None,
        joint: list[str] | None = None,
        condition: dict[str, float] | None = None,
        p_value: float = 0.68,
        global_posterior: bool = False,
        **options: Any,
    ) -> dict[str, Any]:
        """Ask what the data supports for a fit's parameters.

        One question, whichever estimator answers it. See
        :mod:`chisurf.core.fitting.engine`.

        Parameters
        ----------
        fit_index, fit_uid : int or str, optional
            Which fit to query; defaults to the current one.
        engine : {"stored", "laplace", "profile", "mcmc", "auto"}, optional
            Which estimator. ``stored`` reports what has already been computed
            and costs nothing -- the right choice for a summary table.
            ``profile`` and ``mcmc`` **block** for as long as they take.
        targets : list of str, optional
            Parameters to report; defaults to every free parameter.
        joint : list of str, optional
            Parameters to report a joint answer (covariance, correlation) over.
            Only a sampled posterior has a real one.
        condition : dict, optional
            Parameters to hold fixed (``name -> value``) while the rest are
            re-optimised -- what a profile scan does, available to every engine.
        p_value : float, optional
            Interval coverage.
        global_posterior : bool, optional
            Query a group's *joint* posterior rather than its selected member's.
        **options
            Engine options, e.g. ``steps`` and ``n_runs`` for ``mcmc``.

        Returns
        -------
        dict
            ``marginals`` (``name``, ``value``, ``sd``, ``low``, ``high``,
            ``method``, ``quantiles``, ``diagnostics``), ``joint`` when
            requested, ``log_evidence``, and the ``engine`` that answered.

        Examples
        --------
        >>> api = ChiSurfAPI()                              # doctest: +SKIP
        >>> api.posterior(engine='laplace')['marginals'][0]['method']
        'laplace'
        """
        if self.mode == "server" and self.client is not None:
            return self.client.fit__posterior(
                fit_index=fit_index, fit_uid=fit_uid, engine=engine,
                targets=targets, joint=joint, condition=condition,
                p_value=p_value, options=options or None,
                global_posterior=global_posterior,
            )
        from chisurf.server.services import fits as _fits

        class _State:
            """Adapter presenting the process-local fits to the service layer."""

            fits = property(lambda self: _local_fits())

        return _fits.fit_posterior(
            _State(), fit_index=fit_index, fit_uid=fit_uid, engine=engine,
            targets=targets, joint=joint, condition=condition,
            p_value=p_value, options=options or None,
            global_posterior=global_posterior,
        )

    def reweight_prior(
        self,
        priors: Dict[str, Any],
        fit_index: Optional[int] = None,
        fit_uid: Optional[str] = None,
        p_value: float = 0.68,
    ) -> Dict[str, Any]:
        """Ask what a completed sampling run would have said under other priors.

        Changing a prior changes the posterior but not the likelihood, so the
        draws a run already produced can be reweighted to the new posterior
        instead of being thrown away. **No model is evaluated**, so the answer is
        immediate where sampling again costs minutes.

        The reliability of that shortcut is reported, not assumed: ``pareto_k``
        above 0.7 means the new prior favours a region the chain did not explore
        and the numbers must not be used. See
        :mod:`chisurf.core.fitting.reweight`.

        Parameters
        ----------
        priors : dict
            Parameter name to the new prior, as a
            :meth:`~chisurf.core.fitting.priors.Prior.get_state` dict (e.g.
            ``{'tau1': {'kind': 'normal', 'mu': 4.0, 'sigma': 0.2}}``) or a
            :class:`~chisurf.core.fitting.priors.Prior`. ``None`` removes the
            prior on that parameter.
        fit_index, fit_uid : int or str, optional
            Which fit to query; defaults to the current one.
        p_value : float, optional
            Interval coverage for the reported quantiles.

        Returns
        -------
        dict
            ``ok``, and on success ``parameters`` (name, mean, sd, quantiles),
            ``pareto_k``, ``ess``, ``reliable``, ``changed`` and ``warnings``.
            ``ok`` is ``False`` when the fit has no stored chain to reweight.

        Examples
        --------
        >>> api = ChiSurfAPI()                                   # doctest: +SKIP
        >>> api.reweight_prior({'a': {'kind': 'normal',
        ...                           'mu': 1.2, 'sigma': 0.1}})['reliable']
        True
        """
        if self.mode == "server" and self.client is not None:
            return self.client.fit__reweight_prior(
                priors=priors, fit_index=fit_index, fit_uid=fit_uid,
                p_value=p_value,
            )
        from chisurf.server.services import fits as _fits

        class _State:
            """Adapter presenting the process-local fits to the service layer."""

            fits = property(lambda self: _local_fits())

        return _fits.fit_reweight_prior(
            _State(), priors=priors, fit_index=fit_index, fit_uid=fit_uid,
            p_value=p_value,
        )

    def derived_quantities(
        self,
        fit_index: Optional[int] = None,
        fit_uid: Optional[str] = None,
        names: Optional[List[str]] = None,
        p_value: float = 0.68,
        max_draws: int = 2048,
    ) -> Dict[str, Any]:
        """Report the numbers a fit computes but does not fit, with error bars.

        The FRET efficiency that goes in the figure and the mean lifetime that
        goes in the table are functions of the fitted parameters; ChiSurf printed
        them as bare numbers. They carry the parameters' uncertainty, and because
        the function is non-linear they carry a *shape*: a ratio bounded below is
        skewed even when every parameter behind it is Gaussian, so the symmetric
        interval that linear propagation gives is wrong at both ends at once.

        Posterior draws are used when the fit carries a converged chain, and
        linear propagation otherwise; ``method`` on each row says which, and
        whether the interval may be read as ``value ± σ``. See
        :mod:`chisurf.core.fitting.derived`.

        Parameters
        ----------
        fit_index, fit_uid : int or str, optional
            Which fit to query; defaults to the current one.
        names : list of str, optional
            Quantities to report; defaults to whatever the model declares.
        p_value : float, optional
            Central coverage of the reported interval.
        max_draws : int, optional
            Cap on posterior draws evaluated; the chain is thinned to fit.

        Returns
        -------
        dict
            ``ok`` and ``quantities``: per quantity ``name``, ``value``,
            ``median``, ``low``, ``high``, ``method``, ``converged`` and
            ``warning``. ``quantities`` is empty when the model declares none.

        Examples
        --------
        >>> api = ChiSurfAPI()                                   # doctest: +SKIP
        >>> for q in api.derived_quantities()['quantities']:     # doctest: +SKIP
        ...     print(q['name'], q['median'], q['low'], q['high'], q['method'])
        """
        if self.mode == "server" and self.client is not None:
            return self.client.fit__derived(
                fit_index=fit_index, fit_uid=fit_uid, names=names,
                p_value=p_value, max_draws=max_draws,
            )
        from chisurf.server.services import fits as _fits

        class _State:
            """Adapter presenting the process-local fits to the service layer."""

            fits = property(lambda self: _local_fits())

        return _fits.fit_derived(
            _State(), fit_index=fit_index, fit_uid=fit_uid, names=names,
            p_value=p_value, max_draws=max_draws,
        )

    def run_fit(self, fit_index: Optional[int] = None, fit_uid: Optional[str] = None) -> Dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            return self.client.fit__run(fit_index=fit_index, fit_uid=fit_uid)
        fit, idx = _local_fit(fit_index, fit_uid)
        if fit is None:
            return {"ok": False, "error": "fit not found"}
        try:
            chi2_before = _safe_chi2(fit)
            fit.run()
            chi2_after = _safe_chi2(fit)
            return {
                "ok": True,
                "fit_index": idx,
                "fit_uid": str(getattr(fit, "unique_identifier", "") or ""),
                "chi2_before": chi2_before,
                "chi2_after": chi2_after,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def add_fit(
        self,
        dataset_indices: List[int],
        model_name: Optional[str] = None,
        model_kw: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            call_kw: Dict[str, Any] = {"dataset_indices": list(dataset_indices or [])}
            if model_name is not None:
                call_kw["model_name"] = str(model_name)
            if isinstance(model_kw, dict):
                call_kw["model_kw"] = model_kw
            return self.client.fit__create(**call_kw)
        from chisurf.macros import core_fit
        kwargs: Dict[str, Any] = {"dataset_indices": list(dataset_indices or [])}
        if isinstance(model_kw, dict):
            kwargs["model_kw"] = model_kw
        if model_name is not None:
            kwargs["model_name"] = str(model_name)
        return core_fit.add_fit(**kwargs)

    def remove_fits(
        self,
        fit_indices: Optional[List[int]] = None,
        fit_uids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            return self.client.fit__remove(fit_indices=fit_indices, fit_uids=fit_uids)
        fits = list(self._state.fits)
        to_remove: set = set()
        if fit_uids:
            for i, f in enumerate(fits):
                if str(getattr(f, "unique_identifier", "")) in fit_uids:
                    to_remove.add(i)
        if fit_indices:
            to_remove.update(int(i) for i in fit_indices if 0 <= int(i) < len(fits))
        if not to_remove:
            return {"ok": False, "error": "no fits specified"}
        kept = [f for i, f in enumerate(fits) if i not in to_remove]
        self._state.fits[:] = kept
        return {"ok": True, "removed_count": len(to_remove)}

    def clear_fits(self) -> Dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            return self.client.fit__clear()
        self._state.fits.clear()
        return {"ok": True}

    def fit_create(self, dataset_index: int = 0, model_name: Optional[str] = None, fit_name: Optional[str] = None) -> Dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            return self.client.fit__create(dataset_index=dataset_index, model_name=model_name, fit_name=fit_name)
        return {"ok": False, "error": "fit.create requires server mode for server-side creation"}

    def fit_update(self, fit_index: Optional[int] = None, fit_uid: Optional[str] = None) -> Dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            return self.client.fit__update(fit_index=fit_index, fit_uid=fit_uid)
        fit, _ = _local_fit(fit_index, fit_uid)
        if fit is None:
            return {"ok": False, "error": "fit not found"}
        try:
            if hasattr(fit, "update"):
                fit.update()
                return {"ok": True}
            return {"ok": False, "error": "fit has no update method"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── parameters ────────────────────────────────────────────────

    def get_parameter(self, parameter_name: str, fit_index: int = 0, fit_uid: Optional[str] = None) -> Dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            return self.client.parameter__get(parameter_name=parameter_name, fit_index=fit_index, fit_uid=fit_uid)
        _, p, error = _local_parameter(parameter_name, fit_index, fit_uid)
        if error is not None:
            return error
        return {
            "ok": True,
            "parameter": {
                "name": parameter_name,
                "value": getattr(p, "value", None),
                "fixed": bool(getattr(p, "fixed", False)),
                "bounds": getattr(p, "bounds", None),
                "bounds_on": bool(getattr(p, "bounds_on", False)),
                "error_estimate": getattr(p, "error_estimate", None),
                "linked_to": str(getattr(getattr(p, "link", None), "name", "") or ""),
            },
        }

    def set_parameter_value(self, parameter_name: str, value: float, fit_index: int = 0, fit_uid: Optional[str] = None) -> Dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            return self.client.parameter__set_value(parameter_name=parameter_name, value=value, fit_index=fit_index, fit_uid=fit_uid)
        fit, p, error = _local_parameter(parameter_name, fit_index, fit_uid, require_parameters=True)
        if error is not None:
            return error
        try:
            p.value = float(value)
            if hasattr(fit.model, "update_model"):
                fit.model.update_model()
            if hasattr(fit.model, "finalize"):
                fit.model.finalize()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def set_parameter_fixed(self, parameter_name: str, fixed: bool, fit_index: int = 0, fit_uid: Optional[str] = None) -> Dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            return self.client.parameter__set_fixed(parameter_name=parameter_name, fixed=fixed, fit_index=fit_index, fit_uid=fit_uid)
        fit, p, error = _local_parameter(parameter_name, fit_index, fit_uid, require_parameters=True)
        if error is not None:
            return error
        try:
            p.fixed = bool(fixed)
            if hasattr(fit.model, "finalize"):
                fit.model.finalize()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def set_parameter_bounds(self, parameter_name: str, bounds: tuple, fit_index: int = 0, fit_uid: Optional[str] = None) -> Dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            return self.client.parameter__set_bounds(parameter_name=parameter_name, lower=bounds[0], upper=bounds[1], fit_index=fit_index, fit_uid=fit_uid)
        fit, p, error = _local_parameter(parameter_name, fit_index, fit_uid, require_parameters=True)
        if error is not None:
            return error
        try:
            p.bounds = tuple(float(v) for v in bounds)
            if hasattr(fit.model, "finalize"):
                fit.model.finalize()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── model ─────────────────────────────────────────────────────

    def model_finalize(self, fit_index: int = 0, fit_uid: Optional[str] = None) -> Dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            return self.client.model__finalize(fit_index=fit_index, fit_uid=fit_uid)
        fit, _ = _local_fit(fit_index, fit_uid)
        if fit is None:
            return {"ok": False, "error": "fit not found"}
        try:
            model = getattr(fit, "model", None)
            if model is None:
                return {"ok": False, "error": "fit has no model"}
            if hasattr(model, "finalize"):
                model.finalize()
                return {"ok": True}
            return {"ok": False, "error": "model has no finalize method"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def model_set_parse_function(self, parse_function: str, fit_index: int = 0, fit_uid: Optional[str] = None) -> Dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            return self.client.model__set_parse_function(parse_function=parse_function, fit_index=fit_index, fit_uid=fit_uid)
        fit, _ = _local_fit(fit_index, fit_uid)
        if fit is None:
            return {"ok": False, "error": "fit not found"}
        try:
            model = getattr(fit, "model", None)
            if model is None:
                return {"ok": False, "error": "fit has no model"}
            setattr(model, "parse_function", parse_function)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def set_parameter_bounds_on(self, parameter_name: str, bounds_on: bool, fit_index: int = 0, fit_uid: Optional[str] = None) -> Dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            return self.client.parameter__set_bounds_on(parameter_name=parameter_name, bounds_on=bounds_on, fit_index=fit_index, fit_uid=fit_uid)
        _, p, error = _local_parameter(parameter_name, fit_index, fit_uid, require_parameters=True)
        if error is not None:
            return error
        try:
            p.bounds_on = bool(bounds_on)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── projects ──────────────────────────────────────────────────

    def get_project_info(self) -> Dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            return self.client.project__info()
        return {
            "ok": True,
            "project_path": None,
            "fit_count": len(self._state.fits),
            "dataset_count": len(self._state.datasets),
        }

    def save_project(self, target_path: str, project_name: Optional[str] = None) -> Dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            return self.client.project__save(target_path=target_path, project_name=project_name)
        return {"ok": False, "error": "project.save requires server mode"}

    def load_project(self, project_path: str) -> Dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            return self.client.project__load(project_path=project_path)
        return {"ok": False, "error": "project.load requires server mode"}

    # ── convenience ───────────────────────────────────────────────

    def ping(self) -> Dict[str, Any]:
        if self.client is not None:
            return self.client.meta__ping()
        return {"ok": True, "status": "alive-local"}

    def session_describe(self) -> Dict[str, Any]:
        if self.client is not None:
            return self.client.session__describe()
        return {
            "ok": True,
            "datasets": self.list_datasets(),
            "fits": self.list_fits(),
            "dataset_count": len(self._state.datasets),
            "fit_count": len(self._state.fits),
        }

    def session_snapshot(self) -> Dict[str, Any]:
        if self.client is not None:
            return self.client.session__snapshot()
        return {
            "ok": True,
            "snapshot": {
                "dataset_count": len(self._state.datasets),
                "fit_count": len(self._state.fits),
            },
        }

    def session_restore(self, project_path: Optional[str] = None) -> Dict[str, Any]:
        if self.client is not None:
            return self.client.session__restore(project_path=project_path)
        if project_path:
            return {"ok": False, "error": "session restore requires server mode for project loading"}
        self._state.fits.clear()
        self._state.datasets.clear()
        return {"ok": True, "message": "session cleared locally"}

    @property
    def fit_count(self) -> int:
        fits = self.list_fits()
        return len(fits)

    @property
    def dataset_count(self) -> int:
        datasets = self.list_datasets()
        return len(datasets)

    def subscribe(self, topic: str = "", callback: Optional[Callable] = None) -> Any:
        if self.client is not None:
            return self.client.subscribe(topic, callback)
        return None

    def drain(self) -> None:
        """Process all buffered ZMQ subscriber events from the main thread."""
        if self.client is not None:
            self.client.drain()

    def list_methods(self) -> List[str]:
        if self.client is not None:
            return self.client.meta__methods()
        return []

    def install_proxies(self, force: bool = False) -> None:
        """Replace ``cs.fits`` and ``cs.imported_datasets`` with proxy objects.

        Only activates in ``server`` mode (or when *force* is true).
        After this call all access to those globals is routed through the
        ZMQ client.  The API's internal state is updated to share the
        new list objects.
        """
        if not force and self.mode != "server":
            return
        from chisurf.core.api._proxies import install_proxies
        install_proxies(self.client)
        self._state = SessionState(
            datasets=getattr(cs, "imported_datasets", []),
            fits=getattr(cs, "fits", []),
        )

    # ---- graph ----
    def build_fit_graph(
        self,
        fit_indices: Optional[List[int]] = None,
        fit_uids: Optional[List[str]] = None,
        include_fixed: bool = True,
        connect_fits: bool = False,
    ) -> Dict[str, Any]:
        """Build the fit/parameter graph for the selected fits.

        Local and hybrid modes answer from the process-local session state
        through the very same service the server exposes, so a graph does not
        depend on which mode asked for it.

        Parameters
        ----------
        fit_indices : list of int, optional
            Positions of the fits to include; ignored when *fit_uids* is given.
        fit_uids : list of str, optional
            Unique identifiers of the fits to include.  Defaults to every fit.
        include_fixed : bool, optional
            Include fixed parameters as nodes.  Default ``True``.
        connect_fits : bool, optional
            Additionally connect every pair of fit nodes.  Default ``False``.

        Returns
        -------
        dict
            ``{"ok": True, "graph": {"nodes": [...], "edges": [...]}}``.
        """
        if self.mode == "server" and self.client is not None:
            return self.client.graph__build(
                fit_indices=fit_indices,
                fit_uids=fit_uids,
                include_fixed=include_fixed,
                connect_fits=connect_fits,
            )
        from chisurf.server.services import graph as _graph

        return _graph.build_fit_graph(
            self._state,
            fit_indices=fit_indices,
            fit_uids=fit_uids,
            include_fixed=include_fixed,
            connect_fits=connect_fits,
        )


from chisurf.server.services._stats import (
    _safe_chi2,
    _safe_chi2r,
    _safe_n_points,
    _safe_n_free,
    _collect_member_list,
    _collect_param_list,
)
