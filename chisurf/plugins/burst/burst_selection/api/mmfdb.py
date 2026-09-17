"""MMFDB registration for Burst Selection analysis results."""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mmfdb.provenance.result_registry import (
    LinkValidationError,
    register_raw_measurement,
    register_result,
)

from chisurf.core.datastore import write_csv_table

from .contract import CONTRACT_VERSION
from .models import AnalysisRequest, AnalysisResult
from .serialization import to_jsonable

if TYPE_CHECKING:
    from mmfdb.security.base import MMFDBClientBase
    from mmfdb.security.session import SessionContext

logger = logging.getLogger(__name__)


@dataclass
class BurstRegistrationResult:
    """MMFDB artifact IDs created for one burst-selection run.

    Attributes
    ----------
    input_artifacts : dict
        Raw input artifacts keyed by normalized input file path.
    burst_table_artifacts : dict
        Primary burst table artifacts keyed by normalized input file path.
    sidecar_artifacts : dict
        Optional convenience outputs keyed by output role.
    warnings : list
        Non-fatal registration warnings.

    """

    input_artifacts: dict[str, str] = field(default_factory=dict)
    burst_table_artifacts: dict[str, str] = field(default_factory=dict)
    sidecar_artifacts: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class BurstMMFDBPipeline:
    """Register Burst Selection inputs and outputs in MMFDB."""

    def __init__(
        self,
        db: MMFDBClientBase | None = None,
        session: SessionContext | None = None,
    ):
        """Create a burst-selection registration pipeline.

        Parameters
        ----------
        db : MMFDBClientBase, optional
            Explicit MMFDB connection. An enabled request without one is
            reported as a registration warning; no ambient database is used.

        """
        self.db = db
        self.session = session

    def _resolve_calibrated_at(self, request: AnalysisRequest) -> str | None:
        """Return the latest calibration timestamp for the resolved setup.

        Parameters
        ----------
        request : AnalysisRequest
            The analysis request with MMFDB context.

        Returns
        -------
        str or None
            ISO-8601 timestamp of the latest calibration snapshot, or
            ``None`` if no calibration data exists or no setup is set.
        """
        setup_id = request.mmfdb.setup_id
        if not setup_id:
            return None
        if self.db is None:
            return None
        try:
            dates = self.db.list_setup_calibration_dates(setup_id)
            return dates[0] if dates else None
        except Exception:
            return None

    def _resolve_setup_id(self, request: AnalysisRequest) -> str | None:
        """Resolve and validate the MMFDB setup ID for an analysis request.

        When the resolved setup does not exist in ``mmfdb_setup``, clears
        ``request.mmfdb.setup_id`` and returns a warning so the caller can
        append it to the registration result.  ``mmfdb_operation.setup_id``
        stays NULL rather than referencing a dangling setup.

        Parameters
        ----------
        request : AnalysisRequest
            The analysis request whose ``mmfdb`` context is updated in place.

        Returns
        -------
        str or None
            A warning message when the setup does not exist, or ``None``.

        """
        setup_id = (request.mmfdb.setup_id or "").strip()
        selected_setup = (request.selected_setup or "").strip()
        # Setup namespaces follow the explicitly authenticated caller.  Never
        # consult process settings here: a GUI/server may serve multiple users
        # over the lifetime of one process.
        user_id = str(getattr(self.session, "user_id", ""))

        if not setup_id and selected_setup:
            # Try user-namespaced id first, then fall back to global (shared) id
            setup_id = _setup_id_for_name(selected_setup, user_id=user_id)
            if self.db is not None:
                if self.db.get_setup(setup_id) is None:
                    global_id = _setup_id_for_name(selected_setup, user_id="")
                    if self.db.get_setup(global_id) is not None:
                        setup_id = global_id

        if not setup_id:
            request.mmfdb.setup_id = ""
            request.mmfdb.setup_version = None
            return None

        setup_row = None
        if self.db is not None:
            try:
                setup_row = self.db.get_setup(setup_id)
            except Exception:
                setup_row = None

        if setup_row is None:
            msg = (
                f"Setup {setup_id!r} (selected_setup={selected_setup!r}) "
                f"does not exist in MMFDB; setup_id will not be linked."
            )
            request.mmfdb.setup_id = ""
            request.mmfdb.setup_version = None
            return msg

        request.mmfdb.setup_id = setup_id
        request.mmfdb.setup_version = setup_row.get("version") or 1
        return None

    def register_run(
        self,
        request: AnalysisRequest,
        result: AnalysisResult,
    ) -> BurstRegistrationResult:
        """Register the successful analysis result in MMFDB.

        Parameters
        ----------
        request : AnalysisRequest
            Original burst-selection request.
        result : AnalysisResult
            Successful pure-analysis result to archive.

        Returns
        -------
        BurstRegistrationResult
            Created artifact IDs and non-fatal warnings.

        """
        registration = BurstRegistrationResult()
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

        warning = self._resolve_setup_id(request)
        if warning:
            registration.warnings.append(warning)

        source_artifact_ids = _normalize_source_artifact_ids(request.mmfdb.source_artifact_ids)
        for input_file in request.files:
            input_path = _normalize_path(input_file)
            input_artifact_id = self._input_artifact_id(
                input_path, request, source_artifact_ids, registration
            )
            if not input_artifact_id:
                continue
            registration.input_artifacts[input_path] = input_artifact_id
            self._register_burst_table(input_path, input_artifact_id, request, result, registration)

        self._register_sidecars(request, result, registration)
        return registration

    def _input_artifact_id(
        self,
        input_path: str,
        request: AnalysisRequest,
        source_artifact_ids: dict[str, str],
        registration: BurstRegistrationResult,
    ) -> str:
        """Return the raw input artifact ID for one file, creating it if needed.

        Parameters
        ----------
        input_path : str
            Normalized input file path.
        request : AnalysisRequest
            Original analysis request.
        source_artifact_ids : dict
            Normalized caller-provided source artifact mapping.
        registration : BurstRegistrationResult
            Mutable registration result used for warning collection.

        Returns
        -------
        str
            Existing or newly registered artifact ID, or ``""`` on failure.

        """
        provided_id = source_artifact_ids.get(input_path)
        if provided_id:
            if self.db is not None and self.db.get_artifact(provided_id) is None:
                registration.warnings.append(
                    f"MMFDB source artifact {provided_id!r} for {input_path} does not exist."
                )
                return ""
            return provided_id

        if not request.mmfdb.register_missing_inputs:
            return ""

        try:
            artifact_id = register_raw_measurement(
                file_path=input_path,
                sample_id=request.mmfdb.sample_id,
                metadata={
                    "plugin": "burst_selection",
                    "role": "raw_tttr",
                    "filetype": request.filetype,
                    "selected_setup": request.selected_setup,
                },
                setup_id=request.mmfdb.setup_id,
                setup_version=request.mmfdb.setup_version,
                db=self.db,
                session=self.session,
            )
        except LinkValidationError as exc:
            # A bad sample/parent link is validated before any rows are written,
            # so nothing was persisted. Report it and skip this input instead of
            # aborting the whole run.
            registration.warnings.append(f"MMFDB could not register raw input {input_path}: {exc}")
            return ""
        if not artifact_id:
            registration.warnings.append(f"MMFDB did not register raw input {input_path}.")
        return artifact_id

    def _register_burst_table(
        self,
        input_path: str,
        input_artifact_id: str,
        request: AnalysisRequest,
        result: AnalysisResult,
        registration: BurstRegistrationResult,
    ) -> None:
        """Register the primary burst-table artifact for one input file.

        Parameters
        ----------
        input_path : str
            Normalized input file path.
        input_artifact_id : str
            Raw input artifact ID.
        request : AnalysisRequest
            Original analysis request.
        result : AnalysisResult
            Successful analysis result.
        registration : BurstRegistrationResult
            Mutable registration result.

        """
        rows = _rows_for_input(result, input_path)
        bur_path = _bur_path_for_input(result, input_path)
        if not bur_path and not rows:
            return

        data: str | bytes
        data_format = ""
        if bur_path:
            data = bur_path
        else:
            # Use the native, interoperable .bur tabular encoding for in-memory
            # results too. This keeps API/CLI/GUI output equivalent and avoids
            # coupling registration to a Python-only dataframe codec.
            data = write_csv_table(None, rows).encode("utf-8")
            data_format = "bur"

        calibrated_at = self._resolve_calibrated_at(request)
        artifact_id = register_result(
            kind="burst_table",
            data=data,
            sample_id=request.mmfdb.sample_id,
            parent_artifact_id=input_artifact_id,
            operation_type="burst_selection",
            parameters=extract_burst_parameters(request),
            metadata=build_burst_metadata(
                request,
                result,
                input_path,
                calibrated_at=calibrated_at,
            ),
            data_format=data_format,
            setup_id=request.mmfdb.setup_id,
            setup_version=request.mmfdb.setup_version,
            db=self.db,
            session=self.session,
        )
        if artifact_id:
            registration.burst_table_artifacts[input_path] = artifact_id
            return

        registration.warnings.append(f"MMFDB did not register burst table for {input_path}.")

    def _register_sidecars(
        self,
        request: AnalysisRequest,
        result: AnalysisResult,
        registration: BurstRegistrationResult,
    ) -> None:
        """Register optional sidecar outputs after primary tables exist.

        Parameters
        ----------
        request : AnalysisRequest
            Original analysis request.
        result : AnalysisResult
            Successful analysis result.
        registration : BurstRegistrationResult
            Mutable registration result.

        """
        if not registration.burst_table_artifacts:
            return

        first_parent = next(iter(registration.burst_table_artifacts.values()))
        global_roles = {"hdf5", "zip", "output_folder"}
        for role in global_roles:
            path = result.output_paths.get(role)
            if path:
                self._register_sidecar(role, path, first_parent, request, registration)

        for input_path, role_paths in result.output_paths_by_file.items():
            parent_id = registration.burst_table_artifacts.get(_normalize_path(input_path))
            if not parent_id:
                continue
            for role, path in role_paths.items():
                if role == "bur" or not path:
                    continue
                # Per-file directory roles (e.g. the shared ``Info`` / output
                # folder) all point at the single run-level output directory, so
                # registering one per file would list a multi-file run as many
                # duplicate, UUID-named directory entries instead of one group.
                # The run output folder is registered once above via
                # ``global_roles``; skip per-file directories here.
                if Path(path).is_dir():
                    continue
                sidecar_key = f"{_normalize_path(input_path)}:{role}"
                self._register_sidecar(sidecar_key, path, parent_id, request, registration)

    def _register_sidecar(
        self,
        role: str,
        path: str,
        parent_artifact_id: str,
        request: AnalysisRequest,
        registration: BurstRegistrationResult,
    ) -> None:
        """Register one optional sidecar path.

        Parameters
        ----------
        role : str
            Stable output role.
        path : str
            Output file or folder path.
        parent_artifact_id : str
            Parent burst-table artifact ID.
        request : AnalysisRequest
            Original analysis request.
        registration : BurstRegistrationResult
            Mutable registration result.

        """
        sidecar_path = Path(path)
        is_file = sidecar_path.is_file()
        kind = "processed_data" if is_file else "external_reference"
        data = str(sidecar_path) if is_file else None
        calibrated_at = self._resolve_calibrated_at(request)
        metadata = {
            "plugin": "burst_selection",
            "contract_version": CONTRACT_VERSION,
            "output_role": role,
            "path": str(sidecar_path),
            "selected_setup": request.selected_setup,
            "setup_id": request.mmfdb.setup_id,
            "setup_version": request.mmfdb.setup_version,
            "calibrated_at": calibrated_at,
        }
        artifact_id = register_result(
            kind=kind,
            data=data,
            sample_id=request.mmfdb.sample_id,
            parent_artifact_id=parent_artifact_id,
            operation_type="burst_selection",
            metadata=metadata,
            data_format=_sidecar_data_format(sidecar_path) if is_file else "directory",
            setup_id=request.mmfdb.setup_id,
            setup_version=request.mmfdb.setup_version,
            db=self.db,
            session=self.session,
        )
        if artifact_id:
            registration.sidecar_artifacts[role] = artifact_id
            return
        registration.warnings.append(f"MMFDB did not register sidecar {role!r} at {path}.")


