"""Detached, fail-closed serialization of a ChiSurf scientific session."""

from __future__ import annotations

import copy
import importlib
import json
import math
import uuid
import weakref
from collections.abc import MutableMapping
from contextlib import contextmanager
from dataclasses import dataclass
from functools import wraps
from threading import RLock, get_ident
from typing import Any, Iterable

import numpy as np

from .project import Project, ResourceContext

_MODEL_REGISTRY: dict[tuple[str, str], type] = {}
_EXPERIMENT_REGISTRY: dict[tuple[str, str], type] = {}
# The archive cannot turn a package prefix into an arbitrary import. These
# identities are the actual shipped Model classes, not archive-provided aliases.
_BUILTIN_MODELS = {
    "model": ("Model", "ModelCurve"),
    "parse.parse": ("ParseModel",),
    "global_model.globalfit": ("GlobalFitModel",),
    "fcs.mdf": ("MdfFCSModel",),
    "fcs.general": ("GeneralFCSModel",),
    "fcs.kinetics": ("FCSKineticsModel",),
    "fcs.maxent_models": ("MaxEntFCSModel", "MaxEntRHModel"),
    "fcs.dye_shape": ("DyeShapeFCSModel",),
    "deer.deer": ("DeerGaussianModel", "DeerRiceModel", "DeerTikhonovModel", "DeerMaxEntModel"),
    "mfd.two_dimensional": ("Mfd2DModel",),
    "parameter_transform.model": ("ParameterTransformModel",),
    "pch.pch_model": ("PchMultiComponentModel",),
    "pch.fida_model": ("FidaModel",),
    "pda2c.simple": ("Pda2cSimpleModel",),
    "pda2c.pdagauss": ("Pda2cGaussianDistanceModel",),
    "pda2c.saw_nu": ("Pda2cSawNuModel",),
    "pda2c.dynamic_mc": ("Pda2cDynamicNStateModel",),
    "pda2c.dynamic": ("Pda2cDynamicTwoStateModel",),
    "pda2c.anisotropy": ("Pda2cAnisotropyModel",),
    "pda3c.pda3c": ("Pda3cModel",),
    "stopped_flow.reaction": ("ReactionModel",),
    "structure.proteinmc_model": ("ProteinMCModel",),
    "tcspc.fret_structure": ("FRETStructure",),
}
_BUILTIN_MODEL_KEYS = {
    (f"chisurf.core.models.{module}", name)
    for module, names in _BUILTIN_MODELS.items()
    for name in names
}
_CATALOGUE_MODELS = {
    ("chisurf.core.models.fcs.parse", "EquationModel_fcs"): "ParseFCSModel",
    ("chisurf.core.models.pcf.parse", "EquationModel_pcf"): "ParsePCFModel",
    (
        "chisurf.core.models.stopped_flow.parse",
        "EquationModel_stopped_flow",
    ): "ParseStoppedFlowModel",
    ("chisurf.core.models.tcspc.parse.tcspc_parse", "EquationModel_parse"): "ParseDecayModel",
}
_ICS_MODEL_KEY = ("chisurf.core.models.ics.ics", "EquationModel_ics")
_ICS_MODEL_MODES = {
    ("Image correlation (3D)", "Image correlation (2D membrane)"): "ImageCorrelationModel",
    ("2D Gaussian (2 sigma + angle)",): "IcsGaussian2DModel",
}
# Archive data may select only these built-in reader types. Connections,
# controllers and callbacks are runtime resources, never portable state.
_READER_FIELDS = {
    ("chisurf.core.experiments.tcspc.reader", "TCSPCReader"): (
        "dt",
        "rep_rate",
        "excitation_repetition_rate",
        "is_vv_vh",
        "dt_scaled",
        "polarization",
        "g_factor",
        "l1",
        "l2",
        "rebin",
        "matrix_columns",
        "skiprows",
        "use_header",
        "col_x",
        "col_y",
        "fit_area",
        "fit_count_threshold",
        "fit_start_fraction",
        "reading_routine",
        "vh_shift",
    ),
    ("chisurf.core.experiments.fcs.reader", "FCS"): (
        "skiprows",
        "use_header",
        "experiment_reader",
        "weight_mode",
        "weight_kwargs",
        "col_x",
        "col_y",
        "col_ex",
        "col_ey",
        "error_x_on",
        "error_y_on",
    ),
    ("chisurf.core.experiments.globalfit.reader", "GlobalFitSetup"): (),
}
_COMMON_READER_FIELDS = ("name", "record_provenance", "sample_id")
_TCSPC_FIELDS = _READER_FIELDS[("chisurf.core.experiments.tcspc.reader", "TCSPCReader")]
_READER_FIELDS.update(
    {
        ("chisurf.core.experiments.tcspc.sdt_reader", "SDTReader"): (*_TCSPC_FIELDS, "curve_nbr"),
        ("chisurf.core.experiments.tcspc.tttr_reader", "TCSPCTTTRReader"): (
            *_TCSPC_FIELDS,
            "channel_numbers",
            "channel",
            "micro_time_coarsening",
            "micro_time_shift",
            "channel_luts",
            "channel_shifts",
            "apply_lut",
            "detector_setup",
            "detector_name",
        ),
        ("chisurf.core.experiments.tcspc.simulator", "TCSPCSimulatorSetup"): (
            *_TCSPC_FIELDS,
            "sample_name",
            "lifetime_spectrum",
            "rotation_spectrum",
            "n_tac",
            "p0",
            "irf_mean",
            "irf_sigma",
            "add_noise",
            "seed",
        ),
        ("chisurf.core.experiments.deer.reader", "DeerReader"): (
            "phase_correction",
            "normalize",
            "exp_type",
        ),
        ("chisurf.core.experiments.pda2c.reader", "Pda2cReader"): (
            "reading_routine",
            "maximum_number_of_photons",
            "minimum_number_of_photons",
            "minimum_time_window_length",
            "tw_configs",
            "n_colors",
            "segmentation",
            "channels",
            "micro_time_ranges",
        ),
        ("chisurf.core.experiments.pda3c.reader", "Pda3cBurstTableReader"): (),
        ("chisurf.core.experiments.pda3c.reader", "Pda3cSimulatorReader"): (
            "n_bursts",
            "r_gr",
            "r_bg",
            "r_br",
            "sigma",
            "correlation",
            "photons_blue",
            "photons_green",
            "r0_bg",
            "r0_br",
            "r0_gr",
            "seed",
        ),
        ("chisurf.core.experiments.ics", "ICSReader"): (
            "reading_routine",
            "channel",
            "channel_numbers",
            "pixel_duration",
            "line_duration",
            "frame_duration",
            "pixel_size_nm",
            "micro_time_ranges",
            "x_range",
            "y_range",
            "subtract_average",
            "max_frame_lag",
            "fftshift",
            "roi",
            "drift_correction",
        ),
        ("chisurf.core.experiments.mfd.reader", "MfdReader"): (
            "green",
            "red",
            "n_ratio_bins",
            "n_micro_time_bins",
            "micro_time_min",
            "micro_time_max",
            "min_green_photons",
            "n_signal_bins",
            "n_span_bins",
        ),
        ("chisurf.core.experiments.pch.reader", "PCHReader"): (
            "reading_routine",
            "channel",
            "channel_numbers",
            "bin_time_us",
            "micro_time_range",
        ),
        ("chisurf.core.experiments.modelling.reader", "StructureReader"): (
            "compute_internal_coordinates",
        ),
    }
)
_CONSTRUCTION_LOCK = RLock()


class _ConstructionIndex(MutableMapping):
    """Route staging-thread identities away from the live object registry."""

    def __init__(self, live, staged, thread):
        self.live, self.staged, self.thread = live, staged, thread

    def _target(self):
        return self.staged if get_ident() == self.thread else self.live

    def __getitem__(self, key):
        return self._target()[key]

    def __setitem__(self, key, value):
        self._target()[key] = value

    def __delitem__(self, key):
        del self._target()[key]

    def __iter__(self):
        return iter(self._target())

    def __len__(self):
        return len(self._target())


