"""The curve pickers and the ``custom`` sections of a model's editor, as data and as declared writes.

:func:`chisurf.server.services.model_svc.model_editor` resolves a model's
``view.json`` into plain data a client draws. Two kinds of section need more than
a bound attribute:

* ``curve_input`` -- a curve the model takes (the IRF, a background decay, a
  linearisation table, a described model's measurement slot). Resolved to the
  name of the curve it holds (and the IRF's FWHM); written by
  ``model.curve.set`` with a dataset of the session and ``model.curve.unload``.
* ``custom`` -- a section with behaviour of its own (``scalar_table``,
  ``rate_matrix``, ``kappa2_controls``, ``anisotropy_diagnostics``, ``lcurve``,
  ``path_list``, ``background_run``, ``fit_mixer``, ``global_parameter_table``,
  and the ``lifetime_amplitude_options`` a component group carries in its
  header). Each kind has a resolver (what it shows) and a set of operations
  (``model.section.call``), every one checked against what the section declares.

The model's ``view.json`` stays the allow-list: an operation reaches a section
only if the spec declares that section, and only the attributes, methods and
actions the section itself names.
"""

from __future__ import annotations

import json
import math
import pathlib
from typing import Any, Callable

import numpy as np

from chisurf.server.services import (
    INVALID_INPUT,
    INVALID_STATE,
    NOT_FOUND,
    OPERATION_FAILED,
    ServiceResult,
    _resolve_fit,
    service_error,
)
from chisurf.server.session import SessionState

#: The ``custom`` keys a client can draw from what this module resolves.
CUSTOM_KEYS = (
    "scalar_table",
    "rate_matrix",
    "kappa2_controls",
    "anisotropy_diagnostics",
    "lcurve",
    "path_list",
    "background_run",
    "fit_mixer",
    "global_parameter_table",
    "lifetime_amplitude_options",
)


# ── small helpers ──────────────────────────────────────────────────────────


def _model_svc():
    from chisurf.server.services import model_svc

    return model_svc


def _plain(value: Any) -> Any:
    """*value* as JSON data: numpy scalars and arrays unwrapped, mappings and sequences walked."""
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, np.ndarray):
        return [_plain(v) for v in value.tolist()]
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if value is None or isinstance(value, (bool, int, str)):
        return value
    return str(value)


def _read(obj: Any, name: str, default: Any = None) -> Any:
    """``obj.name`` (dotted), called when it is a method; *default* if it is missing or raises."""
    if not name or obj is None:
        return default
    value = obj
    try:
        for part in str(name).split("."):
            value = getattr(value, part)
        return value() if callable(value) else value
    except Exception:  # noqa: BLE001 - a property may raise; the section then shows the default
        return default


def _rows(parameters: list, fit_uid: str) -> list[dict]:
    return [_model_svc()._parameter_row(p, fit_uid) for p in parameters if p is not None]


def _options(section: Any) -> dict:
    return _plain(dict(getattr(section, "options", None) or {}))


def section_id(key: str, target: str | None) -> str:
    """The address of a custom section in its model's editor: ``key:target``."""
    return f"{key}:{target or ''}"


def curve_id(section: Any) -> str:
    """The address of a ``curve_input``: ``target.name_attr``, or the action and its fixed payload."""
    target = str(getattr(section, "target", "") or "")
    name_attr = str(getattr(section, "name_attr", "") or "")
    if target and name_attr:
        return f"{target}.{name_attr}"
    fixed = json.dumps(dict(getattr(section, "action_fixed", None) or {}), sort_keys=True)
    return f"{getattr(section, 'select_action', '')}:{fixed}"


