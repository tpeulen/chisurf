from __future__ import annotations

import gc
import hashlib
import importlib
import inspect
import json
import os
import pathlib
import shutil
import tempfile

import numpy as np

import chisurf as cs
import chisurf.core.base
import chisurf.core.data
import chisurf.core.fitting
from chisurf import typing
from chisurf.core.actions import get_action_catalog, record_action
from chisurf.core.experiments.core.reader import ExperimentReader
from chisurf.core.experiments.core.serialize import decode_array, encode_array
from chisurf.core.project import Project as CSProject
from chisurf.core.project import ProjectArchive, capture_session, restore_session
from chisurf.core.project import fit_state as project_fit_state
from chisurf.core.project import load_project as project_load_json
from chisurf.core.project.archive import DATA_DIR, PROJECT_ARCHIVE_SUFFIX, PROJECT_JSON
from chisurf.core.project.storage import load_file, save_file
from chisurf.emtk.datasets import (
    _BULK_PDA_KEYS as _BULK_PDA_KEYS,
)
from chisurf.emtk.datasets import (
    _apply_anisotropy_calibration_to_fit as _apply_anisotropy_calibration_to_fit,
)
from chisurf.emtk.datasets import (
    _apply_g_factor_to_fit as _apply_g_factor_to_fit,
)
from chisurf.emtk.datasets import (
    _attach_tttr_header as _attach_tttr_header,
)
from chisurf.emtk.datasets import (
    _auto_link_non_nuisance_group_parameters as _auto_link_non_nuisance_group_parameters,
)
from chisurf.emtk.datasets import (
    _coerce_finite_float as _coerce_finite_float,
)
from chisurf.emtk.datasets import (
    _collect_group_nuisance_parameter_names as _collect_group_nuisance_parameter_names,
)
from chisurf.emtk.datasets import (
    _flatten_metadata as _flatten_metadata,
)
from chisurf.emtk.datasets import (
    _iter_group_members as _iter_group_members,
)
from chisurf.emtk.datasets import (
    _resolve_dataset_anisotropy_calibration as _resolve_dataset_anisotropy_calibration,
)
from chisurf.emtk.datasets import (
    _resolve_dataset_g_factor as _resolve_dataset_g_factor,
)


def _call_gui_reinitialize(
    gui: typing.Any,
    show_confirmation: bool = True,
    show_success: bool = True,
) -> None:
    """Call the GUI reinitializer with the requested dialog behavior.

    Parameters
    ----------
    gui : object
        Main window object that may provide ``reinitialize`` or ``onCloseAllFits``.
    show_confirmation : bool, optional
        Whether the GUI reinitializer should ask for confirmation.
    show_success : bool, optional
        Whether the GUI reinitializer should show a completion message.
    """
    reinit = getattr(gui, "reinitialize", None)
    if callable(reinit):
        try:
            signature = inspect.signature(reinit)
            accepts_kwargs = any(
                parameter.kind == inspect.Parameter.VAR_KEYWORD
                for parameter in signature.parameters.values()
            )
            accepts_dialog_flags = accepts_kwargs or {
                "show_confirmation",
                "show_success",
            }.issubset(signature.parameters)
        except (TypeError, ValueError):
            accepts_dialog_flags = False

        if accepts_dialog_flags:
            reinit(show_confirmation=show_confirmation, show_success=show_success)
        else:
            reinit()
        return

    try:
        gui.onCloseAllFits()
    except Exception:
        pass


HISTORY_FILENAME = "history.jsonl"


def _save_history_snapshot(
    project_dir: typing.Union[str, pathlib.Path],
) -> typing.Optional[pathlib.Path]:
    try:
        history_obj = getattr(cs, "history", None)
        if history_obj is None or not hasattr(history_obj, "save_jsonl"):
            return None
        history_path = pathlib.Path(project_dir).resolve() / HISTORY_FILENAME
        return history_obj.save_jsonl(history_path)
    except Exception:
        return None


def _load_history_snapshot(
    project_dir: typing.Union[str, pathlib.Path],
    replace: bool = True,
) -> bool:
    try:
        history_obj = getattr(cs, "history", None)
        if history_obj is None or not hasattr(history_obj, "load_jsonl"):
            return False
        history_path = pathlib.Path(project_dir).resolve() / HISTORY_FILENAME
        if not history_path.exists():
            return False
        history_obj.load_jsonl(history_path, replace=replace)
        return True
    except Exception:
        return False


def _refresh_history_browser() -> None:
    try:
        gui = getattr(cs, "cs", None)
        browser = getattr(gui, "historyBrowser", None)
        if browser is not None and hasattr(browser, "reload"):
            browser.reload()
    except Exception:
        pass


def _record_history(
    action_type: str,
    summary: str,
    payload: typing.Optional[typing.Dict[str, typing.Any]] = None,
    source_uid: str = "",
    target_uid: str = "",
) -> None:
    try:
        record_action(
            action_type=action_type,
            summary=summary,
            payload=payload,
            source_uid=source_uid or "",
            target_uid=target_uid or "",
        )
        return
    except Exception:
        pass


def _history_event_count() -> int:
    try:
        history_obj = getattr(cs, "history", None)
        if history_obj is not None and hasattr(history_obj, "list_events"):
            return int(len(history_obj.list_events()))
    except Exception:
        pass
    return 0


def _project_archive_path(target_path: str, project_name: str) -> tuple[pathlib.Path, str]:
    """Return the ``.cs.pto`` save path and canonical project name."""
    path = pathlib.Path(target_path)
    if str(path).lower().endswith(PROJECT_ARCHIVE_SUFFIX):
        return path, path.stem or project_name
    return path / f"{project_name}{PROJECT_ARCHIVE_SUFFIX}", project_name


def _project_archive_input_path(project_path: str) -> pathlib.Path:
    """Return a ``.cs.pto`` project path from a user-selected path."""
    path = pathlib.Path(project_path)
    if str(path).lower().endswith(PROJECT_ARCHIVE_SUFFIX):
        return path
    if path.is_dir():
        return path / f"project{PROJECT_ARCHIVE_SUFFIX}"
    # If no suffix, treat the path as a stem and append .cs.pto.
    return pathlib.Path(f"{path}{PROJECT_ARCHIVE_SUFFIX}")


def _current_project_root() -> pathlib.Path | None:
    gui = getattr(cs, "cs", None)
    current_path = getattr(gui, "_current_project_path", None)
    if current_path:
        return pathlib.Path(current_path).parent
    return None


def _history_snapshot_bytes() -> bytes | None:
    history_obj = getattr(cs, "history", None)
    if history_obj is None or not hasattr(history_obj, "save_jsonl"):
        return None
    with tempfile.TemporaryDirectory() as tmpdir:
        history_path = history_obj.save_jsonl(pathlib.Path(tmpdir) / HISTORY_FILENAME)
        return pathlib.Path(history_path).read_bytes()


def _write_history_snapshot_to_archive(archive: ProjectArchive) -> None:
    history_bytes = _history_snapshot_bytes()
    if history_bytes is not None:
        archive.write_bytes(HISTORY_FILENAME, history_bytes)


def _write_bff_session_to_archive(archive: ProjectArchive) -> None:
    """Persist bff's default session (chinet's JSONL format) to the archive.

    The node-graph session file is byte-compatible with chinet's format;
    bff's Session reads and writes it, so old projects open unchanged.
    """
    try:
        import IMP.bff as bff
    except (ImportError, AttributeError):
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        session_path = pathlib.Path(tmpdir) / "session.jsonl"
        bff.get_session().save(str(session_path))
        archive.write_bytes("session.jsonl", session_path.read_bytes())


def _resolve_external_path(value: str, project_root: pathlib.Path | None) -> pathlib.Path | None:
    path = pathlib.Path(value)
    candidates: list[pathlib.Path] = []
    if path.is_absolute():
        candidates.append(path)
    else:
        if project_root is not None:
            candidates.append(project_root / path)
        candidates.append(pathlib.Path.cwd() / path)

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _archive_name_for_file(source_path: pathlib.Path, used_names: set[str]) -> str:
    base_name = f"{DATA_DIR}/{source_path.name}"
    if base_name not in used_names:
        used_names.add(base_name)
        return base_name

    digest = hashlib.md5(str(source_path.resolve()).encode("utf-8", errors="ignore")).hexdigest()[
        :8
    ]
    stem = source_path.stem or "file"
    suffix = source_path.suffix
    name = f"{DATA_DIR}/{stem}-{digest}{suffix}"
    counter = 1
    while name in used_names:
        name = f"{DATA_DIR}/{stem}-{digest}-{counter}{suffix}"
        counter += 1
    used_names.add(name)
    return name


def _rewrite_proteinmc_paths(
    state: typing.Any,
    archive: ProjectArchive,
    used_names: set[str],
    missing: list[str],
    project_root: pathlib.Path | None,
    log: typing.Any,
) -> None:
    """Rewrite known ProteinMC file paths to archive-relative paths."""
    if not isinstance(state, dict):
        return
    proteinmc = state.get("proteinmc")
    if not isinstance(proteinmc, dict):
        return

    for key in ("structure_source", "labeling_file", "output_file", "trajectory_file"):
        value = proteinmc.get(key)
        if not isinstance(value, str) or not value:
            continue
        source_path = _resolve_external_path(value, project_root)
        if source_path is not None:
            archive_name = _archive_name_for_file(source_path, used_names)
            try:
                archive.write_file(archive_name, source_path)
            except Exception as exc:
                log.warning(f"save_project: could not embed {source_path}: {exc}")
                continue
            proteinmc[key] = archive_name
        elif value.startswith(f"{DATA_DIR}/"):
            continue
        else:
            missing.append(value)


