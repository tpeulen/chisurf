"""Server-side RPC services for model operations (components, state, editor).

These services allow GUI widgets to add/remove model components and
get/set model-specific state without accessing live model objects
directly.

``model.editor`` hands a client the model's own editor -- its ``view.json``
sections resolved against the live model into plain data (choices with their
current value, parameter tables as rows, the equation text, component lists).
The client draws that and writes back through ``model.state.set``,
``model.component.add/remove`` and the ``parameter.*`` calls. The spec is also
the allow-list of those writes: a bound control the model's ``view.json``
declares may be set, a component group it declares may grow or shrink, and
nothing else.
"""

from __future__ import annotations

from typing import Any

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


def model_component_add(
    state: SessionState,
    component_type: str = "",
    fit_index: int | None = None,
    fit_uid: str | None = None,
    event_bus: Any = None,
    target: str | None = None,
    **kwargs: Any,
) -> ServiceResult:
    """Add a component to a fit's model.

    Parameters
    ----------
    state : SessionState
    component_type : str
        The type/name of the component to add (model-family-specific).
    fit_index : int, optional
    fit_uid : str, optional
    event_bus : object, optional
    target : str, optional
        The ``target`` of a ``dynamic_group`` the model's ``view.json``
        declares; its ``append_method`` is called. Takes precedence over
        *component_type*.
    **kwargs
        Additional arguments forwarded to the component constructor.

    Notes
    -----
    This is a generic endpoint that dispatches to model-family-specific
    add methods.  Model widgets should call this instead of
    ``model.add_lifetime()``, ``model.add_species()``, etc.
    """
    fit, idx = _resolve_fit(state, fit_index, fit_uid)
    if fit is None:
        return service_error("fit not found", error_code=NOT_FOUND)
    model = getattr(fit, "model", None)
    if model is None:
        return service_error("fit has no model", error_code=INVALID_STATE)
    if target:
        return _group_add(fit, model, str(target), event_bus)
    if not component_type:
        return service_error("a component type or a target is required", error_code=INVALID_INPUT)
    try:
        # Mirror the local action handler (model_macros.add_component):
        # 1. Try model.add_{type}() — e.g. add_rotation on AnisotropyModel
        # 2. Try model.{type}.append() — e.g. model.lifetimes.append()
        # 3. Try model.add_component() fallback
        added = False
        method_name = f"add_{component_type}"
        add_method = getattr(model, method_name, None)
        if callable(add_method):
            add_method(**kwargs)
            added = True
        if not added:
            target = getattr(model, component_type, None)
            if target is not None:
                append = getattr(target, "append", None)
                if callable(append):
                    try:
                        append(**kwargs)
                    except TypeError:
                        append()
                    added = True
        if not added:
            add_generic = getattr(model, "add_component", None)
            if callable(add_generic):
                add_generic(component_type, **kwargs)
                added = True
        if not added:
            return service_error(
                f"model has no method to add component '{component_type}'",
                error_code=OPERATION_FAILED,
            )
        # Re-discover parameters so newly added components appear in
        # parameters_all_dict (needed by parameter.set_value, etc.)
        if callable(getattr(model, "find_parameters", None)):
            model.find_parameters()
        if event_bus is not None:
            event_bus.publish(
                "model.component.added",
                {
                    "fit_uid": str(getattr(fit, "unique_identifier", "") or ""),
                    "component_type": component_type,
                },
            )
        return {"ok": True}
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


