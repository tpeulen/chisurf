"""ServiceDispatcher-compatible RPC handlers for 2CDE."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..api.contract import (
    METHOD_COMPUTE_2CDE,
    METHOD_DESCRIBE_CONTRACT,
    contract_descriptor,
    service_success,
)
from ..api.models import TwoCdeResult, TwoCdeSettings
from ..api.serialization import to_jsonable

METHOD_PREPARE_WORKFLOW = "burst_2cde.workflow.prepare"


def register_services(dispatcher: Any) -> None:
    """Register 2CDE RPC handlers with a ServiceDispatcher."""
    dispatcher.register(METHOD_COMPUTE_2CDE, lambda params: compute_2cde_handler(**(params or {})))
    dispatcher.register(
        METHOD_PREPARE_WORKFLOW, lambda params: prepare_workflow_handler(**(params or {}))
    )
    dispatcher.register(METHOD_DESCRIBE_CONTRACT, lambda params: contract_handler(**(params or {})))


def list_methods() -> dict[str, str]:
    """Return 2CDE RPC method descriptions."""
    return {
        METHOD_COMPUTE_2CDE: "Compute the FRET-2CDE / ALEX-2CDE burst feature.",
        METHOD_PREPARE_WORKFLOW: "Resolve 2CDE settings and folders from a burst workflow context.",
        METHOD_DESCRIBE_CONTRACT: "Return the 2CDE workflow contract.",
    }


def prepare_workflow_handler(
    workflow_context: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
    analysis_folder: str | None = None,
    files: list[str] | None = None,
) -> dict[str, Any]:
    """Resolve 2CDE inputs from explicit params plus a workflow context."""
    try:
        resolved_folder = _resolve_analysis_folder(
            analysis_folder=analysis_folder,
            files=files,
            workflow_context=workflow_context,
        )
        two_cde_settings = _settings_from_workflow(settings, workflow_context)
        return service_success(
            {
                "analysis_folder": str(resolved_folder) if resolved_folder else None,
                "settings": asdict(two_cde_settings),
                "workflow_context": workflow_context or {},
            }
        )
    except Exception as exc:
        return _service_error(str(exc))


def compute_2cde_handler(
    files: list[str] | None = None,
    analysis_folder: str | None = None,
    pattern: str = "bi4_bur",
    settings: dict[str, Any] | None = None,
    workflow_context: dict[str, Any] | None = None,
    write_output: bool = True,
) -> dict[str, Any]:
    """Compute the 2CDE feature from explicit parameters or a workflow handoff."""
    try:
        import numpy as np

        from ..core.computation import (
            column_for_variant,
            compute_2cde,
            read_burst_analysis,
            write_2cde_analysis,
        )

        resolved_folder = _resolve_analysis_folder(
            analysis_folder=analysis_folder,
            files=files,
            workflow_context=workflow_context,
        )
        if resolved_folder is None:
            raise ValueError("No 2CDE analysis folder provided or found in workflow_context.")

        cfg = _settings_from_workflow(settings, workflow_context)
        df, tttrs = read_burst_analysis(resolved_folder, cfg.file_type, pattern=pattern)
        df_v = compute_2cde(
            df,
            tttrs,
            donor_channels=cfg.donor_channels,
            donor_micro_time_ranges=cfg.donor_micro_time_ranges,
            acceptor_channels=cfg.acceptor_channels,
            acceptor_micro_time_ranges=cfg.acceptor_micro_time_ranges,
            acceptor_excitation_channels=cfg.acceptor_excitation_channels or None,
            acceptor_excitation_micro_time_ranges=cfg.acceptor_excitation_micro_time_ranges or None,
            tau=cfg.tau,
            kernel=cfg.kernel,
            variant=cfg.variant,
        )

        column = column_for_variant(cfg.variant)
        output_paths: dict[str, str] = {}
        if write_output:
            write_2cde_analysis(df_v, str(resolved_folder), variant=cfg.variant)
            output_paths["2cde_folder"] = str(resolved_folder / "2cde")

        valid = int(np.isfinite(df_v[column]).sum()) if column in df_v else 0
        result = TwoCdeResult(
            files=sorted(str(path) for path in tttrs.keys()),
            n_bursts_total=int(len(df_v)),
            n_bursts_valid=valid,
            output_paths=output_paths,
            settings_applied=asdict(cfg),
        )
        payload = to_jsonable(result)
        payload["analysis_folder"] = str(resolved_folder)
        payload["workflow_context"] = workflow_context or {}
        return service_success(payload)
    except Exception as exc:
        return _service_error(str(exc))


def contract_handler() -> dict[str, Any]:
    """Return the 2CDE workflow contract descriptor."""
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
    """Resolve the burst analysis folder from supported inputs."""
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
) -> TwoCdeSettings:
    """Build 2CDE settings, deriving detector channels from workflow context."""
    if settings:
        return TwoCdeSettings(**settings)

    channel_settings = {}
    if workflow_context:
        channel_settings = workflow_context.get("channel_settings") or {}
    detectors = channel_settings.get("detectors") or {}
    tttr_reading = channel_settings.get("tttr_reading") or {}
    detector_values = list(detectors.values())

    kwargs: dict[str, Any] = {}
    if detector_values:
        donor = detector_values[0]
        kwargs["donor_channels"] = list(donor.get("chs", [0, 8]))
        kwargs["donor_micro_time_ranges"] = _ranges(donor.get("micro_time_ranges", [(0, 32768)]))
    if len(detector_values) > 1:
        acceptor = detector_values[1]
        kwargs["acceptor_channels"] = list(acceptor.get("chs", [1, 9]))
        kwargs["acceptor_micro_time_ranges"] = _ranges(
            acceptor.get("micro_time_ranges", [(0, 32768)])
        )
    if tttr_reading.get("file_type"):
        kwargs["file_type"] = str(tttr_reading["file_type"])
    return TwoCdeSettings(**kwargs)


def _ranges(value: Any) -> list[tuple[int, int]]:
    """Normalize JSON/list micro-time ranges to tuples."""
    ranges: list[tuple[int, int]] = []
    for item in value or []:
        if len(item) >= 2:
            ranges.append((int(item[0]), int(item[1])))
    return ranges or [(0, 32768)]


def _service_error(message: str) -> dict[str, Any]:
    """Return a ServiceDispatcher-compatible error envelope."""
    try:
        from chisurf.server.services import OPERATION_FAILED, service_error

        return service_error(message, error_code=OPERATION_FAILED)
    except Exception:
        return {"ok": False, "error": message}