def _embed_external_file_refs(
    proj: CSProject,
    archive: ProjectArchive,
    project_root: pathlib.Path | None,
    log: typing.Any,
) -> None:
    """Embed known external project files into a project archive."""
    used_names: set[str] = set()
    missing: list[str] = []

    for payload in (proj.datasets or {}).values():
        if not isinstance(payload, dict) or not _is_file_backed_dataset(payload):
            continue
        value = payload.get("path")
        if not isinstance(value, str) or not value:
            continue
        source_path = _resolve_external_path(value, project_root)
        if source_path is not None:
            archive_name = _archive_name_for_file(source_path, used_names)
            try:
                archive.write_file(archive_name, source_path)
            except Exception as exc:
                log.warning(f"save_project: could not embed {source_path}: {exc}")
                continue
            payload["path"] = archive_name
        elif value.startswith(f"{DATA_DIR}/"):
            continue
        else:
            missing.append(value)

    ui_state = proj.ui_state if isinstance(proj.ui_state, dict) else {}
    chimol = ui_state.get("chimol")
    if isinstance(chimol, dict) and isinstance(chimol.get("open_files"), list):
        open_files = []
        for value in chimol["open_files"]:
            if not isinstance(value, str):
                open_files.append(value)
                continue
            source_path = _resolve_external_path(value, project_root)
            if source_path is not None:
                archive_name = _archive_name_for_file(source_path, used_names)
                try:
                    archive.write_file(archive_name, source_path)
                except Exception as exc:
                    log.warning(f"save_project: could not embed {source_path}: {exc}")
                    open_files.append(value)
                    continue
                open_files.append(archive_name)
            elif value.startswith(f"{DATA_DIR}/"):
                open_files.append(value)
            else:
                missing.append(value)
                open_files.append(value)
        chimol["open_files"] = open_files

    _rewrite_proteinmc_paths(ui_state, archive, used_names, missing, project_root, log)

    for fit_record in proj.fits or []:
        if not isinstance(fit_record, dict):
            continue
        for local_fit in fit_record.get("local_fits") or []:
            if isinstance(local_fit, dict):
                _rewrite_proteinmc_paths(
                    local_fit.get("fit_state"),
                    archive,
                    used_names,
                    missing,
                    project_root,
                    log,
                )

    if missing:
        proj.extra["missing_external_files"] = sorted(set(missing))
        log.warning(f"save_project: could not embed external files: {missing}")


def export_action_catalog(
    target_path: str = "",
    file_type: str = "yaml",
) -> pathlib.Path:
    catalog = get_action_catalog()

    def _normalize_format(path_obj: pathlib.Path, raw: str) -> str:
        value = str(raw or "").strip().lower()
        if value in {"yml", "yaml"}:
            return "yaml"
        if value == "json":
            return "json"
        suffix = path_obj.suffix.lower().lstrip(".")
        if suffix in {"yml", "yaml"}:
            return "yaml"
        if suffix == "json":
            return "json"
        return "yaml"

    out_path: pathlib.Path
    if target_path:
        out_path = pathlib.Path(str(target_path))
    else:
        working = getattr(cs, "working_path", None)
        base_dir = pathlib.Path(working) if working else pathlib.Path.cwd()
        out_path = base_dir / "action_catalog"

    fmt = _normalize_format(out_path, file_type)
    if out_path.suffix == "":
        out_path = out_path.with_suffix(".yaml" if fmt == "yaml" else ".json")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        out_path.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    else:
        import yaml

        out_path.write_text(
            yaml.safe_dump(catalog, sort_keys=False, allow_unicode=False),
            encoding="utf-8",
        )

    _record_history(
        action_type="action_catalog_export",
        summary=f"export action catalog to '{out_path.as_posix()}'",
        payload={
            "target_path": out_path.as_posix(),
            "format": fmt,
            "action_count": int(len(catalog)),
        },
    )

    return out_path


def _serialize_reader(reader: typing.Any) -> typing.Optional[typing.Dict[str, typing.Any]]:
    """Serialize an ExperimentReader into a JSON-friendly dict.

    We keep this minimal to avoid recursion loops (e.g. experiment._readers
    holding the same reader). Only elementary attributes are retained; Qt
    widgets, experiment references, and controllers are skipped.
    """
    if not isinstance(reader, ExperimentReader):
        return None

    def _is_basic(v: typing.Any) -> bool:
        return isinstance(v, (str, int, float, bool, type(None)))

    def _to_basic(v: typing.Any):
        if _is_basic(v):
            return v
        if isinstance(v, np.integer):
            return int(v)
        if isinstance(v, np.floating):
            return float(v)
        if isinstance(v, np.ndarray):
            return v.tolist()
        if isinstance(v, (list, tuple)):
            out = []
            for item in v:
                if _is_basic(item) or isinstance(item, (np.integer, np.floating)):
                    out.append(_to_basic(item))
                else:
                    # skip non-basic entries in sequences
                    continue
            return out
        return None

    state: typing.Dict[str, typing.Any] = {}
    banned_keys = {"experiment", "_experiment", "controller", "_readers", "setup"}
    for k, v in getattr(reader, "__dict__", {}).items():
        if k in banned_keys or (k.startswith("_") and k not in {"_irf"}):
            continue
        basic = _to_basic(v)
        if basic is not None:
            state[k] = basic

    rec: typing.Dict[str, typing.Any] = {
        "module": type(reader).__module__,
        "class": type(reader).__name__,
        "state": state,
    }
    return rec


def _deserialize_reader(
    reader_info: typing.Dict[str, typing.Any],
) -> typing.Optional[ExperimentReader]:
    """Reconstruct an ExperimentReader from serialized info."""
    if not isinstance(reader_info, dict):
        return None
    mod_name = reader_info.get("module")
    cls_name = reader_info.get("class")
    state = reader_info.get("state") or {}
    if not mod_name or not cls_name:
        return None
    try:
        mod = importlib.import_module(mod_name)
        cls = getattr(mod, cls_name)
    except Exception:
        return None
    try:
        reader = cls.__new__(cls)
    except Exception:
        return None
    try:
        if isinstance(state, dict):
            reader.__dict__.update(state)
    except Exception:
        pass
    # Attach current experiment if available so autofitrange works
    try:
        exp_obj = getattr(cs.cs, "current_experiment", None)
        if exp_obj is not None:
            reader.experiment = exp_obj
    except Exception:
        pass
    return reader