def model_component_remove(
    state: SessionState,
    component_index: int = -1,
    fit_index: int | None = None,
    fit_uid: str | None = None,
    event_bus: Any = None,
    target: str | None = None,
) -> ServiceResult:
    """Remove a component from a fit's model by index.

    Parameters
    ----------
    state : SessionState
    component_index : int
        Index of the component to remove (``-1``: the last one).
    fit_index : int, optional
    fit_uid : str, optional
    event_bus : object, optional
    target : str, optional
        The ``target`` of a ``dynamic_group`` the model's ``view.json``
        declares; its ``remove_method`` is called, never below ``min_rows``.
    """
    fit, idx = _resolve_fit(state, fit_index, fit_uid)
    if fit is None:
        return service_error("fit not found", error_code=NOT_FOUND)
    model = getattr(fit, "model", None)
    if model is None:
        return service_error("fit has no model", error_code=INVALID_STATE)
    if target:
        return _group_remove(fit, model, str(target), int(component_index), event_bus)
    try:
        # Mirror the local action handler (model_macros.remove_component):
        # 1. Try model.remove_component(index)
        # 2. Try model.{type}.pop() — e.g. model.lifetimes.pop()
        removed = False
        remove_method = getattr(model, "remove_component", None)
        if callable(remove_method):
            remove_method(component_index)
            removed = True
        if not removed:
            # Try sub-component pop — the action handler removes the last component
            for candidate in ("lifetimes", "species", "rotations", "distances", "gaussians"):
                target = getattr(model, candidate, None)
                if target is None:
                    continue
                pop = getattr(target, "pop", None)
                if callable(pop):
                    try:
                        pop()
                    except Exception:
                        continue
                    removed = True
                    break
        if not removed:
            return service_error(
                f"model has no method to remove component at index {component_index}",
                error_code=OPERATION_FAILED,
            )
        # Re-discover parameters so removed components disappear from
        # parameters_all_dict
        if callable(getattr(model, "find_parameters", None)):
            model.find_parameters()
        if event_bus is not None:
            event_bus.publish(
                "model.component.removed",
                {
                    "fit_uid": str(getattr(fit, "unique_identifier", "") or ""),
                    "component_index": component_index,
                },
            )
        return {"ok": True}
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


def model_state_get(
    state: SessionState,
    fit_index: int | None = None,
    fit_uid: str | None = None,
) -> ServiceResult:
    """Get JSON-safe model-specific state.

    Returns model attributes like convolve settings, IRF parameters,
    background parameters, etc.

    Parameters
    ----------
    state : SessionState
    fit_index : int, optional
    fit_uid : str, optional
    """
    fit, idx = _resolve_fit(state, fit_index, fit_uid)
    if fit is None:
        return service_error("fit not found", error_code=NOT_FOUND)
    model = getattr(fit, "model", None)
    if model is None:
        return service_error("fit has no model", error_code=INVALID_STATE)
    try:
        state_dict: dict[str, Any] = {}
        # Collect common state attributes
        for attr in (
            "convolve",
            "irf_range",
            "background",
            "scatter",
            "shift",
            "pulsed_excitation",
            "parse_function",
            "name",
            "n_components",
            "n_lifetimes",
            "n_rotations",
            "n_species",
            "n_distances",
            "n_gaussians",
            "use_convolve",
            "use_irf",
            "use_background",
            "use_scatter",
            "use_shift",
        ):
            val = getattr(model, attr, None)
            if val is not None:
                try:
                    # Convert numpy types to JSON-safe
                    if hasattr(val, "item"):
                        val = val.item()
                    state_dict[attr] = val
                except Exception:
                    pass
        # What the model's own editor binds (``view.json`` choice/toggle/value).
        for key in _declared_controls(model):
            found, value = _read_path(model, key)
            if found:
                state_dict[key] = _json_value(value)
        return {"ok": True, "state": state_dict}
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


# Allowlist of model attributes that can be set via RPC.
# Prevents arbitrary setattr from clients and guards against
# unserializable values.
_MODEL_STATE_SET_ALLOWLIST = frozenset(
    {
        "background",
        "convolve",
        "irf_range",
        "name",
        "parse_function",
        "pulsed_excitation",
        "scatter",
        "shift",
        "use_background",
        "use_convolve",
        "use_irf",
        "use_scatter",
        "use_shift",
    }
)


