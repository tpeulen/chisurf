"""Parse model for stopped-flow traces, as a view on BFF.

``models.yaml`` beside this module holds the standard relaxation forms; BFF
builds each as a competing structure over the trace's time axis.
"""

from __future__ import annotations

import pathlib

from chisurf.core.models.description import for_catalogue

ParseStoppedFlowModel = for_catalogue(
    pathlib.Path(__file__).parent / "models.yaml", name="Parse stopped-flow", module=__name__
)

__all__ = ["ParseStoppedFlowModel"]
