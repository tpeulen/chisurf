"""ServiceDispatcher-compatible RPC handlers for BVA."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from chisurf.core.datastore import numeric_column, row_count

from ..api.contract import (
    METHOD_COMPUTE_BVA,
    METHOD_DESCRIBE_CONTRACT,
    contract_descriptor,
    service_success,
)
from ..api.models import BvaResult, BvaSettings
from ..api.serialization import to_jsonable

METHOD_PREPARE_WORKFLOW = "burst_bva.workflow.prepare"


def register_services(dispatcher: Any) -> None:
    """Register BVA RPC handlers with a ServiceDispatcher."""
    dispatcher.register(METHOD_COMPUTE_BVA, lambda params: compute_bva_handler(**(params or {})))
    dispatcher.register(
        METHOD_PREPARE_WORKFLOW, lambda params: prepare_workflow_handler(**(params or {}))
    )
    dispatcher.register(METHOD_DESCRIBE_CONTRACT, lambda params: contract_handler(**(params or {})))


def list_methods() -> dict[str, str]:
    """Return BVA RPC method descriptions."""
    return {
        METHOD_COMPUTE_BVA: "Run Burst Variance Analysis over burst data.",
        METHOD_PREPARE_WORKFLOW: "Resolve BVA settings and folders from a burst workflow context.",
        METHOD_DESCRIBE_CONTRACT: "Return the BVA workflow contract.",
    }


def prepare_workflow_handler(
    workflow_context: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
    analysis_folder: str | None = None,
    files: list[str] | None = None,
) -> dict[str, Any]:
    """Resolve BVA inputs from explicit params plus a workflow context."""
    try:
        resolved_folder = _resolve_analysis_folder(
            analysis_folder=analysis_folder,
            files=files,
            workflow_context=workflow_context,
        )
        bva_settings = _settings_from_workflow(settings, workflow_context)
        return service_success(
            {
                "analysis_folder": str(resolved_folder) if resolved_folder else None,
                "settings": asdict(bva_settings),
                "workflow_context": workflow_context or {},
            }
        )
    except Exception as exc:
        return _service_error(str(exc))


def compute_bva_handler(
    files: list[str] | None = None,
    analysis_folder: str | None = None,
    pattern: str = "bi4_bur",
    settings: dict[str, Any] | None = None,
    workflow_context: dict[str, Any] | None = None,
    write_output: bool = True,
) -> dict[str, Any]:
    """Run BVA analysis from explicit parameters or a workflow handoff."""
    try:
        from chisurf.core.fluorescence.burst.streams import window_warnings

        from ..core.computation import compute_bva, read_burst_analysis, write_bva_container

        resolved_folder = _resolve_analysis_folder(
            analysis_folder=analysis_folder,
            files=files,
            workflow_context=workflow_context,
        )
        if resolved_folder is None:
            raise ValueError("No BVA analysis folder provided or found in workflow_context.")

        bva_settings = _settings_from_workflow(settings, workflow_context)
        df, tttrs = read_burst_analysis(resolved_folder, bva_settings.file_type, pattern=pattern)
        df_v = compute_bva(
            df,
            tttrs,
            donor_channels=bva_settings.donor_channels,
            donor_micro_time_ranges=bva_settings.donor_micro_time_ranges,
            acceptor_channels=bva_settings.acceptor_channels,
            acceptor_micro_time_ranges=bva_settings.acceptor_micro_time_ranges,
            minimum_window_length=bva_settings.minimum_window_length,
            number_of_photons_per_slice=bva_settings.number_of_photons_per_slice,
        )

        warnings = window_warnings(tttrs, _preflight_detectors(bva_settings, workflow_context))

        output_paths: dict[str, str] = {}
        if write_output:
            containers = write_bva_container(
                df_v,
                parameters=asdict(bva_settings),
                analysis_folder=resolved_folder,
            )
            output_paths["containers"] = ", ".join(containers)

        valid = int((numeric_column(df_v, "Proximity Ratio Std") > 0).sum())
        result = BvaResult(
            files=sorted(str(path) for path in tttrs.keys()),
            n_bursts_total=row_count(df_v),
            n_bursts_valid=valid,
            output_paths=output_paths,
            settings_applied=asdict(bva_settings),
            warnings=warnings,
        )
        payload = to_jsonable(result)
        payload["analysis_folder"] = str(resolved_folder)
        payload["workflow_context"] = workflow_context or {}
        return service_success(payload)
    except Exception as exc:
        return _service_error(str(exc))


def contract_handler() -> dict[str, Any]:
    """Return the BVA workflow contract descriptor."""
    contract = contract_descriptor()
    contract.setdefault("rpc_methods", {})[METHOD_PREPARE_WORKFLOW] = {
        "input": "WorkflowContext",
        "output": "ServiceResult",
        "long_running": False,
    }
    return service_success(contract)


def _resolve_analysis_folder(
    *,
    analysis_folder: str | None,
    files: list[str] | None,
    workflow_context: dict[str, Any] | None,
) -> Path | None:
    """Resolve the legacy BVA analysis folder from supported inputs."""
    candidates: list[str] = []
    if analysis_folder:
        candidates.append(analysis_folder)
    if workflow_context:
        folder = workflow_context.get("burst_folder") or workflow_context.get("analysis_folder")
        if isinstance(folder, str):
            candidates.append(folder)
    if files:
        candidates.append(str(Path(files[0]).parent))

    for candidate in candidates:
        path = Path(candidate).expanduser()
        if path.exists() and path.is_dir():
            return path
    return Path(candidates[0]).expanduser() if candidates else None


def _settings_from_workflow(
    settings: dict[str, Any] | None,
    workflow_context: dict[str, Any] | None,
) -> BvaSettings:
    """BVA settings: explicit ones, else the workflow setup's FRET pair
    (:func:`~chisurf.core.fluorescence.burst.streams.fret_pair_from_workflow`)."""
    if settings:
        return BvaSettings(**settings)
    from chisurf.core.fluorescence.burst.streams import fret_pair_from_workflow

    return BvaSettings(**fret_pair_from_workflow(workflow_context)["settings"])


def _preflight_detectors(cfg: BvaSettings, workflow_context: dict[str, Any] | None) -> dict:
    """The donor and acceptor streams BVA applies, with the workflow setup's detectors that share
    their routing channels."""
    from chisurf.core.fluorescence.burst.streams import fret_pair_from_workflow, preflight_detectors

    pair = fret_pair_from_workflow(workflow_context)
    donor, acceptor = pair["names"]
    return preflight_detectors(
        {
            donor: (cfg.donor_channels, cfg.donor_micro_time_ranges),
            acceptor: (cfg.acceptor_channels, cfg.acceptor_micro_time_ranges),
        },
        pair["detectors"],
    )


def _service_error(message: str) -> dict[str, Any]:
    """Return a ServiceDispatcher-compatible error envelope."""
    try:
        from chisurf.server.services import OPERATION_FAILED, service_error

        return service_error(message, error_code=OPERATION_FAILED)
    except Exception:
        return {"ok": False, "error": message}
