"""Data models and workflow contract for the burstwise_import plugin API."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

PLUGIN_ID = "burstwise_import"
CONTRACT_VERSION = "1.0.0"

METHOD_IMPORT_FOLDER = "burstwise_import.jobs.import_folder"
METHOD_DESCRIBE_CONTRACT = "burstwise_import.contract.describe"

CANONICAL_METHODS = (
    METHOD_IMPORT_FOLDER,
    METHOD_DESCRIBE_CONTRACT,
)


@dataclass
class ImportSettings:
    """Settings of one legacy-folder import.

    Attributes
    ----------
    out_dir : str or None
        Where ``<stem>.mmfdb.pto`` containers are written; None = beside the
        burstwise folder.
    dry_run : bool
        Report only; write nothing.
    raw_data : str
        "embed" (instrument file inside the container) or "sidecar"
        (analysis-only container; raw file stays beside it, its sha256/size
        recorded as container tags).

    source_mode : str
        ``"mti_prefix"`` (remap the .mti original paths), ``"beside"``
        (``<stem>.ht3/.spc/.ptu`` next to the folder) or ``"none"``
        (no instrument file; stems reported).
    mti_prefix_map : dict of str to str
        Old path prefix -> new prefix, e.g. ``{"N:\\\\": "/mnt/user/"}``.
    """

    out_dir: str | None = None
    dry_run: bool = False
    source_mode: str = "beside"
    raw_data: str = "sidecar"
    mti_prefix_map: dict[str, str] = field(default_factory=dict)


def settings_from_dict(payload: dict[str, Any] | None) -> ImportSettings:
    """Build :class:`ImportSettings` from a JSON-compatible dict."""
    payload = payload or {}
    known = {k: v for k, v in payload.items() if k in ImportSettings.__dataclass_fields__}
    return ImportSettings(**known)


def service_success(result: dict[str, Any] | Any) -> dict[str, Any]:
    """Wrap a result in the standard service envelope."""
    return {"status": "ok", "result": result}


def service_error(message: str) -> dict[str, Any]:
    return {"status": "error", "message": message}


def contract_descriptor() -> dict[str, Any]:
    """Describe the workflow contract of this plugin."""
    return {
        "plugin": PLUGIN_ID,
        "contract_version": CONTRACT_VERSION,
        "methods": [
            {
                "name": METHOD_IMPORT_FOLDER,
                "summary": "Convert a legacy burstwise analysis folder to PTO.MFDB containers.",
                "parameters": {
                    "folder": "path to the burstwise_* folder",
                    "settings": "ImportSettings as a dict (optional)",
                },
                "long_running": True,
            },
            {
                "name": METHOD_DESCRIBE_CONTRACT,
                "summary": "Return this contract.",
                "long_running": False,
            },
        ],
        "settings_model": asdict(ImportSettings()),
    }
