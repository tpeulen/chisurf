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
            write_2cde_container,
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

        warnings = _window_warnings(tttrs, cfg, workflow_context)

        column = column_for_variant(cfg.variant)
        output_paths: dict[str, str] = {}
        if write_output:
            containers = write_2cde_container(
                df_v,
                cfg.variant,
                parameters=asdict(cfg),
                analysis_folder=resolved_folder,
            )
            output_paths["containers"] = ", ".join(containers)

        valid = int(np.isfinite(df_v[column]).sum()) if column in df_v else 0
        result = TwoCdeResult(
            files=sorted(str(path) for path in tttrs.keys()),
            n_bursts_total=int(len(df_v)),
            n_bursts_valid=valid,
            output_paths=output_paths,
            settings_applied=asdict(cfg),
            warnings=warnings,
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
    """2CDE settings: explicit ones, else the workflow setup's FRET pair
    (:func:`~chisurf.core.fluorescence.burst.streams.fret_pair_from_workflow`)."""
    if settings:
        return TwoCdeSettings(**settings)
    from chisurf.core.fluorescence.burst.streams import fret_pair_from_workflow

    return TwoCdeSettings(**fret_pair_from_workflow(workflow_context)["settings"])


def _window_warnings(tttrs: dict, cfg: TwoCdeSettings, workflow_context: dict | None) -> list[str]:
    """The excitation-window pre-flight of the streams 2CDE applies, with the workflow setup's
    detectors that share their routing channels."""
    from chisurf.core.fluorescence.burst.streams import (
        fret_pair_from_workflow,
        preflight_detectors,
        window_warnings,
    )

    from ..core.computation import applied_streams

    pair = fret_pair_from_workflow(workflow_context)
    streams = applied_streams(
        cfg.variant,
        cfg.donor_channels,
        cfg.donor_micro_time_ranges,
        cfg.acceptor_channels,
        cfg.acceptor_micro_time_ranges,
        cfg.acceptor_excitation_channels or None,
        cfg.acceptor_excitation_micro_time_ranges or None,
        names=pair["names"],
    )
    return window_warnings(tttrs, preflight_detectors(streams, pair["detectors"]))


def _service_error(message: str) -> dict[str, Any]:
    """Return a ServiceDispatcher-compatible error envelope."""
    try:
        from chisurf.server.services import OPERATION_FAILED, service_error

        return service_error(message, error_code=OPERATION_FAILED)
    except Exception:
        return {"ok": False, "error": message}
