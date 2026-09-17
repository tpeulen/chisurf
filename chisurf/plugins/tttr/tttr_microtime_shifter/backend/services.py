"""ServiceDispatcher-compatible RPC handlers for Micro-time Shifter.

These are thin adapters that accept JSON-compatible params, delegate to
the ``api/`` layer, and return JSON-safe results.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..api.contract import (
    METHOD_APPLY,
    METHOD_DESCRIBE_CONTRACT,
    METHOD_HISTOGRAM,
    METHOD_IDENTIFY,
    METHOD_LOAD_METADATA,
    contract_descriptor,
    service_success,
    shift_request_from_payload,
)
from ..api.mmfdb import MicrotimeShiftMMFDBPipeline
from ..api.models import ShiftResult
from ..api.shift import load_file_metadata, load_histogram, shift_file

if TYPE_CHECKING:
    from mmfdb.security.base import MMFDBClientBase
    from mmfdb.security.session import SessionContext


def register_services(
    dispatcher: Any,
    *,
    mmfdb_db: MMFDBClientBase | None = None,
    mmfdb_db_provider: Callable[[], MMFDBClientBase | None] | None = None,
    mmfdb_session: SessionContext | None = None,
    mmfdb_session_provider: Callable[[], SessionContext | None] | None = None,
) -> None:
    """Register Micro-time Shifter RPC handlers with a ServiceDispatcher.

    Parameters
    ----------
    dispatcher : ServiceDispatcher
        The server's service dispatcher.

    """
    dispatcher.register(
        METHOD_APPLY,
        lambda params: apply_handler(
            **params,
            mmfdb_db=(
                _provided_db(mmfdb_db, mmfdb_db_provider)
                if (params.get("mmfdb") or {}).get("enabled")
                else mmfdb_db
            ),
            mmfdb_session=(
                _provided_session(mmfdb_session, mmfdb_session_provider)
                if (params.get("mmfdb") or {}).get("enabled")
                else mmfdb_session
            ),
        ),
    )
    dispatcher.register(
        METHOD_LOAD_METADATA,
        lambda params: load_metadata_handler(**params),
    )
    dispatcher.register(
        METHOD_IDENTIFY,
        lambda params: identify_handler(
            **params,
            mmfdb_db=_provided_db(mmfdb_db, mmfdb_db_provider),
        ),
    )
    dispatcher.register(
        METHOD_HISTOGRAM,
        lambda params: histogram_handler(**params),
    )
    dispatcher.register(
        METHOD_DESCRIBE_CONTRACT,
        lambda params: contract_handler(**(params or {})),
    )


def list_methods() -> dict[str, str]:
    """Return the Micro-time Shifter RPC method catalogue."""
    return {
        METHOD_APPLY: "Apply micro-time shifts to TTTR files.",
        METHOD_LOAD_METADATA: "Return routing channels and n_mt for a file.",
        METHOD_IDENTIFY: "Look up a file in the MMFDB object store.",
        METHOD_HISTOGRAM: "Return shifted histogram data for preview.",
        METHOD_DESCRIBE_CONTRACT: "Return the workflow contract.",
    }


def apply_handler(
    files: list[str],
    global_shift: int = 0,
    channel_shifts: dict[str, int] | None = None,
    filetype: str | None = None,
    output_dir: str | None = None,
    mmfdb: dict[str, Any] | None = None,
    mmfdb_db: MMFDBClientBase | None = None,
    mmfdb_session: SessionContext | None = None,
) -> dict[str, Any]:
    """Apply micro-time shifts to TTTR files.

    Parameters
    ----------
    files : list of str
        TTTR file paths.
    global_shift : int
        Global micro-time shift.
    channel_shifts : dict, optional
        Per-channel shifts.
    filetype : str, optional
        Explicit TTTR file type.
    output_dir : str, optional
        Output directory.
    mmfdb : dict, optional
        MMFDB archival context.

    Returns
    -------
    dict
        JSON-serializable ServiceResult.

    """
    try:
        import os
        import shutil
        import tempfile

        request = shift_request_from_payload(
            {
                "files": files,
                "global_shift": global_shift,
                "channel_shifts": channel_shifts or {},
                "filetype": filetype,
                "output_dir": output_dir,
                "mmfdb": mmfdb or {},
            }
        )
        result = ShiftResult()
        norm_ch = {int(k): int(v) for k, v in (channel_shifts or {}).items()}

        # Archive-only requests use a temporary working directory. When the
        # caller supplied an output directory, preserve those files and return
        # usable paths in addition to MMFDB artifact IDs.
        use_temp_dir = bool(request.mmfdb.enabled and not request.output_dir)
        temp_dir = None
        target_output_dir = request.output_dir
        if use_temp_dir:
            temp_dir = tempfile.mkdtemp()
            target_output_dir = temp_dir

        try:
            for path in request.files:
                out_path, applied = shift_file(
                    path,
                    global_shift=request.global_shift,
                    channel_shifts=norm_ch,
                    filetype=request.filetype,
                    output_dir=target_output_dir,
                )
                norm_in = str(Path(path).expanduser().resolve())
                result.output_paths_by_file[norm_in] = out_path
                result.applied_shifts_by_file[norm_in] = {
                    "global_shift": request.global_shift,
                    "channel_shifts": {int(k): int(v) for k, v in applied.items()},
                }

            if request.mmfdb.enabled:
                registration = MicrotimeShiftMMFDBPipeline(
                    db=mmfdb_db,
                    session=mmfdb_session,
                ).register_run(request, result)
                result.mmfdb_artifacts = {
                    "input_artifacts": registration.input_artifacts,
                    "output_artifacts": registration.output_artifacts,
                }
                result.warnings.extend(registration.warnings)
        finally:
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
        if temp_dir:
            # Never expose paths that the service has just deleted. Archive-only
            # callers consume the explicit MMFDB artifact IDs instead.
            result.output_paths_by_file.clear()

        return service_success(result)
    except Exception as exc:
        from chisurf.server.services import OPERATION_FAILED, service_error

        return service_error(str(exc), error_code=OPERATION_FAILED)


def load_metadata_handler(
    path: str,
) -> dict[str, Any]:
    """Return routing channels and n_mt for a TTTR file.

    Parameters
    ----------
    path : str
        TTTR file path.

    Returns
    -------
    dict
        JSON-serializable ServiceResult.

    """
    try:
        metadata = load_file_metadata(path)
        return service_success(metadata)
    except Exception as exc:
        from chisurf.server.services import OPERATION_FAILED, service_error

        return service_error(str(exc), error_code=OPERATION_FAILED)


def identify_handler(
    path: str,
    mmfdb_db: MMFDBClientBase | None = None,
) -> dict[str, Any]:
    """Look up a file in the MMFDB object store.

    Parameters
    ----------
    path : str
        TTTR file path.

    Returns
    -------
    dict
        Service result with ``found``, ``artifact_id``, ``is_new`` flags.

    """
    try:
        from ..api.mmfdb import MicrotimeShiftMMFDBPipeline, _file_md5

        pipeline = MicrotimeShiftMMFDBPipeline(db=mmfdb_db)
        md5 = _file_md5(path)
        artifact_id = pipeline._find_raw_artifact_by_md5(md5)
        return service_success(
            {
                "path": path,
                "found": bool(artifact_id),
                "artifact_id": artifact_id or "",
                "md5": md5,
            }
        )
    except Exception as exc:
        from chisurf.server.services import OPERATION_FAILED, service_error

        return service_error(str(exc), error_code=OPERATION_FAILED)


def _provided_db(
    db: MMFDBClientBase | None,
    provider: Callable[[], MMFDBClientBase | None] | None,
) -> MMFDBClientBase | None:
    """Resolve a request-scoped database supplied by the composition root."""
    return provider() if provider is not None else db


def _provided_session(
    session: SessionContext | None,
    provider: Callable[[], SessionContext | None] | None,
) -> SessionContext | None:
    """Resolve a request-scoped authenticated session."""
    return provider() if provider is not None else session


def histogram_handler(
    path: str | list[str],
    global_shift: int = 0,
    channel_shifts: dict[str, int] | None = None,
    filetype: str | None = None,
) -> dict[str, Any]:
    """Return shifted histogram data for GUI preview.

    Parameters
    ----------
    path : str or list of str
        TTTR file path(s).
    global_shift : int
        Global micro-time shift.
    channel_shifts : dict, optional
        Per-channel shifts.
    filetype : str, optional
        Explicit TTTR file type.

    Returns
    -------
    dict
        JSON-serializable ServiceResult with histogram data.

    """
    try:
        norm_ch = {int(k): int(v) for k, v in (channel_shifts or {}).items()}
        histogram = load_histogram(
            path,
            global_shift=global_shift,
            channel_shifts=norm_ch,
            filetype=filetype,
        )
        return service_success(histogram)
    except Exception as exc:
        from chisurf.server.services import OPERATION_FAILED, service_error

        return service_error(str(exc), error_code=OPERATION_FAILED)


def contract_handler() -> dict[str, Any]:
    """Return the Micro-time Shifter workflow contract descriptor."""
    return service_success(contract_descriptor())
