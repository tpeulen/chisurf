"""Data models for the Help plugin API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class HelpState:
    """Persistent plugin state."""

    current_path: str | None = None
    filter_text: str = ""
    edit_mode: bool = False


@dataclass
class HelpRequest:
    """Generic request envelope for help RPC calls."""

    method: str = ""
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class HelpResponse:
    """Generic response envelope from help RPC calls."""

    ok: bool = True
    result: Any = None
    error: str | None = None
    error_code: str | None = None
