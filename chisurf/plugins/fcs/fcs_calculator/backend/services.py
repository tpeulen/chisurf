"""Backend RPC services for the FCS confocal calculator."""

from __future__ import annotations

from typing import Any, Dict

from ..core.algorithms import (
    compute_confocal,
    reference_dyes,
    water_viscosity_Pa_s,
    Pa_s_to_mPa_s,
)


def compute_handler(**params) -> Dict[str, Any]:
    try:
        return {"ok": True, "result": compute_confocal(**params)}
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": str(exc)}


def water_viscosity_handler(temp_C: float) -> Dict[str, Any]:
    try:
        eta = water_viscosity_Pa_s(float(temp_C) + 273.15)
        return {"ok": True, "result": {"eta_mPa_s": Pa_s_to_mPa_s(eta)}}
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": str(exc)}


def reference_dyes_handler(refresh: bool = False) -> Dict[str, Any]:
    """List the MMFDB species carrying a diffusion coefficient D(25 °C, water)."""
    try:
        return {"ok": True, "result": {"species": list(reference_dyes(refresh=refresh).values())}}
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": str(exc)}


def register_services(dispatcher: Any) -> None:
    """Register the fcs_calculator RPC handlers with a ServiceDispatcher."""
    dispatcher.register("fcs_calculator.compute", lambda p: compute_handler(**p))
    dispatcher.register(
        "fcs_calculator.water_viscosity", lambda p: water_viscosity_handler(**p)
    )
    dispatcher.register(
        "fcs_calculator.reference_dyes", lambda p: reference_dyes_handler(**(p or {}))
    )
