"""ChiSurf execution adapters for MMFDB measurement services."""

from mmfdb.admin.backend.measurement_services import *  # noqa: F403


def run_burst_selection_handler(*args, **kwargs):
    from mmfdb.admin.backend.measurement_services import run_burst_selection_handler as handler

    from chisurf.plugins.burst.burst_selection.backend.services import analyze_files_handler

    return handler(*args, **kwargs, analyze_files=analyze_files_handler)
