"""ChiSurf-owned bindings for host-neutral MMFDB fit archiving."""

from __future__ import annotations

from typing import Any


def resolve_parameter_name(short_name: str) -> str | None:
    """Resolve a ChiSurf parameter name to its canonical flrCIF item id."""
    from chisurf.core import settings

    registry = getattr(settings, "parameter_registry", {})
    parameters = registry.get("parameters", registry) if isinstance(registry, dict) else {}
    entry = parameters.get(short_name) if isinstance(parameters, dict) else None
    value = entry.get("flrcif_item_id") if isinstance(entry, dict) else None
    return value if isinstance(value, str) and value else None


def archive_fit_to_mmfdb(db: Any, fit: Any, operation_id: str, **kwargs: Any) -> dict[str, Any]:
    """Archive a ChiSurf fit through MMFDB's explicitly injected host boundary."""
    from mmfdb.adapters.fit_archive import archive_fit_to_mmfdb as archive

    from chisurf.core.project.fit_state import fit_to_state

    return archive(
        db,
        fit,
        operation_id,
        fit_serializer=fit_to_state,
        parameter_name_resolver=resolve_parameter_name,
        **kwargs,
    )