@contextmanager
def _detached_construction():
    """Construct against a private native session and identity/cache namespace.

    Existing constructors register through process-wide accessors. Route only
    this synchronous staging thread to private registries; other threads keep
    the live accessors. No live graph is cleared, loaded, or rolled back.
    """
    import IMP.bff as bff

    from chisurf.core.base import Base
    from chisurf.core.fitting import factorgraph

    with _CONSTRUCTION_LOCK:
        thread = get_ident()
        native = bff.GraphSession()
        live_session = bff.get_session
        live_index = Base._uuid_index
        originals = {
            name: getattr(factorgraph, name)
            for name in (
                "structure_version",
                "window_version",
                "bump_structure_version",
                "bump_window_version",
            )
        }
        versions = {
            "structure": originals["structure_version"](),
            "window": originals["window_version"](),
        }

        def session():
            return native if get_ident() == thread else live_session()

        def counter(name, kind, bump):
            def access():
                if get_ident() != thread:
                    return originals[name]()
                versions[kind] += int(bump)
                return versions[kind]

            return access

        bff.get_session = session
        Base._uuid_index = _ConstructionIndex(live_index, weakref.WeakValueDictionary(), thread)
        for kind in ("structure", "window"):
            for bump in (False, True):
                name = f"{'bump_' if bump else ''}{kind}_version"
                setattr(factorgraph, name, counter(name, kind, bump))
        try:
            yield native
        finally:
            bff.get_session = live_session
            Base._uuid_index = live_index
            for name, function in originals.items():
                setattr(factorgraph, name, function)


def _isolated(function):
    """Keep session capture/reconstruction outside live registries."""

    @wraps(function)
    def run(*args, **kwargs):
        with _detached_construction():
            result = function(*args, **kwargs)
            if isinstance(result, RestoredSession):
                import IMP.bff as bff

                # Re-index current declared topology after UID restoration.
                # Constructors may have registered superseded catalogue nodes.
                indexed = bff.GraphSession()
                ports = {}

                def add_port(port):
                    uid = str(port.get_uid())
                    if uid in ports:
                        return
                    ports[uid] = port
                    indexed.add_port(port)
                    target = port.get_link()
                    if target is not None:
                        add_port(target)

                for fit in result.fits:
                    models = [member.model for member in _local_fits(fit)]
                    if hasattr(fit, "grouped_fits"):
                        models.append(fit._model)
                    for model in models:
                        declared_nodes = getattr(model, "get_session_native_nodes", None)
                        for node in declared_nodes() if callable(declared_nodes) else []:
                            indexed.add_node(node.get_uid(), node)
                            for port in node.get_ports().values():
                                add_port(port)
                        for parameter in _parameter_list(model):
                            add_port(parameter._port)
                result.native_session = indexed
            return result

    return run


def _reader_state(reader: Any) -> dict[str, Any] | None:
    if reader is None:
        return None
    key = (type(reader).__module__, type(reader).__name__)
    if key == ("chisurf.gui.widgets.experiments.tcspc.bh_sdt", "TCSPCSetupSDTWidget"):
        key = ("chisurf.core.experiments.tcspc.sdt_reader", "SDTReader")
    fields = _READER_FIELDS.get(key)
    if fields is None:
        raise SessionCodecError(f"reader {key[0]}.{key[1]} is not trusted")
    result = {
        "module": key[0],
        "class": key[1],
        "uid": _uid(reader, "reader"),
        "state": {
            field: _json_value(getattr(reader, field))
            for field in (*_COMMON_READER_FIELDS, *fields)
            if hasattr(reader, field)
        },
    }
    if key == ("chisurf.core.experiments.tcspc.simulator", "TCSPCSimulatorSetup"):
        irf = getattr(reader, "instrument_response_function", None)
        if irf is not None:
            if hasattr(irf, "x") and hasattr(irf, "y"):
                result["dependencies"] = {"instrument_response_function": _uid(irf, "dataset")}
            else:
                values = np.asarray(irf)
                if values.ndim != 1 or not np.all(np.isfinite(values)):
                    raise SessionCodecError("reader IRF must be a finite vector or curve")
                result["irf_array"] = {"dtype": str(values.dtype), "values": values.tolist()}
    return result


def _restore_reader(state: Any, experiment: Any, cache: dict[str, Any]) -> Any:
    if state is None:
        return None
    if not isinstance(state, dict):
        raise SessionCodecError("invalid reader descriptor")
    module, class_name = state.get("module"), state.get("class")
    if not isinstance(module, str) or not isinstance(class_name, str):
        raise SessionCodecError("invalid reader type descriptor")
    key = (module, class_name)
    fields = _READER_FIELDS.get(key)
    if fields is None:
        raise SessionCodecError(f"reader {key[0]}.{key[1]} is not trusted")
    values = state.get("state")
    allowed = {*_COMMON_READER_FIELDS, *fields}
    if not isinstance(values, dict) or set(values) - allowed:
        raise SessionCodecError("invalid reader configuration fields")
    uid = state.get("uid")
    if not isinstance(uid, str) or not uid:
        raise SessionCodecError("reader UID is missing")
    if uid in cache:
        reader, saved_state = cache[uid]
        if saved_state != state or reader.experiment is not experiment:
            raise SessionCodecError(f"inconsistent reader identity {uid!r}")
        return reader
    cls = getattr(importlib.import_module(key[0]), key[1])
    required = (
        {field: copy.deepcopy(values[field]) for field in ("channels", "micro_time_ranges")}
        if key == ("chisurf.core.experiments.pda2c.reader", "Pda2cReader")
        else {}
    )
    reader = cls(experiment=experiment, record_provenance=False, **required)
    dependencies = state.get("dependencies", {})
    irf_array = state.get("irf_array")
    if dependencies or irf_array is not None:
        if key != ("chisurf.core.experiments.tcspc.simulator", "TCSPCSimulatorSetup"):
            raise SessionCodecError("reader cannot own IRF dependencies")
        if (
            not isinstance(dependencies, dict)
            or set(dependencies) - {"instrument_response_function"}
            or (dependencies and irf_array is not None)
        ):
            raise SessionCodecError("invalid reader dependency")
        if irf_array is not None:
            try:
                irf = np.asarray(irf_array["values"], dtype=irf_array["dtype"])
                if irf.ndim != 1 or not np.all(np.isfinite(irf)):
                    raise ValueError("invalid IRF")
                reader.instrument_response_function = irf
            except Exception as exc:
                raise SessionCodecError("invalid reader IRF array") from exc
    # This property changes other settings. Apply it before the independently
    # recorded fields, including after JSON has sorted the configuration keys.
    if "is_vv_vh" in values:
        reader.is_vv_vh = bool(values["is_vv_vh"])
    if "n_colors" in values:
        reader.n_colors = values["n_colors"]
    for field, value in values.items():
        if field in {"is_vv_vh", "n_colors"}:
            continue
        if field in {"rebin", "matrix_columns"}:
            value = tuple(value)
        if field in {"channel_luts", "channel_shifts"}:
            value = {int(k): v for k, v in value.items()}
        setattr(reader, field, copy.deepcopy(value))
    reader.unique_identifier = uid
    if experiment is not None:
        experiment.add_reader(reader)
    cache[uid] = (reader, copy.deepcopy(state))
    return reader


class SessionCodecError(ValueError):
    """Raised when a session cannot be captured or reconstructed exactly."""


@dataclass
class RestoredSession:
    """Detached result of :func:`restore_session`."""

    datasets: list[Any]
    fits: list[Any]
    ui_state: dict[str, Any]
    experiments: dict[str, Any]
    native_session: Any = None
    resources: ResourceContext | None = None


def owned_scientific_objects(owner: Any, *, include_plugins: bool = True) -> dict[str, Any]:
    """Index only the scientific objects reachable from a declared owner.

    Session-local services use this index rather than the process registry.
    Walking explicit scientific edges also covers additive imports and groups.
    """
    from chisurf.core.models.model import Model

    result: dict[str, Any] = {}
    # Parameter/group properties may return temporary lists. Keep their objects
    # alive for this walk so a later list cannot reuse an already-visited id.
    seen: dict[int, Any] = {}

    def visit(obj):
        if obj is None or id(obj) in seen:
            return
        seen[id(obj)] = obj
        if isinstance(obj, dict):
            for value in obj.values():
                visit(value)
            return
        if isinstance(obj, (list, tuple)):
            for value in obj:
                visit(value)
        uid = getattr(obj, "unique_identifier", None)
        if uid is not None:
            key = str(uid)
            if key in result and result[key] is not obj:
                raise SessionCodecError(f"duplicate owned scientific UID {key!r}")
            result[key] = obj
        else:
            return
        for field in (
            "data",
            "data_reader",
            "experiment",
            "grouped_fits",
            "model",
            "_model",
            "parameters_all",
            "aggregated_parameters",
            "global_parameters_all",
            "readers",
            "generic",
            "convolve",
            "background_curve",
            "_irf",
            "instrument_response_function",
        ):
            if field == "data" and isinstance(obj, Model):
                continue  # Model.data may compute a derived global-fit view.
            # Ownership uses the same declaration as capture/restore, including
            # inactive presets. Nested groups supply their concrete service owner.
            child = (
                _parameter_list(obj)
                if field == "parameters_all" and isinstance(obj, Model)
                else getattr(obj, field, None)
            )
            if child is not obj:
                visit(child)

    roots: tuple[str, ...] = ("datasets", "imported_datasets", "fits", "experiments")
    if include_plugins:
        roots = (*roots, "plugins")
    for field in roots:
        visit(getattr(owner, field, None))
    return result


