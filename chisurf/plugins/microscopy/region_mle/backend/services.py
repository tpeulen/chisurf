"""RPC service registration for region_mle."""

from __future__ import annotations

import dataclasses
import logging
from typing import Any

from ..api.contract import (
    METHOD_ANALYZE,
    METHOD_CONTRACT,
    contract_descriptor,
    service_error,
    service_success,
)

logger = logging.getLogger(__name__)


def register_services(dispatcher: Any) -> None:
    """Register all region_mle RPC handlers with *dispatcher*."""
    dispatcher.register(METHOD_ANALYZE, _handle_analyze)
    dispatcher.register(METHOD_CONTRACT, _handle_contract)


def _handle_analyze(params: dict[str, Any]) -> dict[str, Any]:
    """Run molecule-wise MLE analysis."""
    try:
        from ..api.models import RegionMleRequest, RegionMleSettings
        from ..api.region_mle import analyze_request

        settings_dict = params.get("settings") or {}
        field_names = {f.name for f in dataclasses.fields(RegionMleSettings)}
        settings = RegionMleSettings(**{k: v for k, v in settings_dict.items() if k in field_names})
        request = RegionMleRequest(
            files=params["files"],
            irf_file=params["irf_file"],
            output_dir=params.get("output_dir", ""),
            settings=settings,
        )
        result = analyze_request(request)
        return service_success(
            {
                "processed_files": result.processed_files,
                "output_paths": result.output_paths,
                "joint_tsv": result.joint_tsv,
                "n_molecules": result.n_molecules,
                "warnings": result.warnings,
            }
        )
    except Exception as exc:
        logger.exception("region_mle.analyze.run failed")
        return service_error(exc)


def _handle_contract(params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the RPC contract descriptor."""
    return service_success(contract_descriptor())