def model_state_set(
    state: SessionState,
    state_data: dict[str, Any],
    fit_index: int | None = None,
    fit_uid: str | None = None,
    event_bus: Any = None,
) -> ServiceResult:
    """Set JSON-safe model-specific state.

    Only attributes in ``_MODEL_STATE_SET_ALLOWLIST`` and the controls the
    model's own ``view.json`` binds (``choice`` / ``toggle`` / ``value`` with an
    ``attr``; keyed ``target.attr`` when the section has a ``target``) can be
    set. A declared choice with fixed options only takes one of them, and its
    ``call`` runs with the new value, as the editor's control would. Other keys
    in *state_data* are silently ignored.

    Parameters
    ----------
    state : SessionState
    state_data : dict
        Dictionary of model attributes to set (must match allowlist).
    fit_index : int, optional
    fit_uid : str, optional
    event_bus : object, optional
    """
    fit, idx = _resolve_fit(state, fit_index, fit_uid)
    if fit is None:
        return service_error("fit not found", error_code=NOT_FOUND)
    model = getattr(fit, "model", None)
    if model is None:
        return service_error("fit has no model", error_code=INVALID_STATE)
    declared = _declared_controls(model)
    for key, value in state_data.items():
        section = declared.get(key)
        options = list(getattr(section, "options", ()) or ()) if section is not None else []
        if options and str(value) not in {str(o) for o in options}:
            return service_error(
                f"{key!r} takes one of {options}, not {value!r}", error_code=INVALID_INPUT
            )
    try:
        written = []
        for key, value in state_data.items():
            if key in declared:
                _write_control(model, declared[key], key, value)
                written.append(key)
            elif key in _MODEL_STATE_SET_ALLOWLIST:
                setattr(model, key, value)
                written.append(key)
        if event_bus is not None:
            event_bus.publish(
                "model.state.changed",
                {
                    "fit_uid": str(getattr(fit, "unique_identifier", "") or ""),
                    "keys": written,
                },
            )
        return {"ok": True, "keys": written}
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


# ── the model's own editor ───────────────────────────────────────────────────


def _model_view(model: Any) -> Any:
    """The model's parsed view spec, ``None`` for a model without one."""
    view_spec = getattr(model, "view_spec", None)
    if not callable(view_spec):
        return None
    try:
        return view_spec()
    except Exception:  # noqa: BLE001 - an unreadable spec is "no editor", reported by the caller
        import chisurf.logging

        chisurf.logging.exception("the view spec of %s could not be read", type(model).__name__)
        return None


def _resolve_target(model: Any, target: str | None) -> Any:
    """The object a section's ``target`` names: a dotted path from the model, the model if empty."""
    obj = model
    for part in str(target or "").split("."):
        if not part:
            continue
        obj = getattr(obj, part, None)
        if obj is None:
            return None
    return obj


def _read_path(model: Any, key: str) -> tuple[bool, Any]:
    """``(found, value)`` of a dotted ``target.attr`` key on *model*."""
    obj = model
    try:
        for part in key.split("."):
            obj = getattr(obj, part)
    except Exception:  # noqa: BLE001 - a property may raise; the key is then unreadable
        return False, None
    return True, obj


def _json_value(value: Any) -> Any:
    """*value* as JSON-safe data (numpy scalars unwrapped, anything else as text)."""
    if hasattr(value, "item") and not isinstance(value, (list, tuple, dict)):
        try:
            value = value.item()
        except Exception:  # noqa: BLE001
            pass
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_value(v) for v in value]
    return str(value)


def _control_key(section: Any) -> str:
    """The state key of a bound control: ``attr``, or ``target.attr`` for a targeted one."""
    attr = str(getattr(section, "attr", "") or "")
    target = str(getattr(section, "target", "") or "")
    return f"{target}.{attr}" if target and attr else attr


def _declared_controls(model: Any) -> dict[str, Any]:
    """The bound controls (choice, toggle, value) of the model's ``view.json``, by state key.

    A control that writes through an action (``set_action``) is not one: that
    path dispatches on the client's action registry, which a server does not
    have, so such a control is shown read only.
    """
    from chisurf.core import dataspec as vs

    spec = _model_view(model)
    if spec is None:
        return {}
    found: dict[str, Any] = {}
    for section in spec.flat_sections():
        if isinstance(section, vs.ToggleRowSection):
            # Each item of a toggle row is a toggle of its own (``target`` / ``attr``).
            for item in section.items:
                toggle = vs.ToggleSection(
                    target=item.get("target"), attr=item.get("attr"), label=item.get("label", "")
                )
                if toggle.attr:
                    found[_control_key(toggle)] = toggle
            continue
        if isinstance(section, vs.TableSection) and section.selected_attr:
            # A table's selection is written to its ``selected_attr`` (the row, as in Qt).
            found[str(section.selected_attr)] = section
            continue
        if not isinstance(section, (vs.ChoiceSection, vs.ToggleSection, vs.ValueSection)):
            continue
        if getattr(section, "set_action", "") or not getattr(section, "attr", None):
            continue
        if getattr(section, "read_only", False):
            continue
        found[_control_key(section)] = section
    return found