def declared_sections(model: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """``(curves, customs)``: the model's ``curve_input`` and custom sections by their address.

    A component group's ``header_keys`` are custom sections of that group.
    """
    from chisurf.core import dataspec as vs

    spec = _model_svc()._model_view(model)
    curves: dict[str, Any] = {}
    customs: dict[str, Any] = {}
    if spec is None:
        return curves, customs
    for section in spec.flat_sections():
        if isinstance(section, vs.CurveInputSection):
            curves[curve_id(section)] = section
        elif isinstance(section, vs.CustomSection):
            customs[section_id(section.key, section.target)] = section
        elif isinstance(section, vs.DynamicGroupSection):
            for key in section.header_keys:
                customs[section_id(key, section.target)] = vs.CustomSection(
                    key=str(key), target=section.target
                )
    return curves, customs


# ── curve inputs ─────────────────────────────────────────────────────────────


def _held_curve(model: Any, section: Any) -> Any:
    target = str(getattr(section, "target", "") or "")
    name_attr = str(getattr(section, "name_attr", "") or "")
    if not (target and name_attr):
        return None
    group = _model_svc()._resolve_target(model, target)
    return _read(group, name_attr) if group is not None else None


def resolve_curve_input(section: Any, model: Any) -> dict[str, Any]:
    """A ``curve_input`` as data: the curve it holds now (its name; the IRF's FWHM)."""
    curve = _held_curve(model, section)
    name = (
        (getattr(curve, "name", None) or getattr(curve, "filename", None))
        if curve is not None
        else None
    )
    fwhm = None
    if str(getattr(section, "name_attr", "") or "") == "irf" and curve is not None:
        fwhm = _plain(getattr(curve, "fwhm", None))
    return {
        "type": "curve_input",
        "key": curve_id(section),
        "label": str(getattr(section, "label", "") or ""),
        "curve_name": str(name or ""),
        "loaded": curve is not None,
        "fwhm": fwhm,
        "shows_fwhm": str(getattr(section, "name_attr", "") or "") == "irf",
        "can_unload": bool(getattr(section, "unload_action", "")),
    }


def _session_curve(state: SessionState, dataset_uid: str, member_uid: str | None) -> Any:
    from chisurf.server.services.datasets import _resolve_dataset, _resolve_dataset_member

    dataset, _index = _resolve_dataset(state, dataset_uid=str(dataset_uid))
    if dataset is None:
        return None
    curve, _member = _resolve_dataset_member(dataset, member_uid)
    return curve


def _publish(event_bus: Any, fit: Any, **payload: Any) -> None:
    if event_bus is not None:
        event_bus.publish(
            "model.state.changed",
            {"fit_uid": str(getattr(fit, "unique_identifier", "") or ""), **payload},
        )


def model_curve_set(
    state: SessionState,
    curve: str,
    dataset_uid: str,
    member_uid: str | None = None,
    fit_index: int | None = None,
    fit_uid: str | None = None,
    event_bus: Any = None,
) -> ServiceResult:
    """Give a ``curve_input`` of the model's editor a dataset of the session (the IRF picker's pick).

    Parameters
    ----------
    state : SessionState
    curve : str
        The section's address (``key`` of the resolved section, e.g. ``convolve.irf``).
    dataset_uid : str
        The session dataset to attach (a copy is stored).
    member_uid : str, optional
        A member of that dataset group instead of the group's current one.
    fit_index, fit_uid : optional
        The fit.
    event_bus : object, optional
    """
    from chisurf.macros.model import CURVE_SELECT, attach_curve

    fit, _idx = _resolve_fit(state, fit_index, fit_uid)
    if fit is None:
        return service_error("fit not found", error_code=NOT_FOUND)
    model = getattr(fit, "model", None)
    section = declared_sections(model)[0].get(str(curve)) if model is not None else None
    if section is None:
        return service_error(
            f"the model's editor declares no curve input {curve!r}", error_code=INVALID_INPUT
        )
    if section.select_action not in CURVE_SELECT:
        return service_error(
            f"{section.select_action!r} attaches no curve", error_code=INVALID_STATE
        )
    picked = _session_curve(state, dataset_uid, member_uid)
    if picked is None:
        return service_error(f"dataset {dataset_uid!r} not found", error_code=NOT_FOUND)
    try:
        attach_curve(
            fit,
            section.select_action,
            picked,
            str(getattr(picked, "name", "") or ""),
            **dict(section.action_fixed or {}),
        )
        _publish(event_bus, fit, curve=str(curve))
        return {"ok": True, "curve": resolve_curve_input(section, fit.model)}
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


def model_curve_unload(
    state: SessionState,
    curve: str,
    fit_index: int | None = None,
    fit_uid: str | None = None,
    event_bus: Any = None,
) -> ServiceResult:
    """Unload the curve a ``curve_input`` holds (its ``unload_action``)."""
    from chisurf.macros.model import CURVE_UNLOAD, detach_curve

    fit, _idx = _resolve_fit(state, fit_index, fit_uid)
    if fit is None:
        return service_error("fit not found", error_code=NOT_FOUND)
    model = getattr(fit, "model", None)
    section = declared_sections(model)[0].get(str(curve)) if model is not None else None
    if section is None or not section.unload_action:
        return service_error(
            f"the model's editor declares no curve input {curve!r} to unload",
            error_code=INVALID_INPUT,
        )
    if section.unload_action not in CURVE_UNLOAD:
        return service_error(
            f"{section.unload_action!r} unloads no curve", error_code=INVALID_STATE
        )
    try:
        detach_curve(fit, section.unload_action, **dict(section.action_fixed or {}))
        _publish(event_bus, fit, curve=str(curve))
        return {"ok": True}
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


# ── custom sections: what each shows ─────────────────────────────────────────


def _scalar_table(model, section, fit, state) -> dict:
    owner = _model_svc()._resolve_target(model, section.target) if section.target else model
    rows = []
    for row in dict(section.options or {}).get("rows") or []:
        attr = str(row.get("attr", ""))
        rows.append(
            {
                "attr": attr,
                "label": str(row.get("label", attr)),
                "kind": str(row.get("kind", "float")),
                "decimals": int(row.get("decimals", 4)),
                "description": str(row.get("description", "") or ""),
                "value": _plain(_read(owner, attr)),
            }
        )
    return {"rows": rows}


def _rate_binding(model, section):
    from chisurf.core.dataspec.rate_binding import RateMatrixBinding

    options = dict(section.options or {})
    return RateMatrixBinding(
        model,
        str(section.target or options.get("attr", "")),
        size_attr=options.get("size_attr", ""),
    )


def _rate_matrix(model, section, fit, state) -> dict:
    options = dict(section.options or {})
    binding = _rate_binding(model, section)
    n = binding.size()
    values = binding.values()
    labels = _read(model, str(options.get("labels_attr", "")))
    # A state's short name, as the Qt grid shows it ("S1 (excited)" -> "S1"); S0, S1, ... without one.
    labels = (
        [str(labels[i]).split(" ")[0].split("(")[0].strip() for i in range(n)]
        if isinstance(labels, (list, tuple)) and len(labels) >= n
        else [f"S{i}" for i in range(n)]
    )
    uid = str(getattr(fit, "unique_identifier", "") or "")
    cells = {}
    for i in range(n):
        for j in range(n):
            parameter = binding.parameter(i, j)
            if parameter is not None:
                cells[f"{i},{j}"] = _model_svc()._parameter_row(parameter, uid)
    unit = _read(model, str(options.get("unit_attr", ""))) or options.get("unit", "")
    return {
        "n": n,
        "labels": labels,
        "values": _plain(values),
        "cells": cells,
        "unit": str(unit or ""),
    }


def _orientation(model, section, fit, state) -> dict:
    from chisurf.core.models.tcspc import kappa2_controls as k2

    has = getattr(model, "orientation_parameter", None) is not None
    return {
        "available": has,
        "mode": k2.orientation_mode(model),
        "kappa2": k2.scalar_kappa2(model),
        "can_set_r0": getattr(getattr(model, "fret_parameters", None), "_forster_radius", None)
        is not None,
    }


def _anisotropy_diagnostics(model, section, fit, state) -> dict:
    group = _model_svc()._resolve_target(model, section.target or "anisotropy")
    uid = str(getattr(fit, "unique_identifier", "") or "")
    outputs = [getattr(group, attr, None) for attr in ("_vv_bg_int", "_vh_bg_int")]
    return {
        "outputs": _rows([p for p in outputs if p is not None], uid),
        "has_rt": callable(getattr(group, "_extract_vv_vh_raw_for_diag", None)),
    }


def _lcurve_data(model, section):
    target = str(section.target or "")
    return _read(model, target)


def _lcurve(model, section, fit, state) -> dict:
    data = _lcurve_data(model, section)
    out: dict[str, Any] = {
        "reg": [],
        "residual_norm": [],
        "solution_norm": [],
        "corner_index": None,
    }
    if data is not None and getattr(data, "reg", None) is not None and len(data.reg):
        out.update(
            reg=_plain(np.asarray(data.reg, dtype=float)),
            residual_norm=_plain(np.asarray(data.residual_norm, dtype=float)),
            solution_norm=_plain(np.asarray(data.solution_norm, dtype=float)),
            corner_index=None if data.corner_index is None else int(data.corner_index),
        )
    return out


def _path_list(model, section, fit, state) -> dict:
    paths = _read(model, str(section.target or "")) or []
    return {"paths": [str(p) for p in paths]}


def _background_run(model, section, fit, state) -> dict:
    options = dict(section.options or {})
    progress = _read(model, str(options.get("progress_attr", "")))
    try:
        progress = float(progress)
        progress = progress / 100.0 if progress > 1.0 else progress
    except (TypeError, ValueError):
        progress = None
    return {
        "running": bool(_read(model, str(options.get("running_attr", "")), False)),
        "progress": progress,
        "status": str(_read(model, str(options.get("status_attr", "")), "") or ""),
    }


def _fit_mixer(model, section, fit, state) -> dict:
    uid = str(getattr(fit, "unique_identifier", "") or "")
    candidates = [
        {"uid": str(getattr(f, "unique_identifier", "") or ""), "name": str(getattr(f, "name", ""))}
        for f in (_read(model, "lifetime_fits", []) or [])
    ]
    try:
        fractions = list(getattr(model, "_fractions", []) or [])
    except Exception:  # noqa: BLE001 - a mixture whose sources cannot be combined has no fractions
        fractions = []
    return {
        "candidates": candidates,
        "components": [str(n) for n in (_read(model, "model_names", []) or [])],
        "fractions": _rows(fractions, uid),
    }


def _session_rows(state: SessionState) -> list:
    from chisurf.core.fitting.parameter_network import parameter_rows, session_owners
    from chisurf.core.registry.parameter_groups import iter_registered_parameter_groups

    return parameter_rows(session_owners(list(state.fits), iter_registered_parameter_groups()))


def _global_parameter_table(model, section, fit, state) -> dict:
    rows = _session_rows(state)
    position = {row.param_uid: i + 1 for i, row in enumerate(rows)}
    out = []
    for i, row in enumerate(rows):
        p = row.param
        link = getattr(p, "link", None)
        link_uid = str(getattr(link, "unique_identifier", "") or "") if link is not None else ""
        entry = _model_svc()._parameter_row(p, row.fit_uid or row.owner_uid)
        entry.update(
            row=i + 1,
            owner=str(row.owner_label),
            local=str(row.local_label or ""),
            owner_uid=str(row.owner_uid or ""),
            fit_uid=str(row.fit_uid or ""),
            link_row=position.get(link_uid),
        )
        out.append(entry)
    return {"rows": out}


def _lifetime_groups(state: SessionState):
    """``(fit, member, attr, group)`` for every lifetime group of the session's fits."""
    for fit in list(state.fits):
        members = list(getattr(fit, "grouped_fits", None) or [fit])
        for member in members:
            model = getattr(member, "model", None)
            for attr in ("lifetimes", "fa", "fb"):
                try:
                    group = getattr(model, attr)
                except Exception:  # noqa: BLE001
                    continue
                if hasattr(group, "_amplitudes") and hasattr(group, "_lifetimes"):
                    yield fit, member, attr, group


def _lifetime_amplitude_options(model, section, fit, state) -> dict:
    group = _model_svc()._resolve_target(model, section.target)
    targets = []
    for other_fit, member, attr, other in _lifetime_groups(state):
        if other is group:
            continue
        targets.append(
            {
                "fit_uid": str(getattr(other_fit, "unique_identifier", "") or ""),
                "member": str(getattr(member, "unique_identifier", "") or ""),
                "group": attr,
                "label": f"{getattr(other_fit, 'name', '')}: {getattr(other, 'name', attr)}",
            }
        )
    return {
        "absolute": bool(getattr(group, "absolute_amplitudes", True)),
        "normalize": bool(getattr(group, "normalize_amplitudes", True)),
        "targets": targets,
    }


_RESOLVERS: dict[str, Callable[..., dict]] = {
    "scalar_table": _scalar_table,
    "rate_matrix": _rate_matrix,
    "kappa2_controls": _orientation,
    "anisotropy_diagnostics": _anisotropy_diagnostics,
    "lcurve": _lcurve,
    "path_list": _path_list,
    "background_run": _background_run,
    "fit_mixer": _fit_mixer,
    "global_parameter_table": _global_parameter_table,
    "lifetime_amplitude_options": _lifetime_amplitude_options,
}


def resolve_custom(
    section: Any, model: Any, fit: Any, state: SessionState | None
) -> dict[str, Any]:
    """A ``custom`` section as data: its key, address, options and what its resolver reads now.

    A key without a resolver is ``type: "unsupported"``, as before.
    """
    key = str(getattr(section, "key", "") or "")
    resolver = _RESOLVERS.get(key)
    out: dict[str, Any] = {
        "key": key,
        "id": section_id(key, getattr(section, "target", None)),
        "target": str(getattr(section, "target", "") or ""),
        "options": _options(section),
    }
    if resolver is None:
        out.update(type="unsupported", kind=key)
        return out
    try:
        data = resolver(model, section, fit, state if state is not None else SessionState())
        out.update(type="custom", data=_plain(data))
    except Exception as e:  # noqa: BLE001 - the section says why instead of the editor failing
        out.update(type="custom", data={}, error=str(e))
    return out


# ── custom sections: what each may do ────────────────────────────────────────


class _Refused(ValueError):
    """An operation the section does not declare, or arguments it does not take."""


def _set_scalar(model, section, fit, state, attr: str, value: Any) -> dict:
    rows = {
        str(r.get("attr", "")): dict(r) for r in (dict(section.options or {}).get("rows") or [])
    }
    if str(attr) not in rows:
        raise _Refused(f"the table has no row {attr!r}")
    kind = str(rows[str(attr)].get("kind", "float"))
    owner = _model_svc()._resolve_target(model, section.target) if section.target else model
    if kind == "bool":
        typed: Any = bool(value)
    elif kind == "int":
        typed = int(float(value))
    else:
        typed = float(value)
        if not math.isfinite(typed):
            raise _Refused("a value must be finite")
    setattr(owner, str(attr), typed)
    call = str(dict(section.options or {}).get("call", "") or "")
    fn = getattr(model, call, None) if call else None
    if callable(fn):
        fn()
    return {}


def _set_rate(model, section, fit, state, source: int, target: int, value: float) -> dict:
    options = dict(section.options or {})
    value = float(value)
    if not options.get("diagonal", False) and int(source) == int(target):
        raise _Refused("the diagonal of this rate matrix is not a rate")
    lo, hi = float(options.get("minimum", 0.0)), float(options.get("maximum", 1_000_000.0))
    if not lo <= value <= hi:
        raise _Refused(f"a rate here lies in [{lo:g}, {hi:g}]")
    _rate_binding(model, section).commit_cell(int(source), int(target), value)
    return {}


def _set_mode(model, section, fit, state, mode: str) -> dict:
    from chisurf.core.models.tcspc.kappa2_controls import set_orientation_mode

    set_orientation_mode(model, mode)
    return {}


def _kappa2_distribution(model, section, fit, state, use_fast: bool = True) -> dict:
    from chisurf.core.models.tcspc.kappa2_controls import kappa2_distribution

    return kappa2_distribution(model, use_fast=bool(use_fast))


def _apply_kappa2(model, section, fit, state, k2, p_k2, k2_mean=None) -> dict:
    from chisurf.core.models.tcspc.kappa2_controls import apply_kappa2_distribution

    return {"kappa2": apply_kappa2_distribution(model, k2, p_k2, k2_mean)}


def _set_r0(model, section, fit, state, r0: float) -> dict:
    from chisurf.core.models.tcspc.kappa2_controls import set_forster_radius

    set_forster_radius(model, r0)
    return {}


def _rt(model, section, fit, state, factors: dict | None = None) -> dict:
    group = _model_svc()._resolve_target(model, section.target or "anisotropy")
    decays = getattr(group, "rt_decays", None)
    if not callable(decays):
        raise _Refused("this model's anisotropy offers no VV/VH diagnostics")
    return decays(dict(factors or {}))


def _lcurve_compute(
    model, section, fit, state, n_points: int, log10_min: float, log10_max: float
) -> dict:
    action = str(dict(section.options or {}).get("compute_action", "") or "")
    fn = getattr(model, action, None) if action else None
    if not callable(fn):
        raise _Refused("this L-curve cannot be sampled")
    n_points = int(n_points)
    if not 2 <= n_points <= 256:
        raise _Refused("an L-curve takes 2 to 256 points")
    lo, hi = sorted((float(log10_min), float(log10_max)))
    fn(n_points=n_points, log10_min=lo, log10_max=hi)
    return {}


def _lcurve_select(model, section, fit, state, index: int) -> dict:
    action = str(dict(section.options or {}).get("select_action", "") or "")
    fn = getattr(model, action, None) if action else None
    if not callable(fn):
        raise _Refused("no weight can be picked on this L-curve")
    data = _lcurve_data(model, section)
    count = len(getattr(data, "reg", ()) or ()) if data is not None else 0
    if not 0 <= int(index) < count:
        raise _Refused(f"the L-curve has no point {index}")
    fn(int(index))
    return {}


def _expand(paths: list[str], extensions: list[str], folders: bool) -> list[str]:
    allowed = {str(e).lower() for e in extensions}
    found: list[str] = []
    for raw in paths:
        path = pathlib.Path(str(raw)).expanduser()
        if path.is_dir():
            if not folders:
                continue
            found += [
                str(p)
                for p in sorted(path.rglob("*"))
                if p.is_file() and (not allowed or p.suffix.lower() in allowed)
            ]
        elif path.is_file() and (not allowed or path.suffix.lower() in allowed):
            found.append(str(path))
    return found


def _write_paths(model, section, paths: list[str]) -> None:
    setattr(model, str(section.target), list(paths))
    update = getattr(model, "update", None)
    if callable(update):
        update()


def _paths_add(model, section, fit, state, paths: list) -> dict:
    options = dict(section.options or {})
    if not isinstance(paths, (list, tuple)):
        raise _Refused("paths is a list of file names")
    new = _expand(
        list(paths), list(options.get("extensions") or []), bool(options.get("add_folders", True))
    )
    current = [str(p) for p in (_read(model, str(section.target)) or [])]
    _write_paths(model, section, current + [p for p in new if p not in current])
    return {"added": len([p for p in new if p not in current])}


def _paths_remove(model, section, fit, state, index: int) -> dict:
    current = [str(p) for p in (_read(model, str(section.target)) or [])]
    if not 0 <= int(index) < len(current):
        raise _Refused(f"the list has no entry {index}")
    del current[int(index)]
    _write_paths(model, section, current)
    return {}


def _paths_clear(model, section, fit, state) -> dict:
    _write_paths(model, section, [])
    return {}


def _run(model, section, fit, state, which: str) -> dict:
    options = dict(section.options or {})
    action = str(options.get(f"{which}_action", "") or "")
    fn = getattr(model, action, None) if action else None
    if not callable(fn):
        raise _Refused(f"this section has no {which} action")
    fn()
    return {}


def _mixer_add(model, section, fit, state, fit_uids: list, name: str = "") -> dict:
    by_uid = {
        str(getattr(f, "unique_identifier", "") or ""): f
        for f in (_read(model, "lifetime_fits", []) or [])
    }
    picked = [by_uid.get(str(u)) for u in (fit_uids or [])]
    if not picked or any(f is None for f in picked):
        raise _Refused("pick fits the mixture lists")
    added = 0
    for f in picked:
        count = len(_read(model, "model_names", []) or [])
        model.append_model(f.model, str(name).strip() or f"x_{count + 1}")
        added += 1
    return {"added": added}


def _mixer_remove(model, section, fit, state, index: int) -> dict:
    count = len(_read(model, "model_names", []) or [])
    if not 0 <= int(index) < count:
        raise _Refused(f"the mixture has no component {index}")
    model.pop_model(int(index))
    return {}


def _group_target(state, fit_uid: str, member: str, attr: str):
    for other_fit, other_member, other_attr, group in _lifetime_groups(state):
        if (
            str(getattr(other_fit, "unique_identifier", "")) == str(fit_uid)
            and str(getattr(other_member, "unique_identifier", "")) == str(member)
            and other_attr == str(attr)
        ):
            return group
    raise _Refused("that lifetime group is not in the session")


def _amplitude_options(model, section, fit, state, absolute=None, normalize=None) -> dict:
    group = _model_svc()._resolve_target(model, section.target)
    if absolute is not None:
        group.absolute_amplitudes = bool(absolute)
    if normalize is not None:
        group.normalize_amplitudes = bool(normalize)
    return {}


def _read_group(model, section, fit, state, fit_uid: str, member: str, group: str) -> dict:
    from chisurf.core.api.live_edit import edit_parameter

    mine = _model_svc()._resolve_target(model, section.target)
    theirs = _group_target(state, fit_uid, member, group)
    for p, q in zip(mine.parameters_all, theirs.parameters_all):
        edit_parameter(p, value=float(q.value))
    return {}


def _link_group(model, section, fit, state, fit_uid: str, member: str, group: str) -> dict:
    mine = _model_svc()._resolve_target(model, section.target)
    mine.link = _group_target(state, fit_uid, member, group)
    return {}


#: What each custom section may do, by key then operation. Each takes ``(model, section, fit,
#: state, **args)`` and refuses (:class:`_Refused`) whatever its section does not declare.
_OPERATIONS: dict[str, dict[str, Callable[..., dict]]] = {
    "scalar_table": {"set": _set_scalar},
    "rate_matrix": {"set_cell": _set_rate},
    "kappa2_controls": {
        "set_mode": _set_mode,
        "distribution": _kappa2_distribution,
        "apply_distribution": _apply_kappa2,
        "set_forster_radius": _set_r0,
    },
    "anisotropy_diagnostics": {"rt": _rt},
    "lcurve": {"compute": _lcurve_compute, "select": _lcurve_select},
    "path_list": {"add": _paths_add, "remove": _paths_remove, "clear": _paths_clear},
    "background_run": {
        "start": lambda m, s, f, st: _run(m, s, f, st, "start"),
        "stop": lambda m, s, f, st: _run(m, s, f, st, "stop"),
    },
    "fit_mixer": {"add": _mixer_add, "remove": _mixer_remove},
    "lifetime_amplitude_options": {
        "set": _amplitude_options,
        "read": _read_group,
        "link": _link_group,
    },
}
#: Operations that only read: no update, no event.
_READ_ONLY = {("kappa2_controls", "distribution"), ("anisotropy_diagnostics", "rt")}


def model_section_call(
    state: SessionState,
    section: str,
    op: str,
    args: dict | None = None,
    fit_index: int | None = None,
    fit_uid: str | None = None,
    event_bus: Any = None,
) -> ServiceResult:
    """Run operation *op* of the custom section *section* of the model's editor.

    Parameters
    ----------
    state : SessionState
    section : str
        The section's address (``key:target``, the ``id`` of the resolved section).
    op : str
        One of the operations its key offers (``set``, ``set_cell``, ``compute``, …).
    args : dict, optional
        The operation's arguments, checked against what the section declares.
    fit_index, fit_uid : optional
        The fit.
    event_bus : object, optional

    Returns
    -------
    dict
        ``{"ok": True, "result": {...}}``; a read-only operation's ``result`` is its data.
    """
    fit, _idx = _resolve_fit(state, fit_index, fit_uid)
    if fit is None:
        return service_error("fit not found", error_code=NOT_FOUND)
    model = getattr(fit, "model", None)
    declared = declared_sections(model)[1].get(str(section)) if model is not None else None
    if declared is None:
        return service_error(
            f"the model's editor declares no section {section!r}", error_code=INVALID_INPUT
        )
    operation = _OPERATIONS.get(str(declared.key), {}).get(str(op))
    if operation is None:
        return service_error(
            f"section {section!r} has no operation {op!r}", error_code=INVALID_INPUT
        )
    try:
        result = operation(model, declared, fit, state, **dict(args or {}))
    except (_Refused, TypeError) as e:
        return service_error(str(e), error_code=INVALID_INPUT, exception=e)
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)
    if (str(declared.key), str(op)) not in _READ_ONLY:
        if callable(getattr(model, "find_parameters", None)):
            model.find_parameters()
        _publish(event_bus, fit, section=str(section), op=str(op))
    return {"ok": True, "result": _plain(result)}


__all__ = [
    "CUSTOM_KEYS",
    "curve_id",
    "declared_sections",
    "model_curve_set",
    "model_curve_unload",
    "model_section_call",
    "resolve_curve_input",
    "resolve_custom",
    "section_id",
]
