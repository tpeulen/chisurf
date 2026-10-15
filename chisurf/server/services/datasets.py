from __future__ import annotations

from typing import Any

from chisurf.server.services import (
    INVALID_INPUT,
    INVALID_STATE,
    NOT_FOUND,
    OPERATION_FAILED,
    ServiceResult,
    service_error,
)
from chisurf.server.session import SessionState


def _is_global_fit_dataset(dataset: Any) -> bool:
    """Return ``True`` if *dataset* is a global-fit placeholder.

    Parameters
    ----------
    dataset : object
        Dataset instance.

    """
    try:
        name = str(getattr(dataset, "name", "") or "").strip().lower()
    except Exception:
        name = ""
    return name in {"global-fit", "global dataset", "global-fit dataset"}


def _find_fits_using_dataset(dataset: Any, state: SessionState) -> list[Any]:
    """Return all fits whose data references *dataset*.

    Parameters
    ----------
    dataset : object
        Dataset instance.
    state : SessionState
        Server-side session state.

    """
    dataset_id = id(dataset)
    dependent = []
    for fit in state.fits:
        grouped = getattr(fit, "grouped_fits", None)
        if isinstance(grouped, (list, tuple)):
            for gf in grouped:
                if id(getattr(gf, "data", None)) == dataset_id:
                    dependent.append(fit)
                    break
        else:
            if id(getattr(fit, "data", None)) == dataset_id:
                dependent.append(fit)
    return dependent


def _dataset_members(dataset: Any) -> list[Any] | None:
    """Return direct members of a domain data group, excluding iterable curves."""
    from chisurf.core.data import DataGroup

    return list(dataset) if isinstance(dataset, DataGroup) else None


def _resolve_dataset_member(dataset: Any, member_uid: str | None = None) -> tuple[Any, int | None]:
    """Resolve an explicit child UID without changing the group's active member."""
    if member_uid is None:
        return dataset, None
    members = _dataset_members(dataset)
    if members is None:
        return None, None
    matches = [
        (member, index)
        for index, member in enumerate(members)
        if str(getattr(member, "unique_identifier", "")) == member_uid
    ]
    return matches[0] if len(matches) == 1 else (None, None)


def _dataset_dto(
    dataset: Any,
    index: int | None,
    *,
    include_length: bool = False,
    parent_uid: str | None = None,
    member_index: int | None = None,
) -> dict[str, Any]:
    """Build a serialisable summary dict for a dataset.

    Parameters
    ----------
    dataset : object
        Dataset instance.
    index : int or None
        Positional index.
    include_length : bool
        If ``True``, include the ``length`` field.
    parent_uid : str, optional
        Owning group UID for a direct member. ``index`` remains the outer index.
    member_index : int, optional
        Position within the owning group; never an index into the session.

    """
    members = _dataset_members(dataset)
    empty_group = members is not None and not members
    dto: dict[str, Any] = {
        "index": index,
        "uid": str(getattr(dataset, "unique_identifier", "") or ""),
        "name": str(getattr(dataset, "name", "") or ""),
        "type": type(dataset).__name__,
        "experiment": ""
        if empty_group
        else str(getattr(getattr(dataset, "experiment", None), "name", "") or ""),
        "filename": str(getattr(dataset, "filename", "") or ""),
    }
    if include_length:
        dto["length"] = (
            None
            if empty_group
            else (int(len(getattr(dataset, "y", []))) if hasattr(dataset, "y") else None)
        )
    if parent_uid is not None:
        dto.update(parent_uid=parent_uid, member_index=member_index)
    elif members is not None:
        dto["members"] = [
            _dataset_dto(
                member, index, include_length=True, parent_uid=dto["uid"], member_index=position
            )
            for position, member in enumerate(members)
        ]
    return dto