def _uid(obj: Any, prefix: str) -> str:
    value = getattr(obj, "unique_identifier", None)
    if value is None and isinstance(obj, dict):
        value = obj.get("unique_identifier") or obj.get("uid")
    return str(value or f"{prefix}-{uuid.uuid4()}")


def _json_value(value: Any) -> Any:
    """Make state JSON-safe while retaining explicit optional diagnostics."""
    if isinstance(value, np.ndarray):
        return [_json_value(item) for item in value.tolist()]
    if isinstance(value, (np.integer, np.floating, np.bool_)):
        return _json_value(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(v) for v in value]
    if not isinstance(value, type):
        serializer = getattr(value, "to_dict", None)
        if callable(serializer):
            return _json_value(serializer())
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise SessionCodecError(
            f"unsupported value in project state: {type(value).__name__}"
        ) from exc
    return value


def _scientific_value(value: Any) -> Any:
    """Encode scientific metadata without erasing array dtype or tuple axes."""
    tag = "__chisurf_scientific__"
    if isinstance(value, (np.ndarray, np.generic)):
        array = np.asarray(value)
        if array.dtype.kind not in "biufU" or (
            array.dtype.kind in "iuf" and not np.all(np.isfinite(array))
        ):
            raise SessionCodecError("scientific metadata requires finite non-object arrays")
        return {
            tag: "scalar" if isinstance(value, np.generic) else "array",
            "dtype": array.dtype.str,
            "shape": list(array.shape),
            "values": array.tolist(),
        }
    if isinstance(value, tuple):
        return {tag: "tuple", "items": [_scientific_value(v) for v in value]}
    if isinstance(value, list):
        return [_scientific_value(v) for v in value]
    if isinstance(value, dict):
        if any(not isinstance(k, str) for k in value):
            raise SessionCodecError("scientific metadata keys must be strings")
        items = {k: _scientific_value(v) for k, v in value.items()}
        return {tag: "mapping", "items": items} if tag in value else items
    if value is None or type(value) in (bool, int, float, str):
        if isinstance(value, float) and not math.isfinite(value):
            raise SessionCodecError("scientific metadata contains non-finite values")
        return value
    raise SessionCodecError(f"unsupported scientific metadata type: {type(value).__name__}")


def _restore_scientific_value(value: Any) -> Any:
    """Decode data-only metadata tags; no class imports or executable objects."""
    tag = "__chisurf_scientific__"
    if isinstance(value, list):
        return [_restore_scientific_value(v) for v in value]
    if not isinstance(value, dict):
        return value
    kind = value.get(tag)
    if kind in ("array", "scalar"):
        try:
            dtype = np.dtype(value["dtype"])
            shape = value["shape"]
            if (
                dtype.kind not in "biufU"
                or not isinstance(shape, list)
                or any(type(n) is not int or n < 0 for n in shape)
            ):
                raise ValueError("invalid dtype or shape")
            array = np.asarray(value["values"], dtype=dtype)
            if list(array.shape) != shape or (
                dtype.kind in "iuf" and not np.all(np.isfinite(array))
            ):
                raise ValueError("invalid values or shape")
            if kind == "scalar" and shape:
                raise ValueError("scalar has dimensions")
            return array[()] if kind == "scalar" else array
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise SessionCodecError("invalid typed scientific array") from exc
    if kind == "tuple":
        if not isinstance(value.get("items"), list):
            raise SessionCodecError("invalid scientific tuple")
        return tuple(_restore_scientific_value(v) for v in value["items"])
    if kind == "mapping":
        if not isinstance(value.get("items"), dict):
            raise SessionCodecError("invalid scientific mapping")
        return {k: _restore_scientific_value(v) for k, v in value["items"].items()}
    if tag in value:
        raise SessionCodecError("unknown scientific metadata tag")
    return {k: _restore_scientific_value(v) for k, v in value.items()}


def _curve_record(curve: Any) -> dict[str, Any]:
    from chisurf.core.structure import Structure

    is_structure = isinstance(curve, Structure)
    required = ("x", "y", "ex", "ey", "mask")
    if not is_structure and any(not hasattr(curve, key) for key in required):
        raise SessionCodecError(f"dataset {curve!r} is not a supported curve")
    arrays = {} if is_structure else {key: np.asarray(getattr(curve, key)) for key in required}
    if any(array.ndim != 1 for array in arrays.values()):
        raise SessionCodecError(f"dataset {_uid(curve, 'dataset')} must contain 1D arrays")
    if any(not np.issubdtype(array.dtype, np.number) for array in arrays.values()):
        raise SessionCodecError(f"dataset {_uid(curve, 'dataset')} must contain numeric arrays")
    if arrays and len({len(array) for array in arrays.values()}) != 1:
        raise SessionCodecError(f"dataset {_uid(curve, 'dataset')} has inconsistent array lengths")
    if any(not np.all(np.isfinite(array)) for array in arrays.values()):
        raise SessionCodecError(
            f"dataset {_uid(curve, 'dataset')} contains non-finite scientific data"
        )
    reader = getattr(curve, "data_reader", None)
    reader_state = _reader_state(reader)
    experiment = getattr(curve, "experiment", None)
    experiment_state = None
    if experiment is not None:
        experiment_class = type(experiment)
        _EXPERIMENT_REGISTRY[(experiment_class.__module__, experiment_class.__name__)] = (
            experiment_class
        )
        model_types = []
        for model_class in getattr(experiment, "model_classes", []):
            _MODEL_REGISTRY[(model_class.__module__, model_class.__name__)] = model_class
            model_types.append(_model_identity(model_class))
        experiment_state = {
            "kind": "experiment",
            "uid": _uid(experiment, "experiment"),
            "module": experiment_class.__module__,
            "class": experiment_class.__name__,
            "name": str(experiment.name),
            "hidden": bool(getattr(experiment, "hidden", False)),
            "models": model_types,
        }
    record = {
        "uid": _uid(curve, "dataset"),
        "kind": "structure" if is_structure else "curve",
        "name": str(getattr(curve, "name", "")),
        "filename": str(getattr(curve, "filename", "") or ""),
        "arrays": {
            key: {"dtype": str(value.dtype), "values": value.tolist()}
            for key, value in arrays.items()
        },
        "metadata": _scientific_value(getattr(curve, "meta_data", {}) or {}),
        "auxiliary": {
            key: _scientific_value(getattr(curve, key))
            for key in ("pda", "pda3c")
            if hasattr(curve, key)
        },
        "experiment": experiment_state,
        "reader": reader_state,
    }
    if is_structure:
        from chisurf.core.models.structure.snapshot import capture_structure

        record["structure"] = capture_structure(curve)
    if hasattr(curve, "mfd"):
        from chisurf.core.fluorescence.mfd.fit import MfdData

        if not isinstance(curve.mfd, MfdData):
            raise SessionCodecError("MFD auxiliary requires typed MfdData")
        record["auxiliary"]["mfd"] = _scientific_value(curve.mfd.get_session_state())
    return record


def _local_fits(fit: Any) -> list[Any]:
    members = getattr(fit, "grouped_fits", None)
    return list(members) if members else [fit]


def _parameter_list(model: Any) -> list[Any]:
    """Enumerate document-owned ports, including explicitly declared inactive presets."""
    snapshot_parameters = getattr(model, "get_session_parameters", None)
    if callable(snapshot_parameters):
        return list(snapshot_parameters())
    params = getattr(model, "parameters_all", None)
    if params is None:
        params = list((getattr(model, "parameters_all_dict", {}) or {}).values())
    return list(params or [])


def _canonical_parameter_id(parameter: Any) -> str | None:
    """Return a model-declared stable port identity, never a display label.

    Described BFF models can traverse the same scientific ports in a different
    order after a topology or group-position rebuild.  Their ``canonical_id``
    is the document identity that survives that rebuild; ordinary models that
    do not declare one retain the strict positional restoration contract.
    """
    canonical_id = getattr(parameter, "canonical_id", None)
    return canonical_id if isinstance(canonical_id, str) and canonical_id else None


