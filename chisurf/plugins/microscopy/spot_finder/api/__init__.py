"""Transport-agnostic API for the spot finder."""

from __future__ import annotations

from .models import RunRow, SpotFinderRequest, SpotFinderRunResult, SpotFinderSettings
from .spot_finder import detect_request, run_table

__all__ = [
    "RunRow",
    "SpotFinderRequest",
    "SpotFinderRunResult",
    "SpotFinderSettings",
    "detect_request",
    "run_table",
]