def extract_burst_parameters(request: AnalysisRequest) -> dict[str, Any]:
    """Extract scalar burst parameters for ``mmfdb_parameter`` rows.

    Parameters
    ----------
    request : AnalysisRequest
        Burst-selection request.

    Returns
    -------
    dict
        Scalar parameter names and numeric values.

    """
    photon_filter = request.settings.photon_filter
    burst_detection = request.settings.burst_detection
    count_rate = photon_filter.count_rate_filter
    delta = photon_filter.delta_macro_time_filter
    gmm = request.settings.gmm
    params: dict[str, Any] = {
        "min_photons": burst_detection.min_photons,
        "photon_window": burst_detection.photon_window,
        "time_window": burst_detection.time_window,
        "filter_active": int(bool(photon_filter.filter_active)),
        "count_rate_n_ph_max": count_rate.n_ph_max,
        "count_rate_time_window": count_rate.time_window,
        "delta_macro_time_min": delta.dT_min,
        "delta_macro_time_max": delta.dT_max,
        "gmm_max_components": gmm.max_components,
        # GMM determinism — recorded so a replay reproduces the same clustering.
        "gmm_covariance_type": gmm.covariance_type,
        "gmm_random_state": gmm.random_state,
        "gmm_max_iter": gmm.max_iter,
        "gmm_n_init": gmm.n_init,
    }
    # The detector stream mask is a role-indexed repeatable parameter (role =
    # ordinal index), matching the microtime_shift `shift` precedent; it is part of
    # the reproducible compute spec because it selects which photons are analysed.
    if photon_filter.channels:
        params["channels"] = [
            {"value": int(ch), "role": str(i)} for i, ch in enumerate(photon_filter.channels)
        ]
    return params


