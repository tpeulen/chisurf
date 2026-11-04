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
        context = dict(workflow_context or {})
        if not context.get("channel_settings") and resolved_folder:
            context["channel_settings"] = setup_from_run(resolved_folder)
        two_cde_settings = _settings_from_workflow(settings, context)
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

        context = dict(workflow_context or {})
        if not context.get("channel_settings"):
            context["channel_settings"] = setup_from_run(resolved_folder)
        cfg = _settings_from_workflow(settings, context)
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
            micro_time_resolution_ps=cfg.micro_time_resolution_ps,
            alex_donor_channel_ranges=cfg.alex_donor_channel_ranges,
            alex_acceptor_channel_ranges=cfg.alex_acceptor_channel_ranges,
            donor_macro_phase_ranges=cfg.donor_macro_phase_ranges,
            acceptor_macro_phase_ranges=cfg.acceptor_macro_phase_ranges,
            acceptor_excitation_macro_phase_ranges=cfg.acceptor_excitation_macro_phase_ranges,
            alternation_period_ticks=cfg.alternation_period_ticks,
            alternation_offset_ticks=cfg.alternation_offset_ticks,
            tau=cfg.tau,
            kernel=cfg.kernel,
            variant=cfg.variant,
        )

        warnings = _window_warnings(tttrs, cfg, context)

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


def settings_from_setup(setup: dict) -> dict:
    """Resolve the FRET detectors and excitation windows of a burst setup."""
    from tttrlib import ranges_to_inclusive

    from chisurf.core.fluorescence.burst.streams import fret_pair_from_workflow

    pair = fret_pair_from_workflow({"channel_settings": setup})
    result = dict(pair["settings"])
    result["micro_time_resolution_ps"] = pair["micro_time_resolution_ps"]
    phase = setup.get("alex_phase") or {}
    phase_windows = phase.get("windows_s") or {}
    tick = float(phase.get("macro_time_resolution_s") or 0)
    if tick and phase.get("period_s") and phase_windows.get("prompt") and phase_windows.get("delayed"):
        def ticks(seconds):
            value = float(seconds) / tick
            nearest = round(value)
            return float(nearest) if abs(value - nearest) < 1e-9 else value

        prompt_phase = tuple(ticks(x) for x in phase_windows["prompt"])
        delayed_phase = tuple(ticks(x) for x in phase_windows["delayed"])
        result.update(alternation_period_ticks=ticks(phase["period_s"]),
                      donor_macro_phase_ranges=[prompt_phase],
                      acceptor_macro_phase_ranges=[prompt_phase],
                      acceptor_excitation_macro_phase_ranges=[delayed_phase],
                      acceptor_excitation_channels=result.get("acceptor_channels", []))
        return result
    windows = setup.get("windows") or {}
    prompt, delayed = windows.get("prompt"), windows.get("delayed")
    detectors = pair["detectors"]

    def gated(detector, window):
        gates = detector.get("micro_time_ranges") or [window]
        intersections = [(max(int(a), int(window[0])), min(int(b), int(window[1])))
                         for a, b in gates]
        return [(a, b) for a, b in intersections if a < b]

    if prompt:
        acceptor = result.get("acceptor_channels", [1, 9])
        names = pair["names"]
        donor_gates = {}
        for role, name in zip(("donor", "acceptor"), names):
            ranges = gated(detectors.get(name, {}), prompt)
            if not ranges:
                raise ValueError(f"{role} detector gate does not overlap donor excitation")
            result[f"{role}_micro_time_ranges"] = ranges_to_inclusive(ranges)
            for channel in result.get(f"{role}_channels", []):
                donor_gates.setdefault(int(channel), []).extend(ranges_to_inclusive(ranges))
        result["alex_donor_channel_ranges"] = donor_gates
        if delayed:
            # A setup can split the same physical red detector into separate
            # prompt and delayed virtual detectors. Use all matching gates.
            per_channel = {}
            for channel in acceptor:
                matching = [d for d in detectors.values() if channel in d.get("chs", [])]
                ranges = sorted({tuple(r) for d in matching for r in gated(d, delayed)})
                if not matching:
                    ranges = [tuple(delayed)]
                per_channel[int(channel)] = ranges_to_inclusive(ranges)
            delayed_ranges = sorted({tuple(r) for ranges in per_channel.values() for r in ranges})
            result["acceptor_excitation_channels"] = [c for c in acceptor if per_channel[int(c)]]
            result["acceptor_excitation_micro_time_ranges"] = delayed_ranges
            result["alex_acceptor_channel_ranges"] = per_channel
    return result


