"""Persisted state schema for the FCS confocal calculator plugin."""

from __future__ import annotations

import dataclasses
from typing import Any


@dataclasses.dataclass
class ConfocalState:
    """Last-used calculator settings."""

    settings: dict[str, Any] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ConfocalState:
        return cls(settings=dict((d or {}).get("settings", {})))
