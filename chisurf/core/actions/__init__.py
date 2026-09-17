from __future__ import annotations

from chisurf.core.actions import (
    dataset_actions,
    fit_actions,
    model_actions,
    parameter_actions,
    project_actions,
)
from chisurf.core.actions._decorator import dispatch, is_dispatching
from chisurf.core.actions._infra import (
    ActionDispatcher,
    ActionRegistry,
    ActionSpec,
    build_default_dispatcher,
    canonical,
    get_action_catalog,
    invoke_action,
    record_action,
)

__all__ = [
    "dispatch",
    "is_dispatching",
    "ActionSpec",
    "ActionRegistry",
    "ActionDispatcher",
    "build_default_dispatcher",
    "record_action",
    "invoke_action",
    "get_action_catalog",
    "canonical",
]
