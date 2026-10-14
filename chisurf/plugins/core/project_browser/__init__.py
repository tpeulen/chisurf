from __future__ import annotations

# Plugin brand icon (unified emoji set)
icon = "📂"

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
else:
    name = "Tools:Open Project"

if __name__ == "__main__":
    from chisurf.emtk.__main__ import main as _launch

    _launch(["--plugin", "project_browser"])
