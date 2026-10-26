"""RPC services of the ChiMOL host: the fps.json plan and its structures, headlessly.

The labelling editor and its document are ChiMOL's (``chimol.plugins.labelling``);
these handlers are the server's door to them, for scripts and the agent: check,
summarise and normalise an fps.json payload, fetch a structure by PDB ID, and
write accessible-volume points as an MRC map. Each answers in the server's
service envelope and never raises across the RPC boundary.
"""

from __future__ import annotations

from typing import Any

import numpy as np

METHOD_VALIDATE = "chimol.fps.validate"
METHOD_SUMMARIZE = "chimol.fps.summarize"
METHOD_NORMALIZE = "chimol.fps.normalize"
METHOD_FETCH_PDB = "chimol.pdb.fetch"
METHOD_SAVE_AV_MRC = "chimol.av.mrc.save"


def _ok(result: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "result": result}


def _failed(exc: Exception) -> dict[str, Any]:
    from chisurf.server.services import OPERATION_FAILED, service_error  # noqa: PLC0415

    return service_error(str(exc), error_code=OPERATION_FAILED)


def register_services(dispatcher: Any) -> None:
    """Register the ChiMOL host's handlers with the server's ServiceDispatcher."""
    dispatcher.register(METHOD_VALIDATE, lambda params: validate_handler(**params))
    dispatcher.register(METHOD_SUMMARIZE, lambda params: summarize_handler(**params))
    dispatcher.register(METHOD_NORMALIZE, lambda params: normalize_handler(**params))
    dispatcher.register(METHOD_FETCH_PDB, lambda params: fetch_pdb_handler(**params))
    dispatcher.register(METHOD_SAVE_AV_MRC, lambda params: save_av_mrc_handler(**params))


def validate_handler(payload: Any) -> dict[str, Any]:
    """Check an fps.json payload's sections and references (``valid``, ``errors``, ``warnings``)."""
    try:
        from chimol.plugins.labelling.fps import validate_payload  # noqa: PLC0415

        return _ok(validate_payload(payload))
    except Exception as exc:  # noqa: BLE001 - the envelope carries it
        return _failed(exc)


def summarize_handler(payload: dict[str, Any]) -> dict[str, Any]:
    """Counts, names and dangling references of an fps.json payload."""
    try:
        from chimol.plugins.labelling.fps import summarize_payload  # noqa: PLC0415

        return _ok(summarize_payload(payload))
    except Exception as exc:  # noqa: BLE001
        return _failed(exc)


def normalize_handler(payload: dict[str, Any]) -> dict[str, Any]:
    """The payload in canonical form (``{"payload": ...}``)."""
    try:
        from chimol.plugins.labelling.fps import normalize_payload  # noqa: PLC0415

        return _ok({"payload": normalize_payload(payload)})
    except Exception as exc:  # noqa: BLE001
        return _failed(exc)


def fetch_pdb_handler(pdb_id: str, output_dir: str | None = None) -> dict[str, Any]:
    """Download ``<pdb_id>.pdb`` from RCSB; ``{"pdb_id", "path", "source"}``.

    Parameters
    ----------
    pdb_id : str
        Four-character PDB code.
    output_dir : str, optional
        Where to write; the shared structure cache when omitted.
    """
    try:
        from chisurf.core.fio.structure.fetch import (  # noqa: PLC0415
            download_pdb_file,
            pdb_source_url,
        )
        from chimol.plugins.labelling.fps_cli import normalize_pdb_id  # noqa: PLC0415

        code = normalize_pdb_id(pdb_id)
        path = download_pdb_file(code, output_dir=output_dir)
        return _ok({"pdb_id": code, "path": str(path), "source": pdb_source_url(code)})
    except Exception as exc:  # noqa: BLE001
        return _failed(exc)


def save_av_mrc_handler(path: str, points: list[list[float]], grid_step: float) -> dict[str, Any]:
    """Write accessible-volume points (``(N, 3)`` or ``(N, 4)`` with weights) as an MRC map.

    The voxelisation (rounding, origin, extent, the ``.mrc`` suffix rule) is the
    writer's, ``IMP.bff.write_points_mrc``; the answer carries the path written.
    """
    try:
        import IMP.bff as bff  # noqa: PLC0415

        out = bff.write_points_mrc(
            str(path), np.ascontiguousarray(points, dtype=np.float64), float(grid_step)
        )
        return _ok({"path": str(out)})
    except Exception as exc:  # noqa: BLE001
        return _failed(exc)


__all__ = [
    "METHOD_FETCH_PDB",
    "METHOD_NORMALIZE",
    "METHOD_SAVE_AV_MRC",
    "METHOD_SUMMARIZE",
    "METHOD_VALIDATE",
    "fetch_pdb_handler",
    "normalize_handler",
    "register_services",
    "save_av_mrc_handler",
    "summarize_handler",
    "validate_handler",
]