def _resolve_dataset(
    state: SessionState,
    dataset_index: int | None = None,
    dataset_uid: str | None = None,
) -> tuple[Any, int]:
    """Look up a dataset by index or uid.

    Returns ``(dataset, index)`` or ``(None, -1)``.

    Parameters
    ----------
    state : SessionState
        Server-side session state.
    dataset_index : int, optional
        Positional index.
    dataset_uid : str, optional
        Unique identifier.

    """
    datasets = list(state.datasets)
    if dataset_uid:
        for i, dataset in enumerate(datasets):
            if str(getattr(dataset, "unique_identifier", "")) == dataset_uid:
                return dataset, i
        return None, -1
    if dataset_index is not None and 0 <= dataset_index < len(datasets):
        return datasets[dataset_index], dataset_index
    return None, -1


def _validated_dataset_indices(
    datasets: list[Any],
    dataset_indices: Any,
    *,
    empty_message: str,
) -> tuple[list[int], ServiceResult | None]:
    """Validate and deduplicate a list of dataset indices.

    Returns ``(indices, None)`` on success or ``([], error)`` on failure.

    Parameters
    ----------
    datasets : list
        Current list of datasets.
    dataset_indices : iterable
        Raw indices to validate.
    empty_message : str
        Error message for an empty result.

    """
    if not hasattr(dataset_indices, "__iter__") or isinstance(dataset_indices, (str, bytes)):
        return [], service_error(
            "dataset_indices must be an iterable of ints", error_code=INVALID_INPUT
        )
    try:
        indices = sorted(set(int(i) for i in dataset_indices))
    except Exception as e:
        return [], service_error(str(e), error_code=INVALID_INPUT, exception=e)
    if not indices:
        return [], service_error(empty_message, error_code=INVALID_INPUT)
    for i in indices:
        if i < 0 or i >= len(datasets):
            return [], service_error(f"dataset index {i} out of range", error_code=INVALID_INPUT)
    return indices, None


def list_datasets(state: SessionState) -> ServiceResult:
    """Return a summary of all datasets in the session.

    Parameters
    ----------
    state : SessionState
        Server-side session state.

    """
    return {
        "ok": True,
        "datasets": [_dataset_dto(d, idx) for idx, d in enumerate(state.datasets)],
    }


def get_dataset_info(
    state: SessionState,
    dataset_index: int | None = None,
    dataset_uid: str | None = None,
    member_uid: str | None = None,
) -> ServiceResult:
    """Return detailed info for a single dataset.

    Parameters
    ----------
    state : SessionState
        Server-side session state.
    dataset_index : int, optional
        Positional index.
    dataset_uid : str, optional
        Unique identifier.
    member_uid : str, optional
        Explicit UID of one direct child within the selected dataset group.

    """
    parent, index = _resolve_dataset(state, dataset_index, dataset_uid)
    d, member_index = _resolve_dataset_member(parent, member_uid)
    if d is None:
        return service_error("dataset not found", error_code=NOT_FOUND)
    return {
        "ok": True,
        "dataset": _dataset_dto(
            d,
            index,
            include_length=True,
            parent_uid=str(getattr(parent, "unique_identifier", ""))
            if member_uid is not None
            else None,
            member_index=member_index,
        ),
    }


