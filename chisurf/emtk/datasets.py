"""Qt-free dataset/fit registration shared with the legacy macro adapter."""

from __future__ import annotations

import typing
import json
import logging
import numpy as np

def _iter_group_members(group):
    if isinstance(group, (list, tuple)):
        yield from group
    else:
        yield group


def _coerce_finite_float(value: typing.Any) -> typing.Optional[float]:
    try:
        v = float(value)
    except Exception:
        return None
    if not np.isfinite(v):
        return None
    return v


def _resolve_dataset_anisotropy_calibration(data_group):
    calibration: typing.Dict[str, typing.Optional[float]] = {
        "g_factor": None,
        "l1": None,
        "l2": None,
    }

    reader = getattr(data_group, "data_reader", None)
    if reader is None:
        for member in _iter_group_members(data_group):
            reader = getattr(member, "data_reader", None)
            if reader is not None:
                break
    if reader is not None:
        for key in ("g_factor", "l1", "l2"):
            value = getattr(reader, key, None)
            if value is None:
                continue
            v = _coerce_finite_float(value)
            if v is not None:
                calibration[key] = v

    metas = []
    meta_data = getattr(data_group, "meta_data", None)
    if isinstance(meta_data, dict):
        metas.append(meta_data)
    for member in _iter_group_members(data_group):
        meta = getattr(member, "meta_data", None)
        if isinstance(meta, dict):
            metas.append(meta)
    for meta in metas:
        for key in ("g_factor", "l1", "l2"):
            if calibration.get(key) is not None:
                continue
            if key not in meta:
                continue
            v = _coerce_finite_float(meta[key])
            if v is not None:
                calibration[key] = v
    return calibration


def _resolve_dataset_g_factor(data_group):
    calibration = _resolve_dataset_anisotropy_calibration(data_group)
    return calibration.get("g_factor")


def _apply_g_factor_to_fit(fit_group, g_factor: float) -> None:
    _apply_anisotropy_calibration_to_fit(fit_group, {"g_factor": g_factor})


def _apply_anisotropy_calibration_to_fit(
    fit_group, calibration: typing.Dict[str, typing.Any]
) -> None:
    if not isinstance(calibration, dict):
        return

    resolved = {}
    for source_key in ("g_factor", "l1", "l2"):
        value = _coerce_finite_float(calibration.get(source_key))
        if value is None:
            continue
        resolved[source_key] = value
    if not resolved:
        return

    mapping = {
        "g_factor": ("_g", "g"),
        "l1": ("_l1", "l1"),
        "l2": ("_l2", "l2"),
    }

    def _set_anisotropy(anisotropy):
        if anisotropy is None:
            return
        params = getattr(anisotropy, "parameters_all_dict", None)
        for source_key, value in resolved.items():
            private_name, public_name = mapping[source_key]
            private_param = getattr(anisotropy, private_name, None)
            applied = False
            if private_param is not None and hasattr(private_param, "value"):
                private_param.value = value
                applied = True
            elif isinstance(private_param, (int, float, np.floating)):
                setattr(anisotropy, private_name, value)
                applied = True
            if (not applied) and isinstance(params, dict):
                param_entry = params.get(public_name)
                if param_entry is not None and hasattr(param_entry, "value"):
                    param_entry.value = value
                    applied = True
            if not applied:
                try:
                    setattr(anisotropy, public_name, value)
                except Exception:
                    pass

    _set_anisotropy(getattr(getattr(fit_group, "model", None), "anisotropy", None))
    for member in getattr(fit_group, "grouped_fits", []):
        _set_anisotropy(getattr(member.model, "anisotropy", None))


def _collect_group_nuisance_parameter_names(model: typing.Any) -> typing.Set[str]:
    names: typing.Set[str] = set()
    if model is None:
        return names
    # A model that knows which of its parameters are the instrument's says so
    # (a BFF-described view, by its description's groups).
    declared = getattr(model, "nuisance_parameter_names", None)
    if callable(declared):
        return set(declared())
    for attr_name, attr_value in getattr(model, "__dict__", {}).items():
        lname = str(attr_name).lower()
        is_nuisance_attr = (
            lname in {"nuisance", "nusiance", "generic", "corrections", "convolve"}
            or "nuisance" in lname
            or "nusiance" in lname
        )
        if not is_nuisance_attr:
            continue
        try:
            params = getattr(attr_value, "parameters_all", None)
            if isinstance(params, (list, tuple)):
                for p in params:
                    pname = str(getattr(p, "name", ""))
                    if pname:
                        names.add(pname)
                continue
            params_dict = getattr(attr_value, "parameters_all_dict", None)
            if isinstance(params_dict, dict):
                for pname in params_dict.keys():
                    if pname:
                        names.add(str(pname))
        except Exception:
            continue
    return names


