"""Converter — combined NavigationPanelTool plugin.

A single unified window (left navigation, right panel) that hosts the
conversion tools as embedded panels:

- TTTR Split / Convert     (tttr_splitter)
- TTTR → Time-Window BIDs  (tttr_time_windows)
- BID → Analysis           (bid_to_analysis)

Each sub-tool is embedded as-is; this plugin only provides the shared shell.
The individual tools stay importable and standalone-launchable but are hidden
from the ribbon menu (``menu_hidden``) so they appear only inside Converter.
"""

from __future__ import annotations

import json
from pathlib import Path

_manifest_path = Path(__file__).parent / "manifest.json"
_manifest = json.loads(_manifest_path.read_text()) if _manifest_path.exists() else {}
name = _manifest.get("display_name", "Tools:Converter")


def __getattr__(attr_name: str):
    """Lazy Qt import gate (PRD-23: no Qt import as a package side effect)."""
    if attr_name == "ConverterTool":
        from .gui.tool import ConverterTool as _cls

        globals()["ConverterTool"] = _cls
        return _cls
    raise AttributeError(f"module {__name__!r} has no attribute {attr_name!r}")


if __name__ == "plugin":
    from .gui.tool import ConverterTool

    window = ConverterTool()
    window.show()


__all__ = ["ConverterTool"]
