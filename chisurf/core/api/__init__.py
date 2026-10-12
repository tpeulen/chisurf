from __future__ import annotations

from collections.abc import Callable
from typing import Any, Dict, List, Optional

import numpy as np

import chisurf as cs
from chisurf.core.api.context import PluginContext
from chisurf.core.api.live_edit import (  # noqa: F401 -- the live-object write seam
    add_dataset,
    edit_parameter,
    move_dataset,
    restore_parameter_value,
    run_fit,
    set_current_fit,
    set_fit_range,
    set_parameter_array,
    update_fit,
)
from chisurf.server.session import SessionState


def _extract_curve_data(dataset: Any) -> dict[str, Any] | None:
    """Snapshot a cached curve/group without reading or changing its active child.

    Domain curves use the trusted scientific record/reader codec. Legacy
    curve-like objects keep the bare x/y/ex/ey contract.
    """
    from chisurf.core.data import DataCurve, DataGroup
    from chisurf.core.project.session import _curve_record, _scientific_value

    def record(curve, ancestors=()):
        """Capture the known reader IRF edge along with its exact cached arrays."""
        uid = str(getattr(curve, "unique_identifier", ""))
        if uid in ancestors:
            raise ValueError("cyclic cached reader IRF dependency")
        value = _curve_record(curve)
        dependencies = (value.get("reader") or {}).get("dependencies") or {}
        if dependencies:
            source = getattr(curve.data_reader, "instrument_response_function", None)
            value["reader_inputs"] = {
                "instrument_response_function": record(source, (*ancestors, uid))
            }
        return value

    from chisurf.core.structure import Structure

    if isinstance(dataset, DataGroup):
        if any(not isinstance(member, (DataCurve, Structure)) for member in dataset):
            return None
        if not dataset:
            raise ValueError("cached curve groups require nonempty DataCurve members")
        return {
            "kind": "group",
            "group_type": type(dataset).__name__,
            "uid": str(dataset.unique_identifier),
            "name": str(dataset.name),
            "selected": dataset._current_dataset,
            "metadata": _scientific_value(dataset.meta_data or {}),
            "members": [record(member) for member in dataset],
        }
    # A structure travels as the codec's structure record (its atoms), not as
    # a curve: without it the server had nothing to build but an empty curve
    # named after the file, and every structure model read that.
    if isinstance(dataset, (DataCurve, Structure)):
        return record(dataset)
    x, y = getattr(dataset, "x", None), getattr(dataset, "y", None)
    if x is None or y is None:
        return None
    result = {"x": np.asarray(x, dtype=float).tolist(), "y": np.asarray(y, dtype=float).tolist()}
    for field in ("ex", "ey"):
        values = getattr(dataset, field, None)
        if values is not None:
            result[field] = np.asarray(values, dtype=float).tolist()
    return result


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


def dataset_objects() -> list[Any]:
    """Return a snapshot of the in-process imported-dataset objects.

    This is the API seam for GUI code that has to *read* dataset objects
    (pickers, lookups) instead of reaching into ``chisurf.imported_datasets``.
    Mutations go through :class:`ChiSurfAPI`.

    Returns
    -------
    list
        A new list; editing it does not change the session.
    """
    return list(_global_datasets())


def dataset_container() -> Any:
    """Return the live imported-dataset container (a list, or a dict of datasets).

    For the rare reader that has to see the container itself, e.g. to ask
    whether a dict-style session holds a real dataset.  Do not mutate it.
    """
    return _global_datasets()


def fit_objects() -> list[Any]:
    """Return a snapshot of the in-process fit (group) objects.

    The read-only counterpart of :func:`dataset_objects` for ``chisurf.fits``.

    Returns
    -------
    list
        A new list; editing it does not change the session.
    """
    return list(_global_fits())


def _local_datasets() -> list[Any]:
    return list(_global_datasets())


def _local_fits() -> list[Any]:
    return list(_global_fits())


def _resolve_indexed(
    items: list[Any], index: int | None = None, uid: str | None = None
) -> tuple[Any, int]:
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


def _local_dataset(
    dataset_index: int | None = None, dataset_uid: str | None = None
) -> tuple[Any, int]:
    return _resolve_indexed(_local_datasets(), dataset_index, dataset_uid)


def _local_fit(fit_index: int | None = None, fit_uid: str | None = None) -> tuple[Any, int]:
    return _resolve_indexed(_local_fits(), fit_index, fit_uid)