def _model_identity(model_class: type) -> dict[str, Any]:
    """Describe class identity, including configured catalogues sharing a name."""
    state: dict[str, Any] = {
        "model_module": model_class.__module__,
        "model_class": model_class.__name__,
    }
    if (model_class.__module__, model_class.__name__) == _ICS_MODEL_KEY:
        state["catalogue_entries"] = list(getattr(model_class, "catalogue_entries"))
    return state


def _model_state(model: Any, *, parameters: list[Any] | None = None) -> dict[str, Any]:
    model_class = type(model)
    _MODEL_REGISTRY[(model_class.__module__, model_class.__name__)] = model_class
    params = _parameter_list(model) if parameters is None else parameters
    canonical_ids = [_canonical_parameter_id(parameter) for parameter in params]
    include_canonical_ids = (
        bool(params) and all(canonical_ids) and len(set(canonical_ids)) == len(canonical_ids)
    )
    states = []
    seen: set[str] = set()
    for index, parameter in enumerate(params):
        uid = _uid(parameter, "parameter")
        if uid in seen:
            raise SessionCodecError(f"duplicate parameter UID {uid!r}")
        seen.add(uid)
        # ``bounds`` hides stored endpoints while enforcement is disabled.
        bounds = [float(parameter.lb), float(parameter.ub)]
        if (
            math.isnan(bounds[0])
            or math.isnan(bounds[1])
            or bounds[0] == math.inf
            or bounds[1] == -math.inf
            or bounds[0] > bounds[1]
        ):
            raise SessionCodecError(f"parameter {uid!r} has invalid bounds")
        value = float(parameter.value)
        is_output = bool(getattr(parameter, "is_output", False))
        if not math.isfinite(value) and not is_output:
            raise SessionCodecError(f"parameter {uid!r} has non-finite value")
        try:
            error = float(getattr(parameter, "error_estimate", 0.0))
        except (TypeError, ValueError):
            error = None
        stored_error = getattr(parameter, "_error_estimate", None)
        if stored_error is not None:
            stored_error = float(stored_error)
            if not math.isfinite(stored_error):
                stored_error = None
        state = {
            "uid": uid,
            "native_uid": str(parameter._port.get_uid()),
            "index": index,
            "name": str(getattr(parameter, "name", "")),
            "value": value if math.isfinite(value) else None,
            "is_output": is_output,
            "error_estimate": error if error is not None and math.isfinite(error) else None,
            "stored_error_estimate": stored_error,
            "fixed": bool(getattr(parameter, "fixed", False)),
            "bounds": [
                float(v) if v is not None and math.isfinite(float(v)) else None for v in bounds
            ],
            "bounds_on": bool(getattr(parameter, "bounds_on", False)),
        }
        if include_canonical_ids:
            state["canonical_id"] = canonical_ids[index]
        states.append(state)
    get_state = getattr(model, "get_state", None)
    adapter_state = _json_value(get_state()) if callable(get_state) else {}
    if not isinstance(adapter_state, dict):
        raise SessionCodecError(f"model {model_class.__name__} adapter state must be a mapping")
    adapter_state = {
        key: value
        for key, value in adapter_state.items()
        if key not in {"model_module", "model_class", "parameters"}
    }
    return {
        "uid": _uid(model, "model"),
        **_model_identity(model_class),
        "parameters": states,
        "adapter_state": adapter_state,
    }


@_isolated
def capture_session(
    datasets: Iterable[Any],
    fits: Iterable[Any],
    *,
    experiments: dict[str, Any] | None = None,
    ui_state: dict[str, Any] | None = None,
    name: str = "untitled",
    resources: ResourceContext | None = None,
) -> Project:
    """Capture explicit runtime objects into a detached PTO payload."""
    curves: dict[str, Any] = {}
    layouts: list[dict[str, Any]] = []

    def register(curve: Any) -> str:
        uid = _uid(curve, "dataset")
        if uid in curves and curves[uid] is not curve:
            raise SessionCodecError(f"duplicate dataset UID {uid!r}")
        curves[uid] = curve
        return uid

    for item in datasets or []:
        members = (
            list(item)
            if isinstance(item, list) and not isinstance(item, (str, bytes, dict))
            else None
        )
        if members is None:
            layouts.append({"kind": "dataset", "dataset_uid": register(item)})
        else:
            if not members:
                raise SessionCodecError("dataset groups may not be empty")
            selected = int(getattr(item, "_current_dataset", 0))
            if not 0 <= selected < len(members):
                raise SessionCodecError("dataset group selection is out of range")
            layouts.append(
                {
                    "kind": "group",
                    "group_type": type(item).__name__,
                    "uid": _uid(item, "group"),
                    "name": str(getattr(item, "name", "")),
                    "dataset_uids": [register(v) for v in members],
                    "selected": selected,
                }
            )
    for fit in fits or []:
        for member in _local_fits(fit):
            if getattr(member, "data", None) is None:
                raise SessionCodecError(f"fit {_uid(member, 'fit')} has no curve data")
            register(member.data)

    # Reader dependencies are scientific data, not opaque runtime handles.
    pending = list(curves.values())
    for curve in pending:
        reader = getattr(curve, "data_reader", None)
        if (
            type(reader).__module__ == "chisurf.core.experiments.tcspc.simulator"
            and type(reader).__name__ == "TCSPCSimulatorSetup"
        ):
            irf = getattr(reader, "instrument_response_function", None)
            if irf is not None and hasattr(irf, "x") and hasattr(irf, "y"):
                if _uid(irf, "dataset") not in curves:
                    register(irf)
                    pending.append(irf)
    fit_uids: set[str] = set()
    member_uids: set[str] = set()
    parameter_uid_owners: dict[str, int] = {}
    parameter_refs: dict[int, tuple[str, str, str]] = {}
    fit_records: list[dict[str, Any]] = []
    live_models: dict[tuple[str, str], Any] = {}
    for fit in fits or []:
        members = _local_fits(fit)
        fit_uid = _uid(fit, "fit")
        if fit_uid in fit_uids:
            raise SessionCodecError(f"duplicate fit UID {fit_uid!r}")
        fit_uids.add(fit_uid)
        selected_fit = int(getattr(fit, "selected_fit_index", 0))
        if len(members) > 1 and not 0 <= selected_fit < len(members):
            raise SessionCodecError(f"fit group {fit_uid!r} selection is out of range")
        member_records = []
        for member in members:
            model = getattr(member, "model", None)
            if model is None:
                raise SessionCodecError(f"fit {_uid(member, 'fit')} has no model")
            member_uid = _uid(member, "fit")
            if member_uid in member_uids:
                raise SessionCodecError(f"duplicate fit-member UID {member_uid!r}")
            member_uids.add(member_uid)
            live_models[(fit_uid, member_uid)] = model
            state = _model_state(model)
            for parameter in _parameter_list(model):
                parameter_uid = _uid(parameter, "parameter")
                owner = parameter_uid_owners.get(parameter_uid)
                if owner is not None and owner != id(parameter):
                    raise SessionCodecError(f"duplicate parameter UID {parameter_uid!r}")
                parameter_uid_owners[parameter_uid] = id(parameter)
                parameter_refs[id(parameter)] = (fit_uid, member_uid, parameter_uid)
            dependencies = {}
            for label, owner, attr in (
                ("background", getattr(model, "generic", None), "background_curve"),
                ("irf", getattr(model, "convolve", None), "_irf"),
            ):
                curve = getattr(owner, attr, None) if owner is not None else None
                if curve is not None and hasattr(curve, "x"):
                    dependencies[label] = register(curve)
            member_records.append(
                {
                    "uid": member_uid,
                    "dataset_uid": register(member.data),
                    "fit_range": list(getattr(member, "fit_range", (0, 0))),
                    "mask": _json_value(getattr(member, "mask", None)),
                    "noise_model": str(getattr(member, "noise_model", "default")),
                    "model": state,
                    "dependencies": dependencies,
                }
            )
        record: dict[str, Any] = {
            "uid": fit_uid,
            "kind": "group" if hasattr(fit, "grouped_fits") else "fit",
            "name": str(getattr(fit, "name", "")),
            "selected": selected_fit,
            "members": member_records,
        }
        if record["kind"] == "group":
            from chisurf.core.models.global_model import GlobalFitModel

            aggregate = fit._model
            if (
                type(aggregate) is not GlobalFitModel
                or len(aggregate.fits) != len(members)
                or any(a is not b for a, b in zip(aggregate.fits, members))
            ):
                raise SessionCodecError("unsupported aggregate model or group membership")
            parameters = aggregate.global_parameters_all
            record["aggregate_model"] = _model_state(aggregate, parameters=parameters)
            live_models[(fit_uid, fit_uid)] = aggregate
            for parameter in parameters:
                parameter_uid = _uid(parameter, "parameter")
                if parameter_uid in parameter_uid_owners:
                    raise SessionCodecError(f"duplicate parameter UID {parameter_uid!r}")
                parameter_uid_owners[parameter_uid] = id(parameter)
                parameter_refs[id(parameter)] = (fit_uid, fit_uid, parameter_uid)
        fit_records.append(record)

    model_refs = {id(model): key for key, model in live_models.items()}
    for record in fit_records:
        for owner_uid, model_state in _saved_model_owners(record):
            model = live_models[(record["uid"], owner_uid)]
            get_references = getattr(model, "get_model_references", None)
            if callable(get_references):
                model_dependencies: dict[str, list[dict[str, str]]] = {}
                for role, input_models in get_references().items():
                    model_dependencies[role] = []
                    for source in input_models:
                        input_target = model_refs.get(id(source))
                        if input_target is None:
                            raise SessionCodecError(f"dangling model input for {owner_uid!r}")
                        model_dependencies[role].append(
                            {"fit_uid": input_target[0], "member_uid": input_target[1]}
                        )
                if model_dependencies:
                    model_state["model_dependencies"] = model_dependencies
            parameters = (
                model.global_parameters_all
                if owner_uid == record["uid"] and record["kind"] == "group"
                else _parameter_list(model)
            )
            for parameter_state, parameter in zip(model_state["parameters"], parameters):
                link = getattr(parameter, "link", None)
                if link is not None:
                    ref = parameter_refs.get(id(link))
                    if ref is None:
                        raise SessionCodecError(
                            f"dangling parameter link from {parameter_state['uid']!r}"
                        )
                    parameter_state["link_target"] = {
                        "fit_uid": ref[0],
                        "member_uid": ref[1],
                        "parameter_uid": ref[2],
                    }

    project = Project(
        name=name,
        project_format_version=5,
        datasets={uid: _curve_record(curve) for uid, curve in curves.items()},
        fits=fit_records,
        ui_state={**_json_value(ui_state or {}), "dataset_layout": layouts},
        experiments=_json_value(experiments or {}),
    )
    contexts = [getattr(curve, "_project_resources", None) for curve in curves.values()]
    if resources is not None:
        contexts.append(resources)
    entries: dict[str, bytes] = {}
    sources: dict[str, bytes] = {}
    for context in contexts:
        if context is None:
            continue
        if not isinstance(context, ResourceContext):
            raise SessionCodecError("resources require an owned ResourceContext")
        for target, incoming in ((entries, context.entries), (sources, context.sources)):
            for label, content in incoming.items():
                if label in target and target[label] != content:
                    raise SessionCodecError(f"conflicting resource label {label!r}")
                target[label] = content
    project.resources = ResourceContext(entries, sources)
    project.metadata["session_codec"] = "detached-v2"
    detached = restore_session(project)
    restored_models = {
        (str(record["uid"]), str(saved["uid"])): local.model
        for record, restored_fit in zip(fit_records, detached.fits)
        for saved, local in zip(record["members"], _local_fits(restored_fit))
    }
    for record, fit in zip(fit_records, detached.fits):
        if record["kind"] == "group":
            restored_models[(record["uid"], record["uid"])] = fit._model
    for key, live in live_models.items():
        try:
            live.update()
            restored_model = restored_models[key]
            restored_model.update()
        except Exception as exc:
            raise SessionCodecError(
                f"model {key[1]!r} cannot be reconstructively validated"
            ) from exc
        if hasattr(live, "y"):
            expected = np.asarray(live.y)
            actual = np.asarray(restored_model.y)
            if (
                expected.shape != actual.shape
                or expected.dtype != actual.dtype
                or not np.allclose(expected, actual, rtol=1e-12, atol=1e-12, equal_nan=False)
            ):
                raise SessionCodecError(f"model {key[1]!r} prediction changed after reconstruction")
        if _model_state(live)["adapter_state"] != _model_state(restored_model)["adapter_state"]:
            raise SessionCodecError(f"model {key[1]!r} state changed after reconstruction")
    return project