def build_burst_metadata(
    request: AnalysisRequest,
    result: AnalysisResult,
    input_path: str,
    calibrated_at: str | None = None,
) -> dict[str, Any]:
    """Build JSON-safe metadata for a burst-table artifact.

    Parameters
    ----------
    request : AnalysisRequest
        Burst-selection request.
    result : AnalysisResult
        Analysis result.
    input_path : str
        Normalized input file path.
    calibrated_at : str or None, optional
        ISO-8601 timestamp of the calibration snapshot used for this
        analysis. Stored in operation metadata for provenance.

    Returns
    -------
    dict
        JSON-safe artifact and operation metadata.

    """
    rows = _rows_for_input(result, input_path)
    metadata = {
        "plugin": "burst_selection",
        "contract_version": CONTRACT_VERSION,
        "input_file": _normalize_path(input_path),
        "output_role": "burst_table",
        "n_bursts": len(rows),
        "photon_filter": to_jsonable(request.settings.photon_filter),
        "burst_detection": to_jsonable(request.settings.burst_detection),
        "gmm": to_jsonable(request.settings.gmm),
        "windows": to_jsonable(request.windows),
        "detectors": to_jsonable(request.detectors),
        "selected_setup": request.selected_setup,
        "setup_id": request.mmfdb.setup_id,
        "setup_version": request.mmfdb.setup_version,
        "calibrated_at": calibrated_at,
        "filetype": request.filetype,
    }
    if len(request.files) == 1:
        for key in ("n_selected", "n_photons", "macro_time_resolution"):
            if key in result.metadata:
                metadata[key] = result.metadata[key]
    elif "macro_time_resolution" in result.metadata:
        metadata["macro_time_resolution"] = result.metadata["macro_time_resolution"]
    return metadata