def _prepare_cached_dataset(payload: Any, _seen: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate a complete cached curve/group before constructing or appending objects."""
    import copy

    import numpy as np

    from chisurf.core.project.session import (
        _COMMON_READER_FIELDS,
        _READER_FIELDS,
        AUXILIARY_FIELDS,
        _restore_scientific_value,
        _scientific_value,
    )

    if not isinstance(payload, dict):
        raise ValueError("cached dataset must be an object")
    seen = {} if _seen is None else _seen
    kind = payload.get("kind", "legacy")
    uid = payload.get("uid")
    if uid:
        encoded = _scientific_value(payload)
        if uid in seen and seen[uid] != encoded:
            raise ValueError("cached identity has inconsistent records")
        seen[uid] = encoded
    if kind == "group":
        if payload.get("group_type") not in {
            "DataGroup",
            "DataCurveGroup",
            "ExperimentDataGroup",
            "ExperimentDataCurveGroup",
        }:
            raise ValueError("unsupported cached group type")
        members = payload.get("members")
        if not isinstance(members, list) or not members:
            raise ValueError("cached group has no members")
        prepared = [_prepare_cached_dataset(member, seen) for member in members]
        if any(member["kind"] not in {"curve", "structure"} for member in prepared):
            raise ValueError("cached groups contain curve or structure records only")
        uid = payload.get("uid")
        if not isinstance(uid, str) or not uid:
            raise ValueError("cached group UID is missing")
        identities = [uid, *(member["uid"] for member in prepared)]
        if len(set(identities)) != len(identities):
            raise ValueError("cached group identities are not unique")
        selected = payload.get("selected", 0)
        if type(selected) is not int or not 0 <= selected < len(prepared):
            raise ValueError("cached group selection is invalid")
        metadata = _restore_scientific_value(payload.get("metadata", {}))
        if not isinstance(metadata, dict):
            raise ValueError("cached group metadata must be an object")
        if "unique_identifier" in metadata and metadata["unique_identifier"] != uid:
            raise ValueError("cached group metadata contradicts its UID")
        _scientific_value(metadata)
        return {**payload, "members": prepared, "metadata": metadata}
    if kind not in {"curve", "structure", "legacy"}:
        raise ValueError("unsupported cached dataset kind")
    arrays = {}
    raw_arrays = payload.get("arrays", {}) if kind == "curve" else payload
    fields: tuple[str, ...] = (
        ("x", "y", "ex", "ey", "mask") if kind == "curve" else ("x", "y", "ex", "ey")
    )
    if kind == "structure":
        # Atoms, not arrays: the structural snapshot of the project codec.
        if payload.get("arrays") or not isinstance(payload.get("structure"), dict):
            raise ValueError("cached structure must carry its snapshot and no curve arrays")
        fields = ()
    for field in fields:
        if field not in raw_arrays:
            if kind == "curve" or field in {"x", "y"}:
                raise ValueError(f"cached curve is missing {field}")
            continue
        values = raw_arrays[field]
        if kind == "curve":
            if not isinstance(values, dict) or not isinstance(values.get("dtype"), str):
                raise ValueError("invalid cached array descriptor")
            array = np.asarray(values.get("values"), dtype=np.dtype(values["dtype"]))
        else:
            if values is None:
                continue
            array = np.asarray(values, dtype=float)
        allowed_kinds = "biuf" if field == "mask" else "iuf"
        # A saved curve snapshot is finite by construction; the legacy x/y/ex/ey vectors are
        # what a client sends for measured data, which legitimately carries NaN and Inf (they
        # are masked or sanitised on the way out, never refused on the way in).
        if (
            array.dtype.kind not in allowed_kinds
            or array.ndim != 1
            or (kind != "legacy" and not np.all(np.isfinite(array)))
        ):
            raise ValueError("cached arrays must be finite numeric vectors")
        arrays[field] = array.copy()
    if arrays and len({len(array) for array in arrays.values()}) != 1:
        raise ValueError("cached arrays have different lengths")
    metadata = _restore_scientific_value(payload.get("metadata", {}))
    if not isinstance(metadata, dict):
        raise ValueError("cached curve metadata must be an object")
    if "unique_identifier" in metadata and metadata["unique_identifier"] != uid:
        raise ValueError("cached curve metadata contradicts its UID")
    _scientific_value(metadata)
    # The PDA histogram / burst table and MFD data a curve carries beside x/y:
    # the same fields, decoded the same way, as a project file restores.
    auxiliary = payload.get("auxiliary") or {}
    if not isinstance(auxiliary, dict) or set(auxiliary) - AUXILIARY_FIELDS:
        raise ValueError("unsupported cached curve auxiliary field")
    for value in auxiliary.values():
        _scientific_value(_restore_scientific_value(value))
    reader = payload.get("reader")
    inputs = payload.get("reader_inputs", {})
    if reader is not None:
        if not isinstance(reader, dict):
            raise ValueError("invalid cached reader descriptor")
        module, class_name = reader.get("module"), reader.get("class")
        if not isinstance(module, str) or not isinstance(class_name, str):
            raise ValueError("invalid cached reader type")
        reader_fields = _READER_FIELDS.get((module, class_name))
        if reader_fields is None:
            raise ValueError("cached reader type is not trusted")
        state = reader.get("state")
        if (
            not isinstance(reader.get("uid"), str)
            or not reader["uid"]
            or not isinstance(state, dict)
            or set(state) - {*reader_fields, *_COMMON_READER_FIELDS}
        ):
            raise ValueError("invalid cached reader state")
        identity = _scientific_value({"reader": reader, "experiment": payload.get("experiment")})
        if reader["uid"] in seen and seen[reader["uid"]] != identity:
            raise ValueError("cached reader identity has inconsistent records")
        seen[reader["uid"]] = identity
        _scientific_value(state)
        dependencies = reader.get("dependencies", {})
        irf_array = reader.get("irf_array")
        if not isinstance(dependencies, dict):
            raise ValueError("invalid cached reader dependencies")
        if dependencies or irf_array is not None:
            if (reader["module"], reader["class"]) != (
                "chisurf.core.experiments.tcspc.simulator",
                "TCSPCSimulatorSetup",
            ) or (dependencies and irf_array is not None):
                raise ValueError("invalid cached reader IRF ownership")
        if irf_array is not None:
            if not isinstance(irf_array, dict) or not isinstance(irf_array.get("dtype"), str):
                raise ValueError("invalid cached reader IRF array")
            irf = np.asarray(irf_array.get("values"), dtype=np.dtype(irf_array["dtype"]))
            if irf.dtype.kind not in "iuf" or irf.ndim != 1 or not np.all(np.isfinite(irf)):
                raise ValueError("cached reader IRF must be a finite numeric vector")
        if not isinstance(inputs, dict) or set(inputs) != set(dependencies):
            raise ValueError("cached reader inputs do not match dependencies")
        if set(inputs) - {"instrument_response_function"}:
            raise ValueError("unsupported cached reader input")
        inputs = {role: _prepare_cached_dataset(value, seen) for role, value in inputs.items()}
        if any(
            value.get("uid") != dependencies[role] or value["kind"] != "curve"
            for role, value in inputs.items()
        ):
            raise ValueError("cached reader dependency identity differs")
    elif inputs:
        raise ValueError("cached reader inputs have no owning reader")
    if kind in {"curve", "structure"} and (
        not isinstance(payload.get("uid"), str) or not payload["uid"]
    ):
        raise ValueError("cached curve UID is missing")
    experiment = payload.get("experiment")
    if experiment is not None:
        from chisurf.core.experiments.core.experiment import Experiment
        from chisurf.core.project.session import _resolve_model

        if (
            not isinstance(experiment, dict)
            or experiment.get("kind") != "experiment"
            or (experiment.get("module"), experiment.get("class"))
            != (Experiment.__module__, Experiment.__name__)
            or not isinstance(experiment.get("uid"), str)
            or not experiment["uid"]
            or not isinstance(experiment.get("models", []), list)
        ):
            raise ValueError("unsupported cached experiment descriptor")
        for model_state in experiment.get("models", []):
            _resolve_model(model_state)
    return {
        **copy.deepcopy(payload),
        "kind": kind,
        "arrays": arrays,
        "metadata": metadata,
        "reader_inputs": inputs,
    }


def _live_identities(state: SessionState) -> tuple[dict[str, Any], dict[str, Any]]:
    """The experiments and readers the session's datasets already hold, by UID."""
    experiments: dict[str, Any] = {}
    readers: dict[str, Any] = {}
    for dataset in list(state.datasets):
        members = _dataset_members(dataset) or []
        for item in (dataset, *members):
            experiment = getattr(item, "experiment", None)
            uid = str(getattr(experiment, "unique_identifier", "") or "")
            if uid:
                experiments.setdefault(uid, experiment)
            reader = getattr(item, "data_reader", None)
            uid = str(getattr(reader, "unique_identifier", "") or "")
            if uid:
                readers.setdefault(uid, reader)
    return experiments, readers


def _restore_cached_dataset(
    prepared: dict[str, Any],
    live: tuple[dict[str, Any], dict[str, Any]] | None = None,
) -> Any:
    """Reconstruct validated data using fixed domain types and the trusted reader codec.

    Parameters
    ----------
    prepared : dict
        A record :func:`_prepare_cached_dataset` validated.
    live : tuple of dict, optional
        The experiments and readers the session already holds, by UID
        (:func:`_live_identities`). A record naming one of them binds to that
        object, so a reader that read two files is one reader in the session,
        as it is in the client that read them; its configuration becomes the
        one this record carries (the client's reader as it is now).
    """
    from chisurf.core.data import (
        DataCurve,
        DataCurveGroup,
        DataGroup,
        ExperimentDataCurveGroup,
        ExperimentDataGroup,
    )
    from chisurf.core.experiments.core.experiment import Experiment
    from chisurf.core.project.session import (
        _resolve_model,
        _restore_reader,
        apply_reader_fields,
        restore_auxiliary,
    )

    live_experiments, live_readers = live if live is not None else ({}, {})
    readers: dict[str, Any] = {}
    curves: dict[str, Any] = {}
    experiments: dict[str, Any] = dict(live_experiments)

    def construct(record):
        """Restore the known curve/group and reader-IRF edges without reading data."""
        if record["kind"] == "group":
            members = [construct(member) for member in record["members"]]
            group_class = {
                "DataGroup": DataGroup,
                "DataCurveGroup": DataCurveGroup,
                "ExperimentDataGroup": ExperimentDataGroup,
                "ExperimentDataCurveGroup": ExperimentDataCurveGroup,
            }[record["group_type"]]
            group = group_class(
                members, name=record.get("name", ""), unique_identifier=record["uid"]
            )
            group.meta_data.update(record["metadata"])
            group.current_dataset = record["selected"]
            group.data_reader = getattr(members[0], "data_reader", None)
            group.experiment = getattr(members[0], "experiment", None)
            return group
        uid = record.get("uid")
        if uid and uid in curves:
            return curves[uid]
        experiment = None
        state = record.get("experiment")
        if state is not None:
            if (
                not isinstance(state, dict)
                or state.get("kind") != "experiment"
                or (state.get("module"), state.get("class"))
                != (Experiment.__module__, Experiment.__name__)
                or not isinstance(state.get("uid"), str)
                or not state["uid"]
            ):
                raise ValueError("unsupported cached experiment descriptor")
            if state["uid"] not in experiments:
                experiment = Experiment(name=state.get("name", ""), unique_identifier=state["uid"])
                experiment.hidden = bool(state.get("hidden", False))
                for model_state in state.get("models", []):
                    experiment.add_model_class(_resolve_model(model_state))
                experiments[state["uid"]] = experiment
            experiment = experiments[state["uid"]]
        reader_state = record.get("reader")
        bound = live_readers.get(reader_state["uid"]) if reader_state else None
        if bound is not None and (
            (type(bound).__module__, type(bound).__name__)
            == (reader_state["module"], reader_state["class"])
            and getattr(bound, "experiment", None) is experiment
        ):
            apply_reader_fields(bound, reader_state.get("state") or {})
            reader = bound
        else:
            reader = _restore_reader(reader_state, experiment, readers)
        for role, source in record["reader_inputs"].items():
            setattr(reader, role, construct(source))
        if record["kind"] == "structure":
            from chisurf.core.models.structure.snapshot import restore_structure

            curve = restore_structure(record["structure"])
            if curve is None or str(curve.unique_identifier) != uid:
                raise ValueError("cached structure identity contradicts its UID")
            curve.experiment = experiment
            curve.data_reader = reader
        else:
            curve = DataCurve(
                **record["arrays"],
                name=record.get("name", "dataset"),
                unique_identifier=uid,
                experiment=experiment,
                data_reader=reader,
                setup=reader,
            )
        curve.filename = record.get("filename", "")
        curve.meta_data.update(record["metadata"])
        restore_auxiliary(curve, record.get("auxiliary") or {})
        if uid:
            curves[uid] = curve
        return curve

    return construct(prepared)


def _normalize_cached_group(dataset: Any) -> Any:
    """Keep cached group UID/metadata/members while retaining the live macro's expected type."""
    import copy

    from chisurf.core.data import DataGroup, ExperimentDataCurveGroup, ExperimentDataGroup

    if isinstance(dataset, DataGroup) and not isinstance(dataset, ExperimentDataGroup):
        group = ExperimentDataCurveGroup(
            list(dataset), name=dataset.name, unique_identifier=dataset.unique_identifier
        )
        group.meta_data.update(copy.deepcopy(dataset.meta_data))
        group.current_dataset = dataset._current_dataset
        group.data_reader = getattr(dataset, "data_reader", None)
        return group
    return dataset


def add_dataset(
    state: SessionState,
    reader: Any = None,
    reader_name: str | None = None,
    filename: str | None = None,
    name: str | None = None,
    curve_data: dict[str, Any] | None = None,
    _from_controller: bool = False,
    event_bus: Any = None,
) -> ServiceResult:
    """Add a dataset to the session, either via a reader or raw curve data.

    Parameters
    ----------
    state : SessionState
        Server-side session state.
    reader : object, optional
        Data reader instance.
    reader_name : str, optional
        Name of the reader (ignored if *reader* is provided).
    filename : str, optional
        Path to the data file. Without *curve_data* it is read here by the
        registered reader *reader_name* (display or class name).
    name : str, optional
        Display name for the dataset.
    curve_data : dict, optional
        Legacy x/y/ex/ey vectors or a trusted cached curve/group snapshot.
        Cached groups are fully validated and appended as one dataset.
    _from_controller : bool
        Internal flag to suppress duplicate event publishing.
    event_bus : object, optional
        Event bus for broadcasting.

    """
    if curve_data is not None:
        try:
            prepared = _prepare_cached_dataset(curve_data)
            ds = _restore_cached_dataset(prepared, _live_identities(state))
            if prepared["kind"] == "legacy" and name:
                ds.name = str(name)
            from chisurf.core.data import ensure_unique_dataset_uids

            ensure_unique_dataset_uids(ds, state.datasets)
            state.add_dataset(ds)
            index = len(state.datasets) - 1
            if event_bus is not None and not _from_controller:
                event_bus.publish("dataset.added", {"dataset_index": index, "name": str(ds.name)})
            return {
                "ok": True,
                "uid": str(ds.unique_identifier),
                "name": str(ds.name),
                "dataset_index": index,
            }
        except (TypeError, ValueError, KeyError, AttributeError) as error:
            return service_error(
                f"invalid cached dataset: {error}", error_code=INVALID_INPUT, exception=error
            )
    if reader is None and reader_name and filename:
        # No record from the client: read the file here with the reader it
        # names. Fabricating an empty curve named after the file (as this did)
        # handed a structure's models a ``DataCurve`` to draw.
        from chisurf.core.experiments.bootstrap import (
            ensure_experiments_registered,
            find_reader,
        )

        ensure_experiments_registered(allow_widgets=False)
        named = find_reader(None, str(reader_name))
        if named is None:
            return service_error(f"unknown reader {reader_name!r}", error_code=INVALID_INPUT)
        try:
            group = named.get_data(filename=str(filename))
        except Exception as e:
            return service_error(
                f"{reader_name} could not read {filename}: {e}",
                error_code=OPERATION_FAILED,
                exception=e,
            )
        if name:
            group.name = str(name)
        state.add_dataset(group)
        index = len(state.datasets) - 1
        if event_bus is not None and not _from_controller:
            event_bus.publish("dataset.added", {"dataset_index": index, "name": str(group.name)})
        return {
            "ok": True,
            "uid": str(getattr(group, "unique_identifier", "") or ""),
            "name": str(group.name),
            "dataset_index": index,
        }

    if reader is None:
        return service_error("no reader provided", error_code=INVALID_INPUT)

    dataset_name = str(name or getattr(reader, "name", "dataset"))
    try:
        dataset_group = reader.read(name=dataset_name)
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)

    from chisurf.core.data import DataGroup

    if isinstance(dataset_group, (list, DataGroup)):
        for ds in dataset_group:
            state.add_dataset(ds)
    else:
        if hasattr(dataset_group, "__iter__") and not isinstance(dataset_group, (str, bytes)):
            for ds in dataset_group:
                state.add_dataset(ds)
        else:
            state.add_dataset(dataset_group)

    if event_bus is not None and not _from_controller:
        event_bus.publish(
            "dataset.added", {"dataset_index": len(state.datasets) - 1, "name": dataset_name}
        )

    return {
        "ok": True,
        "uid": str(getattr(dataset_group, "unique_identifier", "") or ""),
        "name": dataset_name,
        "dataset_index": len(state.datasets) - 1,
    }