def _write_control(model: Any, section: Any, key: str, value: Any) -> None:
    """Set a declared control's attribute and run its ``call``, as the editor's control does."""
    owner_path, _, attr = key.rpartition(".")
    owner = _resolve_target(model, owner_path) if owner_path else model
    if owner is None:
        raise AttributeError(f"{owner_path!r} does not resolve on the model")
    kind = type(section).__name__
    if kind == "TableSection":
        value = dict(value) if isinstance(value, dict) else value
    elif kind == "ToggleSection":
        value = bool(value)
    elif kind == "ValueSection":
        number = getattr(section, "kind", "str")
        if number == "int":
            value = int(value)
        elif number == "float":
            value = float(value)
    setattr(owner, attr, value)
    call = str(getattr(section, "call", "") or "")
    if call:
        fn = getattr(model, call, None)
        if callable(fn):
            fn(value)


def _declared_actions(model: Any) -> set[str]:
    """The model methods the ``button_row`` sections of its ``view.json`` press."""
    from chisurf.core import dataspec as vs

    spec = _model_view(model)
    if spec is None:
        return set()
    return {
        str(button.get("action", ""))
        for section in spec.flat_sections()
        if isinstance(section, vs.ButtonRowSection)
        for button in section.buttons
        if button.get("action")
    }


def model_action(
    state: SessionState,
    action: str,
    fit_index: int | None = None,
    fit_uid: str | None = None,
    event_bus: Any = None,
) -> ServiceResult:
    """Press a button of the model's own editor: call the model method its ``view.json`` names.

    Only an ``action`` a ``button_row`` of the model's spec declares is called
    (the global fit's *Add*, *Remove*, *Clear*); anything else is refused.

    Parameters
    ----------
    state : SessionState
    action : str
        The button's ``action``: a method of the model taking no arguments.
    fit_index : int, optional
    fit_uid : str, optional
    event_bus : object, optional
    """
    fit, idx = _resolve_fit(state, fit_index, fit_uid)
    if fit is None:
        return service_error("fit not found", error_code=NOT_FOUND)
    model = getattr(fit, "model", None)
    if model is None:
        return service_error("fit has no model", error_code=INVALID_STATE)
    if str(action) not in _declared_actions(model):
        return service_error(
            f"the model's editor has no button {action!r}", error_code=INVALID_INPUT
        )
    method = getattr(model, str(action), None)
    if not callable(method):
        return service_error(f"the model has no method {action!r}", error_code=OPERATION_FAILED)
    try:
        method()
        if callable(getattr(model, "find_parameters", None)):
            model.find_parameters()
        if event_bus is not None:
            event_bus.publish(
                "model.state.changed",
                {"fit_uid": str(getattr(fit, "unique_identifier", "") or ""), "action": action},
            )
        return {"ok": True}
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


def _declared_groups(model: Any) -> dict[str, Any]:
    """The ``dynamic_group`` sections of the model's ``view.json``, by ``target``."""
    from chisurf.core import dataspec as vs

    spec = _model_view(model)
    if spec is None:
        return {}
    return {
        str(section.target or ""): section
        for section in spec.flat_sections()
        if isinstance(section, vs.DynamicGroupSection)
    }


def _group_rows(group: Any, section: Any) -> list:
    """The parameters a ``dynamic_group`` shows, in its order."""
    source = getattr(section, "rows_source", None)
    if source:
        fn = getattr(group, source, None)
        return list(fn()) if callable(fn) else []
    return list(getattr(group, "parameters_all", None) or [])


