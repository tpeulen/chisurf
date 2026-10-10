"""Structure Tools — combined NavigationPanelTool plugin.

A single unified window (left navigation, right panel) that hosts the existing
structure-modelling tools as embedded panels:

- FPS JSON Editor        (fps_json_editor)
- FRET Docking & Screening (fret)
- (separator)
- QuEst                  (quenching_estimator)
- HydroPro               (hydropro)
- (separator)
- Trajectory Tools       (traj_tools)

Each sub-tool is embedded as-is; this plugin only provides the shared shell.
"""

from __future__ import annotations

import json
from pathlib import Path

_manifest_path = Path(__file__).parent / "manifest.json"
_manifest = (
    json.loads(_manifest_path.read_text(encoding="utf-8")) if _manifest_path.exists() else {}
)
name = _manifest.get("display_name", "Structure:Modelling:Structure Tools")