def dataset_rename(
    state: SessionState,
    dataset_index: int | None = None,
    dataset_uid: str | None = None,
    new_name: str = "",
) -> ServiceResult:
    """Rename a dataset.

    Parameters
    ----------
    state : SessionState
        Server-side session state.
    dataset_index : int, optional
        Positional index.
    dataset_uid : str, optional
        Unique identifier.
    new_name : str
        New name.

    """
    d, _ = _resolve_dataset(state, dataset_index, dataset_uid)
    if d is None:
        return service_error("dataset not found", error_code=NOT_FOUND)
    try:
        d.name = str(new_name)
        return {"ok": True, "uid": dataset_uid, "new_name": new_name}
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


def dataset_group(
    state: SessionState,
    dataset_indices: list[int],
    group_name: str | None = None,
) -> ServiceResult:
    """Group selected datasets into an ``ExperimentDataGroup``.

    Parameters
    ----------
    state : SessionState
        Server-side session state.
    dataset_indices : list of int
        Indices of datasets to group.
    group_name : str, optional
        Name for the new group.

    """
    datasets = list(state.datasets)
    indices, error = _validated_dataset_indices(
        datasets,
        dataset_indices,
        empty_message="no dataset indices provided",
    )
    if error is not None:
        return error

    selected = []
    remaining = []
    for i, d in enumerate(datasets):
        if i in indices:
            selected.append(d)
        else:
            remaining.append(d)

    try:
        from chisurf.core.data import (
            DataCurve,
            DataGroup,
            ExperimentDataCurveGroup,
            ExperimentDataGroup,
        )

        # ``ExperimentDataGroup()`` without its sequence raised, so grouping over
        # RPC never worked. A fit over the group gets one member per curve, so the
        # curves of each one-file group are what is grouped, as the local macro does.
        curves = [c for d in selected for c in (d if isinstance(d, DataGroup) else [d])]
        name = str(group_name or "Data-Group")
        group: ExperimentDataGroup
        if curves and all(isinstance(c, DataCurve) for c in curves):
            group = ExperimentDataCurveGroup(curves, name=name)
        else:
            group = ExperimentDataGroup(selected, name=name)
        remaining.append(group)
        state.datasets[:] = remaining
        return {
            "ok": True,
            "group_uid": str(getattr(group, "unique_identifier", "") or ""),
            "group_name": group.name,
            "member_count": len(selected),
            "dataset_count": len(remaining),
        }
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