def _resolve_model(state: dict[str, Any]) -> type:
    from chisurf.core.models.model import Model

    try:
        key = (str(state["model_module"]), str(state["model_class"]))
    except KeyError as exc:
        raise SessionCodecError("saved model identity is incomplete") from exc
    if key == _ICS_MODEL_KEY:
        entries = state.get("catalogue_entries")
        if not isinstance(entries, list) or any(not isinstance(v, str) for v in entries):
            raise SessionCodecError("ICS model identity requires a catalogue mode")
        exported_name = _ICS_MODEL_MODES.get(tuple(entries))
        if exported_name is None:
            raise SessionCodecError("untrusted ICS catalogue mode")
        return getattr(importlib.import_module(_ICS_MODEL_KEY[0]), exported_name)
    candidate = _MODEL_REGISTRY.get(key)
    if candidate is None:
        module_name, class_name = key
        if module_name == "chisurf.core.models.description" and class_name.startswith(
            "DescriptionModel_"
        ):
            import IMP.bff as bff

            family = class_name.removeprefix("DescriptionModel_")
            if family not in bff.ModelSearchSpec.get_available_names():
                raise SessionCodecError(
                    f"saved model {module_name}.{class_name} is not registered or trusted"
                )
            from chisurf.core.models.description import for_family

            candidate = for_family(family)
        elif key in _BUILTIN_MODEL_KEYS or key in _CATALOGUE_MODELS:
            try:
                candidate = getattr(
                    importlib.import_module(module_name), _CATALOGUE_MODELS.get(key, class_name)
                )
            except (ImportError, AttributeError) as exc:
                raise SessionCodecError(
                    f"saved model cannot be imported: {module_name}.{class_name}"
                ) from exc
        else:
            raise SessionCodecError(
                f"saved model {module_name}.{class_name} is not registered or trusted"
            )
    if not isinstance(candidate, type) or not issubclass(candidate, Model):
        raise SessionCodecError(f"saved model {candidate!r} is not a ChiSurf Model subclass")
    return candidate