def _auto_link_non_nuisance_group_parameters(fit_group) -> typing.Tuple[int, int]:
    grouped_fits = list(getattr(fit_group, "grouped_fits", []) or [])
    if len(grouped_fits) <= 1:
        return 0, 0

    master_fit = grouped_fits[0]
    master_model = getattr(master_fit, "model", None)
    master_params = getattr(master_model, "parameters_all_dict", None)
    if not isinstance(master_params, dict) or not master_params:
        return 0, 0

    nuisance_names = _collect_group_nuisance_parameter_names(master_model)
    linked_master_parameters = 0
    linked_followers = 0

    for parameter_name, master_parameter in master_params.items():
        if parameter_name in nuisance_names:
            continue
        if bool(getattr(master_parameter, "is_output", False)):
            continue
        if not hasattr(master_parameter, "link"):
            continue

        try:
            master_parameter.is_link_master = True
        except Exception:
            pass

        linked_this_parameter = False
        for local_fit in grouped_fits[1:]:
            try:
                local_params = getattr(
                    getattr(local_fit, "model", None), "parameters_all_dict", None
                )
                if not isinstance(local_params, dict):
                    continue
                follower_parameter = local_params.get(parameter_name)
                if follower_parameter is None:
                    continue
                try:
                    follower_parameter.is_link_master = False
                except Exception:
                    pass
                follower_parameter.link = master_parameter
                linked_followers += 1
                linked_this_parameter = True
            except Exception:
                continue

        if linked_this_parameter:
            linked_master_parameters += 1

    return linked_master_parameters, linked_followers



_BULK_PDA_KEYS = frozenset(
    {
        "s1s2",
        "ps",
        "row_indices",
        "col_indices",
        "tttr_indices",
    }
)


def _flatten_metadata(
    src: dict,
    *,
    skip_keys: typing.Collection[str] = (),
    prefix: str = "",
) -> typing.Dict[str, str]:
    """Flatten a nested metadata dict into ``{key: str(value)}`` pairs.

    Parameters
    ----------
    src : dict
        Source metadata dictionary.
    skip_keys : collection of str
        Top-level keys to skip entirely.
    prefix : str
        Optional prefix for output keys.
    """
    result: typing.Dict[str, str] = {}
    for k, v in src.items():
        if k in skip_keys:
            continue
        if v is None or v == "":
            continue
        pkey = f"{prefix}{k}"
        if isinstance(v, dict):
            result.update(_flatten_metadata(v, prefix=f"{pkey}."))
        elif isinstance(v, (list, tuple)):
            # Flatten short lists inline; skip large arrays
            if len(v) <= 12:
                result[pkey] = str(v)
        elif isinstance(v, float):
            result[pkey] = f"{v:.6e}"
        else:
            result[pkey] = str(v)
    return result


def _attach_tttr_header(fit_group, data_group):
    """Extract metadata from the first data curve onto the fit group.

    Parsed TTTR header tags and other reader-level metadata (PDA, etc.)
    are stored on ``fit_group.flr_metadata``, giving GUI components a
    unified view of reader-provided metadata without re-opening files.
    """
    try:
        d = data_group[0] if hasattr(data_group, "__getitem__") else data_group
        meta = getattr(d, "meta_data", None) or {}
    except Exception:
        return

    if not hasattr(fit_group, "flr_metadata") or fit_group.flr_metadata is None:
        fit_group.flr_metadata = {}

    entries: typing.Dict[str, str] = {}

    # 1) Parse TTTR header JSON tags
    hdr = meta.get("tttr_header_json")
    if hdr:
        try:
            raw = json.loads(hdr) if isinstance(hdr, str) else hdr
        except Exception:
            raw = None
        if raw:
            tags = raw.get("tags", [])
            for tag in tags:
                name = tag.get("name", "")
                value = tag.get("value", "")
                idx = tag.get("idx", 0)
                if value is None or value == "":
                    continue
                if isinstance(value, float):
                    value = f"{value:.6e}"
                key = name
                if idx and idx > 0:
                    key = f"{name}[{idx}]"
                if key not in entries:
                    entries[str(key)] = str(value)

    # 2) Surface non-bulk keys from meta_data
    entries.update(_flatten_metadata(meta, skip_keys={"tttr_header_json"}))

    # 3) Surface non-bulk keys from the pda dict
    pda = getattr(d, "pda", None) or {}
    entries.update(_flatten_metadata(pda, skip_keys=_BULK_PDA_KEYS, prefix="pda."))

    # Add entries to flr_metadata (user metadata takes precedence)
    for k, v in entries.items():
        if k not in fit_group.flr_metadata:
            fit_group.flr_metadata[k] = v

    # 4) Populate photon streams only for TTTR-originating data (indicated by a
    #    non-empty tttr_header_json in meta_data). Non-TTTR files (e.g. TCSPC CSV)
    #    set data.filename but should not appear in the photon-streams panel.
    if meta.get("tttr_header_json"):
        raw_filenames = meta.get("filenames")
        if not raw_filenames:
            try:
                raw_filenames = [
                    str(getattr(d, "filename", ""))
                    for d in (data_group if hasattr(data_group, "__getitem__") else [data_group])
                    if getattr(d, "filename", None)
                ]
            except Exception:
                raw_filenames = []
        if raw_filenames:
            streams = []
            for i, entry in enumerate(raw_filenames, 1):
                if isinstance(entry, dict):
                    streams.append(
                        {
                            "stream_id": f"stream_{i}",
                            "file_path": entry.get("path", ""),
                            "file_format": entry.get("format", ""),
                        }
                    )
                else:
                    streams.append(
                        {
                            "stream_id": f"stream_{i}",
                            "file_path": str(entry),
                            "file_format": "",
                        }
                    )
            fit_group.flr_photon_streams = streams


