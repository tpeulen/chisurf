"""ChiSurf curation adapters for MMFDB fluorophore services."""

from mmfdb.admin.backend.fluorophore_services import *  # noqa: F403


def handle_run_ai_triage(*args, **kwargs):
    from mmfdb.admin.backend.fluorophore_services import handle_run_ai_triage as handler

    from chisurf.core.fluorescence.curation.ai_triage import run_deterministic_checks

    return handler(*args, **kwargs, deterministic_checks=run_deterministic_checks)