def _datacurve_arrays(
    dc: cs.core.data.DataCurve,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return x/y/ex/ey arrays for a DataCurve as float64 arrays."""
    try:
        x = np.asarray(getattr(dc, "x", []), dtype=float)
        y = np.asarray(getattr(dc, "y", []), dtype=float)
        ex = np.asarray(getattr(dc, "ex", np.zeros_like(x)), dtype=float)
        ey = np.asarray(getattr(dc, "ey", np.ones_like(y)), dtype=float)
    except Exception:
        x = np.asarray([], dtype=float)
        y = np.asarray([], dtype=float)
        ex = np.asarray([], dtype=float)
        ey = np.asarray([], dtype=float)
    return x, y, ex, ey


def _encode_curve_array(arr: np.ndarray) -> dict[str, typing.Any]:
    """Encode a numeric project curve array as base64 JSON."""
    encoded = encode_array(np.asarray(arr, dtype=float))
    encoded["encoding"] = "base64"
    return encoded


def _decode_project_array(value: typing.Any) -> np.ndarray:
    """Decode a project curve array from base64 or legacy list form."""
    if isinstance(value, dict) and value.get("encoding") == "base64":
        return decode_array(value)
    if value is None:
        return np.asarray([], dtype=float)
    return np.asarray(value, dtype=float)


def _decode_curve_payload(
    payload: typing.Dict[str, typing.Any],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Decode x/y/ex/ey arrays from a project dataset payload."""
    x = _decode_project_array(payload.get("x", []))
    y = _decode_project_array(payload.get("y", []))
    if "ex" in payload:
        ex = _decode_project_array(payload.get("ex"))
    else:
        ex = np.zeros_like(x)
    if "ey" in payload:
        ey = _decode_project_array(payload.get("ey"))
    else:
        ey = np.ones_like(y)
    return x, y, ex, ey


def add_fit(
    dataset_indices: typing.List[int] = None,
    model_name: str = None,
    model_kw: typing.Dict = None,
    model_module: str = None,
    model_class_name: str = None,
    group_datasets: bool = False,
    data_group_name: str = None,
    _defer_cs_update: bool = False,
    _ui_updates_frozen: bool = False,
    _force_local: bool = False,
    _skip_gui_creation: bool = False,
):
    # Phase 8: in server mode, route through the API so the server
    # creates the fit object.  The proxy list will pick it up on the
    # next refresh.
    import chisurf as _cs_guard

    _api_guard = getattr(_cs_guard, "api", None)
    if (
        not _force_local
        and _api_guard is not None
        and getattr(_api_guard, "mode", None) == "server"
    ):
        return _api_guard.add_fit(
            dataset_indices=list(dataset_indices or [0]),
            model_name=model_name,
            model_kw=model_kw,
        )

    def _resolve_model_name_from_cs(main_window) -> str:
        try:
            v = str(getattr(main_window, "current_model_name", "") or "").strip()
            if v:
                return v
        except Exception:
            pass

        try:
            mc = getattr(main_window, "current_model_class", None)
            if mc is not None:
                v = str(getattr(mc, "name", "") or "").strip()
                if v:
                    return v
        except Exception:
            pass

        try:
            exp = getattr(main_window, "current_experiment", None)
            models = list(getattr(exp, "models", []) or [])
            if models:
                v = str(getattr(models[0], "name", "") or "").strip()
                if v:
                    return v
        except Exception:
            pass

        return ""

    gui = getattr(cs, "cs", None)  # noqa: F823 -- ruff false-positive: a sibling function's local `import chisurf.x` submodule import confuses its cross-scope binding tracking for the module-level `cs` alias
    # Process inputs of macro and replace None
    # with more sensible values that are read
    # from the GUI or fallback defaults
    if dataset_indices is None:
        if gui is not None:
            dataset_indices = [gui.dataset_selector.selected_curve_index]
        else:
            dataset_indices = [0] if cs.imported_datasets else []
    if model_name is None:
        if gui is not None:
            model_name = _resolve_model_name_from_cs(gui)
        else:
            model_name = ""

    # Do nothing of no dataset is selected
    if len(dataset_indices) == 0:
        cs.logging.warning("add_fit: no dataset index selected; aborting")
        return {"ok": False, "error": "no dataset index selected"}

    # If multiple datasets were requested, build each fit independently
    # using the already-stable single-dataset code path.
    if len(dataset_indices) > 1 and not group_datasets:
        batched_frozen = bool(_ui_updates_frozen)
        mdl_parent = None
        plo_parent = None

        if gui is not None:
            mdl_parent = getattr(gui.modelLayout, "parentWidget", lambda: None)()
            plo_parent = getattr(gui.plotOptionsLayout, "parentWidget", lambda: None)()
            try:
                if not batched_frozen:
                    if mdl_parent:
                        mdl_parent.setUpdatesEnabled(False)
                    if plo_parent:
                        plo_parent.setUpdatesEnabled(False)
                    gui.mdiarea.setUpdatesEnabled(False)
            except Exception:
                pass

        try:
            for idx in dataset_indices:
                try:
                    add_fit(
                        dataset_indices=[idx],
                        model_name=model_name,
                        model_kw=model_kw,
                        _defer_cs_update=True,
                        _ui_updates_frozen=True,
                    )
                except Exception as e:
                    cs.logging.warning(f"add_fit: failed for dataset index {idx}: {e}")
        finally:
            if gui is not None and not batched_frozen:
                try:
                    gui.mdiarea.setUpdatesEnabled(True)
                    if mdl_parent:
                        mdl_parent.setUpdatesEnabled(True)
                    if plo_parent:
                        plo_parent.setUpdatesEnabled(True)
                except Exception:
                    pass
        if gui is not None and not _defer_cs_update:
            try:
                gui.update()
            except Exception:
                pass
        return

    # create a list of data sets to which a fit with
    # a particular model is added. Avoid GUI access if missing.
    try:
        data_sets = [cs.imported_datasets[i] for i in dataset_indices]
    except IndexError:
        cs.logging.error("add_fit: dataset indices out of bounds of cs.imported_datasets")
        return {"ok": False, "error": "dataset indices out of bounds"}

    # Dataset selection and fit grouping are different operations. Interactive
    # multi-selection historically means one fit group per selected dataset;
    # project restoration explicitly asks for the saved group to be rebuilt as
    # one heterogeneous collection of member curves.
    if group_datasets and len(data_sets) > 1:
        members = []
        for selected in data_sets:
            if isinstance(selected, cs.core.data.DataGroup):
                members.extend(list(selected))
            else:
                members.append(selected)
        combined = cs.core.data.ExperimentDataCurveGroup(
            members,
            name=str(data_group_name or getattr(data_sets[0], "name", "")),
        )
        try:
            combined.experiment = getattr(data_sets[0], "experiment", None)
        except Exception:
            pass
        try:
            combined.data_reader = getattr(data_sets[0], "data_reader", None)
        except Exception:
            pass
        data_sets = [combined]

    # Prefer the experiment attached to the dataset; fall back to the
    # globally selected experiment if necessary (e.g. after project load).
    exp = getattr(data_sets[0], "experiment", None)
    if exp is None and gui is not None:
        exp = getattr(gui, "current_experiment", None)
    if exp is None:
        # Headless fallback: trying to use first registered experiment
        try:
            exp = list(cs.core.experiments.types.values())[0] if cs.core.experiments.types else None
        except Exception:
            exp = None
    if exp is None:
        cs.logging.warning(
            "add_fit: no experiment available on dataset or gui.current_experiment; aborting"
        )
        return {"ok": False, "error": "no experiment available"}

    model_names = exp.model_names
    model_class = None

    # A project records the exact Python type that produced the fit.  Resolve
    # it before consulting experiment display names: registration is optional
    # in headless sessions and user-facing labels are not stable identity.
    if model_module and model_class_name:
        try:
            import importlib

            from chisurf.core.models.model import Model

            candidate = getattr(importlib.import_module(str(model_module)), str(model_class_name))
            if isinstance(candidate, type) and issubclass(candidate, Model):
                model_class = candidate
        except Exception as exc:
            cs.logging.warning(
                "add_fit: could not import saved model %s.%s: %s",
                model_module,
                model_class_name,
                exc,
            )

    # Try to find the model by name in the experiment type. Compared stripped:
    # a model whose ``name`` carries stray whitespace ("Lifetime ") would
    # otherwise never match the string a caller reasonably passes, fall through
    # to the global subclass scan below, and resolve by luck rather than by
    # registration.
    wanted = str(model_name or "").strip()
    for model_idx, mn in enumerate(model_names):
        if str(mn or "").strip() == wanted:
            model_class = exp.model_classes[model_idx]
            break

    # If not found and we have a specific name, search globally in all Model subclasses.
    # This ensures headless project loading works for any registered model class in the environment.
    if model_class is None and model_name != "None":
        if model_name == "ProteinMC":
            try:
                import chisurf.core.models.structure.proteinmc_model  # noqa: F401
            except Exception:
                pass
        from chisurf.core.models.model import Model

        def get_all_subclasses(cls):
            all_subclasses = []
            for subclass in cls.__subclasses__():
                all_subclasses.append(subclass)
                all_subclasses.extend(get_all_subclasses(subclass))
            return all_subclasses

        for cls in get_all_subclasses(Model):
            if getattr(cls, "name", None) == model_name:
                model_class = cls
                break

    # Fallback to the experiment's default model if still not found and no
    # specific name requested. Filtered by the dataset: one experiment can hold
    # data of more than one shape (PDA reads two-colour histograms and
    # three-colour burst tables), and the first model overall may be one that
    # cannot fit this dataset at all. A name that was asked for and matched
    # nothing is an error, not a request for the default: a renamed model
    # used to come back as whatever model happened to be first.
    if model_class is None and wanted and wanted != "None":
        cs.logging.warning(f"add_fit: no model named '{model_name}'; aborting")
        return {"ok": False, "error": f"no model named '{model_name}'"}
    if model_class is None:
        applicable = exp.get_model_classes(data_sets[0]) or exp.model_classes
        if applicable:
            model_class = applicable[0]

    if model_class is None:
        cs.logging.warning(f"add_fit: could not resolve model '{model_name}'; aborting")
        return {"ok": False, "error": f"could not resolve model '{model_name}'"}

    base_model_kw = dict(model_kw or {})

    for data_set in data_sets:
        if data_set.experiment is data_sets[0].experiment:
            # Make sure the data set is a DataGroup
            if not isinstance(data_set, cs.core.data.DataGroup):
                data_group = cs.core.data.ExperimentDataCurveGroup([data_set])
            else:
                data_group = data_set

            # Propagate data_reader/experiment to the group for restored projects
            try:
                if getattr(data_group, "data_reader", None) is None:
                    data_group.data_reader = getattr(data_set, "data_reader", None)
            except Exception:
                pass
            try:
                if getattr(data_group, "experiment", None) is None:
                    data_group.experiment = getattr(data_set, "experiment", None)
            except Exception:
                pass
            try:
                # Ensure contained curves have the reader attached (legacy projects)
                reader_obj = getattr(data_set, "data_reader", None)
                if reader_obj is not None:
                    for dc in data_group:
                        if getattr(dc, "data_reader", None) is None:
                            dc.data_reader = reader_obj
            except Exception:
                pass

            _record_history(
                action_type="fit_add_start",
                summary=(
                    f"start add fit for dataset '{getattr(data_set, 'name', '')}' "
                    f"with model '{model_name}'"
                ),
                payload={
                    "dataset_name": str(getattr(data_set, "name", "")),
                    "model_name": str(model_name),
                    "dataset_indices": [int(i) for i in dataset_indices],
                },
            )

            dataset_model_kw = dict(base_model_kw)
            dataset_calibration = _resolve_dataset_anisotropy_calibration(data_group)
            for key in ("g_factor", "l1", "l2"):
                value = _coerce_finite_float(dataset_calibration.get(key))
                if value is not None and key not in dataset_model_kw:
                    dataset_model_kw[key] = value

            # Create the fit
            fit_group = cs.core.fitting.fit.FitGroup(
                data=data_group, model_class=model_class, model_kw=dataset_model_kw
            )
            _apply_anisotropy_calibration_to_fit(fit_group, dataset_calibration)
            # Extract TTTR header metadata from the data's meta_data (populated
            # during the initial file read — no second file access).
            try:
                _attach_tttr_header(fit_group, data_group)
            except Exception:
                pass
            linked_masters, linked_followers = _auto_link_non_nuisance_group_parameters(fit_group)
            cs.fits.append(fit_group)
            _record_history(
                action_type="fit_add",
                summary=(
                    f"add fit group '{getattr(fit_group, 'name', '')}' for dataset "
                    f"'{getattr(data_set, 'name', '')}' with model '{model_name}'"
                ),
                payload={
                    "fit_group_name": str(getattr(fit_group, "name", "")),
                    "dataset_name": str(getattr(data_set, "name", "")),
                    "model_name": str(model_name),
                    "dataset_indices": [int(i) for i in dataset_indices],
                },
                source_uid=str(getattr(fit_group, "unique_identifier", "")) or None,
            )
            if linked_followers > 0:
                _record_history(
                    action_type="fit_group_auto_link",
                    summary=(
                        f"auto-link non-nuisance parameters for fit group '{getattr(fit_group, 'name', '')}' "
                        f"({linked_masters} master parameter(s), {linked_followers} follower link(s))"
                    ),
                    payload={
                        "fit_group_name": str(getattr(fit_group, "name", "")),
                        "linked_master_parameters": int(linked_masters),
                        "linked_followers": int(linked_followers),
                        "policy": "non_nuisance_default_link",
                    },
                    source_uid=str(getattr(fit_group, "unique_identifier", "")) or "",
                )

            # During project load we skip GUI creation entirely —
            # restore_gui_from_fits (called via QTimer) opens the windows.
            if not _skip_gui_creation:
                # Publish event so the GUI can create the MDI subwindow reactively
                try:
                    from chisurf.server.startup import get_shared_event_bus

                    _bus = get_shared_event_bus()
                    if _bus is not None:
                        _bus.publish(
                            "fit.added",
                            {
                                "fit_uid": str(getattr(fit_group, "unique_identifier", "")),
                                "fit_index": len(cs.fits) - 1,
                                "fit_name": str(getattr(fit_group, "name", "")),
                            },
                        )
                except Exception:
                    cs.logging.exception("add_fit: failed to publish fit.added event")

            # Batch UI updates to avoid repeated repaints while constructing widgets
            if gui is not None and not _skip_gui_creation:
                mdl_parent = getattr(gui.modelLayout, "parentWidget", lambda: None)()
                plo_parent = getattr(gui.plotOptionsLayout, "parentWidget", lambda: None)()
                try:
                    if not _ui_updates_frozen:
                        if mdl_parent:
                            mdl_parent.setUpdatesEnabled(False)
                        if plo_parent:
                            plo_parent.setUpdatesEnabled(False)
                        gui.mdiarea.setUpdatesEnabled(False)

                    # The main window owns opening a fit window: the
                    # ``fit.added`` event published above goes to the same
                    # opener, which de-duplicates per fit. A second, inline
                    # copy here opened a duplicate window whenever an event
                    # loop spun mid-build and delivered that event first.
                    gui._open_fit_subwindow(fit_group)
                finally:
                    if not _ui_updates_frozen:
                        gui.mdiarea.setUpdatesEnabled(True)
                        if mdl_parent:
                            mdl_parent.setUpdatesEnabled(True)
                        if plo_parent:
                            plo_parent.setUpdatesEnabled(True)

    if gui is not None and not _defer_cs_update:
        try:
            gui.update()
        except Exception:
            pass


def save_fit(target_path: str = None, use_complex_name: bool = False, fit_window=None):
    log = cs.logging
    log.debug(
        "save_fit: start (target_path=%r, use_complex_name=%r)", target_path, use_complex_name
    )

    gui = getattr(cs, "cs", None)
    if gui is None:
        log.error("save_fit: no active main window (cs.cs is missing)")
        return
    if fit_window is None:
        log.debug("No fit_window passed—taking current MDI subwindow")
        fit_window = gui.mdiarea.currentSubWindow()

    fit = fit_window.fit
    widget = fit_window.fit_widget
    fit_group = widget.fit

    # decide on save directory & base name
    if target_path is None:
        target_path = cs.working_path
        log.debug("No target_path passed—using working_path=%r", target_path)

    if use_complex_name:
        save_name = cs.core.base.clean_string(fit.name)
        log.debug("Using complex fit.name → %r", save_name)
    else:
        save_name = os.path.basename(fit.data.name)
        log.debug("Using simple data name → %r", save_name)

    # Keep output filenames readable by dropping any trailing source extension
    # from dataset-based names (e.g. "*.dat VV" -> "* VV").
    save_stem = os.path.splitext(save_name)[0]
    basename = os.path.join(target_path, save_stem)
    log.info("Will write files with base %r", basename)

    # 1) dump numeric data
    log.debug("Saving fit CSV and curves to %r.csv", basename)
    fit.save(basename, "csv", save_curves=True)
    # Also persist fit.json as ChiSurf project-style state without global links.
    try:
        fg_key, fit_payload = _build_fitgroup_payload_from_window(
            fit_window,
            register_datacurve=lambda dc: "",
            log=log,
            group_index=0,
        )
        # embed dataset in-place to avoid cross-fit collisions; reuse fit.data arrays
        datasets: typing.Dict[str, typing.Dict] = {}
        try:
            data_obj = getattr(fit, "data", None)
            if isinstance(data_obj, cs.core.data.DataCurve):
                x, y, ex, ey = _datacurve_arrays(data_obj)
                datasets["ds000"] = {
                    "name": getattr(data_obj, "name", ""),
                    "filename": getattr(data_obj, "filename", ""),
                    "x": _encode_curve_array(x),
                    "y": _encode_curve_array(y),
                    "ex": _encode_curve_array(ex),
                    "ey": _encode_curve_array(ey),
                }
                # attach dataset_id directly to the fit payload
                if fit_payload and fit_payload.get("local_fits"):
                    fit_payload["local_fits"][0]["dataset_id"] = "ds000"
        except Exception as exc:
            log.warning(f"save_fit: could not build dataset payload for fit.json: {exc}")

        if fit_payload:
            fit_ui_state = {"current_fit_index": getattr(gui, "fit_idx", 0)}
            try:
                history_browser = getattr(gui, "historyBrowser", None)
                get_hist_state = getattr(history_browser, "get_ui_state", None)
                if callable(get_hist_state):
                    fit_ui_state["history_browser"] = get_hist_state()
            except Exception:
                pass

            proj = CSProject(
                name=fit.name or save_stem,
                description=f"ChiSurf fit '{fit.name or save_stem}'",
                chisurf_version=getattr(cs.core.info, "__version__", None),
                datasets=datasets,
                experiments={},
                fits={fg_key: fit_payload},
                ui_state=fit_ui_state,
            )
            # Write fit.json using the base name without the original data extension
            base_no_ext = os.path.join(target_path, save_stem)
            fit_json_path = base_no_ext + ".fit.json"
            try:
                with open(fit_json_path, "w", encoding="utf-8") as f:
                    json.dump(proj.to_dict(), f, indent=2, sort_keys=True)
                log.info(f"Saved fit state to {fit_json_path}")
            except Exception as exc:
                log.warning(f"save_fit: could not write fit.json: {exc}")
    except Exception as exc:
        log.warning(f"save_fit: failed to build fit.json payload: {exc}")
    # log.debug("Saving fit data object to %r_data.pkl", basename)
    # fit.data.save(basename + "_data", 'pkl')

    # 2) build the Word report
    log.debug("Building Word document")
    import docx
    from docx.shared import Inches

    document = docx.Document()
    document.add_heading(gui.current_fit.name, 0)

    if not os.path.isdir(target_path):
        log.warning("Target folder %r does not exist, aborting report", target_path)
        return

    document.add_heading("Fit‑Results", level=1)
    overlay_prev = bool(getattr(cs, "_suspend_plot_metrics_overlay", False))
    setattr(cs, "_suspend_plot_metrics_overlay", True)
    try:
        for i, f in enumerate(fit):
            widget.selected_fit = i
            log.debug("Adding screenshots for fit #%d", i + 1)
            document.add_paragraph(f"Fit #{i + 1}", style="ListNumber")

            from chisurf.gui.widgets.models.model_editor import model_editor_widget

            for suffix, source in (
                ("_screenshot_fit.png", fit_window),
                ("_screenshot_model.png", model_editor_widget(f.model)),
            ):
                png_path = basename + suffix
                if source is None:  # pure model with no built editor widget
                    continue
                log.debug(" Grabbing %r → %r", source, png_path)

                pix = source.grab()
                pix.save(png_path)
                del pix
                log.debug("  Saved and deleted QPixmap")

                document.add_picture(png_path, width=Inches(2.0))
                log.debug("  Embedded picture %r", png_path)
    finally:
        setattr(cs, "_suspend_plot_metrics_overlay", overlay_prev)

    # 3) summary table
    log.debug("Adding summary table for %d grouped fits", len(fit_group.grouped_fits))
    document.add_heading("Summary", level=1)
    p = document.add_paragraph("Parameters which are fitted are given in ")
    p.add_run("bold").bold = True
    p.add_run(", linked parameters in ")
    p.add_run("italic.").italic = True
    p.add_run(" Fixed parameters are plain name.")

    n = len(fit_group.grouped_fits)
    table = document.add_table(rows=1, cols=n + 1)
    hdr = table.rows[0].cells
    hdr[0].text = "Param"
    for col in range(n):
        hdr[col + 1].text = str(col + 1)

    parameters = sorted(fit.model.parameters_all_dict.keys())
    for k in parameters:
        row = table.add_row().cells
        row[0].text = k
        for col, f in enumerate(fit_group):
            val = f.model.parameters_all_dict[k]
            run = row[col + 1].paragraphs[0].add_run(f"{val.value:.3f}")
            if val.fixed:
                style = "fixed"
            elif val.link is not None:
                run.italic = True
                style = "linked"
            else:
                run.bold = True
                style = "fitted"
            log.debug(" Table cell [%r, fit #%d] = %.3f (%s)", k, col + 1, val.value, style)

    # chi² row
    chi_row = table.add_row().cells
    chi_row[0].text = "Chi2r"
    for col, f in enumerate(fit_group):
        val = f.chi2r
        chi_row[col + 1].paragraphs[0].add_run(f"{val:.4f}")
        log.debug(" Table cell [Chi2r, fit #%d] = %.4f", col + 1, val)

    # finally save the document
    docx_path = basename + ".docx"
    log.info("Saving report document to %r", docx_path)
    document.save(docx_path)

    # ——— attempt Qt event processing cleanup —————
    log.debug("Processing pending Qt events and cleaning up")
    try:
        from qtpy.QtWidgets import QApplication

        QApplication.processEvents()
    except Exception:
        pass

    # drop Qt references and run GC
    fit_window = widget = fit_group = document = None
    gc.collect()
    log.debug("save_fit: done")


def load_fit_result(fit_index: int, filename: str) -> bool:
    if os.path.isfile(filename):
        cs.fits[fit_index].model.load(filename)
        cs.fits[fit_index].update()
        return True
    else:
        return False


def _merge_docx(docx_files, out_path: str) -> bool:
    """Merge multiple DOCX files into a single document by stacking their bodies.

    Returns True on success, False otherwise.
    Note: This simple merge appends XML bodies and may not keep images/styles perfectly,
    but is sufficient to "simply stack" documents.
    """
    try:
        from docx import Document
    except Exception as e:
        cs.logging.info(f"python-docx not available, skipping combined DOCX creation: {e}")
        return False

    from copy import deepcopy

    try:
        master = Document()
        first = True

        # Helper to get body element compatibly
        def _body(doc):
            try:
                return doc.element.body
            except Exception:
                return doc._element.body

        for fp in docx_files:
            if not fp or not os.path.exists(fp):
                continue
            sub = Document(fp)
            if not first:
                master.add_page_break()
            first = False
            src_body = _body(sub)
            dst_body = _body(master)
            # Append deep copies of all children (paragraphs, tables, images)
            for child in list(src_body):
                dst_body.append(deepcopy(child))
        master.save(out_path)
        return True
    except Exception as e:
        cs.logging.warning(f"Failed to merge DOCX files: {e}")
        return False


def save_fits(target_path: str, use_complex_name: bool = False):
    if os.path.isdir(target_path):
        created_docx = []
        for fit_window in cs.gui.fit_windows:
            fit = fit_window.fit

            # Skip global fits
            setup = getattr(fit.data, "setup", None)
            if isinstance(setup, cs.core.experiments.globalfit.GlobalFitSetup):
                continue

            if use_complex_name:
                save_name = cs.core.base.clean_string(fit.name)
            else:
                save_name = os.path.basename(fit.data.name)
            save_stem = os.path.splitext(save_name)[0]

            p2 = os.path.join(target_path, save_stem)

            # Ensure per-fit directory handling with overwrite/skip/cancel dialog
            if os.path.exists(p2):
                try:
                    # Imported here, not at module scope: macros run headless
                    # (server mode, CLI) and must not drag Qt in to be defined.
                    from chisurf.gui import dialogs

                    answer = dialogs.choice(
                        None,
                        "Folder exists",
                        f"The folder '{p2}' already exists.",
                        {"overwrite": "Overwrite", "skip": "Skip", "cancel": "Cancel"},
                        # Unattended, keep what is on disk rather than delete it.
                        default="skip",
                        informative="Do you want to overwrite it?",
                    )
                    if answer.key == "overwrite":
                        cs.logging.info(f"Overwriting existing folder: {p2}")
                        try:
                            if os.path.isdir(p2):
                                shutil.rmtree(p2)
                            else:
                                os.remove(p2)
                        except Exception as e:
                            cs.logging.warning(f"Failed to remove existing path {p2}: {e}")
                        os.makedirs(p2, exist_ok=True)
                    elif answer.key == "skip":
                        cs.logging.info(f"Skipping existing folder: {p2}")
                        continue
                    else:
                        cs.logging.info("Save all fits cancelled by user")
                        return
                except Exception as e:
                    # Headless or dialog failed: default to skipping
                    cs.logging.warning(
                        f"Could not show overwrite dialog or handle existing folder ({e}). Skipping fit."
                    )
                    continue
            else:
                os.makedirs(p2, exist_ok=True)

            save_fit(target_path=p2, fit_window=fit_window)

            # Track created per-fit DOCX path for merging
            per_fit_docx = os.path.join(p2, f"{save_stem}.docx")
            if os.path.exists(per_fit_docx):
                created_docx.append(per_fit_docx)

        # After saving all, create combined DOCX by stacking
        if created_docx:
            combined_path = os.path.join(target_path, "all_fits.docx")
            ok = _merge_docx(created_docx, combined_path)
            if ok:
                cs.logging.info(f"Combined DOCX created: {combined_path}")
            else:
                cs.logging.info("Combined DOCX could not be created.")


def close_fit(idx: int = None):
    gui = getattr(cs, "cs", None)
    if gui is None:
        cs.logging.error("close_fit: no active main window (cs.cs is missing)")
        return

    # Resolve index from current subwindow if not explicitly provided.
    if idx is None:
        sub_window = None
        try:
            mdi = getattr(gui, "mdiarea", None)
            if mdi is not None:
                sub_window = mdi.currentSubWindow()
        except Exception:
            sub_window = None

        if sub_window is not None:
            for i, w in enumerate(cs.gui.fit_windows):
                if w is sub_window:
                    idx = i
                    break

        # Fallback: try to resolve via gui.current_fit if available.
        if idx is None:
            current_fit = getattr(gui, "current_fit", None)
            if current_fit is not None:
                try:
                    idx = cs.fits.index(current_fit)
                except ValueError:
                    idx = None

    # If we still do not have a valid index, log and bail out gracefully.
    try:
        idx_int = int(idx) if idx is not None else None
    except Exception:
        idx_int = None

    if idx_int is None:
        cs.logging.warning("close_fit: no active fit to close (idx is None); ignoring request")
        return

    if idx_int < 0 or idx_int >= len(cs.fits) or idx_int >= len(cs.gui.fit_windows):
        cs.logging.warning(f"close_fit: index {idx_int} out of range; ignoring request")
        return

    fit_name = ""
    fit_uid = None
    try:
        fit_obj = cs.fits[idx_int]
        fit_name = str(getattr(fit_obj, "name", ""))
        uid = str(getattr(fit_obj, "unique_identifier", ""))
        fit_uid = uid or None
    except Exception:
        pass

    _record_history(
        action_type="fit_close",
        summary=f"close fit '{fit_name}'",
        payload={
            "fit_index": int(idx_int),
            "fit_name": str(fit_name),
        },
        source_uid=fit_uid or "",
    )

    # Remove the fit object and its corresponding window.
    try:
        cs.fits.pop(idx_int)
    except Exception as e:
        cs.logging.warning(f"close_fit: failed to remove fit at index {idx_int}: {e}")

    try:
        sub_window = cs.gui.fit_windows.pop(idx_int)
    except Exception as e:
        cs.logging.warning(f"close_fit: failed to pop fit window at index {idx_int}: {e}")
        sub_window = None

    if sub_window is not None:
        try:
            sub_window.close()
        except Exception:
            pass

    try:
        gui.update()
    except Exception:
        pass


def close_all_fits():
    """Close all currently active fits."""
    gui = getattr(cs, "cs", None)
    if gui is None:
        cs.logging.error("close_all_fits: no active main window (cs.cs is missing)")
        return
    for fit_window in list(cs.gui.fit_windows):
        try:
            fit_window.close_confirm = False
            fit_window.close()
        except Exception:
            pass
    cs.fits.clear()
    cs.gui.fit_windows.clear()
    gui.update()


def link_fit_group(fitting_parameter_name: str, csi: int = 0) -> None:
    """
    This macro links the parameters with a name
    specified by fitting_parameter_name within
    a FitGroup.

    :param fitting_parameter_name:
    :param csi:
    :return:
    """
    gui = getattr(cs, "cs", None)
    if gui is None:
        cs.logging.error("add_fit: no active main window (cs.cs is missing)")
        return
    linked_count = 0
    unlinked_count = 0
    master_uid = None

    # Only the currently displayed fit in a group has its model parameters
    # discovered; the other members keep a stale (possibly empty)
    # ``parameters_all_dict`` until they are rendered. Refresh every member so
    # the master lookup and the per-fit linking below see all parameters (e.g.
    # linking lifetimes across a VV/VH group where the master VV fit was never
    # the displayed one).
    current_fit = gui.current_fit
    for f in current_fit:
        try:
            f.model.find_parameters()
        except Exception:
            continue

    if csi == 2:
        # Establish a fit-group link. Prefer the first local fit in the group
        # as the master, but tolerate a heterogeneous group (e.g. VV/VH
        # anisotropy fits where the first member may transiently lack the
        # parameter): fall back to the first member that actually exposes it.
        grouped_fits = list(getattr(current_fit, "grouped_fits", []))
        if not grouped_fits:
            grouped_fits = [current_fit]

        parameter = None
        for f in grouped_fits:
            try:
                parameter = f.model.parameters_all_dict[fitting_parameter_name]
            except Exception:
                continue
            else:
                break

        if parameter is None:
            # No member of the group carries this parameter; report which
            # parameters the members do have so the cause is visible.
            try:
                avail = {
                    getattr(f, "name", "?"): sorted(f.model.parameters_all_dict.keys())
                    for f in grouped_fits
                }
            except Exception:
                avail = {}
            cs.logging.warning(
                f"link_fit_group: no fit in the group has parameter "
                f"'{fitting_parameter_name}', cannot link group; available={avail}"
            )
            return
        try:
            uid = str(getattr(parameter, "unique_identifier", ""))
            master_uid = uid or None
        except Exception:
            master_uid = None

        # Reset all master flags first to avoid stale GUI state.
        for f in current_fit:
            try:
                p_reset = f.model.parameters_all_dict[fitting_parameter_name]
                p_reset.is_link_master = False
            except Exception:
                continue

        # Mark master for GUI purposes only; numerical behaviour is governed
        # by the underlying parameter links.
        try:
            parameter.is_link_master = True
        except Exception:
            pass

        for f in current_fit:
            try:
                p = f.model.parameters_all_dict[fitting_parameter_name]
            except KeyError:
                cs.logging.warning(f"The fit {f.name} has no parameter {fitting_parameter_name}")
                continue
            if p is parameter:
                # Master remains unlinked but flagged as such for the GUI.
                continue
            try:
                p.is_link_master = False
            except Exception:
                pass
            p.link = parameter
            linked_count += 1

    if csi == 0:
        # Unlink the entire fit group for this parameter name and clear any
        # master flags so the GUI shows the unchecked state everywhere.
        for f in gui.current_fit:
            try:
                p = f.model.parameters_all_dict[fitting_parameter_name]
            except KeyError:
                continue
            try:
                p.is_link_master = False
            except Exception:
                pass
            p.link = None
            unlinked_count += 1

    if csi == 2:
        _record_history(
            action_type="fit_group_link",
            summary=(
                f"link fit group parameter '{fitting_parameter_name}' across "
                f"{linked_count} follower(s)"
            ),
            payload={
                "parameter_name": str(fitting_parameter_name),
                "linked_followers": int(linked_count),
                "mode": int(csi),
            },
            source_uid=master_uid,
        )
    elif csi == 0:
        _record_history(
            action_type="fit_group_unlink",
            summary=(
                f"unlink fit group parameter '{fitting_parameter_name}' across "
                f"{unlinked_count} local fit(s)"
            ),
            payload={
                "parameter_name": str(fitting_parameter_name),
                "unlinked": int(unlinked_count),
                "mode": int(csi),
            },
        )


def change_selected_fit_of_group(selected_fit: int) -> None:
    """
    Changes the currently selected fit.

    :param selected_fit:
    :return:
    """
    gui = getattr(cs, "cs", None)
    if gui is None:
        cs.logging.error("change_selected_fit_of_group: no active main window (cs.cs is missing)")
        return

    # Switching local fits changes the underlying model/parameter objects.
    # Ensure any derived output parameters are recomputed and the parameter
    # widgets refresh accordingly.
    try:
        from chisurf.gui.widgets.models.model_editor import hide_model_editor

        hide_model_editor(gui.current_fit.model)
    except Exception:
        pass

    gui.current_fit.selected_fit = selected_fit
    gui.current_fit.update()
    try:
        gui.current_fit.model.finalize()
    except Exception:
        pass

    # Refresh parameter controllers for the associated (selected) fit/model only
    # (includes output/result parameters).
    try:
        model = getattr(gui.current_fit, "model", None)
        params = getattr(model, "parameters_all", None)
        if isinstance(params, (list, tuple)):
            for p in params:
                try:
                    ctrl = getattr(p, "controller", None)
                    if ctrl is not None and hasattr(ctrl, "finalize"):
                        ctrl.finalize()
                except (AttributeError, RuntimeError, TypeError):
                    continue
    except Exception:
        pass

    try:
        from chisurf.gui.widgets.models.model_editor import show_model_editor

        show_model_editor(gui.current_fit.model)
    except Exception:
        pass


def get_project_payload(project_name: str = "chisurf_project") -> CSProject:
    """Capture owned science and client presentation through the shared codec."""
    from chisurf.core.project.ui_state import get_ui_state

    gui = getattr(cs, "cs", None)
    ui_state = get_ui_state(gui)
    selected = getattr(gui, "fit_idx", getattr(cs, "current_fit_idx", -1))
    ui_state["current_fit_index"] = selected if cs.fits else None
    client = getattr(cs, "__client__", None)
    if client is not None:
        from chisurf.core.api._proxies import ProxyDatasetList, ProxyFitList

        if isinstance(cs.imported_datasets, ProxyDatasetList) and isinstance(cs.fits, ProxyFitList):
            result = client.call("project.capture", {"ui_state": ui_state})
            from chisurf.core.project.capture import project_from_capture_reply

            return project_from_capture_reply(result, name=project_name)
    project = capture_session(
        cs.imported_datasets,
        cs.fits,
        experiments={},
        ui_state=ui_state,
        name=project_name,
        resources=getattr(cs, "project_resources", None),
    )
    from chisurf.core.project.history import capture_history

    project.extra.update(capture_history(getattr(cs, "history", None)))
    return project


def build_project_archive(
    project_name: str = "chisurf_project",
    *,
    include_save_history_event: bool = False,
    target_path: pathlib.Path | None = None,
) -> typing.Tuple[CSProject, bytes]:
    """Build a complete project payload and finalized ``.cs.pto`` bytes.

    Parameters
    ----------
    project_name : str, optional
        Project display name.
    include_save_history_event : bool, optional
        Whether to record a project-save event before writing history.
    target_path : pathlib.Path, optional
        Target path used only for the optional history event.

    Returns
    -------
    tuple
        The project payload and finalized archive bytes.
    """
    proj = get_project_payload(project_name)
    archive = ProjectArchive()
    if include_save_history_event and target_path is not None:
        _record_history(
            action_type="project_save",
            summary=f"save project '{project_name}' to '{target_path.as_posix()}'",
            payload={
                "project_path": target_path.as_posix(),
                "project_name": project_name,
            },
        )
    _write_history_snapshot_to_archive(archive)
    archive.write_text(PROJECT_JSON, json.dumps(proj.to_dict(), indent=2, sort_keys=True))
    return proj, archive.to_bytes()


def save_project(target_path: str, project_name: str = "chisurf_project"):
    """Save the current state of the application as a ``.cs.pto`` project.

    Works in headless mode (without GUI).
    """
    log = cs.logging
    gui = getattr(cs, "cs", None)
    project_path, project_name = _project_archive_path(target_path, project_name)
    project = get_project_payload(project_name)
    project_path = save_file(project, project_path)

    log.info(f"Project saved to {project_path}")
    try:
        if gui is not None:
            gui._current_project_path = project_path
            from chisurf.gui.project_helpers import add_recent_project

            add_recent_project(gui, project_path)
    except Exception:
        pass

    return project_path


def _write_fit_docx(
    fit_window,
    fit_group,
    local_fit,
    lf_dir: pathlib.Path,
    clean_name: str,
    fit_index: int,
) -> pathlib.Path | None:
    """Create a per-local-fit DOCX + screenshots inside the local-fit folder."""
    log = cs.logging
    try:
        import docx
        from docx.shared import Inches
    except Exception as exc:
        log.info(f"python-docx not available; skipping DOCX for {clean_name}: {exc}")
        return None

    widget = getattr(fit_window, "fit_widget", None)
    if widget is None or fit_group is None or local_fit is None:
        return None

    lf_dir.mkdir(parents=True, exist_ok=True)
    basename = lf_dir / clean_name

    document = docx.Document()
    document.add_heading(local_fit.name or clean_name, 0)

    # One fit => single section
    try:
        widget.selected_fit = fit_index
    except Exception:
        pass

    from chisurf.gui.widgets.models.model_editor import model_editor_widget

    for suffix, source in (
        ("_screenshot_fit.png", fit_window),
        ("_screenshot_model.png", model_editor_widget(local_fit.model)),
    ):
        png_path = basename.parent / f"{basename.name}{suffix}"
        if source is None:
            continue
        try:
            pix = source.grab()
            pix.save(str(png_path))
            del pix
            document.add_picture(str(png_path), width=Inches(2.0))
        except Exception as exc:
            log.debug(f"Could not add screenshot {png_path}: {exc}")

    # Compact summary table for this fit only
    document.add_heading("Summary", level=1)
    p = document.add_paragraph("Parameters: fitted in ")
    p.add_run("bold").bold = True
    p.add_run(", linked in ")
    p.add_run("italic.").italic = True
    p.add_run(" Fixed are plain.")

    table = document.add_table(rows=1, cols=2)
    hdr = table.rows[0].cells
    hdr[0].text = "Param"
    hdr[1].text = "#1"

    parameters = sorted(local_fit.model.parameters_all_dict.keys())
    for k in parameters:
        row = table.add_row().cells
        row[0].text = k
        try:
            val = local_fit.model.parameters_all_dict[k]
            run = row[1].paragraphs[0].add_run(f"{val.value:.3f}")
            if val.fixed:
                pass
            elif val.link is not None:
                run.italic = True
            else:
                run.bold = True
        except Exception:
            continue

    chi_row = table.add_row().cells
    chi_row[0].text = "Chi2r"
    try:
        chi_row[1].paragraphs[0].add_run(f"{local_fit.chi2r:.4f}")
    except Exception:
        pass

    docx_path = basename.with_suffix(".docx")
    document.save(str(docx_path))
    return docx_path


def _build_fitgroup_payload(
    fit_group,
    register_datacurve: typing.Callable[[cs.core.data.DataCurve], str],
    log: typing.Any,
    group_index: int = 0,
) -> typing.Tuple[str, typing.Dict]:
    """Helper to serialize a FitGroup into the Project payload.

    Works headlessly — no GUI window required.
    """
    if fit_group is None:
        return None, {}

    local_fits_state = []
    model_name = None
    model_module = None
    model_class_name = None

    grouped = getattr(fit_group, "grouped_fits", [])
    for local_fit in grouped:
        data_obj = getattr(local_fit, "data", None)
        ds_id = None
        if isinstance(data_obj, cs.core.data.DataCurve):
            ds_id = register_datacurve(data_obj)

        # Derive human-readable model label from experiment, if available
        if model_name is None and data_obj is not None:
            try:
                exp = getattr(data_obj, "experiment", None)
                mn = getattr(exp, "model_names", [])
                mc = getattr(exp, "model_classes", [])
                for name, cls in zip(mn, mc):
                    try:
                        if isinstance(local_fit.model, cls):
                            model_name = name
                            break
                    except Exception:
                        continue
            except Exception:
                pass

        # Capture per-fit model state and current x-range so that a
        # round-trip restores both parameters and fit limits.
        try:
            get_state = getattr(local_fit, "get_state", None)
            if callable(get_state):
                fit_state = get_state()
            else:
                fit_state = project_fit_state.fit_to_state(local_fit)
        except Exception as exc:
            log.warning(f"save_fit: could not serialize fit group #{group_index}: {exc}")
            fit_state = {}

        if model_module is None:
            model_module = str(fit_state.get("model_module") or type(local_fit.model).__module__)
            model_class_name = str(fit_state.get("model_class") or type(local_fit.model).__name__)
            if model_name is None:
                model_name = str(
                    getattr(type(local_fit.model), "name", "") or model_class_name
                ).strip()

        try:
            fr = getattr(local_fit, "fit_range", None)
            if isinstance(fr, tuple) and len(fr) == 2:
                fit_range = [int(fr[0]), int(fr[1])]
            else:
                fit_range = None
        except Exception:
            fit_range = None

        rec = {
            "dataset_id": ds_id,
            "fit_state": fit_state,
        }
        if fit_range is not None:
            rec["fit_range"] = fit_range

        local_fits_state.append(rec)

    fg_key = f"fitgroup_{group_index:03d}"
    return fg_key, {
        "type": "fit_group",
        "name": getattr(fit_group, "name", fg_key),
        "model_name": model_name,
        "model_module": model_module,
        "model_class": model_class_name,
        "data_group_name": str(getattr(getattr(fit_group, "_data", None), "name", "")),
        "local_fits": local_fits_state,
    }


def _build_fitgroup_payload_from_window(
    fit_window,
    register_datacurve: typing.Callable[[cs.core.data.DataCurve], str],
    log: typing.Any,
    group_index: int = 0,
) -> typing.Tuple[str, typing.Dict]:
    """Legacy wrapper: extract FitGroup from a GUI window, then delegate."""
    fit_group = getattr(fit_window, "fit", None)
    return _build_fitgroup_payload(fit_group, register_datacurve, log, group_index)


def _project_path(project_root: pathlib.Path, value: typing.Any) -> pathlib.Path | None:
    """Return an absolute path for a project-local path value."""
    if not isinstance(value, str) or not value:
        return None
    path = pathlib.Path(value)
    if not path.is_absolute():
        path = project_root / path
    return path


def _is_file_backed_dataset(payload: typing.Any) -> bool:
    """Return whether a project dataset describes an external file."""
    if not isinstance(payload, dict):
        return False
    fmt = str(payload.get("format", "")).lower()
    role = str(payload.get("role", "")).lower()
    if fmt in {"pdb", "pqr", "cif", "mmcif", "gro", "rmf", "rmf3", "fps.json", "json"}:
        return True
    return role in {"structure", "trajectory", "labeling_file", "labeling", "fps_json"}


def _restore_chimol_project_files(
    gui: typing.Any,
    project_root: pathlib.Path | None,
    ui_state: typing.Dict[str, typing.Any],
    log: typing.Any,
) -> None:
    """Open project-local Chimol files in a Chimol plugin window."""
    if gui is None or project_root is None:
        return
    chimol_state = ui_state.get("chimol") if isinstance(ui_state, dict) else None
    if not isinstance(chimol_state, dict):
        return
    open_files = chimol_state.get("open_files")
    if not isinstance(open_files, list) or not open_files:
        return

    paths: list[pathlib.Path] = []
    for item in open_files:
        path = _project_path(project_root, item)
        if path is None:
            continue
        suffixes = "".join(path.suffixes).lower()
        if suffixes.endswith(".fps.json"):
            continue
        if path.suffix.lower() not in {".pdb", ".pqr", ".cif", ".mmcif", ".gro", ".rmf", ".rmf3"}:
            continue
        if path.is_file():
            paths.append(path)
        else:
            log.warning(f"load_project: Chimol file does not exist: {path}")

    if not paths:
        return

    try:
        from chimol.hosts.qt.window import MolViewPluginWindow
    except Exception as exc:
        log.warning(f"load_project: could not import Chimol window: {exc}")
        return

    try:
        window = MolViewPluginWindow(parent=gui)
        window.resize(1000, 700)
        for path in paths:
            window.load_structure_from_path(path)
        window.show()
        refs = getattr(gui, "_project_chimol_windows", None)
        if refs is None:
            refs = []
            setattr(gui, "_project_chimol_windows", refs)
        refs.append(window)
    except Exception as exc:
        log.warning(f"load_project: could not restore Chimol files: {exc}")


def _resolve_project_local_model_state(
    state: typing.Any,
    project_root: pathlib.Path | None,
) -> typing.Any:
    """Resolve known model-state file paths relative to a project root."""
    if project_root is None or not isinstance(state, dict):
        return state
    proteinmc = state.get("proteinmc")
    if not isinstance(proteinmc, dict):
        return state
    for key in ("structure_source", "labeling_file", "output_file", "trajectory_file"):
        value = proteinmc.get(key)
        path = _project_path(project_root, value)
        if path is not None:
            proteinmc[key] = str(path)
    return state


def _fitgroup_plot_state(fit_group: typing.Any) -> typing.Dict[str, typing.Any]:
    """Return project-serializable plot/window state for a fit group."""
    try:
        import chisurf.gui as _gui_mod
    except Exception:
        return {}

    for fit_window in list(getattr(_gui_mod, "fit_windows", []) or []):
        try:
            if getattr(fit_window, "fit", None) is not fit_group:
                continue
            get_state = getattr(fit_window, "get_project_plot_state", None)
            if callable(get_state):
                state = get_state()
                if isinstance(state, dict):
                    return state
        except Exception:
            continue
    return {}


def _apply_pending_plot_state(
    fit_group: typing.Any, fit_record: typing.Dict[str, typing.Any]
) -> None:
    """Attach serialized plot state to a fit group for later GUI restoration."""
    if not isinstance(fit_record, dict):
        return
    state = fit_record.get("plot_state")
    if isinstance(state, dict) and state:
        try:
            setattr(fit_group, "_project_plot_state", state)
        except Exception:
            pass


def save_fit_project(target_path: str, fit_window=None, fit_name: str = "chisurf_project"):
    """Export one fit with the canonical detached codec and portable transport."""
    gui = getattr(cs, "cs", None)
    if fit_window is None and gui is not None:
        fit_window = getattr(gui.mdiarea, "currentSubWindow", lambda: None)()
    fit_group = (
        getattr(fit_window, "fit", None)
        if fit_window is not None
        else (cs.fits[-1] if cs.fits else None)
    )
    if fit_group is None:
        raise ValueError("No fit is available to save")
    members = list(getattr(fit_group, "grouped_fits", None) or [fit_group])
    data = cs.core.data.DataCurveGroup([member.data for member in members], name=fit_name)
    project = capture_session([data], [fit_group], name=fit_name)
    project.metadata["document_kind"] = "fit"
    project_path, _name = _project_archive_path(target_path, fit_name)
    return save_file(project, project_path)


def load_project_payload(
    proj: CSProject,
    project_path: typing.Optional[str] = None,
    _skip_gui_creation: bool = False,
    _history_transaction: bool = True,
):
    """Replace science through its authoritative owner, returning normalized UIDs."""
    del _skip_gui_creation, _history_transaction
    from chisurf.core.project.transition import replace_project

    gui = getattr(cs, "cs", None)
    document = getattr(gui, "_get_project_document", lambda: None)()
    staged = (
        document.stage_file_save(proj, project_path)
        if document is not None and project_path is not None
        else None
    )
    return replace_project(
        proj,
        gui=gui,
        document=document,
        target_identity=staged,
        project_path=project_path,
        present=restore_gui_from_fits if gui is not None else None,
    )


def load_fit_project(project_path: str):
    """Import detached fit state without replacing any existing live fits."""
    archive_path = _project_archive_input_path(project_path)
    project = _load_project_archive(str(archive_path))
    restored = restore_session(project)
    existing = capture_session(cs.imported_datasets, cs.fits)
    existing_fit_ids = {record["uid"] for record in existing.fits}
    incoming_fit_ids = {record["uid"] for record in project.fits}
    if existing_fit_ids & incoming_fit_ids or set(existing.datasets) & set(project.datasets):
        raise ValueError("Imported fit or dataset UIDs already exist in the live session")
    old_datasets, old_fits = list(cs.imported_datasets), list(cs.fits)
    try:
        cs.imported_datasets[:] = old_datasets + restored.datasets
        cs.fits[:] = old_fits + restored.fits
    except Exception:
        cs.imported_datasets[:] = old_datasets
        cs.fits[:] = old_fits
        raise
    return restored


def _load_project_archive(project_path: str) -> CSProject:
    """Load a full project from a ``.cs.pto`` container."""
    return load_file(_project_archive_input_path(project_path))


def load_project_data(project_path: str) -> list:
    """Restore datasets and fits into cs.fits/cs.imported_datasets.

    No Qt operations — safe to call from any thread or context.

    Parameters
    ----------
    project_path : str
        Path to the ``.cs.pto`` project.

    Returns
    -------
    list of str
        UIDs of the fits that were restored.
    """
    proj = _load_project_archive(project_path)
    result = load_project_payload(proj, project_path, _skip_gui_creation=True)
    return result.get("fit_uids", [])


def restore_gui_from_fits(
    fit_uids: list,
    ui_state: dict | None = None,
    *,
    main_window=None,
    fits=None,
):
    """Stage replacement MDI windows and return reversible synchronous publication.

    Parameters
    ----------
    fit_uids : list of str
        Installed authoritative fit identities, in canonical order.
    ui_state : dict, optional
        Canonical presentation and selection state.

    Returns
    -------
    PreparedPresentation or None
        Reversible window publication for the owner transaction; None headlessly.
        Original windows remain alive until the caller accepts the transaction.
    """
    import sys

    from chisurf.core.project.transition import PreparedPresentation, ProjectTransitionError

    main_window = main_window if main_window is not None else getattr(cs, "cs", None)
    if main_window is None:
        return None
    area = getattr(main_window, "mdiarea", None)
    old_windows = list(area.subWindowList()) if area is not None else []
    old_visibility = [(window, window.isVisible()) for window in old_windows]
    gui_module = sys.modules.get("chisurf.gui")
    registry = getattr(gui_module, "fit_windows", None)
    old_registry = list(registry) if registry is not None else []
    layouts = [
        getattr(main_window, name, None)
        for name in (
            "modelLayout",
            "analysisHeaderLayout",
            "plotOptionsLayout",
        )
    ]
    old_controls = [
        (layout, index, widget, widget.isVisible())
        for layout in layouts
        if layout is not None
        for index in range(layout.count())
        if (widget := layout.itemAt(index).widget()) is not None
    ]
    old_widgets = {widget for _layout, _index, widget, _visible in old_controls}
    previous_fit = getattr(main_window, "current_fit", None)
    previous_index = getattr(main_window, "_fit_idx", -1)
    from chisurf.core.project.ui_state import get_ui_state, set_ui_state

    previous_ui = get_ui_state(main_window)
    previous_active = area.activeSubWindow() if area is not None else None
    window_geometry = [(window, window.geometry()) for window in old_windows]
    previous_title = getattr(main_window, "windowTitle", lambda: None)()
    previous_runtime = {
        name: (name in vars(main_window), getattr(main_window, name, None))
        for name in ("_current_dataset", "_current_model_class", "current_fit_widget")
    }
    model_combo = getattr(main_window, "comboBox_Model", None)
    model_items = (
        [(model_combo.itemText(i), model_combo.itemData(i)) for i in range(model_combo.count())]
        if model_combo is not None
        else []
    )
    model_index = model_combo.currentIndex() if model_combo is not None else -1
    selector_states = []
    for name in ("dataset_selector", "fit_selector"):
        selector = getattr(main_window, name, None)
        if selector is None or not callable(getattr(selector, "topLevelItemCount", None)):
            continue
        roots = [selector.topLevelItem(i) for i in range(selector.topLevelItemCount())]
        expanded = []
        pending = list(roots)
        while pending:
            item = pending.pop()
            expanded.append((item, item.isExpanded()))
            pending.extend(item.child(i) for i in range(item.childCount()))
        selector_states.append(
            (
                selector,
                roots,
                selector.currentItem(),
                selector.selectedItems(),
                expanded,
                selector.horizontalScrollBar().value(),
                selector.verticalScrollBar().value(),
            )
        )

    def rollback_windows():
        """Discard staged views and reinstate original live windows and controls."""
        main_window.current_fit = previous_fit
        main_window._fit_idx = previous_index
        if area is not None:
            blocked = area.blockSignals(True)
            try:
                for window in list(area.subWindowList()):
                    if window not in old_windows:
                        area.removeSubWindow(window)
                        window.close_confirm = False
                        window.close()
                for window, visible in old_visibility:
                    if window not in area.subWindowList():
                        area.addSubWindow(window)
                    window.setVisible(visible)
            finally:
                area.blockSignals(blocked)
        if registry is not None:
            registry[:] = old_registry
        for layout in layouts:
            if layout is None:
                continue
            for index in reversed(range(layout.count())):
                widget = layout.itemAt(index).widget()
                if widget is not None and widget not in old_widgets:
                    layout.removeWidget(widget)
                    widget.hide()
                    widget.deleteLater()
        for layout, index, widget, visible in old_controls:
            if layout.indexOf(widget) < 0:
                layout.insertWidget(index, widget)
            widget.setVisible(visible)
        main_window.current_fit = previous_fit
        main_window._fit_idx = previous_index
        set_ui_state(main_window, previous_ui)
        for window, geometry in window_geometry:
            window.setGeometry(geometry)
        if area is not None and previous_active is not None:
            blocked = area.blockSignals(True)
            try:
                area.setActiveSubWindow(previous_active)
            finally:
                area.blockSignals(blocked)
        for selector, roots, current, selected, expanded, horizontal, vertical in selector_states:
            blocked = selector.blockSignals(True)
            selection = selector.selectionModel()
            selection_blocked = selection.blockSignals(True)
            try:
                # Keep the exact old items (including tooltip callbacks), even
                # when failure occurred before all old rows were detached.
                for index in reversed(range(selector.topLevelItemCount())):
                    if selector.topLevelItem(index) not in roots:
                        selector.takeTopLevelItem(index)
                for index, item in enumerate(roots):
                    position = selector.indexOfTopLevelItem(item)
                    if position != index:
                        if position >= 0:
                            selector.takeTopLevelItem(position)
                        selector.insertTopLevelItem(index, item)
                selector.setCurrentItem(current)
                selector.clearSelection()
                for item in selected:
                    item.setSelected(True)
                for item, was_expanded in expanded:
                    item.setExpanded(was_expanded)
                selector.horizontalScrollBar().setValue(horizontal)
                selector.verticalScrollBar().setValue(vertical)
            finally:
                selection.blockSignals(selection_blocked)
                selector.blockSignals(blocked)
        if model_combo is not None:
            blocked = model_combo.blockSignals(True)
            try:
                model_combo.clear()
                for text, data in model_items:
                    model_combo.addItem(text, data)
                model_combo.setCurrentIndex(model_index)
            finally:
                model_combo.blockSignals(blocked)
        for name, (existed, value) in previous_runtime.items():
            if existed:
                setattr(main_window, name, value)
            elif name in vars(main_window):
                delattr(main_window, name)
        if previous_title is not None:
            main_window.setWindowTitle(previous_title)

    try:
        # Selector.update clears and destroys its items. Detach originals before
        # any window construction or publication callback can refresh them.
        for selector, roots, *_rest in selector_states:
            blocked = selector.blockSignals(True)
            selection = selector.selectionModel()
            selection_blocked = selection.blockSignals(True)
            try:
                for _item in roots:
                    selector.takeTopLevelItem(0)
            finally:
                selection.blockSignals(selection_blocked)
                selector.blockSignals(blocked)
        if area is not None:
            for window in old_windows:
                area.removeSubWindow(window)
                window.hide()
        installed = {
            str(getattr(fit, "unique_identifier", getattr(fit, "uid", ""))): fit
            for fit in (cs.fits if fits is None else fits)
        }
        for uid in fit_uids:
            fit_obj = installed.get(str(uid))
            if fit_obj is None:
                raise ProjectTransitionError(
                    f"Restored fit {uid!r} is not available for presentation"
                )
            main_window._open_fit_subwindow(fit_obj, restored=True)
            if area is not None and not any(
                getattr(window, "fit", None) is fit_obj
                or str(
                    getattr(
                        getattr(window, "fit", None),
                        "unique_identifier",
                        getattr(getattr(window, "fit", None), "uid", ""),
                    )
                )
                == str(uid)
                for window in area.subWindowList()
            ):
                raise ProjectTransitionError(f"Window construction failed for fit {uid!r}")
    except Exception:
        rollback_windows()
        raise

    def publish_windows():
        """Apply selection and refresh views before the owner accepts science."""
        if registry is not None:
            registry[:] = [window for window in registry if window not in old_windows]
        for window in old_windows:
            window.setParent(None)
        for layout, _index, widget, _visible in old_controls:
            layout.removeWidget(widget)
            widget.hide()
            widget.setParent(None)
        state = ui_state or {}
        selected = state.get("current_fit_index")
        selected_uid = state.get("current_fit_uid")
        if selected_uid is not None:
            selected = next(
                (i for i, uid in enumerate(fit_uids) if str(uid) == str(selected_uid)), -1
            )
        selected = -1 if selected is None else selected
        main_window.current_fit = (
            installed.get(str(fit_uids[selected])) if 0 <= selected < len(fit_uids) else None
        )
        main_window._fit_idx = selected
        if state:
            set_ui_state(main_window, state)
        for selector_name in ("dataset_selector", "fit_selector"):
            selector = getattr(main_window, selector_name, None)
            if selector is not None:
                selector.update()
        changed = getattr(main_window, "onCurrentDatasetChanged", None)
        if callable(changed):
            changed()
        if not fit_uids and hasattr(main_window, "current_fit_widget"):
            main_window.current_fit_widget = None

    def finalize_windows():
        """Retire detached view resources only after the scientific owner accepts."""
        from qtpy import QtCore

        try:
            from qtpy import sip
        except ImportError:
            try:
                from PyQt5 import sip
            except ImportError:
                try:
                    import sip
                except ImportError:
                    sip = None

        def _is_deleted(w):
            if sip is not None:
                try:
                    return bool(sip.isdeleted(w))
                except Exception:
                    pass
            try:
                w.objectName()
                return False
            except RuntimeError:
                return True

        retired = set()
        for widget in [*old_windows, *old_widgets]:
            if id(widget) in retired or _is_deleted(widget):
                continue
            retired.add(id(widget))
            for timer in widget.findChildren(QtCore.QTimer):
                timer.stop()
            # Deferred deletion also releases externally hosted plot controls
            # through their existing destroyed callbacks. Do not call close():
            # those handlers can dispatch removal into the newly installed fit.
            widget.hide()
            widget.deleteLater()

    return PreparedPresentation(
        commit=publish_windows,
        rollback=rollback_windows,
        finalize=finalize_windows,
    )


def load_project(project_path: str):
    """Replace science and its synchronous presentation through one owner transaction."""
    from chisurf.server.services.projects import _public_transition

    archive_path = _project_archive_input_path(project_path)
    from chisurf.core.api._proxies import ProxyDatasetList, ProxyFitList
    from chisurf.core.project import storage

    client = None
    if isinstance(cs.imported_datasets, ProxyDatasetList) and isinstance(cs.fits, ProxyFitList):
        client = getattr(cs, "__client__", None)
        if client is None:
            raise RuntimeError("Installed proxies have no authoritative client")
    return _public_transition(
        cs,
        lambda: (storage.load_file(archive_path), str(archive_path)),
        client=client,
    )