def _components_changed(fit: Any, model: Any, target: str, added: bool, event_bus: Any) -> None:
    """Re-discover the model's parameters and announce the grown or shrunk group."""
    if callable(getattr(model, "find_parameters", None)):
        model.find_parameters()
    if event_bus is None:
        return
    payload = {"fit_uid": str(getattr(fit, "unique_identifier", "") or ""), "target": target}
    if added:
        event_bus.publish("model.component.added", payload)
    else:
        event_bus.publish("model.component.removed", payload)


def _group_add(fit: Any, model: Any, target: str, event_bus: Any) -> ServiceResult:
    section = _declared_groups(model).get(target)
    if section is None:
        return service_error(
            f"the model's editor declares no component group {target!r}",
            error_code=INVALID_INPUT,
        )
    group = _resolve_target(model, target)
    add = getattr(group, section.append_method, None) if group is not None else None
    if not callable(add):
        return service_error(
            f"{target!r} has no method {section.append_method!r}", error_code=OPERATION_FAILED
        )
    try:
        add()
        _components_changed(fit, model, target, True, event_bus)
        return {"ok": True}
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


def _group_remove(
    fit: Any, model: Any, target: str, component_index: int, event_bus: Any
) -> ServiceResult:
    import inspect

    section = _declared_groups(model).get(target)
    if section is None:
        return service_error(
            f"the model's editor declares no component group {target!r}",
            error_code=INVALID_INPUT,
        )
    group = _resolve_target(model, target)
    remove = getattr(group, section.remove_method, None) if group is not None else None
    if not callable(remove):
        return service_error(
            f"{target!r} has no method {section.remove_method!r}", error_code=OPERATION_FAILED
        )
    count = len(_group_rows(group, section)) // max(1, int(section.row_width))
    if count <= int(section.min_rows):
        return service_error(
            f"{target!r} keeps at least {section.min_rows} component(s)",
            error_code=INVALID_STATE,
        )
    try:
        try:
            takes_index = bool(inspect.signature(remove).parameters)
        except (TypeError, ValueError):
            takes_index = False
        if takes_index and 0 <= component_index < count:
            remove(component_index)
        else:
            remove()
        _components_changed(fit, model, target, False, event_bus)
        return {"ok": True}
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


def _hidden(section: Any, model: Any) -> bool:
    """A section's ``visible`` / ``hidden_when``, evaluated on the live model."""
    if getattr(section, "visible", True) is False:
        return True
    cond = getattr(section, "hidden_when", None)
    if not cond:
        return False
    owner = _resolve_target(model, cond.get("target")) if cond.get("target") else model
    found, value = (
        _read_path(owner, str(cond.get("attr", "")))
        if owner is not None
        else (
            False,
            None,
        )
    )
    if not found:
        return False
    if "equals" in cond:
        return str(value).lower() == str(cond["equals"]).lower()
    if "not_equals" in cond:
        return str(value).lower() != str(cond["not_equals"]).lower()
    return False


def _parameter_row(parameter: Any, fit_uid: str) -> dict[str, Any]:
    """One editor row: the fit DTO's parameter entry plus its display label and bounds."""
    from chisurf.server.services._stats import _param_entry

    row = _param_entry(parameter, fit_uid)
    row["label"] = str(parameter.__dict__.get("label_text", row["name"]) or row["name"])
    bounds = row.get("bounds") or (None, None)
    row["lo"], row["hi"] = (_json_value(b) for b in (list(bounds) + [None, None])[:2])
    row["value"] = _json_value(row.get("value"))
    row["error_estimate"] = _json_value(row.get("error_estimate"))
    row["bounds"] = [row["lo"], row["hi"]]
    return row


def _table_parameters(group: Any, section: Any) -> list:
    """The parameters a ``parameter_group_table`` / ``parameter_group`` lists, as the Qt editor does."""
    source = getattr(section, "parameters_source", None)
    if source:
        produced = getattr(group, source, None)
        return list(produced() if callable(produced) else produced or [])
    exclude = getattr(section, "exclude_source", None)
    params = list(getattr(group, "parameters_all", None) or [])
    if exclude:
        try:
            excluded = {id(p) for p in getattr(group, exclude)()}
        except Exception:  # noqa: BLE001
            excluded = set()
        params = [p for p in params if id(p) not in excluded]
    return params


