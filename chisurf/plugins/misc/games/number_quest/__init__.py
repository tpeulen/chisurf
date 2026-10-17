"""Number Quest, a compact guessing-game plugin for ChiSurf."""

from __future__ import annotations

# Plugin brand icon (unified emoji set)
icon = "🔢"

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
name = _manifest.display_name if _manifest is not None else "Tools:Miscellaneous:Number Quest"


if __name__ == "__main__":
    from chisurf.emtk.__main__ import main as _launch

    _launch(["--plugin", "number_quest"])
