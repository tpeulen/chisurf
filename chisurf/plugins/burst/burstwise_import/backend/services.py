"""ServiceDispatcher-compatible RPC handlers for burstwise_import."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from chisurf.plugins.burst.burstwise_import.api import import_folder
from chisurf.plugins.burst.burstwise_import.api.models import (
    METHOD_DESCRIBE_CONTRACT,
    METHOD_IMPORT_FOLDER,
    contract_descriptor,
    service_error,
    service_success,
    settings_from_dict,
)


def register_services(dispatcher: Any) -> None:
    """Register burstwise_import RPC handlers with a ServiceDispatcher."""
    dispatcher.register(
        METHOD_IMPORT_FOLDER, lambda params: import_folder_handler(**(params or {}))
    )
    dispatcher.register(METHOD_DESCRIBE_CONTRACT, lambda params: contract_handler(**(params or {})))


def list_methods() -> dict[str, str]:
    return {
        METHOD_IMPORT_FOLDER: "Convert a legacy burstwise analysis folder to PTO.MFDB containers.",
        METHOD_DESCRIBE_CONTRACT: "Return the burstwise_import workflow contract.",
    }


def import_folder_handler(
    folder: str | None = None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not folder:
        return service_error("folder is required")
    try:
        report = import_folder(Path(folder), settings_from_dict(settings))
    except Exception as exc:  # surface as envelope, never crash the dispatcher
        return service_error(str(exc))
    return service_success(
        {
            "containers": report.containers,
            "stems": report.stems,
            "unmapped_columns": report.unmapped_columns,
            "parameters": report.parameters,
        }
    )


def contract_handler() -> dict[str, Any]:
    return service_success(contract_descriptor())