def _paired_layout(section: Any, group: Any) -> dict[str, Any]:
    """How a parameter table pairs its rows: ``row_width`` parameters a row, with slot and row captions."""
    width = max(1, int(getattr(section, "row_width", 1) or 1))
    if width == 1:
        return {"row_width": 1}
    labels = [str(x) for x in (getattr(section, "row_labels", ()) or ())]
    source = getattr(section, "row_labels_source", None)
    if not labels and source:
        produced = getattr(group, source, None)
        try:
            labels = [str(x) for x in (produced() if callable(produced) else produced or [])]
        except Exception:  # noqa: BLE001 - numbered rows instead
            labels = []
    return {
        "row_width": width,
        "columns": [str(c) for c in (getattr(section, "columns", ()) or ())],
        "slot_labels": [str(c) for c in (getattr(section, "slot_labels", ()) or ())],
        "row_labels": labels,
    }


#: Option lists a ``choice`` may name by ``options_source`` without its model providing them.
def _builtin_options(name: str) -> list | None:
    if name == "window_function_types":
        import chisurf.core.math.signal

        return list(chisurf.core.math.signal.window_function_types)
    return None


def _options(section: Any, owner: Any) -> list[list[Any]]:
    """A choice's ``[value, label]`` pairs: its own, or what ``options_source`` returns."""
    values = list(getattr(section, "options", ()) or ())
    labels = list(getattr(section, "labels", ()) or ())
    if not values and getattr(section, "options_source", None):
        found, produced = (
            _read_path(owner, str(section.options_source))
            if owner is not None
            else (
                False,
                None,
            )
        )
        if callable(produced):
            produced = produced()
        if not found or produced is None:
            produced = _builtin_options(str(section.options_source))
        pairs = []
        for item in list(produced or []):
            if isinstance(item, (list, tuple)) and len(item) == 2:
                pairs.append([_json_value(item[0]), str(item[1])])
            else:
                pairs.append([_json_value(item), str(item)])
        return pairs
    return [
        [_json_value(v), str(labels[i]) if i < len(labels) else str(v)]
        for i, v in enumerate(values)
    ]