def dataset_ungroup(
    state: SessionState,
    dataset_indices: list[int],
) -> ServiceResult:
    """Ungroup previously grouped datasets at *dataset_indices*.

    Parameters
    ----------
    state : SessionState
        Server-side session state.
    dataset_indices : list of int
        Indices of groups to ungroup.

    """
    datasets = list(state.datasets)
    indices, error = _validated_dataset_indices(
        datasets,
        dataset_indices,
        empty_message="no dataset indices provided",
    )
    if error is not None:
        return error

    new_datasets = []
    ungrouped = 0
    for i, d in enumerate(datasets):
        if i in indices:
            try:
                if hasattr(d, "__iter__") and not isinstance(d, (str, bytes)):
                    for member in d:
                        new_datasets.append(member)
                        ungrouped += 1
                    continue
            except Exception:
                pass
            new_datasets.append(d)
        else:
            new_datasets.append(d)

    state.datasets[:] = new_datasets
    return {
        "ok": True,
        "ungrouped_count": ungrouped,
        "dataset_count": len(new_datasets),
    }


def remove_datasets(
    state: SessionState,
    dataset_indices: list[int] | None = None,
    dataset_uids: list[str] | None = None,
    _from_controller: bool = False,
    event_bus: Any = None,
) -> ServiceResult:
    """Remove datasets by index or uid, preventing removal if fits depend on them.

    Parameters
    ----------
    state : SessionState
        Server-side session state.
    dataset_indices : list of int, optional
        Indices to remove.
    dataset_uids : list of str, optional
        UIDs to remove.
    _from_controller : bool
        Internal flag to suppress duplicate event publishing.
    event_bus : object, optional
        Event bus for broadcasting.

    """
    indices: list[int] = []

    if dataset_uids:
        all_ds = list(state.datasets)
        for i, d in enumerate(all_ds):
            if str(getattr(d, "unique_identifier", "")) in dataset_uids:
                indices.append(i)

    if dataset_indices:
        indices.extend(int(i) for i in dataset_indices)

    if not indices:
        return service_error("no datasets specified for removal", error_code=INVALID_INPUT)

    datasets = list(state.datasets)
    indices, error = _validated_dataset_indices(
        datasets,
        indices,
        empty_message="no datasets specified for removal",
    )
    if error is not None:
        return error

    for i in indices:
        deps = _find_fits_using_dataset(datasets[i], state)
        if deps:
            ds_name = getattr(datasets[i], "name", f"index {i}")
            fit_names = ", ".join(str(getattr(f, "name", "?")) for f in deps)
            return service_error(
                f"dataset '{ds_name}' is used by fit(s): {fit_names}. Remove fits first.",
                error_code=INVALID_STATE,
            )

    to_remove = [datasets[i] for i in indices if not _is_global_fit_dataset(datasets[i])]
    kept = [d for d in datasets if d not in to_remove]
    state.datasets[:] = kept

    if event_bus is not None and not _from_controller:
        event_bus.publish(
            "dataset.removed", {"removed_count": len(to_remove), "remaining_count": len(kept)}
        )

    return {
        "ok": True,
        "removed_count": len(to_remove),
        "remaining_count": len(kept),
    }