def registration_result_to_payload(result: BurstRegistrationResult) -> dict[str, Any]:
    """Return a JSON-compatible registration result payload.

    Parameters
    ----------
    result : BurstRegistrationResult
        Registration result dataclass.

    Returns
    -------
    dict
        JSON-compatible payload.

    """
    return to_jsonable(result)


def _normalize_path(path: str | Path) -> str:
    """Return a stable absolute path key.

    Parameters
    ----------
    path : str or Path
        File or folder path.

    Returns
    -------
    str
        Resolved absolute path string.

    """
    return str(Path(path).expanduser().resolve())


def _setup_id_for_name(name: str, *, user_id: str = "") -> str:
    """Return the stable detector-setup identifier without importing GUI code."""
    slug = re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")
    if user_id:
        user_slug = re.sub(r"[^a-z0-9]+", "_", str(user_id).strip().lower()).strip("_")
        return f"tttr_detector_setup:{user_slug}:{slug or 'unnamed'}"
    return f"tttr_detector_setup:{slug or 'unnamed'}"


def _normalize_source_artifact_ids(source_artifact_ids: dict[str, str]) -> dict[str, str]:
    """Normalize caller-provided source artifact path keys.

    Parameters
    ----------
    source_artifact_ids : dict
        Mapping from input path to existing artifact ID.

    Returns
    -------
    dict
        Mapping keyed by normalized absolute paths.

    """
    return {
        _normalize_path(path): str(artifact_id)
        for path, artifact_id in source_artifact_ids.items()
        if artifact_id
    }


