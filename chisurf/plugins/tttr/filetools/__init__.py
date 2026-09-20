"""File tools — combined NavigationPanelTool plugin.

A single unified window (left navigation, right panel) hosting the tools that
act on a *file* rather than on the physics inside it: converting between
containers, packing a measurement into a ``.pto`` and unpacking it again,
reading a container back, splitting a recording, and editing the header a vendor
wrote.

- TTTR Split / Convert     (tttr_splitter)
- TTTR → Time-Window BIDs  (tttr_time_windows)
- BID → Analysis           (bid_to_analysis)
- ⇄ .pto                   (tttr_to_pto)
- PTO Inspector            (pto_inspector)
- TTTR header editor       (tttr_header_edit)

Each sub-tool is embedded as-is; this plugin only provides the shared shell.
The individual tools stay importable and standalone-launchable but are hidden
from the ribbon menu (``menu_hidden``) so they appear only inside File tools.
"""

from __future__ import annotations

import json
from pathlib import Path

_manifest_path = Path(__file__).parent / "manifest.json"
_manifest = (
    json.loads(_manifest_path.read_text(encoding="utf-8")) if _manifest_path.exists() else {}
)
name = _manifest.get("display_name", "Tools:File tools")


def __getattr__(attr_name: str):
    """Lazy Qt import gate (no Qt import as a package side effect)."""
    if attr_name == "FileToolsTool":
        from .gui.tool import FileToolsTool as _cls

        globals()["FileToolsTool"] = _cls
        return _cls
    raise AttributeError(f"module {__name__!r} has no attribute {attr_name!r}")


if __name__ == "plugin":
    from .gui.tool import FileToolsTool

    window = FileToolsTool()
    window.show()


__all__ = ["FileToolsTool"]
