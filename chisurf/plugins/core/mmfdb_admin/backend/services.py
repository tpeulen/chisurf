"""ChiSurf service adapters for the host-neutral :mod:`mmfdb` backend."""

from mmfdb.admin.backend.services import *  # noqa: F403

from chisurf.core.mmfdb_services import register_services  # noqa: F401


def list_pipelines_handler(scope="all", auth=None):
    from mmfdb.admin.backend.services import list_pipelines_handler as handler

    from chisurf.core.pipeline import list_pipelines

    return handler(scope, auth, list_pipelines=list_pipelines)


def get_pipeline_handler(pipeline_id, auth=None):
    from mmfdb.admin.backend.services import get_pipeline_handler as handler

    from chisurf.core.pipeline import get_pipeline

    return handler(pipeline_id, auth, get_pipeline=get_pipeline)


def list_pipeline_runs_handler(pipeline_id=None, auth=None):
    from mmfdb.admin.backend.services import list_pipeline_runs_handler as handler

    from chisurf.core.pipeline import list_pipeline_runs

    return handler(pipeline_id, auth, list_pipeline_runs=list_pipeline_runs)
