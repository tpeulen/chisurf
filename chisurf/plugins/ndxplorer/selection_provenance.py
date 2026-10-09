"""Selection write-back for the artifact identity returned by the native picker.

Artifacts and legacy processed-data products are different MMFDB identities.
Use authenticated canonical artifact/operation services here; do not invent a
processed-data ID or fall back to another client/database.
"""

from __future__ import annotations

import json
from uuid import uuid4


def record_artifact_selection(client, artifact_id: str, record: dict) -> str:
    """Archive a saved mask and link its analysis to an existing input artifact.

    The output and operation are created together. Link the existing input
    separately rather than re-registering it (which would require write access
    and could overwrite its metadata). A partially linked operation is failed,
    never announced as successful; the caller retains the already written BIDs.
    """
    source = client.call("mmfdb.v1.artifacts.get", {"artifact_id": artifact_id}).get("artifact")
    if not source:
        raise RuntimeError(f"MMFDB source artifact is unavailable: {artifact_id}")
    operation_id, mask_id = str(uuid4()), str(uuid4())
    settings = {key: record[key] for key in ("gate", "folder", "files", "n_rows", "n_selected")}
    settings.update(source_artifact_id=artifact_id, analysis_type="ndxplorer_selection")
    from importlib.metadata import PackageNotFoundError, version

    try:
        software_version = version("ndxplorer")
    except PackageNotFoundError:
        software_version = None

    reply = client.call(
        "mmfdb.v1.operations.record_with_artifacts",
        {
            "operation_id": operation_id,
            "operation_type": "analysis",
            "status": "running",
            "settings": settings,
            "software_package": "ndxplorer",
            "software_module": "selection",
            "software_version": software_version,
            "input_artifacts": [],
            "output_artifacts": [
                {
                    "artifact_id": mask_id,
                    "artifact_kind": "selection_mask",
                    "role": "selection_mask",
                    "storage_mode": "embedded_json",
                    "data_format": "json",
                    "data_json": json.dumps({"mask": record["mask"]}),
                    "row_count": record["n_rows"],
                    "validation_status": "valid",
                    "metadata": {"source_artifact_id": artifact_id, "folder": record["folder"]},
                }
            ],
        },
    )
    if not reply.get("ok") or reply.get("operation_id") != operation_id:
        raise RuntimeError("MMFDB did not create the selection operation")
    try:
        linked = client.call(
            "mmfdb.v1.operations.link_artifact",
            {
                "operation_id": operation_id,
                "artifact_id": artifact_id,
                "direction": "input",
                "role": "burst_selection",
                "checksum_snapshot": source.get("checksum"),
            },
        )
        if not linked.get("ok"):
            raise RuntimeError("MMFDB did not link the input artifact")
        client.call(
            "mmfdb.v1.operations.transition_status",
            {
                "operation_id": operation_id,
                "status": "succeeded",
            },
        )
    except Exception as exc:
        try:
            client.call(
                "mmfdb.v1.operations.transition_status",
                {
                    "operation_id": operation_id,
                    "status": "failed",
                    "error_message": str(exc),
                },
            )
        except Exception:
            pass  # The caller reports the original error; BIDs are already saved.
        raise
    saved = client.call("mmfdb.v1.operations.get", {"operation_id": operation_id}).get("operation")
    if not saved or saved.get("status") != "succeeded":
        raise RuntimeError("MMFDB did not confirm the saved selection operation")
    return (
        f"Recorded the selection ({record['n_selected']} of {record['n_rows']} bursts) "
        f"in MMFDB as {operation_id}"
    )
