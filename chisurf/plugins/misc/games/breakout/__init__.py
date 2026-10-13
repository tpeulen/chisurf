"""Breakout Game Plugin

Classic Breakout game with progressive difficulty, multiple brick types,
mouse/keyboard control, and particle effects.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
name = _manifest.display_name if _manifest is not None else "Tools:Miscellaneous:Games:Breakout"


if __name__ == "__main__":
    from chisurf.emtk.__main__ import main as _launch

    _launch(["--plugin", "breakout"])

if __name__ == "plugin":  # pragma: no cover - the legacy macro launch; the manifest's emtk entry comes first
    from emtk.qt_host import ControlHost

    from chisurf.plugins.misc.games.breakout.app import make_app

    window = ControlHost(make_app())
    window.show()
