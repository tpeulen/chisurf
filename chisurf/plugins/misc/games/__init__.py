"""A compact collection of games for ChiSurf."""

from __future__ import annotations

# Plugin brand icon (unified emoji set)
icon = "🎮"

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
name = _manifest.display_name if _manifest is not None else "Tools:System:Games"


def load():
    """Return the native Games hub app (:func:`.gui.app.make_app`)."""
    from .gui.app import make_app

    return make_app()


if __name__ == "__main__":
    from chisurf.emtk.__main__ import main as _launch

    _launch(["--plugin", "games"])

if __name__ == "plugin":  # pragma: no cover - the legacy macro launch; the manifest's emtk entry comes first
    from emtk.qt_host import ControlHost

    from chisurf.plugins.misc.games.gui.app import make_app

    window = ControlHost(make_app())
    window.show()
