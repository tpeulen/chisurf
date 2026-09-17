"""Stopped-flow models: a user-supplied kinetic equation, or an explicit scheme."""

from __future__ import annotations

from chisurf.core.math.reaction.continuous import ReactionSystem
from chisurf.core.models.stopped_flow.parse import ParseStoppedFlowModel
from chisurf.core.models.stopped_flow.reaction import ReactionModel

__all__ = ["ParseStoppedFlowModel", "ReactionModel", "ReactionSystem"]
