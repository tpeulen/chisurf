"""Help plugin state namespace."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class HelpPluginState:
    """Persistent state for the Help plugin."""

    current_path: str | None = None
    filter_text: str = ""
    edit_mode: bool = False
    window_geometry: dict[str, Any] | None = None