def _local_parameter(
    parameter_name: str,
    fit_index: int = 0,
    fit_uid: str | None = None,
    require_parameters: bool = False,
) -> tuple[Any, Any, dict[str, Any] | None]:
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
            self._state.project_resources = getattr(cs, "project_resources", None)
            self._state.history = getattr(cs, "history", None)

    # ── datasets ─────────────────────────────────────────────────

    def list_datasets(self) -> list[dict[str, Any]]:
        """Return owning-session summaries with stable indices and direct group members."""
        if self.mode == "server" and self.client is not None:
            return self.client.dataset__list()
        from chisurf.server.services.datasets import list_datasets

        return list_datasets(self._state)["datasets"]

    def get_dataset_info(
        self,
        dataset_index: int | None = None,
        dataset_uid: str | None = None,
        *,
        member_uid: str | None = None,
    ) -> dict[str, Any]:
        """Read dataset metadata, optionally identifying one direct child by ``member_uid``."""
        if self.mode == "server" and self.client is not None:
            params = {"dataset_index": dataset_index, "dataset_uid": dataset_uid}
            if member_uid is not None:
                params["member_uid"] = member_uid
            return self.client.dataset__get(**params)
        from chisurf.server.services.datasets import get_dataset_info

        return get_dataset_info(self._state, dataset_index, dataset_uid, member_uid=member_uid)

    def get_dataset_curve_data(
        self,
        dataset_index: int | None = None,
        dataset_uid: str | None = None,
        *,
        member_uid: str | None = None,
    ) -> dict[str, Any]:
        """Read exact dataset/member arrays without changing a group's active selection."""
        if self.mode == "server" and self.client is not None:
            params = {"dataset_index": dataset_index, "dataset_uid": dataset_uid}
            if member_uid is not None:
                params["member_uid"] = member_uid
            return self.client.dataset__curve_data(**params)
        from chisurf.server.services.datasets import (
            NOT_FOUND,
            _resolve_dataset,
            _resolve_dataset_member,
            service_error,
        )

        parent, index = _resolve_dataset(self._state, dataset_index, dataset_uid)
        d, member_index = _resolve_dataset_member(parent, member_uid)
        if d is None:
            return service_error("dataset not found", error_code=NOT_FOUND)
        try:
            result: dict[str, Any] = {"ok": True}
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
            if member_uid is not None:
                result.update(
                    dataset_index=index,
                    dataset_uid=str(getattr(parent, "unique_identifier", "")),
                    member_index=member_index,
                    member_uid=str(getattr(d, "unique_identifier", "")),
                )
            return result
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def load_dataset(
        self,
        experiment_reader: Any = None,
        dataset: Any = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Import a supplied cached object once into this facade's owning session.

        Supplied curve groups are validated completely before any append.
        Live aliased sessions retain their existing macro/history route.
        """
        from chisurf.server.services import INVALID_INPUT, service_error
        from chisurf.server.services.datasets import (
            _normalize_cached_group,
            _prepare_cached_dataset,
        )

        curve_data = None
        if dataset is not None:
            try:
                curve_data = _extract_curve_data(dataset)
                if curve_data is not None:
                    _prepare_cached_dataset(curve_data)
            except (TypeError, ValueError, AttributeError) as error:
                return service_error(f"invalid cached dataset: {error}", error_code=INVALID_INPUT)
        if self.mode == "server" and self.client is not None:
            params: dict[str, Any] = dict(kwargs)
            if experiment_reader is not None:
                params.setdefault("reader_name", type(experiment_reader).__name__)
                filename = getattr(experiment_reader, "filename", None) or kwargs.get("filename")
                if filename:
                    params.setdefault("filename", str(filename))
                params.setdefault("name", str(getattr(experiment_reader, "name", "dataset")))
            if dataset is None and experiment_reader is not None:
                # Reading once is only appropriate when the caller supplied no preview.
                local_data = experiment_reader.get_data(**kwargs)
                curve_data = _extract_curve_data(local_data)
                if curve_data is not None:
                    _prepare_cached_dataset(curve_data)
            if curve_data is not None:
                params["curve_data"] = curve_data
            elif dataset is not None:
                return service_error(
                    "supplied dataset has no supported curve data", error_code=INVALID_INPUT
                )
            return self.client.call("dataset.load", params)
        if self._state.datasets is not _global_datasets():
            if dataset is None:
                if experiment_reader is None:
                    return service_error(
                        "no reader or cached dataset provided", error_code=INVALID_INPUT
                    )
                dataset = experiment_reader.get_data(**kwargs)
                try:
                    curve_data = _extract_curve_data(dataset)
                    if curve_data is not None:
                        _prepare_cached_dataset(curve_data)
                except (TypeError, ValueError, AttributeError) as error:
                    return service_error(
                        f"invalid cached dataset: {error}", error_code=INVALID_INPUT
                    )
            if dataset is None:
                return service_error("reader returned no dataset", error_code=INVALID_INPUT)
            self._state.add_dataset(dataset)
            return {
                "ok": True,
                "uid": str(getattr(dataset, "unique_identifier", "")),
                "dataset_index": len(self._state.datasets) - 1,
            }
        from chisurf.macros import core_data

        local_dataset: Any = _normalize_cached_group(dataset) if dataset is not None else None
        core_data.add_dataset(
            experiment_reader=experiment_reader,
            dataset=local_dataset,
            _from_controller=True,
            **kwargs,
        )
        return {"ok": True}

    def remove_datasets(
        self,
        dataset_indices: list[int] | None = None,
        dataset_uids: list[str] | None = None,
    ) -> dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            return self.client.dataset__remove(
                dataset_indices=dataset_indices, dataset_uids=dataset_uids
            )
        from chisurf.macros import core_data

        indices = list(dataset_indices or [])
        if dataset_uids:
            for i, d in enumerate(self._state.datasets):
                if str(getattr(d, "unique_identifier", "")) in dataset_uids:
                    indices.append(i)
        if indices:
            core_data.remove_datasets(dataset_indices=list(set(indices)), _from_controller=True)
        return {"ok": True}

    def clear_datasets(self) -> dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            return self.client.dataset__clear()
        self._state.datasets.clear()
        return {"ok": True}

    def group_datasets(
        self,
        dataset_indices: list[int],
        group_name: str | None = None,
    ) -> dict[str, Any]:
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
        dataset_indices: list[int],
    ) -> dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            return self.client.dataset__ungroup(dataset_indices=dataset_indices)
        from chisurf.macros import core_data

        core_data.ungroup_datasets(
            dataset_indices=dataset_indices,
            _from_controller=True,
        )
        return {"ok": True}

    # ── fits ──────────────────────────────────────────────────────

    def list_fits(self, statistics: bool = False) -> list[dict[str, Any]]:
        """One summary row per fit of the session.

        ``chi2`` / ``chi2r`` are what the fit's last run reached (``None``: never run); with
        *statistics* every row also carries ``chi2r_current``, the reduced χ² of the parameters
        as they are now (what the fit window shows)::

            [(f["name"], f["chi2r_current"]) for f in api.list_fits(statistics=True)]
        """
        if self.mode == "server" and self.client is not None:
            return self.client.fit__list(statistics=True) if statistics else self.client.fit__list()
        result: list[dict[str, Any]] = []
        fits = list(self._state.fits)
        for idx, f in enumerate(fits):
            # the same row the server lists: what the last run reached, nothing evaluated
            chi2 = _safe_chi2(f)
            data_name = ""
            try:
                data_name = str(getattr(getattr(f, "data", None), "name", "") or "")
            except Exception:
                pass
            param_count = 0
            try:
                param_count = len(
                    getattr(getattr(f, "model", None), "parameters_all_dict", {}) or {}
                )
            except Exception:
                pass
            result.append(
                {
                    "index": idx,
                    "uid": str(getattr(f, "unique_identifier", "") or ""),
                    "name": str(getattr(f, "name", "") or ""),
                    "type": type(f).__name__,
                    "chi2": chi2,
                    "chi2r": _safe_chi2r(f),
                    "n_points": _safe_n_points(f),
                    "n_free": _safe_n_free(f),
                    "dataset_uid": str(
                        getattr(getattr(f, "data", None), "unique_identifier", "") or ""
                    ),
                    "dataset_name": data_name,
                    "model_name": str(getattr(getattr(f, "model", None), "name", "") or ""),
                    "parameter_count": param_count,
                    "data": {
                        "name": str(getattr(getattr(f, "data", None), "name", "") or ""),
                        "uid": str(
                            getattr(getattr(f, "data", None), "unique_identifier", "") or ""
                        ),
                        "filename": str(getattr(getattr(f, "data", None), "filename", "") or ""),
                        "experiment": str(
                            getattr(getattr(f, "data", None), "experiment", "")
                            or getattr(
                                getattr(getattr(f, "data", None), "experiment", None), "name", ""
                            )
                            or ""
                        ),
                    }
                    if hasattr(f, "data") and f.data is not None
                    else {},
                    "model": {
                        "name": str(getattr(getattr(f, "model", None), "name", "") or ""),
                        "n_points": _safe_n_points(f),
                        "n_free": _safe_n_free(f),
                        "chi2r": _safe_chi2r(f),
                        "parameters_all": _collect_param_list(
                            f, fit_uid=str(getattr(f, "unique_identifier", "") or "")
                        ),
                    }
                    if hasattr(f, "model") and f.model is not None
                    else {},
                }
            )
            if statistics:
                result[-1]["chi2r_current"] = _safe_chi2r_current(f)
        return result

    def get_fit_info(
        self, fit_index: int | None = None, fit_uid: str | None = None
    ) -> dict[str, Any]:
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
                "fit_range": _safe_fit_range(fit),
                "chi2r_current": _safe_chi2r_current(fit),
                "dataset_uid": str(
                    getattr(getattr(fit, "data", None), "unique_identifier", "") or ""
                ),
                "dataset_name": str(getattr(getattr(fit, "data", None), "name", "") or ""),
                "model_name": str(getattr(getattr(fit, "model", None), "name", "") or ""),
                "parameter_count": len(params),
                "parameters": params,
                "members": _collect_member_list(fit),
                "data": {
                    "name": str(getattr(getattr(fit, "data", None), "name", "") or ""),
                    "uid": str(getattr(getattr(fit, "data", None), "unique_identifier", "") or ""),
                    "filename": str(getattr(getattr(fit, "data", None), "filename", "") or ""),
                    "experiment": str(
                        getattr(getattr(fit, "data", None), "experiment", "")
                        or getattr(
                            getattr(getattr(fit, "data", None), "experiment", None), "name", ""
                        )
                        or ""
                    ),
                }
                if hasattr(fit, "data") and fit.data is not None
                else {},
                "model": {
                    "name": str(getattr(getattr(fit, "model", None), "name", "") or ""),
                    "n_points": _safe_n_points(fit),
                    "n_free": _safe_n_free(fit),
                    "chi2r": _safe_chi2r(fit),
                    "parameters_all": _collect_param_list(
                        fit, fit_uid=str(getattr(fit, "unique_identifier", "") or "")
                    ),
                }
                if hasattr(fit, "model") and fit.model is not None
                else {},
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
                fit_index=fit_index,
                fit_uid=fit_uid,
                engine=engine,
                targets=targets,
                joint=joint,
                condition=condition,
                p_value=p_value,
                options=options or None,
                global_posterior=global_posterior,
            )
        from chisurf.server.services import fits as _fits

        class _State:
            """Adapter presenting the process-local fits to the service layer."""

            fits = property(lambda self: _local_fits())

        return _fits.fit_posterior(
            _State(),
            fit_index=fit_index,
            fit_uid=fit_uid,
            engine=engine,
            targets=targets,
            joint=joint,
            condition=condition,
            p_value=p_value,
            options=options or None,
            global_posterior=global_posterior,
        )

    def reweight_prior(
        self,
        priors: dict[str, Any],
        fit_index: int | None = None,
        fit_uid: str | None = None,
        p_value: float = 0.68,
    ) -> dict[str, Any]:
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
                priors=priors,
                fit_index=fit_index,
                fit_uid=fit_uid,
                p_value=p_value,
            )
        from chisurf.server.services import fits as _fits

        class _State:
            """Adapter presenting the process-local fits to the service layer."""

            fits = property(lambda self: _local_fits())

        return _fits.fit_reweight_prior(
            _State(),
            priors=priors,
            fit_index=fit_index,
            fit_uid=fit_uid,
            p_value=p_value,
        )

    def derived_quantities(
        self,
        fit_index: int | None = None,
        fit_uid: str | None = None,
        names: list[str] | None = None,
        p_value: float = 0.68,
        max_draws: int = 2048,
    ) -> dict[str, Any]:
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
                fit_index=fit_index,
                fit_uid=fit_uid,
                names=names,
                p_value=p_value,
                max_draws=max_draws,
            )
        from chisurf.server.services import fits as _fits

        class _State:
            """Adapter presenting the process-local fits to the service layer."""

            fits = property(lambda self: _local_fits())

        return _fits.fit_derived(
            _State(),
            fit_index=fit_index,
            fit_uid=fit_uid,
            names=names,
            p_value=p_value,
            max_draws=max_draws,
        )

    def run_fit(
        self,
        fit_index: int | None = None,
        fit_uid: str | None = None,
        local_first: bool | None = None,
    ) -> dict[str, Any]:
        """Run a fit; *local_first* fits a group's members one by one before the global step."""
        if self.mode == "server" and self.client is not None:
            extra = {} if local_first is None else {"local_first": bool(local_first)}
            return self.client.fit__run(fit_index=fit_index, fit_uid=fit_uid, **extra)
        fit, idx = _local_fit(fit_index, fit_uid)
        if fit is None:
            return {"ok": False, "error": "fit not found"}
        try:
            chi2_before = _safe_chi2(fit)
            if local_first is not None and getattr(fit, "grouped_fits", None) is not None:
                fit.run(local_first=bool(local_first))
            else:
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
        dataset_indices: list[int],
        model_name: str | None = None,
        model_kw: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            call_kw: dict[str, Any] = {"dataset_indices": list(dataset_indices or [])}
            if model_name is not None:
                call_kw["model_name"] = str(model_name)
            if isinstance(model_kw, dict):
                call_kw["model_kw"] = model_kw
            return self.client.fit__create(**call_kw)
        from chisurf.macros import core_fit

        kwargs: dict[str, Any] = {"dataset_indices": list(dataset_indices or [])}
        if isinstance(model_kw, dict):
            kwargs["model_kw"] = model_kw
        if model_name is not None:
            kwargs["model_name"] = str(model_name)
        return core_fit.add_fit(**kwargs)

    def remove_fits(
        self,
        fit_indices: list[int] | None = None,
        fit_uids: list[str] | None = None,
    ) -> dict[str, Any]:
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

    def clear_fits(self) -> dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            return self.client.fit__clear()
        self._state.fits.clear()
        return {"ok": True}

    def fit_create(
        self, dataset_index: int = 0, model_name: str | None = None, fit_name: str | None = None
    ) -> dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            return self.client.fit__create(
                dataset_index=dataset_index, model_name=model_name, fit_name=fit_name
            )
        return {"ok": False, "error": "fit.create requires server mode for server-side creation"}

    def fit_update(
        self, fit_index: int | None = None, fit_uid: str | None = None
    ) -> dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            return self.client.fit__update(fit_index=fit_index, fit_uid=fit_uid)
        fit, _ = _local_fit(fit_index, fit_uid)
        if fit is None:
            return {"ok": False, "error": "fit not found"}
        try:
            if hasattr(fit, "update"):
                from chisurf.core.fitting.link_propagation import refresh_link_followers

                fit.update()
                refresh_link_followers(_local_fits(), fit)
                return {"ok": True}
            return {"ok": False, "error": "fit has no update method"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def set_fit_range(
        self,
        xmin: int,
        xmax: int,
        fit_index: int | None = None,
        fit_uid: str | None = None,
    ) -> dict[str, Any]:
        """Set the index range of the data points a fit uses.

        Parameters
        ----------
        xmin, xmax : int
            First and last data-point index of the range.
        fit_index : int, optional
            Positional index of the fit.
        fit_uid : str, optional
            Unique identifier of the fit (preferred).

        Returns
        -------
        dict
            ``{"ok": True}`` or an error result.
        """
        if self.mode == "server" and self.client is not None:
            return self.client.fit__set_fit_range(
                fit_index=fit_index, fit_uid=fit_uid, xmin=int(xmin), xmax=int(xmax)
            )
        from chisurf.server.services.fits import fit_set_fit_range

        return fit_set_fit_range(self._state, fit_index, fit_uid, int(xmin), int(xmax))

    def _fit_call(self, rpc: str, service: str, **params: Any) -> Any:
        """One fit RPC: over the client in ``server`` mode, the service on this state otherwise."""
        if self.mode == "server" and self.client is not None:
            return getattr(self.client, rpc)(**params)
        from chisurf.server.services import fits as svc

        return getattr(svc, service)(self._state, **params)

    def set_fit_dataset(
        self, dataset_uid: str, fit_uid: str | None = None, fit_index: int | None = None
    ) -> dict[str, Any]:
        """Attach the dataset *dataset_uid* to the fit (the controller's ``…``)."""
        return self._fit_call(
            "fit__set_dataset",
            "fit_set_dataset",
            fit_index=fit_index,
            fit_uid=fit_uid,
            dataset_uid=dataset_uid,
        )

    def set_fit_result_idx(
        self, result_idx: int, fit_uid: str | None = None, fit_index: int | None = None
    ) -> dict[str, Any]:
        """Show stored result *result_idx* (0-based) of the fit."""
        return self._fit_call(
            "fit__set_result_idx",
            "fit_set_result_idx",
            fit_index=fit_index,
            fit_uid=fit_uid,
            result_idx=int(result_idx),
        )

    def auto_fit_range(self, fit_uid: str | None = None, fit_index: int | None = None) -> Any:
        """Set the fit range from the data (the reader's ``autofitrange``); returns it."""
        return self._fit_call(
            "fit__range_auto", "fit_range_auto", fit_index=fit_index, fit_uid=fit_uid
        )

    def set_fit_grid_range(
        self,
        x0: int,
        x1: int,
        y0: int,
        y1: int,
        fit_uid: str | None = None,
        fit_index: int | None = None,
    ) -> dict[str, Any]:
        """Fit only the rectangle ``x0..x1`` × ``y0..y1`` of a 2-D grid dataset."""
        return self._fit_call(
            "fit__set_grid_range",
            "fit_set_grid_range",
            x0=int(x0),
            x1=int(x1),
            y0=int(y0),
            y1=int(y1),
            fit_index=fit_index,
            fit_uid=fit_uid,
        )

    def model_search_available(
        self, fit_uid: str | None = None, fit_index: int | None = None
    ) -> bool:
        """Whether BFF can search the fit's model structure."""
        result = self._fit_call(
            "fit__model_search_available",
            "fit_model_search_available",
            fit_index=fit_index,
            fit_uid=fit_uid,
        )
        return bool(result.get("available")) if isinstance(result, dict) else bool(result)

    def model_search(
        self,
        fit_uid: str | None = None,
        fit_index: int | None = None,
        search_fit_settings: bool = False,
    ) -> dict[str, Any]:
        """Search the model structure (MCTS) and apply the winner; see ``fit.model_search``."""
        return self._fit_call(
            "fit__model_search",
            "fit_model_search",
            fit_index=fit_index,
            fit_uid=fit_uid,
            search_fit_settings=bool(search_fit_settings),
        )

    def start_sampling(
        self,
        target_directory: str,
        fit_uid: str | None = None,
        fit_index: int | None = None,
        n_steps: int = 1000,
        n_runs: int = 1,
        **settings: Any,
    ) -> dict[str, Any]:
        """Start sampling the fit's posterior into *target_directory*; returns ``job_id``."""
        return self._fit_call(
            "fit__sample_start",
            "fit_sample_start",
            fit_index=fit_index,
            fit_uid=fit_uid,
            n_steps=int(n_steps),
            n_runs=int(n_runs),
            target_directory=str(target_directory),
            **settings,
        )

    def sampling_status(self, job_id: str) -> dict[str, Any]:
        """Status, progress and convergence of a sampling job."""
        return self._fit_call("fit__sample_status", "fit_sample_status", job_id=str(job_id))

    def cancel_sampling(self, job_id: str) -> dict[str, Any]:
        """Ask a sampling job to stop."""
        return self._fit_call("fit__sample_cancel", "fit_sample_cancel", job_id=str(job_id))

    def select_group_member(self, member_index: int, fit_uid: str) -> dict[str, Any]:
        """Make member *member_index* of the fit group the one the fit shows and edits."""
        return self._fit_call(
            "fit__group_select_member",
            "fit_group_select_member",
            fit_uid=fit_uid,
            member_index=int(member_index),
        )

    # ── parameters ────────────────────────────────────────────────

    def get_parameter(
        self, parameter_name: str, fit_index: int = 0, fit_uid: str | None = None
    ) -> dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            return self.client.parameter__get(
                parameter_name=parameter_name, fit_index=fit_index, fit_uid=fit_uid
            )
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

    def set_parameter_value(
        self, parameter_name: str, value: float, fit_index: int = 0, fit_uid: str | None = None
    ) -> dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            return self.client.parameter__set_value(
                parameter_name=parameter_name, value=value, fit_index=fit_index, fit_uid=fit_uid
            )
        fit, p, error = _local_parameter(
            parameter_name, fit_index, fit_uid, require_parameters=True
        )
        if error is not None:
            return error
        try:
            p.value = float(value)
            if hasattr(fit.model, "update_model"):
                from chisurf.core.fitting.link_propagation import refresh_link_followers

                fit.model.update()
                refresh_link_followers(_local_fits(), fit)
            if hasattr(fit.model, "finalize"):
                fit.model.finalize()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def set_parameter_fixed(
        self, parameter_name: str, fixed: bool, fit_index: int = 0, fit_uid: str | None = None
    ) -> dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            return self.client.parameter__set_fixed(
                parameter_name=parameter_name, fixed=fixed, fit_index=fit_index, fit_uid=fit_uid
            )
        fit, p, error = _local_parameter(
            parameter_name, fit_index, fit_uid, require_parameters=True
        )
        if error is not None:
            return error
        try:
            p.fixed = bool(fixed)
            if hasattr(fit.model, "finalize"):
                fit.model.finalize()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def set_parameter_bounds(
        self, parameter_name: str, bounds: tuple, fit_index: int = 0, fit_uid: str | None = None
    ) -> dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            return self.client.parameter__set_bounds(
                parameter_name=parameter_name,
                lower=bounds[0],
                upper=bounds[1],
                fit_index=fit_index,
                fit_uid=fit_uid,
            )
        fit, p, error = _local_parameter(
            parameter_name, fit_index, fit_uid, require_parameters=True
        )
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

    def model_finalize(self, fit_index: int = 0, fit_uid: str | None = None) -> dict[str, Any]:
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

    def model_set_parse_function(
        self, parse_function: str, fit_index: int = 0, fit_uid: str | None = None
    ) -> dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            return self.client.model__set_parse_function(
                parse_function=parse_function, fit_index=fit_index, fit_uid=fit_uid
            )
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

    def set_parameter_bounds_on(
        self, parameter_name: str, bounds_on: bool, fit_index: int = 0, fit_uid: str | None = None
    ) -> dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            return self.client.parameter__set_bounds_on(
                parameter_name=parameter_name,
                bounds_on=bounds_on,
                fit_index=fit_index,
                fit_uid=fit_uid,
            )
        _, p, error = _local_parameter(parameter_name, fit_index, fit_uid, require_parameters=True)
        if error is not None:
            return error
        try:
            p.bounds_on = bool(bounds_on)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def edit_parameter(
        self,
        parameter_uid: str,
        *,
        fit_uid: str | None = None,
        parameter_name: str = "",
        value: float | None = None,
        fixed: bool | None = None,
        bounds: tuple | None = None,
        bounds_on: bool | None = None,
    ) -> dict[str, Any]:
        """Change one parameter addressed by its unique identifier.

        A model editor lists parameters of several groups, and names repeat
        across groups (each diffusion preset has its own ``N``), so an editor
        addresses a parameter by its uid. Each given field is one
        ``parameter.*`` call, in the order value, fixed, bounds, bounds_on;
        the first failure is returned.

        Parameters
        ----------
        parameter_uid : str
            The parameter's ``unique_identifier`` (the ``uid`` of an editor or fit DTO row).
        fit_uid : str, optional
            The fit owning the parameter; its model is updated after the change.
        parameter_name : str
            The name, for messages only.
        value, fixed, bounds, bounds_on : optional
            The fields to set; ``None`` leaves a field as it is.

        Returns
        -------
        dict
            ``{"ok": True}`` or the first error result.
        """
        from chisurf.server.services import parameters as svc

        changes = []
        if value is not None:
            changes.append(("set_value", "value", float(value)))
        if fixed is not None:
            changes.append(("set_fixed", "fixed", bool(fixed)))
        if bounds is not None:
            changes.append(("set_bounds", "bounds", tuple(bounds)))
        if bounds_on is not None:
            changes.append(("set_bounds_on", "bounds_on", bool(bounds_on)))
        result: dict[str, Any] = {"ok": True}
        for rpc, key, field_value in changes:
            address = {
                "parameter_name": str(parameter_name or ""),
                "parameter_uid": str(parameter_uid),
                "owner_uid": fit_uid,
                "fit_uid": fit_uid,
            }
            if self.mode == "server" and self.client is not None:
                method = getattr(self.client, f"parameter__{rpc}")
                if key == "bounds":
                    result = method(lower=field_value[0], upper=field_value[1], **address)
                else:
                    result = method(**{key: field_value}, **address)
            else:
                service = getattr(svc, f"{rpc.replace('set_', 'set_parameter_')}")
                result = service(self._state, **{key: field_value}, **address)
            if isinstance(result, dict) and result.get("ok") is False:
                return result
        return result

    # ── model editor ──────────────────────────────────────────────

    def model_editor(self, fit_uid: str | None = None, fit_index: int | None = None) -> Any:
        """The fit's model editor: its ``view.json`` resolved against the model, as data.

        See :func:`chisurf.server.services.model_svc.model_editor`. Returns the
        editor dict, ``None`` for a model without a view spec, or an error result.
        """
        if self.mode == "server" and self.client is not None:
            return self.client.model__editor(fit_index=fit_index, fit_uid=fit_uid)
        from chisurf.server.services.model_svc import model_editor

        result = model_editor(self._state, fit_index, fit_uid)
        return result.get("editor") if result.get("ok") else result

    def model_action(
        self, action: str, fit_uid: str | None = None, fit_index: int | None = None
    ) -> dict[str, Any]:
        """Press a button of the model's editor (an ``action`` its ``view.json`` declares)."""
        if self.mode == "server" and self.client is not None:
            return self.client.model__action(action=action, fit_index=fit_index, fit_uid=fit_uid)
        from chisurf.server.services.model_svc import model_action

        return model_action(self._state, action, fit_index, fit_uid)

    def model_curve_set(
        self,
        curve: str,
        dataset_uid: str,
        member_uid: str | None = None,
        fit_uid: str | None = None,
        fit_index: int | None = None,
    ) -> dict[str, Any]:
        """Give a curve picker of the model's editor (``curve`` = its ``key``) a session dataset."""
        if self.mode == "server" and self.client is not None:
            return self.client.model__curve_set(
                curve=str(curve),
                dataset_uid=str(dataset_uid),
                member_uid=member_uid,
                fit_index=fit_index,
                fit_uid=fit_uid,
            )
        from chisurf.server.services.model_sections import model_curve_set

        return model_curve_set(
            self._state, str(curve), str(dataset_uid), member_uid, fit_index, fit_uid
        )

    def model_curve_unload(
        self, curve: str, fit_uid: str | None = None, fit_index: int | None = None
    ) -> dict[str, Any]:
        """Unload the curve a curve picker of the model's editor holds."""
        if self.mode == "server" and self.client is not None:
            return self.client.model__curve_unload(
                curve=str(curve), fit_index=fit_index, fit_uid=fit_uid
            )
        from chisurf.server.services.model_sections import model_curve_unload

        return model_curve_unload(self._state, str(curve), fit_index, fit_uid)

    def model_section_call(
        self,
        section: str,
        op: str,
        args: dict[str, Any] | None = None,
        fit_uid: str | None = None,
        fit_index: int | None = None,
    ) -> dict[str, Any]:
        """Run operation *op* of a custom section of the model's editor (``section`` = its ``id``)."""
        if self.mode == "server" and self.client is not None:
            return self.client.model__section_call(
                section=str(section),
                op=str(op),
                args=dict(args or {}),
                fit_index=fit_index,
                fit_uid=fit_uid,
            )
        from chisurf.server.services.model_sections import model_section_call

        return model_section_call(
            self._state, str(section), str(op), dict(args or {}), fit_index, fit_uid
        )

    def link_parameter(
        self,
        parameter_uid: str,
        target_parameter_uid: str,
        fit_uid: str | None = None,
        owner_uid: str | None = None,
    ) -> dict[str, Any]:
        """Link the parameter *parameter_uid* (of fit *fit_uid*) to *target_parameter_uid*, anywhere."""
        address = {
            "parameter_uid": str(parameter_uid),
            "owner_uid": owner_uid or fit_uid,
            "fit_uid": fit_uid,
            "target_parameter_uid": str(target_parameter_uid),
        }
        if self.mode == "server" and self.client is not None:
            return self.client.parameter__link(**address)
        from chisurf.server.services.parameters import parameter_link

        return parameter_link(self._state, **address)

    def unlink_parameter(
        self, parameter_uid: str, fit_uid: str | None = None, owner_uid: str | None = None
    ) -> dict[str, Any]:
        """Drop the link of the parameter *parameter_uid*."""
        address = {
            "parameter_uid": str(parameter_uid),
            "owner_uid": owner_uid or fit_uid,
            "fit_uid": fit_uid,
        }
        if self.mode == "server" and self.client is not None:
            return self.client.parameter__unlink(**address)
        from chisurf.server.services.parameters import parameter_unlink

        return parameter_unlink(self._state, **address)

    def model_code_files(
        self, fit_uid: str | None = None, fit_index: int | None = None
    ) -> dict[str, Any]:
        """The model's source, its ``view.json`` and the files of its folder (the Code face's)."""
        if self.mode == "server" and self.client is not None:
            return self.client.model__code_files(fit_index=fit_index, fit_uid=fit_uid)
        from chisurf.server.services.model_svc import model_code_files

        return model_code_files(self._state, fit_index, fit_uid)

    def model_code_apply(
        self, path: str, code: str, fit_uid: str | None = None, fit_index: int | None = None
    ) -> dict[str, Any]:
        """Save an edit of a model file and apply it to the fit (its module re-executed)."""
        if self.mode == "server" and self.client is not None:
            return self.client.model__code_apply(
                path=str(path), code=str(code), fit_index=fit_index, fit_uid=fit_uid
            )
        from chisurf.server.services.model_svc import model_code_apply

        return model_code_apply(self._state, str(path), str(code), fit_index, fit_uid)

    def model_state_get(
        self, fit_uid: str | None = None, fit_index: int | None = None
    ) -> dict[str, Any]:
        """The model's JSON-safe state, including what its editor's controls bind."""
        if self.mode == "server" and self.client is not None:
            return self.client.model__state_get(fit_index=fit_index, fit_uid=fit_uid)
        from chisurf.server.services.model_svc import model_state_get

        return model_state_get(self._state, fit_index, fit_uid)

    def model_state_set(
        self, state_data: dict[str, Any], fit_uid: str | None = None, fit_index: int | None = None
    ) -> dict[str, Any]:
        """Set model state: the allow-listed attributes and the controls its ``view.json`` binds."""
        if self.mode == "server" and self.client is not None:
            return self.client.model__state_set(
                state_data=dict(state_data), fit_index=fit_index, fit_uid=fit_uid
            )
        from chisurf.server.services.model_svc import model_state_set

        return model_state_set(self._state, dict(state_data), fit_index, fit_uid)

    def model_component_add(
        self, target: str, fit_uid: str | None = None, fit_index: int | None = None
    ) -> dict[str, Any]:
        """Add a component to the editor's component group *target* (its ``dynamic_group``)."""
        if self.mode == "server" and self.client is not None:
            return self.client.model__component_add(
                target=target, fit_index=fit_index, fit_uid=fit_uid
            )
        from chisurf.server.services.model_svc import model_component_add

        return model_component_add(self._state, fit_index=fit_index, fit_uid=fit_uid, target=target)

    def model_component_remove(
        self,
        target: str,
        component_index: int = -1,
        fit_uid: str | None = None,
        fit_index: int | None = None,
    ) -> dict[str, Any]:
        """Remove component *component_index* (``-1``: the last) of the group *target*."""
        if self.mode == "server" and self.client is not None:
            return self.client.model__component_remove(
                component_index=int(component_index),
                target=target,
                fit_index=fit_index,
                fit_uid=fit_uid,
            )
        from chisurf.server.services.model_svc import model_component_remove

        return model_component_remove(
            self._state,
            int(component_index),
            fit_index=fit_index,
            fit_uid=fit_uid,
            target=target,
        )

    # ── projects ──────────────────────────────────────────────────

    def get_project_info(self) -> dict[str, Any]:
        if self.mode == "server" and self.client is not None:
            return self.client.project__info()
        return {
            "ok": True,
            "project_path": None,
            "fit_count": len(self._state.fits),
            "dataset_count": len(self._state.datasets),
        }

    def save_project(self, target_path: str, project_name: str | None = None) -> dict[str, Any]:
        """Save this API's session with the canonical portable project service."""
        if self.mode == "server" and self.client is not None:
            return self.client.project__save(target_path=target_path, project_name=project_name)
        from chisurf.server.services.projects import save_project

        return save_project(self._state, target_path, project_name)

    def load_project(self, project_path: str) -> dict[str, Any]:
        """Stage and restore a portable project into this API's explicit session."""
        if self.mode == "server" and self.client is not None:
            if self._project_gui() is not None:
                return self._replace_remote_project(project_path=project_path)
            return self.client.project__load(project_path=project_path)
        from chisurf.server.services.projects import load_project

        return load_project(self._state, project_path)

    def capture_project(self, project_name: str = "chisurf_project"):
        """Capture this API's authoritative session as a detached Project."""
        from chisurf.core.project.capture import project_from_capture_reply
        from chisurf.core.project.transition import _bound_project_gui
        from chisurf.core.project.ui_state import get_ui_state
        from chisurf.server.services.projects import _capture_project

        ui_state = get_ui_state(_bound_project_gui(self._state))
        if self.mode == "server" and self.client is not None:
            result = self.client.call("project.capture", {"ui_state": ui_state})
            return project_from_capture_reply(result, name=project_name)
        return _capture_project(self._state, name=project_name, ui_state=ui_state)

    def restore_project_payload(self, project: Any) -> dict[str, Any]:
        """Restore a detached Project through the owning session boundary."""
        if self.mode == "server" and self.client is not None:
            if self._project_gui() is not None:
                return self._replace_remote_project(project=project)
            return self.client.call(
                "project.restore_payload",
                {
                    "project": project.to_dict(),
                    "resources": project.resources.to_transport_dict(),
                },
            )
        from chisurf.server.services.projects import restore_project_payload

        return restore_project_payload(self._state, project)

    def _replace_remote_project(
        self,
        *,
        project: Any = None,
        project_path: str | None = None,
        reset: bool = False,
    ) -> dict[str, Any]:
        """Authorize on the GUI before using the remote owner's staged transaction."""
        from chisurf.core.project import Project, capture_session
        from chisurf.core.project.project import ResourceContext
        from chisurf.server.services import OPERATION_FAILED, service_error
        from chisurf.server.services.projects import _public_transition

        def load():
            """Decode detached science without invoking a public replacement RPC."""
            if reset:
                return capture_session([], [], name="untitled"), None
            if project_path is None:
                return project, None
            result = self.client.call("project.read", {"project_path": project_path})
            if not isinstance(result, dict) or result.get("ok") is not True:
                raise RuntimeError(result.get("error", "Project read failed"))
            decoded = Project.from_dict(result["project"])
            decoded.resources = ResourceContext.from_transport_dict(result["resources"])
            return decoded, result["path"]

        try:
            attached = self.client.call("project.presentation.attach")
            if not isinstance(attached, dict) or attached.get("ok") is not True:
                raise RuntimeError("Remote owner did not accept GUI presentation ownership")
            return _public_transition(
                self._state,
                load,
                reset=reset,
                client=self.client,
            )
        except Exception as exc:
            return service_error(str(exc), error_code=OPERATION_FAILED, exception=exc)

    def _project_gui(self) -> Any:
        """Retain an attached GUI rather than treating a missing global as consent."""
        return getattr(self._state, "_project_gui", None) or getattr(cs, "cs", None)

    # ── convenience ───────────────────────────────────────────────

    def ping(self) -> dict[str, Any]:
        if self.client is not None:
            return self.client.meta__ping()
        return {"ok": True, "status": "alive-local"}

    def session_describe(self) -> dict[str, Any]:
        if self.client is not None:
            return self.client.session__describe()
        return {
            "ok": True,
            "datasets": self.list_datasets(),
            "fits": self.list_fits(),
            "dataset_count": len(self._state.datasets),
            "fit_count": len(self._state.fits),
        }

    def session_snapshot(self) -> dict[str, Any]:
        if self.client is not None:
            return self.client.session__snapshot()
        return {
            "ok": True,
            "snapshot": {
                "dataset_count": len(self._state.datasets),
                "fit_count": len(self._state.fits),
            },
        }

    def session_restore(self, project_path: str | None = None) -> dict[str, Any]:
        """Open or reset through the owning project's guarded lifecycle."""
        if project_path:
            return self.load_project(project_path)
        if self.mode == "server" and self.client is not None:
            if self._project_gui() is not None:
                return self._replace_remote_project(reset=True)
            return self.client.session__restore(project_path=project_path)
        from chisurf.server.services.projects import reset_project

        return reset_project(self._state)

    @property
    def fit_count(self) -> int:
        fits = self.list_fits()
        return len(fits)

    @property
    def dataset_count(self) -> int:
        datasets = self.list_datasets()
        return len(datasets)

    def subscribe(self, topic: str = "", callback: Callable | None = None) -> Any:
        if self.client is not None:
            return self.client.subscribe(topic, callback)
        return None

    def drain(self) -> None:
        """Process all buffered ZMQ subscriber events from the main thread."""
        if self.client is not None:
            self.client.drain()

    def list_methods(self) -> list[str]:
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

        gui = self._project_gui()
        if gui is not None:
            attached = self.client.call("project.presentation.attach")
            if not isinstance(attached, dict) or attached.get("ok") is not True:
                raise RuntimeError("Remote owner did not accept GUI presentation ownership")
        install_proxies(self.client)
        self._state = SessionState(
            datasets=getattr(cs, "imported_datasets", []),
            fits=getattr(cs, "fits", []),
        )
        if gui is not None:
            self._state._project_gui = gui

    # ---- graph ----
    def build_fit_graph(
        self,
        fit_indices: list[int] | None = None,
        fit_uids: list[str] | None = None,
        include_fixed: bool = True,
        connect_owners: bool = False,
    ) -> dict[str, Any]:
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
        connect_owners : bool, optional
            Additionally connect every pair of *owner* nodes — fits and
            registered parameter groups alike.  Default ``False``.

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
                connect_owners=connect_owners,
            )
        from chisurf.server.services import graph as _graph

        return _graph.build_fit_graph(
            self._state,
            fit_indices=fit_indices,
            fit_uids=fit_uids,
            include_fixed=include_fixed,
            connect_owners=connect_owners,
        )


from chisurf.server.services._stats import (
    _collect_member_list,
    _collect_param_list,
    _safe_chi2,
    _safe_chi2r,
    _safe_chi2r_current,
    _safe_fit_range,
    _safe_n_free,
    _safe_n_points,
)