def _rows_for_input(result: AnalysisResult, input_path: str) -> list[dict[str, Any]]:
    """Return burst rows for one normalized input path.

    Parameters
    ----------
    result : AnalysisResult
        Analysis result.
    input_path : str
        Normalized input file path.

    Returns
    -------
    list
        Burst row dictionaries.

    """
    normalized_input = _normalize_path(input_path)
    for key, rows in result.dataframes.items():
        if _normalize_path(key) == normalized_input:
            return list(rows or [])
    return []


def _bur_path_for_input(result: AnalysisResult, input_path: str) -> str:
    """Return the per-file ``.bur`` path for one input, if any.

    Parameters
    ----------
    result : AnalysisResult
        Analysis result.
    input_path : str
        Normalized input file path.

    Returns
    -------
    str
        Burst table path, or ``""``.

    """
    normalized_input = _normalize_path(input_path)
    for key, role_paths in result.output_paths_by_file.items():
        if _normalize_path(key) == normalized_input:
            return str(role_paths.get("bur") or "")
    if len(result.files) == 1:
        return str(result.output_paths.get("bur") or "")
    return ""


def _sidecar_data_format(path: Path) -> str:
    """Return an MMFDB vocabulary data format for a sidecar file.

    Parameters
    ----------
    path : Path
        Sidecar file path.

    Returns
    -------
    str
        MMFDB data format value.

    """
    suffix = path.suffix.lower().lstrip(".")
    if suffix in {"h5", "hdf"}:
        return "hdf5"
    return suffix or "unknown"


# --- raw-input registration / lookup (PRD-23: moved out of gui/) -------------
#
# These are view-agnostic MMFDB/IO helpers; the GUI tool re-exports them so its
# construction stays free of registration logic (PRD-23 Task 2/4).


def file_md5(path: Path) -> str:
    """Return the hex-encoded MD5 digest of a file (streamed)."""
    digest = hashlib.md5()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sample_id_for_raw_path(db: MMFDBClientBase, path: Path) -> str | None:
    """Return the sample already associated with a raw file's content, or ``None``."""
    try:
        return db.lookup_sample_by_md5(file_md5(path))
    except Exception:
        return None


def raw_artifact_id_for_path(db: MMFDBClientBase, path: Path) -> str:
    """Return an existing raw-measurement artifact for a file, or an empty string."""
    try:
        return db.find_raw_artifact_by_md5(file_md5(path))
    except Exception:
        return ""


def raw_file_data_format(path: Path) -> str:
    """Return the MMFDB data-format vocabulary value for a raw TTTR file."""
    suffix = Path(path).suffix.lower().lstrip(".")
    return {"h5": "hdf5", "ht3": "tttr"}.get(suffix, suffix or "tttr")


def register_raw_input_for_sample(
    *,
    db: MMFDBClientBase,
    path: Path,
    sample_id: str,
    filetype: str | None,
    selected_setup: str | None,
    setup_id: str = "",
    session: SessionContext | None = None,
) -> str:
    """Register a raw input artifact and bind its object content to a sample.

    Returns the registered raw artifact ID, or an empty string when the sample
    does not exist or registration produced no artifact.
    """
    if not db.sample_exists(sample_id):
        return ""
    from chisurf.core.transform.mmfdb import require_authenticated_session

    require_authenticated_session(db, session)
    artifact_id = register_raw_measurement(
        file_path=str(path),
        sample_id=sample_id,
        setup_id=setup_id,
        metadata={
            "plugin": "burst_selection",
            "role": "raw_tttr",
            "filetype": filetype,
            "selected_setup": selected_setup,
            "data_format": raw_file_data_format(path),
        },
        db=db,
        session=session,
    )
    if not artifact_id:
        return ""
    artifact = db.get_artifact(artifact_id)
    object_uuid = artifact.get("object_uuid") if artifact else None
    if object_uuid:
        db.set_object_sample_id(object_uuid, sample_id)
    return artifact_id


def acquire_mmfdb_connection() -> MMFDBClientBase | None:
    """Open the configured MMFDB for a GUI composition root.

    The returned connection must be passed into the service/pipeline explicitly;
    this helper never consults the result registry's process global.
    """
    try:
        from mmfdb.repository import MFDatabase
        from mmfdb.store.database_resolver import resolve_database_path

        return MFDatabase(resolve_database_path())
    except Exception as exc:  # pragma: no cover - environment-dependent
        logger.warning("failed to open MMFDB connection: %s", exc)
        return None