def _record_history(action_type, summary, payload=None, source_uid=""):
    from chisurf.core.actions._infra import record_action

    try:
        record_action(action_type=action_type, summary=summary, payload=payload, source_uid=source_uid)
    except Exception:
        logging.getLogger(__name__).exception("Could not record dataset/fit history")


def _publish(topic, payload):
    from chisurf.server.startup import get_shared_event_bus

    try:
        bus = get_shared_event_bus()
        if bus is not None:
            bus.publish(topic, payload)
    except Exception:
        logging.getLogger(__name__).exception("Could not publish %s", topic)


def register_dataset(dataset):
    """Register an already constructed dataset and publish its state change."""
    import chisurf as cs

    name = str(getattr(dataset, "name", "dataset"))
    uid = str(getattr(dataset, "unique_identifier", ""))
    cs.imported_datasets.append(dataset)
    index = len(cs.imported_datasets) - 1
    _record_history("dataset_add", f"add dataset(s): {name}", {
        "filename": getattr(dataset, "filename", None), "reader": None,
        "loaded_names": [name], "loaded_uids": [uid], "loaded_count": 1,
        "is_experiment_group": hasattr(dataset, "__iter__"),
    })
    _publish("dataset.added", {"dataset_index": index, "dataset_name": name})
    return index


def build_fit_group(dataset, model_class, model_kw=None):
    """Build a calibrated fit before making any session registry changes."""
    from chisurf.core.fitting.fit import FitGroup

    calibration = _resolve_dataset_anisotropy_calibration(dataset)
    model_kw = dict(model_kw or {})
    for key in ("g_factor", "l1", "l2"):
        value = _coerce_finite_float(calibration.get(key))
        if value is not None:
            model_kw.setdefault(key, value)
    group = FitGroup(data=dataset, model_class=model_class, model_kw=model_kw)
    _apply_anisotropy_calibration_to_fit(group, calibration)
    _attach_tttr_header(group, dataset)
    return group


def publish_fit_group(group, dataset, model_name):
    """Register a fully configured group with shared linking/history/events."""
    import chisurf as cs

    masters, followers = _auto_link_non_nuisance_group_parameters(group)
    cs.fits.append(group)
    name = str(getattr(group, "name", ""))
    uid = str(getattr(group, "unique_identifier", ""))
    _record_history("fit_add", f"add fit group '{name}' for dataset '{getattr(dataset, 'name', '')}' with model '{model_name}'", {
        "fit_group_name": name, "dataset_name": getattr(dataset, "name", ""),
        "model_name": model_name,
        "dataset_indices": [i for i, item in enumerate(cs.imported_datasets) if item is dataset],
    }, source_uid=uid)
    if followers:
        _record_history("fit_group_auto_link", f"auto-link non-nuisance parameters for fit group '{name}'", {
            "fit_group_name": name, "linked_master_parameters": masters,
            "linked_followers": followers, "policy": "non_nuisance_default_link",
        }, source_uid=uid)
    _publish("fit.added", {"fit_uid": uid, "fit_index": len(cs.fits) - 1, "fit_name": name})
    return group


def register_fit_group(dataset, model_class, model_kw=None):
    """Use the canonical fitting model, calibration and grouped-link policy."""
    group = build_fit_group(dataset, model_class, model_kw)
    return publish_fit_group(group, dataset, model_class.name)


def register_synthetic_fit(dataset, polarized=False):
    """Register synthetic curves and their lifetime fit without a GUI macro."""
    from chisurf.core.models.description import for_family

    model = for_family("tcspc_polarized" if polarized else "tcspc_lifetime")
    register_dataset(dataset)
    return register_fit_group(dataset, model)
