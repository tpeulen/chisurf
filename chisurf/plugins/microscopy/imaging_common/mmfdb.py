"""Qt-free MMFDB boundary for per-pixel imaging outputs."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def require_imaging_source_access(db: Any, artifact_id: str, principal: Any) -> None:
    """Require read access to an imaging source before binding it to a tool."""
    from mmfdb.security.auth import AuthError, require_authenticated

    if principal is None:
        raise AuthError("Authentication required")
    require_authenticated(principal)
    if not artifact_id:
        raise ValueError("source_artifact_id is required")
    get_artifact = getattr(db, "get_artifact", None)
    if not callable(get_artifact):
        raise TypeError("MMFDB client does not support artifact lookup")
    if get_artifact(artifact_id) is None:
        raise KeyError(f"source artifact not found: {artifact_id}")
    conn = getattr(db, "conn", None)
    if conn is None:
        raise TypeError("ACL enforcement requires an MMFDB client with a connection")
    from mmfdb.security.auth import PERM_READ, require_access

    require_access(conn, principal, "artifact", artifact_id, PERM_READ)


def json_safe(value: Any) -> Any:
    """Convert imaging parameters containing paths/NumPy values to JSON values."""
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (Path, os.PathLike)):
        return str(value)
    try:
        import numpy as np

        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            return value.item()
    except ImportError:  # pragma: no cover - imaging requires NumPy
        pass
    return value


def register_imaging_output(
    db: Any,
    *,
    output_path: str | os.PathLike[str],
    source_artifact_id: str,
    parent_artifact_id: str | None = None,
    sample_id: str = "",
    metadata: dict[str, Any] | None = None,
    session: Any,
) -> str:
    """Archive one immutable imaging-HDF5 snapshot with source lineage."""
    path = Path(output_path)
    if not path.is_file():
        raise FileNotFoundError(f"imaging output was not created: {path}")
    from mmfdb.provenance.result_registry import register_result

    with db.transaction():
        return register_result(
            kind="processed_data",
            data=path,
            sample_id=sample_id,
            parent_artifact_id=parent_artifact_id or source_artifact_id,
            operation_type="image_analysis",
            data_format="hdf5",
            metadata=json_safe(
                {
                    **(metadata or {}),
                    "source_artifact_id": source_artifact_id,
                    "output_path": str(path.resolve()),
                    "output_role": "imaging_hdf5_snapshot",
                }
            ),
            db=db,
            session=session,
        )
