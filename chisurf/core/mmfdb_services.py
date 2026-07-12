"""ChiSurf-owned service bindings for the standalone MMFDB package."""

from __future__ import annotations


def register_services(dispatcher_or_context):
    """Register MMFDB plus the ChiSurf-owned execution and browsing services."""
    from mmfdb.admin.backend.services import register_services as register_mmfdb_services

    from chisurf.core.fluorescence.curation.ai_triage import run_deterministic_checks
    from chisurf.core.pipeline import get_pipeline, list_pipeline_runs, list_pipelines
    from chisurf.plugins.burst.burst_selection.backend.services import analyze_files_handler

    register_mmfdb_services(
        dispatcher_or_context,
        burst_selection_runner=analyze_files_handler,
        deterministic_checks=run_deterministic_checks,
        pipeline_list=list_pipelines,
        pipeline_get=get_pipeline,
        pipeline_runs=list_pipeline_runs,
    )