def setup_from_run(address: str | Path) -> dict:
    """Read the detector and window settings recorded with a burst run."""
    from chisurf.core.fio.analysis_path import split_container_path
    from chisurf.core.fio.fluorescence.burst_container import burst_table_name
    from chisurf.core.fio.fluorescence.burst_manifest import read_analysis_manifest
    from chisurf.core.fio.pto import Measurement

    container, run = split_container_path(address)
    if container is not None:
        with Measurement.open(container, writable=False) as measurement:
            name = burst_table_name(measurement, run)
            uid = measurement._f.find(name) if name else 0
            recorded = measurement.provenance(uid)["settings"] if uid else {}
    else:
        manifest = read_analysis_manifest(address) or {}
        sources = manifest.get("sources") or []
        records = [s.get("settings") or {} for s in sources]
        if records and any(r != records[0] for r in records[1:]):
            raise ValueError("Burst sources have different detector setups; select one run at a time")
        recorded = records[0] if records else {}
    record = recorded.get("micro_time_windows") or {}
    windows = record.get("windows") or recorded.get("windows") or {}
    detectors = recorded.get("detectors") or {}
    reading = dict(recorded.get("tttr_reading") or {})
    width = record.get("micro_time_resolution_ps")
    if width:
        reading["micro_time_resolution"] = width
        reading["micro_time_resolution_unit"] = "ps"
    return {"windows": windows, "detectors": detectors, "tttr_reading": reading,
            "alex_phase": recorded.get("alex_phase") or {}}


def stale_results(address: str | Path) -> list[str]:
    """Find old 2CDE artifacts of this run whose excitation streams are unrecorded."""
    from chisurf.core.fio.analysis_path import split_container_path
    from chisurf.core.fio.fluorescence.burst_container import burst_table_name
    from chisurf.core.fio.pto import Measurement

    from ..core.computation import STREAM_ALGORITHM_VERSION

    container, run = split_container_path(address)
    if container is None or not container.exists():
        return []
    stale = set()
    with Measurement.open(container, writable=False) as measurement:
        parent = burst_table_name(measurement, run)
        parent_uid = measurement._f.find(parent) if parent else 0
        for artifact in measurement.artifacts():
            info = measurement.provenance(artifact.uid)
            if info["operation"] != "burst_2cde":
                continue
            if parent_uid and parent_uid not in info["parents"]:
                continue
            settings = info["settings"]
            if settings.get("stream_algorithm_version", 0) < STREAM_ALGORITHM_VERSION:
                stale.add(str(settings.get("variant") or artifact.name))
    return sorted(stale)


def _settings_from_workflow(
    settings: dict[str, Any] | None,
    workflow_context: dict[str, Any] | None,
) -> TwoCdeSettings:
    """2CDE settings: explicit ones, else the workflow setup's FRET pair
    (:func:`~chisurf.core.fluorescence.burst.streams.fret_pair_from_workflow`)."""
    cfg = settings_from_setup((workflow_context or {}).get("channel_settings") or {})
    cfg.update(settings or {})
    return TwoCdeSettings(**cfg)


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
    from chisurf.core.fluorescence.burst.streams import gates_record

    detectors = preflight_detectors(streams, pair["detectors"])
    return window_warnings(tttrs, gates_record(detectors, cfg.micro_time_resolution_ps), detectors)


def _service_error(message: str) -> dict[str, Any]:
    """Return a ServiceDispatcher-compatible error envelope."""
    try:
        from chisurf.server.services import OPERATION_FAILED, service_error

        return service_error(message, error_code=OPERATION_FAILED)
    except Exception:
        return {"ok": False, "error": message}