def _saved_model_owners(record: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Enumerate member models and the aggregate's own global parameters."""
    owners = [(member["uid"], member.get("model")) for member in record["members"]]
    if record["kind"] == "group":
        state = record.get("aggregate_model")
        if (
            not isinstance(state, dict)
            or (state.get("model_module"), state.get("model_class"))
            != ("chisurf.core.models.global_model.globalfit", "GlobalFitModel")
            or not isinstance(state.get("parameters"), list)
        ):
            raise SessionCodecError("invalid or missing aggregate model state")
        declared = {
            "global_parameters": [parameter.get("name") for parameter in state["parameters"]]
        }
        if state.get("adapter_state") not in ({}, declared):
            raise SessionCodecError("invalid aggregate global parameter topology")
        owners.append((record["uid"], state))
    return owners


def _validate_project_graph(project: Project) -> None:
    """Validate archive-controlled identity and reference data before construction."""
    dataset_uids = set(project.datasets)
    fit_uids: set[str] = set()
    member_uids: set[str] = set()
    parameter_keys: set[tuple[str, str, str]] = set()
    parameter_uids: set[str] = set()
    native_uids: set[str] = set()
    links: dict[tuple[str, str, str], tuple[str, str, str]] = {}
    for uid, dataset in project.datasets.items():
        if (
            not isinstance(dataset, dict)
            or dataset.get("uid") != uid
            or dataset.get("kind") not in {"curve", "structure"}
        ):
            raise SessionCodecError(f"invalid dataset UID/record {uid!r}")
        metadata = _restore_scientific_value(dataset.get("metadata"))
        if not isinstance(metadata, dict):
            raise SessionCodecError(f"invalid dataset metadata for {uid!r}")
        if "unique_identifier" in metadata and metadata["unique_identifier"] != uid:
            raise SessionCodecError(f"dataset metadata contradicts UID {uid!r}")
    for record in project.fits:
        if not isinstance(record, dict):
            raise SessionCodecError("invalid fit record")
        fit_uid = str(record.get("uid", ""))
        if not fit_uid or fit_uid in fit_uids:
            raise SessionCodecError(f"duplicate fit UID {fit_uid!r}")
        fit_uids.add(fit_uid)
        members = record.get("members")
        if not isinstance(members, list) or not members:
            raise SessionCodecError(f"fit {fit_uid!r} has no members")
        if record.get("kind") not in {"fit", "group"}:
            raise SessionCodecError("invalid fit kind")
        for member in members:
            if not isinstance(member, dict):
                raise SessionCodecError(f"fit {fit_uid!r} contains invalid member")
            member_uid = str(member.get("uid", ""))
            if not member_uid or member_uid in member_uids:
                raise SessionCodecError(f"duplicate fit-member UID {member_uid!r}")
            member_uids.add(member_uid)
            dataset_uid = str(member.get("dataset_uid", ""))
            if dataset_uid not in dataset_uids:
                raise SessionCodecError(f"fit {fit_uid!r} references missing dataset")
            size = len(
                project.datasets[dataset_uid].get("arrays", {}).get("y", {}).get("values", [])
            )
            fit_range = member.get("fit_range")
            if (
                not isinstance(fit_range, list)
                or len(fit_range) != 2
                or any(isinstance(v, bool) or not isinstance(v, int) for v in fit_range)
                or not 0 <= fit_range[0] <= fit_range[1] <= size
            ):
                raise SessionCodecError(f"invalid fit range for {member_uid!r}")
            mask = member.get("mask")
            if mask is not None:
                try:
                    mask_array = np.asarray(mask)
                except Exception as exc:
                    raise SessionCodecError(f"invalid fit mask for {member_uid!r}") from exc
                if (
                    mask_array.ndim != 1
                    or len(mask_array) != size
                    or not np.issubdtype(mask_array.dtype, np.number)
                    or not np.all(np.isfinite(mask_array))
                ):
                    raise SessionCodecError(f"invalid fit mask for {member_uid!r}")
            if member.get("noise_model") not in {"default", "poisson"}:
                raise SessionCodecError(f"invalid noise model for {member_uid!r}")
        for owner_uid, model in _saved_model_owners(record):
            if not isinstance(model, dict) or not isinstance(model.get("parameters"), list):
                raise SessionCodecError(f"invalid model record for {owner_uid!r}")
            seen_here: set[str] = set()
            canonical_ids_here: set[str] = set()
            for parameter in model["parameters"]:
                uid = str(parameter.get("uid", ""))
                if not uid or uid in seen_here or uid in parameter_uids:
                    raise SessionCodecError(f"duplicate parameter UID {uid!r}")
                seen_here.add(uid)
                parameter_uids.add(uid)
                canonical_id = parameter.get("canonical_id")
                if canonical_id is not None:
                    if (
                        not isinstance(canonical_id, str)
                        or not canonical_id
                        or canonical_id in canonical_ids_here
                    ):
                        raise SessionCodecError(
                            f"duplicate or invalid canonical parameter ID {canonical_id!r}"
                        )
                    canonical_ids_here.add(canonical_id)
                native_uid = parameter.get("native_uid")
                if native_uid is not None:
                    if (
                        not isinstance(native_uid, str)
                        or not native_uid
                        or native_uid in native_uids
                    ):
                        raise SessionCodecError(
                            f"duplicate or invalid native parameter UID {native_uid!r}"
                        )
                    native_uids.add(native_uid)
                bounds = parameter.get("bounds")
                if not isinstance(bounds, list) or len(bounds) != 2:
                    raise SessionCodecError(f"invalid parameter bounds for {uid!r}")
                _decode_bounds(bounds, uid)
                value = parameter.get("value")
                if value is None:
                    if not parameter.get("is_output", False):
                        raise SessionCodecError(f"parameter {uid!r} has incomplete value")
                elif (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                ):
                    raise SessionCodecError(f"parameter {uid!r} has invalid value")
                key = (fit_uid, owner_uid, uid)
                if key in parameter_keys:
                    raise SessionCodecError(f"duplicate parameter UID {uid!r}")
                parameter_keys.add(key)
                target = parameter.get("link_target")
                if target is not None:
                    if not isinstance(target, dict):
                        raise SessionCodecError(f"invalid parameter link from {uid!r}")
                    links[key] = (
                        str(target.get("fit_uid", "")),
                        str(target.get("member_uid", "")),
                        str(target.get("parameter_uid", "")),
                    )
        if record["kind"] == "fit" and len(members) != 1:
            raise SessionCodecError(f"fit {fit_uid!r} has invalid member count")
    for source, target in links.items():
        if target not in parameter_keys:
            raise SessionCodecError(f"unresolved parameter link {target!r}")
        visited = {source}
        cursor = target
        while cursor in links:
            if cursor in visited:
                raise SessionCodecError("parameter link cycle detected")
            visited.add(cursor)
            cursor = links[cursor]

    _model_reference_order(project)

    ui_state = project.ui_state
    if (dataset_uids or project.fits) and (
        not isinstance(ui_state, dict) or "dataset_layout" not in ui_state
    ):
        raise SessionCodecError("dataset layout is missing")
    layouts = ui_state.get("dataset_layout", []) if isinstance(ui_state, dict) else []
    if not isinstance(layouts, list) or (dataset_uids and not layouts):
        raise SessionCodecError("dataset layout is invalid or empty")
    group_uids: set[str] = set()
    for layout in layouts:
        if not isinstance(layout, dict) or layout.get("kind") not in {"dataset", "group"}:
            raise SessionCodecError("invalid dataset layout record")
        if layout["kind"] == "dataset":
            if layout.get("dataset_uid") not in dataset_uids:
                raise SessionCodecError("dataset layout references missing dataset")
        else:
            uid = layout.get("uid")
            if not isinstance(uid, str) or not uid or uid in group_uids or uid in dataset_uids:
                raise SessionCodecError(f"duplicate dataset-group UID {uid!r}")
            group_uids.add(uid)
            uids = layout.get("dataset_uids")
            if (
                not isinstance(uids, list)
                or not uids
                or any(uid not in dataset_uids for uid in uids)
            ):
                raise SessionCodecError("invalid dataset group layout")
            if layout.get("group_type") not in {
                "DataGroup",
                "DataCurveGroup",
                "ExperimentDataGroup",
                "ExperimentDataCurveGroup",
            }:
                raise SessionCodecError("invalid dataset group type")
            selected = layout.get("selected")
            if (
                isinstance(selected, bool)
                or not isinstance(selected, int)
                or not 0 <= selected < len(uids)
            ):
                raise SessionCodecError("invalid dataset group layout")


def _decode_bounds(bounds: Any, uid: str) -> tuple[float, float]:
    """Decode each JSON-safe infinite endpoint without losing a finite limit."""
    if not isinstance(bounds, list) or len(bounds) != 2:
        raise SessionCodecError(f"invalid parameter bounds for {uid!r}")
    for value in bounds:
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise SessionCodecError(f"invalid parameter bounds for {uid!r}")
    lower = -math.inf if bounds[0] is None else float(bounds[0])
    upper = math.inf if bounds[1] is None else float(bounds[1])
    if lower > upper:
        raise SessionCodecError(f"invalid parameter bounds for {uid!r}")
    return lower, upper


def _model_reference_order(project: Project) -> list[tuple[str, str]]:
    """Validate exact model input roles and return producer-before-consumer order."""
    states = {
        (record["uid"], owner): state
        for record in project.fits
        for owner, state in _saved_model_owners(record)
    }
    ordered, visiting, visited = [], set(), set()

    def visit(key):
        if key in visiting:
            raise SessionCodecError("model dependency cycle detected")
        if key in visited:
            return
        visiting.add(key)
        dependencies = states[key].get("model_dependencies", {})
        if not isinstance(dependencies, dict):
            raise SessionCodecError("invalid model dependencies")
        for role, inputs in dependencies.items():
            if not isinstance(role, str) or not role or not isinstance(inputs, list):
                raise SessionCodecError("invalid model input role")
            for ref in inputs:
                if (
                    not isinstance(ref, dict)
                    or set(ref) != {"fit_uid", "member_uid"}
                    or any(not isinstance(v, str) or not v for v in ref.values())
                ):
                    raise SessionCodecError("invalid model input descriptor")
                target = (ref["fit_uid"], ref["member_uid"])
                if target not in states:
                    raise SessionCodecError(f"dangling model input {target!r}")
                visit(target)
        visiting.remove(key)
        visited.add(key)
        ordered.append(key)

    for key in states:
        visit(key)
    return ordered


def _parameter_restore_pairs(
    model: Any,
    params: list[Any],
    states: list[dict[str, Any]],
) -> list[tuple[Any, dict[str, Any]]]:
    """Match archive records to live ports by declared semantic identity.

    Positional matching remains the fail-closed fallback for ordinary models.
    A snapshot that advertises canonical identities must advertise them for all
    ports and match the rebuilt model exactly; falling back from a partial or
    incompatible canonical mapping would silently write scientific values to
    the wrong ports.
    """
    has_canonical_ids = ["canonical_id" in state for state in states]
    if not any(has_canonical_ids):
        return list(zip(params, states))
    if not all(has_canonical_ids):
        raise SessionCodecError("model snapshot has incomplete canonical parameter identities")

    saved_ids = [state["canonical_id"] for state in states]
    if any(
        not isinstance(canonical_id, str) or not canonical_id for canonical_id in saved_ids
    ) or len(set(saved_ids)) != len(saved_ids):
        raise SessionCodecError("model snapshot has invalid canonical parameter identities")
    current_ids = [_canonical_parameter_id(parameter) for parameter in params]
    if any(canonical_id is None for canonical_id in current_ids) or len(set(current_ids)) != len(
        current_ids
    ):
        raise SessionCodecError(
            f"model {type(model).__name__} cannot restore canonical parameter identities"
        )
    if set(saved_ids) != set(current_ids):
        raise SessionCodecError(
            f"model {type(model).__name__} canonical parameter identities changed"
        )
    by_canonical_id = {
        canonical_id: parameter for canonical_id, parameter in zip(current_ids, params)
    }
    return [(by_canonical_id[state["canonical_id"]], state) for state in states]


def _apply_scalar_state(
    model: Any, states: list[dict[str, Any]], *, parameters: list[Any] | None = None
) -> dict[str, Any]:
    params = _parameter_list(model) if parameters is None else parameters
    if len(params) != len(states):
        raise SessionCodecError(
            f"model {type(model).__name__} parameter count changed ({len(params)} != {len(states)})"
        )
    by_uid = {}
    for parameter, state in _parameter_restore_pairs(model, params, states):
        if "canonical_id" not in state and str(getattr(parameter, "name", "")) != str(
            state.get("name", "")
        ):
            raise SessionCodecError(
                f"model parameter order/name changed at index {state.get('index')}"
            )
        parameter.unique_identifier = str(state["uid"])
        if state.get("native_uid"):
            parameter._port.set_uid(str(state["native_uid"]))
        parameter.bounds = _decode_bounds(state.get("bounds"), str(state["uid"]))
        parameter.bounds_on = bool(state.get("bounds_on", False))
        fixed = bool(state.get("fixed", False))
        # Description parameters may be fixed by their inactive topology. An
        # unnecessary setter call turns that into an explicit scientific lock.
        restore_link_fixed = getattr(model, "restore_session_link_fixed", None)
        if state.get("link_target") and callable(restore_link_fixed):
            restore_link_fixed(parameter, fixed)
        elif bool(parameter.fixed) != fixed:
            parameter.fixed = fixed
        if bool(state.get("is_output", False)) != bool(getattr(parameter, "is_output", False)):
            raise SessionCodecError(f"parameter {state['uid']!r} output role changed")
        if state.get("value") is not None:
            parameter.value = float(state["value"])
        if "stored_error_estimate" in state:
            parameter.error_estimate = state["stored_error_estimate"]
        elif state.get("error_estimate") is not None:
            parameter.error_estimate = float(state["error_estimate"])
        by_uid[str(state["uid"])] = parameter
    return by_uid


def _construct_saved_model(cls: type, fit: Any, state: dict[str, Any]) -> Any:
    """Construct trusted transforms directly on their saved shipped definition."""
    from chisurf.core.models.parameter_transform.model import ParameterTransformModel

    if cls is ParameterTransformModel:
        return cls.from_session_state(fit, state["adapter_state"])
    return cls(fit)


@_isolated
def restore_session(
    project: Project, *, experiments: dict[str, Any] | None = None
) -> RestoredSession:
    """Build every object detached, validate references, and return atomically."""
    if not isinstance(project, Project) or project.project_format_version != 5:
        raise SessionCodecError("restore requires project format v5")
    _validate_project_graph(project)
    from chisurf.core.data import (
        DataCurve,
        DataCurveGroup,
        DataGroup,
        ExperimentDataCurveGroup,
        ExperimentDataGroup,
    )
    from chisurf.core.experiments.core.experiment import Experiment
    from chisurf.core.fitting.fit import Fit, FitGroup

    datasets: dict[str, Any] = {}
    reader_cache: dict[str, Any] = {}
    experiment_cache: dict[str, Any] = {}
    for uid, record in project.datasets.items():
        if (
            not isinstance(record, dict)
            or uid != record.get("uid")
            or record.get("kind") not in {"curve", "structure"}
        ):
            raise SessionCodecError(f"invalid dataset UID/record {uid!r}")
        try:
            arrays = {
                key: np.asarray(value["values"], dtype=value.get("dtype"))
                for key, value in record["arrays"].items()
            }
            expected_arrays = (
                set() if record["kind"] == "structure" else {"x", "y", "ex", "ey", "mask"}
            )
            if set(arrays) != expected_arrays or any(
                a.ndim != 1 or not np.issubdtype(a.dtype, np.number) or not np.all(np.isfinite(a))
                for a in arrays.values()
            ):
                raise ValueError("arrays must be finite numeric vectors")
            if arrays and len({len(a) for a in arrays.values()}) != 1:
                raise ValueError("arrays have different lengths")
            experiment_state = record.get("experiment")
            experiment = None
            if experiment_state is not None:
                if (
                    not isinstance(experiment_state, dict)
                    or experiment_state.get("kind") != "experiment"
                ):
                    raise ValueError("unsupported experiment descriptor")
                key = (
                    str(experiment_state.get("module", "")),
                    str(experiment_state.get("class", "")),
                )
                experiment_class = _EXPERIMENT_REGISTRY.get(key)
                if experiment_class is None:
                    if key == (Experiment.__module__, Experiment.__name__):
                        experiment_class = Experiment
                    else:
                        raise ValueError(f"experiment {key[0]}.{key[1]} is not registered")
                experiment_uid = experiment_state.get("uid")
                if not isinstance(experiment_uid, str) or not experiment_uid:
                    raise ValueError("experiment UID is missing")
                if experiment_uid in experiment_cache:
                    experiment, saved_state = experiment_cache[experiment_uid]
                    if saved_state != experiment_state:
                        raise ValueError("inconsistent experiment identity")
                else:
                    try:
                        experiment = experiment_class()
                    except Exception as exc:
                        raise ValueError(f"cannot construct experiment {key[0]}.{key[1]}") from exc
                    experiment.name = str(experiment_state.get("name", ""))
                    experiment.hidden = bool(experiment_state.get("hidden", False))
                    experiment.unique_identifier = experiment_uid
                    model_states = experiment_state.get("models", [])
                    if not isinstance(model_states, list) or any(
                        not isinstance(s, dict) for s in model_states
                    ):
                        raise ValueError("invalid experiment model registry")
                    for model_state in model_states:
                        experiment.add_model_class(_resolve_model(model_state))
                    experiment_cache[experiment_uid] = (experiment, copy.deepcopy(experiment_state))
            reader = _restore_reader(record.get("reader"), experiment, reader_cache)
            if record["kind"] == "structure":
                from chisurf.core.models.structure.snapshot import restore_structure

                curve = restore_structure(record["structure"])
                if curve is None or str(curve.unique_identifier) != uid:
                    raise ValueError("structure identity contradicts dataset UID")
                curve.data_reader = reader
                curve.experiment = experiment
            else:
                curve = DataCurve(
                    x=arrays["x"],
                    y=arrays["y"],
                    ex=arrays["ex"],
                    ey=arrays["ey"],
                    mask=arrays["mask"],
                    data_reader=reader,
                    experiment=experiment,
                    name=record.get("name", ""),
                    unique_identifier=uid,
                )
            curve.filename = record.get("filename", "")
            curve.meta_data.update(_restore_scientific_value(record.get("metadata") or {}))
            auxiliary = record.get("auxiliary", {})
            if not isinstance(auxiliary, dict) or set(auxiliary) - {"pda", "pda3c", "mfd"}:
                raise ValueError("unsupported dataset auxiliary field")
            for field, value in auxiliary.items():
                payload = _restore_scientific_value(value)
                if field == "mfd":
                    from chisurf.core.fluorescence.mfd.fit import MfdData

                    payload = MfdData.from_session_state(payload)
                setattr(curve, field, payload)
            curve._project_resources = project.resources
            if reader is not None:
                reader._project_resources = project.resources
        except Exception as exc:
            raise SessionCodecError(f"cannot restore dataset {uid!r}: {exc}") from exc
        datasets[uid] = curve

    for reader, reader_state in reader_cache.values():
        for field, dependency_uid in reader_state.get("dependencies", {}).items():
            if dependency_uid not in datasets:
                raise SessionCodecError(f"missing reader dependency {dependency_uid!r}")
            setattr(reader, field, datasets[dependency_uid])

    restored_fits: list[Any] = []
    refs: dict[tuple[str, str, str], Any] = {}
    pending_links = []
    pending_models = {}
    # A FitGroup constructs interactive placeholder Fits with ``fit.group``
    # already populated.  During restore, that runtime context must not be
    # visible while a model constructor or its canonical adapter state runs:
    # model families may use it to choose a UI/default topology.  Preserve and
    # reattach it after all canonical state and link restoration is complete.
    deferred_group_contexts: list[tuple[Any, Any]] = []
    missing_group_context = object()
    for record in project.fits:
        members = record.get("members")
        if not isinstance(members, list) or not members:
            raise SessionCodecError(f"fit {record.get('uid')!r} has no members")
        classes = [_resolve_model(member["model"]) for member in members]
        try:
            curves = [datasets[member["dataset_uid"]] for member in members]
        except KeyError as exc:
            raise SessionCodecError(
                f"fit {record.get('uid')!r} references missing dataset"
            ) from exc
        try:
            if record.get("kind") == "group":
                fit = FitGroup(DataCurveGroup(curves))
                for local, cls, saved in zip(fit.grouped_fits, classes, members):
                    # FitGroup's placeholder is an interactive construction:
                    # its group-position policy is allowed to set defaults.
                    # A canonical snapshot must instead construct its model
                    # before that policy can affect topology or adapter state.
                    group_context = local.__dict__.pop("group", missing_group_context)
                    try:
                        local._model = _construct_saved_model(cls, local, saved["model"])
                    except Exception:
                        if group_context is not missing_group_context:
                            local.group = group_context
                        raise
                    if group_context is not missing_group_context:
                        deferred_group_contexts.append((local, group_context))
                fit.unique_identifier = str(record["uid"])
                fit.name = str(record.get("name", ""))
                from chisurf.core.models.global_model import GlobalFitModel

                try:
                    fit._model = GlobalFitModel(fit=fit, fits=fit.grouped_fits)
                except Exception as exc:
                    raise SessionCodecError(f"cannot construct group model: {exc}") from exc
            else:
                # Interactive attachment evaluates immediately. Restoration
                # must first restore topology, ranges, inputs and port state.
                fit = Fit(data=curves[0], noise_model=members[0]["noise_model"])
                fit._model = _construct_saved_model(classes[0], fit, members[0]["model"])
                fit.unique_identifier = str(record["uid"])
                fit.name = str(record.get("name", ""))
        except SessionCodecError:
            raise
        except Exception as exc:
            raise SessionCodecError(f"cannot construct fit {record.get('uid')!r}: {exc}") from exc
        if record.get("kind") == "group":
            selected = int(record.get("selected", 0))
            if not 0 <= selected < len(members):
                raise SessionCodecError(f"fit group {record['uid']!r} selection is out of range")
            fit.selected_fit = selected
        local_members = _local_fits(fit)
        if len(local_members) != len(members):
            raise SessionCodecError(f"fit group {record['uid']!r} member count changed")
        for local, saved in zip(local_members, members):
            pending_models[(str(record["uid"]), str(saved["uid"]))] = (local, saved)
        if record["kind"] == "group":
            from chisurf.core.fitting.parameter import FittingParameter

            aggregate_state = record["aggregate_model"]
            if aggregate_state.get("uid"):
                fit._model.unique_identifier = str(aggregate_state["uid"])
            if _resolve_model(aggregate_state) is not GlobalFitModel:
                raise SessionCodecError("unsupported aggregate model")
            for state in aggregate_state["parameters"]:
                fit._model.append_global_parameter(FittingParameter(name=state["name"]))
            params = _apply_scalar_state(
                fit._model,
                aggregate_state["parameters"],
                parameters=fit._model.global_parameters_all,
            )
            for state in aggregate_state["parameters"]:
                parameter = params[state["uid"]]
                refs[(record["uid"], record["uid"], state["uid"])] = parameter
                if state.get("link_target"):
                    pending_links.append((parameter, state["link_target"]))
        restored_fits.append(fit)

    for key in _model_reference_order(project):
        if key not in pending_models:
            continue
        fit_uid = key[0]
        local, saved = pending_models[key]
        local.unique_identifier = str(saved["uid"])
        local.noise_model = str(saved["noise_model"])
        try:
            # Establish the scientific window before building native graphs or
            # routing linked ports; a later rebind would rebuild those graphs.
            local.fit_range = tuple(int(v) for v in saved.get("fit_range", (0, 0)))
            local._xmin, local._xmax = saved["fit_range"]
            local.mask = None if saved.get("mask") is None else np.asarray(saved["mask"])
        except Exception as exc:
            raise SessionCodecError(f"cannot restore range/mask for {saved['uid']!r}") from exc
        model_state = saved["model"]
        if model_state.get("uid"):
            local.model.unique_identifier = str(model_state["uid"])
        dependencies = model_state.get("model_dependencies", {})
        if dependencies:
            bind = getattr(local.model, "set_model_references", None)
            if not callable(bind):
                raise SessionCodecError("model cannot bind its saved inputs")
            bind(
                {
                    role: [
                        pending_models[(ref["fit_uid"], ref["member_uid"])][0].model
                        for ref in inputs
                    ]
                    for role, inputs in dependencies.items()
                }
            )
        setter = getattr(local.model, "set_state", None)
        if callable(setter):
            try:
                setter(model_state["adapter_state"])
            except Exception as exc:
                raise SessionCodecError(f"cannot restore model state for {saved['uid']!r}") from exc
        local_params = _apply_scalar_state(local.model, model_state.get("parameters", []))
        for state in model_state.get("parameters", []):
            refs[(fit_uid, str(saved["uid"]), str(state["uid"]))] = local_params[str(state["uid"])]
            if state.get("link_target"):
                pending_links.append((local_params[str(state["uid"])], state["link_target"]))
        for label, dep_uid in (saved.get("dependencies") or {}).items():
            if label not in {"background", "irf"}:
                raise SessionCodecError(f"unsupported model dependency {label!r}")
            dependency = datasets.get(dep_uid)
            if dependency is None:
                raise SessionCodecError(f"missing {label} dependency {dep_uid!r}")
            owner, attr = (
                (getattr(local.model, "generic", None), "background_curve")
                if label == "background"
                else (getattr(local.model, "convolve", None), "_irf")
            )
            if owner is None:
                raise SessionCodecError(
                    f"model {type(local.model).__name__} cannot accept {label} dependency"
                )
            setattr(owner, attr, dependency)

    for parameter, target in pending_links:
        link_key = (
            str(target.get("fit_uid")),
            str(target.get("member_uid")),
            str(target.get("parameter_uid")),
        )
        target_param = refs.get(link_key)
        if target_param is None:
            raise SessionCodecError(f"unresolved parameter link {link_key!r}")
        try:
            parameter.link = target_param
        except Exception as exc:
            raise SessionCodecError("parameter link cycle detected") from exc

    # Adapter state and links now define the scientific model.  Restore the
    # runtime grouping before evaluation, without rerunning its interactive
    # constructor-time defaulting policy.
    for local, group_context in deferred_group_contexts:
        local.group = group_context

    for fit in restored_fits:
        for local in _local_fits(fit):
            try:
                local.model.update()
            except Exception as exc:
                raise SessionCodecError(
                    f"cannot update restored model {local.unique_identifier!r}"
                ) from exc

    output = []
    for layout in (project.ui_state or {}).get("dataset_layout", []):
        if layout.get("kind") == "dataset":
            if layout["dataset_uid"] not in datasets:
                raise SessionCodecError(
                    f"dataset layout references missing {layout['dataset_uid']!r}"
                )
            output.append(datasets[layout["dataset_uid"]])
        elif layout.get("kind") == "group":
            members = [datasets[uid] for uid in layout["dataset_uids"]]
            selected = int(layout.get("selected", 0))
            if not members or not 0 <= selected < len(members):
                raise SessionCodecError("invalid dataset group layout")
            group_class = {
                "DataGroup": DataGroup,
                "DataCurveGroup": DataCurveGroup,
                "ExperimentDataGroup": ExperimentDataGroup,
                "ExperimentDataCurveGroup": ExperimentDataCurveGroup,
            }[layout["group_type"]]
            group = group_class(members, unique_identifier=layout.get("uid"))
            group.name = layout.get("name", "")
            group.current_dataset = selected
            output.append(group)
    return RestoredSession(
        output,
        restored_fits,
        copy.deepcopy(project.ui_state or {}),
        copy.deepcopy(experiments if experiments is not None else project.experiments or {}),
        resources=project.resources,
    )
