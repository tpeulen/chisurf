"""TTTR Tools — hub of native emtk apps.

A single unified window (left navigation, right panel) that hosts the existing
TTTR file tools as embedded panels:

- ALEX Creator        (ptu_alex_creator)
- Micro-time Shifter  (tttr_microtime_shifter)
- TTTR Header Editor  (tttr_header_edit)
- (separator)
- Split / Convert     (tttr_splitter)

Each sub-tool opens as its own emtk app; this plugin only provides the shared hub.
The individual tools stay importable and standalone-launchable but are hidden
from the ribbon menu (``menu_hidden``) so they appear only inside TTTR Tools.
"""

from __future__ import annotations

import json
from pathlib import Path

_manifest_path = Path(__file__).parent / "manifest.json"
_manifest = (
    json.loads(_manifest_path.read_text(encoding="utf-8")) if _manifest_path.exists() else {}
)
name = _manifest.get("display_name", "Tools:Photon data:TTTR Tools")