def clear_datasets(state: SessionState, event_bus: Any = None) -> ServiceResult:
    """Remove all datasets from the session.

    Parameters
    ----------
    state : SessionState
        Server-side session state.
    event_bus : object, optional
        Event bus for broadcasting.

    """
    count = len(state.datasets)
    global_datasets = [d for d in state.datasets if _is_global_fit_dataset(d)]
    state.datasets.clear()
    state.datasets.extend(global_datasets)
    if event_bus is not None:
        event_bus.publish("dataset.cleared", {"cleared_count": count})
    return {"ok": True, "cleared_count": count}


def _sanitize_float_list(values: Any) -> list[float | None] | None:
    """Convert an iterable to a JSON-safe list of floats, replacing NaN/Inf with None."""
    import numpy as np

    if values is None:
        return None
    try:
        arr = np.asarray(values, dtype=float)
        result: list[float | None] = []
        for v in arr.flat:
            if np.isnan(v) or np.isinf(v):
                result.append(None)
            else:
                result.append(float(v))
        return result
    except Exception:
        return None


def get_dataset_curve_data(
    state: SessionState,
    dataset_index: int | None = None,
    dataset_uid: str | None = None,
    member_uid: str | None = None,
) -> ServiceResult:
    """Return x/y/ex/ey for a dataset or explicit direct member, without changing selection."""
    parent, index = _resolve_dataset(state, dataset_index, dataset_uid)
    d, member_index = _resolve_dataset_member(parent, member_uid)
    if d is None:
        return service_error("dataset not found", error_code=NOT_FOUND)
    try:
        result: dict[str, Any] = {"ok": True}
        result["x"] = _sanitize_float_list(getattr(d, "x", None))
        result["y"] = _sanitize_float_list(getattr(d, "y", None))
        result["ex"] = _sanitize_float_list(getattr(d, "ex", None))
        result["ey"] = _sanitize_float_list(getattr(d, "ey", None))
        if member_uid is not None:
            result.update(
                dataset_index=index,
                dataset_uid=str(getattr(parent, "unique_identifier", "")),
                member_index=member_index,
                member_uid=str(getattr(d, "unique_identifier", "")),
            )
        return result
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)