def _resolve_section(
    section: Any,
    model: Any,
    fit_uid: str,
    declared: dict,
    fit: Any = None,
    state: SessionState | None = None,
) -> dict[str, Any]:
    """One ``view.json`` section as data the client can draw without the model.

    ``curve_input`` and ``custom`` sections are resolved by
    :mod:`chisurf.server.services.model_sections`; *fit* and *state* are what
    those read (a mixture's candidate fits, the session's parameters).
    """
    from chisurf.core import dataspec as vs
    from chisurf.server.services import model_sections

    out: dict[str, Any] = {
        "title": str(getattr(section, "title", "") or ""),
        "description": str(getattr(section, "description", "") or ""),
        "hidden": _hidden(section, model),
    }
    if isinstance(section, (vs.PanelSection, vs.DockAreaSection)):
        out.update(
            type="panel",
            collapsible=bool(getattr(section, "collapsible", True)),
            collapsed=bool(getattr(section, "collapsed", False)),
            n_col=int(getattr(section, "n_col", None) or 1),
            sections=[
                _resolve_section(child, model, fit_uid, declared, fit, state)
                for child in getattr(section, "sections", ())
            ],
        )
        return out
    if isinstance(section, (vs.ChoiceSection, vs.ToggleSection, vs.ValueSection)):
        key = _control_key(section)
        found, value = _read_path(model, key) if key else (False, None)
        owner = _resolve_target(model, getattr(section, "target", None))
        out.update(
            type={
                vs.ChoiceSection: "choice",
                vs.ToggleSection: "toggle",
                vs.ValueSection: "value",
            }[type(section)],
            key=key,
            label=str(getattr(section, "label", "") or ""),
            value=_json_value(value) if found else None,
            read_only=key not in declared,
        )
        if isinstance(section, vs.ChoiceSection):
            out.update(
                options=_options(section, owner),
                descriptions=[str(d) for d in (getattr(section, "descriptions", ()) or ())],
                style=str(section.style or "combo"),
            )
        if isinstance(section, vs.ValueSection):
            out.update(
                kind=str(section.kind or "str"),
                minimum=section.minimum,
                maximum=section.maximum,
                decimals=int(section.decimals),
                suffix=str(section.suffix or ""),
            )
        return out
    if isinstance(section, vs.InfoSection):
        text = section.text
        if section.source:
            produced = getattr(model, section.source, None)
            try:
                produced = produced() if callable(produced) else produced
            except Exception as e:  # noqa: BLE001 - shown in place of the text
                produced = f"({e})"
            text = "" if produced is None else str(produced)
        out.update(type="info", text=str(text or ""), is_markdown=bool(section.is_markdown))
        return out
    if isinstance(section, (vs.ParameterGroupTableSection, vs.ParameterGroupSection)):
        group = _resolve_target(model, section.target)
        params = _table_parameters(group, section) if group is not None else []
        out.update(
            type="parameters",
            key=str(section.target or ""),
            title=out["title"] or str(getattr(group, "name", "") or ""),
            collapsible=bool(getattr(section, "collapsible", True)),
            collapsed=bool(getattr(section, "collapsed", False)),
            rows=[_parameter_row(p, fit_uid) for p in params],
            **_paired_layout(section, group),
        )
        return out
    if isinstance(section, vs.DynamicGroupSection):
        group = _resolve_target(model, section.target)
        params = _group_rows(group, section) if group is not None else []
        width = max(1, int(section.row_width))
        out.update(
            type="components",
            key=str(section.target or ""),
            title=out["title"] or str(getattr(group, "name", "") or ""),
            collapsible=bool(getattr(section, "collapsible", True)),
            collapsed=bool(getattr(section, "collapsed", False)),
            rows=[_parameter_row(p, fit_uid) for p in params],
            row_width=width,
            count=len(params) // width,
            min_rows=int(section.min_rows),
            add_label=str(section.add_label),
            remove_label=str(section.remove_label),
            can_add=callable(getattr(group, section.append_method, None)),
            can_remove=callable(getattr(group, section.remove_method, None)),
            style=str(getattr(section, "style", "grid") or "grid"),
            columns=[str(c) for c in (getattr(section, "columns", ()) or ())],
            slot_labels=[str(c) for c in (getattr(section, "slot_labels", ()) or ())],
            header=[
                model_sections.resolve_custom(
                    vs.CustomSection(key=str(key), target=section.target), model, fit, state
                )
                for key in section.header_keys
            ],
        )
        return out
    if isinstance(section, vs.CurveInputSection):
        out.update(model_sections.resolve_curve_input(section, model))
        return out
    if isinstance(section, vs.CustomSection):
        out.update(model_sections.resolve_custom(section, model, fit, state))
        return out
    if isinstance(section, vs.ToggleRowSection):
        items = []
        for item in section.items:
            key = (
                f"{item['target']}.{item['attr']}"
                if item.get("target")
                else str(item.get("attr", ""))
            )
            found, value = _read_path(model, key) if key else (False, None)
            items.append(
                {
                    "key": key,
                    "label": str(item.get("label", "") or ""),
                    "description": str(item.get("description", "") or ""),
                    "value": bool(value) if found else False,
                    "read_only": key not in declared,
                }
            )
        out.update(type="toggle_row", items=items)
        return out
    if isinstance(section, vs.ButtonRowSection):
        out.update(
            type="buttons",
            buttons=[
                {
                    "label": str(b.get("label", b.get("action", ""))),
                    "action": str(b.get("action", "")),
                    "description": str(b.get("description", "") or ""),
                }
                for b in section.buttons
                if b.get("action")
            ],
        )
        return out
    if isinstance(section, vs.TableSection) and section.source:
        produced = getattr(model, section.source, None)
        try:
            produced = produced() if callable(produced) else produced
        except Exception as e:  # noqa: BLE001 - an empty table, said so
            import chisurf.logging

            chisurf.logging.warning("table source %s failed: %s", section.source, e)
            produced = []
        rows = [
            {str(k): _json_value(v) for k, v in dict(row).items()}
            for row in list(produced or [])
            if isinstance(row, dict)
        ]
        out.update(
            type="records",
            key=str(section.source),
            rows=rows,
            columns=[dict(c) for c in section.columns],
            selected_key=str(section.selected_attr or ""),
            height=int(section.height or 0),
        )
        return out
    kind = next((k for k, cls in vs._SECTION_TYPES.items() if type(section) is cls), "?")
    out.update(type="unsupported", kind=str(getattr(section, "key", "") or kind))
    return out


