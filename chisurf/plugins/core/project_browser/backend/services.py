"""Local adapters to MMFDB's authoritative content-only project services."""

from __future__ import annotations

import base64
import uuid
from pathlib import Path
from typing import Any

from mmfdb.project import services as canonical_project_services
from mmfdb.store.database_resolver import resolve_database_path


def register_services(dispatcher: Any) -> None:
    """Register the same standalone service contract without server path adapters."""
    canonical_project_services.register_services(dispatcher, db_path=str(resolve_database_path()))


def save_project_handler(**params: Any) -> dict[str, Any]:
    """Bundle files at the local caller before invoking the content-only service."""
    from chisurf.plugins.core.project_browser.gui.client import project_resources

    params.setdefault("resource_bundle", project_resources(params.get("project_payload")))
    return canonical_project_services.save_project_handler(
        db_path=str(resolve_database_path()), **params
    )


def import_preview_handler(*, file_path: str | None = None, **params: Any) -> dict[str, Any]:
    """Read a local chooser file before previewing its bytes with MMFDB."""
    if file_path is not None:
        params["archive_base64"] = base64.b64encode(Path(file_path).read_bytes()).decode("ascii")
    return canonical_project_services.import_preview_handler(
        db_path=str(resolve_database_path()), **params
    )


def import_csp_handler(*, file_path: str | None = None, **params: Any) -> dict[str, Any]:
    """Read a local chooser file before importing its bytes with MMFDB."""
    if file_path is not None:
        params["archive_base64"] = base64.b64encode(Path(file_path).read_bytes()).decode("ascii")
    return canonical_project_services.import_csp_handler(
        db_path=str(resolve_database_path()), **params
    )


list_projects_handler = canonical_project_services.list_projects_handler
restore_project_handler = canonical_project_services.restore_project_handler
export_csp_handler = canonical_project_services.export_csp_handler
delete_version_handler = canonical_project_services.delete_version_handler
create_branch_handler = canonical_project_services.create_branch_handler
list_branches_handler = canonical_project_services.list_branches_handler
get_version_graph_handler = canonical_project_services.get_version_graph_handler
list_project_artifacts_handler = canonical_project_services.list_project_artifacts_handler
list_project_parameters_handler = canonical_project_services.list_project_parameters_handler


def _generate_id_remap(collisions: dict[str, list[str]]) -> dict[str, dict[str, str]]:
    remap: dict[str, dict[str, str]] = {
        "operations": {},
        "artifacts": {},
        "objects": {},
        "parameters": {},
    }
    for category, ids in collisions.items():
        for old_id in ids:
            remap[category][old_id] = f"{old_id[:4]}_{uuid.uuid4().hex[:12]}"
    return remap


def _apply_remap_to_export(
    export_meta: dict[str, Any], remap: dict[str, dict[str, str]]
) -> dict[str, Any]:
    import copy

    meta = copy.deepcopy(export_meta)
    deps = meta.setdefault("dependencies", {})

    ops_map = remap.get("operations", {})
    for op in deps.get("operations", []):
        oid = op.get("operation_id", "")
        if oid in ops_map:
            op["operation_id"] = ops_map[oid]
            op["_original_operation_id"] = oid

    arts_map = remap.get("artifacts", {})
    for art in deps.get("artifacts", []):
        for key in ("artifact_id", "processed_data_id", "raw_data_id"):
            aid = art.get(key, "")
            if aid in arts_map:
                art[key] = arts_map[aid]
                art["_original_id"] = aid
                break

    objs_map = remap.get("objects", {})
    for obj in deps.get("objects", []):
        ou = obj.get("object_uuid", "")
        if ou in objs_map:
            obj["object_uuid"] = objs_map[ou]
            obj["_original_object_uuid"] = ou

    params_map = remap.get("parameters", {})
    for param in deps.get("parameters", []):
        pu = param.get("parameter_uuid", param.get("parameter_id", ""))
        if pu in params_map:
            param["parameter_uuid"] = params_map[pu]
            param["_original_parameter_uuid"] = pu

    for edge in deps.get("provenance_edges", []):
        for key in ("source_node_id", "target_node_id", "processing_id"):
            val = edge.get(key, "")
            for category in ("operations", "artifacts", "parameters"):
                if val in remap.get(category, {}):
                    edge[key] = remap[category][val]
                    break

    return meta
