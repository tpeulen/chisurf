"""MMFDB registration for Micro-time Shifter results."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mmfdb.provenance.result_registry import (
    register_raw_measurement,
    register_result,
)

from .contract import CONTRACT_VERSION
from .models import ShiftRequest, ShiftResult

if TYPE_CHECKING:
    from mmfdb.security.base import MMFDBClientBase
    from mmfdb.security.session import SessionContext

logger = logging.getLogger(__name__)


@dataclass
class ShiftRegistrationResult:
    """MMFDB artifact IDs created for one micro-time shift run.

    Attributes
    ----------
    input_artifacts : dict
        Raw input artifacts keyed by input file path.
    output_artifacts : dict
        Shifted output artifacts keyed by input file path.
    warnings : list
        Non-fatal registration warnings.

    """

    input_artifacts: dict[str, str] = field(default_factory=dict)
    output_artifacts: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _file_md5(path: str) -> str:
    """Return the MD5 content hash for a file.

    Parameters
    ----------
    path : str
        File path.

    Returns
    -------
    str
        Hex-encoded MD5 digest.

    """
    digest = hashlib.md5()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def active_mmfdb_connection() -> "MMFDBClientBase | None":
    """Open the configured MMFDB for a GUI composition root.

    This compatibility-named helper never reads the result registry's process
    global. Computational pipelines receive the returned connection explicitly.
    """
    try:
        from mmfdb.repository import MFDatabase
        from mmfdb.store.database_resolver import resolve_database_path

        return MFDatabase(resolve_database_path())
    except Exception as exc:  # pragma: no cover - environment-dependent
        logger.warning("failed to open MMFDB connection: %s", exc)
        return None


class MicrotimeShiftMMFDBPipeline:
    """Register Micro-time Shifter inputs and outputs in MMFDB."""

    def __init__(
        self,
        db: MMFDBClientBase | None = None,
        session: "SessionContext | None" = None,
    ):
        """Create a shift registration pipeline.

        Parameters
        ----------
        db : MMFDBClientBase, optional
            Explicit MMFDB connection. An enabled request without one is
            reported as a registration warning; no ambient database is used.

        """
        self.db = db
        self.session = session

    def _find_raw_artifact_by_md5(self, md5: str) -> str:
        """Look up an existing raw artifact by content hash.

        Parameters
        ----------
        md5 : str
            MD5 content hash.

        Returns
        -------
        str
            Artifact ID, or empty string if not found.

        """
        if self.db is None:
            return ""
        try:
            return self.db.find_raw_artifact_by_md5(md5)
        except Exception:
            return ""

    def _lookup_or_register_raw(
        self,
        path: str,
        request: ShiftRequest,
    ) -> tuple[str, bool]:
        """Look up or register a raw input artifact.

        Parameters
        ----------
        path : str
            Input file path.
        request : ShiftRequest
            Shift request with MMFDB context.

        Returns
        -------
        tuple of (str, bool)
            Artifact ID and whether it was newly registered.

        """
        normalized_sources = {
            str(Path(source_path).expanduser().resolve()): str(artifact_id)
            for source_path, artifact_id in request.mmfdb.source_artifact_ids.items()
            if artifact_id
        }
        provided_id = normalized_sources.get(str(Path(path).expanduser().resolve()))
        if provided_id:
            if self.db is not None and self.db.get_artifact(provided_id) is None:
                return "", False
            return provided_id, False

        md5 = _file_md5(path)
        existing = self._find_raw_artifact_by_md5(md5)
        if existing:
            # Content already registered (dedup): record this user as a
            # co-owner so the dataset appears under their "Mine" scope too.
            try:
                if self.db is not None and self.session is not None:
                    self.db.add_artifact_owner(existing, self.session.user_id)
            except Exception:
                pass
            return existing, False

        if not request.mmfdb.register_missing_inputs:
            return "", False

        artifact_id = register_raw_measurement(
            file_path=path,
            sample_id=request.mmfdb.sample_id,
            metadata={
                "plugin": "microtime_shifter",
                "role": "raw_tttr",
                "filetype": request.filetype,
            },
            setup_id=request.mmfdb.setup_id,
            setup_version=request.mmfdb.setup_version,
            db=self.db,
            session=self.session,
        )
        return artifact_id, bool(artifact_id)

    def register_run(
        self,
        request: ShiftRequest,
        result: ShiftResult,
    ) -> ShiftRegistrationResult:
        """Register shift inputs and outputs in MMFDB.

        Parameters
        ----------
        request : ShiftRequest
            Original shift request.
        result : ShiftResult
            Successful shift result.

        Returns
        -------
        ShiftRegistrationResult
            Created artifact IDs and warnings.

        """
        registration = ShiftRegistrationResult()
        if not request.mmfdb.enabled:
            return registration
        if self.db is None:
            registration.warnings.append(
                "MMFDB registration requested without an explicit database connection."
            )
            return registration
        try:
            from chisurf.core.transform.mmfdb import require_authenticated_session

            require_authenticated_session(self.db, self.session)
        except Exception as exc:
            registration.warnings.append(f"MMFDB archival refused: {exc}")
            return registration

        for input_file in request.files:
            norm_path = str(Path(input_file).resolve())
            raw_id, is_new = self._lookup_or_register_raw(norm_path, request)
            if not raw_id:
                registration.warnings.append(
                    f"MMFDB registration skipped for input {norm_path}."
                )
                continue
            registration.input_artifacts[norm_path] = raw_id

            shifted_path = _value_for_path(result.output_paths_by_file, norm_path)
            if not shifted_path:
                continue

            applied = _value_for_path(result.applied_shifts_by_file, norm_path) or {}
            # Operation parameters per the .dic schema for operation_type
            # "microtime_shift": a scalar global_shift and the repeatable,
            # role-indexed shift (one entry per detector channel, role = channel).
            # This replaces both the flat shift_ch<N> names and the bespoke
            # mmfdb_microtime_shift table (retired) with role-indexed mmfdb_parameter
            # rows recorded by register_result/_record_parameters.
            param_dict: dict[str, Any] = {
                "global_shift": applied.get("global_shift", 0),
                "shift": [
                    {"value": sv, "role": str(ch)}
                    for ch, sv in applied.get("channel_shifts", {}).items()
                ],
            }

            try:
                artifact_id = register_result(
                    kind="processed_data",
                    data=shifted_path,
                    sample_id=request.mmfdb.sample_id,
                    parent_artifact_id=raw_id,
                    operation_type="microtime_shift",
                    parameters=param_dict,
                    metadata={
                        "plugin": "microtime_shifter",
                        "contract_version": CONTRACT_VERSION,
                        "input_file": norm_path,
                        "global_shift": applied.get("global_shift", 0),
                        "channel_shifts": {
                            str(k): v
                            for k, v in applied.get("channel_shifts", {}).items()
                        },
                    },
                    data_format=Path(shifted_path).suffix.lstrip(".") or "tttr",
                    setup_id=request.mmfdb.setup_id,
                    setup_version=request.mmfdb.setup_version,
                    db=self.db,
                    session=self.session,
                )
                if artifact_id:
                    registration.output_artifacts[norm_path] = artifact_id
                else:
                    registration.warnings.append(
                        f"MMFDB did not register shifted output for {norm_path}."
                    )
            except Exception as exc:
                registration.warnings.append(
                    f"MMFDB registration error for {norm_path}: {exc}"
                )

        return registration


def _value_for_path(mapping: dict[str, Any], path: str) -> Any:
    """Return a path-keyed value after normalizing caller and stored keys."""
    normalized = str(Path(path).expanduser().resolve())
    for key, value in mapping.items():
        if str(Path(key).expanduser().resolve()) == normalized:
            return value
    return None