def model_editor(
    state: SessionState,
    fit_index: int | None = None,
    fit_uid: str | None = None,
) -> ServiceResult:
    """The fit's model editor: its ``view.json`` sections resolved against the live model.

    Parameters
    ----------
    state : SessionState
    fit_index : int, optional
    fit_uid : str, optional

    Returns
    -------
    dict
        ``{"ok": True, "editor": {"model", "sections", "state"}}``. Each
        section is plain data: ``panel`` (``sections``), ``choice`` / ``toggle``
        / ``value`` (``key``, ``value``, ``read_only``; a choice's
        ``options`` as ``[value, label]``), ``info`` (``text``), ``parameters``
        (``rows``, one per parameter with ``uid``, ``name``, ``label`` and its
        value, fixed, bounds and error), ``components`` (``rows``, ``count``,
        ``add_label`` / ``remove_label``) and ``unsupported`` (``kind``). Every
        section carries ``hidden`` (its ``hidden_when`` on the model now).
        ``editor`` is ``None`` for a model without a view spec.
    """
    fit, idx = _resolve_fit(state, fit_index, fit_uid)
    if fit is None:
        return service_error("fit not found", error_code=NOT_FOUND)
    model = getattr(fit, "model", None)
    if model is None:
        return service_error("fit has no model", error_code=INVALID_STATE)
    spec = _model_view(model)
    if spec is None:
        return {"ok": True, "editor": None}
    uid = str(getattr(fit, "unique_identifier", "") or "")
    try:
        declared = _declared_controls(model)
        sections = [_resolve_section(s, model, uid, declared, fit, state) for s in spec.sections]
        values = {}
        for key in declared:
            found, value = _read_path(model, key)
            if found:
                values[key] = _json_value(value)
        return {
            "ok": True,
            "editor": {
                "model": str(getattr(model, "name", "") or type(model).__name__),
                "sections": sections,
                "state": values,
            },
        }
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


def model_code_files(
    state: SessionState,
    fit_index: int | None = None,
    fit_uid: str | None = None,
) -> ServiceResult:
    """The source files of the fit's model the *Code* face may show and write.

    Returns ``source``, ``view_spec`` and ``files`` (see
    :func:`chisurf.core.models.source_files.model_source_files`).
    """
    fit, idx = _resolve_fit(state, fit_index, fit_uid)
    if fit is None:
        return service_error("fit not found", error_code=NOT_FOUND)
    from chisurf.core.models.source_files import model_source_files

    try:
        return {"ok": True, **model_source_files(getattr(fit, "model", None))}
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


def model_code_apply(
    state: SessionState,
    path: str,
    code: str,
    fit_index: int | None = None,
    fit_uid: str | None = None,
    event_bus: Any = None,
) -> ServiceResult:
    """Save an edit of one of the model's files and, for its module, apply it to the fit.

    Only a path :func:`model_code_files` lists is written.
    """
    fit, idx = _resolve_fit(state, fit_index, fit_uid)
    if fit is None:
        return service_error("fit not found", error_code=NOT_FOUND)
    from chisurf.core.models.source_files import apply_model_code

    try:
        result = apply_model_code(fit, str(path), str(code))
    except ValueError as e:
        return service_error(str(e), error_code=INVALID_INPUT, exception=e)
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)
    if event_bus is not None and result.get("applied"):
        event_bus.publish(
            "fit.updated",
            {"fit_index": idx, "fit_uid": str(getattr(fit, "unique_identifier", "") or "")},
        )
    return {"ok": True, **result}
