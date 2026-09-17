"""Persisted state schema for the burst-wise FCS correlator plugin."""

from __future__ import annotations

import dataclasses
from typing import Any

from ..core.algorithms import BurstFcsSettings


@dataclasses.dataclass
class BurstFcsState:
    """Last-used settings and selected channel pairs."""

    settings: dict[str, Any] = dataclasses.field(
        default_factory=lambda: BurstFcsSettings().to_dict()
    )
    selected_pairs: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    detector_setup: str = ""

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> BurstFcsState:
        d = d or {}
        return cls(
            settings=dict(d.get("settings", {}) or BurstFcsSettings().to_dict()),
            selected_pairs=list(d.get("selected_pairs", []) or []),
            detector_setup=str(d.get("detector_setup", "")),
        )
